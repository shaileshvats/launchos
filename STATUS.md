# Build status (hackathon log)

_Last updated: 2026-11-07, about 20:00 IST. Deadline 23:59 IST._

## Done and verified

| Item | How it was verified |
|---|---|
| Switch 0.31.0 self-hosted (server, Postgres, Mattermost, Gateway) | `GET :8000/health` → ok; Gateway :3000 → 200; Mattermost ping → 200; the setup container registered the Mattermost bridge |
| Six Switch agents with their own API keys and event streams | `/api/health` lists all six as connected; heartbeats return 200 |
| Rooms per launch (HQ + 5 team rooms), bridged to Mattermost, human invited | Six `lch-…` channels exist in Mattermost team `switch` for each launch |
| Handoff → specialist → deliverable → done → next handoff, all over Switch | Live run `lch_50e95f`: five stages completed with Qwen3-4B (27–44 s each); the timeline was read back from the rooms |
| Specialists read their inputs from Switch (`read_context` on HQ), not from the DB | `_read_inputs` in `workflow.py`; the integration test asserts every `[deliverable]` is in the HQ room |
| Three live runs with Qwen3-4B | `lch_50e95f` BrewDesk (approved in Mattermost), `lch_946169` started from the UI (approved in the UI by Asha Rao), `lch_7976c6` AI study planner (247 s for 5 stages; left waiting for approval as the demo state) |
| Human approval in Mattermost | Posted `approve …` as `user` in the HQ channel; the launch became `launched` with "via Switch room (Mattermost)" and the decision was posted back to Switch |
| Human approval in the UI, with validation (note + name required, no double decisions) | Integration test |
| Readiness from 8 deterministic checks; legal is always "needs human review" | Unit tests; live score 94/100 |
| Landing page rendered from escaped JSON, served with `script-src 'none'`, sandboxed iframe | Unit test (script injection is escaped); seen in the UI |
| Web UI against the real backend | Built-in browser: no console errors; pipeline, deliverable tabs, iframe, Switch feed (29 messages) and approval panel all render |
| Tests | `scripts/test.sh`: 12 passed (9 unit, 3 Switch integration, including fail → report in Switch → retry → complete) |
| Fresh-clone reproducibility | Cloned the repo, ran `scripts/setup.sh` and started a separate Switch stack on alternate ports. `scripts/test.sh` passed 12/12. `scripts/run.sh` then took a launch through all 5 stages and a reject decision. The verification stack was then deleted |
| Fresh-server robustness | The first fresh-stack run exposed Switch returning 500 on early stream opens, which lost a handoff. Fixed by waiting for all streams to attach and re-sending unacknowledged handoffs; re-verified on a rebuilt stack |
| Secret scan | All 41 objects in git history checked: (1) exact match against every real secret on this machine (Switch and LaunchOS `.env` values, all agent API keys, the Mattermost session token): no secret found; (2) pattern scan (GitHub, OpenAI, AWS, Google and Slack tokens, private keys, JWTs, long hex strings, password/token assignments): no hits. Gitleaks couldn't be downloaded here (blocked by the environment's policy) |
| Fake statistics | Prompt forbids unlabelled numbers; every live deliverable carries an "AI-generated draft… unverified estimates" note |

## Delegation

- Web UI (`web/` only) was built by a Sonnet subagent against `web/CONTRACT.md`, then integrated and tested here.
- OpenCode/DeepSeek delegation was attempted, but running OpenCode with `--auto` (self-approving permissions) was
  blocked by this environment's safety policy, so it wasn't used.

## Remaining / known limits

- Two leftover probe agents (`launchos-probe`, `launchos-probe2`) and the `itest-*` test agents remain in the local
  Switch server. They're harmless.
- The landing page's waitlist form is a prototype and doesn't submit.
- Only tested on macOS Apple Silicon with LM Studio Qwen3-4B-Instruct-2507.
