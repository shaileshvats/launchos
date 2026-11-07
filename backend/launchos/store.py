"""SQLite persistence: one JSON document per launch, plus agent credentials."""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._lock = threading.RLock()
        with self._lock:
            self._db.execute("CREATE TABLE IF NOT EXISTS launches (id TEXT PRIMARY KEY, created_at TEXT, doc TEXT)")
            self._db.execute("CREATE TABLE IF NOT EXISTS agents (name TEXT PRIMARY KEY, agent_id TEXT, api_key TEXT)")
            self._db.commit()

    # ── launches ──────────────────────────────────────────────────────────────
    def create(self, doc: Dict[str, Any]) -> Dict[str, Any]:
        with self._lock:
            self._db.execute("INSERT INTO launches VALUES (?,?,?)", (doc["id"], doc["created_at"], json.dumps(doc)))
            self._db.commit()
        return doc

    def get(self, launch_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._db.execute("SELECT doc FROM launches WHERE id=?", (launch_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def list(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._db.execute("SELECT doc FROM launches ORDER BY created_at DESC").fetchall()
        return [json.loads(r[0]) for r in rows]

    def update(self, launch_id: str, fn: Callable[[Dict[str, Any]], None]) -> Dict[str, Any]:
        """Read-modify-write under the lock, so concurrent agent threads never lose an update."""
        with self._lock:
            doc = self.get(launch_id)
            if doc is None:
                raise KeyError(launch_id)
            fn(doc)
            doc["updated_at"] = now_iso()
            self._db.execute("UPDATE launches SET doc=? WHERE id=?", (json.dumps(doc), launch_id))
            self._db.commit()
            return doc

    # ── agent credentials (never leave the data dir) ─────────────────────────
    def save_agent(self, name: str, agent_id: str, api_key: str) -> None:
        with self._lock:
            self._db.execute("INSERT OR REPLACE INTO agents VALUES (?,?,?)", (name, agent_id, api_key))
            self._db.commit()

    def agents(self) -> Dict[str, Dict[str, str]]:
        with self._lock:
            rows = self._db.execute("SELECT name, agent_id, api_key FROM agents").fetchall()
        return {n: {"agent_id": i, "api_key": k} for n, i, k in rows}
