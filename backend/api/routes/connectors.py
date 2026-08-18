"""
Generic, provider-agnostic connector routes. Every route is driven by the
registry + manifest — adding provider #18 to the framework never means
writing a new route here, only a new PlatformConnector + AuthStrategy
config registered in bootstrap.py.

OAuth2 connectors use GET /connect (browser redirect) + GET /callback.
Every other auth strategy uses GET /connect (returns a form schema) +
POST /credentials (submits the filled form) — no callback route needed.
"""
from __future__ import annotations

import logging
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db, crud
from api.middleware.auth import require_auth
from api.services.connectors.registry import connector_registry
from api.services.connectors.service import connector_service
from api.services.connectors.events import log_event
from api.services.connectors.bootstrap import register_all_connectors
from api.services.connectors.base import PlatformConnector
from api.services.drive_export import export_canva_design, upload_bytes_to_drive, sanitize_filename

# Which Settings fields (→ which env var names) each OAuth2 connector's
# app-level credentials come from. Used only to report *names* of missing
# variables in diagnostics — never values.
_OAUTH2_CREDENTIAL_ENV_VARS: dict[str, tuple[str, str]] = {
    "canva": ("CANVA_CLIENT_ID", "CANVA_CLIENT_SECRET"),
    "google_drive": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
    "gmail": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
    "google_calendar": ("GOOGLE_CLIENT_ID", "GOOGLE_CLIENT_SECRET"),
    "onedrive": ("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"),
    "sharepoint": ("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"),
    "teams": ("MICROSOFT_CLIENT_ID", "MICROSOFT_CLIENT_SECRET"),
    "dropbox": ("DROPBOX_CLIENT_ID", "DROPBOX_CLIENT_SECRET"),
    "confluence": ("ATLASSIAN_CLIENT_ID", "ATLASSIAN_CLIENT_SECRET"),
    "slack": ("SLACK_CLIENT_ID", "SLACK_CLIENT_SECRET"),
}
_OAUTH2_SETTINGS_FIELDS: dict[str, tuple[str, str]] = {
    "canva": ("canva_client_id", "canva_client_secret"),
    "google_drive": ("google_client_id", "google_client_secret"),
    "gmail": ("google_client_id", "google_client_secret"),
    "google_calendar": ("google_client_id", "google_client_secret"),
    "onedrive": ("microsoft_client_id", "microsoft_client_secret"),
    "sharepoint": ("microsoft_client_id", "microsoft_client_secret"),
    "teams": ("microsoft_client_id", "microsoft_client_secret"),
    "dropbox": ("dropbox_client_id", "dropbox_client_secret"),
    "confluence": ("atlassian_client_id", "atlassian_client_secret"),
    "slack": ("slack_client_id", "slack_client_secret"),
}

log = logging.getLogger(__name__)
router = APIRouter(prefix="/connectors", tags=["connectors"])

register_all_connectors(connector_registry)

_FRONTEND_ORIGIN = "http://127.0.0.1:5173"
_FRONTEND_CONNECTORS_URL = f"{_FRONTEND_ORIGIN}/connectors"
_SESSION_OAUTH_KEY = "connector_oauth"


def _safe_return_to(return_to: Optional[str]) -> Optional[str]:
    """Only ever accept a same-origin relative path — never redirect off-site
    based on client-supplied input (open-redirect prevention)."""
    if not return_to or not return_to.startswith("/") or return_to.startswith("//"):
        return None
    return return_to


def _redirect_target(pending: Optional[dict], **query: str) -> str:
    return_to = _safe_return_to((pending or {}).get("return_to"))
    base = f"{_FRONTEND_ORIGIN}{return_to}" if return_to else _FRONTEND_CONNECTORS_URL
    if not query:
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}{urlencode(query)}"


def _status_dict(status) -> dict:
    return {
        "connection_status": status.connection_status,
        "external_account_email": status.external_account_email,
        "granted_scopes": status.granted_scopes,
        "last_connected_at": status.last_connected_at.isoformat() if status.last_connected_at else None,
        "last_successful_action_at": status.last_successful_action_at.isoformat() if status.last_successful_action_at else None,
        "error_message": status.error_message,
    }


