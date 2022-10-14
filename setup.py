import os

import setuptools


def local_file(name: str) -> str:
    """Interpret filename as relative to this file."""
    return os.path.relpath(os.path.join(os.path.dirname(__file__), name))


SOURCE = local_file("src")
README = local_file("README.md")

with open(local_file("src/hypofuzz/__init__.py")) as o:
    for line in o:
        if line.startswith("__version__"):
            _, __version__, _ = line.split('"')


setuptools.setup(
    name="hypofuzz",
    version=__version__,
    author="Zac Hatfield-Dodds",
    author_email="zac@hypofuzz.com",
    packages=setuptools.find_packages(SOURCE),
    package_dir={"": SOURCE},
    package_data={"": ["py.typed"]},
    url="https://hypofuzz.com/",
    project_urls={
        "Documentation": "https://hypofuzz.com/docs/",
        "Changelog": "https://hypofuzz.com/docs/changelog.html",
    },
    license="AGPL-3.0",
    description="Adaptive fuzzing for property-based tests",
    zip_safe=False,
    install_requires=[
        "coverage >= 5.2.1",
        "dash >= 2.0.0",
        "hypothesis[cli] >= 6.50.1",
        "pandas >= 1.0.0",
        "psutil >= 3.0.0",
        "pytest >= 6.0.1",
        "requests >= 2.24.0",
    ],
    extras_require={
        "pytrace": [
            "flask-cors >= 3.0.10",
            "pycrunch-trace >= 0.1.6",
        ],
    },
    python_requires=">=3.8",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Framework :: Hypothesis",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Topic :: Software Development :: Testing",
        "Typing :: Typed",
    ],
    entry_points={"hypothesis": ["_ = hypofuzz.entrypoint"]},
    long_description=open(README).read(),
    long_description_content_type="text/markdown",
    keywords="python testing fuzzing property-based-testing",
)
