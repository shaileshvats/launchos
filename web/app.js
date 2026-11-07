/*
 * LaunchOS web UI - plain ES module, no build step.
 *
 * Add ?mock=1 to the URL to read fixtures from ./mock/*.json instead of /api/*.
 * All dynamic text is inserted with textContent / DOM APIs. The only innerHTML
 * use is (a) static SVG icon strings defined below and (b) the output of the
 * escaping Markdown renderer in markdown.js.
 */
import { renderMarkdown, safeUrl } from './markdown.js';

/* ================================================================ constants */

const MOCK = new URLSearchParams(location.search).has('mock');
const POLL_MS = 2000;
const SLOW_POLL_MS = 15000;
const TERMINAL = new Set(['launched', 'rejected', 'failed']);
const STAGE_ORDER = ['research', 'product', 'builder', 'marketing', 'readiness'];

const LAUNCH_LABELS = {
  queued: 'Queued',
  running: 'Running',
  waiting_approval: 'Awaiting approval',
  launched: 'Launched',
  rejected: 'Rejected',
  failed: 'Failed',
};
const STAGE_LABELS = {
  pending: 'Pending',
  running: 'Running',
  done: 'Done',
  failed: 'Failed',
  waiting_approval: 'Awaiting approval',
};
const APPROVAL_LABELS = { pending: 'Pending', approved: 'Approved', rejected: 'Rejected' };
const KIND_LABELS = { message: 'Message', handoff: 'Hand-off', deliverable: 'Deliverable', approval: 'Approval' };

const STAGE_META = {
  research: { label: 'Research', icon: 'research' },
  product: { label: 'Product', icon: 'product' },
  builder: { label: 'Builder', icon: 'builder' },
  marketing: { label: 'Marketing', icon: 'marketing' },
  readiness: { label: 'Readiness', icon: 'readiness' },
};

const TABS = [
  { key: 'research', label: 'Research' },
  { key: 'product', label: 'Product spec & backlog' },
  { key: 'builder', label: 'Landing page' },
  { key: 'marketing', label: 'Marketing' },
  { key: 'readiness', label: 'Readiness' },
];

const SAMPLE = {
  idea: 'A subscription service that delivers locally roasted coffee to remote workers in Bengaluru, with a Slack bot for team re-orders',
  founder_name: 'Asha Rao',
  target_customer: 'Remote-first startups in Bengaluru with 10–200 staff',
  constraints: 'Launch in 6 weeks, budget ₹5 lakh, no custom hardware',
};

const ICONS = {
  research: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
  product: '<path d="M9 5H6a1 1 0 0 0-1 1v13a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V6a1 1 0 0 0-1-1h-3"/><rect x="9" y="3" width="6" height="4" rx="1"/><path d="M9 12h6M9 16h4"/>',
  builder: '<path d="m8 8-5 4 5 4M16 8l5 4-5 4M14 5l-4 14"/>',
  marketing: '<path d="M3 11v2a1 1 0 0 0 1 1h2l5 4V6L6 10H4a1 1 0 0 0-1 1z"/><path d="M15 9a4 4 0 0 1 0 6M18 6.5a8 8 0 0 1 0 11"/>',
  readiness: '<path d="M12 3 5 6v5c0 4.5 3 8 7 10 4-2 7-5.5 7-10V6z"/><path d="m9 12 2 2 4-4"/>',
  check: '<path d="m5 12.5 4.5 4.5L19 7.5"/>',
  warn: '<path d="M12 4 2.5 20h19z"/><path d="M12 10v4M12 17.2v.1"/>',
  x: '<path d="m6 6 12 12M18 6 6 18"/>',
  ext: '<path d="M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  arrow: '<path d="M5 12h14M13 6l6 6-6 6"/>',
  doc: '<path d="M14 3H7a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1V7z"/><path d="M14 3v4h4M9 13h6M9 17h6"/>',
  switch: '<rect x="2" y="7" width="20" height="10" rx="5"/><circle cx="16.5" cy="12" r="2.4"/>',
  agent: '<rect x="5" y="8" width="14" height="11" rx="3"/><path d="M12 8V5M9.5 13h.01M14.5 13h.01M9 16.5h6"/>',
  clock: '<circle cx="12" cy="12" r="8.5"/><path d="M12 7.5V12l3 2"/>',
  desktop: '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
  phone: '<rect x="7" y="3" width="10" height="18" rx="2.5"/><path d="M11 18h2"/>',
};

/* ================================================================== helpers */

const $ = (sel, root = document) => root.querySelector(sel);
const enc = encodeURIComponent;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const cls = (s) => String(s == null ? '' : s).toLowerCase().replace(/[^a-z0-9_]/g, '');
const clone = (o) => JSON.parse(JSON.stringify(o));

/** Tiny hyperscript. Children: nodes, strings, numbers, arrays; null/false skipped. */
function h(tag, props, ...kids) {
  const el = document.createElement(tag);
  if (props) {
    for (const [k, v] of Object.entries(props)) {
      if (v == null || v === false) continue;
      if (k === 'class') el.className = v;
      else if (k === 'dataset') {
        for (const [dk, dv] of Object.entries(v)) if (dv != null) el.dataset[dk] = dv;
      }
      else if (k === 'html') el.innerHTML = v; // only ever trusted/escaped markup
      else if (k === 'value') el.value = v;
      else if (k.startsWith('on') && typeof v === 'function') el.addEventListener(k.slice(2), v);
      else if (v === true) el.setAttribute(k, '');
      else el.setAttribute(k, String(v));
    }
  }
  for (const kid of kids.flat(Infinity)) {
    if (kid == null || kid === false) continue;
    el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
  }
  return el;
}

/** Like el.replaceChildren(), but flattens arrays and skips null/false (native replaceChildren stringifies them). */
function setKids(el, ...kids) {
  el.replaceChildren(
    ...kids.flat(Infinity)
      .filter((k) => k != null && k !== false)
      .map((k) => (k.nodeType ? k : document.createTextNode(String(k))))
  );
}

function icon(name, size = 16) {
  return h('span', {
    class: 'icon',
    'aria-hidden': 'true',
    html:
      '<svg viewBox="0 0 24 24" width="' + size + '" height="' + size +
      '" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">' +
      (ICONS[name] || '') + '</svg>',
  });
}

function mdBlock(src) {
  const text = String(src == null ? '' : src);
  if (!text.trim()) return h('p', { class: 'muted' }, 'No content.');
  return h('div', { class: 'md', html: renderMarkdown(text) });
}

