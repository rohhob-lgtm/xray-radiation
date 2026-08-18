"""
Authentication routes using Replit OIDC (OpenID Connect with PKCE).

Flow:
  GET /api/login      → redirect to Replit OIDC provider
  GET /api/callback   → handle OIDC callback, create session, redirect to app
  GET /api/logout     → clear session, redirect home
  GET /api/auth/user  → return current user from session
"""
from __future__ import annotations
import os
import logging

from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse, JSONResponse
from authlib.integrations.starlette_client import OAuth
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.db.crud import upsert_user

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# ──────────────────────────────────────────────────────────
# OAuth / OIDC setup
# ──────────────────────────────────────────────────────────

oauth = OAuth()
oauth.register(
    name="replit",
    server_metadata_url="https://replit.com/oidc/.well-known/openid-configuration",
    client_id=settings.repl_id or os.environ.get("REPL_ID", ""),
    client_kwargs={
        "scope": "openid profile email",
        "code_challenge_method": "S256",
    },
)

# Google sign-in — registered only when credentials are present, so the app runs
# fine before they are set (the tiered free-quota model stays off until then).
_google_ready = bool(settings.google_client_id and settings.google_client_secret)
if _google_ready:
    oauth.register(
        name="google",
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        client_kwargs={"scope": "openid email profile"},
    )


def _google_redirect_uri(request: Request) -> str:
    base = (settings.public_base_url or "").rstrip("/")
    if base:
        return f"{base}/api/auth/google/callback"
    return str(request.url_for("google_callback"))


@router.get("/auth/config")
async def auth_config():
    """Public flags the SPA uses to decide whether to show sign-in / quotas."""
    return {
        "auth_enabled": settings.auth_enabled,
        "google_available": _google_ready,
        "anon_free": settings.anon_free_translations,
        "account_free": settings.account_free_translations,
    }


@router.get("/auth/google/login")
async def google_login(request: Request, returnTo: str = "/"):
    """Start the Google OAuth sign-in flow."""
    if not _google_ready:
        return RedirectResponse(url=f"{returnTo}?auth_error=google_not_configured")
    request.session["return_to"] = returnTo
    return await oauth.google.authorize_redirect(request, _google_redirect_uri(request))


@router.get("/auth/google/callback", name="google_callback")
async def google_callback(request: Request, db: Session = Depends(get_db)):
    """Handle the Google callback: create the session identity + user record."""
    if not _google_ready:
        return RedirectResponse(url="/?auth_error=google_not_configured")
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception as exc:
        logger.error("Google OAuth callback error: %s", exc)
        try:
            from api.security.events import log_security_event
            log_security_event("auth_failed", request, reason="google_token_exchange")
        except Exception:
            pass
        return RedirectResponse(url="/?auth_error=1")

    info = token.get("userinfo") or {}
    sub = str(info.get("sub", ""))
    if not sub:
        return RedirectResponse(url="/?auth_error=1")
    email = info.get("email") or ""
    name = info.get("name") or email or "User"
    picture = info.get("picture")
    identity = f"google:{sub}"

    try:
        upsert_user(db, user_id=identity, username=email or name, name=name, profile_image=picture)
    except Exception as exc:
        logger.error("Failed to upsert Google user: %s", exc)

    request.session["user"] = {
        "id": identity,
        "email": email,
        "name": name,
        "profile_image": picture,
        "provider": "google",
    }
    # Owner auto-admin: if this email is in ADMIN_USER_IDS, unlock admin too.
    admin_ids = {a.strip().lower() for a in (os.environ.get("ADMIN_USER_IDS") or "").split(",") if a.strip()}
    if email and email.lower() in admin_ids:
        request.session["is_admin"] = True

    return RedirectResponse(url=request.session.pop("return_to", "/"))


# ──────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────

@router.get("/login")
async def login(request: Request, returnTo: str = "/"):
    """Redirect to Replit OIDC provider."""
    # Always bypass external OIDC for localhost development.
    if request.url.hostname in {"localhost", "127.0.0.1"}:
        request.session["user"] = {
            "id": "dev-user-local",
            "username": "developer",
            "name": "Local Developer",
            "profile_image": None,
        }
        return RedirectResponse(url=returnTo)

    repl_client_id = settings.repl_id or os.environ.get("REPL_ID", "")

    # Local dev safety: if OIDC is not configured, avoid sending users to a broken
    # provider URL with empty client_id and localhost callback.
    if not repl_client_id:
        return RedirectResponse(url=f"{returnTo}?auth_error=oidc_not_configured")

    # Prefer request-derived callback so deployed hosts don't get forced to localhost.
    redirect_uri = str(request.url_for("callback"))
    # Store returnTo in session for after callback
    request.session["return_to"] = returnTo
    return await oauth.replit.authorize_redirect(request, redirect_uri)


