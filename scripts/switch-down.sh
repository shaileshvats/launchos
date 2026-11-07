#!/usr/bin/env bash
# Stop the Switch stack. Data (rooms, messages, agents) is kept in Docker volumes; add -v to delete it.
set -euo pipefail
cd "$(dirname "$0")/../switch"
docker compose -p "${SWITCH_PROJECT:-launchos-switch}" -f docker-compose.yml --env-file .env --profile collab --profile gateway --project-directory . down "$@"
