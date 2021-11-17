"""Live web dashboard for a fuzzing run."""
import datetime
import json
import os
from typing import List, Tuple

import black
import dash
import dash_core_components as dcc
import dash_html_components as html
import flask
import flask_cors
import plotly.graph_objects as go
import plotly.express as px
from dash.dependencies import Input, Output

try:
    from pycrunch_trace.oop.safe_filename import SafeFilename
except ImportError:
    SafeFilename = None

DATA_TO_PLOT = [{"nodeid": "", "elapsed_time": 0, "ninputs": 0, "branches": 0}]
LAST_UPDATE = {}

DEMO_JSON_FILE = ".hypothesis/dashboard-demo-data.json"
DEMO_SAVED_DATA: List[dict] = []
DEMO_MODE = os.environ.get("_HYPOFUZZ_DEMO_MODE") == "true"
RECORD_MODE = os.environ.get("_HYPOFUZZ_RECORD_MODE") == "true"
assert not (DEMO_MODE and RECORD_MODE)

headings = ["nodeid", "elapsed time", "ninputs", "since new cov", "branches", "note"]
app = flask.Flask(__name__, static_folder=os.path.abspath("pycrunch-recordings"))
flask_cors.CORS(app)


@app.route("/", methods=["POST"])
def recv_data() -> Tuple[str, int]:
    assert not DEMO_MODE
    data = flask.request.json
    if not isinstance(data, list):
        data = [data]
    for d in data:
        add_data(d)
    return "", 200


def add_data(d: dict) -> None:
    if RECORD_MODE:
        DEMO_SAVED_DATA.append(d)
    if not LAST_UPDATE:
        del DATA_TO_PLOT[0]
    DATA_TO_PLOT.append(
        {k: d[k] for k in ["nodeid", "elapsed_time", "ninputs", "branches"] if k in d}
    )
    LAST_UPDATE[d["nodeid"]] = d


external_stylesheets = ["https://codepen.io/chriddyp/pen/bWLwgP.css"]
board = dash.Dash(__name__, server=app, external_stylesheets=external_stylesheets)
board.layout = html.Div(
    children=[
        # represents the URL bar, doesn't render anything
        dcc.Location(id="url", refresh=False),
        html.H1(
            children=[
                html.A("HypoFuzz", href="https://hypofuzz.com"),
                " Live Dashboard",
            ]
        ),
        html.Div(id="page-content"),
        dcc.Interval(id="interval-component", interval=5000),  # time in millis
    ]
)


def row_for(data: dict, include_link: bool = True, *extra: object) -> html.Tr:
    parts = []
    if include_link:
        parts.append(
            dcc.Link(data["nodeid"], href="/" + data["nodeid"].replace("/", "_"))
        )
    if "elapsed_time" in data:
        parts.append(str(datetime.timedelta(seconds=int(data["elapsed_time"]))))
    else:
        parts.append("")
    for key in headings[2:]:
        parts.append(data.get(key, ""))
    return html.Tr([html.Td(p) for p in parts + [str(e) for e in extra]])


def try_format(code: str) -> str:
    try:
        return black.format_str(code, mode=black.FileMode())
    except black.InvalidInput:
        return code


def update_data_for_demo_mode() -> None:
    if RECORD_MODE:
        with open(DEMO_JSON_FILE, mode="w") as f:
            json.dump(DEMO_SAVED_DATA, indent=4, fp=f)

    if not DEMO_MODE:
        return
    global DEMO_START_TIME
    if len(DATA_TO_PLOT) <= 1:
        with open(DEMO_JSON_FILE) as f:
            DEMO_SAVED_DATA.extend(json.load(f))
        DEMO_SAVED_DATA.sort(key=lambda d: -d.get("timestamp", 0))

    if DEMO_SAVED_DATA:
        stop_at_timestamp = DEMO_SAVED_DATA[-1].get("timestamp", 0) + 10
        while (
            DEMO_SAVED_DATA
            and DEMO_SAVED_DATA[-1].get("timestamp", 0) <= stop_at_timestamp
        ):
            add_data(DEMO_SAVED_DATA.pop())


