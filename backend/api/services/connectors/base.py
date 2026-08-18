"""
PlatformConnector — the contract every connector implements, regardless of
category (design tool, file storage, code repo, ...) or auth mechanism.

A connector composes an AuthStrategy rather than implementing auth itself:
connect/disconnect/get_connection_status/refresh_connection are thin,
strategy-agnostic wrappers here; only execute_action (and, for connectors
that declare support, health_check/sync) is connector-specific.
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.db import crud

from .manifest import ConnectorManifest
from .credential_store import (
    save_credentials, clear_credentials, mark_status, mark_successful_action,
)
from .auth_strategies.base import AuthStrategy, AuthInitiation, CredentialResult

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ── Result shapes ────────────────────────────────────────────────────────────

@dataclass
class ConnectionStatus:
    provider: str
    connection_status: str  # connected | disconnected | error | expired
    external_account_email: Optional[str] = None
    granted_scopes: list[str] = field(default_factory=list)
    last_connected_at: Optional[datetime] = None
    last_successful_action_at: Optional[datetime] = None
    error_message: Optional[str] = None


@dataclass
class TokenResult:
    success: bool
    token_expiry: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class ConnectorActionResult:
    success: bool
    action: str = ""
    data: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class HealthStatus:
    healthy: bool
    checked_at: datetime = field(default_factory=_now)
    detail: Optional[str] = None


@dataclass
class SyncResult:
    success: bool
    items_synced: int = 0
    next_cursor: Optional[dict[str, Any]] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


# ── Connector contract ───────────────────────────────────────────────────────

class PlatformConnector(ABC):
    manifest: ConnectorManifest
    auth_strategy: AuthStrategy

    def _connector_row(self, db: Session):
        row = crud.get_connector_by_provider(db, self.manifest.provider)
        if row is None:
            raise RuntimeError(
                f"Connector row for provider '{self.manifest.provider}' is missing — seed did not run"
            )
        return row

    # ── Lifecycle (strategy-delegated — do not override in subclasses) ─────

    async def connect(self, db: Session, user_id: str) -> AuthInitiation:
        return await self.auth_strategy.initiate(db, user_id, self._connector_row(db))

    async def complete_connection(self, db: Session, user_id: str, payload: dict) -> CredentialResult:
        connector_row = self._connector_row(db)
        result = await self.auth_strategy.complete(db, user_id, connector_row, payload)
        if result.success:
            await self.on_connected(db, user_id)
        return result

    async def disconnect(self, db: Session, user_id: str) -> None:
        connector_row = self._connector_row(db)
        try:
            await self.auth_strategy.revoke(db, user_id, connector_row)
        except Exception:
            log.warning("Revoke failed for provider=%s user=%s — clearing local state anyway",
                        self.manifest.provider, user_id, exc_info=True)
        clear_credentials(db, user_id, connector_row.id)

    async def get_connection_status(self, db: Session, user_id: str) -> ConnectionStatus:
        connector_row = crud.get_connector_by_provider(db, self.manifest.provider)
        if connector_row is None:
            return ConnectionStatus(provider=self.manifest.provider, connection_status="disconnected")
        account = crud.get_user_connector_account(db, user_id, connector_row.id)
        if not account:
            return ConnectionStatus(provider=self.manifest.provider, connection_status="disconnected")
        return ConnectionStatus(
            provider=self.manifest.provider,
            connection_status=account.connection_status,
            external_account_email=account.external_account_email,
            granted_scopes=account.granted_scopes or [],
            last_connected_at=account.last_connected_at,
            last_successful_action_at=account.last_successful_action_at,
            error_message=account.last_error,
        )

    async def refresh_connection(self, db: Session, user_id: str) -> TokenResult:
        connector_row = self._connector_row(db)
        result = await self.auth_strategy.refresh(db, user_id, connector_row)
        if not result.success:
            mark_status(db, user_id, connector_row.id, connection_status="error",
                        error_message=result.error_message)
            return TokenResult(success=False, error_code=result.error_code, error_message=result.error_message)
        mark_status(db, user_id, connector_row.id, connection_status="connected")
        return TokenResult(success=True, token_expiry=result.token_expiry)

    # ── Connector-specific ──────────────────────────────────────────────────

    @abstractmethod
    async def execute_action(
        self, db: Session, user_id: str, action: str, parameters: dict[str, Any]
    ) -> ConnectorActionResult:
        """Perform one capability declared in self.manifest.capabilities."""

    async def on_connected(self, db: Session, user_id: str) -> None:
        """Optional post-connect hook (e.g. fetch a display name for the account label).

        Kept out of AuthStrategy so OAuth2PkceAuthStrategy stays free of any
        per-provider API knowledge — only connectors that need this override it.
        """
        return None

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        if not self.manifest.supports_health_check:
            return HealthStatus(healthy=False, detail="Connector does not support health checks")
        return HealthStatus(healthy=False, detail="health_check not implemented")

    async def sync(self, db: Session, user_id: str, cursor: dict[str, Any]) -> SyncResult:
        if not self.manifest.supports_sync:
            return SyncResult(success=False, error_code="SYNC_NOT_SUPPORTED")
        return SyncResult(success=False, error_code="SYNC_NOT_IMPLEMENTED")

    # ── Shared helpers for execute_action implementations ───────────────────

    async def _mark_action_success(self, db: Session, user_id: str) -> None:
        connector_row = self._connector_row(db)
        mark_successful_action(db, user_id, connector_row.id)

    async def _get_bearer_token(self, db: Session, user_id: str) -> Optional[str]:
        """For OAuth2-strategy connectors: the stored access token, or None if not connected."""
        connector_row = self._connector_row(db)
        ctx = await self.auth_strategy.build_auth_context(db, user_id, connector_row)
        if not ctx or "Authorization" not in ctx.headers:
            return None
        return ctx.headers["Authorization"].removeprefix("Bearer ")
