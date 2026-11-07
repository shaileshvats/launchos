"""Minimal client for the Switch agent protocol (SSE down, HTTP up).

Implements what LaunchOS needs from https://docs.switchagents.ai/flintai/switch/internals/agent-protocol:
agent registration, operations (`POST /agents/{id}/ops/{name}`), posting messages, the event stream
and the heartbeat.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, Iterator, List, Optional

import httpx

log = logging.getLogger("launchos.switch")


class SwitchError(RuntimeError):
    def __init__(self, message: str, status: Optional[int] = None):
        super().__init__(message)
        self.status = status


INTEGRATION_PROFILE = {
    "connection_model": "always_on",
    "message_exchange": True,
    "pre_invocation_mediation": [],
    "post_invocation_mediation": [],
    "event_reporting": [],
}


def health(base_url: str, timeout: float = 3.0) -> bool:
    try:
        return httpx.get(f"{base_url}/health", timeout=timeout).status_code == 200
    except httpx.HTTPError:
        return False


def register_agent(base_url: str, registration_token: str, name: str, description: str,
                   display_name: str, overwrite: bool = True) -> Dict[str, str]:
    """Register a custom agent (`POST /agents`). Returns {id, api_key}; the key is shown once."""
    r = httpx.post(
        f"{base_url}/agents",
        headers={"Authorization": f"Bearer {registration_token}"},
        json={
            "name": name,
            "description": description,
            "display_name": display_name,
            "connector_type": "LaunchOS",
            "integration_profile": INTEGRATION_PROFILE,
            "metadata": {"app": "launchos"},
            "overwrite": overwrite,
        },
        timeout=20,
    )
    if r.status_code >= 300:
        raise SwitchError(f"register {name}: {r.status_code} {r.text[:300]}", r.status_code)
    return r.json()


class SwitchAgent:
    """One registered Switch agent, acting with its own API key."""

    def __init__(self, base_url: str, agent_id: str, api_key: str, name: str):
        self.base_url = base_url.rstrip("/")
        self.agent_id = agent_id
        self.api_key = api_key
        self.name = name
        self.connection_id = str(uuid.uuid4())
        self.attached = threading.Event()  # set once the server has sent connection_state at least once
        self._http = httpx.Client(timeout=60, headers={"Authorization": f"Bearer {api_key}"})

    # ── operations ────────────────────────────────────────────────────────────
    def op(self, name: str, args: Optional[Dict[str, Any]] = None, room_bound: bool = False) -> Any:
        headers = {"X-Switch-Connection-Id": self.connection_id} if room_bound else {}
        r = self._http.post(f"{self.base_url}/agents/{self.agent_id}/ops/{name}", json=args or {}, headers=headers)
        if r.status_code >= 300:
            raise SwitchError(f"{self.name}.{name}: {r.status_code} {r.text[:400]}", r.status_code)
        return r.json().get("result")

    def list_ops(self) -> Dict[str, Any]:
        r = self._http.get(f"{self.base_url}/agents/{self.agent_id}/ops")
        r.raise_for_status()
        return r.json().get("operations", {})

    def post(self, room_id: str, content: str) -> Any:
        """Post into a room without a connection (`POST /agents/{id}/message`)."""
        r = self._http.post(f"{self.base_url}/agents/{self.agent_id}/message",
                            json={"room_id": room_id, "content": content})
        if r.status_code >= 300:
            raise SwitchError(f"{self.name} post: {r.status_code} {r.text[:300]}", r.status_code)
        return r.json() if r.content else {}

    def read_context(self, room_id: str, limit: int = 100) -> Dict[str, Any]:
        return self.op("read_context", {"room_id": room_id, "limit": limit})

    # ── event stream ──────────────────────────────────────────────────────────
    def beat(self, cursor: Optional[int]) -> int:
        body: Dict[str, Any] = {"connection_id": self.connection_id}
        if cursor is not None:
            body["cursor"] = cursor
        r = self._http.post(f"{self.base_url}/agents/{self.agent_id}/connection/beat", json=body)
        return r.status_code

    def stream(self, on_event: Callable[[str, Dict[str, Any]], None], stop: threading.Event) -> None:
        """Hold the SSE stream open (scope=all) and dispatch domain events until `stop` is set.

        Reconnects with the same connection id and Last-Event-ID; beats every 2 s while attached.
        """
        cursor: Optional[int] = None
        while not stop.is_set():
            attached = threading.Event()
            beater = threading.Thread(target=self._beat_loop, args=(attached, stop, lambda: cursor), daemon=True)
            beater.start()
            try:
                params = {"connection_id": self.connection_id, "scope": "all", "filter": "all",
                          "start_from": "head", "client": "launchos", "client_version": "0.1.0"}
                headers = {"Accept": "text/event-stream"}
                if cursor is not None:
                    headers["Last-Event-ID"] = str(cursor)
                with self._http.stream("GET", f"{self.base_url}/agents/{self.agent_id}/events",
                                       params=params, headers=headers, timeout=httpx.Timeout(60, read=None)) as resp:
                    if resp.status_code >= 300:
                        raise SwitchError(f"{self.name} stream: {resp.status_code}", resp.status_code)
                    for kind, data, seq in _parse_sse(resp.iter_lines()):
                        if stop.is_set():
                            break
                        if kind == "connection_state":
                            attached.set()
                            self.attached.set()
                            if cursor is None and isinstance(data.get("cursor"), int):
                                cursor = data["cursor"]  # resume from here if the socket drops
                            continue
                        if seq is not None:
                            cursor = seq
                        if kind in ("message", "command", "room_join"):
                            try:
                                on_event(kind, data)
                            except Exception:  # never let a handler kill the stream
                                log.exception("%s event handler failed", self.name)
            except (httpx.HTTPError, SwitchError) as exc:
                log.warning("%s stream dropped: %s; reconnecting", self.name, exc)
                stop.wait(2)
            finally:
                attached.clear()

    def _beat_loop(self, attached: threading.Event, stop: threading.Event, cursor_fn: Callable[[], Optional[int]]):
        while not stop.is_set():
            if attached.wait(1):
                try:
                    self.beat(cursor_fn())
                except httpx.HTTPError:
                    pass
                time.sleep(2)
            elif not attached.is_set() and stop.is_set():
                return


def _parse_sse(lines: Iterator[str]):
    event, data, seq = None, [], None
    for line in lines:
        if line == "":
            if data:
                try:
                    payload = json.loads("\n".join(data))
                except ValueError:
                    payload = {}
                yield (event or payload.get("type") or "message"), payload, seq
            event, data, seq = None, [], None
            continue
        if line.startswith(":"):
            continue
        field, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if field == "event":
            event = value
        elif field == "data":
            data.append(value)
        elif field == "id":
            try:
                seq = int(value)
            except ValueError:
                seq = None


def messages_from_context(ctx: Any, include_joins: bool = False) -> List[Dict[str, Any]]:
    """Flatten a read_context result ({threads: [{root, replies}]}) into chronological messages."""
    items: List[Dict[str, Any]] = []
    threads = ctx.get("threads", []) if isinstance(ctx, dict) else []
    for t in threads:
        for m in [t.get("root")] + list(t.get("replies") or []):
            if isinstance(m, dict):
                items.append(m)
    out = []
    for m in items:
        kind = m.get("kind", "message")
        if kind != "message" and not include_joins:
            continue
        out.append({
            "id": m.get("id"),
            "kind": kind,
            "sender": m.get("sender", ""),
            "sender_name": m.get("sender_name") or m.get("sender", ""),
            "body": m.get("body") or "",
            "timestamp": m.get("timestamp") or 0,
        })
    out.sort(key=lambda m: m["timestamp"] or 0)
    return out
