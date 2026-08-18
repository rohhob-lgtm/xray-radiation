"""Production security hardening for the X-Ray Academy API.

Centralizes cross-cutting security concerns so individual routes stay simple:

  - ``headers``    — SecurityHeadersMiddleware (CSP, HSTS, X-Frame-Options, …)
  - ``rate_limit`` — RateLimitMiddleware (per-IP inbound throttling)
  - ``exceptions`` — global handlers that hide stack traces from clients
  - ``events``     — structured security-event logging
  - ``uploads``    — file-upload allow-listing (extension + MIME + size + magic)
  - ``sanitize``   — user-input validation / sanitization helpers

Wire the middleware and handlers into the app via :func:`install_security`.
"""
from __future__ import annotations

from fastapi import FastAPI

from api.config import settings
from .headers import SecurityHeadersMiddleware
from .rate_limit import RateLimitMiddleware
from .exceptions import install_exception_handlers
from .events import log_security_event

__all__ = [
    "install_security",
    "SecurityHeadersMiddleware",
    "RateLimitMiddleware",
    "install_exception_handlers",
    "log_security_event",
]


def install_security(app: FastAPI) -> None:
    """Attach security middleware and exception handlers to ``app``.

    Middleware added here runs *outside* whatever is already registered
    (Starlette applies the most-recently-added middleware first), so security
    headers land on every response — including those produced by inner
    middleware and error handlers.
    """
    install_exception_handlers(app)

    if settings.enable_rate_limit:
        app.add_middleware(RateLimitMiddleware)

    if settings.enable_security_headers:
        app.add_middleware(SecurityHeadersMiddleware)
