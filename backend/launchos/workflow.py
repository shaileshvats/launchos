"""LaunchOS orchestration over Switch.

Six registered Switch agents run in this process, each with its own API key and its own event stream:
the conductor and five specialists. They coordinate only through Switch rooms:

  conductor ──[handoff]──▶ team room ──▶ specialist (event stream)
  specialist ── read_context(HQ room) ◀── brief + earlier deliverables
  specialist ──[deliverable]──▶ HQ room   (shared context for the next agent)
  specialist ──[done]──▶ team room ──▶ conductor (event stream) ──▶ next handoff
  launch-auditor ──[approval]──▶ HQ room ◀── human decision (LaunchOS UI or a reply in Mattermost)
"""
from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional

from .config import Settings
from .llm import LLM, LLMError
from .specialists import BY_KEY, CONDUCTOR, SPECIALISTS, StageResult, run_stage
from .store import Store, now_iso
from .switch_client import SwitchAgent, SwitchError, health, messages_from_context, register_agent

log = logging.getLogger("launchos.workflow")
MARK = re.compile(r"\[(brief|handoff|deliverable|done|failed|approval|decision):([a-z0-9_]+)(?::([a-z0-9_]+))?\]")
STAGE_KEYS = [s.key for s in SPECIALISTS]
MAX_POST = 12000
ACK_TIMEOUT = 30  # seconds before an unacknowledged handoff is re-sent
MAX_HANDOFFS = 3


def marker(kind: str, lid: str, sub: str = "") -> str:
    return f"[{kind}:{lid}:{sub}]" if sub else f"[{kind}:{lid}]"


def strip_markers(body: str) -> str:
    return MARK.sub("", body).strip()


