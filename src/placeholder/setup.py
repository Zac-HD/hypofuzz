import os

import setuptools

LONG_DESCRIPTION = """
This is a placeholder package to direct people to https://hypofuzz.com
if they accidentally installed `hypofuzz` from PyPI, and to prevent
typosquatting-style attacks from such accidents.
"""

if "HYPOFUZZ_DISABLE_INSTALL_ERROR" not in os.environ:
    raise Exception(LONG_DESCRIPTION)

setuptools.setup(
    name="hypofuzz",
    version="0.0.0",
    author="Zac Hatfield-Dodds",
    author_email="hypofuzz@zhd.dev",
    py_modules=["hypofuzz"],
    url="https://hypofuzz.com",
    description="See hypofuzz.com",
    install_requires=[],
    python_requires=">=3.6",
    classifiers=["License :: Other/Proprietary License"],
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
)
