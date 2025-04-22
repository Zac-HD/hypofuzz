import argparse
import json
from pathlib import Path
from urllib.parse import urlparse

import requests

parser = argparse.ArgumentParser()
parser.add_argument("url")
args = parser.parse_args()

url = urlparse(args.url)
response = requests.get(f"http://{url.hostname}:{url.port}/api/backing_state/")
response.raise_for_status()

output_file = Path("dashboard_state.json")
with open(output_file, "w") as f:
    json.dump(response.json(), f, indent=2)

# use like:
# python scripts/dump_dashboard_state.py http://localhost:9999/