class LaunchOS:
    def __init__(self, settings: Settings, store: Store, llm: Optional[LLM] = None):
        self.s = settings
        self.store = store
        self.llm = llm or LLM(settings)
        self.agents: Dict[str, SwitchAgent] = {}
        self._stop = threading.Event()
        self._seen: Dict[str, set] = {}
        self._seen_lock = threading.Lock()
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="stage")
        self._timeline_cache: Dict[str, Any] = {}
        self.started = False
        self.start_error: Optional[str] = None

    # ── startup ───────────────────────────────────────────────────────────────
    def start(self) -> None:
        """Register (or reuse) the six agents and open their event streams."""
        if not health(self.s.switch_api_url):
            raise SwitchError(f"Switch API not reachable at {self.s.switch_api_url}")
        saved = self.store.agents()
        roster = [(self.n(CONDUCTOR[0]), CONDUCTOR[1], CONDUCTOR[2])] + [(self.n(sp.agent), sp.display, sp.purpose) for sp in SPECIALISTS]
        for base, display, desc in roster:
            name = base if base.startswith(self.s.agent_prefix) else self.n(base)
            cred = saved.get(name)
            if cred:
                agent = SwitchAgent(self.s.switch_api_url, cred["agent_id"], cred["api_key"], name)
                try:
                    agent.op("get_my_context")
                except SwitchError:
                    cred = None
            if not cred:
                if not self.s.switch_registration_token:
                    raise SwitchError("SWITCH_REGISTRATION_TOKEN is not set")
                r = register_agent(self.s.switch_api_url, self.s.switch_registration_token, name, desc, display)
                self.store.save_agent(name, r["id"], r["api_key"])
                agent = SwitchAgent(self.s.switch_api_url, r["id"], r["api_key"], name)
            self.agents[name] = agent
        for name, agent in self.agents.items():
            threading.Thread(target=agent.stream, args=(self._handler(name), self._stop),
                             name=f"sse-{name}", daemon=True).start()
        deadline = time.time() + 60
        for name, agent in self.agents.items():
            if not agent.attached.wait(max(0.1, deadline - time.time())):
                raise SwitchError(f"event stream for {name} did not attach within 60 s")
        threading.Thread(target=self._watchdog, name="watchdog", daemon=True).start()
        self._recover_interrupted()
        self.started = True

    def stop(self) -> None:
        self._stop.set()
        self._pool.shutdown(wait=False)

    def n(self, base: str) -> str:
        """Agent name with the deployment prefix (lets a test instance run beside the live one)."""
        return base if not self.s.agent_prefix or base.startswith(self.s.agent_prefix) else self.s.agent_prefix + base

    @property
    def conductor(self) -> SwitchAgent:
        return self.agents[self.n(CONDUCTOR[0])]

    def llm_status(self) -> Dict[str, Any]:
        if self.s.llm_mode == "offline":
            return {"ok": True, "mode": "offline", "model": None}
        ok = self.llm.available()
        return {"ok": ok, "mode": "live" if ok else "offline", "model": self.s.llm_model if ok else None}

    # ── launches ──────────────────────────────────────────────────────────────
    def create_launch(self, idea: str, founder_name: str = "", target_customer: str = "", constraints: str = "",
                      name: str = "") -> Dict[str, Any]:
        lid = "lch_" + secrets.token_hex(3)
        doc = {
            "id": lid, "name": (name.strip() or self._suggest_name(idea))[:60], "idea": idea.strip(),
            "founder_name": founder_name.strip(), "target_customer": target_customer.strip(),
            "constraints": constraints.strip(), "status": "queued", "created_at": now_iso(), "updated_at": now_iso(),
            "stages": [{"key": sp.key, "title": sp.title, "agent": self.n(sp.agent), "status": "pending", "started_at": None,
                        "finished_at": None, "room_name": None, "room_id": None, "error": None, "mode": None}
                       for sp in SPECIALISTS],
            "deliverables": {k: None for k in STAGE_KEYS},
            "approvals": [], "rooms": {}, "landing_html": None,
        }
        self.store.create(doc)
        self._pool.submit(self._safe, self._open_rooms_and_begin, lid)
        return doc

    def _suggest_name(self, idea: str) -> str:
        """A short working brand name from the model, or a name derived from the idea's words."""
        if self.s.llm_mode != "offline":
            try:
                text = self.llm.chat("You name startups. Reply with ONE invented brand name of 1-2 words, nothing else.",
                                     f"Idea: {idea[:500]}", max_tokens=12, temperature=0.7)
                cand = re.sub(r"[^A-Za-z0-9 \-]", "", text.splitlines()[0] if text else "").strip()
                if 2 <= len(cand) <= 30 and len(cand.split()) <= 3:
                    return cand
            except LLMError:
                pass
        return _derive_name(idea)

    def _safe(self, fn, *args):
        try:
            fn(*args)
        except Exception as exc:  # surface any orchestration failure on the launch itself
            log.exception("orchestration failed")
            lid = args[0]
            self.store.update(lid, lambda d: d.update(status="failed", error=f"{type(exc).__name__}: {exc}"))

    def _open_rooms_and_begin(self, lid: str) -> None:
        doc = self.store.get(lid)
        slug = (self.s.agent_prefix + lid).replace("_", "-")
        c = self.conductor
        human = [self.s.mattermost_user] if self.s.mattermost_user else []
        all_agents = list(self.agents.keys())
        hq = c.op("create_room", {
            "name": f"{slug}-hq", "description": f"LaunchOS HQ for {doc['name']}", "agent_names": all_agents,
            "user_names": human,
            "instructions": "Launch HQ. The conductor posts the founder brief here; every specialist posts its "
                            "deliverable here so the next specialist can read it. Approvals are requested here."})
        rooms = {"hq": {"id": hq["id"], "name": hq["name"], "purpose": "Brief, deliverables, approvals"}}
        for sp in SPECIALISTS:
            r = c.op("create_room", {
                "name": f"{slug}-{sp.room_suffix}", "description": f"{sp.display}: {sp.purpose}",
                "agent_names": [self.n(CONDUCTOR[0]), self.n(sp.agent)], "user_names": human,
                "instructions": f"Work room for {sp.display}. Handoffs from the conductor arrive here."})
            rooms[sp.key] = {"id": r["id"], "name": r["name"], "purpose": sp.purpose}
            try:
                c.op("link_rooms", {"source_room_id": r["id"], "target_room_id": hq["id"], "label": "reports to HQ"})
            except SwitchError as exc:
                log.warning("link_rooms failed: %s", exc)

        def save(d):
            d["rooms"] = rooms
            d["status"] = "running"
            for st in d["stages"]:
                st["room_name"] = rooms[st["key"]]["name"]
                st["room_id"] = rooms[st["key"]]["id"]
        self.store.update(lid, save)
        brief = (f"{marker('brief', lid)}\n**Founder brief for {doc['name']}**\n\n"
                 f"Launch name: {doc['name']}\nIdea: {doc['idea']}\nFounder: {doc['founder_name'] or 'n/a'}\n"
                 f"Target customer: {doc['target_customer'] or 'n/a'}\nConstraints: {doc['constraints'] or 'n/a'}\n\n"
                 f"Team: " + ", ".join(f"@{self.n(sp.agent)} ({sp.title})" for sp in SPECIALISTS))
        c.post(rooms["hq"]["id"], brief)
        self._handoff(lid, "research")

    def _handoff(self, lid: str, key: str, retry: bool = False, resend: bool = False) -> None:
        doc = self.store.get(lid)
        sp = BY_KEY[key]
        hq, room = doc["rooms"]["hq"], doc["rooms"][key]
        inputs = [BY_KEY[k].title for k in STAGE_KEYS[:STAGE_KEYS.index(key)]]

        def mark(d):
            st = _stage(d, key)
            if resend:
                st["handoffs"] = st.get("handoffs", 1) + 1
            else:
                st.update(status="running", started_at=now_iso(), finished_at=None, error=None, ack_at=None, handoffs=1)
            st["handoff_at"] = now_iso()
            d["status"] = "running"
        self.store.update(lid, mark)
        self.conductor.post(room["id"],
                            f"{marker('handoff', lid, key)} @{self.n(sp.agent)} {'Retry: ' if retry else ''}please produce: **{sp.title}**.\n"
                            f"Read the founder brief{' and ' + ', '.join(inputs) if inputs else ''} in #{hq['name']}, "
                            f"post your deliverable there, then report back here.")
        self.conductor.post(hq["id"], f"{'No acknowledgement yet, so I re-sent' if resend else 'Handed'} **{sp.title}** "
                                      f"to @{self.n(sp.agent)} in #{room['name']}.")

    # ── event handling ────────────────────────────────────────────────────────
    def _handler(self, me: str):
        def on_event(kind: str, ev: Dict[str, Any]) -> None:
            if kind != "message":
                return
            p = ev.get("payload") or {}
            body, sender = p.get("body") or "", p.get("sender_name") or ""
            if sender == me:
                return
            with self._seen_lock:
                seen = self._seen.setdefault(me, set())
                if p.get("message_id") in seen:
                    return
                seen.add(p.get("message_id"))
            m = MARK.search(body)
            if me == self.n(CONDUCTOR[0]):
                if m and m.group(1) in ("done", "failed") and sender in {self.n(sp.agent) for sp in SPECIALISTS}:
                    self._pool.submit(self._safe, self._on_stage_report, m.group(2), m.group(3), m.group(1), body)
                elif not m and sender not in self.agents:
                    self._maybe_human_decision(ev.get("room_id"), sender, body)
                return
            sp = next((s for s in SPECIALISTS if self.n(s.agent) == me), None)
            if sp and m and m.group(1) == "handoff" and m.group(3) == sp.key and sender == self.n(CONDUCTOR[0]):
                self._pool.submit(self._run_specialist, m.group(2), sp.key)
        return on_event

    def _run_specialist(self, lid: str, key: str) -> None:
        sp = BY_KEY[key]
        agent = self.agents[self.n(sp.agent)]
        claimed = []

        def claim(d):
            st = _stage(d, key)
            if st["status"] == "running" and not st.get("ack_at"):
                st["ack_at"] = now_iso()
                claimed.append(True)
        doc = self.store.update(lid, claim) if self.store.get(lid) else None
        if not doc or not claimed:
            return  # a duplicate (re-sent) handoff for work already under way
        hq_id, room_id = doc["rooms"]["hq"]["id"], doc["rooms"][key]["id"]
        try:
            agent.post(room_id, f"On it: reading the brief and earlier deliverables from #{doc['rooms']['hq']['name']}.")
            brief, upstream = self._read_inputs(agent, lid, hq_id)
            if not brief:
                raise RuntimeError("founder brief not found in the HQ room")
            llm = self._llm_for_stage()
            result: StageResult = run_stage(key, llm, brief, upstream)
            self._save_result(lid, key, result)
            body = f"{marker('deliverable', lid, key)}\n### {sp.title} · by {sp.display}\n\n{result.markdown}"
            if len(body) > MAX_POST:
                body = body[:MAX_POST] + "\n\n…(truncated; full version in LaunchOS)"
            agent.post(hq_id, body)
            agent.post(room_id, f"{marker('done', lid, key)} @{self.n(CONDUCTOR[0])} {sp.title} is posted in "
                                f"#{doc['rooms']['hq']['name']}{' (offline template mode)' if result.mode == 'offline' else ''}.")
        except Exception as exc:
            log.exception("%s failed", self.n(sp.agent))
            msg = f"{type(exc).__name__}: {str(exc)[:300]}"
            try:
                agent.post(room_id, f"{marker('failed', lid, key)} @{self.n(CONDUCTOR[0])} I couldn't finish: {msg}")
            except Exception:
                self._on_stage_report(lid, key, "failed", msg)

    def _read_inputs(self, agent: SwitchAgent, lid: str, hq_id: str):
        """Everything a specialist knows about the launch comes from the HQ room's history in Switch."""
        msgs = messages_from_context(agent.read_context(hq_id, limit=200))
        brief, upstream = "", {}
        for m in msgs:
            mm = MARK.search(m["body"])
            if not mm or mm.group(2) != lid:
                continue
            if mm.group(1) == "brief":
                brief = strip_markers(m["body"])
            elif mm.group(1) == "deliverable" and mm.group(3) in BY_KEY:
                upstream[mm.group(3)] = strip_markers(m["body"])
        upstream["_data"] = {"backlog": parse_backlog(upstream.get("product", "")),
                             "landing": parse_landing(upstream.get("builder", ""))}
        return brief, upstream

    def _llm_for_stage(self) -> Optional[LLM]:
        if self.s.llm_mode == "offline":
            return None
        if self.llm.available():
            return self.llm
        if self.s.llm_mode == "live":
            raise LLMError(f"LLM not reachable at {self.s.llm_base_url}")
        return None

    def _save_result(self, lid: str, key: str, r: StageResult) -> None:
        def upd(d):
            if key == "research":
                d["deliverables"]["research"] = {"markdown": r.markdown, "mode": r.mode}
            elif key == "product":
                d["deliverables"]["product"] = {"markdown": r.markdown, "backlog": r.data.get("backlog", []), "mode": r.mode}
            elif key == "builder":
                d["landing_html"] = r.data.get("html")
                d["deliverables"]["builder"] = {"url": f"/api/launches/{d['id']}/landing", "summary": r.markdown,
                                                "content": r.data.get("landing"), "mode": r.mode}
            elif key == "marketing":
                d["deliverables"]["marketing"] = {"markdown": r.markdown, "mode": r.mode}
            elif key == "readiness":
                d["deliverables"]["readiness"] = {"markdown": r.markdown, "score": r.data.get("score"),
                                                  "checks": r.data.get("checks", []), "mode": r.mode}
            _stage(d, key)["mode"] = r.mode
        self.store.update(lid, upd)

    def _on_stage_report(self, lid: str, key: str, kind: str, body: str) -> None:
        doc = self.store.get(lid)
        if not doc or key not in BY_KEY or _stage(doc, key)["status"] != "running":
            return
        if kind == "failed":
            err = strip_markers(body).replace(f"@{self.n(CONDUCTOR[0])}", "").strip()

            def fail(d):
                _stage(d, key).update(status="failed", finished_at=now_iso(), error=err[:400])
                d["status"] = "failed"
            self.store.update(lid, fail)
            self.conductor.post(doc["rooms"]["hq"]["id"], f"⚠️ **{BY_KEY[key].title}** failed: {err[:300]}. "
                                                          f"The founder can retry this stage from LaunchOS.")
            return
        self.store.update(lid, lambda d: _stage(d, key).update(status="done", finished_at=now_iso()))
        idx = STAGE_KEYS.index(key)
        if idx + 1 < len(STAGE_KEYS):
            self._handoff(lid, STAGE_KEYS[idx + 1])
        else:
            self._request_approval(lid)

    # ── human approval ────────────────────────────────────────────────────────
    def _request_approval(self, lid: str) -> None:
        doc = self.store.get(lid)
        score = (doc["deliverables"].get("readiness") or {}).get("score")
        apr = {"id": "apr_" + secrets.token_hex(2), "title": "Approve public launch",
               "description": f"The launch auditor scored readiness {score}/100. Approving publishes the landing page and "
                              f"starts the marketing plan. This is a consequential decision and needs a human.",
               "status": "pending", "decided_by": None, "note": None, "decided_at": None, "via": None}

        def upd(d):
            d["approvals"].append(apr)
            d["status"] = "waiting_approval"
            _stage(d, "readiness")["status"] = "done"
        self.store.update(lid, upd)
        human = f"@{self.s.mattermost_user} " if self.s.mattermost_user else ""
        self.agents[self.n("launch-auditor")].post(
            doc["rooms"]["hq"]["id"],
            f"{marker('approval', lid, apr['id'])} {human}**Human approval needed: {apr['title']}** "
            f"(readiness {score}/100).\nReply here with `approve <reason>` or `reject <reason>`, or decide in LaunchOS.")

    def decide(self, lid: str, approval_id: str, decision: str, note: str, decided_by: str, via: str = "LaunchOS UI") -> Dict[str, Any]:
        if decision not in ("approve", "reject"):
            raise ValueError("decision must be approve or reject")
        if not note.strip() or not decided_by.strip():
            raise ValueError("note and decided_by are required")
        result = {}

        def upd(d):
            apr = next((a for a in d["approvals"] if a["id"] == approval_id), None)
            if apr is None:
                raise KeyError(approval_id)
            if apr["status"] != "pending":
                raise ValueError(f"approval already {apr['status']}")
            apr.update(status="approved" if decision == "approve" else "rejected", decided_by=decided_by.strip()[:80],
                       note=note.strip()[:500], decided_at=now_iso(), via=via)
            d["status"] = "launched" if decision == "approve" else "rejected"
            result.update(apr)
        doc = self.store.update(lid, upd)
        verdict = "APPROVED ✅ launch is go" if decision == "approve" else "REJECTED ⛔ launch is on hold"
        self.conductor.post(doc["rooms"]["hq"]["id"],
                            f"{marker('decision', lid, approval_id)} **{result['title']}: {verdict}**\n"
                            f"Decided by {result['decided_by']} via {via}: {result['note']}")
        return doc

    def _maybe_human_decision(self, room_id: Optional[str], sender: str, body: str) -> None:
        text = body.strip()
        m = re.match(r"^(?:@\S+\s+)?(approve|reject)\b[:\s-]*(.*)$", text, flags=re.I | re.S)
        if not m or not room_id:
            return
        for doc in self.store.list():
            if doc.get("rooms", {}).get("hq", {}).get("id") != room_id:
                continue
            pending = [a for a in doc["approvals"] if a["status"] == "pending"]
            if pending:
                note = m.group(2).strip() or "(no reason given)"
                try:
                    self.decide(doc["id"], pending[-1]["id"], m.group(1).lower(), note, sender, via="Switch room (Mattermost)")
                except (ValueError, KeyError) as exc:
                    log.warning("human decision ignored: %s", exc)
            return

    # ── retries, recovery, watchdog ───────────────────────────────────────────
    def retry(self, lid: str, key: str) -> Dict[str, Any]:
        doc = self.store.get(lid)
        if doc is None:
            raise KeyError(lid)
        if key not in BY_KEY:
            raise ValueError("unknown stage")
        if _stage(doc, key)["status"] not in ("failed",):
            raise ValueError("only a failed stage can be retried")
        if not doc.get("rooms"):
            self.store.update(lid, lambda d: d.update(status="queued", error=None))
            self._pool.submit(self._safe, self._open_rooms_and_begin, lid)
        else:
            self._pool.submit(self._safe, self._handoff, lid, key, True)
        return self.store.get(lid)

    def _recover_interrupted(self) -> None:
        for doc in self.store.list():
            if doc["status"] in ("running", "queued"):
                def upd(d):
                    for st in d["stages"]:
                        if st["status"] == "running":
                            st.update(status="failed", error="Interrupted by a LaunchOS restart; retry this stage.")
                    if any(st["status"] == "failed" for st in d["stages"]) or not d.get("rooms"):
                        d["status"] = "failed"
                        if not d.get("rooms"):
                            d["stages"][0].update(status="failed", error="Interrupted before rooms were created; retry.")
                self.store.update(doc["id"], upd)

    def _watchdog(self) -> None:
        while not self._stop.wait(5):
            for doc in self.store.list():
                if doc["status"] != "running":
                    continue
                for st in doc["stages"]:
                    if (st["status"] == "running" and not st.get("ack_at") and st.get("handoff_at")
                            and _age(st["handoff_at"]) > ACK_TIMEOUT and st.get("handoffs", 1) < MAX_HANDOFFS):
                        self._pool.submit(self._safe, self._handoff, doc["id"], st["key"], False, True)
                        continue
                    if st["status"] == "running" and st["started_at"] and _age(st["started_at"]) > self.s.stage_timeout:
                        self._on_stage_report(doc["id"], st["key"], "failed",
                                              f"No report from @{st['agent']} within {int(self.s.stage_timeout)} s")

    # ── timeline (read back from Switch) ──────────────────────────────────────
    def timeline(self, lid: str) -> List[Dict[str, Any]]:
        doc = self.store.get(lid)
        if doc is None:
            raise KeyError(lid)
        cached = self._timeline_cache.get(lid)
        if cached and time.time() - cached[0] < 2.5:
            return cached[1]
        items = []
        for key, room in (doc.get("rooms") or {}).items():
            try:
                msgs = messages_from_context(self.conductor.read_context(room["id"], limit=200))
            except SwitchError as exc:
                log.warning("timeline read failed: %s", exc)
                continue
            for m in msgs:
                mm = MARK.search(m["body"])
                if mm and mm.group(2) != lid:
                    continue
                kind = {"handoff": "handoff", "deliverable": "deliverable", "approval": "approval",
                        "decision": "approval", "brief": "message"}.get(mm.group(1) if mm else "", "message")
                if not mm and len(m["body"]) < 120 and f"@{m['sender_name']}" in m["body"]:
                    continue  # Switch's automatic "tag me" introduction when an agent joins a room
                items.append({"ts": _iso_ms(m["timestamp"]), "room": room["name"], "sender": m["sender_name"],
                              "kind": kind, "body": strip_markers(m["body"])})
        items.sort(key=lambda x: x["ts"])
        self._timeline_cache[lid] = (time.time(), items)
        return items


