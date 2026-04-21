import multiprocessing
from multiprocessing import Process

from common import setup_test_code, wait_for
from hypothesis.database import DirectoryBasedExampleDatabase

from hypofuzz.database import HypofuzzDatabase
from hypofuzz.hypofuzz import FuzzWorkerHub, _start_worker

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


def start_worker(manager, *, pytest_args, nodeids: list[str] = []) -> None:
    shared_state = manager.dict()
    shared_state["hub_state"] = manager.dict()
    shared_state["hub_state"]["nodeids"] = nodeids
    shared_state["worker_state"] = manager.dict()
    shared_state["worker_state"]["nodeids"] = manager.dict()
    shared_state["worker_state"]["valid_nodeids"] = manager.list()
    shared_state["worker_state"]["current_lifetime"] = 0.0
    shared_state["worker_state"]["expected_lifetime"] = 0.0
    process = Process(
        target=_start_worker,
        kwargs={"pytest_args": pytest_args, "shared_state": shared_state},
    )
    process.start()
    return (process, shared_state)


def test_workers(tmp_path):
    test_dir, _db_dir = setup_test_code(tmp_path, test_code)

    with multiprocessing.Manager() as manager:
        process, shared_state = start_worker(manager, pytest_args=[str(test_dir)])
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


def test_hub_shuts_down_workers_cleanly(tmp_path):
    # Regression test for #246: when the hub finishes a full exploration pass
    # (here, triggered by an always-failing test), it must signal workers to
    # exit before tearing down the Manager. Otherwise workers crash with
    # BrokenPipeError / FileNotFoundError on their next shared_state access.
    code = """
@given(st.integers())
def test_always_fails(n):
    assert False
"""
    test_dir, _db_dir = setup_test_code(tmp_path, code)

    hub = FuzzWorkerHub(
        nodeids=["test_a.py::test_always_fails"],
        pytest_args=[str(test_dir)],
        n_processes=1,
    )
    hub._rebalance_interval = 0.5
    hub.start()

    assert hub.processes
    for process in hub.processes:
        assert process.exitcode == 0, (
            f"worker exited with code {process.exitcode} (likely crashed on "
            f"shared_state access after Manager shutdown)"
        )


def test_worker_writes_worker_identity(tmp_path):
    test_dir, db_dir = setup_test_code(tmp_path, test_code)
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_dir))
    with multiprocessing.Manager() as manager:
        process, _shared_state = start_worker(manager, pytest_args=[str(test_dir)])

        wait_for(lambda: len(list(db.worker_uuids.fetch())) > 0, interval=0.01)
        uuid = list(db.worker_uuids.fetch())[0]
        wait_for(lambda: db.worker_identities.fetch(uuid) is not None, interval=0.01)

        process.kill()
        process.join()
