"""Live web dashboard for a fuzzing run."""

import abc
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import black
import trio
from hypercorn.config import Config
from hypercorn.trio import serve
from hypothesis.database import ListenerEventT
from sortedcontainers import SortedList
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
from trio import MemoryReceiveChannel

from hypofuzz.database import (
    HypofuzzEncoder,
    LinearReports,
    Metadata,
    Report,
    get_db,
    linearize_reports,
    metadata_key,
    reports_key,
)
from hypofuzz.interface import CollectionResult
from hypofuzz.patching import make_and_save_patches


class HypofuzzJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        # arguments copied from starlette.JSONResponse, with the addition of
        # cls=HypofuzzEncoder
        return json.dumps(
            content,
            ensure_ascii=False,
            allow_nan=False,
            indent=None,
            separators=(",", ":"),
            cls=HypofuzzEncoder,
        ).encode("utf-8")


class HypofuzzWebsocket(abc.ABC):
    def __init__(self, websocket: WebSocket) -> None:
        self.websocket = websocket

    async def accept(self) -> None:
        await self.websocket.accept()

    async def receive_json(self) -> None:
        await self.websocket.receive_json()

    async def send_json(self, data: Any) -> None:
        await self.websocket.send_text(json.dumps(data, cls=HypofuzzEncoder))

    @abc.abstractmethod
    async def initial(
        self, reports: dict[str, LinearReports], metadata: dict[str, Metadata]
    ) -> None:
        pass

    @abc.abstractmethod
    async def on_event(self, event_type: str, data: Any) -> None:
        pass


class OverviewWebsocket(HypofuzzWebsocket):
    async def initial(
        self, reports: dict[str, LinearReports], metadata: dict[str, Metadata]
    ) -> None:
        await self.send_json(
            {"type": "initial", "reports": reports, "metadata": metadata}
        )

    async def on_event(self, event_type: str, data: Any) -> None:
        if event_type == "save":
            await self.send_json({"type": "save", "data": data})


class TestWebsocket(HypofuzzWebsocket):
    def __init__(self, websocket: WebSocket, node_id: str) -> None:
        super().__init__(websocket)
        self.node_id = node_id

    async def initial(
        self, reports: dict[str, LinearReports], metadata: dict[str, Metadata]
    ) -> None:
        # match same shape as overview for now (mapping of node id to data)
        # TODO refactor this, drop the nesting and fix the types typescript-side
        await self.send_json(
            {
                "type": "initial",
                "reports": {self.node_id: reports[self.node_id]},
                "metadata": {self.node_id: metadata[self.node_id]},
            }
        )

    async def on_event(self, event_type: str, data: Any) -> None:
        if event_type == "save":
            node_id = data.nodeid
            if node_id != self.node_id:
                return
            await self.send_json({"type": "save", "data": data})

        if event_type == "metadata":
            node_id = data.nodeid
            if node_id != self.node_id:
                return
            await self.send_json({"type": "metadata", "data": data})

        # TODO handle delete and refresh events


REPORTS: dict[str, SortedList[Report]] = defaultdict(
    lambda: SortedList(key=lambda r: r.elapsed_time)
)
METADATA: dict[str, Metadata] = {}
COLLECTION_RESULT: Optional[CollectionResult] = None
PYTEST_ARGS: Optional[list[str]] = None
websockets: set[HypofuzzWebsocket] = set()


async def websocket(websocket: WebSocket) -> None:
    websocket = (
        TestWebsocket(websocket, node_id)
        if (node_id := websocket.query_params.get("node_id"))
        else OverviewWebsocket(websocket)
    )
    await websocket.accept()
    websockets.add(websocket)

    reports = {
        node_id: linearize_reports(reports) for node_id, reports in REPORTS.items()
    }
    await websocket.initial(reports, METADATA)

    try:
        while True:
            await websocket.receive_json()
    except WebSocketDisconnect:
        websockets.remove(websocket)


async def broadcast_event(event_type: str, data: Any) -> None:
    for websocket in websockets:
        await websocket.on_event(event_type, data)


def try_format(code: str) -> str:
    try:
        return black.format_str(code, mode=black.FileMode())
    except Exception:
        return code


async def api_tests(request: Request) -> Response:
    return HypofuzzJSONResponse(
        {node_id: list(reports) for node_id, reports in REPORTS.items()}
    )


async def api_test(request: Request) -> Response:
    node_id = request.path_params["node_id"]
    return HypofuzzJSONResponse(list(REPORTS[node_id]))


async def api_patches(request: Request) -> Response:
    patches = make_and_save_patches(PYTEST_ARGS, REPORTS, METADATA)

    return HypofuzzJSONResponse(
        {name: str(patch_path.read_text()) for name, patch_path in patches.items()}
    )


