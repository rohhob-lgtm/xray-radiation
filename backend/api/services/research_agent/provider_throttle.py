"""Central provider throttle — Phase 2B.2.1.

Every external research-data provider call (Crossref, OpenAlex, Semantic
Scholar, PubMed, arXiv, CORE, DOAJ, PatentsView, web search, direct crawl,
Ollama) must go through call_with_throttle() rather than calling httpx
directly. Before this module, 775 concurrently-resumed missions could each
fire unthrottled HTTP requests at the same providers simultaneously — this
is what turns that into a bounded, backoff-aware, circuit-broken flow.

Reuses api.utils.rate_limiter._TokenBucketLimiter (already proven, already
async-safe — used today for Gemini RPM pacing) for the per-provider token
bucket instead of writing a new one. Adds a small CircuitBreaker on top and
Retry-After-aware backoff, neither of which existed anywhere in this
codebase before (confirmed by grep — zero hits for "Retry-After" or
"CircuitBreaker" prior to this file).

Every provider here is free/keyless today (confirmed in
api.services.research_agent.discovery's own docstring and by reading every
provider function in api.services.innovation_external_research) — `is_paid`
on ProviderConfig exists so a future paid provider is structurally forced
through the same Free-Mode gate api.services.research_brain.graph_extraction
already enforces, rather than silently bypassing it.
"""
from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, TypeVar

import httpx

from api.config import settings
from api.utils.rate_limiter import _TokenBucketLimiter

log = logging.getLogger(__name__)

T = TypeVar("T")

# Error-type vocabulary from the product spec — used for last_attempt_error_type
# and dead-letter decisions.
ERROR_TRANSIENT = "Transient"
ERROR_RATE_LIMITED = "RateLimited"
ERROR_AUTHENTICATION = "Authentication"
ERROR_PERMANENT = "Permanent"
ERROR_VALIDATION = "Validation"
ERROR_NETWORK = "Network"
ERROR_PROVIDER_UNAVAILABLE = "ProviderUnavailable"
ERROR_CANCELLED = "Cancelled"

PROVIDER_NAMES: tuple[str, ...] = (
    "crossref", "openalex", "semantic_scholar", "pubmed", "arxiv", "core",
    "doaj", "patentsview", "web_search", "direct_crawl", "ollama", "doi_resolver",
)


class ProviderThrottleError(Exception):
    """Raised when a throttled call ultimately fails — carries the §7 error
    vocabulary tag so callers (mission_queue.py) can decide Retry vs. Failed."""

    def __init__(self, provider: str, error_type: str, message: str):
        super().__init__(f"[{provider}] {error_type}: {message}")
        self.provider = provider
        self.error_type = error_type


@dataclass
class ProviderConfig:
    name: str
    rpm: int
    concurrency: int
    breaker_failure_threshold: int
    breaker_cooldown_s: int
    max_attempts: int = 4
    is_paid: bool = False


@dataclass
class ProviderMetrics:
    """Read by the scheduler-status endpoint — not a full metrics system,
    just the counters the product spec explicitly asks to expose."""
    request_count: int = 0
    success_count: int = 0
    failure_count: int = 0
    rate_limited_count: int = 0
    last_429_at: float | None = None
    consecutive_failures: int = 0


class CircuitBreaker:
    """Closed -> Open -> Half-Open -> Closed, isolated per provider.

    Opens after `failure_threshold` consecutive failures (429/timeout/5xx/
    connection error). While open, requests are rejected immediately
    (ProviderUnavailable) without ever reaching the network, until
    `cooldown_s` has elapsed, at which point exactly one probe request is
    allowed through (half-open); its outcome decides closed vs. re-opened
    (with the same cooldown — no escalating cooldown this round, disclosed
    as a simplification, not a correctness gap).
    """

    def __init__(self, failure_threshold: int, cooldown_s: int):
        self.failure_threshold = max(1, failure_threshold)
        self.cooldown_s = max(1, cooldown_s)
        self.state = "closed"
        self._opened_at: float | None = None
        self._half_open_probe_in_flight = False

    def allow_request(self) -> bool:
        if self.state == "closed":
            return True
        if self.state == "open":
            assert self._opened_at is not None
            if time.monotonic() - self._opened_at >= self.cooldown_s:
                self.state = "half_open"
                self._half_open_probe_in_flight = False
            else:
                return False
        if self.state == "half_open":
            if self._half_open_probe_in_flight:
                return False
            self._half_open_probe_in_flight = True
            return True
        return True

    def record_success(self) -> None:
        self.state = "closed"
        self._opened_at = None
        self._half_open_probe_in_flight = False

    def record_failure(self) -> None:
        if self.state == "half_open":
            self.state = "open"
            self._opened_at = time.monotonic()
            self._half_open_probe_in_flight = False
            return
        if self.state == "closed":
            # Threshold tracked externally via ProviderMetrics.consecutive_failures
            # (record_failure() is called once the caller has already confirmed
            # the threshold was crossed) — see _open_if_threshold_crossed below.
            self.state = "open"
            self._opened_at = time.monotonic()


@dataclass
class _ProviderState:
    config: ProviderConfig
    limiter: _TokenBucketLimiter
    semaphore: asyncio.Semaphore
    breaker: CircuitBreaker
    metrics: ProviderMetrics = field(default_factory=ProviderMetrics)


