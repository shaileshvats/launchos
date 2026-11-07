#!/usr/bin/env bash
# Unit tests always; the Switch integration test runs when a Switch server is reachable.
set -euo pipefail
cd "$(dirname "$0")/../backend"
../.venv/bin/python -m pytest -v tests/ "$@"
