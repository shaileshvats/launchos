"""End-to-end against a real Switch server (skipped when none is configured).

Runs the whole founder-to-launch journey in offline-template mode under `itest-` agent names, so it
can run beside a live LaunchOS. Every assertion about coordination is checked by reading the Switch
rooms back, not LaunchOS's own state.
"""
import time

import pytest
from fastapi.testclient import TestClient

from launchos.app import create_app
from launchos.config import Settings
from launchos.store import Store
from launchos.switch_client import health, messages_from_context
from launchos.workflow import LaunchOS

S = Settings.from_env()
pytestmark = pytest.mark.skipif(not (S.switch_registration_token and health(S.switch_api_url)),
                                reason="needs a running Switch server and SWITCH_REGISTRATION_TOKEN")


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    s = Settings.from_env()
    s.llm_mode = "offline"
    s.agent_prefix = "itest-"
    s.data_dir = tmp_path_factory.mktemp("data")
    eng = LaunchOS(s, Store(s.data_dir / "t.db"))
    eng.start()
    app = create_app(s, eng, start=False)
    with TestClient(app) as c:
        c.engine = eng
        yield c
    eng.stop()


def wait_for(fn, timeout=120, every=1.0):
    end = time.time() + timeout
    while time.time() < end:
        v = fn()
        if v:
            return v
        time.sleep(every)
    raise AssertionError("timed out")


def test_full_journey_through_switch(client):
    r = client.post("/api/launches", json={"idea": "A meal-prep service for night-shift nurses in Pune",
                                           "founder_name": "Test Founder", "name": "ShiftMeals"})
    assert r.status_code == 201
    lid = r.json()["id"]

    doc = wait_for(lambda: (lambda d: d if d["status"] in ("waiting_approval", "failed") else None)(
        client.get(f"/api/launches/{lid}").json()))
    assert doc["status"] == "waiting_approval", doc
    assert [s["status"] for s in doc["stages"]] == ["done"] * 5
    assert all(doc["deliverables"][k] for k in ["research", "product", "builder", "marketing", "readiness"])
    assert doc["deliverables"]["product"]["backlog"]
    assert len(doc["switch"]["rooms"]) == 6
    assert client.get(f"/api/launches/{lid}/landing").status_code == 200

    # The coordination really happened in Switch: read the HQ room as the conductor.
    eng = client.engine
    hq = eng.store.get(lid)["rooms"]["hq"]["id"]
    bodies = [m["body"] for m in messages_from_context(eng.conductor.read_context(hq, limit=200))]
    for key in ["research", "product", "builder", "marketing", "readiness"]:
        assert any(f"[deliverable:{lid}:{key}]" in b for b in bodies), key
    assert any(f"[approval:{lid}:" in b for b in bodies)

    timeline = client.get(f"/api/launches/{lid}/timeline").json()
    kinds = {t["kind"] for t in timeline}
    assert {"handoff", "deliverable", "approval"} <= kinds

    # Human approval: validation, then the decision is posted back into the HQ room.
    apr = doc["approvals"][0]["id"]
    bad = client.post(f"/api/launches/{lid}/approvals/{apr}", json={"decision": "approve", "note": "", "decided_by": "x"})
    assert bad.status_code == 400
    ok = client.post(f"/api/launches/{lid}/approvals/{apr}",
                     json={"decision": "approve", "note": "Looks ready", "decided_by": "Test Founder"})
    assert ok.status_code == 200 and ok.json()["status"] == "launched"
    again = client.post(f"/api/launches/{lid}/approvals/{apr}",
                        json={"decision": "reject", "note": "late", "decided_by": "x"})
    assert again.status_code == 400
    bodies = [m["body"] for m in messages_from_context(eng.conductor.read_context(hq, limit=200))]
    assert any(f"[decision:{lid}:{apr}]" in b and "Test Founder" in b for b in bodies)


def test_validation_and_not_found(client):
    assert client.post("/api/launches", json={"idea": "short"}).status_code == 422
    assert client.get("/api/launches/lch_nope").status_code == 404
    assert client.post("/api/launches/lch_nope/retry", json={"stage": "research"}).status_code == 404
