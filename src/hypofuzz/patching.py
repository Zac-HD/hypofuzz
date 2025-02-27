import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

from hypothesis.configuration import storage_directory
from hypothesis.extra._patching import FAIL_MSG, get_patch_for, make_patch, save_patch

COV_MSG = "HypoFuzz covering example"
get_patch_for_cached = lru_cache(maxsize=8192)(get_patch_for)
make_patch_cached = lru_cache(maxsize=1024)(make_patch)


@lru_cache
def get_all_tests(pytest_args: Any) -> list:
    from .interface import _get_hypothesis_tests_with_pytest

    return _get_hypothesis_tests_with_pytest(pytest_args)


def make_and_save_patches(
    pytest_args: Any, reports: dict, metadata: dict, *, canonical: bool = True
) -> dict[str, Path]:
    triples_all: list = []
    triples_cov: list = []
    triples_fail: list = []

    tests = {t.nodeid: t._test_fn for t in get_all_tests(pytest_args)}
    for nodeid, test_fn in tests.items():
        report = reports[nodeid][-1]
        node_metadata = metadata[nodeid]
        # for each func
        #   - only strip_via if replay is complete
        #   - only add failing if not currently shrinking
        #   - tag covering examples with covering-via
        failing_examples = []
        covering_examples = []
        if (
            node_metadata.get("failures")
            and report.get("note") != "shrinking known examples"
        ):
            failing_examples = [
                (ex, FAIL_MSG) for ex, _, _, _ in node_metadata["failures"]
            ]
        if (
            node_metadata.get("seed_pool")
            and report.get("note") != "replaying saved examples"
        ):
            covering_examples = [
                (ex, COV_MSG) for _, ex, _ in node_metadata["seed_pool"]
            ]

        for out, examples, strip_via in [
            (triples_fail, failing_examples, ()),
            (triples_cov, covering_examples, (COV_MSG,)),
            (triples_all, failing_examples + covering_examples, (COV_MSG,)),
        ]:
            if examples:
                xs = get_patch_for_cached(test_fn, tuple(examples), strip_via=strip_via)
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
