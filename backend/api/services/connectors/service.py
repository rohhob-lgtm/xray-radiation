"""
Connector Service — the layer between transport (REST routes today, the AI
tool router later) and individual connector implementations.

Responsibilities: resolve the connector via the registry (refusing anything
unregistered/disabled), check the requesting user is actually connected
with the scopes the requested capability declares in its manifest, enforce
per-user rate limiting, execute the action, and record a sanitized
ConnectorEvent — so every caller gets the same guarantees no matter what
triggered the call.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from api.db import crud

from .base import ConnectorActionResult
from .events import log_event
from .rate_limit import check_rate_limit, RateLimitExceededError
from .registry import connector_registry, ConnectorNotRegisteredError

log = logging.getLogger(__name__)


class ConnectorService:
    async def execute_action(
        self, db: Session, user_id: str, provider: str, action: str, parameters: dict[str, Any]
    ) -> ConnectorActionResult:
        connector_row = crud.get_connector_by_provider(db, provider)
        if connector_row is None or not connector_row.enabled:
            return ConnectorActionResult(
                success=False, action=action, error_code="PROVIDER_DISABLED",
                error_message=f"Connector '{provider}' is not enabled",
            )

        try:
            connector = connector_registry.get(provider)
        except ConnectorNotRegisteredError as exc:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_REGISTERED", error_message=str(exc))

        capability = connector.manifest.get_capability(action)
        if capability is None:
            return ConnectorActionResult(
                success=False, action=action, error_code="UNKNOWN_ACTION",
                error_message=f"'{action}' is not a declared capability of '{provider}'",
            )
        if not capability.is_implemented:
            return ConnectorActionResult(
                success=False, action=action, error_code="NOT_IMPLEMENTED",
                error_message=f"'{action}' is declared but not implemented yet",
            )

        account = crud.get_user_connector_account(db, user_id, connector_row.id)
        if not account or account.connection_status != "connected":
            return ConnectorActionResult(
                success=False, action=action, error_code="NOT_CONNECTED",
                error_message=f"Connect your {connector_row.display_name} account to perform this action.",
            )
        missing_scopes = set(capability.required_scopes) - set(account.granted_scopes or [])
        if missing_scopes:
            return ConnectorActionResult(
                success=False, action=action, error_code="INSUFFICIENT_SCOPE",
                error_message=f"Missing required scope(s): {', '.join(sorted(missing_scopes))}",
            )

        # Transparent refresh — generic to any connector whose credentials
        # expire (mainly OAuth2), not something each connector re-implements.
        # SQLite doesn't round-trip tzinfo, so a value read back from it is
        # naive even though it was stored as UTC — normalize before comparing.
        expiry = account.token_expiry
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if expiry and expiry <= datetime.now(timezone.utc) + timedelta(seconds=30):
            refreshed = await connector.refresh_connection(db, user_id)
            if not refreshed.success:
                return ConnectorActionResult(
                    success=False, action=action, error_code=refreshed.error_code or "REFRESH_FAILED",
                    error_message=refreshed.error_message,
                )

        try:
            check_rate_limit(user_id, provider)
        except RateLimitExceededError as exc:
            result = ConnectorActionResult(success=False, action=action, error_code="RATE_LIMITED", error_message=str(exc))
            log_event(
                db, user_id, connector_row.id, event_type="action", action=action, status="error",
                request_metadata=parameters, error_code=result.error_code, error_message=result.error_message,
            )
            return result

        try:
            result = await connector.execute_action(db, user_id, action, parameters)
        except Exception as exc:  # connector implementations should not raise, but never let one crash a route
            log.exception("Connector action raised unexpectedly: provider=%s action=%s", provider, action)
            result = ConnectorActionResult(success=False, action=action, error_code="INTERNAL_ERROR", error_message=str(exc))

        log_event(
            db, user_id, connector_row.id, event_type="action", action=action,
            status="success" if result.success else "error",
            request_metadata=parameters,
            response_metadata=result.data if result.success else None,
            error_code=result.error_code, error_message=result.error_message,
        )
        return result


connector_service = ConnectorService()
