"""Settings from environment variables (see .env.example)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip())


@dataclass
class Settings:
    switch_api_url: str = "http://127.0.0.1:8000"
    switch_gateway_url: str = "http://localhost:3000"
    mattermost_url: str = "http://localhost:8065"
    mattermost_team: str = "switch"
    switch_registration_token: str = ""
    mattermost_user: str = "user"
    llm_base_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = "qwen/qwen3-4b-2507"
    llm_api_key: str = ""
    llm_timeout: float = 240.0
    llm_mode: str = "auto"  # auto | live | offline
    data_dir: Path = field(default_factory=lambda: ROOT / "data")
    stage_timeout: float = 420.0
    agent_prefix: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        _load_dotenv(ROOT / ".env")
        s = cls()
        env = os.environ.get
        s.switch_api_url = env("SWITCH_API_URL", s.switch_api_url)
        s.switch_gateway_url = env("SWITCH_GATEWAY_URL", s.switch_gateway_url)
        s.mattermost_url = env("MATTERMOST_URL", s.mattermost_url)
        s.mattermost_team = env("MATTERMOST_TEAM", s.mattermost_team)
        s.switch_registration_token = env("SWITCH_REGISTRATION_TOKEN", s.switch_registration_token)
        s.mattermost_user = env("SWITCH_HUMAN_USER", s.mattermost_user)
        s.llm_base_url = env("LLM_BASE_URL", s.llm_base_url)
        s.llm_model = env("LLM_MODEL", s.llm_model)
        s.llm_api_key = env("LLM_API_KEY", s.llm_api_key)
        s.llm_timeout = float(env("LLM_TIMEOUT", str(s.llm_timeout)))
        s.llm_mode = env("LLM_MODE", s.llm_mode)
        s.data_dir = Path(env("LAUNCHOS_DATA_DIR", str(s.data_dir)))
        s.stage_timeout = float(env("STAGE_TIMEOUT", str(s.stage_timeout)))
        s.agent_prefix = env("AGENT_PREFIX", s.agent_prefix)
        return s
