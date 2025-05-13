import subprocess
from pathlib import Path


def test_cli_output():
    expected = subprocess.check_output(
        ["hypothesis", "fuzz", "--help"], text=True
    ).strip()
    p = (
        Path(__file__).parent.parent
        / "src"
        / "hypofuzz"
        / "docs"
        / "cli_output_fuzz.txt"
    )
    header = "$ hypothesis fuzz --help\n"
    assert p.read_text().strip() == header + expected
