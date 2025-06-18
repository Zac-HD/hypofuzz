import threading
from collections import defaultdict
from functools import lru_cache
from queue import Empty, Queue
from typing import Any, Literal, Optional

from hypothesis.extra._patching import (
    get_patch_for as _get_patch_for,
    make_patch as _make_patch,
)

from hypofuzz import __version__
from hypofuzz.database import Observation

COVERING_VIA = "covering example"
FAILING_VIA = "discovered failure"
# nodeid: {
#   "covering": [(fname, before, after), ...],
#   "failing": [(fname, before, after), ...],
# }
# TODO this duplicates the test function contents in `before` and `after`,
# we probably want a more memory-efficient representation eventually
# (and a smaller win: map fname to a list of (before, after), instead of storing
# each fname)
PATCHES: dict[str, dict[str, list[tuple[str, str, str]]]] = defaultdict(
    lambda: {"covering": [], "failing": []}
)
get_patch_for = lru_cache(maxsize=8192)(_get_patch_for)

_queue: Queue = Queue()
_thread: Optional[threading.Thread] = None


def add_patch(
    *,
    test_function: Any,
    nodeid: str,
    observation: Observation,
    observation_type: Literal["covering", "failing"],
) -> None:
    _queue.put((test_function, nodeid, observation, observation_type))


@lru_cache(maxsize=1024)
def make_patch(triples: tuple[tuple[str, str, str]], *, msg: str) -> str:
    return _make_patch(
        triples,
        msg=msg,
        author=f"HypoFuzz {__version__} <no-reply@hypofuzz.com>",
    )


def failing_patch(nodeid: str) -> Optional[str]:
    failing = PATCHES[nodeid]["failing"]
    return make_patch(tuple(failing), msg="add failing examples") if failing else None


def covering_patch(nodeid: str) -> Optional[str]:
    covering = PATCHES[nodeid]["covering"]
    return (
        make_patch(tuple(covering), msg="add covering examples") if covering else None
    )


def _worker() -> None:
    while True:
        try:
            item = _queue.get(timeout=1.0)
        except Empty:
            continue

        test_function, nodeid, observation, observation_type = item

        via = COVERING_VIA if observation_type == "covering" else FAILING_VIA
        # If this thread ends up using significant resources, we might optimize
        # this by checking each function ahead of time for known reasons why a
        # patch would fail, for instance using st.data in the signature, and then
        # simply discarding those here entirely.
        patch = get_patch_for(
            test_function, ((observation.representation, via),), strip_via=via
        )
        if patch is not None:
            PATCHES[nodeid][observation_type].append(patch)
        _queue.task_done()


def start_patching_thread() -> None:
    global _thread
    assert _thread is None

    _thread = threading.Thread(target=_worker, daemon=True)
    _thread.start()
