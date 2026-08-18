"""Free-tier translation quotas.

The tiered model (active only when ``settings.auth_enabled``):

  * anonymous browser  → ``anon_free_translations`` free jobs  (default 1)
  * signed in (Google) → ``account_free_translations`` free jobs (default 5)
  * beyond that        → HTTP 402 with a prompt to sign in / buy a plan

Usage is counted from completed ``TranslationUsage`` rows keyed by the identity
that ``require_auth`` returns (``google:<sub>`` or ``anon:<cookie>``), so no
separate counter table is needed. Admins are never limited.
"""
from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import func

from api.config import settings


def user_tier(user: dict | None) -> str:
    if not user:
        return "anon"
    if user.get("anonymous"):
        return "anon"
    # A real signed-in account (Google, etc.)
    return "account"


def free_limit(tier: str) -> int:
    return (
        settings.account_free_translations
        if tier == "account"
        else settings.anon_free_translations
    )


def used_count(db, identity: str) -> int:
    from api.db.models import TranslationUsage
    return int(
        db.query(func.count(TranslationUsage.id))
        .filter(
            TranslationUsage.user_id == identity,
            TranslationUsage.status == "complete",
        )
        .scalar()
        or 0
    )


def quota_status(db, request, user: dict | None) -> dict:
    """Report the current identity's tier, usage, and remaining free jobs."""
    is_admin = bool(getattr(request, "session", {}).get("is_admin")) if request else False
    tier = user_tier(user)
    identity = (user or {}).get("id") or "anon:nocookie"
    limit = free_limit(tier)
    used = used_count(db, identity) if not is_admin else 0
    return {
        "enabled": settings.auth_enabled,
        "authenticated": tier == "account",
        "is_admin": is_admin,
        "tier": tier,
        "used": used,
        "limit": limit,
        "remaining": max(0, limit - used) if not is_admin else 9999,
        "email": (user or {}).get("email"),
    }


def enforce(db, request, user: dict) -> None:
    """Raise HTTP 402 when the identity has exhausted its free allowance.

    No-op when auth is disabled or the caller is an admin.
    """
    if not settings.auth_enabled:
        return
    if request is not None and getattr(request, "session", {}).get("is_admin"):
        return
    tier = user_tier(user)
    identity = (user or {}).get("id") or "anon:nocookie"
    limit = free_limit(tier)
    used = used_count(db, identity)
    if used >= limit:
        if tier == "anon":
            _n = settings.account_free_translations
            msg = (
                f"You've used your free translation ({limit}). "
                f"Sign in with Google to get {_n} free translations."
            )
            cta = "sign_in"
        else:
            msg = (
                f"You've used your {limit} free translations. "
                "Choose a plan to continue."
            )
            cta = "upgrade"
        raise HTTPException(
            status_code=402,
            detail={
                "error": "free_quota_exceeded",
                "tier": tier,
                "used": used,
                "limit": limit,
                "cta": cta,
                "message": msg,
            },
        )