_states: dict[str, _ProviderState] = {}
_setup_lock = asyncio.Lock()


def _build_config(name: str) -> ProviderConfig:
    prefix = f"research_provider_{name}"
    return ProviderConfig(
        name=name,
        rpm=getattr(settings, f"{prefix}_rpm"),
        concurrency=getattr(settings, f"{prefix}_concurrency"),
        breaker_failure_threshold=settings.research_provider_breaker_failure_threshold,
        breaker_cooldown_s=settings.research_provider_breaker_cooldown_s,
    )


async def _get_state(provider: str) -> _ProviderState:
    state = _states.get(provider)
    if state is not None:
        return state
    async with _setup_lock:
        state = _states.get(provider)
        if state is None:
            config = _build_config(provider)
            state = _ProviderState(
                config=config,
                limiter=_TokenBucketLimiter(config.rpm),
                semaphore=asyncio.Semaphore(max(1, config.concurrency)),
                breaker=CircuitBreaker(config.breaker_failure_threshold, config.breaker_cooldown_s),
            )
            _states[provider] = state
    return state


def _parse_retry_after(exc: httpx.HTTPStatusError) -> float | None:
    header = exc.response.headers.get("Retry-After")
    if not header:
        return None
    try:
        return max(0.0, float(header))
    except ValueError:
        return None  # HTTP-date form — not parsed this round, falls back to backoff


def _classify(exc: BaseException) -> str:
    if isinstance(exc, asyncio.CancelledError):
        return ERROR_CANCELLED
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        if status == 429:
            return ERROR_RATE_LIMITED
        if status in (401, 403):
            return ERROR_AUTHENTICATION
        if status in (400, 404, 422):
            return ERROR_VALIDATION
        if status >= 500:
            return ERROR_TRANSIENT
        return ERROR_PERMANENT
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return ERROR_NETWORK
    if isinstance(exc, httpx.TimeoutException):
        return ERROR_TRANSIENT
    if isinstance(exc, httpx.RequestError):
        return ERROR_NETWORK
    return ERROR_TRANSIENT


def _backoff_with_jitter(attempt: int, base: float = 1.0, cap: float = 30.0) -> float:
    delay = min(cap, base * (2 ** attempt))
    return delay * (0.5 + random.random())  # 50%-150% jitter, never zero-wait retries


async def call_with_throttle(provider: str, fn: Callable[[], Awaitable[T]]) -> T:
    """Run fn() through provider's token bucket + concurrency limit +
    circuit breaker, with Retry-After-aware / backoff+jitter retry on
    transient failures. Raises ProviderThrottleError on exhaustion or when
    the breaker is open — never silently returns a wrong/empty result."""
    state = await _get_state(provider)
    max_attempts = state.config.max_attempts

    if not state.breaker.allow_request():
        raise ProviderThrottleError(provider, ERROR_PROVIDER_UNAVAILABLE, "circuit breaker open")

    last_error_type = ERROR_TRANSIENT
    for attempt in range(max_attempts):
        await state.limiter.acquire()
        async with state.semaphore:
            state.metrics.request_count += 1
            try:
                result = await fn()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                error_type = _classify(exc)
                last_error_type = error_type
                state.metrics.failure_count += 1
                state.metrics.consecutive_failures += 1

                if error_type in (ERROR_AUTHENTICATION, ERROR_VALIDATION, ERROR_PERMANENT):
                    # Caller misconfiguration / permanent rejection — never
                    # retried, and not counted against the breaker (this is
                    # not evidence the provider itself is unhealthy).
                    raise ProviderThrottleError(provider, error_type, str(exc)) from exc

                if state.metrics.consecutive_failures >= state.config.breaker_failure_threshold:
                    state.breaker.record_failure()
                elif state.breaker.state == "half_open":
                    state.breaker.record_failure()

                if error_type == ERROR_RATE_LIMITED:
                    state.metrics.rate_limited_count += 1
                    state.metrics.last_429_at = time.monotonic()
                    retry_after = _parse_retry_after(exc) if isinstance(exc, httpx.HTTPStatusError) else None
                    wait = retry_after if retry_after is not None else _backoff_with_jitter(attempt)
                else:
                    wait = _backoff_with_jitter(attempt)

                if attempt + 1 >= max_attempts or not state.breaker.allow_request():
                    raise ProviderThrottleError(provider, error_type, str(exc)) from exc

                log.warning(
                    "Provider throttle retry: provider=%s attempt=%d error_type=%s wait=%.1fs",
                    provider, attempt + 1, error_type, wait,
                )
                await asyncio.sleep(wait)
                continue
            else:
                state.metrics.success_count += 1
                state.metrics.consecutive_failures = 0
                state.breaker.record_success()
                return result

    raise ProviderThrottleError(provider, last_error_type, "max attempts exhausted")


def get_provider_status() -> dict[str, dict]:
    """Read-only snapshot for GET /research-agent/scheduler/providers."""
    out: dict[str, dict] = {}
    for name, state in _states.items():
        out[name] = {
            "state": state.breaker.state,
            "request_count": state.metrics.request_count,
            "success_count": state.metrics.success_count,
            "failure_count": state.metrics.failure_count,
            "rate_limited_count": state.metrics.rate_limited_count,
            "consecutive_failures": state.metrics.consecutive_failures,
            "is_paid": state.config.is_paid,
        }
    return out
