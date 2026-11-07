# Architecture

## Components

| Component | Where | What it does |
|---|---|---|
| Switch server 0.31.0 | `switch/docker-compose.yml` (official standalone stack) | Rooms, agent identities, message history, the agent event stream, the Mattermost bridge |
| Mattermost | same stack | Where people see and join the rooms; humans can approve a launch by replying in the HQ room |
| Switch Gateway | same stack, port 3000 | Switch's admin console (agents, rooms) |
| LaunchOS backend | `backend/launchos/` (FastAPI, Python 3.9+) | Runs six Switch agents, the HTTP API and serves the web UI |
| LaunchOS web UI | `web/` (vanilla JS, no build step) | Founder journey: submit an idea, watch the pipeline and Switch activity, read deliverables, approve |
| Language model | any OpenAI-compatible endpoint (default LM Studio, Qwen3-4B-Instruct-2507) | Writes the deliverables |
| SQLite | `data/launchos.db` | Launch status, structured deliverables, agent credentials |

## The six agents

Each one is registered in Switch with its own identity and API key (`POST /agents`), and keeps its own event stream open
(`GET /agents/{id}/events`, heartbeat every 2 s).

| Agent | Room | Produces |
|---|---|---|
| `launchos-conductor` | all rooms | Creates the rooms, posts the founder brief, hands off work, tracks completion and approvals |
| `research-analyst` | `<launch>-research` | Segments, competitor table, sizing assumptions, risks |
| `product-strategist` | `<launch>-product` | Spec (problem, personas, MVP, metrics) and a prioritised backlog |
| `prototype-builder` | `<launch>-build` | Landing-page copy rendered into a working, escaped HTML page |
| `growth-marketer` | `<launch>-growth` | Positioning, channel plan, 4-week calendar, launch copy |
| `launch-auditor` | `<launch>-readiness` | 8 deterministic readiness checks, a score, a risk narrative, and the human approval request |

## How work moves through Switch

```
founder ──POST /api/launches──▶ conductor
conductor: create_room ×6 (HQ + one per specialist, bridged to Mattermost, human invited), link_rooms team→HQ
conductor ──[brief]──────────────▶ HQ room
for each stage:
  conductor ──[handoff] @agent──▶ team room ──event stream──▶ specialist
  specialist ── read_context(HQ) ◀── brief + every earlier [deliverable]        (its only input)
  specialist ──[deliverable]──────▶ HQ room                                     (input for the next agent)
  specialist ──[done] @conductor──▶ team room ──event stream──▶ conductor ──▶ next handoff
launch-auditor ──[approval] @user─▶ HQ room
human: "approve <reason>" reply in Mattermost  ─or─  Approve in the LaunchOS UI
conductor ──[decision]───────────▶ HQ room; launch status = launched | rejected
```

Markers such as `[handoff:lch_ab12cd:research]` make messages machine-readable while staying readable for people.

**What Switch is the source of truth for:** the coordination (handoffs, completion reports, failures), the context each
specialist works from (it reads the HQ room; it is never handed LaunchOS's database), the approval request and the
decision record, and the activity feed in the UI (read back from the rooms with `read_context`).

**What SQLite holds:** pipeline status for the UI, structured copies of deliverables (backlog rows, landing-page JSON
and HTML), and the agents' API keys. Credentials never leave `data/`.

## Failure handling

- A specialist that fails posts `[failed:…]` with the reason; the stage and launch are marked failed, and the founder
  can retry that stage (`POST /api/launches/{id}/retry`), which posts a fresh handoff.
- A watchdog fails any stage with no report within `STAGE_TIMEOUT` (default 420 s).
- On restart, any stage that was running is marked failed with "Interrupted by a LaunchOS restart", so nothing hangs.
- Event streams reconnect with the same connection id and `Last-Event-ID`; duplicate deliveries are ignored by message id.
- Model JSON that doesn't parse gets one corrective retry, then the stage fails visibly.
- `LLM_MODE=auto` falls back to offline templates when the model is unreachable; that output is labelled
  "Offline template output" everywhere it appears.

## Safety choices

- Model output is untrusted: the landing page is rendered from escaped JSON fields into a fixed template, served with
  `script-src 'none'`, and shown in a sandboxed iframe; the UI's Markdown renderer escapes HTML first.
- Every live deliverable carries a note that figures are unverified model estimates.
- Readiness is scored by deterministic checks over what was delivered, not by the model's opinion; legal/compliance
  is always "needs human review".
- The consequential step (public launch) needs a named human decision with a reason, recorded in Switch.
- The Switch stack binds to 127.0.0.1 with freshly generated secrets; `.env` files are git-ignored.
