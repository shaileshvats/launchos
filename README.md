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

## Quick start

**Requirements:**
- Docker with Compose v2
- Python 3.9 or later
- `openssl` and `curl`
- About 2.5 GB of disk for the Switch images
- Optional: LM Studio, or any OpenAI-compatible model endpoint

Tested on macOS (Apple Silicon); the scripts are plain bash and should work on Linux, but that is untested.

```bash
git clone https://github.com/shaileshvats/launchos && cd launchos
scripts/setup.sh        # generates fresh Switch secrets, creates .venv, writes .env (both .env files are git-ignored, mode 600)
scripts/switch-up.sh    # official Switch 0.31.0 stack, bound to 127.0.0.1: API :8000, Mattermost :8065, Gateway :3000
scripts/run.sh          # LaunchOS on http://127.0.0.1:8787
```

`scripts/switch-down.sh` stops the stack and keeps its data; `scripts/switch-down.sh -v` deletes the data too.
To run a second stack beside the first, change the four `*_HOST_PORT` values in `switch/.env` and set
`SWITCH_PROJECT=<name>`.

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
- **3 integration tests** run against the running Switch server in offline mode, under `itest-` agent names.
  - The full journey: they check from the Switch rooms themselves that all five deliverables, the approval request and
    the decision were posted there.
  - The failure path: an unreachable model fails the research stage, the failure is reported in Switch, and a retry
    completes the pipeline.
  - Input validation and 404s.

  They're skipped when no Switch server is configured.

The integration tests register `itest-` and `itest2-` agents in your Switch server and leave their rooms behind.
Before publishing, the suite was also run from a fresh clone against a brand-new, separate Switch stack: 12 passed.

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
STATUS.md           build log: what was verified, and how
THIRD_PARTY_NOTICES.md
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

## Known limitations

- **Localhost only, no authentication.** The LaunchOS API and UI have no login, and anyone who can reach port 8787 can
  start launches and approve them. Everything binds to 127.0.0.1 by default. Don't expose it on a network or the
  internet without adding authentication and TLS in front.
- **The waitlist form is a prototype.** The generated landing page is static: its email form doesn't submit or store
  anything.
- **Handoffs don't use Switch's task protocol.** Switch 0.31.0 documents its task operations (`delegate_task` and
  related) as "present but not ready for use". So LaunchOS hands off work with ordinary room messages carrying markers
  such as `[handoff:lch_ab12cd:research]`, and tracks completion through `[done]` and `[failed]` replies.
- **A fresh Switch server can drop event streams.** In its first minutes it can return HTTP 500 when an agent opens
  its stream (`No incarnation drawn`). LaunchOS waits for every agent's stream to attach before it accepts launches,
  reconnects dropped streams, and re-sends any handoff not acknowledged within 30 seconds (up to 3 times).
- **Model quality.** Deliverables come from a 4-billion-parameter local model with no internet access. Figures are
  unverified estimates, and every live deliverable says so. Treat the output as a first draft.
- **One process, one machine.** The six agents run inside the LaunchOS process. Launch state is in a local SQLite
  file, and a restart marks any running stage as failed, so it can be retried.
- **Tested setup.** Tested only on macOS (Apple Silicon) with Switch 0.31.0 and Qwen3-4B-Instruct-2507 in LM Studio.

## Licence

LaunchOS code is under the MIT licence (see `LICENSE`).

Switch is a separate project under Apache 2.0 with the Commons Clause. `switch/docker-compose.yml` and
`switch/.env.example` are copied from it, and the stack runs its published images. Those files and images remain
under Switch's terms: see `switch/SWITCH-LICENSE`, `switch/SWITCH-NOTICE` and `THIRD_PARTY_NOTICES.md`.
