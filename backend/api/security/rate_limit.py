"""Per-client inbound rate limiting.

A lightweight in-process sliding-window limiter applied to every ``/api`` route.
Two independent budgets are enforced per client IP:

  - a general budget (``rate_limit_requests`` per ``rate_limit_window_s``)
  - a tighter budget for authentication paths (login/callback/auth), which are
    the most attractive target for credential-stuffing / brute force.

Exceeding a budget yields ``429 Too Many Requests`` with a ``Retry-After``
header, and the rejection is logged as a security event.

Scope note: state lives in this worker process, so with multiple uvicorn
workers each enforces the limit independently. That is intentionally simple and
sufficient as a first line of defence; a shared store (Redis) would be the next
step for a horizontally-scaled deployment.
"""
from __future__ import annotations

import time
from collections import defaultdict, deque
from threading import Lock
from typing import Deque, Dict, Tuple

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from api.config import settings
from .events import client_ip, log_security_event

# Paths exempt from throttling: liveness/readiness probes must always answer.
_EXEMPT_PREFIXES = ("/api/health", "/api/healthz", "/api/ready")

# Auth-sensitive path fragments that get the stricter budget.
_AUTH_PREFIXES = ("/api/login", "/api/callback", "/api/logout", "/api/auth")


class _SlidingWindow:
    """Fixed-budget sliding-window counter keyed by an arbitrary string."""

    def __init__(self, limit: int, window_s: int):
        self.limit = max(1, limit)
        self.window = max(1, window_s)
        self._hits: Dict[str, Deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, now: float) -> Tuple[bool, float]:
        """Return (allowed, retry_after_seconds)."""
        cutoff = now - self.window
        with self._lock:
            q = self._hits[key]
            while q and q[0] <= cutoff:
                q.popleft()
            if len(q) >= self.limit:
                retry_after = max(0.0, q[0] + self.window - now)
                return False, retry_after
            q.append(now)
            return True, 0.0

    def sweep(self, now: float) -> None:
        """Drop empty/stale buckets so memory doesn't grow unbounded."""
        cutoff = now - self.window
        with self._lock:
            for key in list(self._hits.keys()):
                q = self._hits[key]
                while q and q[0] <= cutoff:
                    q.popleft()
                if not q:
                    del self._hits[key]


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self._general = _SlidingWindow(
            settings.rate_limit_requests, settings.rate_limit_window_s
        )
        self._auth = _SlidingWindow(
            settings.rate_limit_auth_requests, settings.rate_limit_auth_window_s
        )
        self._last_sweep = 0.0
        self._sweep_interval = max(
            settings.rate_limit_window_s, settings.rate_limit_auth_window_s
        )

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or path.startswith(_EXEMPT_PREFIXES):
            return await call_next(request)

        now = time.monotonic()
        self._maybe_sweep(now)

        ip = client_ip(request)
        is_auth = path.startswith(_AUTH_PREFIXES)
        limiter = self._auth if is_auth else self._general
        key = f"{'auth' if is_auth else 'gen'}:{ip}"

        allowed, retry_after = limiter.check(key, now)
        if not allowed:
            retry = int(retry_after) + 1
            log_security_event(
                "rate_limit_exceeded",
                request,
                scope="auth" if is_auth else "general",
                retry_after=retry,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Please slow down."},
                headers={"Retry-After": str(retry)},
            )

        return await call_next(request)

    def _maybe_sweep(self, now: float) -> None:
        if now - self._last_sweep < self._sweep_interval:
            return
        self._last_sweep = now
        self._general.sweep(now)
        self._auth.sweep(now)
