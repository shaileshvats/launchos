"""Unit tests: no Switch server or model needed."""
from launchos.llm import extract_json, strip_think
from launchos.specialists import (backlog_md, readiness_checks, readiness_score, render_landing, run_stage)
from launchos.store import Store
from launchos.switch_client import _parse_sse, messages_from_context
from launchos.workflow import MARK, marker, parse_backlog, parse_landing, strip_markers

BRIEF = "Launch name: BrewDesk\nIdea: coffee subscription\nTarget customer: startups"


def test_extract_json_handles_fences_and_think_blocks():
    assert extract_json('<think>hmm</think>```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('Sure! [1, 2] done') == [1, 2]
    assert strip_think("<think>x</think>ok") == "ok"


def test_markers_round_trip():
    m = MARK.search("text " + marker("done", "lch_ab12cd", "research") + " more")
    assert m.group(1, 2, 3) == ("done", "lch_ab12cd", "research")
    assert strip_markers(marker("brief", "lch_x") + " hello") == "hello"


def test_sse_parser_reads_ids_and_events():
    lines = ["id: 7", "event: message", 'data: {"type":"message","payload":{"body":"hi"}}', "", ": keepalive", ""]
    events = list(_parse_sse(iter(lines)))
    assert events == [("message", {"type": "message", "payload": {"body": "hi"}}, 7)]


def test_messages_from_context_flattens_threads_and_skips_joins():
    ctx = {"threads": [
        {"root": {"id": "1", "kind": "room_join", "sender_name": "a", "body": "a joined", "timestamp": 1}, "replies": []},
        {"root": {"id": "2", "kind": "message", "sender_name": "a", "body": "root", "timestamp": 3},
         "replies": [{"id": "3", "kind": "message", "sender_name": "b", "body": "reply", "timestamp": 2}]}]}
    msgs = messages_from_context(ctx)
    assert [m["body"] for m in msgs] == ["reply", "root"]


def test_offline_pipeline_produces_every_deliverable():
    upstream = {}
    for key in ["research", "product", "builder", "marketing"]:
        r = run_stage(key, None, BRIEF, upstream)
        assert r.mode == "offline" and r.markdown
        upstream[key] = r.markdown
    upstream["_data"] = {"backlog": parse_backlog(upstream["product"]), "landing": parse_landing(upstream["builder"])}
    r = run_stage("readiness", None, BRIEF, upstream)
    assert 0 <= r.data["score"] <= 100 and len(r.data["checks"]) == 8


def test_backlog_table_parses_back():
    items = [{"id": "LOS-1", "title": "Waitlist", "priority": "P0", "estimate": "1d", "acceptance": "Email stored"}]
    assert parse_backlog(backlog_md(items)) == items


def test_readiness_is_deterministic_and_flags_missing_work():
    checks = readiness_checks({}, [], None)
    assert {c["name"]: c["status"] for c in checks}["Landing page live"] == "fail"
    assert readiness_score(checks) < 30
    legal = [c for c in checks if c["name"].startswith("Legal")][0]
    assert legal["status"] == "warn"  # never auto-passed by AI


def test_landing_page_escapes_model_output():
    page = render_landing({"product_name": "<script>alert(1)</script>", "headline": "Hi", "features": [],
                           "pricing": [], "faq": []})
    assert "<script>alert" not in page and "&lt;script&gt;" in page


def test_store_update_is_atomic(tmp_path):
    s = Store(tmp_path / "t.db")
    s.create({"id": "lch_1", "created_at": "2026-01-01", "n": 0})
    s.update("lch_1", lambda d: d.update(n=d["n"] + 1))
    assert s.get("lch_1")["n"] == 1
    s.save_agent("a", "id1", "key1")
    assert s.agents() == {"a": {"agent_id": "id1", "api_key": "key1"}}
