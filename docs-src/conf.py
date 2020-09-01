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
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.extlinks",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
    "sphinxcontrib.bibtex",
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
    "hydocs": ("https://hypothesis.readthedocs.io/en/latest/%s", ""),
}


# -- Options for HTML output -------------------------------------------------
html_title = "HypoFuzz docs"
html_theme = "sphinx_rtd_theme"
html_theme_path = [sphinx_rtd_theme.get_html_theme_path()]
# html_favicon = "favicon.ico"
# html_logo = ""  # path to the project logo, for the top of the sidebar, ~200px
html_baseurl = "https://hypofuzz.com/docs/"
html_show_sphinx = False


# -- Inline plugin to add Google Analytics js, modelled on sphinxcontrib-googleanalytics

ANALYTICS_JS = """
  <!-- Global site tag (gtag.js) - Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=UA-176879127-1"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag() { dataLayer.push(arguments); }
    gtag('js', new Date());
    gtag('config', 'UA-176879127-1');
  </script>
"""


def add_ga_javascript(app, pagename, templatename, context, doctree):
    context["metatags"] = context.get("metatags", "") + ANALYTICS_JS


def setup(app):
    app.connect("html-page-context", add_ga_javascript)
    return {"version": "1.0.0", "parallel_read_safe": True}
