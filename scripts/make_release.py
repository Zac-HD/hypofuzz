import os
import re
import sys
from pathlib import Path

import requests
from packaging import version
from packaging.version import Version

repo = os.environ["HYPOFUZZ_GITHUB_REPOSITORY"]
token = os.environ["HYPOFUZZ_GITHUB_TOKEN"]


def latest_changelog() -> str:
    pattern = re.compile(r"^## (\d\d\.\d\d\.\d+)$")
    with open(
        Path(__file__).parent.parent / "src" / "hypofuzz" / "docs" / "changelog.md"
    ) as f:
        lines = f.readlines()

    start_idx = None
    for i, line in enumerate(lines):
        if pattern.match(line.strip()):
            start_idx = i
            break

    end_idx = len(lines)
    for i in range(start_idx + 1, len(lines)):
        if pattern.match(lines[i].strip()):
            end_idx = i
            break

    # enough space for a changelog to actually be present
    assert end_idx - start_idx > 3

    lines = lines[start_idx + 1 : end_idx - 1]
    changelog = "".join(lines).strip()
    assert changelog != ""
    return changelog


def local_version() -> str:
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    import hypofuzz

    return hypofuzz.__version__


def latest_version() -> Version:
    r = requests.get(
        f"https://api.github.com/repos/{repo}/releases/latest",
        headers={
            "Accept": "application/vnd.github.v3+json",
        },
    )
    r.raise_for_status()
    data = r.json()
    return data["tag_name"].lstrip("v")


def do_release(version: str) -> None:
    changelog = latest_changelog()
    r = requests.post(
        f"https://api.github.com/repos/{repo}/releases",
        json={
            "tag_name": f"v{version}",
            "name": f"v{version}",
            "body": f"### https://hypofuzz.com/\n\n{changelog}",
        },
        headers={
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"token {token}",
            "Content-Type": "application/json",
        },
    )
    r.raise_for_status()


local_ver = local_version()
latest_ver = latest_version()


if version.parse(local_ver) > version.parse(latest_ver):
    do_release(local_ver)
