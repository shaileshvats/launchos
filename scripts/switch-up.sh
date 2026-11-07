#!/usr/bin/env bash
# Start the official Switch 0.31.0 self-host stack: Switch server, Postgres, Mattermost, Gateway.
set -euo pipefail
cd "$(dirname "$0")/../switch"
docker compose -p launchos-switch -f docker-compose.yml --env-file .env --profile collab --profile gateway --project-directory . up -d
echo "Waiting for Switch..."; for i in $(seq 1 60); do curl -sf http://127.0.0.1:8000/health >/dev/null && break; sleep 2; done
curl -sf http://127.0.0.1:8000/health && echo " Switch API ready on :8000 · Gateway :3000 · Mattermost :8065"
