import inspect
import os
import re
import select
import signal
import subprocess
import time
from collections.abc import Generator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import requests
from hypothesis.internal.escalation import InterestingOrigin
from hypothesis.internal.reflection import get_pretty_function_description


@dataclass(frozen=True)
class Dashboard:
    port: int
    process: subprocess.Popen

    def state(self, *, id=None):
        r = requests.get(
            f"http://localhost:{self.port}/api/tests/{'' if id is None else id}",
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


@contextmanager
def dashboard(
    *, port: int = 0, test_path: Optional[Path] = None
) -> Generator[Dashboard, None, None]:
    """
    Launches a dashboard process with --dashboard-only. Defaults to a random open
    port.
    """
    args = ["hypothesis", "fuzz", "--dashboard-only", "--port", str(port)]
    if test_path is not None:
        args += ["--", str(test_path)]
    process = subprocess.Popen(
        args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        text=True,
    )
    assert process.stdout is not None
    assert process.stderr is not None
    port = None
    # wait for dashboard to start up
    for _ in range(25):
        time.sleep(0.05)
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            raise Exception(
                f"dashboard exited with return code {process.returncode}. "
                f"args: {args}, cwd: {os.getcwd()}\n"
                f"stdout:\n{stdout!r}\nstderr:\n{stderr!r}"
            )

        # wait to call the blocking .readline call until the stderr is readable
        readable, _writable, _exceptional = select.select([process.stderr], [], [], 0.5)
        if process.stderr in readable:
            output = process.stderr.readline()
            if m := re.search(r"Running on http://127.0.0.1:(\d+)", output):
                port = int(m.group(1))
                break
    else:
        raise Exception(
            "dashboard took too long to start up. "
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
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
        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        process.wait()
        stdout, stderr = process.communicate()
        process.stdout.close()
        process.stderr.close()
        debug_msg = ""
        debug_msg += f"[pid {process.pid}] dashboard stdout: "
        debug_msg += f"\n{stdout!r}" if stdout != "" else "''"
        debug_msg += f"\n[pid {process.pid}] dashboard stderr: "
        debug_msg += f"\n{stderr!r}" if stderr != "" else "''"
        print(debug_msg)


@contextmanager
def fuzz(*, n=1, dashboard=False, test_path=None, pytest_args=()):
    args = [
        "hypothesis",
        "fuzz",
        "-n",
        str(n),
        "--dashboard" if dashboard else "--no-dashboard",
    ]
    if test_path is not None:
        args += ["--", str(test_path), *pytest_args]
    process = subprocess.Popen(args, start_new_session=True)

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
    time.sleep(0.05)
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
            from hypothesis import given, settings, strategies as st
            from hypothesis.database import DirectoryBasedExampleDatabase
            import pytest

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
