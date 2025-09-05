#!/usr/bin/env bash

# poor man's makefile. We could just use make here,
# but ./build.sh <args> matches hypothesis.

set -o xtrace
set -o errexit
set -o nounset

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

if [ "$1" = "docs" ]; then
    sphinx-build "$ROOT/src/hypofuzz/docs" "$ROOT/src/hypofuzz/frontend/public/docs"
elif [ "$1" = "docs-clean" ]; then
    rm -rf "$ROOT/src/hypofuzz/frontend/public/docs"
elif [ "$1" = "dashboard" ]; then
    VITE_USE_DASHBOARD_STATE=0 npm --prefix "$ROOT/src/hypofuzz/frontend" run build
elif [ "$1" = "dashboard-profiling" ]; then
    VITE_USE_DASHBOARD_STATE=0 npm --prefix "$ROOT/src/hypofuzz/frontend" run build:profiling
# builds the dashboard with USE_DASHBOARD_STATE=1
elif [ "$1" = "dashboard-json" ]; then
    VITE_USE_DASHBOARD_STATE=1 npm --prefix "$ROOT/src/hypofuzz/frontend" run build
    cp -r "$ROOT/src/hypofuzz/docs/dashboard_state" "$ROOT/src/hypofuzz/frontend/dist/assets/dashboard_state"
# dashboard-demo tries to mimic the /demo page on the website as much as possible
# Right now, that means using both USE_DASHBOARD_STATE=1 and ROUTER_TYPE=hash.
elif [ "$1" = "dashboard-demo" ]; then
    VITE_ROUTER_TYPE=hash VITE_USE_DASHBOARD_STATE=1 npm --prefix "$ROOT/src/hypofuzz/frontend" run build
    cp -r "$ROOT/src/hypofuzz/docs/dashboard_state" "$ROOT/src/hypofuzz/frontend/dist/assets/dashboard_state"
elif [ "$1" = "test" ]; then
    npm --prefix "$ROOT/src/hypofuzz/frontend" run test
elif [ "$1" = "format" ]; then
    npm --prefix "$ROOT/src/hypofuzz/frontend" run format && shed
elif [ "$1" = "deps" ]; then
    tox -e deps
elif [ "$1" = "deps-js" ]; then
    npx npm-check-updates -u --packageFile src/hypofuzz/frontend/package.json && npm install --prefix src/hypofuzz/frontend
else
    echo "Unknown build target $1. Available targets: docs, docs-clean, dashboard, dashboard-profiling, dashboard-json, dashboard-demo, test, format"
    exit 1
fi
