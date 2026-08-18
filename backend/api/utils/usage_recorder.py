"""
Central OpenAI usage recorder — the single point where every API call is logged.

Every feature that calls OpenAI (Innovation Engine, Training Generator, Gallery
Reindex, RAG Vision Analysis, Image Translator, LinkedIn, X-Ray Image Analysis,
mandatory-section builder, etc.) should call record_usage() after every response.

Design principles:
- Synchronous and fire-and-forget: a failed log write never breaks the calling feature.
- Creates its own DB session when the caller doesn't have one (background tasks, utils).
- Pass db= when a session is already open to avoid extra connections.
- Pricing is definitive here; cost_dashboard.py imports from this module.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

log = logging.getLogger(__name__)

# ── Pricing constants (USD per 1M tokens) ─────────────────────────────────────

_IN_PRICES: dict[str, float] = {
    "gpt-4o":       5.00,
    "gpt-4o-mini":  0.15,
    "gpt-4.1":      2.00,
    "gpt-4.1-mini": 0.40,
    "gpt-4.5":     75.00,
    "gpt-5":       100.00,
    "gpt-5.4":     100.00,
    "o1":           15.00,
    "o3":           10.00,
    "o3-mini":       1.10,
    # Anthropic Claude — USD per 1M input tokens
    "claude-fable-5":    10.00,
    "claude-mythos-5":   10.00,
    "claude-opus-5":      5.00,
    "claude-opus-4":      5.00,
    "claude-sonnet-5":    3.00,
    "claude-sonnet-4":    3.00,
    "claude-haiku-4-5":   1.00,
}
_OUT_PRICES: dict[str, float] = {
    "gpt-4o":       15.00,
    "gpt-4o-mini":   0.60,
    "gpt-4.1":       8.00,
    "gpt-4.1-mini":  1.60,
    "gpt-4.5":     150.00,
    "gpt-5":       200.00,
    "gpt-5.4":     200.00,
    "o1":           60.00,
    "o3":           40.00,
    "o3-mini":       4.40,
    # Anthropic Claude — USD per 1M output tokens
    "claude-fable-5":    50.00,
    "claude-mythos-5":   50.00,
    "claude-opus-5":     25.00,
    "claude-opus-4":     25.00,
    "claude-sonnet-5":   15.00,
    "claude-sonnet-4":   15.00,
    "claude-haiku-4-5":   5.00,
}


def price_for(model: str | None, side: str) -> float:
    """Return price in USD per 1M tokens for the given model and side (in/out)."""
    if not model:
        model = "gpt-4o"
    prices = _IN_PRICES if side == "in" else _OUT_PRICES
    for key, price in prices.items():
        if model.lower().startswith(key):
            return price
    return prices.get("gpt-4o", 5.00)


def compute_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: str | None = None,
    cached_tokens: int = 0,
) -> float:
    """
    Compute USD cost for one API call.

    OpenAI bills cached tokens at 50% of the standard input price.
    Uncached prompt tokens are billed at the full input price.
    """
    uncached = max(0, prompt_tokens - cached_tokens)
    cost = (
        uncached        * price_for(model, "in")
        + cached_tokens * price_for(model, "in") * 0.5
        + completion_tokens * price_for(model, "out")
    ) / 1_000_000
    return round(cost, 8)


def record_usage(
    feature: str,
    model: str | None,
    prompt_tokens: int,
    completion_tokens: int,
    *,
    cached_tokens: int = 0,
    duration_ms: int = 0,
    sub_feature: str | None = None,
    meta: dict | None = None,
    db=None,
) -> None:
    """
    Write one row to openai_usage_log.

    This function is synchronous and NEVER raises — any exception is logged as
    a warning so the calling feature is not disrupted.

    Parameters
    ----------
    feature       : Human-readable feature name, e.g. "Innovation Engine"
    model         : OpenAI model string, e.g. "gpt-5.4"
    prompt_tokens : Prompt token count from response.usage.prompt_tokens
    completion_tokens : Completion token count from response.usage.completion_tokens
    cached_tokens : Cached prompt tokens (from usage.prompt_tokens_details.cached_tokens)
    duration_ms   : Wall-clock milliseconds for the API call
    sub_feature   : Optional sub-category, e.g. "report_stream", "slides_batch_1"
    meta          : Optional JSON dict (doc_id, filename, etc.)
    db            : Existing SQLAlchemy Session; if None, a new one is created.
    """
    try:
        from api.db.base import SessionLocal
        from api.db.models import UnifiedUsageLog

        cost = compute_cost(prompt_tokens, completion_tokens, model, cached_tokens)

        row = UnifiedUsageLog(
            feature=feature,
            sub_feature=sub_feature,
            model=model or "unknown",
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cached_tokens=cached_tokens,
            cost_usd=cost,
            duration_ms=duration_ms,
            meta=meta,
        )

        own_session = db is None
        if own_session:
            db = SessionLocal()
        try:
            db.add(row)
            db.commit()
        finally:
            if own_session:
                db.close()

    except Exception as exc:
        log.warning(
            "record_usage failed (feature=%s model=%s pt=%s ct=%s): %s",
            feature, model, prompt_tokens, completion_tokens, exc,
        )


def record_usage_from_response(
    feature: str,
    response: Any,
    *,
    duration_ms: int = 0,
    sub_feature: str | None = None,
    meta: dict | None = None,
    db=None,
) -> None:
    """
    Convenience wrapper: extract token counts directly from an OpenAI response object
    (ChatCompletion or similar) and call record_usage().

    Silently does nothing if response.usage is None (e.g. streaming without usage).
    """
    try:
        usage = getattr(response, "usage", None)
        if not usage:
            return
        model = getattr(response, "model", None)
        pt = getattr(usage, "prompt_tokens", 0) or 0
        ct = getattr(usage, "completion_tokens", 0) or 0
        # Try to get cached tokens from prompt_tokens_details
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details:
            cached = getattr(details, "cached_tokens", 0) or 0
        record_usage(
            feature=feature,
            model=model,
            prompt_tokens=pt,
            completion_tokens=ct,
            cached_tokens=cached,
            duration_ms=duration_ms,
            sub_feature=sub_feature,
            meta=meta,
            db=db,
        )
    except Exception as exc:
        log.warning("record_usage_from_response failed (feature=%s): %s", feature, exc)
