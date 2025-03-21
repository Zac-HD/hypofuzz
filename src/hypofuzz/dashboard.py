"""Live web dashboard for a fuzzing run."""

import abc
import json
import math
import time
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
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect
from trio import MemoryReceiveChannel

from hypofuzz.database import Metadata, Report, get_db, metadata_key, reports_key
from hypofuzz.patching import make_and_save_patches


class HypofuzzEncoder(json.JSONEncoder):
    def default(self, obj: object) -> object:
        if isinstance(obj, SortedList):
            return list(obj)
        return super().default(obj)


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
        self, reports: dict[str, list[Report]], metadata: dict[str, Metadata]
    ) -> None:
        pass

    @abc.abstractmethod
    async def on_event(self, event_type: str, data: Any) -> None:
        pass


class OverviewWebsocket(HypofuzzWebsocket):
    async def initial(
        self, reports: dict[str, list[Report]], metadata: dict[str, Metadata]
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
        self, reports: dict[str, list[Report]], metadata: dict[str, Metadata]
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
            node_id = data["nodeid"]
            if node_id != self.node_id:
                return
            await self.send_json({"type": "save", "data": data})

        if event_type == "metadata":
            node_id = data["nodeid"]
            if node_id != self.node_id:
                return
            await self.send_json({"type": "metadata", "data": data})

        # TODO handle delete and refresh events


REPORTS: dict[str, SortedList[Report]] = defaultdict(
    lambda: SortedList(key=lambda r: r["elapsed_time"])
)
METADATA: dict[str, Metadata] = {}
PYTEST_ARGS: Optional[list[str]] = None
websockets: set[HypofuzzWebsocket] = set()
delete_debounce = 300
refreshed_at: dict[bytes, float] = defaultdict(int)


async def websocket(websocket: WebSocket) -> None:
    websocket = (
        TestWebsocket(websocket, node_id)
        if (node_id := websocket.query_params.get("node_id"))
        else OverviewWebsocket(websocket)
    )
    await websocket.accept()
    websockets.add(websocket)
    await websocket.initial(REPORTS, METADATA)

    try:
        while True:
            await websocket.receive_json()
    except WebSocketDisconnect:
        websockets.remove(websocket)


async def broadcast_event(event_type: str, data: dict) -> None:
    for websocket in websockets:
        await websocket.on_event(event_type, data)


def try_format(code: str) -> str:
    try:
        return black.format_str(code, mode=black.FileMode())
    except Exception:
        return code


async def api_tests(request: Request) -> Response:
    # ideally we'd use HypofuzzEncoder here, but JSONResponse doesn't accept an encoder
    reports = {node_id: list(reports) for node_id, reports in REPORTS.items()}
    return JSONResponse(reports)


async def api_test(request: Request) -> Response:
    node_id = request.path_params["node_id"]
    return JSONResponse(list(REPORTS[node_id]))


async def api_patches(request: Request) -> Response:
    patches = make_and_save_patches(PYTEST_ARGS, REPORTS, METADATA)

    return JSONResponse(
        {name: str(patch_path.read_text()) for name, patch_path in patches.items()}
    )


def pycrunch_path(node_id: str) -> Path:
    node_id = "".join(c if c.isalnum() else "_" for c in node_id).rstrip("_")
    return Path("pycrunch-recordings") / node_id / "session.chunked.pycrunch-trace"


async def api_pycrunch_available(request: Request) -> Response:
    path = pycrunch_path(request.path_params["node_id"])
    return JSONResponse({"available": path.exists()})


async def api_pycrunch_file(request: Request) -> Response:
    path = pycrunch_path(request.path_params["node_id"])
    if not path.exists():
        return Response(status_code=404)

    return FileResponse(path=path, media_type="application/octet-stream")


dist = Path(__file__).parent / "frontend" / "dist"
dist.mkdir(exist_ok=True)
routes = [
    WebSocketRoute("/ws", websocket),
    Route("/api/tests/", api_tests),
    Route("/api/tests/{node_id:path}", api_test),
    Route("/api/patches/", api_patches),
    Route(
        "/api/pycrunch/{node_id:path}/session.chunked.pycrunch-trace", api_pycrunch_file
    ),
    Route("/api/pycrunch/{node_id:path}", api_pycrunch_available),
    Mount("/assets", StaticFiles(directory=dist / "assets")),
    # catchall fallback. react will handle the routing of dynamic urls here,
    # such as to a node id.
    Route("/{path:path}", FileResponse(dist / "index.html")),
]

middleware = [
    # allow pytrace to request pycrunch recordings for the web interface
    Middleware(
        CORSMiddleware,
        allow_origins=["https://app.pytrace.com"],
    )
]
app = Starlette(routes=routes, middleware=middleware)


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
                report = json.loads(value)
                REPORTS[report["nodeid"]].add(report)
                await broadcast_event("save", report)
            if key.endswith(metadata_key):
                metadata = json.loads(value)
                METADATA[metadata["nodeid"]] = metadata
                await broadcast_event("metadata", metadata)

        if event_type == "delete":
            key, value = args

            if key.endswith(reports_key):
                key = key.rstrip(reports_key)
                if value is not None:
                    report = json.loads(value)
                    REPORTS[report["nodeid"]].remove(report)
                    await broadcast_event("delete", report)
                else:
                    # debounce each key, to relieve db read pressure for this expensive
                    # re-scan. Deletions aren't important for correctness, just
                    # performance / memory.
                    if time.time() - refreshed_at[key] > delete_debounce:
                        reports = SortedList(
                            list(get_db().fetch_reports(key)),
                            key=lambda r: r["elapsed_time"],
                        )
                        if reports:
                            node_id = reports[0]["nodeid"]
                            REPORTS[node_id] = reports
                            await broadcast_event("refresh", reports)
                        refreshed_at[key] = time.time()

            # We're only keeping a reference to the latest metadata, so we don't need
            # to bother handling deletion events for it, just save.


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
            node_id = reports[0]["nodeid"]
            REPORTS[node_id] = SortedList(reports, key=lambda r: r["elapsed_time"])
        if metadata:
            node_id = metadata[0]["nodeid"]
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
    PYTEST_ARGS = pytest_args

    # we run a pytest collection step for the dashboard to pick up on databases
    # from custom profiles.
    _get_hypothesis_tests_with_pytest(pytest_args)

    print(f"\n\tNow serving dashboard at  http://{host}:{port}/\n")
    trio.run(run_dashboard, port, host)
