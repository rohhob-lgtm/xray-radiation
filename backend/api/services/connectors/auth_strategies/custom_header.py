"""
CustomHeaderAuthStrategy — for arbitrary REST APIs where the user supplies
whatever header(s) that API needs (e.g. "X-Api-Key: ...", a custom bearer
scheme, etc). This is the escape hatch the "Custom REST APIs" requirement
maps to: no code changes needed to support a new custom API, only a new
Connector row + a user-supplied header set.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..manifest import AuthStrategyType
from ..credential_store import save_credentials, load_credentials
from .base import AuthStrategy, AuthInitiation, CredentialResult, AuthContext

_MAX_CUSTOM_HEADERS = 10


class CustomHeaderAuthStrategy(AuthStrategy):
    strategy_type = AuthStrategyType.CUSTOM_HEADER

    async def initiate(self, db: Session, user_id: str, connector_row) -> AuthInitiation:
        return AuthInitiation(
            success=True, mode="form",
            credential_fields=[
                {"name": "base_url", "label": "API Base URL", "type": "text", "required": True},
                {"name": "headers", "label": "Headers (name: value, one per line)", "type": "textarea", "required": True},
            ],
        )

    async def complete(self, db: Session, user_id: str, connector_row, payload: dict) -> CredentialResult:
        base_url = (payload.get("base_url") or "").strip()
        raw_headers = payload.get("headers") or ""
        if not base_url:
            return CredentialResult(success=False, error_code="MISSING_FIELDS", error_message="base_url is required")

        headers: dict[str, str] = {}
        for line in raw_headers.splitlines():
            if ":" not in line:
                continue
            name, _, value = line.partition(":")
            name, value = name.strip(), value.strip()
            if name:
                headers[name] = value
        if not headers:
            return CredentialResult(success=False, error_code="MISSING_FIELDS", error_message="At least one header is required")
        if len(headers) > _MAX_CUSTOM_HEADERS:
            return CredentialResult(success=False, error_code="TOO_MANY_HEADERS",
                                     error_message=f"At most {_MAX_CUSTOM_HEADERS} headers are supported")

        save_credentials(db, user_id, connector_row.id, {"base_url": base_url, "headers": headers})
        return CredentialResult(success=True)

    async def refresh(self, db: Session, user_id: str, connector_row) -> CredentialResult:
        stored = load_credentials(db, user_id, connector_row.id)
        if not stored:
            return CredentialResult(success=False, error_code="NOT_CONNECTED")
        return CredentialResult(success=True)

    async def revoke(self, db: Session, user_id: str, connector_row) -> bool:
        return False  # revocation is API-specific and out of band

    async def build_auth_context(self, db: Session, user_id: str, connector_row) -> Optional[AuthContext]:
        stored = load_credentials(db, user_id, connector_row.id)
        if not stored:
            return None
        return AuthContext(headers=stored.get("headers", {}), extra={"base_url": stored.get("base_url")})
