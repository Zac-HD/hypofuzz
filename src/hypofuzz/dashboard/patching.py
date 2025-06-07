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
    fuzz_targets: list[FuzzProcess],
    tests: dict[str, "Test"],
    *,
    canonical: bool = True,
) -> dict[str, Path]:
    triples_all: list = []
    triples_cov: list = []
    triples_fail: list = []

    test_functions = {t.nodeid: t._test_fn for t in fuzz_targets}
    for nodeid, test in tests.items():
        # for each func
        #   - only strip_via if replay is complete
        #   - only add failing if not currently shrinking
        #   - tag covering examples with covering-via
        assert nodeid in test_functions
        test_fn = test_functions[nodeid]

        failing_examples = []
        covering_examples = []

        if test.failure:
            failing_examples.append((test.failure.metadata.traceback, FAIL_MSG))

        if test.phase is not Phase.REPLAY:
            covering_examples = [
                (observation.representation, COV_MSG)
                for observation in test.corpus_observations
            ]

        for out, examples, strip_via in [
            (triples_fail, failing_examples, ()),
            (triples_cov, covering_examples, (COV_MSG,)),
            (triples_all, failing_examples + covering_examples, (COV_MSG,)),
        ]:
            if examples:
                xs = get_patch_for_cached(test_fn, tuple(examples), strip_via=strip_via)  # type: ignore
                if xs:
                    out.append(xs)

    result = {}
    for key, triples in [
        ("all", triples_all),
        ("cov", triples_cov),
        ("fail", triples_fail),
    ]:
        if triples:
            patch = make_patch_cached(tuple(sorted(triples)))
            result[key] = save_patch(patch, slug="hypofuzz-")
            # Note that these canonical-latest locations *must* remain stable,
            # making it practical to upload them as artifacts from CI systems.
            if canonical:
                latest = storage_directory("patches", f"latest_hypofuzz_{key}.patch")
                shutil.copy(result[key], latest)
    return result
