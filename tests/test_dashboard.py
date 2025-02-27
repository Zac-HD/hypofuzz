import requests
from common import BASIC_TEST_CODE, dashboard, fuzz, wait_for, write_test_code


def test_can_launch_dashboard():
    test_dir, _db_dir = write_test_code(BASIC_TEST_CODE)

    with dashboard(test_path=test_dir) as dash:
        requests.get(f"http://localhost:{dash.port}", timeout=10).raise_for_status()
        dash.state()


def test_fuzzing_fills_dashboard():
    test_dir, _db_dir = write_test_code(BASIC_TEST_CODE)

    with dashboard(test_path=test_dir) as dash:
        # we haven't started any fuzzers yet, so the dashboard is empty
        assert dash.state() == {}

        # now launch a fuzzer, and check that it eventually updates the dashboard state
        with fuzz(n=1, dashboard=False, test_path=test_dir):
            wait_for(lambda: len(dash.state()) > 0, timeout=10, interval=0.25)
