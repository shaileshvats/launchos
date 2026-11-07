"""The five specialist agents: what each one produces from the context it reads in Switch.

Every specialist receives its inputs as text that was read back from the launch's Switch HQ room
(the founder brief and the deliverables earlier agents posted there), never from LaunchOS's own
database. `offline` mode produces clearly-labelled template output so the pipeline can be shown
and tested without a model.
"""
from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .llm import LLM, LLMError


@dataclass
class Specialist:
    key: str
    agent: str
    display: str
    title: str
    room_suffix: str
    purpose: str


SPECIALISTS: List[Specialist] = [
    Specialist("research", "research-analyst", "Research Analyst", "Market research", "research",
               "Market sizing, customer segments and competitor analysis"),
    Specialist("product", "product-strategist", "Product Strategist", "Product spec & backlog", "product",
               "Product specification and a prioritised development backlog"),
    Specialist("builder", "prototype-builder", "Prototype Builder", "Landing page prototype", "build",
               "A working landing page for the product"),
    Specialist("marketing", "growth-marketer", "Growth Marketer", "Marketing & launch content", "growth",
               "Positioning, channels, launch plan and launch copy"),
    Specialist("readiness", "launch-auditor", "Launch Auditor", "Launch readiness", "readiness",
               "Launch-readiness assessment and the human approval request"),
]
BY_KEY = {s.key: s for s in SPECIALISTS}
CONDUCTOR = ("launchos-conductor", "LaunchOS Conductor",
             "Orchestrates LaunchOS: creates launch rooms, hands work to specialists and tracks approvals")


@dataclass
class StageResult:
    markdown: str
    data: Dict[str, Any] = field(default_factory=dict)
    mode: str = "live"


SYSTEM_BASE = ("You are {display}, a specialist on the LaunchOS launch team. You collaborate with other AI agents "
               "in shared Switch rooms. Be concrete and specific to the founder's idea; no filler. "
               "You have no internet access and no data sources. Never present a statistic, percentage or market "
               "figure as a fact: prefix every number with 'Assumption:' or 'Estimate:', and never invent survey "
               "results, studies or customer quotes.")
AI_NOTE = ("> AI-generated draft by a local language model. Figures are unverified estimates, not sourced data; "
           "validate before acting.\n\n")


def run_stage(key: str, llm: Optional[LLM], brief: str, upstream: Dict[str, str]) -> StageResult:
    """Run one specialist. `llm=None` means offline template mode."""
    fn = {"research": _research, "product": _product, "builder": _builder,
          "marketing": _marketing, "readiness": _readiness}[key]
    return fn(llm, brief, upstream)


def _ctx(brief: str, upstream: Dict[str, str], keys: List[str], limit: int = 3500) -> str:
    parts = [f"FOUNDER BRIEF (from the Switch HQ room):\n{brief.strip()}"]
    for k in keys:
        if upstream.get(k):
            parts.append(f"{BY_KEY[k].title.upper()} (posted in Switch by {BY_KEY[k].agent}):\n{upstream[k][:limit]}")
    return "\n\n".join(parts)


# ── research ──────────────────────────────────────────────────────────────────
def _research(llm, brief, upstream) -> StageResult:
    if llm is None:
        return StageResult(_offline_doc("Market research", brief, [
            "## Target segments\n- Primary segment taken from the brief's target customer.\n- Adjacent segment to validate later.",
            "## Competitors\n| Competitor | Type | Strength | Gap we exploit |\n|---|---|---|---|\n| Incumbent A | Direct | Brand | Slow, generic |\n| DIY / status quo | Indirect | Free | Time-consuming |",
            "## Market size (assumption)\nTop-down estimate to be validated with 10 customer interviews.",
            "## Key risks\n- Willingness to pay unproven\n- Acquisition cost unknown"]), mode="offline")
    sys = SYSTEM_BASE.format(display="the Research Analyst")
    user = (_ctx(brief, upstream, []) +
            "\n\nWrite a market research brief in Markdown with exactly these sections: "
            "## Summary (3 bullets), ## Target customer segments (2-3, each with pains and buying trigger), "
            "## Competitor analysis (a Markdown table with 4-5 named or realistic competitor types: Competitor | Type | Pricing | Strength | Weakness), "
            "## Market size (TAM/SAM/SOM as clearly-labelled assumptions with the arithmetic), "
            "## Opportunities, ## Risks and open questions. Max 450 words.")
    return StageResult(AI_NOTE + llm.chat(sys, user, max_tokens=1100))


