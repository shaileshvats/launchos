# Third-party notices

## Agent Switch (SandboxAQ)

`switch/docker-compose.yml` and `switch/.env.example` are copied from the
[Agent Switch](https://github.com/sandbox-quantum/switch) repository at tag `switch-v0.31.0`
(`deploy/local/standalone-docker-compose.yml` and `.env.example`). The only change is `SWITCH_VERSION=0.31.0` in
`.env.example`. The compose file pulls Switch's published container images from `ghcr.io/sandbox-quantum`.

Agent Switch is licensed under the Apache License 2.0 as limited by the Commons Clause License Condition v1.0. See
`switch/SWITCH-LICENSE` and `switch/SWITCH-NOTICE`. Those terms apply to the copied files and the Switch images,
not to the rest of LaunchOS.

## Python dependencies (installed by `scripts/setup.sh`, not vendored)

FastAPI (MIT), Uvicorn (BSD-3-Clause), HTTPX (BSD-3-Clause), pytest (MIT).

## Container images pulled by the Switch stack (not vendored)

PostgreSQL 16 (PostgreSQL License), Mattermost Team Edition 11.9.0 (MIT-licensed source; see Mattermost's terms).
