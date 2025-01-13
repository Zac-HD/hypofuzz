import requests
from common import dashboard, fuzz, wait_for, write_basic_test_code


def test_can_launch_dashboard():
    with dashboard() as dash:
        requests.get(f"http://localhost:{dash.port}", timeout=10).raise_for_status()
        dash.state()


def test_fuzzing_fills_dashboard():
    test_dir, _db_dir = write_basic_test_code()

    with dashboard(test_dir=test_dir) as dash:
        # we haven't started any fuzzers yet, so the dashboard is empty
        assert dash.state()["latest"] == {}

        # now launch a fuzzer, and check that it eventually updates the dashboard state
        with fuzz(n=1, dashboard=False, test_dir=test_dir):
            wait_for(lambda: len(dash.state()["latest"]) > 0, timeout=10, interval=0.25)
