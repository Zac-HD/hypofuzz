import shutil
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

from hypothesis.configuration import storage_directory
from hypothesis.extra._patching import FAIL_MSG, get_patch_for, make_patch, save_patch

from hypofuzz.database import Phase
from hypofuzz.hypofuzz import FuzzProcess

if TYPE_CHECKING:
    from hypofuzz.dashboard.test import Test

COV_MSG = "HypoFuzz covering example"
get_patch_for_cached = lru_cache(maxsize=8192)(get_patch_for)
make_patch_cached = lru_cache(maxsize=1024)(make_patch)


def make_and_save_patches(
    fuzz_target: FuzzProcess,
    test: "Test",
    *,
    canonical: bool = True,
) -> dict[str, Path]:
    triples_covering: list = []
    triples_failing: list = []

    # - only strip_via if replay is complete
    # - only add failing if not currently shrinking
    # - tag covering examples with covering-via

    failing_examples = []
    covering_examples = []

    if test.failure:
        failing_examples.append((test.failure.representation, FAIL_MSG))

    if test.phase is not Phase.REPLAY:
        covering_examples = [
            (observation.representation, COV_MSG)
            for observation in test.corpus_observations
        ]

    for triples, examples, strip_via in [
        (triples_failing, failing_examples, ()),
        (triples_covering, covering_examples, (COV_MSG,)),
    ]:
        if examples:
            patch = get_patch_for_cached(
                fuzz_target._test_fn, tuple(examples), strip_via=strip_via
            )
            if patch:
                triples.append(patch)

    result = {}
    for key, triples in [
        ("covering", triples_covering),
        ("failing", triples_failing),
    ]:
        if triples:
            patch = make_patch_cached(tuple(sorted(triples)), msg=f"add {key} examples")
            result[key] = save_patch(patch, slug="hypofuzz-")
            # Note that these canonical-latest locations *must* remain stable,
            # making it practical to upload them as artifacts from CI systems.
            if canonical:
                latest = storage_directory("patches", f"latest_hypofuzz_{key}.patch")
                shutil.copy(result[key], latest)
    return result
