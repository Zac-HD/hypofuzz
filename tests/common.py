import inspect
import os
import queue
import re
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from queue import Queue
from typing import Optional

import requests
from hypothesis.database import DirectoryBasedExampleDatabase
from hypothesis.internal.escalation import InterestingOrigin
from hypothesis.internal.reflection import get_pretty_function_description

from hypofuzz.collection import CollectionResult, collect_tests
from hypofuzz.database import FailureState, HypofuzzDatabase, test_keys_key


@dataclass(frozen=True)
class Dashboard:
    port: int
    process: subprocess.Popen

    def state(self, *, nodeid=None):
        r = requests.get(
            f"http://localhost:{self.port}/api/tests/{'' if nodeid is None else nodeid}",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()

    def patches(self, *, nodeid):
        r = requests.get(
            f"http://localhost:{self.port}/api/patches/{nodeid}",
            timeout=10,
        )
        r.raise_for_status()
        return r.json()


def wait_for(condition, *, timeout=10, interval):
    for _ in range(int(timeout // interval) + 1):
        if value := condition():
            return value
        time.sleep(interval)
    raise Exception(
        f"timing out after waiting {timeout}s for condition "
        f"{get_pretty_function_description(condition)}"
    )


def wait_for_test_key(db, *, timeout=10):
    keys = wait_for(
        lambda: list(db.fetch(test_keys_key)), interval=0.1, timeout=timeout
    )
    # assume we're only working with a single test
    assert len(keys) == 1
    return list(keys)[0]


def _enqueue_output(stream, queue):
    for line in iter(stream.readline, ""):
        queue.put((stream, line))
    stream.close()


@contextmanager
def dashboard(
    *, port: int = 0, test_path: Optional[Path] = None, numprocesses: int = 0
) -> Generator[Dashboard, None, None]:
    """
    Launches a dashboard process with --dashboard-only (unless numprocesses is
    passed). Defaults to a random open port.
    """

    args = [
        "hypothesis",
        "fuzz",
        "--port",
        str(port),
        *(
            ["--dashboard-only"]
            if numprocesses == 0
            else ["--numprocesses", str(numprocesses)]
        ),
    ]

    if test_path is not None:
        args += ["--", str(test_path)]

    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=True,
        # line buffered
        bufsize=1,
    )
    assert process.stdout is not None
    assert process.stderr is not None

    output_queue = Queue()
    output_thread = threading.Thread(
        target=_enqueue_output, args=(process.stdout, output_queue), daemon=True
    )
    stderr_thread = threading.Thread(
        target=_enqueue_output, args=(process.stderr, output_queue), daemon=True
    )
    output_thread.start()
    stderr_thread.start()
    stdout = []
    stderr = []

    def read_output():
        try:
            while True:
                stream, line = output_queue.get(block=True, timeout=0.1)
                if stream == process.stdout:
                    stdout.append(line)
                else:
                    stderr.append(line)
        except queue.Empty:
            pass

    port = None
    # wait for dashboard to start up
    for _ in range(25):
        time.sleep(0.05)
        if process.poll() is not None:
            read_output()
            stdout_text = "".join(stdout)
            stderr_text = "".join(stderr)
            raise Exception(
                f"dashboard exited with return code {process.returncode}. "
                f"args: {args}, cwd: {os.getcwd()}\n"
                f"stdout:\n{stdout_text!r}\nstderr:\n{stderr_text!r}"
            )

        read_output()
        stderr_text = "".join(stderr)
        if m := re.search(r"Running on http://127.0.0.1:(\d+)", stderr_text):
            port = int(m.group(1))
            break
    else:
        read_output()
        stdout_text = "".join(stdout)
        stderr_text = "".join(stderr)
        raise Exception(
            "dashboard took too long to start up. "
            f"stdout:\n{stdout_text!r}\nstderr:\n{stderr_text!r}"
        )

    wait_for(
        lambda: requests.get(f"http://localhost:{port}").status_code == 200,
        timeout=2,
        interval=0.01,
    )
    dashboard = Dashboard(port=port, process=process)

    try:
        yield dashboard
    finally:
        read_output()

        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait()

        if process.stdout:
            process.stdout.close()
        if process.stderr:
            process.stderr.close()

        stdout_text = "".join(stdout)
        stderr_text = "".join(stderr)
        debug_msg = ""
        debug_msg += f"[pid {process.pid}] dashboard stdout: "
        debug_msg += f"\n{stdout_text!r}" if stdout_text else "''"
        debug_msg += f"\n[pid {process.pid}] dashboard stderr: "
        debug_msg += f"\n{stderr_text!r}" if stderr_text else "''"
        print(debug_msg)


@contextmanager
def fuzz(test_path, *, n=1, dashboard=False, pytest_args=()):
    process = subprocess.Popen(
        [
            "hypothesis",
            "fuzz",
            "-n",
            str(n),
            "--dashboard" if dashboard else "--no-dashboard",
            "--",
            str(test_path),
            *pytest_args,
        ],
        start_new_session=True,
    )

    try:
        yield
    finally:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except ProcessLookupError:
            # the process might have exited already
            pass
        process.wait()


BASIC_TEST_CODE = """
import json
import time

# some non-trivial test that will exercise a bunch of lines
jsons = st.deferred(lambda: st.none() | st.integers() | st.floats() | st.text() | lists | objects)
lists = st.lists(jsons)
objects = st.dictionaries(st.text(), jsons)

def to_jsonable(obj):
    time.sleep(0.01)
    if isinstance(obj, int):
        # create a bunch of artificial branches
        if abs(obj) <= 100:
            pass
        elif abs(obj) <= 200:
            pass
        elif abs(obj) <= 300:
            pass
        elif abs(obj) <= 400:
            pass
        elif abs(obj) <= 500:
            pass
        elif abs(obj) <= 1000:
            pass
        elif abs(obj) <= 2000:
            pass
        elif abs(obj) <= 3000:
            pass
        elif abs(obj) <= 4000:
            pass
        elif abs(obj) <= 5000:
            pass
        elif abs(obj) <= 10_000:
            pass
        elif abs(obj) <= 20_000:
            pass
        elif abs(obj) <= 30_000:
            pass
        elif abs(obj) <= 40_000:
            pass
        elif abs(obj) <= 50_000:
            pass
        return obj
    if isinstance(obj, float):
        return obj
    if isinstance(obj, str):
        return obj
    if isinstance(obj, bool):
        return obj
    if obj is None:
        return obj
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [to_jsonable(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): to_jsonable(v) for k, v in obj.items()}

    return str(obj)

@given(jsons)
def test(x):
    to_jsonable(x)
"""


def write_test_code(path: Path, db_dir, code: str) -> None:
    code = (
        inspect.cleandoc(
            f"""
            from hypothesis import given, settings, strategies as st, HealthCheck, target
            from hypothesis.database import DirectoryBasedExampleDatabase
            import pytest
            from unittest import TestCase

            settings.register_profile("testing", settings(database=DirectoryBasedExampleDatabase("{db_dir}")))
            settings.load_profile("testing")
            """
        )
        + "\n\n"
        + inspect.cleandoc(code)
    )
    path.write_text(code)


def setup_test_code(tmp_path, code):
    tmp_path.mkdir(exist_ok=True)
    db_dir = tmp_path / "db"
    test_dir = tmp_path / "test"
    test_dir.mkdir()

    write_test_code(test_dir / "test_a.py", db_dir, code)
    return (test_dir, db_dir)


def interesting_origin(n: Optional[int] = None) -> InterestingOrigin:
    """
    Creates and returns an InterestingOrigin, parameterized by n, such that
    interesting_origin(n) == interesting_origin(m) iff n = m.

    Since n=None may by chance concide with an explicitly-passed value of n, I
    recommend not mixing interesting_origin() and interesting_origin(n) in the
    same test.
    """
    try:
        int("not an int")
    except Exception as e:
        origin = InterestingOrigin.from_exception(e)
        return origin._replace(lineno=n if n is not None else origin.lineno)


def collect(code: str) -> CollectionResult:
    code = (
        inspect.cleandoc(
            """
            import pytest
            from hypothesis import given, strategies as st, settings, HealthCheck, Phase
            from hypothesis.stateful import RuleBasedStateMachine, Bundle, initialize, rule
            from hypothesis.database import InMemoryExampleDatabase
            """
        )
        + "\n"
        + inspect.cleandoc(code)
    )
    p = Path(tempfile.mkstemp(prefix="test_", suffix=".py")[1])
    p.write_text(code)
    result = collect_tests([str(p)])
    p.unlink()
    return result


def collect_names(code: str) -> set[str]:
    return {fp.test_fn.__name__ for fp in collect(code).fuzz_targets}


def assert_no_failures(db, key):
    fatal_failure = db.fetch_fatal_failure(key)
    assert not fatal_failure, fatal_failure

    for state in [FailureState.SHRUNK, FailureState.UNSHRUNK, FailureState.FIXED]:
        failures = list(db.fetch_failures(key, state=state))
        assert not failures, [
            db.fetch_failure_observation(key, choices, state=state)
            for choices in failures
        ]


def fuzz_with_no_error(tmp_path, code):
    test_path, db_path = setup_test_code(tmp_path, code)
    db = HypofuzzDatabase(DirectoryBasedExampleDatabase(db_path))

    with fuzz(test_path):
        key = wait_for_test_key(db)
        start = time.time()
        wait_for(
            lambda: len(list(db.fetch_observations(key))) > 5
            or time.time() - start > 2,
            interval=0.1,
        )

    assert_no_failures(db, key)
