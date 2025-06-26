import requests
from common import (
    BASIC_TEST_CODE,
    dashboard,
    fuzz,
    setup_test_code,
    wait_for,
    write_test_code,
)


def test_can_launch_dashboard(tmp_path):
    test_dir, _db_dir = setup_test_code(tmp_path, BASIC_TEST_CODE)

    with dashboard(test_path=test_dir) as dash:
        requests.get(f"http://localhost:{dash.port}", timeout=10).raise_for_status()
        dash.state()


def test_fuzzing_fills_dashboard(tmp_path):
    test_dir, _db_dir = setup_test_code(tmp_path, BASIC_TEST_CODE)

    with dashboard(test_path=test_dir) as dash:
        state = dash.state()
        assert state.keys() == {"test_a.py::test"}
        # dashboard runs a collection step, so it knows about the test, but doesn't
        # have any reports for it
        assert not state["test_a.py::test"]["reports_by_worker"]

        # now launch a fuzzer, and check that it eventually updates the dashboard state
        with fuzz(test_dir):
            wait_for(
                lambda: len(dash.state()["test_a.py::test"]["reports_by_worker"]) > 0,
                interval=0.25,
            )


def test_dashboard_failure(tmp_path):
    test_dir, db_dir = setup_test_code(
        tmp_path,
        """
        def maybe_fail():
            assert False

        @given(st.integers())
        def test_maybe_fail(n):
            maybe_fail()
        """,
    )

    with dashboard(test_path=test_dir) as dash:
        assert dash.state()["test_a.py::test_maybe_fail"]["failures"] == {}
        with fuzz(test_dir):
            wait_for(
                lambda: dash.state()["test_a.py::test_maybe_fail"]["failures"],
                interval=0.25,
            )

    # if we restart the dasbhoard, the failure is still shown
    with dashboard(test_path=test_dir) as dash:
        failures = dash.state()["test_a.py::test_maybe_fail"]["failures"]
        assert len(failures) == 1
        failure = list(failures.values())[0]
        assert failure["observation"]["property"] == "test_a.py::test_maybe_fail"
        # TODO wait for shrinking to finish? or put that into a separate test?
        assert failure["state"] in ["unshrunk", "shrunk"]

    # and also if we change the code to pass, but don't run the worker again, the
    # failure is still shown
    write_test_code(
        test_dir / "test_a.py",
        db_dir,
        """
        def maybe_fail():
            assert True

        @given(st.integers())
        def test_maybe_fail(n):
            maybe_fail()
        """,
    )
    with dashboard(test_path=test_dir) as dash:
        failures = dash.state()["test_a.py::test_maybe_fail"]["failures"]
        assert len(failures) == 1
        failure = list(failures.values())[0]
        assert failure["observation"]["property"] == "test_a.py::test_maybe_fail"
        assert failure["state"] in ["unshrunk", "shrunk"]

        # but if we run the worker again, the failure disappears
        with fuzz(test_dir):
            wait_for(
                lambda: dash.state()["test_a.py::test_maybe_fail"]["failures"] == {},
                interval=0.25,
            )
