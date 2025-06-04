#!/usr/bin/env bash

# poor man's makefile. We could just use make here,
# but ./build.sh <args> matches hypothesis.

set -o xtrace
set -o errexit
set -o nounset

ROOT="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"

if [ "$1" = "docs" ]; then
    sphinx-build "$ROOT/src/hypofuzz/docs" "$ROOT/src/hypofuzz/frontend/public/docs"
elif [ "$1" = "dashboard" ]; then
    npm --prefix "$ROOT/src/hypofuzz/frontend" run build
else
    echo "Unknown build target $1. Availabletargets: docs, dashboard"
    exit 1
fi