def _configured(connector: PlatformConnector) -> bool:
    try:
        return connector.auth_strategy.is_configured()
    except Exception:
        return False


def _get_enabled_connector(db: Session, provider: str) -> tuple[object, PlatformConnector]:
    """Returns (connector_row, connector_instance) or raises HTTPException."""
    connector_row = crud.get_connector_by_provider(db, provider)
    if connector_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector '{provider}'")
    if not connector_row.enabled or not connector_registry.is_registered(provider):
        raise HTTPException(status_code=400, detail={
            "error_code": "PROVIDER_DISABLED",
            "error_message": f"'{connector_row.display_name}' is not available yet.",
        })
    return connector_row, connector_registry.get(provider)


# ──────────────────────────────────────────────────────────
# Generic listing
# ──────────────────────────────────────────────────────────

@router.get("")
async def list_connectors(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    rows = crud.list_connectors(db)
    result = []
    for row in rows:
        entry = {
            "provider": row.provider,
            "display_name": row.display_name,
            "category": row.category,
            "auth_strategy_type": row.auth_strategy_type,
            "icon": row.icon,
            "enabled": row.enabled,
            "supports_sync": row.supports_sync,
            "supports_health_check": row.supports_health_check,
            "capabilities": row.capabilities,
            "configured": False,
            "connection_status": "disconnected",
            "external_account_email": None,
            "granted_scopes": [],
            "last_connected_at": None,
            "last_successful_action_at": None,
            "error_message": None,
        }
        if row.enabled and connector_registry.is_registered(row.provider):
            connector = connector_registry.get(row.provider)
            entry["configured"] = _configured(connector)
            status = await connector.get_connection_status(db, user["id"])
            entry.update(_status_dict(status))
        result.append(entry)
    return result


# ──────────────────────────────────────────────────────────
# Per-provider lifecycle
# ──────────────────────────────────────────────────────────

@router.get("/{provider}/status")
async def connector_status(provider: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _, connector = _get_enabled_connector(db, provider)
    status = await connector.get_connection_status(db, user["id"])
    return {"configured": _configured(connector), **_status_dict(status)}


@router.get("/{provider}/diagnostics")
async def connector_diagnostics(provider: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    """
    Setup-time diagnostics for the Connectors UI's "Setup Instructions"
    button. Reports which named env vars are missing and the exact
    callback URL to register — never the configured values themselves.
    """
    connector_row = crud.get_connector_by_provider(db, provider)
    if connector_row is None:
        raise HTTPException(status_code=404, detail=f"Unknown connector '{provider}'")

    missing_variables: list[str] = []
    callback_url: Optional[str] = None
    configured = False

    if connector_row.auth_strategy_type == "oauth2_pkce":
        callback_url = settings.connector_redirect_uri(provider)
        env_names = _OAUTH2_CREDENTIAL_ENV_VARS.get(provider)
        field_names = _OAUTH2_SETTINGS_FIELDS.get(provider)
        if env_names and field_names:
            client_id = getattr(settings, field_names[0], "")
            client_secret = getattr(settings, field_names[1], "")
            if not client_id:
                missing_variables.append(env_names[0])
            if not client_secret:
                missing_variables.append(env_names[1])
            configured = not missing_variables
    else:
        # Non-OAuth strategies (API key, SSH key, basic auth, no-auth,
        # custom header) have no app-level credential to be "missing" —
        # each user supplies their own at connect time.
        configured = True

    if connector_row.enabled and connector_registry.is_registered(provider):
        # Cross-check against the connector's own is_configured() so this
        # never drifts from what actually gates the Connect button.
        configured = configured and _configured(connector_registry.get(provider))

    return {
        "configured": configured,
        "missingVariables": missing_variables,
        "callbackUrl": callback_url,
        "backendPort": settings.port,
    }


@router.get("/{provider}/connect")
async def connector_connect(
    provider: str, request: Request, db: Session = Depends(get_db), user: dict = Depends(require_auth),
    return_to: Optional[str] = None,
):
    connector_row, connector = _get_enabled_connector(db, provider)
    result = await connector.connect(db, user["id"])
    if not result.success:
        return JSONResponse(status_code=400, content={
            "error_code": result.error_code, "error_message": result.error_message,
        })

    if result.mode == "redirect":
        # PKCE verifier + state live server-side only — never sent to the browser as a token.
        # return_to (e.g. "/chat?id=<conversation_id>&resume_pending=1") lets any
        # calling page — not just the Connectors page — bring the user back to
        # itself after OAuth completes, instead of always landing on /connectors.
        request.session[_SESSION_OAUTH_KEY] = {
            "provider": provider, "state": result.oauth_state,
            "verifier": result.pkce_verifier, "user_id": user["id"],
            "return_to": _safe_return_to(return_to),
        }
        return RedirectResponse(url=result.authorize_url)

    return {"mode": "form", "fields": result.credential_fields}


@router.post("/{provider}/credentials")
async def connector_submit_credentials(
    provider: str, body: dict, db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    connector_row, connector = _get_enabled_connector(db, provider)
    result = await connector.complete_connection(db, user["id"], body)
    if not result.success:
        raise HTTPException(status_code=400, detail={
            "error_code": result.error_code, "error_message": result.error_message,
        })
    log_event(db, user["id"], connector_row.id, event_type="auth", status="success", action="connect")
    return {"status": "connected"}


@router.get("/{provider}/callback")
async def connector_oauth_callback(
    provider: str, request: Request,
    code: Optional[str] = None, state: Optional[str] = None, error: Optional[str] = None,
    db: Session = Depends(get_db),
):
    pending = request.session.pop(_SESSION_OAUTH_KEY, None)

    if error:
        return RedirectResponse(url=_redirect_target(pending, connector=provider, error=error))

    if (
        not pending or pending.get("provider") != provider
        or not state or state != pending.get("state") or not pending.get("verifier")
    ):
        log.warning("OAuth callback rejected for provider=%s: invalid or missing state", provider)
        return RedirectResponse(url=_redirect_target(pending, connector=provider, error="invalid_state"))

    if not code:
        return RedirectResponse(url=_redirect_target(pending, connector=provider, error="missing_code"))

    connector_row = crud.get_connector_by_provider(db, provider)
    if connector_row is None or not connector_registry.is_registered(provider):
        return RedirectResponse(url=_redirect_target(pending, connector=provider, error="unknown_connector"))
    connector = connector_registry.get(provider)

    user_id = pending["user_id"]
    result = await connector.complete_connection(db, user_id, {"code": code, "code_verifier": pending["verifier"]})
    if not result.success:
        log_event(db, user_id, connector_row.id, event_type="auth", status="error", action="connect",
                   error_code=result.error_code, error_message=result.error_message)
        return RedirectResponse(url=_redirect_target(pending, connector=provider, error=result.error_code or "connect_failed"))

    log_event(db, user_id, connector_row.id, event_type="auth", status="success", action="connect")
    return RedirectResponse(url=_redirect_target(pending, connected=provider))


@router.post("/{provider}/disconnect")
async def connector_disconnect(provider: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    connector_row, connector = _get_enabled_connector(db, provider)
    await connector.disconnect(db, user["id"])
    log_event(db, user["id"], connector_row.id, event_type="auth", status="success", action="disconnect")
    return {"status": "disconnected"}


# ──────────────────────────────────────────────────────────
# Actions / sync / health
# ──────────────────────────────────────────────────────────

@router.post("/{provider}/actions")
async def connector_action(
    provider: str, body: dict, db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    action = body.get("action")
    if not action:
        raise HTTPException(status_code=400, detail="Missing 'action'")
    parameters = body.get("parameters") or {}
    result = await connector_service.execute_action(db, user["id"], provider, action, parameters)
    if not result.success:
        status_code = {
            "NOT_CONNECTED": 401, "UNKNOWN_ACTION": 404, "NOT_IMPLEMENTED": 400,
            "INSUFFICIENT_SCOPE": 403, "RATE_LIMITED": 429,
        }.get(result.error_code, 502)
        raise HTTPException(status_code=status_code, detail={
            "error_code": result.error_code, "error_message": result.error_message,
        })
    return {"success": True, "action": result.action, "data": result.data}


@router.post("/canva/{design_id}/save-to-drive")
async def canva_save_to_drive(
    design_id: str, body: dict, db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    """
    Chains two connectors server-side (export via Canva, then upload to
    Google Drive) — the one action in the AI Tool Router's design workflow
    that genuinely needs a dedicated route instead of the generic
    /{provider}/actions dispatcher, since no single connector call can do
    both halves. Both halves still go through connector_service.execute_action,
    so scope/connection enforcement and audit logging apply exactly as for
    every other connector action.
    """
    export_format = body.get("format", "png")
    if export_format not in ("png", "pdf"):
        raise HTTPException(status_code=400, detail={"error_code": "INVALID_FORMAT", "error_message": "format must be 'png' or 'pdf'"})

    outcome = await export_canva_design(db, user["id"], design_id, export_format)
    if not outcome.success:
        status_code = {"NOT_CONNECTED": 401, "INSUFFICIENT_SCOPE": 403, "RATE_LIMITED": 429}.get(outcome.error_code, 502)
        raise HTTPException(status_code=status_code, detail={
            "error_code": outcome.error_code, "error_message": outcome.error_message,
        })

    title = body.get("title") or f"canva-design-{design_id}"
    filename = f"{sanitize_filename(title)}.{export_format}"
    drive_result = await upload_bytes_to_drive(
        db, user["id"], filename, outcome.content_bytes, outcome.mime_type, body.get("folder_id"),
    )
    if not drive_result.success:
        status_code = {"NOT_CONNECTED": 401, "INSUFFICIENT_SCOPE": 403, "RATE_LIMITED": 429}.get(drive_result.error_code, 502)
        raise HTTPException(status_code=status_code, detail={
            "error_code": drive_result.error_code, "error_message": drive_result.error_message,
        })
    return {"success": True, "file": drive_result.data}


@router.post("/{provider}/sync")
async def connector_sync(provider: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    connector_row, connector = _get_enabled_connector(db, provider)
    if not connector.manifest.supports_sync:
        raise HTTPException(status_code=400, detail={
            "error_code": "SYNC_NOT_SUPPORTED", "error_message": f"'{provider}' does not support sync",
        })
    state = crud.get_connector_sync_state(db, user["id"], connector_row.id)
    cursor = (state.cursor if state else {}) or {}
    result = await connector.sync(db, user["id"], cursor)
    status = "success" if result.success else "error"
    crud.upsert_connector_sync_state(
        db, user_id=user["id"], connector_id=connector_row.id,
        cursor=result.next_cursor or cursor, last_sync_status=status,
        last_sync_error=result.error_message,
    )
    log_event(db, user["id"], connector_row.id, event_type="sync", status=status, action="manual_sync",
              error_code=result.error_code, error_message=result.error_message)
    if not result.success:
        raise HTTPException(status_code=502, detail={"error_code": result.error_code, "error_message": result.error_message})
    return {"success": True, "items_synced": result.items_synced}


@router.get("/{provider}/health")
async def connector_health(provider: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    connector_row, connector = _get_enabled_connector(db, provider)
    if not connector.manifest.supports_health_check:
        raise HTTPException(status_code=400, detail={
            "error_code": "HEALTH_CHECK_NOT_SUPPORTED", "error_message": f"'{provider}' does not support health checks",
        })
    result = await connector.health_check(db, user["id"])
    log_event(db, user["id"], connector_row.id, event_type="health",
              status="success" if result.healthy else "error", error_message=result.detail)
    return {"healthy": result.healthy, "checked_at": result.checked_at.isoformat(), "detail": result.detail}


@router.post("/{provider}/test")
async def connector_test(provider: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    """
    'Test Connection' button — makes one real, live call against the
    provider's API (via health_check, which every connector implements as
    a genuine authenticated request, not a local-only check) and reports
    exactly what came back. Never fabricates success.
    """
    connector_row, connector = _get_enabled_connector(db, provider)
    if not connector.manifest.supports_health_check:
        raise HTTPException(status_code=400, detail={
            "error_code": "TEST_NOT_SUPPORTED", "error_message": f"'{provider}' does not support connection testing",
        })
    result = await connector.health_check(db, user["id"])
    status = "success" if result.healthy else "error"
    log_event(db, user["id"], connector_row.id, event_type="health", action="test",
              status=status, error_message=result.detail)
    return {"success": result.healthy, "checked_at": result.checked_at.isoformat(), "detail": result.detail}
