"""
Billing-safety guard for the runtime translation platform.

The live translation pipeline calls the official OpenAI API directly
(OPENAI_API_KEY) — it never invokes Replit Agent, Replit Assistant,
subagents, or any autonomous development workflow. This module adds the
server-side cost controls around that direct API usage:

- Emergency kill switch          TRANSLATION_ENABLED
- Upload size limit              MAX_FILE_SIZE_MB
- Job size limits                MAX_SEGMENTS_PER_JOB / MAX_CHARS_PER_JOB
- Per-user rate limit            MAX_REQUESTS_PER_USER_PER_HOUR
                                 TRANSLATION_RATE_LIMIT_MODE
                                 TRANSLATION_LOCALHOST_UNLIMITED
                                 DEVELOPMENT_MODE
                                 DISABLE_TRANSLATION_RATE_LIMIT
                                 DISABLE_HOURLY_QUOTA
                                 DISABLE_DAILY_QUOTA
                                 DISABLE_MONTHLY_QUOTA
                                 LOCAL_DEVELOPER_USER_IDS
- Concurrency + idempotency      MAX_CONCURRENT_TRANSLATIONS (+ per-project slot)
- Cost ceilings                  MAX_COST_PER_JOB_USD / MAX_DAILY_API_COST_USD /
                                 MAX_MONTHLY_API_COST_USD
- Large-job confirmation         CONFIRM_SEGMENTS_THRESHOLD / CONFIRM_CHARS_THRESHOLD
- Model selection                OPENAI_TRANSLATION_MODEL (default gpt-4o)
- Admin gating                   ADMIN_USER_IDS (comma-separated ids/emails)

All limits have safe defaults and are enforced server-side. Guard checks are
synchronous on purpose: the check-and-acquire block runs without awaiting, so
double-clicked Translate buttons cannot interleave past the guards.
"""

from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from fastapi import HTTPException

log = logging.getLogger(__name__)

# ── Env helpers ────────────────────────────────────────────────────────────────

def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _env_str(name: str, default: str) -> str:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return default
    return v.strip()


