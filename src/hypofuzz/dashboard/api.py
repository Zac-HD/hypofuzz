import json
from typing import Any, Optional

import black
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from hypofuzz.dashboard.models import (
    dashboard_observation,
    dashboard_report,
    dashboard_test,
)
from hypofuzz.dashboard.patching import (
    covering_patch,
    failing_patch,
)
from hypofuzz.database import HypofuzzEncoder
from hypofuzz.utils import convert_to_fuzzjson


class HypofuzzJSONResponse(JSONResponse):
    def render(self, content: Any) -> bytes:
        data = json.dumps(
            convert_to_fuzzjson(content),
            ensure_ascii=False,
            separators=(",", ":"),
            cls=HypofuzzEncoder,
        )
        return data.encode("utf-8", errors="surrogatepass")


def try_format(code: str) -> str:
    try:
        return black.format_str(code, mode=black.FileMode())
    except Exception:
        return code


async def api_tests(request: Request) -> Response:
    from hypofuzz.dashboard.dashboard import TESTS

    return HypofuzzJSONResponse(
        {nodeid: dashboard_test(test) for nodeid, test in TESTS.items()}
    )


async def api_test(request: Request) -> Response:
    from hypofuzz.dashboard.dashboard import TESTS

    nodeid = request.path_params["nodeid"]
    return HypofuzzJSONResponse(dashboard_test(TESTS[nodeid]))


def _patches() -> dict[str, dict[str, Optional[str]]]:
    from hypofuzz.dashboard.dashboard import COLLECTION_RESULT

    assert COLLECTION_RESULT is not None
    return {
        target.nodeid: {
            "failing": failing_patch(target.nodeid),
            "covering": covering_patch(target.nodeid),
        }
        for target in COLLECTION_RESULT.fuzz_targets
    }


async def api_patches(request: Request) -> Response:
    return HypofuzzJSONResponse(_patches())


async def api_available_patches(request: Request) -> Response:
    # returns the nodeids with available patches
    from hypofuzz.dashboard.patching import PATCHES

    nodeids = [
        nodeid
        for nodeid, patches in PATCHES.items()
        if patches["failing"] or patches["covering"]
    ]
    return HypofuzzJSONResponse(nodeids)


async def api_patch(request: Request) -> Response:
    from hypofuzz.dashboard.dashboard import COLLECTION_RESULT, TESTS

    assert COLLECTION_RESULT is not None
    nodeid = request.path_params["nodeid"]
    if nodeid not in TESTS:
        return Response(status_code=404)

    return HypofuzzJSONResponse(
        {"failing": failing_patch(nodeid), "covering": covering_patch(nodeid)}
    )


def _collection_status() -> list[dict[str, Any]]:
    from hypofuzz.dashboard.dashboard import COLLECTION_RESULT

    assert COLLECTION_RESULT is not None

    collection_status = [
        {"nodeid": target.nodeid, "status": "collected"}
        for target in COLLECTION_RESULT.fuzz_targets
    ]
    for nodeid, item in COLLECTION_RESULT.not_collected.items():
        collection_status.append(
            {
                "nodeid": nodeid,
                "status": "not_collected",
                "status_reason": item["status_reason"],
            }
        )
    return collection_status


async def api_collected_tests(request: Request) -> Response:
    return HypofuzzJSONResponse({"collection_status": _collection_status()})


# get the backing state of the dashboard, suitable for use by dashboard_state/*.json.
async def api_backing_state_tests(request: Request) -> Response:
    from hypofuzz.dashboard.dashboard import TESTS

    tests = {
        nodeid: {
            "database_key": test.database_key,
            "nodeid": test.nodeid,
            "failure": test.failure,
            "reports_by_worker": {
                worker_uuid: [dashboard_report(report) for report in reports]
                for worker_uuid, reports in test.reports_by_worker.items()
            },
        }
        for nodeid, test in TESTS.items()
    }
    return HypofuzzJSONResponse(tests)


async def api_backing_state_observations(request: Request) -> Response:
    from hypofuzz.dashboard.dashboard import TESTS

    observations = {
        nodeid: {
            "rolling": [
                dashboard_observation(obs) for obs in test.rolling_observations
            ],
            "corpus": [dashboard_observation(obs) for obs in test.corpus_observations],
        }
        for nodeid, test in TESTS.items()
    }
    return HypofuzzJSONResponse(observations)


async def api_backing_state_api(request: Request) -> Response:
    return HypofuzzJSONResponse(
        {
            "collected_tests": {"collection_status": _collection_status()},
            "patches": _patches(),
        }
    )


api_routes = [
    Route("/api/tests/", api_tests),
    Route("/api/tests/{nodeid:path}", api_test),
    Route("/api/patches/{nodeid:path}", api_patch),
    Route("/api/available_patches/", api_available_patches),
    Route("/api/collected_tests/", api_collected_tests),
    Route("/api/backing_state/tests", api_backing_state_tests),
    Route("/api/backing_state/observations", api_backing_state_observations),
    Route("/api/backing_state/api", api_backing_state_api),
]
