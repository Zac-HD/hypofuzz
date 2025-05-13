import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import requests

# usage:
# python scripts/update_dashboard_state.py <url>

parser = argparse.ArgumentParser()
parser.add_argument("url", nargs="?", default="http://localhost:9999/")
args = parser.parse_args()
url = urlparse(args.url)

dashboard_state = (
    Path(__file__).parent.parent / "src" / "hypofuzz" / "docs" / "dashboard_state"
)
dashboard_state.mkdir(exist_ok=True)

for page in ["tests", "observations", "api"]:
    response = requests.get(
        f"http://{url.hostname}:{url.port}/api/backing_state/{page}"
    )
    response.raise_for_status()

    output_file = dashboard_state / f"{page}.json"
    with open(output_file, "w") as f:
        json.dump(response.json(), f, indent=2)
