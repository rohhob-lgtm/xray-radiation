"""Structured logging for security-relevant events.

A single dedicated logger (``security``) so operators can route these to a
separate sink / alerting pipeline. Every record carries a machine-readable
``event`` field plus the client IP and request path, and values are kept short
and non-sensitive (never log secrets, tokens, or full request bodies).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from starlette.requests import Request

logger = logging.getLogger("security")


def client_ip(request: Optional[Request]) -> str:
    """Best-effort client IP.

    Honours a single X-Forwarded-For hop (the left-most entry) since the app is
    expected to run behind one trusted reverse proxy; falls back to the direct
    peer address. Never trust this for authorization — it is for logging only.
    """
    if request is None:
        return "-"
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    if request.client:
        return request.client.host
    return "-"


def log_security_event(
    event: str,
    request: Optional[Request] = None,
    *,
    level: int = logging.WARNING,
    **details: Any,
) -> None:
    """Emit one structured security event.

    ``event`` is a stable machine-readable slug (e.g. ``rate_limit_exceeded``,
    ``auth_failed``, ``upload_rejected``). Extra keyword args are appended as
    ``key=value`` pairs; keep them small and free of sensitive data.
    """
    path = request.url.path if request is not None else "-"
    method = request.method if request is not None else "-"
    ip = client_ip(request)
    extra = " ".join(f"{k}={v}" for k, v in details.items() if v is not None)
    logger.log(
        level,
        "security_event event=%s ip=%s method=%s path=%s %s",
        event,
        ip,
        method,
        path,
        extra,
    )
