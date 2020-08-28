from pathlib import Path

import sphinx_rtd_theme

# See https://www.sphinx-doc.org/en/master/usage/configuration.html
# -- Project information -----------------------------------------------------
project = "HypoFuzz"
copyright = "2020, Zac Hatfield-Dodds"  # noqa: A001  # shadows a builtin
author = "Zac Hatfield-Dodds"
init_file = Path(__file__).parent.parent / "src/hypofuzz/__init__.py"
for line in init_file.read_text().splitlines():
    if line.startswith("__version__ = "):
        _, version, _ = line.split('"')


# -- General configuration ---------------------------------------------------
needs_sphinx = "3.2"
nitpicky = True

extensions = [
    "sphinx.ext.autodoc",
    "sphinx.ext.extlinks",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.programoutput",
]
intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "pytest": ("https://docs.pytest.org/en/stable/", None),
    "hypothesis": ("https://hypothesis.readthedocs.io/en/latest/", None),
}
# See http://sphinx-doc.org/ext/extlinks.html
_repo = "https://github.com/Zac-HD/hypofuzz"
extlinks = {
    "commit": (f"{_repo}/commit/%s", "commit "),
    "gh-file": (f"{_repo}/blob/master/%s", ""),
    "gh-link": (f"{_repo}/%s", ""),
    "issue": (f"{_repo}/issues/%s", "issue #"),
    "pull": (f"{_repo}/pull/%s", "pull request #"),
    "pypi": ("https://pypi.org/project/%s", ""),
    "bpo": ("https://bugs.python.org/issue%s", "bpo-"),
}


# -- Options for HTML output -------------------------------------------------
html_title = "HypoFuzz docs"
html_theme = "sphinx_rtd_theme"
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
# html_favicon = "favicon.ico"
# html_logo = ""  # path to the project logo, for the top of the sidebar, ~200px
# html_baseurl = ""
html_show_sphinx = False
