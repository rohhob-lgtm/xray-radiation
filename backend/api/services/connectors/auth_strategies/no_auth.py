"""
NoAuthStrategy — for connectors with no remote credential at all (local
folders, mounted NAS shares). "Connecting" just means configuring which
path to expose; there is nothing to encrypt for secrecy, but it is stored
through the same encrypted credential_store as everything else so the
storage layer stays uniform across every connector.
"""
from __future__ import annotations

from typing import Optional

from sqlalchemy.orm import Session

from ..manifest import AuthStrategyType
from ..credential_store import save_credentials, load_credentials
from .base import AuthStrategy, AuthInitiation, CredentialResult, AuthContext


class NoAuthStrategy(AuthStrategy):
    strategy_type = AuthStrategyType.NO_AUTH

    def __init__(self, config_fields: Optional[list[dict]] = None):
        self._config_fields = config_fields or [
            {"name": "root_path", "label": "Folder Path", "type": "text", "required": True},
        ]

    async def initiate(self, db: Session, user_id: str, connector_row) -> AuthInitiation:
        return AuthInitiation(success=True, mode="form", credential_fields=self._config_fields)

    async def complete(self, db: Session, user_id: str, connector_row, payload: dict) -> CredentialResult:
        config = {f["name"]: payload.get(f["name"]) for f in self._config_fields}
        missing = [f["name"] for f in self._config_fields if f.get("required") and not config.get(f["name"])]
        if missing:
            return CredentialResult(success=False, error_code="MISSING_FIELDS",
                                     error_message=f"Missing required field(s): {', '.join(missing)}")
        save_credentials(db, user_id, connector_row.id, config)
        return CredentialResult(success=True)

    async def refresh(self, db: Session, user_id: str, connector_row) -> CredentialResult:
        return CredentialResult(success=True)  # nothing expires

    async def revoke(self, db: Session, user_id: str, connector_row) -> bool:
        return True  # nothing remote to revoke; local config removal always succeeds

    async def build_auth_context(self, db: Session, user_id: str, connector_row) -> Optional[AuthContext]:
        stored = load_credentials(db, user_id, connector_row.id)
        if not stored:
            return None
        return AuthContext(extra=stored)