@board.callback(  # type: ignore
    Output("page-content", "children"),
    [Input("url", "pathname")],
)
def display_page(pathname: str) -> html.Div:
    # Main page
    if pathname == "/" or pathname is None:
        return html.Div(
            children=[
                html.Div("Total branch coverage for each test."),
                dcc.Graph(id="live-update-graph"),
                html.Button("Toggle log-xaxis", id="xaxis-state", n_clicks=0),
                html.Div(html.Table(id="summary-table-rows")),
            ]
        )

    # Target-specific subpages
    nodeid = pathname[1:]
    trace = [
        d
        for d in DATA_TO_PLOT
        if d["nodeid"].replace("/", "_") == nodeid  # type: ignore
    ]
    fig1 = px.line(
        trace, x="ninputs", y="branches", line_shape="hv", hover_data=["elapsed_time"]
    )
    fig2 = px.line(
        trace, x="elapsed_time", y="branches", line_shape="hv", hover_data=["ninputs"]
    )
    if RECORD_MODE:
        slug = pathname.split("::")[-1]
        fig1.write_html(f".hypothesis/{slug}-fig1.html", include_plotlyjs="cdn")
        fig2.write_html(f".hypothesis/{slug}-fig2.html", include_plotlyjs="cdn")
    last_update = LAST_UPDATE[trace[-1]["nodeid"]]
    add: List[str] = []
    if "failures" in last_update:
        for failures in last_update["failures"]:
            failures[0] = try_format(failures[0])
            add.extend(html.Pre(children=[html.Code(children=[x])]) for x in failures)
        if SafeFilename:
            url = f"http://{flask.request.host}/pycrunch-recordings/{SafeFilename(nodeid)}/session.chunked"
            link = dcc.Link(
                "Debug failing example online with pytrace",
                href=f"https://app.pytrace.com/?open={url}",
            )
            add.append(html.Pre(children=[link]))
    return html.Div(
        children=[
            dcc.Link("Back to main dashboard", href="/"),
            html.P(
                children=[
                    "Example count by status: ",
                    str(last_update.get("status_counts", "???")),
                ]
            ),
            html.Table(
                children=[
                    html.Tr(
                        [html.Th(h) for h in headings[1:]] + [html.Th(["seed count"])]
                    ),
                    row_for(last_update, False, len(last_update.get("seed_pool", []))),
                ]
            ),
            *add,
            dcc.Graph(id=f"graph-of-{pathname}-1", figure=fig1),
            dcc.Graph(id=f"graph-of-{pathname}-2", figure=fig2),
            html.H3(["Minimal covering examples"]),
            html.P(
                [
                    "Each additional example shown below covers at least one branch "
                    "not covered by any previous, more-minimal, example."
                ]
            ),
        ]
        + [
            html.Pre([html.Code([try_format(row[1]), row[2], "\n"])])
            for row in last_update.get("seed_pool", [])
        ]
    )


@board.callback(  # type: ignore
    Output("live-update-graph", "figure"),
    [Input("interval-component", "n_intervals"), Input("xaxis-state", "n_clicks")],
)
def update_graph_live(n: int, clicks: int) -> object:
    update_data_for_demo_mode()
    fig = px.line(
        DATA_TO_PLOT,
        x="ninputs",
        y="branches",
        color="nodeid",
        line_shape="hv",
        hover_data=["elapsed_time"],
        log_x=bool(clicks % 2),
    )
    failing = [
        (d["ninputs"], d["branches"])
        for d in LAST_UPDATE.values()
        if d.get("note", "").startswith("raised ")
    ]
    if failing:
        xs, ys = zip(*failing)
        fig.add_trace(go.Scatter(x=xs, y=ys, mode="text", text="💥", showlegend=False))
    fig.update_layout(
        height=800,
        legend_yanchor="top",
        legend_xanchor="left",
        legend_y=-0.08,
        legend_x=0,
    )
    if RECORD_MODE:
        fig.write_html(".hypothesis/figure.html", include_plotlyjs="cdn")
    # Setting this to a constant prevents data updates clobbering zoom / selections
    fig.layout.uirevision = "this key never changes"
    return fig


@board.callback(  # type: ignore
    Output("summary-table-rows", "children"),
    [Input("interval-component", "n_intervals")],
)
def update_table_live(n: int) -> object:
    return [html.Tr([html.Th(h) for h in headings])] + [
        row_for(data) for name, data in sorted(LAST_UPDATE.items()) if name
    ]


@app.route("/pycrunch-recordings/<path:name>")
def download_file(name):
    return flask.send_from_directory(
        directory="pycrunch-recordings",
        filename=name,
        mimetype="application/octet-stream",
    )


def start_dashboard_process(
    port: int, *, host: str = "localhost", debug: bool = False
) -> None:
    print(f"\n\tNow serving dashboard at  http://{host}:{port}/\n")  # noqa
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    assert DEMO_MODE
    start_dashboard_process(port=9999, debug=True)