# ── product ───────────────────────────────────────────────────────────────────
def _product(llm, brief, upstream) -> StageResult:
    if llm is None:
        backlog = [
            {"id": "LOS-1", "title": "Landing page with waitlist signup", "priority": "P0", "estimate": "1d",
             "acceptance": "Visitor can submit email; stored and confirmed"},
            {"id": "LOS-2", "title": "Core ordering flow", "priority": "P0", "estimate": "4d",
             "acceptance": "Customer completes an order end to end"},
            {"id": "LOS-3", "title": "Payments integration", "priority": "P1", "estimate": "2d",
             "acceptance": "Test-mode payment succeeds and is recorded"},
            {"id": "LOS-4", "title": "Admin dashboard", "priority": "P2", "estimate": "3d",
             "acceptance": "Operator sees orders and status"},
        ]
        md = _offline_doc("Product specification", brief, [
            "## Problem\nRestated from the founder brief.", "## MVP scope\n- Waitlist\n- Ordering\n- Payments",
            "## Out of scope\n- Native mobile apps", "## Success metrics\n- 100 waitlist signups in 2 weeks"])
        return StageResult(md + "\n\n" + backlog_md(backlog), {"backlog": backlog}, mode="offline")
    sys = SYSTEM_BASE.format(display="the Product Strategist")
    user = (_ctx(brief, upstream, ["research"]) +
            "\n\nReturn ONLY a JSON object with keys: "
            '"problem" (string), "personas" (array of 2 strings), "value_proposition" (string), '
            '"mvp_features" (array of 4-6 strings), "out_of_scope" (array of 2-3 strings), '
            '"success_metrics" (array of 3 strings with numeric targets), '
            '"backlog" (array of 6-8 objects with "title", "priority" one of P0/P1/P2, "estimate" like "2d", '
            '"acceptance" one-sentence acceptance criterion). Order the backlog by priority.')
    spec = llm.chat_json(sys, user, max_tokens=1400)
    if not isinstance(spec, dict):
        raise LLMError("product spec was not a JSON object")
    backlog = []
    for i, item in enumerate(spec.get("backlog") or [], 1):
        if isinstance(item, dict) and item.get("title"):
            pr = str(item.get("priority", "P1")).upper()
            backlog.append({"id": f"LOS-{i}", "title": str(item["title"])[:120],
                            "priority": pr if pr in ("P0", "P1", "P2") else "P1",
                            "estimate": str(item.get("estimate", "?"))[:12],
                            "acceptance": str(item.get("acceptance", ""))[:240]})
    if not backlog:
        raise LLMError("product spec had no backlog")
    order = {"P0": 0, "P1": 1, "P2": 2}
    backlog.sort(key=lambda b: order[b["priority"]])
    for i, b in enumerate(backlog, 1):
        b["id"] = f"LOS-{i}"

    def bullets(xs):
        return "\n".join(f"- {x}" for x in (xs or []) if isinstance(x, str))
    md = (AI_NOTE + f"## Problem\n{spec.get('problem', '')}\n\n## Personas\n{bullets(spec.get('personas'))}\n\n"
          f"## Value proposition\n{spec.get('value_proposition', '')}\n\n## MVP features\n{bullets(spec.get('mvp_features'))}\n\n"
          f"## Out of scope\n{bullets(spec.get('out_of_scope'))}\n\n## Success metrics\n{bullets(spec.get('success_metrics'))}\n\n"
          + backlog_md(backlog))
    return StageResult(md, {"backlog": backlog, "spec": spec})


