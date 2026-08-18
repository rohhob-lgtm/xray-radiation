"""
FastAPI auth dependency.

Routes that require authentication call `require_auth(request)`.
Routes that optionally use auth call `optional_auth(request)`.
"""
from __future__ import annotations
from typing import Optional

from fastapi import Request, HTTPException


def _user_from_session(request: Request) -> Optional[dict]:
    return request.session.get("user")


def optional_auth(request: Request) -> Optional[dict]:
    """Return the session user if logged in, or None."""
    return _user_from_session(request)


def require_admin_session(request: Request) -> None:
    """Require an unlocked admin session (set via POST /api/auth/admin-login).

    This is the server-side enforcement behind the admin UI lockdown: sensitive
    config endpoints (provider activation, task routing, API keys, cost budgets)
    depend on it, so hiding the controls in the client is backed by a real 403
    for anyone who calls the API directly without unlocking admin.
    """
    if not request.session.get("is_admin"):
        try:
            from api.security.events import log_security_event
            log_security_event("admin_required", request)
        except Exception:
            pass
        raise HTTPException(status_code=403, detail="Admin access required.")


def _anon_identity(request: Request) -> dict:
    """A per-browser anonymous identity keyed on the first-party ts_vid cookie.

    Lets an anonymous visitor use their free-tier allowance (and own their
    projects) without a session. The cookie is minted by POST /track-visit on
    page load, so it is normally present by the time work starts.
    """
    vid = request.cookies.get("ts_vid") or ""
    if not (len(vid) == 32 and all(c in "0123456789abcdef" for c in vid)):
        vid = "nocookie"
    return {"id": f"anon:{vid}", "name": "Guest", "anonymous": True, "tier": "anon"}


def require_auth(request: Request) -> dict:
    """Return the current identity.

    - A real session user (Google sign-in, or the local mock) is returned as-is.
    - When `auth_enabled` and there is no session, an anonymous per-browser
      identity is returned so guests can use their free allowance.
    - Otherwise (auth disabled and no session) raise 401.
    """
    user = _user_from_session(request)
    if user and user.get("id"):
        return user

    from api.config import settings
    if settings.auth_enabled:
        return _anon_identity(request)

    # Log unauthenticated access attempts to protected routes as a security
    # event (helps spot credential probing / broken clients).
    try:
        from api.security.events import log_security_event
        log_security_event("auth_required", request)
    except Exception:
        pass
    raise HTTPException(status_code=401, detail="Authentication required")