function prettyAgent(slug) {
  const s = String(slug || '').trim();
  if (!s) return 'Unknown';
  if (s.toLowerCase() === 'launchos') return 'LaunchOS';
  return s.replace(/[-_]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
}

function initials(slug) {
  const p = prettyAgent(slug).split(' ').filter(Boolean);
  if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
  return (p[0][0] + p[1][0]).toUpperCase();
}

function hueOf(str) {
  let n = 0;
  for (let i = 0; i < str.length; i++) n = (n * 31 + str.charCodeAt(i)) % 360;
  return n;
}

function badge(status, labels) {
  return h('span', { class: 'badge s-' + cls(status) }, h('i', { class: 'dot', 'aria-hidden': 'true' }), (labels && labels[status]) || String(status || 'unknown'));
}

function parseDate(iso) {
  const d = new Date(iso);
  return isNaN(d.getTime()) ? null : d;
}

function fmtFull(iso) {
  const d = parseDate(iso);
  return d ? d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'medium' }) : '';
}

function fmtShort(iso) {
  const d = parseDate(iso);
  return d ? d.toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
}

function fmtClock(iso) {
  const d = parseDate(iso);
  return d ? d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : '';
}

function fmtRel(iso) {
  const d = parseDate(iso);
  if (!d) return '';
  const sec = (Date.now() - d.getTime()) / 1000;
  const abs = Math.abs(sec);
  let rtf;
  try { rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' }); } catch (e) { rtf = null; }
  if (abs < 45) return 'just now';
  if (!rtf || abs >= 7 * 86400) return fmtShort(iso);
  if (abs < 3600) return rtf.format(-Math.round(sec / 60), 'minute');
  if (abs < 86400) return rtf.format(-Math.round(sec / 3600), 'hour');
  return rtf.format(-Math.round(sec / 86400), 'day');
}

function timeEl(iso, mode) {
  if (!iso) return h('span', { class: 'muted' }, '-');
  return h('time', { datetime: iso, title: fmtFull(iso) }, mode === 'abs' ? fmtShort(iso) : mode === 'clock' ? fmtClock(iso) : fmtRel(iso));
}

function fmtDur(totalSec) {
  const s = Math.max(0, Math.round(totalSec));
  if (s < 60) return s + 's';
  const m = Math.floor(s / 60);
  if (m < 60) return m + 'm ' + String(s % 60).padStart(2, '0') + 's';
  return Math.floor(m / 60) + 'h ' + String(m % 60).padStart(2, '0') + 'm';
}

function stageDuration(stage) {
  const start = parseDate(stage.started_at);
  if (!start) return null;
  const end = parseDate(stage.finished_at);
  if (end) return fmtDur((end - start) / 1000);
  if (stage.status === 'running') return fmtDur((Date.now() - start.getTime()) / 1000);
  return null;
}

function safeHref(u) {
  const s = safeUrl(u);
  return s ? s : null;
}

function rememberName(name) {
  try { localStorage.setItem('launchos.decidedBy', name); } catch (e) { /* storage unavailable */ }
}
function recallName() {
  try { return localStorage.getItem('launchos.decidedBy') || ''; } catch (e) { return ''; }
}

function toast(message, kind) {
  const host = $('#toasts');
  if (!host) return;
  const el = h('div', { class: 'toast toast-' + (kind || 'info') }, message);
  host.append(el);
  setTimeout(() => el.remove(), kind === 'error' ? 8000 : 4500);
}

function loadingEl(text) {
  return h('div', { class: 'state state-loading' }, h('span', { class: 'spinner', 'aria-hidden': 'true' }), text || 'Loading...');
}

function errorEl(message, onRetry, title) {
  return h(
    'div', { class: 'state state-error', role: 'alert' },
    h('strong', null, title || 'Something went wrong'),
    h('p', null, message),
    onRetry && h('button', { type: 'button', class: 'btn btn-sm', onclick: onRetry }, 'Try again')
  );
}

function emptyEl(title, text) {
  return h('div', { class: 'state state-empty' }, h('strong', null, title), text && h('p', null, text));
}

/* ====================================================================== API */

let mockLaunch = null;

async function fetchJson(url, opts) {
  let res;
  try {
    res = await fetch(url, opts);
  } catch (e) {
    throw new Error('Network error: could not reach ' + url);
  }
  const text = await res.text();
  let data = null;
  if (text) {
    try { data = JSON.parse(text); } catch (e) { data = null; }
  }
  if (!res.ok) {
    const d = data && data.detail;
    let msg;
    if (typeof d === 'string') msg = d;
    else if (Array.isArray(d)) msg = d.map((x) => (x && x.msg) || JSON.stringify(x)).join('; ');
    else if (d) msg = JSON.stringify(d);
    else msg = res.status + ' ' + (res.statusText || 'Request failed');
    throw new Error(msg);
  }
  return data;
}

async function mockLaunchData() {
  if (!mockLaunch) mockLaunch = await fetchJson('mock/launch.json', { cache: 'no-store' });
  return mockLaunch;
}

async function mockApi(method, path, body) {
  await sleep(120);
  if (method !== 'GET') {
    console.log('[mock]', method, path, body);
    const l = await mockLaunchData();
    if (method === 'POST' && path === '/api/launches') return { id: l.id };
    const m = path.match(/\/approvals\/([^/]+)$/);
    if (m && body) {
      const a = (l.approvals || []).find((x) => x.id === decodeURIComponent(m[1]));
      if (a) {
        // Apply the decision to the in-memory copy so the UI can be demoed end to end.
        a.status = body.decision === 'approve' ? 'approved' : 'rejected';
        a.decided_by = body.decided_by;
        a.note = body.note;
        a.decided_at = new Date().toISOString();
        l.status = body.decision === 'approve' ? 'launched' : 'rejected';
        l.updated_at = a.decided_at;
        (l.stages || []).forEach((s) => { if (s.status === 'waiting_approval') s.status = 'done'; });
      }
    }
    return clone(l);
  }
  if (path === '/api/health') return fetchJson('mock/health.json', { cache: 'no-store' });
  if (path === '/api/launches') return fetchJson('mock/launches.json', { cache: 'no-store' });
  if (/^\/api\/launches\/[^/]+\/timeline$/.test(path)) return fetchJson('mock/timeline.json', { cache: 'no-store' });
  if (/^\/api\/launches\/[^/]+$/.test(path)) return clone(await mockLaunchData());
  throw new Error('No mock for ' + method + ' ' + path);
}

async function api(method, path, body) {
  if (MOCK) return mockApi(method, path, body);
  if (method === 'GET') return fetchJson(path, { cache: 'no-store' });
  return fetchJson(path, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body == null ? {} : body),
  });
}