def backlog_md(backlog: List[Dict[str, str]]) -> str:
    rows = "\n".join(f"| {b['id']} | {b['title']} | {b['priority']} | {b['estimate']} | {b['acceptance']} |" for b in backlog)
    return "## Prioritised backlog\n| ID | Item | Priority | Estimate | Acceptance |\n|---|---|---|---|---|\n" + rows


# ── builder (landing page) ────────────────────────────────────────────────────
def _builder(llm, brief, upstream) -> StageResult:
    if llm is None:
        content = {"product_name": _name_from_brief(brief), "headline": "Launching soon",
                   "subheadline": "Template landing page generated in offline mode.",
                   "features": [{"title": "Fast", "text": "Gets the job done quickly."},
                                {"title": "Simple", "text": "No setup required."},
                                {"title": "Local", "text": "Built for our first market."}],
                   "pricing": [{"name": "Starter", "price": "TBD", "includes": ["Core features"]}],
                   "faq": [{"q": "When do you launch?", "a": "Join the waitlist to hear first."}],
                   "cta": "Join the waitlist"}
        mode = "offline"
    else:
        sys = SYSTEM_BASE.format(display="the Prototype Builder") + " You write conversion-focused landing page copy."
        user = (_ctx(brief, upstream, ["research", "product"], limit=2500) +
                "\n\nReturn ONLY a JSON object for the landing page with keys: "
                '"product_name", "headline" (max 9 words), "subheadline" (max 25 words), '
                '"features" (array of 3 objects {"title","text"}), '
                '"how_it_works" (array of 3 short steps), '
                '"pricing" (array of 2-3 objects {"name","price","includes": array of 3 strings}; prices are proposals), '
                '"faq" (array of 3 objects {"q","a"}), "cta" (button text, max 4 words).')
        content = llm.chat_json(sys, user, max_tokens=1100)
        if not isinstance(content, dict) or not content.get("headline"):
            raise LLMError("landing page JSON missing headline")
        mode = "live"
    page = render_landing(content)
    md = (f"Built a landing page for **{_esc_md(content.get('product_name', ''))}**.\n\n"
          f"- Headline: {_esc_md(content.get('headline', ''))}\n- Subheadline: {_esc_md(content.get('subheadline', ''))}\n"
          f"- Sections: hero, features ({len(content.get('features') or [])}), how it works, pricing "
          f"({len(content.get('pricing') or [])} tiers), FAQ, waitlist form\n- CTA: {_esc_md(content.get('cta', ''))}")
    return StageResult(md, {"landing": content, "html": page}, mode=mode)


def render_landing(c: Dict[str, Any]) -> str:
    e = lambda v: html.escape(str(v or ""))  # noqa: E731
    feats = "".join(f"<div class='card'><h3>{e(f.get('title'))}</h3><p>{e(f.get('text'))}</p></div>"
                    for f in (c.get("features") or []) if isinstance(f, dict))
    steps = "".join(f"<li>{e(s)}</li>" for s in (c.get("how_it_works") or []) if isinstance(s, str))
    tiers = "".join(
        f"<div class='card tier'><h3>{e(t.get('name'))}</h3><div class='price'>{e(t.get('price'))}</div><ul>"
        + "".join(f"<li>{e(i)}</li>" for i in (t.get("includes") or []) if isinstance(i, str))
        + "</ul></div>" for t in (c.get("pricing") or []) if isinstance(t, dict))
    faq = "".join(f"<details><summary>{e(q.get('q'))}</summary><p>{e(q.get('a'))}</p></details>"
                  for q in (c.get("faq") or []) if isinstance(q, dict))
    name = e(c.get("product_name") or "Our product")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{name}</title><style>
