"""Global exception handlers that keep stack traces off the wire.

FastAPI's own handlers for ``HTTPException`` and ``RequestValidationError`` are
kept (their bodies are developer-authored and safe). The catch-all handler for
any *unhandled* exception logs the full traceback server-side and returns a
generic ``500`` to the client — so an unexpected error never leaks internal
paths, SQL, or source lines. It also emits a security event so operators see a
spike of server errors.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .events import log_security_event

logger = logging.getLogger(__name__)


async def _unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full detail server-side only.
    logger.error(
        "Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc
    )
    log_security_event(
        "unhandled_exception",
        request,
        level=logging.ERROR,
        error_type=type(exc).__name__,
    )
    # Opaque body for the client — no traceback, no message text.
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error."},
    )


def install_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(Exception, _unhandled_exception_handler)
