"""
ApiKeyAuthStrategy — for providers authenticated with a single static token
sent as a header (GitHub/GitLab personal access tokens, Notion internal
integration tokens, etc). No OAuth redirect — the frontend renders a form
field and POSTs the key.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy.orm import Session

from ..manifest import AuthStrategyType
from ..credential_store import save_credentials, load_credentials
from .base import AuthStrategy, AuthInitiation, CredentialResult, AuthContext


@dataclass(frozen=True)
class ApiKeyConfig:
    header_name: str = "Authorization"
    header_format: str = "Bearer {key}"  # {key} substituted with the stored value
    field_label: str = "API Key"


class ApiKeyAuthStrategy(AuthStrategy):
    strategy_type = AuthStrategyType.API_KEY

    def __init__(self, config: ApiKeyConfig):
        self._config = config

    async def initiate(self, db: Session, user_id: str, connector_row) -> AuthInitiation:
        return AuthInitiation(
            success=True, mode="form",
            credential_fields=[
                {"name": "api_key", "label": self._config.field_label, "type": "password", "required": True},
            ],
        )

    async def complete(self, db: Session, user_id: str, connector_row, payload: dict) -> CredentialResult:
        api_key = (payload.get("api_key") or "").strip()
        if not api_key:
            return CredentialResult(success=False, error_code="MISSING_API_KEY", error_message="API key is required")
        save_credentials(db, user_id, connector_row.id, {"api_key": api_key})
        return CredentialResult(success=True)

    async def refresh(self, db: Session, user_id: str, connector_row) -> CredentialResult:
        # Static keys don't expire/refresh — treat as always-valid as long as one is stored.
        stored = load_credentials(db, user_id, connector_row.id)
        if not stored or not stored.get("api_key"):
            return CredentialResult(success=False, error_code="NOT_CONNECTED")
        return CredentialResult(success=True)

    async def revoke(self, db: Session, user_id: str, connector_row) -> bool:
        # No remote revocation endpoint exists for a static key in general —
        # the user must revoke it on the provider's side. Local state is
        # still cleared by PlatformConnector.disconnect() regardless.
        return False

    async def build_auth_context(self, db: Session, user_id: str, connector_row) -> Optional[AuthContext]:
        stored = load_credentials(db, user_id, connector_row.id)
        api_key = (stored or {}).get("api_key")
        if not api_key:
            return None
        header_value = self._config.header_format.format(key=api_key)
        return AuthContext(headers={self._config.header_name: header_value})
