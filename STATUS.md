# Build status (hackathon log)

_Last updated: 2026-11-07, about 19:30 IST. Deadline 23:59 IST._

## Done and verified

| Item | How it was verified |
|---|---|
| Switch 0.31.0 self-hosted (server, Postgres, Mattermost, Gateway) | `GET :8000/health` → ok; Gateway :3000 → 200; Mattermost ping → 200; the setup container registered the Mattermost bridge |
| Six Switch agents with their own API keys and event streams | `/api/health` lists all six as connected; heartbeats return 200 |
| Rooms per launch (HQ + 5 team rooms), bridged to Mattermost, human invited | Six `lch-…` channels exist in Mattermost team `switch` for each launch |
| Handoff → specialist → deliverable → done → next handoff, all over Switch | Live run `lch_50e95f`: five stages completed with Qwen3-4B (27–44 s each); the timeline was read back from the rooms |
| Specialists read their inputs from Switch (`read_context` on HQ), not from the DB | `_read_inputs` in `workflow.py`; the integration test asserts every `[deliverable]` is in the HQ room |
| Human approval in Mattermost | Posted `approve …` as `user` in the HQ channel; the launch became `launched` with "via Switch room (Mattermost)" and the decision was posted back to Switch |
| Human approval in the UI, with validation (note + name required, no double decisions) | Integration test |
| Readiness from 8 deterministic checks; legal is always "needs human review" | Unit tests; live score 94/100 |
| Landing page rendered from escaped JSON, served with `script-src 'none'`, sandboxed iframe | Unit test (script injection is escaped); seen in the UI |
| Web UI against the real backend | Built-in browser: no console errors; pipeline, deliverable tabs, iframe, Switch feed (29 messages) and approval panel all render |
| Tests | `scripts/test.sh`: 11 passed (9 unit, 2 Switch integration) |
| Fake statistics | Prompt forbids unlabelled numbers; every live deliverable carries an "AI-generated draft… unverified estimates" note |

## Delegation

- Web UI (`web/` only) was built by a Sonnet subagent against `web/CONTRACT.md`, then integrated and tested here.
- OpenCode/DeepSeek delegation was attempted, but running OpenCode with `--auto` (self-approving permissions) was
  blocked by this environment's safety policy, so it wasn't used.

## Remaining / known limits

- Public GitHub repo: not created. It needs the owner's go-ahead and GitHub credentials.
- Two leftover probe agents (`launchos-probe`, `launchos-probe2`) and the `itest-*` test agents remain in the local
  Switch server. They're harmless.
- The landing page's waitlist form is a prototype and doesn't submit.
- Only tested on macOS Apple Silicon with LM Studio Qwen3-4B-Instruct-2507.
