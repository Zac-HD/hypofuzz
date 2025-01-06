import tempfile
from pathlib import Path

import requests
from common import dashboard, fuzz, wait_for


def test_can_launch_dashboard():
    with dashboard() as dash:
        requests.get(f"http://localhost:{dash.port}", timeout=10).raise_for_status()
        dash.state()


TEST_CODE = """
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


def test_fuzzing_fills_dashboard():
    db_dir = Path(tempfile.mkdtemp())
    test_dir = Path(tempfile.mkdtemp())
    test_file = test_dir / "test_a.py"
    test_file.write_text(TEST_CODE.format(str(db_dir)))

    with dashboard(test_dir=test_dir) as dash:
        # we haven't started any fuzzers yet, so the dashboard is empty
        assert dash.state()["latest"] == {}

        # now launch a fuzzer, and check that it eventually updates the dashboard state
        with fuzz(n=1, dashboard=False, test_dir=test_dir):
            wait_for(lambda: len(dash.state()["latest"]) > 0, timeout=10, interval=0.25)
