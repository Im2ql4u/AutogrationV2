"""Study settings from the environment and the study's git-ignored `.env`."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

STUDY_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_API_URL = "http://localhost:5201/api/v1"
AUTH_MODES = ("auto", "browser", "device-code", "azure-cli", "token", "none")


class ConfigError(ValueError):
    """The study is not configured for what was asked."""


def _env(name: str) -> str | None:
    value = os.environ.get(name, "").strip()
    return value or None


@dataclass(frozen=True)
class Environment:
    name: str
    api_url: str
    api_scope: str | None


def _environments() -> dict[str, Environment]:
    """Named environments from ``AUTOGRATION_<NAME>_API_URL`` (+ ``_API_SCOPE``)."""
    out: dict[str, Environment] = {}
    for key, value in os.environ.items():
        m = re.fullmatch(r"AUTOGRATION_([A-Z0-9]+)_API_URL", key)
        if m and value.strip():
            name = m.group(1).lower()
            out[name] = Environment(
                name, value.strip().rstrip("/"), _env(f"AUTOGRATION_{m.group(1)}_API_SCOPE")
            )
    return out


@dataclass(frozen=True)
class Settings:
    api_url: str
    auth: str
    api_scope: str | None
    tenant_id: str | None
    token: str | None
    data_dir: Path
    environments: dict[str, Environment] = field(default_factory=dict)

    @classmethod
    def from_env(cls, env_file: Path | None = None) -> Settings:
        load_dotenv(env_file or STUDY_ROOT / ".env", override=False)
        auth = (_env("AUTOGRATION_AUTH") or "auto").lower()
        if auth not in AUTH_MODES:
            raise ConfigError(f"AUTOGRATION_AUTH={auth!r}; use one of {', '.join(AUTH_MODES)}")
        data_dir = Path(_env("STUDY_DATA_DIR") or "data")
        if not data_dir.is_absolute():
            data_dir = STUDY_ROOT / data_dir
        return cls(
            api_url=(_env("AUTOGRATION_API_URL") or DEFAULT_API_URL).rstrip("/"),
            auth=auth,
            api_scope=_env("AUTOGRATION_API_SCOPE"),
            tenant_id=_env("AZURE_TENANT_ID"),
            token=_env("AUTOGRATION_TOKEN"),
            data_dir=data_dir,
            environments=_environments(),
        )

    def for_environment(self, name: str | None) -> Settings:
        """These settings pointed at a named environment (None: unchanged)."""
        if not name:
            return self
        env = self.environments.get(name.lower())
        if env is None:
            known = ", ".join(sorted(self.environments)) or "none"
            raise ConfigError(
                f"environment {name!r} is not configured; set AUTOGRATION_{name.upper()}_API_URL "
                f"and AUTOGRATION_{name.upper()}_API_SCOPE in .env (configured: {known})"
            )
        return replace(self, api_url=env.api_url, api_scope=env.api_scope)

    @property
    def environment(self) -> str | None:
        """Name of the configured environment the API URL belongs to, if any."""
        for env in self.environments.values():
            if env.api_url == self.api_url:
                return env.name
        return None

    @property
    def web_url(self) -> str:
        """The web app's base URL (the API URL without ``/api/v1``)."""
        return re.sub(r"/api/v\d+$", "", self.api_url)

    @property
    def is_local(self) -> bool:
        return urlparse(self.api_url).hostname in {"localhost", "127.0.0.1", "::1"}

    def resolved_auth(self) -> str:
        if self.auth != "auto":
            return self.auth
        if self.token:
            return "token"
        return "none" if self.is_local else "browser"