/* ==================================================================== state */

const state = {
  health: null,
  healthError: null,
  launches: null,
  launchesError: null,
  route: { name: 'new' },
  onHealth: null,
};
let currentView = null;

/* ================================================================== sidebar */

async function loadLaunches() {
  if (!state.launches) {
    $('#launch-list-state').replaceChildren(loadingEl('Loading launches...'));
  }
  try {
    const data = await api('GET', '/api/launches');
    state.launches = (Array.isArray(data) ? data : [])
      .slice()
      .sort((a, b) => (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0));
    state.launchesError = null;
  } catch (e) {
    state.launchesError = e.message;
  }
  renderLaunchList();
}

function renderLaunchList() {
  const stateEl = $('#launch-list-state');
  const ul = $('#launch-list');
  if (!state.launches) {
    if (state.launchesError) {
      stateEl.replaceChildren(errorEl(state.launchesError, loadLaunches, 'Could not load launches'));
    }
    ul.replaceChildren();
    return;
  }
  if (state.launchesError) {
    stateEl.replaceChildren(h('p', { class: 'small warn-text', role: 'alert' }, 'Refresh failed: ' + state.launchesError));
  } else if (!state.launches.length) {
    stateEl.replaceChildren(emptyEl('No launches yet', 'Submit your first idea to see the agents work.'));
  } else {
    stateEl.replaceChildren();
  }
  const activeId = state.route.name === 'launch' ? state.route.id : null;
  ul.replaceChildren(
    ...state.launches.map((l) =>
      h(
        'li', null,
        h(
          'a',
          { class: 'launch-item', href: '#/launch/' + enc(l.id), 'aria-current': l.id === activeId ? 'page' : null },
          h('span', { class: 'launch-item-name' }, l.name || l.id),
          h('span', { class: 'launch-item-meta' }, badge(l.status, LAUNCH_LABELS), h('span', { class: 'muted small' }, fmtRel(l.created_at)))
        )
      )
    )
  );
}

/* ==================================================================== health */

async function loadHealth() {
  try {
    state.health = await api('GET', '/api/health');
    state.healthError = null;
  } catch (e) {
    state.healthError = e.message;
  }
  renderHealth();
  if (state.onHealth) state.onHealth();
}

function healthItem(tone, label, detail, title) {
  return h(
    'span', { class: 'health-item', title: title || null },
    h('i', { class: 'hdot hdot-' + tone, 'aria-hidden': 'true' }),
    h('strong', null, label),
    detail && h('span', { class: 'muted' }, detail)
  );
}

function renderHealth() {
  const el = $('#health');
  const items = [];
  const hl = state.health;
  if (!hl) {
    if (state.healthError) items.push(healthItem('bad', 'API unreachable', state.healthError));
    else items.push(h('span', { class: 'health-item muted' }, 'Checking system health...'));
  } else {
    const sw = hl.switch || {};
    items.push(healthItem(sw.ok ? 'ok' : 'bad', sw.ok ? 'Switch connected' : 'Switch disconnected', null, sw.api_url || ''));
    const llm = hl.llm || {};
    const live = llm.mode === 'live';
    items.push(
      healthItem(
        llm.ok === false ? 'bad' : live ? 'ok' : 'warn',
        live ? 'LLM live' : 'LLM offline mode',
        (live ? '' : 'template fallback · ') + (llm.model || 'no model'),
        live ? 'Agents call the model for each stage' : 'The model is not reachable; agents use offline templates'
      )
    );
    items.push(healthItem(hl.ok ? 'ok' : 'warn', hl.ok ? 'API healthy' : 'API degraded'));
    if (state.healthError) items.push(healthItem('warn', 'Last check failed', state.healthError));
  }
  el.replaceChildren(...items);
}

/* ================================================================ New launch */

function viewNew() {
  const errBox = h('div', { class: 'state state-error', role: 'alert', hidden: true });
  const showErr = (m) => { errBox.textContent = m; errBox.hidden = false; };

  const idea = h('textarea', { id: 'f-idea', name: 'idea', rows: 5, required: true, 'aria-required': 'true', placeholder: 'What are you building, and for whom?' });
  const founder = h('input', { id: 'f-founder', name: 'founder_name', type: 'text', autocomplete: 'name', placeholder: 'e.g. Asha Rao' });
  const target = h('input', { id: 'f-target', name: 'target_customer', type: 'text', placeholder: 'Who will pay for this?' });
  const constraints = h('textarea', { id: 'f-constraints', name: 'constraints', rows: 3, placeholder: 'Timeline, budget, technical limits...' });

  const submit = h('button', { type: 'submit', class: 'btn btn-primary btn-lg' }, 'Start launch');
  const sample = h('button', {
    type: 'button', class: 'btn',
    onclick: () => {
      idea.value = SAMPLE.idea;
      founder.value = SAMPLE.founder_name;
      target.value = SAMPLE.target_customer;
      constraints.value = SAMPLE.constraints;
      idea.removeAttribute('aria-invalid');
      errBox.hidden = true;
      idea.focus();
    },
  }, 'Load sample idea');

  const field = (id, label, control, opts) =>
    h('div', { class: 'field' },
      h('label', { for: id }, label, opts && opts.required ? h('span', { class: 'req', 'aria-hidden': 'true' }, ' *') : null, opts && opts.optional ? h('span', { class: 'optional' }, ' optional') : null),
      control,
      opts && opts.hint ? h('p', { class: 'hint' }, opts.hint) : null);

  const form = h(
    'form', { class: 'card form', novalidate: true, 'aria-label': 'New launch' },
    field('f-idea', 'Your idea', idea, { required: true, hint: 'One or two sentences is enough. The Research agent will fill in the rest.' }),
    h('div', { class: 'form-row' },
      field('f-founder', 'Founder name', founder, { optional: true }),
      field('f-target', 'Target customer', target, { optional: true })),
    field('f-constraints', 'Constraints', constraints, { optional: true, hint: 'Anything the agents must respect: deadline, budget, tech or legal limits.' }),
    errBox,
    h('div', { class: 'form-actions' }, submit, sample)
  );

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errBox.hidden = true;
    const body = { idea: idea.value.trim() };
    if (!body.idea) {
      idea.setAttribute('aria-invalid', 'true');
      showErr('Please describe your idea before starting a launch.');
      idea.focus();
      return;
    }
    idea.removeAttribute('aria-invalid');
    if (founder.value.trim()) body.founder_name = founder.value.trim();
    if (target.value.trim()) body.target_customer = target.value.trim();
    if (constraints.value.trim()) body.constraints = constraints.value.trim();
    submit.disabled = true;
    submit.textContent = 'Starting...';
    try {
      const res = await api('POST', '/api/launches', body);
      if (!res || !res.id) throw new Error('The server did not return a launch id.');
      loadLaunches();
      location.hash = '#/launch/' + enc(res.id);
    } catch (err) {
      showErr(err.message);
      submit.disabled = false;
      submit.textContent = 'Start launch';
    }
  });

  const chips = STAGE_ORDER.map((k, i) =>
    h('li', { class: 'flow-step' }, icon(STAGE_META[k].icon, 15), STAGE_META[k].label, i < STAGE_ORDER.length - 1 ? h('span', { class: 'flow-arrow', 'aria-hidden': 'true' }, icon('arrow', 14)) : null)
  );

  const el = h(
    'div', { class: 'new-view' },
    h('section', { class: 'hero' },
      h('p', { class: 'eyebrow' }, 'New launch'),
      h('h1', null, 'Turn an idea into a launch decision'),
      h('p', { class: 'lead' }, 'Five specialist agents research, specify, build, market and review your idea. They work in Switch rooms you can watch, and nothing goes public until a human approves it.'),
      h('ol', { class: 'flow', 'aria-label': 'Agent pipeline' }, chips)),
    form
  );

  return { el, destroy() {}, start() { setTimeout(() => { try { idea.focus({ preventScroll: true }); } catch (e) { /* ignore */ } }, 0); } };
}

