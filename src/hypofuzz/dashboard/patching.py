from functools import lru_cache
from typing import Callable, Optional

from hypothesis.extra._patching import (
    get_patch_for as _get_patch_for,
    make_patch as _make_patch,
)

from hypofuzz import __version__
from hypofuzz.database import Observation

COVERING_VIA = "covering example"
FAILING_VIA = "discovered failure"

get_patch_for = lru_cache(maxsize=8192)(_get_patch_for)


@lru_cache(maxsize=1024)
def make_patch(triples: tuple[tuple[str, str, str]], *, msg: str) -> str:
    return _make_patch(
        triples,
        msg=msg,
        author=f"HypoFuzz {__version__} <no-reply@hypofuzz.com>",
    )


def failing_patch(test_function: Callable, failure: Observation) -> Optional[str]:
    triple = get_patch_for(
        test_function, ((failure.representation, FAILING_VIA),), strip_via=FAILING_VIA
    )
    if not triple:
        return None

    return make_patch((triple,), msg=f"add failing example")


def covering_patch(
    test_function: Callable, observations: list[Observation]
) -> Optional[str]:
    triple = get_patch_for(
        test_function,
        tuple(
            (observation.representation, COVERING_VIA)
            for observation in sorted(observations, key=lambda obs: obs.representation)
        ),
        strip_via=COVERING_VIA,
    )

    if not triple:
        return None

    return make_patch((triple,), msg="add covering examples")
