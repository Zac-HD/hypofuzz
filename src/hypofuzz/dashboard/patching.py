import threading
from collections import defaultdict
from collections.abc import Sequence
from queue import Empty, Queue
from typing import TYPE_CHECKING, Any, Literal, Optional

from hypothesis.extra._patching import get_patch_for, make_patch as _make_patch
from sortedcontainers import SortedList

from hypofuzz import __version__
from hypofuzz.database import Observation

if TYPE_CHECKING:
    from typing import TypeAlias

# we have a two tiered structure.
# * First, we store the list of test case reprs corresponding to the list of
#   @examples.
# * Each time we add a new such input, we compute the new patch for the entire
#   list.

# nodeid: {
#   "covering": list[observation.representation],
#   "failing": list[observation.representation],
# }
#
# We sort by string length, as a heuristic for putting simpler examples first in
# the patch.
EXAMPLES: dict[str, dict[str, SortedList[str]]] = defaultdict(
    lambda: {"covering": SortedList(key=len), "failing": SortedList(key=len)}
)
# nodeid: {
#   "covering": patch,
#   "failing": patch,
# }
PATCHES: dict[str, dict[str, Optional[str]]] = defaultdict(
    lambda: {"covering": None, "failing": None}
)
VIA = {"covering": "covering example", "failing": "discovered failure"}
COMMIT_MESSAGE = {
    "covering": "add covering examples",
    "failing": "add failing examples",
}

ObservationTypeT: "TypeAlias" = Literal["covering", "failing"]
_queue: Queue[tuple[Any, str, Observation, ObservationTypeT]] = Queue()
_thread: Optional[threading.Thread] = None


def add_patch(
    *,
    test_function: Any,
    nodeid: str,
    observation: Observation,
    observation_type: ObservationTypeT,
) -> None:
    _queue.put((test_function, nodeid, observation, observation_type))


def make_patch(
    function: Any, examples: Sequence[str], observation_type: ObservationTypeT
) -> Optional[str]:
    via = VIA[observation_type]
    triple = get_patch_for(function, examples=[(example, via) for example in examples])
    if triple is None:
        return None

    commit_message = COMMIT_MESSAGE[observation_type]
    return _make_patch(
        (triple,),
        msg=commit_message,
        author=f"HypoFuzz {__version__} <no-reply@hypofuzz.com>",
    )


def _worker() -> None:
    # TODO We might optimize this by checking each function ahead of time for known
    # reasons why a patch would fail, for instance using st.data in the signature,
    # and then early-returning here before calling get_patch_for.
    while True:
        try:
            test_function, nodeid, observation, observation_type = _queue.get(
                timeout=1.0
            )
        except Empty:
            continue

        examples = EXAMPLES[nodeid][observation_type]
        examples.add(observation.representation)
        PATCHES[nodeid][observation_type] = make_patch(
            test_function, examples, observation_type
        )

        _queue.task_done()


def start_patching_thread() -> None:
    global _thread
    assert _thread is None

    _thread = threading.Thread(target=_worker, daemon=True)
    _thread.start()


def failing_patch(nodeid: str) -> Optional[str]:
    return PATCHES[nodeid]["failing"]


def covering_patch(nodeid: str) -> Optional[str]:
    return PATCHES[nodeid]["covering"]
