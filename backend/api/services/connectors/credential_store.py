"""
Shared credential storage — every AuthStrategy reads/writes credentials
through this module instead of touching encryption or the DB row directly.
Keeping this in one place means there is exactly one place that encrypts,
one place that decrypts, and one place that enforces per-user isolation,
regardless of which of the 6 auth strategies produced the credential.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.db import crud
from api.utils.crypto import encrypt_secret, decrypt_secret

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def save_credentials(
    db: Session,
    user_id: str,
    connector_id: str,
    credentials: dict[str, Any],
    *,
    granted_scopes: Optional[list[str]] = None,
    token_expiry: Optional[datetime] = None,
    external_account_label: Optional[str] = None,
    connection_status: str = "connected",
) -> None:
    crud.upsert_user_connector_account(
        db,
        user_id=user_id,
        connector_id=connector_id,
        encrypted_credentials=encrypt_secret(json.dumps(credentials)),
        granted_scopes=granted_scopes or [],
        token_expiry=token_expiry,
        external_account_email=external_account_label,
        connection_status=connection_status,
        last_error=None,
        last_connected_at=_now(),
    )


def load_credentials(db: Session, user_id: str, connector_id: str) -> Optional[dict[str, Any]]:
    """Scoped to user_id via crud.get_user_connector_account — the enforcement
    point that stops one user from ever reading another user's credentials."""
    account = crud.get_user_connector_account(db, user_id, connector_id)
    if not account or not account.encrypted_credentials:
        return None
    raw = decrypt_secret(account.encrypted_credentials)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        log.warning("Stored credentials for connector_id=%s are not valid JSON", connector_id)
        return None


def mark_status(
    db: Session,
    user_id: str,
    connector_id: str,
    *,
    connection_status: str,
    error_message: Optional[str] = None,
) -> None:
    crud.upsert_user_connector_account(
        db, user_id=user_id, connector_id=connector_id,
        connection_status=connection_status, last_error=error_message,
    )


def mark_successful_action(db: Session, user_id: str, connector_id: str) -> None:
    crud.upsert_user_connector_account(
        db, user_id=user_id, connector_id=connector_id,
        last_successful_action_at=_now(),
    )


def clear_credentials(db: Session, user_id: str, connector_id: str) -> bool:
    return crud.delete_user_connector_account(db, user_id, connector_id)
