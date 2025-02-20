import subprocess
from pathlib import Path

from setuptools.command.build_py import build_py
from setuptools.command.editable_wheel import editable_wheel


def build_frontend() -> None:
    try:
        subprocess.check_call(["npm", "--version"])
    except Exception:
        raise Exception(
            "npm is required to build HypoFuzz, but was not found.\n"
            "Install npm and add it to your path."
        )

    frontend_dir = Path(__file__).parent / "frontend"
    subprocess.check_call(["npm", "install"], cwd=frontend_dir)
    subprocess.check_call(["npm", "run", "build"], cwd=frontend_dir)


# runs via pip install .
class HypofuzzBuildPy(build_py):
    def run(self) -> None:
        # super().run() copies files over to the final sdist/bdist, so building
        # the frontend html files has to come first.
        build_frontend()
        super().run()


# runs via pip install -e . (iff PEP 660 behavior is enabled?)
class HypofuzzEditableWheel(editable_wheel):
    def run(self) -> None:
        build_frontend()
        super().run()
