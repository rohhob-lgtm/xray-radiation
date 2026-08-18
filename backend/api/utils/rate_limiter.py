"""
Shared async rate limiter for outbound LLM calls.

Gemini's free tier caps requests at a low per-minute ceiling (e.g. 15 RPM for
gemini-*-flash-lite). Both the translation pipeline (translator.py) and the
engineering review pass (engineering_review.py) fire batches concurrently
without knowing about that external ceiling, so most requests were bursting
past it and immediately getting HTTP 429'd, then retried with backoff — most
of the wall-clock time was spent on failed attempts rather than useful work.

This module paces outbound calls to a configurable requests-per-minute
budget, keyed by provider (detected from the model name), so translation and
review batches queue for their turn instead of bursting and failing. Only
models identified as Gemini are throttled; other providers are left
unaffected since they are not hitting this specific free-tier ceiling.
"""
from __future__ import annotations

import asyncio
import os
import time


class _TokenBucketLimiter:
    """Serializes acquire() calls so no more than `rpm` succeed per 60s window."""

    def __init__(self, rpm: int):
        self.rpm = max(1, rpm)
        self._interval = 60.0 / self.rpm
        self._lock = asyncio.Lock()
        self._next_slot = 0.0

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next_slot)
            self._next_slot = start + self._interval
            wait = start - now
        if wait > 0:
            await asyncio.sleep(wait)


def _env_rpm(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, "") or default))
    except ValueError:
        return default


_limiters: dict[str, _TokenBucketLimiter] = {}
_limiters_setup_lock = asyncio.Lock()


def _provider_key(model_name: str | None) -> str | None:
    name = (model_name or "").lower()
    if "gemini" in name:
        return "gemini"
    return None


async def acquire_slot(model_name: str | None) -> None:
    """Pace one outbound call according to its provider's known free-tier RPM.

    No-ops for providers without a known low ceiling (e.g. OpenAI), which
    already have their own much higher limits and retry handling.
    """
    key = _provider_key(model_name)
    if key is None:
        return
    limiter = _limiters.get(key)
    if limiter is None:
        async with _limiters_setup_lock:
            limiter = _limiters.get(key)
            if limiter is None:
                rpm = _env_rpm("GEMINI_RPM_LIMIT", 12)  # small safety margin under Google's 15
                limiter = _TokenBucketLimiter(rpm)
                _limiters[key] = limiter
    await limiter.acquire()