@router.get("/callback")
async def callback(request: Request, db: Session = Depends(get_db)):
    """Handle OIDC callback, create/update user record, set session."""
    try:
        token = await oauth.replit.authorize_access_token(request)
    except Exception as exc:
        logger.error("OIDC callback error: %s", exc)
        try:
            from api.security.events import log_security_event
            log_security_event("auth_failed", request, reason="oidc_token_exchange")
        except Exception:
            pass
        return RedirectResponse(url="/?auth_error=1")

    userinfo = token.get("userinfo") or {}
    user_id = str(userinfo.get("sub", ""))
    username = userinfo.get("username") or userinfo.get("preferred_username") or "user"
    name = userinfo.get("name") or username
    profile_image = userinfo.get("picture") or userinfo.get("profile_image_url")

    if user_id:
        try:
            upsert_user(db, user_id=user_id, username=username, name=name, profile_image=profile_image)
        except Exception as exc:
            logger.error("Failed to upsert user: %s", exc)

    request.session["user"] = {
        "id": user_id,
        "username": username,
        "name": name,
        "profile_image": profile_image,
    }

    return_to = request.session.pop("return_to", "/")
    return RedirectResponse(url=return_to)


@router.get("/logout")
async def logout(request: Request, returnTo: str = "/"):
    """Clear session and redirect."""
    request.session.clear()
    return RedirectResponse(url=returnTo)


@router.get("/auth/user")
async def get_current_user(request: Request, db: Session = Depends(get_db)):
    """Return the current user (+ free-tier quota when auth is enabled).

    When auth is enabled, an anonymous visitor is not a 401 — they get a Guest
    identity plus their remaining free allowance so the UI can prompt sign-in.
    """
    user = request.session.get("user")
    if settings.auth_enabled:
        from api.middleware.auth import _anon_identity
        from api.utils import quota
        effective = user if (user and user.get("id")) else _anon_identity(request)
        status = quota.quota_status(db, request, effective)
        return {**effective, "quota": status}
    if not user or not user.get("id"):
        return JSONResponse(status_code=401, content={"detail": "Not authenticated"})
    return user


@router.post("/auth/mock")
async def create_mock_session(request: Request):
    """
    Local development only: create a mock session without Replit OIDC.
    
    Only available when DISABLE_AUTH=true.
    Used for local development and testing.
    """
    from api.config import settings
    
    if not settings.disable_auth:
        return JSONResponse(
            status_code=403,
            content={"detail": "Mock auth disabled (DISABLE_AUTH=false)"}
        )
    
    # Create mock user session
    request.session["user"] = {
        "id": "dev-user-local",
        "username": "developer",
        "name": "Local Developer",
        "profile_image": None,
    }
    
    return JSONResponse(
        status_code=200,
        content={
            "status": "ok",
            "user": request.session["user"],
            "message": "Mock session created (local development only)"
        }
    )


# ── Admin access (Translation Studio) ─────────────────────────────────────────
# Lightweight admin gate for the single site owner while full user auth is
# deferred: the admin enters a secret key (ADMIN_KEY env). On success the session
# is flagged is_admin=true, which unlocks the admin UI and admin-only endpoints.
# The client also stores a local flag purely to reveal the admin controls; the
# session flag below is the real authority the backend checks.

@router.get("/auth/admin-status")
async def admin_status(request: Request):
    """Whether the current session is an unlocked admin."""
    return {"is_admin": bool(request.session.get("is_admin"))}


@router.post("/auth/admin-login")
async def admin_login(request: Request):
    """Unlock admin for this session by presenting the correct ADMIN_KEY."""
    import os
    import hmac

    admin_key = (os.environ.get("ADMIN_KEY") or "").strip()
    if not admin_key:
        return JSONResponse(status_code=403, content={"detail": "Admin access is not configured (ADMIN_KEY unset)."})

    try:
        body = await request.json()
    except Exception:
        body = {}
    provided = str((body or {}).get("key", "")).strip()

    # Constant-time comparison to avoid timing leaks.
    if not provided or not hmac.compare_digest(provided, admin_key):
        from api.security.events import log_security_event
        try:
            log_security_event("admin_login_failed", request)
        except Exception:
            pass
        return JSONResponse(status_code=403, content={"detail": "Incorrect admin key."})

    # Ensure a user session exists too — admin endpoints also require_auth. In the
    # browser the mock/user session is already set; this makes admin self-contained.
    if not request.session.get("user"):
        request.session["user"] = {
            "id": "dev-user-local",
            "username": "admin",
            "name": "Admin",
            "profile_image": None,
        }
    request.session["is_admin"] = True
    return {"status": "ok", "is_admin": True}


@router.post("/auth/admin-logout")
async def admin_logout(request: Request):
    """Drop admin privileges for this session (stays signed in as a normal user)."""
    request.session.pop("is_admin", None)
    return {"status": "ok", "is_admin": False}