:root{{--a:#5B5BD6;--ink:#1c1d29;--mut:#5d6075;--bg:#f7f7fb}}*{{box-sizing:border-box}}body{{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;color:var(--ink);background:#fff;line-height:1.55}}
header{{padding:20px 6vw;display:flex;justify-content:space-between;align-items:center}}.logo{{font-weight:800;font-size:20px}}
.hero{{padding:64px 6vw 72px;background:linear-gradient(135deg,#eef0ff,#fdf4ff);text-align:center}}.hero h1{{font-size:clamp(30px,5vw,52px);margin:0 0 16px;letter-spacing:-.02em}}
.hero p{{font-size:19px;color:var(--mut);max-width:640px;margin:0 auto 28px}}form{{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}}
input{{padding:14px 16px;border:1px solid #cfd1e3;border-radius:10px;min-width:260px;font-size:16px}}button{{padding:14px 22px;border:0;border-radius:10px;background:var(--a);color:#fff;font-weight:700;font-size:16px;cursor:pointer}}
section{{padding:56px 6vw}}h2{{text-align:center;font-size:30px;margin:0 0 28px}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px;max-width:1040px;margin:0 auto}}
.card{{background:var(--bg);border-radius:14px;padding:22px}}.card h3{{margin:0 0 8px}}.price{{font-size:28px;font-weight:800;color:var(--a);margin-bottom:8px}}
ol{{max-width:640px;margin:0 auto;font-size:18px}}details{{max-width:720px;margin:0 auto 10px;background:var(--bg);border-radius:10px;padding:14px 18px}}summary{{font-weight:700;cursor:pointer}}
footer{{padding:28px 6vw;color:var(--mut);font-size:14px;text-align:center}}</style></head><body>
<header><div class="logo">{name}</div><a href="#join">{e(c.get('cta') or 'Join')}</a></header>
<div class="hero" id="join"><h1>{e(c.get('headline'))}</h1><p>{e(c.get('subheadline'))}</p>
<form onsubmit="return false"><input type="email" placeholder="you@company.com" aria-label="Email address" required><button type="submit">{e(c.get('cta') or 'Join the waitlist')}</button></form></div>
<section><h2>Why {name}</h2><div class="grid">{feats}</div></section>
{f'<section><h2>How it works</h2><ol>{steps}</ol></section>' if steps else ''}
{f'<section><h2>Pricing</h2><div class="grid">{tiers}</div></section>' if tiers else ''}
{f'<section><h2>FAQ</h2>{faq}</section>' if faq else ''}
<footer>Prototype generated by LaunchOS. Prices and claims are proposals pending founder approval.</footer></body></html>"""


# ── marketing ─────────────────────────────────────────────────────────────────
def _marketing(llm, brief, upstream) -> StageResult:
    if llm is None:
        return StageResult(_offline_doc("Marketing strategy", brief, [
            "## Positioning\nFor the target customer in the brief.", "## Channels\n1. Founder-led outreach\n2. Community posts",
            "## Launch plan\n- Week -2: waitlist\n- Week 0: launch post", "## Launch content\n**Launch post:** We're live."]),
            mode="offline")
    sys = SYSTEM_BASE.format(display="the Growth Marketer")
    user = (_ctx(brief, upstream, ["research", "product", "builder"], limit=2000) +
            "\n\nWrite the marketing strategy and launch content in Markdown with sections: "
            "## Positioning statement, ## Channel plan (table: Channel | Why | First action | Budget share), "
            "## 4-week launch calendar (table: Week | Goal | Activities), "
            "## Launch content (a LinkedIn post under 120 words, a tweet under 260 characters, an email subject line and a 3-sentence launch email), "
            "## Metrics to watch. Max 500 words.")
    return StageResult(AI_NOTE + llm.chat(sys, user, max_tokens=1200))


# ── readiness ─────────────────────────────────────────────────────────────────
def readiness_checks(upstream: Dict[str, str], backlog: List[Dict[str, str]], landing: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Deterministic checks over what the team actually delivered (not model opinion)."""
    checks = []

    def add(name, ok, warn_detail, ok_detail, fail=False):
        checks.append({"name": name, "status": "pass" if ok else ("fail" if fail else "warn"),
                       "detail": ok_detail if ok else warn_detail})
    r = upstream.get("research", "")
    add("Market research delivered", len(r) > 300, "Research is missing or very short", "Research brief posted in Switch", fail=not r)
    add("Competitors analysed", "|" in r and r.lower().count("competitor") >= 1, "No competitor table found",
        "Competitor table present", fail=not r)
    p0 = [b for b in backlog if b.get("priority") == "P0"]
    add("Backlog prioritised", len(backlog) >= 4 and len(p0) >= 1, f"{len(backlog)} items, {len(p0)} P0",
        f"{len(backlog)} items, {len(p0)} P0", fail=not backlog)
    add("MVP scope realistic", 0 < len(p0) <= 4, f"{len(p0)} P0 items: scope needs trimming" if p0 else "No P0 items",
        f"{len(p0)} P0 items", fail=not p0)
    add("Landing page live", bool(landing and landing.get("headline")), "No landing page", "Prototype page renders", fail=not landing)
    add("Pricing proposed", bool(landing and landing.get("pricing")), "No pricing on the landing page", "Pricing tiers proposed",
        fail=not landing)
    m = upstream.get("marketing", "")
    add("Launch content ready", len(m) > 300 and ("launch" in m.lower()), "Marketing plan missing or thin",
        "Channel plan and launch copy posted", fail=not m)
    checks.append({"name": "Legal & compliance review", "status": "warn",
                   "detail": "Not assessed by AI: terms, privacy policy and local regulations need a human review"})
    return checks


def readiness_score(checks: List[Dict[str, str]]) -> int:
    pts = {"pass": 1.0, "warn": 0.5, "fail": 0.0}
    return round(100 * sum(pts[c["status"]] for c in checks) / max(1, len(checks)))


def _readiness(llm, brief, upstream) -> StageResult:
    # backlog/landing data arrive through `upstream["_data"]` populated by the workflow from stage results
    data = upstream.get("_data") or {}
    checks = readiness_checks(upstream, data.get("backlog") or [], data.get("landing"))
    score = readiness_score(checks)
    table = "\n".join(f"| {c['name']} | {c['status'].upper()} | {c['detail']} |" for c in checks)
    base = (f"## Readiness score: {score}/100\n(Computed from {len(checks)} deterministic checks over the team's deliverables.)\n\n"
            f"| Check | Result | Detail |\n|---|---|---|\n{table}\n")
    if llm is None:
        return StageResult(base + "\n## Recommendation\nOffline mode: review the deliverables before approving.",
                           {"score": score, "checks": checks}, mode="offline")
    sys = SYSTEM_BASE.format(display="the Launch Auditor") + " You are cautious; a human makes the final call."
    user = (_ctx(brief, upstream, ["research", "product", "marketing"], limit=1500) + "\n\nAUTOMATED CHECKS:\n" + base +
            "\n\nWrite ## Top risks (3 bullets), ## Must-fix before launch (2-4 bullets), and ## Recommendation "
            "(one paragraph ending with 'Recommend: GO', 'Recommend: GO WITH CONDITIONS' or 'Recommend: NO-GO'). Max 220 words.")
    return StageResult(base + "\n" + llm.chat(sys, user, max_tokens=600), {"score": score, "checks": checks})


# ── helpers ───────────────────────────────────────────────────────────────────
def _offline_doc(title: str, brief: str, sections: List[str]) -> str:
    return (f"> Offline template output (no language model was used). It shows the pipeline, not real analysis.\n\n"
            f"# {title}\n\n" + "\n\n".join(sections))


def _name_from_brief(brief: str) -> str:
    m = re.search(r"Launch name:\s*(.+)", brief)
    return m.group(1).strip() if m else "New Venture"


def _esc_md(s: Any) -> str:
    return str(s).replace("|", "/").replace("\n", " ")