/* ============================================================= Launch detail */

function viewLaunch(id) {
  let alive = true;
  let timer = null;
  let ticker = null;
  let seq = 0;
  let mounted = false;
  let launch = null;
  let timeline = null;
  let tlError = null;
  let activeTab = null;
  let userPickedTab = false;
  let feedRoom = 'all';
  let tabEls = {};
  let panelEl = null;
  const expanded = new Set();
  const drafts = {};
  const sigs = {};

  const root = h('div', { class: 'launch-view' });
  const banner = h('div', { class: 'state state-warn banner', role: 'status', hidden: true });

  /* ---- persistent header skeleton (status region keeps aria-live intact) */
  const nameEl = h('h1', { class: 'launch-name' });
  const idEl = h('code', null, id);
  const statusSlot = h('div', { class: 'head-status', 'aria-live': 'polite', 'aria-atomic': 'true' });
  const ideaEl = h('p', { class: 'idea' });
  const metaEl = h('dl', { class: 'meta' });
  const head = h(
    'header', { class: 'launch-head card' },
    h('div', { class: 'head-top' },
      h('div', { class: 'head-title' }, h('p', { class: 'eyebrow' }, 'Launch ', idEl), nameEl),
      statusSlot),
    ideaEl,
    metaEl
  );

  const slots = {
    pipeline: h('section', { class: 'pipeline-section', 'aria-labelledby': 'pipeline-title' }),
    deliverables: h('section', { class: 'card panel area-deliv', 'aria-labelledby': 'deliv-title' }),
    approvals: h('section', { class: 'card panel area-appr', 'aria-labelledby': 'appr-title' }),
    feed: h('section', { class: 'card panel area-feed', 'aria-labelledby': 'feed-title' }),
    links: h('section', { class: 'card panel area-links', 'aria-labelledby': 'links-title' }),
  };
  const grid = h('div', { class: 'detail-grid' }, slots.deliverables, slots.approvals, slots.feed, slots.links);

  root.append(loadingEl('Loading launch...'));

  /* ---- data loop */
  async function tick() {
    clearTimeout(timer);
    if (!alive) return;
    const mine = ++seq;
    const base = '/api/launches/' + enc(id);
    try {
      const lp = api('GET', base);
      const tp = api('GET', base + '/timeline').then((d) => ({ d }), (e) => ({ e }));
      const l = await lp;
      const t = await tp;
      if (!alive || mine !== seq) return;
      banner.hidden = true;
      if (t.d) { timeline = Array.isArray(t.d) ? t.d : []; tlError = null; } else { tlError = t.e.message; }
      applyLaunch(l);
    } catch (e) {
      if (!alive || mine !== seq) return;
      if (!launch) {
        root.replaceChildren(
          errorEl(e.message, () => { root.replaceChildren(loadingEl('Loading launch...')); tick(); }, 'Could not load this launch'),
          h('p', null, h('a', { href: '#/new' }, 'Back to new launch'))
        );
        return;
      }
      banner.textContent = 'Connection problem: ' + e.message + '. Retrying...';
      banner.hidden = false;
    }
    if (alive && mine === seq && (!launch || !TERMINAL.has(launch.status))) timer = setTimeout(tick, POLL_MS);
  }

  function applyLaunch(l) {
    if (!l || typeof l !== 'object') return;
    const prev = launch && launch.status;
    launch = l;
    if (!mounted) {
      mounted = true;
      root.replaceChildren(banner, head, slots.pipeline, grid);
    }
    if (prev && prev !== l.status) {
      toast('Launch status: ' + (LAUNCH_LABELS[l.status] || l.status));
      loadLaunches();
    }
    document.title = (l.name || l.id) + ' - LaunchOS';
    renderAll();
  }

  function section(key, sig, fn) {
    const s = JSON.stringify(sig);
    if (sigs[key] === s) return;
    sigs[key] = s;
    fn();
  }

  function renderAll() {
    const l = launch;
    section('head', [l.name, l.idea, l.founder_name, l.target_customer, l.constraints, l.status, l.created_at, l.updated_at], renderHead);
    section('pipeline', [l.stages, l.switch], renderPipeline);
    section('deliv', [l.deliverables, (l.stages || []).map((s) => s.status)], renderDeliverables);
    section('appr', l.approvals, renderApprovals);
    section('feed', [timeline, tlError], renderFeed);
    section('links', [l.switch, state.health && state.health.switch], renderLinks);
  }

  /* ---- header */
  function renderHead() {
    const l = launch;
    nameEl.textContent = l.name || l.id;
    idEl.textContent = l.id;
    statusSlot.replaceChildren(badge(l.status, LAUNCH_LABELS));
    ideaEl.textContent = l.idea || '';
    const rows = [
      ['Founder', l.founder_name],
      ['Target customer', l.target_customer],
      ['Constraints', l.constraints],
      ['Created', l.created_at ? timeEl(l.created_at, 'abs') : null],
      ['Updated', l.updated_at ? timeEl(l.updated_at, 'rel') : null],
    ].filter((r) => r[1]);
    metaEl.replaceChildren(...rows.map(([k, v]) => h('div', { class: 'meta-item' }, h('dt', null, k), h('dd', null, v))));
  }

  /* ---- pipeline */
  function renderPipeline() {
    const stages = launch.stages || [];
    const byKey = {};
    stages.forEach((s) => { byKey[s.key] = s; });
    const keys = STAGE_ORDER.concat(stages.map((s) => s.key).filter((k) => STAGE_ORDER.indexOf(k) === -1));
    const rooms = (launch.switch && launch.switch.rooms) || [];
    const roomUrl = (name) => {
      const r = rooms.find((x) => x.name === name);
      return r ? safeHref(r.url) : null;
    };

    const items = keys.map((key, i) => {
      const s = byKey[key] || { key, status: 'pending' };
      const meta = STAGE_META[key] || { label: key, icon: 'agent' };
      const dur = stageDuration(s);
      const url = s.room_name ? roomUrl(s.room_name) : null;
      const room = s.room_name
        ? url
          ? h('a', { class: 'chip chip-room', href: url, target: '_blank', rel: 'noopener noreferrer', title: 'Open Switch room' }, '#' + s.room_name, icon('ext', 12))
          : h('span', { class: 'chip chip-room' }, '#' + s.room_name)
        : h('span', { class: 'chip chip-room chip-empty' }, 'Room not created yet');

      let retry = null;
      if (s.status === 'failed') {
        const btn = h('button', {
          type: 'button', class: 'btn btn-sm btn-danger',
          onclick: async () => {
            btn.disabled = true;
            btn.textContent = 'Retrying...';
            try {
              const updated = await api('POST', '/api/launches/' + enc(id) + '/retry', { stage: key });
              toast('Retrying ' + (s.title || meta.label));
              if (updated && updated.stages) applyLaunch(updated);
              tick();
            } catch (e) {
              toast('Retry failed: ' + e.message, 'error');
              btn.disabled = false;
              btn.textContent = 'Retry stage';
            }
          },
        }, 'Retry stage');
        retry = btn;
      }

      return h(
        'li', { class: 'stage s-' + cls(s.status), dataset: { key } },
        h('div', { class: 'stage-top' },
          h('span', { class: 'stage-icon' }, icon(meta.icon, 18)),
          h('span', { class: 'stage-num' }, 'Step ' + (i + 1))),
        h('h3', { class: 'stage-title' }, s.title || meta.label),
        h('p', { class: 'stage-agent' }, icon('agent', 14), s.agent ? prettyAgent(s.agent) : meta.label + ' agent'),
        h('div', { class: 'stage-status' }, badge(s.status, STAGE_LABELS)),
        h('div', { class: 'stage-meta' },
          icon('clock', 14),
          h('span', { class: 'dur', dataset: { start: s.status === 'running' ? s.started_at : null, running: s.status === 'running' ? '1' : null } },
            dur || (s.status === 'waiting_approval' ? 'awaiting human' : '-'))),
        room,
        s.error ? h('div', { class: 'stage-error', role: 'alert' }, h('strong', null, 'Error: '), s.error) : null,
        retry
      );
    });

    setKids(slots.pipeline, 
      h('div', { class: 'section-head' },
        h('h2', { id: 'pipeline-title' }, 'Pipeline'),
        h('span', { class: 'muted small' }, 'Five agents, one hand-off at a time')),
      h('ol', { class: 'pipeline' }, items)
    );
  }

  /* ---- deliverables */
  function emptyDeliverable(key) {
    const s = (launch.stages || []).find((x) => x.key === key);
    const meta = STAGE_META[key] || { label: key };
    let text = 'The ' + meta.label + ' agent has not started yet.';
    if (s) {
      if (s.status === 'running') text = 'The ' + meta.label + ' agent is working on this right now. It will appear here as soon as it is posted.';
      else if (s.status === 'failed') text = 'This stage failed' + (s.error ? ': ' + s.error : '.') + ' Use "Retry stage" in the pipeline.';
      else if (s.status === 'pending') text = 'Waiting for the earlier stages to hand off.';
    }
    return emptyEl('Not produced yet', text);
  }

  function backlogTable(items) {
    if (!items.length) return emptyEl('Backlog is empty', 'The Product agent has not added backlog items.');
    const p0 = items.filter((b) => String(b.priority).toUpperCase() === 'P0').length;
    const cols = [['id', 'ID'], ['title', 'Title'], ['priority', 'Priority'], ['estimate', 'Estimate'], ['acceptance', 'Acceptance criteria']];
    return h(
      'div', { class: 'backlog' },
      h('div', { class: 'section-head' },
        h('h3', { class: 'sub-title' }, 'Backlog'),
        h('span', { class: 'muted small' }, items.length + ' items' + (p0 ? ' · ' + p0 + ' at P0' : ''))),
      h('div', { class: 'table-wrap' },
        h('table', { class: 'backlog-table' },
          h('thead', null, h('tr', null, cols.map(([, label]) => h('th', { scope: 'col' }, label)))),
          h('tbody', null, items.map((b) =>
            h('tr', null,
              h('td', { 'data-label': 'ID', class: 'col-id' }, b.id),
              h('td', { 'data-label': 'Title', class: 'col-title' }, b.title),
              h('td', { 'data-label': 'Priority' }, h('span', { class: 'prio prio-' + cls(b.priority) }, b.priority || '-')),
              h('td', { 'data-label': 'Estimate', class: 'col-est' }, b.estimate || '-'),
              h('td', { 'data-label': 'Acceptance', class: 'col-acc' }, b.acceptance || '-'))))))
    );
  }

  function landingPanel(d) {
    const href = safeHref(d.url);
    const parts = [];
    if (d.summary) parts.push(mdBlock(d.summary));
    if (!href) {
      parts.push(emptyEl('No preview available', 'The Builder did not return a usable landing page URL.'));
      return h('div', null, parts);
    }
    const wrap = h('div', { class: 'frame-wrap' });
    const frame = h('iframe', {
      class: 'preview-frame', src: href, sandbox: 'allow-same-origin', title: 'Generated landing page preview',
      loading: 'lazy', referrerpolicy: 'no-referrer',
    });
    wrap.append(frame);
    const mk = (label, ic, mobile) => {
      const b = h('button', { type: 'button', class: 'seg', 'aria-pressed': mobile ? 'false' : 'true', onclick: () => {
        wrap.classList.toggle('is-mobile', mobile);
        seg.forEach((x) => x.setAttribute('aria-pressed', String(x === b)));
      } }, icon(ic, 15), label);
      return b;
    };
    const desk = mk('Desktop', 'desktop', false);
    const mob = mk('Mobile', 'phone', true);
    const seg = [desk, mob];
    parts.push(
      h('div', { class: 'preview-bar' },
        h('div', { class: 'seg-group', role: 'group', 'aria-label': 'Preview width' }, desk, mob),
        h('a', { class: 'btn btn-sm', href, target: '_blank', rel: 'noopener noreferrer' }, 'Open in new tab', icon('ext', 14))),
      wrap,
      h('p', { class: 'hint' }, 'Preview is sandboxed: scripts are disabled. ', h('code', null, href))
    );
    return h('div', null, parts);
  }

  function readinessPanel(d) {
    const raw = Number(d.score);
    const score = isFinite(raw) ? Math.max(0, Math.min(100, Math.round(raw))) : null;
    const tone = score == null ? 'none' : score >= 80 ? 'ok' : score >= 55 ? 'warn' : 'bad';
    const band = score == null ? 'No score' : score >= 85 ? 'Ready to launch' : score >= 70 ? 'Nearly ready' : score >= 50 ? 'Needs work' : 'Not ready';
    const checks = Array.isArray(d.checks) ? d.checks : [];
    const count = (st) => checks.filter((c) => c.status === st).length;
    const ring = h(
      'div', {
        class: 'ring ring-' + tone, role: 'meter', 'aria-label': 'Readiness score',
        'aria-valuemin': '0', 'aria-valuemax': '100', 'aria-valuenow': score == null ? null : String(score),
        style: '--p:' + (score == null ? 0 : score),
      },
      h('span', { class: 'ring-num' }, score == null ? '-' : String(score), h('small', null, '/100'))
    );
    const iconFor = { pass: 'check', warn: 'warn', fail: 'x' };
    const word = { pass: 'Pass', warn: 'Warning', fail: 'Fail' };
    return h(
      'div', null,
      h('div', { class: 'score-card' },
        ring,
        h('div', { class: 'score-info' },
          h('p', { class: 'eyebrow' }, 'Readiness score'),
          h('p', { class: 'score-band tone-' + tone }, band),
          h('div', { class: 'score-counts' },
            h('span', { class: 'cnt cnt-pass' }, count('pass') + ' pass'),
            h('span', { class: 'cnt cnt-warn' }, count('warn') + ' warn'),
            h('span', { class: 'cnt cnt-fail' }, count('fail') + ' fail')),
          h('div', { class: 'bar', 'aria-hidden': 'true' }, h('i', { class: 'bar-fill bar-' + tone, style: 'width:' + (score || 0) + '%' })))),
      checks.length
        ? h('ul', { class: 'checks', 'aria-label': 'Readiness checks' }, checks.map((c) =>
            h('li', { class: 'check check-' + cls(c.status) },
              h('span', { class: 'check-icon' }, icon(iconFor[c.status] || 'warn', 14), h('span', { class: 'sr-only' }, word[c.status] || String(c.status))),
              h('div', { class: 'check-body' }, h('strong', null, c.name), c.detail ? h('p', null, c.detail) : null))))
        : emptyEl('No checks yet', 'The Readiness agent has not reported individual checks.'),
      d.markdown ? h('div', { class: 'sub-block' }, mdBlock(d.markdown)) : null
    );
  }

  function panelContent(key) {
    const d = launch.deliverables && launch.deliverables[key];
    if (!d) return emptyDeliverable(key);
    if (key === 'research' || key === 'marketing') return mdBlock(d.markdown);
    if (key === 'product') return h('div', null, mdBlock(d.markdown), h('div', { class: 'sub-block' }, backlogTable(Array.isArray(d.backlog) ? d.backlog : [])));
    if (key === 'builder') return landingPanel(d);
    if (key === 'readiness') return readinessPanel(d);
    return mdBlock(d.markdown);
  }

  function fillPanel() {
    panelEl.setAttribute('aria-labelledby', 'tab-' + activeTab);
    panelEl.replaceChildren(panelContent(activeTab));
  }

  function selectTab(key, focus) {
    activeTab = key;
    userPickedTab = true;
    TABS.forEach((t) => {
      const el = tabEls[t.key];
      el.setAttribute('aria-selected', String(t.key === key));
      el.tabIndex = t.key === key ? 0 : -1;
    });
    if (focus) tabEls[key].focus();
    fillPanel();
  }

  function renderDeliverables() {
    const d = launch.deliverables || {};
    if (!activeTab || !userPickedTab) {
      const first = TABS.find((t) => d[t.key]);
      activeTab = first ? first.key : 'research';
    }
    tabEls = {};
    const onKey = (e) => {
      const idx = TABS.findIndex((t) => t.key === activeTab);
      let next = -1;
      if (e.key === 'ArrowRight') next = (idx + 1) % TABS.length;
      else if (e.key === 'ArrowLeft') next = (idx - 1 + TABS.length) % TABS.length;
      else if (e.key === 'Home') next = 0;
      else if (e.key === 'End') next = TABS.length - 1;
      if (next >= 0) { e.preventDefault(); selectTab(TABS[next].key, true); }
    };
    const tabs = h('div', { class: 'tabs', role: 'tablist', 'aria-label': 'Deliverables' },
      TABS.map((t) => {
        const el = h('button', {
          type: 'button', role: 'tab', id: 'tab-' + t.key, class: 'tab' + (d[t.key] ? ' has-content' : ''),
          'aria-selected': String(t.key === activeTab), 'aria-controls': 'tabpanel', tabindex: t.key === activeTab ? '0' : '-1',
          onclick: () => selectTab(t.key), onkeydown: onKey,
        }, t.label, d[t.key] ? h('i', { class: 'tab-dot', title: 'Ready' }) : null);
        tabEls[t.key] = el;
        return el;
      }));
    panelEl = h('div', { id: 'tabpanel', role: 'tabpanel', class: 'tabpanel', tabindex: '0' });
    setKids(slots.deliverables, h('div', { class: 'section-head' }, h('h2', { id: 'deliv-title' }, 'Deliverables')), tabs, panelEl);
    fillPanel();
  }

  /* ---- approvals */
  function approvalCard(a) {
    const head = h('div', { class: 'appr-head' }, h('h3', null, a.title || a.id), badge(a.status, APPROVAL_LABELS));
    const desc = a.description ? h('p', { class: 'appr-desc' }, a.description) : null;

    if (a.status !== 'pending') {
      return h(
        'article', { class: 'approval s-' + cls(a.status) },
        head, desc,
        h('p', { class: 'decision' },
          h('strong', null, (a.status === 'approved' ? 'Approved' : 'Rejected') + (a.decided_by ? ' by ' + a.decided_by : '')),
          a.decided_at ? [' · ', timeEl(a.decided_at, 'abs')] : null),
        a.note ? h('blockquote', { class: 'decision-note' }, a.note) : null
      );
    }

    const draft = drafts[a.id] || (drafts[a.id] = { note: '', by: recallName() });
    const by = h('input', { id: 'by-' + a.id, type: 'text', autocomplete: 'name', required: true, 'aria-required': 'true', placeholder: 'Your name', value: draft.by, oninput: (e) => { draft.by = e.target.value; } });
    const note = h('textarea', { id: 'note-' + a.id, rows: 3, required: true, 'aria-required': 'true', placeholder: 'Why are you approving or rejecting?', value: draft.note, oninput: (e) => { draft.note = e.target.value; } });
    const err = h('div', { class: 'form-error', role: 'alert', hidden: true });
    let pending = 'approve';
    const approve = h('button', { type: 'submit', class: 'btn btn-approve', onclick: () => { pending = 'approve'; } }, 'Approve');
    const reject = h('button', { type: 'submit', class: 'btn btn-reject', onclick: () => { pending = 'reject'; } }, 'Reject');

    const form = h(
      'form', { class: 'decide', novalidate: true, 'aria-label': 'Decide: ' + (a.title || a.id) },
      h('div', { class: 'field' }, h('label', { for: 'by-' + a.id }, 'Decided by', h('span', { class: 'req', 'aria-hidden': 'true' }, ' *')), by),
      h('div', { class: 'field' }, h('label', { for: 'note-' + a.id }, 'Note', h('span', { class: 'req', 'aria-hidden': 'true' }, ' *')), note),
      err,
      h('div', { class: 'decide-actions' }, approve, reject),
      h('p', { class: 'hint' }, 'A note and your name are required. Both are stored with the decision.')
    );

    form.addEventListener('submit', async (e) => {
      e.preventDefault();
      const decision = e.submitter && e.submitter.classList.contains('btn-reject') ? 'reject' : e.submitter ? 'approve' : pending;
      const who = by.value.trim();
      const why = note.value.trim();
      err.hidden = true;
      by.removeAttribute('aria-invalid');
      note.removeAttribute('aria-invalid');
      if (!who || !why) {
        const bad = !who ? by : note;
        if (!who) by.setAttribute('aria-invalid', 'true');
        if (!why) note.setAttribute('aria-invalid', 'true');
        err.textContent = 'Please add ' + (!who && !why ? 'your name and a note' : !who ? 'your name' : 'a note') + ' to record this decision.';
        err.hidden = false;
        bad.focus();
        return;
      }
      approve.disabled = true;
      reject.disabled = true;
      const active = decision === 'reject' ? reject : approve;
      const label = active.textContent;
      active.textContent = decision === 'reject' ? 'Rejecting...' : 'Approving...';
      try {
        const updated = await api('POST', '/api/launches/' + enc(id) + '/approvals/' + enc(a.id), { decision, note: why, decided_by: who });
        rememberName(who);
        delete drafts[a.id];
        toast('Decision recorded: ' + (decision === 'approve' ? 'approved' : 'rejected'), 'success');
        if (updated && updated.stages) applyLaunch(updated);
        tick();
      } catch (ex) {
        err.textContent = 'Could not record decision: ' + ex.message;
        err.hidden = false;
        approve.disabled = false;
        reject.disabled = false;
        active.textContent = label;
      }
    });

    return h('article', { class: 'approval s-pending' }, head, desc, form);
  }

  function renderApprovals() {
    const list = launch.approvals || [];
    const pending = list.filter((a) => a.status === 'pending').length;
    slots.approvals.classList.toggle('needs-action', pending > 0);
    setKids(slots.approvals, 
      h('div', { class: 'section-head' },
        h('h2', { id: 'appr-title' }, 'Approvals'),
        pending ? h('span', { class: 'badge s-waiting_approval' }, h('i', { class: 'dot', 'aria-hidden': 'true' }), pending + ' pending') : null),
      list.length
        ? list.map(approvalCard)
        : emptyEl('No approvals requested', 'The Readiness agent asks for a human decision once the earlier stages are done.')
    );
  }

  /* ---- Switch room feed */
  let measures = [];
  function feedItem(m) {
    const key = [m.ts, m.room, m.sender, m.kind].join('|');
    const hue = hueOf(String(m.sender || ''));
    const isSys = String(m.sender).toLowerCase() === 'launchos';
    const rooms = (launch.switch && launch.switch.rooms) || [];
    const r = rooms.find((x) => x.name === m.room);
    const url = r ? safeHref(r.url) : null;
    const roomChip = url
      ? h('a', { class: 'chip chip-room', href: url, target: '_blank', rel: 'noopener noreferrer', title: 'Open in Switch' }, '#' + m.room)
      : h('span', { class: 'chip chip-room' }, '#' + (m.room || 'unknown'));
    const isOpen = expanded.has(key);
    const body = h('div', { class: 'msg-body md' + (isOpen ? '' : ' clamped'), html: renderMarkdown(m.body) });
    const more = h('button', { type: 'button', class: 'more', 'aria-expanded': String(isOpen) }, isOpen ? 'Show less' : 'Show more');
    more.addEventListener('click', () => {
      const open = body.classList.toggle('clamped') === false;
      if (open) expanded.add(key); else expanded.delete(key);
      more.textContent = open ? 'Show less' : 'Show more';
      more.setAttribute('aria-expanded', String(open));
    });
    if (!isOpen) {
      more.hidden = true;
      // measured synchronously by renderFeed() once the item is attached
      measures.push(() => {
        if (body.scrollHeight > body.clientHeight + 4) more.hidden = false;
        else body.classList.remove('clamped');
      });
    }
    const kind = cls(m.kind) || 'message';
    return h(
      'li', { class: 'msg k-' + kind },
      h('span', { class: 'avatar' + (isSys ? ' avatar-sys' : ''), 'aria-hidden': 'true', style: isSys ? null : '--h:' + hue }, initials(m.sender)),
      h('div', { class: 'msg-main' },
        h('div', { class: 'msg-head' },
          h('strong', { class: 'msg-sender' }, prettyAgent(m.sender)),
          h('span', { class: 'kind kind-' + kind }, kind === 'handoff' ? icon('arrow', 12) : kind === 'deliverable' ? icon('doc', 12) : kind === 'approval' ? icon('readiness', 12) : null, KIND_LABELS[m.kind] || m.kind || 'Message'),
          roomChip,
          h('span', { class: 'msg-time' }, timeEl(m.ts, 'clock'))),
        body, more)
    );
  }

  function renderFeed() {
    const prev = $('.feed-scroll', slots.feed);
    const stick = !prev || prev.scrollHeight - prev.scrollTop - prev.clientHeight < 60;
    const prevTop = prev ? prev.scrollTop : 0;
    measures = [];

    const all = timeline || [];
    const roomNames = Array.from(new Set(all.map((m) => m.room).filter(Boolean)));
    if (feedRoom !== 'all' && roomNames.indexOf(feedRoom) === -1) feedRoom = 'all';
    const shown = feedRoom === 'all' ? all : all.filter((m) => m.room === feedRoom);

    const select = roomNames.length > 1
      ? h('select', {
          class: 'select', 'aria-label': 'Filter by room',
          onchange: (e) => { feedRoom = e.target.value; renderFeed(); const s = $('select', slots.feed); if (s) s.focus(); },
        }, h('option', { value: 'all' }, 'All rooms (' + all.length + ')'),
        roomNames.map((n) => h('option', { value: n, selected: n === feedRoom ? true : null }, '#' + n)))
      : null;

    let bodyEl;
    if (timeline == null && tlError) bodyEl = errorEl(tlError, tick, 'Could not load room activity');
    else if (timeline == null) bodyEl = loadingEl('Loading room activity...');
    else if (!shown.length) bodyEl = emptyEl('No room activity yet', 'Messages from the agents will stream in here as they work.');
    else bodyEl = h('div', { class: 'feed-scroll', tabindex: '0', role: 'region', 'aria-label': 'Room messages, oldest first' }, h('ol', { class: 'feed' }, shown.map(feedItem)));

    setKids(slots.feed, 
      h('div', { class: 'section-head' },
        h('h2', { id: 'feed-title' }, 'Room activity'),
        h('span', { class: 'via-switch', title: 'Messages are read from Switch rooms' }, icon('switch', 14), 'via Switch')),
      h('p', { class: 'muted small feed-sub' }, 'Live messages from the Switch rooms where the agents collaborate.'),
      select ? h('div', { class: 'feed-filter' }, select) : null,
      timeline && tlError ? h('p', { class: 'small warn-text', role: 'alert' }, 'Refresh failed: ' + tlError) : null,
      bodyEl
    );
    measures.forEach((fn) => fn());
    measures = [];
    const scroller = $('.feed-scroll', slots.feed);
    if (scroller) scroller.scrollTop = stick ? scroller.scrollHeight : prevTop;
  }

  /* ---- links */
  function renderLinks() {
    const rooms = (launch.switch && launch.switch.rooms) || [];
    const sw = (state.health && state.health.switch) || {};
    const tools = [
      ['Mattermost', sw.mattermost_url],
      ['Switch gateway', sw.gateway_url],
    ].map(([label, u]) => [label, u && safeHref(u)]).filter((t) => t[1]);

    setKids(slots.links, 
      h('div', { class: 'section-head' }, h('h2', { id: 'links-title' }, 'Switch rooms & tools')),
      rooms.length
        ? h('ul', { class: 'rooms' }, rooms.map((r) => {
            const href = safeHref(r.url);
            const inner = [h('span', { class: 'room-name' }, '#' + r.name), r.purpose ? h('span', { class: 'room-purpose' }, r.purpose) : null];
            return h('li', null, href
              ? h('a', { class: 'room-link', href, target: '_blank', rel: 'noopener noreferrer' }, h('span', { class: 'room-text' }, inner), icon('ext', 14))
              : h('span', { class: 'room-link' }, h('span', { class: 'room-text' }, inner)));
          }))
        : emptyEl('No rooms yet', 'Switch rooms are created when the launch starts.'),
      tools.length
        ? h('div', { class: 'tool-links' }, tools.map(([label, u]) => h('a', { class: 'btn btn-sm', href: u, target: '_blank', rel: 'noopener noreferrer' }, label, icon('ext', 14))))
        : null
    );
  }

  /* ---- live duration ticker */
  function tickDurations() {
    root.querySelectorAll('.dur[data-running="1"]').forEach((el) => {
      const start = parseDate(el.dataset.start);
      if (start) el.textContent = fmtDur((Date.now() - start.getTime()) / 1000);
    });
  }

  return {
    el: root,
    start() {
      state.onHealth = () => { if (launch) renderAll(); };
      ticker = setInterval(tickDurations, 1000);
      tick();
    },
    destroy() {
      alive = false;
      clearTimeout(timer);
      clearInterval(ticker);
      state.onHealth = null;
      document.title = 'LaunchOS - from idea to launch with AI agents';
    },
  };
}

