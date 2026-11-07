# LaunchOS web UI: delegated task contract

You own **only** the files under `web/` (except this file, `web/mock/` fixtures that already exist are yours to extend).
Do not create or edit anything outside `web/`. The backend (`backend/`) is owned by someone else and is served from the same origin.

## What to build

A single-page app for **LaunchOS**, an AI-native business launch platform. A founder submits an idea; specialist AI agents
(Research, Product, Builder, Marketing, Readiness) collaborate in **Switch rooms** and produce deliverables. A human must
approve the final launch decision.

Files: `web/index.html`, `web/app.js`, `web/styles.css` (plain HTML/CSS/vanilla JS, ES modules OK, **no build step, no npm**).
Markdown rendering: write a small, safe renderer in `web/markdown.js` (headings, lists, bold/italic, code, tables, links). Escape HTML first; never inject raw model output as HTML.

### Screens (one page, hash routing is fine)

1. **New launch** form: idea (textarea, required), founder name, target customer, constraints. Submit → `POST /api/launches`, then go to that launch.
   Show a "Load sample idea" button that fills the form with: idea "A subscription service that delivers locally roasted coffee to remote workers in Bengaluru, with a Slack bot for team re-orders", founder "Asha Rao", target "Remote-first startups in Bengaluru with 10–200 staff", constraints "Launch in 6 weeks, budget ₹5 lakh, no custom hardware".
2. **Launch list** (sidebar or top): `GET /api/launches`, newest first, status badge.
3. **Launch detail**:
   - Header: name, idea, status badge, created time.
   - **Pipeline**: five stage cards in order (research → product → builder → marketing → readiness) showing agent name, status (`pending|running|done|failed|waiting_approval`), duration, the Switch room name. Running = animated indicator. Failed = error text + "Retry stage" button → `POST /api/launches/{id}/retry` with `{"stage": key}`.
   - **Switch room activity**: a chronological feed from `GET /api/launches/{id}/timeline` (room, sender, kind, body; body is markdown, collapse long messages to ~6 lines with "show more"). Make clear this comes from Switch rooms (e.g. a "via Switch" label + room chip).
   - **Deliverables** tabs: Research, Product spec & backlog (render `backlog` as a table: id, title, priority, estimate, acceptance), Landing page (iframe of `landing.url` + "Open in new tab"), Marketing, Readiness (score as a meter 0–100, checks list with pass/warn/fail icons).
   - **Approvals** panel: each approval with title, description, status. Pending → Approve / Reject buttons with a required note and "decided by" name → `POST /api/launches/{id}/approvals/{approval_id}` with `{"decision":"approve"|"reject","note":"...","decided_by":"..."}`. Show who decided and when.
   - Links: Switch rooms (`switch.rooms[].url`), Mattermost, Gateway if present.
   - Poll `GET /api/launches/{id}` and the timeline every 2 s while status is not `launched|rejected|failed`.
4. **Health bar** (footer or header): `GET /api/health` → show Switch connected/disconnected, LLM mode and model.

### Quality bar
- Polished, modern, responsive (works at 375 px wide). Dark-on-light, one accent colour (#5B5BD6 or similar), system font stack.
- Loading, empty and error states for every fetch (show the API error message).
- Accessible: labels on inputs, buttons have text, focus styles, `aria-live` on the status area.
- No external network requests except optional Google Fonts.

## API (same origin). All JSON. Errors: non-2xx with `{"detail": "message"}`.

```
GET  /api/health
  → {"ok":true,"switch":{"ok":true,"api_url":"...","gateway_url":"http://localhost:3000","mattermost_url":"http://localhost:8065"},
     "llm":{"ok":true,"mode":"live"|"offline","model":"qwen/qwen3-4b-2507"}}

POST /api/launches   {"idea":str,"founder_name":str?,"target_customer":str?,"constraints":str?}
  → 201 {"id":"lch_ab12cd"}

GET  /api/launches
  → [{"id","name","status","created_at"}]

GET  /api/launches/{id}
  → {"id","name","idea","founder_name","target_customer","constraints","status","created_at","updated_at",
     "stages":[{"key":"research","title":"Market research","agent":"research-analyst","status":"done",
                "started_at":"ISO","finished_at":"ISO","room_name":"lch-ab12cd-research","error":null}],
     "deliverables":{
        "research":{"markdown":"..."} | null,
        "product":{"markdown":"...","backlog":[{"id":"LOS-1","title":"...","priority":"P0","estimate":"2d","acceptance":"..."}]} | null,
        "builder":{"url":"/api/launches/{id}/landing","summary":"..."} | null,
        "marketing":{"markdown":"..."} | null,
        "readiness":{"markdown":"...","score":78,"checks":[{"name":"...","status":"pass"|"warn"|"fail","detail":"..."}]} | null},
     "approvals":[{"id":"apr_1","title":"Approve public launch","description":"...","status":"pending"|"approved"|"rejected",
                   "decided_by":null,"note":null,"decided_at":null}],
     "switch":{"rooms":[{"id":"!abc","name":"lch-ab12cd-hq","purpose":"...","url":"http://localhost:8065/..."}]}}
  status ∈ queued | running | waiting_approval | launched | rejected | failed

GET  /api/launches/{id}/timeline
  → [{"ts":"ISO","room":"lch-ab12cd-research","sender":"research-analyst","kind":"message"|"handoff"|"deliverable"|"approval","body":"markdown"}]

POST /api/launches/{id}/approvals/{approval_id}  {"decision","note","decided_by"} → updated launch
POST /api/launches/{id}/retry {"stage":"research"} → updated launch
GET  /api/launches/{id}/landing → text/html (the generated landing page)
```

## Mock mode (for your own testing)
`web/mock/` holds `health.json`, `launches.json`, `launch.json`, `timeline.json`. If the page is opened with `?mock=1`,
`app.js` must read these files instead of calling the API (POSTs just log and return the mock launch). Create these fixtures yourself with realistic content matching the shapes above.

## Acceptance criteria
1. `python3 -m http.server -d web 8099` then `http://localhost:8099/?mock=1` renders every screen with no console errors.
2. All fields above are displayed; approvals POST the exact body shape.
3. No files outside `web/` created or modified.
4. When done, write `web/DONE.md` listing files and anything incomplete.
