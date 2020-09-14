"""Live web dashboard for a fuzzing run."""
import datetime
import json
from typing import Tuple

import dash
import dash_core_components as dcc
import dash_html_components as html
import flask
import plotly.express as px
from dash.dependencies import Input, Output

DATA_TO_PLOT = [{"nodeid": "", "ninputs": 0, "arcs": 0}]
LAST_UPDATE = {}

headings = ["nodeid", "elapsed time", "ninputs", "since new cov", "arcs", "note"]
app = flask.Flask(__name__)


@app.route("/", methods=["POST"])
def add_data() -> Tuple[str, int]:
    data = flask.request.json
    if not isinstance(data, list):
        data = [data]
    DATA_TO_PLOT.extend(data)
    LAST_UPDATE[data[-1]["nodeid"]] = data[-1]
    return "", 200


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

UPDATEMENUS = [
    {
        "type": "buttons",
        "buttons": [
            {
                "label": "Linear xaxis",
                "method": "update",
                "args": [{"visible": True}, {"xaxis": {"type": "linear"}}],
            },
            {
                "label": "Log xaxis",
                "method": "update",
                "args": [{"visible": True}, {"xaxis": {"type": "log"}}],
            },
        ],
    },
]


def row_for(data: dict, include_link: bool = True) -> html.Tr:
    parts = []
    if include_link:
        parts.append(dcc.Link(data["nodeid"], href=data["nodeid"].replace("/", "_")))
    if "elapsed_time" in data:
        parts.append(str(datetime.timedelta(seconds=int(data["elapsed_time"]))))
    else:
        parts.append("")
    for key in headings[2:]:
        parts.append(data.get(key, ""))
    return html.Tr([html.Td(p) for p in parts])


@board.callback(  # type: ignore
    Output("page-content", "children"),
    [Input("url", "pathname")],
)
def display_page(pathname: str) -> html.Div:
    # Main page
    if pathname == "/" or pathname is None:
        return html.Div(
            children=[
                html.Div(
                    "Covered arcs discovered for each target.  "
                    "Data updates every 100th input, or immediately for new arcs."
                ),
                dcc.Graph(id="live-update-graph"),
                html.Div(html.Table(id="summary-table-rows")),
            ]
        )

    # Target-specific subpages
    trace = [
        d
        for d in DATA_TO_PLOT
        if d["nodeid"].replace("/", "_") == pathname[1:]  # type: ignore
    ]
    fig1 = px.line(
        trace, x="ninputs", y="arcs", line_shape="hv", hover_data=["elapsed_time"]
    )
    fig2 = px.line(
        trace, x="elapsed_time", y="arcs", line_shape="hv", hover_data=["ninputs"]
    )
    fig1.update_layout(updatemenus=UPDATEMENUS)
    fig2.update_layout(updatemenus=UPDATEMENUS)
    return html.Div(
        children=[
            dcc.Link("Back to home", href="/"),
            html.Table(
                children=[
                    html.Tr([html.Th(h) for h in headings[1:]]),
                    row_for(trace[-1], include_link=False),
                ]
            ),
            dcc.Graph(id=f"graph-of-{pathname}-1", figure=fig1),
            dcc.Graph(id=f"graph-of-{pathname}-2", figure=fig2),
        ]
    )


@board.callback(  # type: ignore
    Output("live-update-graph", "figure"),
    [Input("interval-component", "n_intervals")],
)
def update_graph_live(n: int) -> object:
    fig = px.line(
        DATA_TO_PLOT,
        x="ninputs",
        y="arcs",
        color="nodeid",
        line_shape="hv",
        hover_data=["elapsed_time"],
    )
    # Define some controls for log-x-axis plotting, which values to plot, etc.
    # TODO: work out why axis UI state resets on every interval despite uirevision
    fig.update_layout(
        height=800,
        updatemenus=UPDATEMENUS,
        legend_yanchor="top",
        legend_xanchor="left",
        legend_y=-0.08,
        legend_x=0,
    )
    # Setting this to a constant prevents data updates clobbering zoom / selections
    fig.layout.uirevision = "this key never changes"
    return fig


@board.callback(  # type: ignore
    Output("summary-table-rows", "children"),
    [Input("interval-component", "n_intervals")],
)
def update_table_live(n: int) -> object:
    # with open(".hypothesis/dump.json", mode="w") as f:
    #     json.dump([LAST_UPDATE, DATA_TO_PLOT], indent=4, fp=f)
    return [html.Tr([html.Th(h) for h in headings])] + [
        row_for(data) for name, data in sorted(LAST_UPDATE.items()) if name
    ]


def start_dashboard_process(
    port: int, *, host: str = "localhost", debug: bool = False
) -> None:
    print(f"\n\tNow serving dashboard at  http://{host}:{port}/\n")  # noqa
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    # for debugging
    with open(".hypothesis/dump.json") as f:
        LAST_UPDATE, DATA_TO_PLOT = json.load(f)
    start_dashboard_process(port=9999, debug=True)