async def api_collected_tests(request: Request) -> Response:
    assert COLLECTION_RESULT is not None

    collection_status = [
        {"node_id": target.nodeid, "status": "collected"}
        for target in COLLECTION_RESULT.fuzz_targets
    ]
    for node_id, item in COLLECTION_RESULT.not_collected.items():
        collection_status.append(
            {
                "node_id": node_id,
                "status": "not_collected",
                "status_reason": item["status_reason"],
            }
        )

    return HypofuzzJSONResponse({"collection_status": collection_status})


async def api_backing_state(request: Request) -> Response:
    # get the backing state of the dashboard, suitable for use by
    # dashboard_state.json.
    # The data returned here looks very similar to other endpoints for now, but
    # I'm keeping it separate because the data required to back a dashboard may
    # change over time.
    reports = {
        node_id: linearize_reports(reports) for node_id, reports in REPORTS.items()
    }
    return HypofuzzJSONResponse(
        {"reports": reports, "metadata": METADATA},
    )


dist = Path(__file__).parent / "frontend" / "dist"
dist.mkdir(exist_ok=True)
routes = [
    WebSocketRoute("/ws", websocket),
    Route("/api/tests/", api_tests),
    Route("/api/tests/{node_id:path}", api_test),
    Route("/api/patches/", api_patches),
    Route("/api/collected_tests/", api_collected_tests),
    Route("/api/backing_state/", api_backing_state),
    Mount("/assets", StaticFiles(directory=dist / "assets")),
    # catchall fallback. react will handle the routing of dynamic urls here,
    # such as to a node id.
    Route("/{path:path}", FileResponse(dist / "index.html")),
]
app = Starlette(routes=routes)


async def serve_app(app: Any, host: str, port: str) -> None:
    config = Config()
    config.bind = [f"{host}:{port}"]
    await serve(app, config)


async def handle_event(receive_channel: MemoryReceiveChannel) -> None:
    async for event_type, args in receive_channel:
        if event_type == "save":
            key, value = args
            assert value is not None
            if key.endswith(reports_key):
                report = Report.from_dict(json.loads(value))
                REPORTS[report.nodeid].add(report)
                await broadcast_event("save", report)
            if key.endswith(metadata_key):
                metadata = Metadata.from_dict(json.loads(value))
                METADATA[metadata.nodeid] = metadata
                await broadcast_event("metadata", metadata)

        # We're only keeping a reference to the latest metadata, so we don't need
        # to bother handling deletion events for it, just save.

        # we'll want to send the relinearized history to the dashboard every now
        # and then (via the "refresh" event), to avoid falling too far out of sync.
        # Unclear whether we want this on a long debounce for any arbitrary event,
        # or on a timer.


async def run_dashboard(port: int, host: str) -> None:
    send_channel, receive_channel = trio.open_memory_channel[ListenerEventT](math.inf)
    token = trio.lowlevel.current_trio_token()

    def send_nowait_from_anywhere(msg: ListenerEventT) -> None:
        # DirectoryBasedExampleDatabase sends events from a background thread (via watchdog),
        # so we need to support sending from anywhere, i.e. whether or not the calling thread
        # has any Trio state.  We can do that with the following branch:
        try:
            trio.lowlevel.current_task()
        except RuntimeError:
            trio.from_thread.run_sync(send_channel.send_nowait, msg, trio_token=token)
        else:
            send_channel.send_nowait(msg)

    db = get_db()
    # load initial database state before starting dashboard
    for key in db.fetch(b"hypofuzz-test-keys"):
        reports = db.fetch_reports(key)
        metadata = db.fetch_metadata(key)
        if reports:
            # TODO we should really add the node id to hypofuzz-test-keys entries
            node_id = reports[0].nodeid
            REPORTS[node_id] = SortedList(reports, key=lambda r: r.elapsed_time)
        if metadata:
            node_id = metadata[0].nodeid
            # there is usually only a single metadata, unless we updated right
            # as the db is inserting a new one. TODO take latest by
            # elapsed_time, when we have Metadata extend Report
            METADATA[node_id] = metadata[0]

    db._db.add_listener(send_nowait_from_anywhere)
    async with trio.open_nursery() as nursery:
        nursery.start_soon(serve_app, app, host, port)  # type: ignore
        nursery.start_soon(handle_event, receive_channel)


def start_dashboard_process(
    port: int, *, pytest_args: list, host: str = "localhost"
) -> None:
    from hypofuzz.interface import _get_hypothesis_tests_with_pytest

    global PYTEST_ARGS
    global COLLECTION_RESULT
    PYTEST_ARGS = pytest_args

    # we run a pytest collection step for the dashboard to pick up on databases
    # from custom profiles, and to figure out what tests are available.
    COLLECTION_RESULT = _get_hypothesis_tests_with_pytest(pytest_args)

    print(f"\n\tNow serving dashboard at  http://{host}:{port}/\n")
    trio.run(run_dashboard, port, host)
