# LaunchOS web UI: status

## Files (all under `web/`)
- `index.html` - shell: top bar, launch list sidebar (drawer on mobile), main view, health footer, toast area.
- `app.js` - ES module: API layer + mock mode, hash router (`#/new`, `#/launch/{id}`), all screens, 2 s polling.
- `markdown.js` - safe Markdown renderer (HTML-escapes first; links limited to http(s) and relative; no images; headings demoted two levels).
- `styles.css` - light theme, accent `#5B5BD6`, system font stack, responsive down to 375 px.
- `mock/health.json`, `mock/launches.json`, `mock/launch.json`, `mock/timeline.json` - fixtures (BrewLoop coffee-subscription sample: 5 stages, 10-item backlog, readiness 78/100 with 8 checks, 21 Switch-room messages, 1 pending approval).
- `mock/landing.html` - self-contained sample landing page (no scripts, no external requests) used by the mock Landing page tab.

## How mock mode works
Open `http://localhost:8099/?mock=1`. `app.js` then reads `mock/*.json` instead of `/api/*`.
- Any `/api/launches/{id}` returns `mock/launch.json` (the list shows 3 entries, but all open the same detail).
- POSTs are logged to the console (`[mock] POST ...`) and return the mock launch. `POST /api/launches` returns `{id: "lch_7f3a9c"}`.
- Convenience beyond the contract: an approval POST also mutates the in-memory copy (approval becomes approved/rejected, launch becomes launched/rejected, waiting stage becomes done) so the flow can be demoed. A page reload resets it.
- Mock landing URL is `mock/landing.html`; with the real backend the contract URL `/api/launches/{id}/landing` is used as given.

## Behaviour notes
- Approvals POST the exact body `{"decision":"approve"|"reject","note":"...","decided_by":"..."}`; note and name are required (validated client side). "Decided by" is remembered in localStorage.
- Landing page iframe uses `sandbox="allow-same-origin"` only (no scripts).
- Polling every 2 s for launch + timeline until status is `launched|rejected|failed`; sections only re-render when their data changes (typed approval text, expanded messages, selected tab and feed scroll are preserved).
- Health bar polls every 15 s; launch list every 15 s.

## Verification done
- All files served 200 by `python3 -m http.server 8099 --directory web`; mock JSON files parse.
- No Node available: `app.js` and `markdown.js` syntax-checked with macOS JavaScriptCore (`jsc -m`; a deliberately bad file gives SyntaxError, app.js only stops at a runtime `URLSearchParams` reference, i.e. it parsed).
- Loaded in the built-in browser with `?mock=1`: no console errors; all five tabs, approval validation + submit, new-launch form with sample, 375 px layout (no horizontal overflow), non-mock error states (404 API) checked.

## Incomplete / caveats
- Not tested against the real backend (none was running); error text comes from `{"detail": ...}` as specified.
- Mock list entries other than BrewLoop show the same detail page.
- Mobile hides the "Mock data" pill to save room; the footer still works.
- The mobile launch drawer closes via backdrop click, Escape, or choosing a launch (no explicit close button).
