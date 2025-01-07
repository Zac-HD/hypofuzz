import re
import shutil
import subprocess
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Optional
import tempfile

import attr
import requests
from hypothesis.internal.reflection import get_pretty_function_description


@attr.s(frozen=True, slots=True)
class Dashboard:
    port: int = attr.ib()
    process: subprocess.Popen = attr.ib()

    def state(self):
        r = requests.get(f"http://localhost:{self.port}/api/state", timeout=10)
        r.raise_for_status()
        return r.json()


def wait_for(condition, *, timeout, interval):
    for _ in range(int(timeout // interval) + 1):
        if condition():
            return
        time.sleep(interval)
    raise Exception(
        f"timing out after waiting {timeout}s for condition"
        f"{get_pretty_function_description(condition)}"
    )


@contextmanager
def dashboard(*, port: int = 0, test_dir: Optional[Path] = None) -> Dashboard:
    """
    Launches a dashboard process with --dashboard-only. Defaults to a random open
    port.
    """
    args = ["hypothesis", "fuzz", "--dashboard-only", "--port", str(port)]
    if test_dir is not None:
        args += ["--", str(test_dir)]
    process = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    port = None
    # wait for dashboard to start up
    for _ in range(100):
        time.sleep(0.05)
        if process.poll() is not None:
            raise Exception(
                f"dashboard invocation exited with return code {process.returncode}"
            )

        # flask prints the port on stderr :(
        output = process.stderr.readline()
        if m := re.search(rb"\* Running on http://localhost:(\d+)", output):
            port = int(m.group(1))
            break
    else:
        raise Exception(
            "dashboard took too long to start up. "
            f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
        )

    # ...plus a little more, for slow CI?
    time.sleep(0.1)
    dashboard = Dashboard(port=port, process=process)

    try:
        yield dashboard
    finally:
        dashboard.process.stdout.close()
        dashboard.process.stderr.close()
        dashboard.process.kill()
        dashboard.process.wait()
        if test_dir is not None:
            shutil.rmtree(test_dir)


@contextmanager
def fuzz(*, n=1, dashboard=False, test_dir=None):
    args = [
        "hypothesis",
        "fuzz",
        "-n",
        str(n),
        "--dashboard" if dashboard else "--no-dashboard",
    ]
    if test_dir is not None:
        args += ["--", str(test_dir)]
    process = subprocess.Popen(args)

    try:
        yield
    finally:
        process.terminate()
        process.wait()


BASIC_TEST_CODE = """
import json

from hypothesis import given, settings, strategies as st
from hypothesis.database import DirectoryBasedExampleDatabase

settings.register_profile("testing", settings(database=DirectoryBasedExampleDatabase("{}")))
settings.load_profile("testing")
n = st.integers(0, 127)

# some non-trivial test that will exercise a bunch of lines (albeit in the stdlib).
jsons = st.deferred(lambda: st.none() | st.floats() | st.text() | lists | objects)
lists = st.lists(jsons)
objects = st.dictionaries(st.text(), jsons)

@given(jsons)
def test(x):
    json.loads(json.dumps(x))
"""


def write_basic_test_code():
    db_dir = Path(tempfile.mkdtemp())
    test_dir = Path(tempfile.mkdtemp())
    test_file = test_dir / "test_a.py"
    test_file.write_text(BASIC_TEST_CODE.format(str(db_dir)))
    return (test_dir, db_dir)
