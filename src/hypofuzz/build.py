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


def build_docs() -> None:
    try:
        subprocess.check_call(["sphinx-build", "--version"])
    except Exception:
        raise Exception(
            "sphinx-build is required to build HypoFuzz docs, but was not found.\n"
            "Install sphinx-build and add it to your path."
        )

    source_p = Path(__file__).parent / "docs"
    out_p = Path(__file__).parent / "frontend" / "public" / "docs"
    out_p.mkdir(exist_ok=True, parents=True)
    subprocess.check_call(["sphinx-build", str(source_p), str(out_p)])


def build() -> None:
    build_docs()
    build_frontend()


# runs via pip install .
class HypofuzzBuildPy(build_py):
    def run(self) -> None:
        # super().run() copies files over to the final sdist/bdist, so building
        # the frontend html files has to come first.
        build()
        super().run()


# runs via pip install -e . (iff PEP 660 behavior is enabled?)
class HypofuzzEditableWheel(editable_wheel):
    def run(self) -> None:
        build()
        super().run()
