"""Live web dashboard for a fuzzing run."""
from typing import Tuple

import dash
import dash_core_components as dcc
import dash_html_components as html
import flask
import plotly.express as px
from dash.dependencies import Input, Output

DATA_TO_PLOT = [{"nodeid": "", "ninputs": 0, "arcs": 0}]
LAST_UPDATE = {}

headings = ["nodeid", "ninputs", "since new cov", "arcs", "estimated value", "note"]
app = flask.Flask(__name__)


@app.route("/", methods=["POST"])
def add_data() -> Tuple[str, int]:
    DATA_TO_PLOT.append(flask.request.json)
    LAST_UPDATE[flask.request.json["nodeid"]] = flask.request.json
    return "", 200


external_stylesheets = ["https://codepen.io/chriddyp/pen/bWLwgP.css"]
board = dash.Dash(__name__, server=app, external_stylesheets=external_stylesheets)
board.layout = html.Div(
    children=[
        html.H1(children="HypoFuzz Live Dashboard"),
        html.Div(
            "Covered arcs discovered for each target.  "
            "Data updates every 100th input, or immediately for new arcs."
        ),
        dcc.Graph(id="live-update-graph"),
        html.Div(html.Table(id="summary-table-rows")),
        dcc.Interval(id="interval-component", interval=5000),  # time in millis
    ]
)


@board.callback(  # type: ignore
    Output("live-update-graph", "figure"),
    [Input("interval-component", "n_intervals")],
)
def update_graph_live(n: int) -> object:
    fig = px.line(DATA_TO_PLOT, x="ninputs", y="arcs", color="nodeid", line_shape="hv")
    # Setting this to a constant prevents data updates clobbering zoom / selections
    fig.layout.uirevision = "this key never changes"
    return fig


@board.callback(  # type: ignore
    Output("summary-table-rows", "children"),
    [Input("interval-component", "n_intervals")],
)
def update_table_live(n: int) -> object:
    return [html.Tr([html.Th(h) for h in headings])] + [
        html.Tr([html.Td(data.get(k, "")) for k in headings])
        for name, data in sorted(LAST_UPDATE.items())
    ]


def start_dashboard_process(port: int, *, host: str = "localhost") -> None:
    print(f"\n\tNow serving dashboard at  http://{host}:{port}/\n")  # noqa
    app.run(host=host, port=port)


if __name__ == "__main__":
    # for debugging
    start_dashboard_process(port=9999)
