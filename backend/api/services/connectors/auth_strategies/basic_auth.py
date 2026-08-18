"""BasicAuthStrategy — username/password (SFTP without SSH keys, some legacy REST APIs)."""
from __future__ import annotations

import base64
from typing import Optional

from sqlalchemy.orm import Session

from ..manifest import AuthStrategyType
from ..credential_store import save_credentials, load_credentials
from .base import AuthStrategy, AuthInitiation, CredentialResult, AuthContext


class BasicAuthStrategy(AuthStrategy):
    strategy_type = AuthStrategyType.BASIC_AUTH

    async def initiate(self, db: Session, user_id: str, connector_row) -> AuthInitiation:
        return AuthInitiation(
            success=True, mode="form",
            credential_fields=[
                {"name": "username", "label": "Username", "type": "text", "required": True},
                {"name": "password", "label": "Password", "type": "password", "required": True},
                {"name": "host", "label": "Host", "type": "text", "required": True},
                {"name": "port", "label": "Port", "type": "number", "required": False},
            ],
        )

    async def complete(self, db: Session, user_id: str, connector_row, payload: dict) -> CredentialResult:
        username = (payload.get("username") or "").strip()
        password = payload.get("password") or ""
        host = (payload.get("host") or "").strip()
        if not username or not password or not host:
            return CredentialResult(success=False, error_code="MISSING_FIELDS",
                                     error_message="username, password, and host are required")
        save_credentials(db, user_id, connector_row.id, {
            "username": username, "password": password, "host": host, "port": payload.get("port"),
        })
        return CredentialResult(success=True)

    async def refresh(self, db: Session, user_id: str, connector_row) -> CredentialResult:
        stored = load_credentials(db, user_id, connector_row.id)
        if not stored or not stored.get("password"):
            return CredentialResult(success=False, error_code="NOT_CONNECTED")
        return CredentialResult(success=True)

    async def revoke(self, db: Session, user_id: str, connector_row) -> bool:
        return False  # nothing remote to revoke for username/password

    async def build_auth_context(self, db: Session, user_id: str, connector_row) -> Optional[AuthContext]:
        stored = load_credentials(db, user_id, connector_row.id)
        if not stored or not stored.get("password"):
            return None
        raw = f"{stored['username']}:{stored['password']}".encode("utf-8")
        return AuthContext(
            headers={"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"},
            extra={"host": stored.get("host"), "port": stored.get("port")},
        )
