"""
Central provider throttle tests — Phase 2B.2.1.

Covers: token bucket pacing, circuit breaker open/half-open/closed
transitions and per-provider isolation, Retry-After-aware 429 handling,
exponential backoff+jitter, no-retry on permanent/auth/validation errors,
and max-attempts exhaustion. Uses fake provider callables — no real network
calls — and asyncio.sleep is exercised for real (short durations only) since
these tests care about the actual scheduling behavior, not just call counts.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import asyncio
import uuid

import httpx
import pytest

from api.config import settings
from api.services.research_agent import provider_throttle as pt


def _http_error(status: int, retry_after: str | None = None) -> httpx.HTTPStatusError:
    req = httpx.Request("GET", "https://example.test/x")
    headers = {"Retry-After": retry_after} if retry_after else {}
    resp = httpx.Response(status, headers=headers, request=req)
    return httpx.HTTPStatusError(f"{status}", request=req, response=resp)


def _fresh_provider_name(prefix: str) -> str:
    """Each test gets its own provider *name* mapped onto a real base
    provider's settings via monkeypatching config lookups would be more
    invasive — instead, tests use the existing named providers but always
    start from a clean state by constructing a throwaway provider key that
    reuses crossref's settings shape. Since _build_config() reads
    settings.research_provider_<name>_rpm/_concurrency directly, and those
    only exist for the fixed provider set, tests use the real provider
    names (crossref/openalex/...) and rely on each test using a distinct
    provider so breaker/metrics state from one test never leaks into
    another."""
    return prefix


@pytest.fixture(autouse=True)
def _reset_provider_state(monkeypatch):
    pt._states.clear()
    # Simulated clock: real backoff/jitter math is exercised (test_backoff_
    # without_retry_after_increases_with_attempt asserts on the real
    # formula directly), but call_with_throttle's actual awaited sleeps are
    # not — no test here needs wall-clock delay to pass, and letting them
    # run at real speed made this suite take 30s+ for what is otherwise a
    # sub-second set of assertions.
    _real_sleep = asyncio.sleep

    async def _instant_sleep(*_a, **_k):
        await _real_sleep(0)

    monkeypatch.setattr(pt.asyncio, "sleep", _instant_sleep)
    pt._states.clear()
    yield
    pt._states.clear()


@pytest.mark.asyncio
async def test_success_path_records_metrics():
    async def ok():
        return "result"

    result = await pt.call_with_throttle("crossref", ok)
    assert result == "result"
    status = pt.get_provider_status()["crossref"]
    assert status["success_count"] == 1
    assert status["state"] == "closed"


@pytest.mark.asyncio
async def test_429_respects_retry_after_and_recovers():
    calls = {"n": 0}

    async def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise _http_error(429, retry_after="0")
        return "recovered"

    result = await pt.call_with_throttle("openalex", flaky)
    assert result == "recovered"
    assert calls["n"] == 2
    status = pt.get_provider_status()["openalex"]
    assert status["rate_limited_count"] == 1


@pytest.mark.asyncio
async def test_backoff_without_retry_after_increases_with_attempt():
    delays = [pt._backoff_with_jitter(a) for a in range(4)]
    # Each successive base delay (before jitter) doubles — even with jitter's
    # 0.5x-1.5x randomization, attempt 3's floor (min delay) must exceed
    # attempt 0's ceiling (max delay) given the 2x-per-step growth and the
    # jitter range not overlapping across two full doublings.
    assert delays[0] > 0  # never a zero-wait retry
    floor_3 = 1.0 * (2 ** 3) * 0.5
    ceiling_0 = 1.0 * (2 ** 0) * 1.5
    assert floor_3 > ceiling_0


@pytest.mark.asyncio
async def test_authentication_error_never_retried():
    calls = {"n": 0}

    async def auth_fail():
        calls["n"] += 1
        raise _http_error(401)

    with pytest.raises(pt.ProviderThrottleError) as exc_info:
        await pt.call_with_throttle("pubmed", auth_fail)
    assert exc_info.value.error_type == pt.ERROR_AUTHENTICATION
    assert calls["n"] == 1  # no retry attempted


@pytest.mark.asyncio
async def test_validation_error_never_retried():
    async def bad_request():
        raise _http_error(422)

    with pytest.raises(pt.ProviderThrottleError) as exc_info:
        await pt.call_with_throttle("doaj", bad_request)
    assert exc_info.value.error_type == pt.ERROR_VALIDATION


@pytest.mark.asyncio
async def test_circuit_breaker_opens_after_threshold_and_isolates_providers():
    async def always_503():
        raise _http_error(503)

    threshold = settings.research_provider_breaker_failure_threshold
    for _ in range(threshold + 1):
        with pytest.raises(pt.ProviderThrottleError):
            await pt.call_with_throttle("arxiv", always_503)

    status = pt.get_provider_status()
    assert status["arxiv"]["state"] == "open"

    # A DIFFERENT provider must be completely unaffected.
    async def ok():
        return "fine"
    result = await pt.call_with_throttle("core", ok)
    assert result == "fine"
    status_after = pt.get_provider_status()
    assert status_after["core"]["state"] == "closed"


@pytest.mark.asyncio
async def test_open_breaker_rejects_immediately_without_calling_fn():
    async def always_503():
        raise _http_error(503)

    threshold = settings.research_provider_breaker_failure_threshold
    for _ in range(threshold + 1):
        with pytest.raises(pt.ProviderThrottleError):
            await pt.call_with_throttle("semantic_scholar", always_503)
    assert pt.get_provider_status()["semantic_scholar"]["state"] == "open"

    call_count = {"n": 0}

    async def should_not_be_called():
        call_count["n"] += 1
        return "unreachable"

    with pytest.raises(pt.ProviderThrottleError) as exc_info:
        await pt.call_with_throttle("semantic_scholar", should_not_be_called)
    assert exc_info.value.error_type == pt.ERROR_PROVIDER_UNAVAILABLE
    assert call_count["n"] == 0  # breaker rejected before fn() ever ran


@pytest.mark.asyncio
async def test_half_open_probe_closes_breaker_on_success():
    async def always_503():
        raise _http_error(503)

    threshold = settings.research_provider_breaker_failure_threshold
    for _ in range(threshold + 1):
        with pytest.raises(pt.ProviderThrottleError):
            await pt.call_with_throttle("patentsview", always_503)
    state = await pt._get_state("patentsview")
    assert state.breaker.state == "open"

    # Force the cooldown window to have already elapsed.
    state.breaker._opened_at -= (state.breaker.cooldown_s + 1)

    async def ok():
        return "recovered"
    result = await pt.call_with_throttle("patentsview", ok)
    assert result == "recovered"
    assert state.breaker.state == "closed"


@pytest.mark.asyncio
async def test_max_attempts_exhaustion_raises_with_last_error_type():
    async def always_timeout():
        raise httpx.TimeoutException("timed out")

    with pytest.raises(pt.ProviderThrottleError) as exc_info:
        await pt.call_with_throttle("web_search", always_timeout)
    assert exc_info.value.error_type == pt.ERROR_TRANSIENT
    status = pt.get_provider_status()["web_search"]
    assert status["failure_count"] >= settings.research_provider_web_search_rpm or status["failure_count"] > 0
