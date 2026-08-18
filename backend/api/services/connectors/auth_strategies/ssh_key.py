"""SshKeyAuthStrategy — key-based SFTP auth (preferred over BasicAuthStrategy's password form for SFTP/NAS)."""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..manifest import AuthStrategyType
from ..credential_store import save_credentials, load_credentials
from .base import AuthStrategy, AuthInitiation, CredentialResult, AuthContext


class SshKeyAuthStrategy(AuthStrategy):
    strategy_type = AuthStrategyType.SSH_KEY

    async def initiate(self, db: Session, user_id: str, connector_row) -> AuthInitiation:
        return AuthInitiation(
            success=True, mode="form",
            credential_fields=[
                {"name": "username", "label": "Username", "type": "text", "required": True},
                {"name": "host", "label": "Host", "type": "text", "required": True},
                {"name": "port", "label": "Port", "type": "number", "required": False},
                {"name": "private_key", "label": "SSH Private Key", "type": "textarea", "required": True},
                {"name": "passphrase", "label": "Key Passphrase", "type": "password", "required": False},
            ],
        )

    async def complete(self, db: Session, user_id: str, connector_row, payload: dict) -> CredentialResult:
        username = (payload.get("username") or "").strip()
        host = (payload.get("host") or "").strip()
        private_key = payload.get("private_key") or ""
        if not username or not host or not private_key:
            return CredentialResult(success=False, error_code="MISSING_FIELDS",
                                     error_message="username, host, and private_key are required")
        save_credentials(db, user_id, connector_row.id, {
            "username": username, "host": host, "port": payload.get("port"),
            "private_key": private_key, "passphrase": payload.get("passphrase"),
        })
        return CredentialResult(success=True)

    async def refresh(self, db: Session, user_id: str, connector_row) -> CredentialResult:
        stored = load_credentials(db, user_id, connector_row.id)
        if not stored or not stored.get("private_key"):
            return CredentialResult(success=False, error_code="NOT_CONNECTED")
        return CredentialResult(success=True)

    async def revoke(self, db: Session, user_id: str, connector_row) -> bool:
        return False  # key revocation happens on the remote server, out of band

    async def build_auth_context(self, db: Session, user_id: str, connector_row) -> Optional[AuthContext]:
        stored = load_credentials(db, user_id, connector_row.id)
        if not stored or not stored.get("private_key"):
            return None
        return AuthContext(extra={
            "username": stored.get("username"), "host": stored.get("host"), "port": stored.get("port"),
            "private_key": stored.get("private_key"), "passphrase": stored.get("passphrase"),
        })
