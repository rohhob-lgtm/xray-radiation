"""
Per-user, per-provider rate limiting for connector actions.

Simple in-memory token bucket — sufficient for a single-process local/dev
deployment. A multi-worker production deployment would need a shared store
(e.g. Redis) since this state does not cross processes.
"""
from __future__ import annotations

import time
from collections import deque
from threading import Lock

_MAX_ACTIONS_PER_WINDOW = 30
_WINDOW_SECONDS = 60.0

_buckets: dict[str, deque] = {}
_lock = Lock()


class RateLimitExceededError(Exception):
    pass


def check_rate_limit(user_id: str, provider: str) -> None:
    """Raise RateLimitExceededError if the user has exceeded the action rate for this provider."""
    key = f"{user_id}:{provider}"
    now = time.monotonic()
    with _lock:
        bucket = _buckets.setdefault(key, deque())
        while bucket and now - bucket[0] > _WINDOW_SECONDS:
            bucket.popleft()
        if len(bucket) >= _MAX_ACTIONS_PER_WINDOW:
            raise RateLimitExceededError(
                f"Rate limit exceeded: max {_MAX_ACTIONS_PER_WINDOW} actions per "
                f"{int(_WINDOW_SECONDS)}s for provider '{provider}'"
            )
        bucket.append(now)
