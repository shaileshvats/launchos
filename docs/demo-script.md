# Demo script (about 4 minutes)

**Before you start:** the Switch stack is up (`scripts/switch-up.sh`), LM Studio has `qwen/qwen3-4b-2507` loaded,
LaunchOS is running (`scripts/run.sh`), and Mattermost is open and signed in as `user` in a second window.

| Time | Show | Say |
|---|---|---|
| 0:00 | LaunchOS home; the health bar shows Switch connected, model live | "LaunchOS turns a founder's idea into an approved launch. The work is done by six AI agents that coordinate in Switch." |
| 0:20 | Click **Load sample idea** (BrewDesk coffee subscription), then **Start launch** | "One idea in. The conductor agent opens six Switch rooms: HQ plus one per specialist." |
| 0:40 | Switch to Mattermost; the new `lch-…-hq` and team channels appear | "These are real Switch rooms bridged to Mattermost. I'm in them as a human teammate." |
| 1:00 | In `lch-…-research`: the conductor's handoff and the analyst's "On it" | "A handoff is a Switch message. The research analyst picks it up from its own event stream and reads the brief from HQ." |
| 1:30 | Back in LaunchOS: the pipeline advances; the activity feed is labelled "via Switch" | "Each specialist posts its deliverable to HQ. The next one reads it from there, so context moves through Switch." |
| 2:00 | Deliverable tabs: research competitor table, backlog table, the live landing page | "Research, a prioritised backlog, and a working landing page, each built on the previous step." |
| 2:40 | Readiness tab: score and checks; legal is marked *needs human review* | "Readiness comes from deterministic checks over what was delivered, not the model's opinion. Legal is never auto-passed." |
| 3:00 | Mattermost HQ: the auditor's "Human approval needed" message. Type `approve Legal review booked, roasters confirmed` | "The launch is a consequential decision, so it waits for a person. I can approve right here in the room…" |
| 3:20 | LaunchOS: the approval shows approved by `user` via Switch room; status **launched** | "…and the decision, the reason and who made it are recorded in Switch and in LaunchOS." |
| 3:40 | Optional: open a failed stage and click **Retry** | "If an agent fails or times out, the founder sees the error and can retry that stage with a fresh handoff." |

**Fallback:** if the model is slow or unavailable, set `LLM_MODE=offline` and restart LaunchOS. The whole Switch
workflow still runs, and every deliverable is labelled template output.