/* ================================================================== routing */

function parseRoute() {
  const hash = location.hash.replace(/^#/, '');
  const m = hash.match(/^\/launch\/([^/?]+)/);
  if (m) {
    try { return { name: 'launch', id: decodeURIComponent(m[1]) }; } catch (e) { return { name: 'new' }; }
  }
  return { name: 'new' };
}

function setNav(open) {
  document.body.classList.toggle('nav-open', open);
  $('#nav-toggle').setAttribute('aria-expanded', String(open));
  $('#backdrop').hidden = !open;
}

let firstRoute = true;
function route() {
  if (currentView) { currentView.destroy(); currentView = null; }
  state.route = parseRoute();
  setNav(false);
  currentView = state.route.name === 'launch' ? viewLaunch(state.route.id) : viewNew();
  $('#view').replaceChildren(currentView.el);
  renderLaunchList();
  window.scrollTo(0, 0);
  if (!firstRoute) { try { $('#main').focus({ preventScroll: true }); } catch (e) { /* ignore */ } }
  firstRoute = false;
  if (currentView.start) currentView.start();
}

/* ===================================================================== boot */

function boot() {
  if (MOCK) $('#mock-pill').hidden = false;
  $('#nav-toggle').addEventListener('click', () => setNav(!document.body.classList.contains('nav-open')));
  $('#backdrop').addEventListener('click', () => setNav(false));
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') setNav(false); });
  $('#refresh-launches').addEventListener('click', loadLaunches);
  window.addEventListener('hashchange', route);

  renderHealth();
  loadHealth();
  loadLaunches();
  route();
  setInterval(loadHealth, SLOW_POLL_MS);
  setInterval(loadLaunches, SLOW_POLL_MS);
}

boot();
