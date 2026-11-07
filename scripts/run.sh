#!/usr/bin/env bash
# Run LaunchOS (API + web UI) on http://127.0.0.1:8787
set -euo pipefail
cd "$(dirname "$0")/../backend"
exec ../.venv/bin/python -m uvicorn launchos.app:create_app --factory --host 127.0.0.1 --port "${PORT:-8787}"
