"""Bearer tokens for the Autogration API.

The backend accepts Entra tokens for scope ``api://<app-id>/access_as_user`` that were
issued to an allowed client app. The Azure CLI's public client is allowed by default
(``ALLOWED_CLIENT_APPS``) and is also azure-identity's default client id, so browser and
device-code sign-in here need no app registration of their own. ``GET
/users/me/api-access`` on the deployed API shows the scope to use.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from alvheim_tiein.config import ConfigError, Settings

TokenProvider = Callable[[], str]
CACHE_NAME = "alvheim-tiein"
_REFRESH_MARGIN_S = 120


def _record_file(mode: str) -> Path:
    return Path.home() / ".alvheim-tiein" / f"auth-record-{mode}.json"


class StaticToken:
    def __init__(self, token: str) -> None:
        self._token = token.removeprefix("Bearer ").strip()

    def __call__(self) -> str:
        return self._token


class CredentialToken:
    """Caches an azure-identity access token until shortly before it expires."""

    def __init__(self, credential: Any, scope: str) -> None:
        self._credential = credential
        self._scope = scope
        self._token: Any = None

    def __call__(self) -> str:
        if self._token is None or self._token.expires_on - _REFRESH_MARGIN_S < time.time():
            self._token = self._credential.get_token(self._scope)
        return self._token.token


def _signed_in_credential(mode: str, settings: Settings, scope: str) -> Any:
    from azure.identity import (
        AuthenticationRecord,
        DeviceCodeCredential,
        InteractiveBrowserCredential,
        TokenCachePersistenceOptions,
    )

    if not settings.tenant_id:
        raise ConfigError("AZURE_TENANT_ID is needed for browser or device-code sign-in")
    record_file = _record_file(mode)
    record = (
        AuthenticationRecord.deserialize(record_file.read_text(encoding="utf-8"))
        if record_file.exists()
        else None
    )
    kind = InteractiveBrowserCredential if mode == "browser" else DeviceCodeCredential
    credential = kind(
        tenant_id=settings.tenant_id,
        cache_persistence_options=TokenCachePersistenceOptions(name=CACHE_NAME),
        authentication_record=record,
    )
    if record is None:
        record = credential.authenticate(scopes=[scope])
        record_file.parent.mkdir(parents=True, exist_ok=True)
        record_file.write_text(record.serialize(), encoding="utf-8")
    return credential


def token_provider(settings: Settings) -> TokenProvider | None:
    """The token source for the configured auth mode, or None for an unauthenticated
    local backend."""
    mode = settings.resolved_auth()
    if mode == "none":
        return None
    if mode == "token":
        if not settings.token:
            raise ConfigError("AUTOGRATION_AUTH=token but AUTOGRATION_TOKEN is empty")
        return StaticToken(settings.token)
    if not settings.api_scope:
        raise ConfigError(
            "AUTOGRATION_API_SCOPE is empty. Open <web app>/api/v1/users/me/api-access in a "
            "signed-in browser and copy token_scope into the study's .env"
        )
    if mode == "azure-cli":
        from azure.identity import AzureCliCredential

        return CredentialToken(AzureCliCredential(tenant_id=settings.tenant_id), settings.api_scope)
    return CredentialToken(
        _signed_in_credential(mode, settings, settings.api_scope), settings.api_scope
    )
