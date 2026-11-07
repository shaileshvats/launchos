"""OpenAI-compatible chat client (LM Studio, Ollama or any hosted endpoint)."""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Dict, List, Optional

import httpx

from .config import Settings

log = logging.getLogger("launchos.llm")


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self, settings: Settings):
        self.base_url = settings.llm_base_url.rstrip("/")
        self.model = settings.llm_model
        self.api_key = settings.llm_api_key or "local-no-key"
        self.timeout = settings.llm_timeout

    def available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/models", headers={"Authorization": f"Bearer {self.api_key}"}, timeout=3)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def chat(self, system: str, user: str, max_tokens: int = 1400, temperature: float = 0.4) -> str:
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body,
                           headers={"Authorization": f"Bearer {self.api_key}"}, timeout=self.timeout)
        except httpx.HTTPError as exc:
            raise LLMError(f"LLM request failed: {exc}") from exc
        if r.status_code >= 300:
            raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
        try:
            text = r.json()["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, ValueError) as exc:
            raise LLMError(f"Unexpected LLM response: {r.text[:300]}") from exc
        return strip_think(text).strip()

    def chat_json(self, system: str, user: str, max_tokens: int = 1400) -> Any:
        """Ask for JSON; one corrective retry if the reply doesn't parse."""
        text = self.chat(system, user, max_tokens=max_tokens, temperature=0.2)
        try:
            return extract_json(text)
        except ValueError:
            fix = self.chat(system, user + "\n\nYour previous reply was not valid JSON. Reply with ONLY the JSON value.",
                            max_tokens=max_tokens, temperature=0.0)
            return extract_json(fix)


def strip_think(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.S)


def extract_json(text: str) -> Any:
    text = strip_think(text).strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.S)
    if fenced:
        text = fenced.group(1).strip()
    for opener, closer in (("{", "}"), ("[", "]")):
        start = text.find(opener)
        end = text.rfind(closer)
        if start != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except ValueError:
                continue
    raise ValueError("no JSON found")
