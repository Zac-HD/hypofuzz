from datetime import date
from pathlib import Path

# See https://www.sphinx-doc.org/en/master/usage/configuration.html
# -- Project information -----------------------------------------------------
project = "HypoFuzz"
copyright = f"{date.today().year}, Zac Hatfield-Dodds"
author = "Zac Hatfield-Dodds"
init_file = Path(__file__).parent.parent / "__init__.py"
for line in init_file.read_text().splitlines():
    if line.startswith("__version__ = "):
        _, version, _ = line.split('"')


# -- General configuration ---------------------------------------------------
needs_sphinx = "3.2"
nitpicky = True

extensions = [
    # for reading changelog.md
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.extlinks",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.bibtex",
]
intersphinx_mapping = {
    "python": ("https://docs.python.org/3/", None),
    "pytest": ("https://docs.pytest.org/en/stable/", None),
    "hypothesis": ("https://hypothesis.readthedocs.io/en/latest/", None),
}
# See http://sphinx-doc.org/ext/extlinks.html
_repo = "https://github.com/Zac-HD/hypofuzz"
extlinks = {
    "commit": (f"{_repo}/commit/%s", "commit %s"),
    "gh-file": (f"{_repo}/blob/master/%s", "%s"),
    "gh-link": (f"{_repo}/%s", "%s"),
    "issue": (f"{_repo}/issues/%s", "issue #%s"),
    "pull": (f"{_repo}/pull/%s", "pull request #%s"),
    "pypi": ("https://pypi.org/project/%s", "%s"),
    "bpo": ("https://bugs.python.org/issue%s", "bpo-%s"),
    "hydocs": ("https://hypothesis.readthedocs.io/en/latest/%s", "%s"),
    "wikipedia": ("https://en.wikipedia.org/wiki/%s", "%s"),
}

bibtex_bibfiles = ["literature.bib"]


# -- Options for HTML output -------------------------------------------------
html_title = "HypoFuzz docs"
html_theme = "furo"
# https://sphinx-rtd-theme.readthedocs.io/en/stable/configuring.html#confval-analytics_id
# > Deprecated since version 3.0.0: The analytics_id option is deprecated, use
# > the sphinxcontrib-googleanalytics extension instead.
# html_theme_options = {"analytics_id": "UA-176879127-1"}
# html_favicon = "favicon.ico"
# html_logo = ""  # path to the project logo, for the top of the sidebar, ~200px
html_baseurl = "https://hypofuzz.com/docs/"
html_show_sphinx = False
