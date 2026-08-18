"""Sanitized connector event logging — action | sync | health | auth."""
from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from api.db import crud

_SECRET_KEYS = {
    "access_token", "refresh_token", "api_key", "password", "private_key",
    "passphrase", "encrypted_credentials", "code", "code_verifier", "headers",
    "ssh_private_key",
}


def sanitize(payload: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Strip anything that looks like a credential before it is ever logged."""
    if not payload:
        return payload
    return {k: ("<redacted>" if k in _SECRET_KEYS else v) for k, v in payload.items()}


def log_event(
    db: Session,
    user_id: Optional[str],
    connector_id: Optional[str],
    *,
    event_type: str,
    status: str,
    action: str = "",
    request_metadata: Optional[dict] = None,
    response_metadata: Optional[dict] = None,
    error_code: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    crud.create_connector_event(
        db, user_id=user_id, connector_id=connector_id, event_type=event_type, action=action,
        status=status, request_metadata=sanitize(request_metadata), response_metadata=sanitize(response_metadata),
        error_code=error_code, error_message=error_message,
    )