def _env_opt_bool(name: str) -> bool | None:
    v = os.environ.get(name)
    if v is None or v.strip() == "":
        return None
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_csv(name: str, default: str = "") -> set[str]:
    raw = _env_str(name, default)
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _host_is_local(host: str | None) -> bool:
    if not host:
        return False
    h = host.strip().lower()
    return h in {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


def _url_is_local(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if parsed.hostname:
            return _host_is_local(parsed.hostname)
    except Exception:
        pass
    return any(tok in url.lower() for tok in ("localhost", "127.0.0.1", "0.0.0.0"))


def _looks_like_local_runtime() -> bool:
    # Explicit local auth bypass is the strongest local-dev signal in this app.
    if _env_bool("DISABLE_AUTH", False):
        return True
    if _host_is_local(_env_str("REPLIT_DEV_DOMAIN", "")):
        return True

    for env_name in ("FRONTEND_URL", "BASE_URL", "PUBLIC_BASE_URL", "APP_BASE_URL"):
        if _url_is_local(_env_str(env_name, "")):
            return True

    runtime = _env_str("XRAY_RUNTIME_ENV", "").lower()
    node_env = _env_str("NODE_ENV", "").lower()
    if runtime in {"local", "development", "dev", "test"}:
        return True
    if node_env in {"local", "development", "dev", "test"}:
        return True

    return False


def _is_development_mode() -> bool:
    """Detect development mode automatically, with explicit env override support."""
    explicit = _env_opt_bool("DEVELOPMENT_MODE")
    if explicit is not None:
        return explicit
    return _looks_like_local_runtime()


def _flag_default_true_in_dev(name: str) -> bool:
    explicit = _env_opt_bool(name)
    if explicit is not None:
        return explicit
    return _is_development_mode()


def _local_developer_ids() -> set[str]:
    return _env_csv("LOCAL_DEVELOPER_USER_IDS", "dev-user-local")


def _is_local_developer_user(user_id: str | None) -> bool:
    if not user_id:
        return False
    return user_id.strip().lower() in _local_developer_ids()


def _has_unlimited_dev_quota(user_id: str | None) -> bool:
    # Local Developer account is unlimited only in development mode.
    return _is_development_mode() and _is_local_developer_user(user_id)


def _hourly_rate_limit_enabled() -> bool:
    """Rate-limit toggle with safe defaults for production and localhost."""
    if _flag_default_true_in_dev("DISABLE_TRANSLATION_RATE_LIMIT"):
        return False
    if _flag_default_true_in_dev("DISABLE_HOURLY_QUOTA"):
        return False

    mode = _env_str("TRANSLATION_RATE_LIMIT_MODE", "auto").lower()
    if mode in {"off", "false", "0", "disabled"}:
        return False
    if mode in {"on", "true", "1", "enabled"}:
        return True
    # auto: keep production protection, disable for local developer mode
    if _is_development_mode() and _env_bool("TRANSLATION_LOCALHOST_UNLIMITED", True):
        return False
    return True


# ── Model & pricing (USD per 1M tokens: input, output). Estimates only. ───────

_PRICES = {
    "gpt-4o":        (2.50, 10.00),
    "gpt-4o-mini":   (0.15, 0.60),
    "gpt-4.1":       (2.00, 8.00),
    "gpt-4.1-mini":  (0.40, 1.60),
}
_DEFAULT_PRICE = (2.50, 10.00)  # conservative fallback for unknown models


def translation_model() -> str:
    """Configured translation model — never switched automatically.

    Default: gpt-4o-mini (≈16× cheaper than gpt-4o for segment translation).
    Engineering review always uses gpt-4o regardless of this setting.
    Override: set OPENAI_TRANSLATION_MODEL=gpt-4o to restore the original.
    """
    return (os.environ.get("OPENAI_TRANSLATION_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"


def _price_for(model: str) -> tuple[float, float]:
    for key, price in _PRICES.items():
        if model.startswith(key):
            return price
    return _DEFAULT_PRICE


def est_cost_usd(input_tokens: int, output_tokens: int, model: str | None = None) -> float:
    pin, pout = _price_for(model or translation_model())
    return round((input_tokens * pin + output_tokens * pout) / 1_000_000, 4)


# ── Config snapshot ────────────────────────────────────────────────────────────

def config_snapshot() -> dict:
    return {
        "translation_enabled": _env_bool("TRANSLATION_ENABLED", True),
        "translation_rate_limit_mode": _env_str("TRANSLATION_RATE_LIMIT_MODE", "auto"),
        "translation_localhost_unlimited": _env_bool("TRANSLATION_LOCALHOST_UNLIMITED", True),
        "development_mode": _is_development_mode(),
        "disable_translation_rate_limit": _flag_default_true_in_dev("DISABLE_TRANSLATION_RATE_LIMIT"),
        "disable_hourly_quota": _flag_default_true_in_dev("DISABLE_HOURLY_QUOTA"),
        "disable_daily_quota": _flag_default_true_in_dev("DISABLE_DAILY_QUOTA"),
        "disable_monthly_quota": _flag_default_true_in_dev("DISABLE_MONTHLY_QUOTA"),
        "hourly_rate_limit_enabled": _hourly_rate_limit_enabled(),
        "local_developer_user_ids": sorted(_local_developer_ids()),
        "model": translation_model(),
        "max_file_size_mb": _env_int("MAX_FILE_SIZE_MB", 200),
        "max_segments_per_job": _env_int("MAX_SEGMENTS_PER_JOB", 2500),
        "max_chars_per_job": _env_int("MAX_CHARS_PER_JOB", 600_000),
        "max_requests_per_user_per_hour": _env_int("MAX_REQUESTS_PER_USER_PER_HOUR", 10),
        "max_concurrent_translations": _env_int("MAX_CONCURRENT_TRANSLATIONS", 2),
        "max_cost_per_job_usd": _env_float("MAX_COST_PER_JOB_USD", 5.0),
        "max_daily_api_cost_usd": _env_float("MAX_DAILY_API_COST_USD", 25.0),
        "max_monthly_api_cost_usd": _env_float("MAX_MONTHLY_API_COST_USD", 200.0),
        "confirm_segments_threshold": _env_int("CONFIRM_SEGMENTS_THRESHOLD", 300),
        "confirm_chars_threshold": _env_int("CONFIRM_CHARS_THRESHOLD", 150_000),
    }


def max_file_size_bytes() -> int:
    return _env_int("MAX_FILE_SIZE_MB", 200) * 1024 * 1024


def ensure_enabled() -> None:
    """Emergency kill switch — set TRANSLATION_ENABLED=false to stop all jobs."""
    if not _env_bool("TRANSLATION_ENABLED", True):
        raise HTTPException(
            503,
            "Translation is currently disabled by the administrator "
            "(TRANSLATION_ENABLED=false). No new translation jobs are accepted.",
        )


# ── Job estimation ─────────────────────────────────────────────────────────────

def estimate_segments(segments: list[dict]) -> dict:
    """Estimate size/cost for a job from its extracted segments.

    Token math is an estimate (chars/3 ≈ tokens for mixed EN/AR) plus prompt
    overhead per batch; output ≈ input for translation. Costs cover the main
    translation batches (glossary/review overhead is why a high bound exists).
    """
    n = len(segments)
    chars = sum(len(s.get("source") or "") for s in segments)
    pages = len({
        (s.get("loc") or {}).get("slide_idx",
                                 (s.get("loc") or {}).get("page", 0))
        for s in segments
    }) if segments else 0
    batches = max(1, (n + 29) // 30)
    in_tokens = int(chars / 3) + batches * 700   # system prompt + JSON wrapper
    out_tokens = int(chars / 3 * 1.15)
    model = translation_model()
    low = est_cost_usd(in_tokens, out_tokens, model)
    high = round(low * 1.6, 4)  # absorbs review/labels/glossary overhead
    return {
        "segments": n,
        "chars": chars,
        "pages": pages,
        "est_input_tokens": in_tokens,
        "est_output_tokens": out_tokens,
        "model": model,
        "est_cost_usd_low": low,
        "est_cost_usd_high": high,
    }


def needs_confirmation(est: dict) -> bool:
    cfg = config_snapshot()
    return (
        est["segments"] > cfg["confirm_segments_threshold"]
        or est["chars"] > cfg["confirm_chars_threshold"]
    )


def check_job_size(est: dict) -> None:
    """Reject oversized jobs before any content is sent to the API."""
    cfg = config_snapshot()
    if est["segments"] > cfg["max_segments_per_job"]:
        raise HTTPException(
            413,
            f"Document has {est['segments']} text segments — the configured "
            f"maximum is {cfg['max_segments_per_job']} (MAX_SEGMENTS_PER_JOB). "
            "Split the document and try again.",
        )
    if est["chars"] > cfg["max_chars_per_job"]:
        raise HTTPException(
            413,
            f"Document has {est['chars']:,} characters — the configured "
            f"maximum is {cfg['max_chars_per_job']:,} (MAX_CHARS_PER_JOB). "
            "Split the document and try again.",
        )


# ── Concurrency slots + rate limit + cost ceilings ─────────────────────────────

_slots: set[str] = set()
_slots_lock = threading.Lock()


def check_and_acquire(db, user_id: str | None, project_id: str) -> None:
    """All start-of-job guards in one synchronous, lock-protected block.

    Raises HTTPException (409/429/503) when the job must not start.
    On success the project's concurrency slot is acquired — the caller MUST
    call release_slot(project_id) when the job ends (any outcome).
    """
    from api.db.models import TranslationUsage  # local import avoids cycles

    ensure_enabled()
    cfg = config_snapshot()
    now = datetime.now(timezone.utc)
    unlimited_dev_quota = _has_unlimited_dev_quota(user_id)

    with _slots_lock:
        # Idempotency: the same project can never run twice at once —
        # repeated button clicks cannot double-charge a job.
        if project_id in _slots:
            raise HTTPException(
                409, "This project is already being translated. "
                     "Wait for the current run to finish.",
            )
        if len(_slots) >= cfg["max_concurrent_translations"]:
            raise HTTPException(
                429,
                f"Maximum simultaneous translations "
                f"({cfg['max_concurrent_translations']}) reached. "
                "Try again in a few minutes.",
            )

        # Per-user hourly rate limit (production by default, configurable)
        if user_id and cfg["hourly_rate_limit_enabled"] and not unlimited_dev_quota:
            hour_ago = now - timedelta(hours=1)
            recent = (
                db.query(TranslationUsage)
                .filter(
                    TranslationUsage.user_id == user_id,
                    TranslationUsage.created_at >= hour_ago,
                )
                .count()
            )
            if recent >= cfg["max_requests_per_user_per_hour"]:
                raise HTTPException(
                    429,
                    f"Hourly translation limit reached "
                    f"({cfg['max_requests_per_user_per_hour']} jobs/hour). "
                    "Try again later.",
                )

        # Daily / monthly platform cost ceilings — never silently exceeded
        # Dev-mode and Local Developer account can bypass budget ceilings for testing.
        if not unlimited_dev_quota:
            day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
            month_start = day_start.replace(day=1)
            from sqlalchemy import func as _f

            if not cfg["disable_daily_quota"]:
                day_cost = (
                    db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0))
                    .filter(TranslationUsage.created_at >= day_start)
                    .scalar() or 0.0
                )
                if day_cost >= cfg["max_daily_api_cost_usd"]:
                    raise HTTPException(
                        503,
                        "ADMINISTRATOR NOTICE: the daily API cost ceiling "
                        f"(${cfg['max_daily_api_cost_usd']:.2f}, MAX_DAILY_API_COST_USD) "
                        f"has been reached (${day_cost:.2f} used today). New translation "
                        "jobs are stopped until tomorrow or until the limit is raised.",
                    )

            if not cfg["disable_monthly_quota"]:
                month_cost = (
                    db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0))
                    .filter(TranslationUsage.created_at >= month_start)
                    .scalar() or 0.0
                )
                if month_cost >= cfg["max_monthly_api_cost_usd"]:
                    raise HTTPException(
                        503,
                        "ADMINISTRATOR NOTICE: the monthly API cost ceiling "
                        f"(${cfg['max_monthly_api_cost_usd']:.2f}, MAX_MONTHLY_API_COST_USD) "
                        f"has been reached (${month_cost:.2f} this month). New translation "
                        "jobs are stopped until the limit is raised.",
                    )

        _slots.add(project_id)


def release_slot(project_id: str) -> None:
    with _slots_lock:
        _slots.discard(project_id)


def active_jobs() -> int:
    with _slots_lock:
        return len(_slots)


def startup_cleanup() -> None:
    """
    Cleanup orphaned slots at application startup.
    
    Slots can be orphaned if:
    - Server crashed during translation
    - Exception occurred before slot was released
    - Session timeout or forced shutdown
    
    This ensures slots do not accumulate and block future translations.
    Called once on app startup, safe to call multiple times.
    """
    with _slots_lock:
        if _slots:
            log.warning(
                "Cleanup: Releasing %d orphaned translation slot(s) from previous session",
                len(_slots)
            )
            _slots.clear()


# ── Usage recording (admin dashboard data) ─────────────────────────────────────

def record_usage(
    *,
    user_id: str | None,
    project_id: str,
    project_name: str,
    file_type: str,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    segments_total: int,
    segments_translated: int,
    memory_hits: int,
    duration_secs: float,
    status: str,
    error: str = "",
    retries: int = 0,
    chars_translated: int = 0,
    # Per-stage token breakdown (actual API values)
    translate_in_tokens: int = 0,
    translate_out_tokens: int = 0,
    translate_cached_tokens: int = 0,
    review_in_tokens: int = 0,
    review_out_tokens: int = 0,
    review_cached_tokens: int = 0,
    # Stage wall-clock times
    stage_extract_s: float = 0.0,
    stage_translate_s: float = 0.0,
    stage_review_s: float = 0.0,
    stage_rebuild_s: float = 0.0,
    stage_validate_s: float = 0.0,
    # API call counts
    api_calls_translate: int = 0,
    api_calls_review: int = 0,
    # Segment detail
    segments_reviewed: int = 0,
    memory_misses: int = 0,
    source_pages: int = 0,
) -> None:
    """Best-effort usage record — never breaks the pipeline."""
    try:
        from api.db import SessionLocal
        from api.db.models import TranslationUsage

        # Compute per-stage costs from actual token counts + published model prices
        _translate_model = translation_model()
        _translate_cost = est_cost_usd(translate_in_tokens or 0, translate_out_tokens or 0, _translate_model)
        _review_cost = est_cost_usd(review_in_tokens or 0, review_out_tokens or 0, "gpt-4o")
        _total_cost = _translate_cost + _review_cost
        # Fall back to combined totals if per-stage tracking wasn't available
        if _total_cost == 0.0:
            _total_cost = est_cost_usd(input_tokens or 0, output_tokens or 0, model)

        s = SessionLocal()
        try:
            s.add(TranslationUsage(
                id=str(uuid.uuid4()),
                user_id=user_id,
                project_id=project_id,
                project_name=(project_name or "")[:256],
                file_type=(file_type or "")[:16],
                model=(model or "")[:64],
                provider=(provider or "")[:128],
                input_tokens=int(input_tokens or 0),
                output_tokens=int(output_tokens or 0),
                est_cost_usd=_total_cost,
                segments_total=int(segments_total or 0),
                segments_translated=int(segments_translated or 0),
                memory_hits=int(memory_hits or 0),
                duration_secs=round(float(duration_secs or 0), 1),
                status=(status or "")[:32],
                error=(error or "")[:512],
                retries=int(retries or 0),
                chars_translated=int(chars_translated or 0),
                translate_in_tokens=int(translate_in_tokens or 0),
                translate_out_tokens=int(translate_out_tokens or 0),
                translate_cached_tokens=int(translate_cached_tokens or 0),
                review_in_tokens=int(review_in_tokens or 0),
                review_out_tokens=int(review_out_tokens or 0),
                review_cached_tokens=int(review_cached_tokens or 0),
                stage_extract_s=round(float(stage_extract_s or 0), 3),
                stage_translate_s=round(float(stage_translate_s or 0), 3),
                stage_review_s=round(float(stage_review_s or 0), 3),
                stage_rebuild_s=round(float(stage_rebuild_s or 0), 3),
                stage_validate_s=round(float(stage_validate_s or 0), 3),
                api_calls_translate=int(api_calls_translate or 0),
                api_calls_review=int(api_calls_review or 0),
                segments_reviewed=int(segments_reviewed or 0),
                memory_misses=int(memory_misses or 0),
                source_pages=int(source_pages or 0),
            ))
            s.commit()
        finally:
            s.close()
    except Exception as exc:
        log.warning("Usage recording failed (non-fatal): %s", exc)


# ── Admin gating ───────────────────────────────────────────────────────────────

def require_admin(user: dict) -> None:
    """403 unless the user's id or email is listed in ADMIN_USER_IDS."""
    allowed = {
        a.strip() for a in (os.environ.get("ADMIN_USER_IDS") or "").split(",")
        if a.strip()
    }
    ident = {str(user.get("id") or ""), str(user.get("email") or "")}
    if not allowed or not (ident & allowed):
        raise HTTPException(403, "Administrator access required.")
