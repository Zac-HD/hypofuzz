import multiprocessing
from multiprocessing import Process

from common import setup_test_code, wait_for

from hypofuzz.hypofuzz import _start_worker

test_code = """
@given(st.integers())
def test_a(n):
    pass

@given(st.integers())
def test_b():
    pass

@given(st.integers())
def test_c():
    pass
"""


def test_workers(tmp_path):
    test_dir, _db_dir = setup_test_code(tmp_path, test_code)

    with multiprocessing.Manager() as manager:
        shared_state = manager.dict()
        shared_state["hub_state"] = manager.dict()
        shared_state["hub_state"]["nodeids"] = []
        shared_state["worker_state"] = manager.dict()
        shared_state["worker_state"]["nodeids"] = manager.dict()
        shared_state["worker_state"]["valid_nodeids"] = manager.list()
        shared_state["worker_state"]["current_lifetime"] = 0.0
        shared_state["worker_state"]["expected_lifetime"] = 0.0
        process = Process(
            target=_start_worker,
            kwargs={"pytest_args": [str(test_dir)], "shared_state": shared_state},
        )
        process.start()

        assert shared_state["hub_state"]["nodeids"] == []

        shared_state["hub_state"]["nodeids"] = ["test_a.py::test_a"]
        wait_for(
            lambda: shared_state["worker_state"]["valid_nodeids"]
            == ["test_a.py::test_a"],
            interval=0.01,
        )
        assert shared_state["worker_state"]["current_lifetime"] > 0.0

        process.kill()
        process.join()
