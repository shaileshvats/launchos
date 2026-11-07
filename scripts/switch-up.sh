#!/usr/bin/env bash
# Start the official Switch 0.31.0 self-host stack: Switch server, Postgres, Mattermost, Gateway.
# Binds to 127.0.0.1 only (SWITCH_BIND_ADDR in switch/.env). Override the compose project with SWITCH_PROJECT.
set -euo pipefail
cd "$(dirname "$0")/../switch"
project="${SWITCH_PROJECT:-launchos-switch}"
port=$(grep '^API_HOST_PORT=' .env | cut -d= -f2); port="${port:-8000}"
docker compose -p "$project" -f docker-compose.yml --env-file .env --profile collab --profile gateway --project-directory . up -d
echo "Waiting for Switch on :$port ..."
for _ in $(seq 1 90); do curl -sf "http://127.0.0.1:$port/health" >/dev/null && break; sleep 2; done
curl -sf "http://127.0.0.1:$port/health" >/dev/null || { echo "Switch did not become healthy; see: docker compose -p $project logs switch" >&2; exit 1; }
echo "Switch API ready on :$port (Gateway :$(grep '^GATEWAY_HOST_PORT=' .env | cut -d= -f2), Mattermost :$(grep '^MATTERMOST_HOST_PORT=' .env | cut -d= -f2))"
