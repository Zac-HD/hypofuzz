import subprocess
import time
import re
import attr
from contextlib import contextmanager
import requests
from pathlib import Path
from typing import Optional
import shutil

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