# ── helpers ───────────────────────────────────────────────────────────────────
def _stage(doc: Dict[str, Any], key: str) -> Dict[str, Any]:
    return next(st for st in doc["stages"] if st["key"] == key)


def _derive_name(idea: str) -> str:
    first = re.split(r"[.,;:\n]| that | which | with ", idea.strip(), maxsplit=1)[0]
    words = first.split()[:6]
    return " ".join(words).strip().rstrip(".").capitalize() or "Untitled launch"


def _age(iso: str) -> float:
    from datetime import datetime
    return time.time() - datetime.fromisoformat(iso).timestamp()


def _iso_ms(ms: Any) -> str:
    from datetime import datetime, timezone
    try:
        return datetime.fromtimestamp(int(ms) / 1000, tz=timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return now_iso()


def parse_backlog(md: str) -> List[Dict[str, str]]:
    out = []
    for line in md.splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 5 and re.match(r"^LOS-\d+$", cells[0]):
            out.append({"id": cells[0], "title": cells[1], "priority": cells[2], "estimate": cells[3], "acceptance": cells[4]})
    return out


def parse_landing(md: str) -> Optional[Dict[str, Any]]:
    if not md:
        return None
    head = re.search(r"Headline:\s*(.+)", md)
    tiers = re.search(r"pricing \((\d+) tiers\)", md)
    return {"headline": head.group(1).strip() if head else "",
            "pricing": [None] * int(tiers.group(1)) if tiers and int(tiers.group(1)) > 0 else []}
