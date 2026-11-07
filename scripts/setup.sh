#!/usr/bin/env bash
# One-time setup: Switch stack secrets, Python venv, LaunchOS .env.
set -euo pipefail
cd "$(dirname "$0")/.."
if [ ! -f switch/.env ]; then
  cp switch/.env.example switch/.env
  for key in DB_PASSWORD DB_OWNER_PASSWORD AGENT_REGISTRATION_TOKEN GATEWAY_ADMIN_PASSWORD \
             MATTERMOST_ADMIN_PASSWORD MATTERMOST_USER_PASSWORD JWT_SECRET_KEY CONTROLLER_TOKEN_SECRET; do
    sed -i.bak "s|^${key}=.*|${key}=$(openssl rand -hex 24)|" switch/.env
  done
  sed -i.bak "s|^SECRET_KEYS=.*|SECRET_KEYS=local:$(openssl rand -hex 32)|" switch/.env && rm -f switch/.env.bak
  echo "Generated switch/.env with fresh secrets."
fi
python3 -m venv .venv
.venv/bin/pip install -q -r backend/requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  tok=$(grep '^AGENT_REGISTRATION_TOKEN=' switch/.env | cut -d= -f2)
  sed -i.bak "s|^SWITCH_REGISTRATION_TOKEN=.*|SWITCH_REGISTRATION_TOKEN=${tok}|" .env && rm -f .env.bak
  echo "Wrote .env"
fi
echo "Setup done. Next: scripts/switch-up.sh, then scripts/run.sh"
