"""Live web dashboard for a fuzzing run."""

import atexit
import signal
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

import black
import trio
from hypercorn.config import Config
from hypercorn.trio import serve
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from .database import get_db
from .patching import make_and_save_patches

DATA_TO_PLOT: dict = {}
LAST_UPDATE: dict = {}
PYTEST_ARGS: Optional[list[str]] = None
active_connections: set[WebSocket] = set()


async def websocket(websocket: WebSocket) -> None:
    await websocket.accept()
    active_connections.add(websocket)
    try:
        while True:
            await websocket.receive_json()
    except WebSocketDisconnect:
        active_connections.remove(websocket)


async def broadcast_update(data: dict) -> None:
    # copy since we might modify it
    for connection in set(active_connections):
        try:
            await connection.send_json(data)
        except WebSocketDisconnect:
            active_connections.remove(connection)


def try_format(code: str) -> str:
    try:
        return black.format_str(code, mode=black.FileMode())
    except Exception:
        return code


async def api_tests(request: Request) -> Response:
    return JSONResponse(DATA_TO_PLOT)


async def api_test(request: Request) -> Response:
    node_id = request.path_params["node_id"]
    return JSONResponse(DATA_TO_PLOT[node_id])


async def api_patches(request: Request) -> Response:
    patches = make_and_save_patches(PYTEST_ARGS, LAST_UPDATE)

    return JSONResponse(
        {name: str(patch_path.read_text()) for name, patch_path in patches.items()}
    )


async def pycrunch_file(request: Request) -> Response:
    name = request.path_params["name"]
    return FileResponse(Path("pycrunch-recordings") / name)


async def poll_database_forever() -> None:
    previous_data = None
    while True:
        await poll_database()
        # TODO use hypothesis db listening
        if DATA_TO_PLOT != previous_data:
            await broadcast_update(DATA_TO_PLOT)
            previous_data = dict(DATA_TO_PLOT)
        await trio.sleep(1)


async def poll_database() -> None:
    global DATA_TO_PLOT

    db = get_db()
    data: list = []
    for key in db.fetch(b"hypofuzz-test-keys"):
        data.extend(db.fetch_metadata(key))
    data.sort(key=lambda d: d["elapsed_time"])

    DATA_TO_PLOT = defaultdict(list)
    for d in data:
        DATA_TO_PLOT[d["nodeid"]].append(d)
        LAST_UPDATE[d["nodeid"]] = d
    DATA_TO_PLOT = dict(DATA_TO_PLOT)


dist = Path(__file__).parent / "frontend" / "dist"
dist.mkdir(exist_ok=True)
routes = [
    WebSocketRoute("/ws", websocket),
    Route("/api/tests/", api_tests),
    Route("/api/tests/{node_id:path}", api_test),
    Route("/api/patches/", api_patches),
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


async def run_dashboard(port: int, host: str) -> None:
    async with trio.open_nursery() as nursery:
        nursery.start_soon(poll_database_forever)
        nursery.start_soon(serve_app, app, host, port)


def start_dashboard_process(
    port: int, *, pytest_args: list, host: str = "localhost"
) -> None:
    from .interface import _get_hypothesis_tests_with_pytest

    global PYTEST_ARGS
    PYTEST_ARGS = pytest_args

    # we run a pytest collection step for the dashboard to pick up on databases
    # from custom profiles.
    _get_hypothesis_tests_with_pytest(pytest_args)

    # Ensure that we dump whatever patches are ready before shutting down
    def signal_handler(signum, frame):  # type: ignore
        make_and_save_patches(pytest_args, LAST_UPDATE)
        if old_handler in (signal.SIG_DFL, None):
            return old_handler
        elif old_handler is not signal.SIG_IGN:
            return old_handler(signum, frame)
        raise NotImplementedError("Unreachable")

    old_handler = signal.signal(signal.SIGTERM, signal_handler)
    atexit.register(make_and_save_patches, pytest_args, LAST_UPDATE)

    print(f"\n\tNow serving dashboard at  http://{host}:{port}/\n")
    trio.run(run_dashboard, port, host)
