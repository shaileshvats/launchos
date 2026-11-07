# LaunchOS

**From a founder's idea to an approved launch, by a team of AI agents that work together in Switch rooms.**

A founder describes a business idea. Five specialist agents (research, product, prototype, marketing, launch readiness)
pick up the work in [Switch](https://github.com/sandbox-quantum/switch) rooms. They hand off to each other, read each
other's deliverables from the shared HQ room, and finish with a launch-readiness assessment. The public launch only
happens when a named human approves it, either in the LaunchOS UI or by replying `approve <reason>` in the
Mattermost room.

What one run produces:

1. Market research with segments, a competitor table, sizing assumptions and risks
2. A product spec and a prioritised backlog (IDs, priority, estimate, acceptance criteria)
3. A working landing page (hero, features, how it works, pricing, FAQ, waitlist form)
4. A marketing strategy: positioning, channel plan, 4-week calendar and launch copy
5. A readiness score from 8 deterministic checks, a risk review, and a human approval gate

## Switch is the workflow, not a chat window

- Each agent is a separate registered Switch agent with its own API key and its own live event stream.
- Every launch gets six Switch rooms (HQ plus one per specialist), bridged to Mattermost, with the human invited.
- Handoffs, completion reports, failures, approval requests and decisions are all Switch messages. The conductor
  starts the next stage only when it receives the previous specialist's `[done]` report on its event stream.
- **A specialist's only input is what it reads from the HQ room** with `read_context`: the founder brief and earlier
  deliverables. It never reads LaunchOS's database.
- The activity feed in the UI is read back from the Switch rooms.

See [docs/architecture.md](docs/architecture.md) for the full flow and failure handling.

## Quick start (macOS/Linux, Docker, Python 3.9+)

```bash
scripts/setup.sh        # generates Switch secrets, creates .venv, writes .env
scripts/switch-up.sh    # official Switch 0.31.0 stack: server :8000, Mattermost :8065, Gateway :3000
scripts/run.sh          # LaunchOS on http://127.0.0.1:8787
```

The first `switch-up.sh` downloads about 1.5 GB of images.

**Model:** by default LaunchOS calls LM Studio on `http://127.0.0.1:1234/v1` with `qwen/qwen3-4b-2507`. Load that
model, or point `LLM_BASE_URL` / `LLM_MODEL` / `LLM_API_KEY` in `.env` at any OpenAI-compatible endpoint.

With `LLM_MODE=auto` and no model reachable, LaunchOS still runs the whole Switch workflow. It uses offline templates,
and every deliverable is clearly labelled as template output.

**See the rooms:** open http://localhost:8065 and sign in as `user`. The password is `MATTERMOST_USER_PASSWORD` in
`switch/.env`. Channels are named `lch-xxxxxx-hq`, `lch-xxxxxx-research`, and so on.

## Tests

```bash
scripts/test.sh
```

- **9 unit tests** cover parsers, the SSE reader, readiness scoring, landing-page escaping, the store and the offline pipeline.
- **2 integration tests** run the full journey against the running Switch server in offline mode, under `itest-`
  agent names. They check from the Switch rooms themselves that all five deliverables, the approval request and the
  decision were posted there. They're skipped when no Switch server is configured.

## Project layout

```
backend/launchos/
  switch_client.py  Switch agent protocol: registration, operations, SSE stream, heartbeat
  workflow.py       conductor + specialists, handoffs, approvals, retries, watchdog, timeline
  specialists.py    prompts, JSON parsing, readiness checks, landing-page renderer, offline mode
  llm.py            OpenAI-compatible client
  store.py          SQLite
  app.py            FastAPI API + static UI
backend/tests/      unit + Switch integration tests
web/                UI (vanilla JS, no build step); ?mock=1 runs it on fixtures
switch/             pinned official Switch compose file + env template (Apache 2.0 + Commons Clause)
docs/               architecture, demo script
```

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | Switch and agent connection, model status |
| POST | `/api/launches` | `{idea, founder_name?, target_customer?, constraints?, name?}` starts a launch |
| GET | `/api/launches`, `/api/launches/{id}` | List launches, or get one with stages, deliverables, approvals and Switch room links |
| GET | `/api/launches/{id}/timeline` | Activity read back from the launch's Switch rooms |
| POST | `/api/launches/{id}/approvals/{aid}` | `{decision: approve\|reject, note, decided_by}` |
| POST | `/api/launches/{id}/retry` | `{stage}` retries a failed stage with a fresh handoff |
| GET | `/api/launches/{id}/landing` | The generated landing page |

## Honest limits

- Deliverables come from a 4-billion-parameter local model with no internet access. Figures are estimates and every
  live deliverable says so. Treat the output as a strong first draft.
- The landing page is a static prototype; its waitlist form doesn't submit anywhere.
- Switch's task protocol is marked "not ready for use" in 0.31.0, so handoffs use room messages with markers instead.
- Tested on macOS (Apple Silicon) with Switch 0.31.0 and Qwen3-4B-Instruct-2507 in LM Studio. Nothing else was tested.
- The Switch stack and LaunchOS bind to localhost and have no authentication on the LaunchOS API.

## Licence

LaunchOS code: MIT (see `LICENSE`). Switch is a separate project under Apache 2.0 with the Commons Clause
(`switch/SWITCH-LICENSE`). LaunchOS only uses its published images and protocol.
