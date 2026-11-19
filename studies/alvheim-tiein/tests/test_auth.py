from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any

import pytest
from azure.core.exceptions import ClientAuthenticationError

from alvheim_tiein.auth import CredentialToken, SignInError


class Credential:
    def __init__(self, *outcomes: Any) -> None:
        self.outcomes = list(outcomes)
        self.calls = 0

    def get_token(self, scope: str) -> Any:
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_offline_sign_in_is_a_sign_in_error_and_the_next_call_retries() -> None:
    good = SimpleNamespace(token="abc", expires_on=time.time() + 3600)
    credential = Credential(ClientAuthenticationError("getaddrinfo failed"), good)
    provider = CredentialToken(credential, "api://x/access_as_user")
    with pytest.raises(SignInError, match="getaddrinfo failed"):
        provider()
    assert provider() == "abc"
    assert provider() == "abc"
    assert credential.calls == 2
