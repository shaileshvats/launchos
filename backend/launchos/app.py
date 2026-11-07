"""LaunchOS HTTP API and static web UI."""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .config import ROOT, Settings
from .store import Store
from .switch_client import SwitchError, health
from .workflow import LaunchOS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)  # heartbeats every 2 s would drown the log
log = logging.getLogger("launchos")


class NewLaunch(BaseModel):
    idea: str = Field(..., min_length=10, max_length=2000)
    founder_name: str = Field("", max_length=80)
    target_customer: str = Field("", max_length=300)
    constraints: str = Field("", max_length=500)
    name: str = Field("", max_length=60)


class Decision(BaseModel):
    decision: str
    note: str = Field(..., max_length=500)
    decided_by: str = Field(..., max_length=80)


class Retry(BaseModel):
    stage: str


def create_app(settings: Optional[Settings] = None, engine: Optional[LaunchOS] = None, start: bool = True) -> FastAPI:
    s = settings or Settings.from_env()
    eng = engine or LaunchOS(s, Store(s.data_dir / "launchos.db"))
    app = FastAPI(title="LaunchOS", version="0.1.0")
    app.state.engine = eng

    def boot():
        try:
            eng.start()
            log.info("LaunchOS agents connected to Switch at %s", s.switch_api_url)
        except Exception as exc:
            eng.start_error = str(exc)
            log.error("Switch startup failed: %s", exc)

    if start:
        app.add_event_handler("startup", lambda: threading.Thread(target=boot, daemon=True).start())
        app.add_event_handler("shutdown", eng.stop)

    def need_started():
        if not eng.started:
            raise HTTPException(503, eng.start_error or "LaunchOS is still connecting to Switch")

    def public(doc: Dict[str, Any]) -> Dict[str, Any]:
        out = {k: v for k, v in doc.items() if k not in ("landing_html", "rooms")}
        mm = s.mattermost_url.rstrip("/")
        out["switch"] = {"rooms": [{"id": r["id"], "name": r["name"], "purpose": r.get("purpose", ""),
                                    "url": f"{mm}/{s.mattermost_team}/channels/{r['name']}"}
                                   for r in (doc.get("rooms") or {}).values()]}
        return out

    def get_doc(lid: str) -> Dict[str, Any]:
        doc = eng.store.get(lid)
        if doc is None:
            raise HTTPException(404, "launch not found")
        return doc

    @app.get("/api/health")
    def api_health():
        sw_ok = health(s.switch_api_url)
        return {"ok": sw_ok and eng.started,
                "switch": {"ok": sw_ok, "agents_connected": eng.started, "error": eng.start_error,
                           "api_url": s.switch_api_url, "gateway_url": s.switch_gateway_url,
                           "mattermost_url": s.mattermost_url, "agents": sorted(eng.agents)},
                "llm": eng.llm_status()}

    @app.post("/api/launches", status_code=201)
    def api_create(body: NewLaunch):
        need_started()
        doc = eng.create_launch(body.idea, body.founder_name, body.target_customer, body.constraints, body.name)
        return {"id": doc["id"]}

    @app.get("/api/launches")
    def api_list():
        return [{"id": d["id"], "name": d["name"], "status": d["status"], "created_at": d["created_at"]}
                for d in eng.store.list()]

    @app.get("/api/launches/{lid}")
    def api_get(lid: str):
        return public(get_doc(lid))

    @app.get("/api/launches/{lid}/timeline")
    def api_timeline(lid: str):
        get_doc(lid)
        need_started()
        try:
            return eng.timeline(lid)
        except SwitchError as exc:
            raise HTTPException(502, f"Could not read Switch rooms: {exc}")

    @app.post("/api/launches/{lid}/approvals/{aid}")
    def api_decide(lid: str, aid: str, body: Decision):
        get_doc(lid)
        need_started()
        try:
            return public(eng.decide(lid, aid, body.decision, body.note, body.decided_by))
        except KeyError:
            raise HTTPException(404, "approval not found")
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.post("/api/launches/{lid}/retry")
    def api_retry(lid: str, body: Retry):
        get_doc(lid)
        need_started()
        try:
            return public(eng.retry(lid, body.stage))
        except ValueError as exc:
            raise HTTPException(400, str(exc))

    @app.get("/api/launches/{lid}/landing", response_class=HTMLResponse)
    def api_landing(lid: str):
        doc = get_doc(lid)
        if not doc.get("landing_html"):
            raise HTTPException(404, "landing page not built yet")
        return HTMLResponse(doc["landing_html"], headers={"Content-Security-Policy": "script-src 'none'; frame-ancestors 'self'"})

    web = ROOT / "web"
    if web.exists():
        app.mount("/static", StaticFiles(directory=str(web)), name="static")

        @app.get("/")
        def index():
            return FileResponse(str(web / "index.html"))

        @app.get("/{path:path}")
        def assets(path: str):
            f = (web / path).resolve()
            if web.resolve() in f.parents and f.is_file():
                return FileResponse(str(f))
            raise HTTPException(404, "not found")

    return app
