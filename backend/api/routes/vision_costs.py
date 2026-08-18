"""Vision Cost Protection — estimation, confirmation, stats, and audit log routes."""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func as _f
from sqlalchemy.orm import Session

from api.db import get_db
from api.db.models import RagDocument, RagImage, VisionCostLog
from api.middleware.auth import require_auth

log = logging.getLogger(__name__)

router = APIRouter(tags=["vision"])


@router.get("/vision/estimate/{doc_id}")
def get_vision_estimate(doc_id: str, db: Session = Depends(get_db)):
    """Return the pre-flight vision cost estimate stored during image extraction."""
    doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    est = getattr(doc, "vision_estimate", None)
    if not est:
        # Fallback: compute counts from images table
        total = db.query(RagImage).filter(RagImage.doc_id == doc_id).count()
        pending = db.query(RagImage).filter(
            RagImage.doc_id == doc_id,
            RagImage.caption.is_(None),
        ).count()
        from api.services.vision_guard import max_vision_calls_per_job, _vision_model
        return {
            "doc_id": doc_id,
            "total_images": total,
            "vision_eligible": pending,
            "vision_skipped_local": 0,
            "estimated_cost_usd": 0.0,
            "saved_by_filter_usd": 0.0,
            "over_limit": False,
            "limit": max_vision_calls_per_job(),
            "status": "no_vision_needed" if pending == 0 else "pending_confirmation",
            "model": _vision_model(),
        }

    return {"doc_id": doc_id, **est}


@router.post("/vision/start/{doc_id}")
async def start_vision_processing(
    doc_id: str,
    body: dict = None,
    db: Session = Depends(get_db),
):
    """
    Start GPT Vision captioning for all eligible images in a document.
    Body (optional JSON):
        override (bool) — allow processing beyond MAX_VISION_CALLS_PER_JOB limit
    """
    from api.db.base import SessionLocal
    from api.services.vision_guard import max_vision_calls_per_job

    override = (body or {}).get("override", False)

    doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    # All images needing captioning (not yet captioned, not locally skipped)
    images = (
        db.query(RagImage)
        .filter(
            RagImage.doc_id == doc_id,
            RagImage.caption.is_(None),
        )
        .all()
    )

    eligible = [img for img in images if not getattr(img, "vision_skipped", False)]

    limit = max_vision_calls_per_job()
    if not override and len(eligible) > limit:
        eligible = eligible[:limit]

    if not eligible:
        return {"started": 0, "message": "No images need captioning"}

    image_ids    = [img.id for img in eligible]
    doc_filename = doc.filename

    async def _run_vision_batch():
        from api.services.image_service import process_rag_image_guarded
        _db = SessionLocal()
        try:
            for img_id in image_ids:
                try:
                    await process_rag_image_guarded(
                        _db, img_id, doc_id=doc_id, doc_filename=doc_filename
                    )
                except Exception as exc:
                    log.warning("Vision caption failed for image %s: %s", img_id, exc)
        finally:
            _db.close()

    asyncio.create_task(_run_vision_batch())

    return {
        "started": len(image_ids),
        "message": f"Vision captioning started for {len(image_ids)} images",
        "doc_id":  doc_id,
    }


@router.post("/vision/skip/{doc_id}")
def skip_vision_processing(doc_id: str, db: Session = Depends(get_db)):
    """Mark all uncaptioned images in a document as user-cancelled."""
    images = (
        db.query(RagImage)
        .filter(
            RagImage.doc_id == doc_id,
            RagImage.caption.is_(None),
        )
        .all()
    )

    count = 0
    for img in images:
        if not getattr(img, "vision_skipped", False):
            img.vision_skipped = True
            img.skip_reason    = "user_cancelled"
            count += 1

    if count:
        db.commit()

    return {"skipped": count, "message": f"{count} images marked as skipped"}


@router.get("/vision/stats")
def get_vision_stats(db: Session = Depends(get_db)):
    """Aggregated cost dashboard — total spent, saved, cache hits, skipped, etc."""
    rows = db.query(VisionCostLog).all()

    if not rows:
        return {
            "total_decisions":   0,
            "actual_calls":      0,
            "cache_hits":        0,
            "skipped_count":     0,
            "total_cost_usd":    0.0,
            "total_saved_usd":   0.0,
            "total_prompt_tokens":     0,
            "total_completion_tokens": 0,
        }

    actual  = sum(1 for r in rows if not r.skipped and not r.cache_hit)
    cached  = sum(1 for r in rows if r.cache_hit)
    skipped = sum(1 for r in rows if r.skipped)

    return {
        "total_decisions":         len(rows),
        "actual_calls":            actual,
        "cache_hits":              cached,
        "skipped_count":           skipped,
        "total_cost_usd":          round(sum(r.cost_usd  or 0 for r in rows), 4),
        "total_saved_usd":         round(sum(r.saved_usd or 0 for r in rows), 4),
        "total_prompt_tokens":     sum(r.prompt_tokens     or 0 for r in rows),
        "total_completion_tokens": sum(r.completion_tokens or 0 for r in rows),
    }


# ── Kill switch ──────────────────────────────────────────────────────────────

def _log_config_change(db: Session, key: str, old_val: str | None, new_val: str,
                        user_id: str | None, reason: str | None = None, source: str = "api"):
    """Write an immutable protection config change record."""
    from api.db.models import ProtectionConfigLog
    try:
        db.add(ProtectionConfigLog(
            config_key=key, old_value=old_val, new_value=new_val,
            user_id=user_id, reason=reason, source=source,
        ))
        db.flush()
    except Exception as exc:
        log.warning("Could not write ProtectionConfigLog: %s", exc)


@router.post("/vision/kill-switch")
def vision_kill_switch(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Emergency disable — immediately blocks all vision processing."""
    from api.services.vision_guard import set_vision_enabled, vision_enabled as _vision_enabled
    from api.db.models import PlatformConfig

    old_cfg = db.query(PlatformConfig).filter(PlatformConfig.key == "vision_enabled").first()
    old_val = old_cfg.value if old_cfg else None

    set_vision_enabled(db, enabled=False, note=f"kill switch triggered by user {user.get('id', '?')}")

    _log_config_change(db, "vision_enabled", old_val, "false",
                        user_id=user.get("id"), reason="Emergency kill switch triggered via dashboard",
                        source="kill_switch")
    db.commit()

    return {"vision_enabled": False, "message": "Vision processing disabled. All image captioning, gallery reindex, and RAG vision calls are now blocked."}


@router.post("/vision/enable")
def vision_enable(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Re-enable vision processing after an emergency disable."""
    from api.services.vision_guard import set_vision_enabled
    from api.db.models import PlatformConfig

    old_cfg = db.query(PlatformConfig).filter(PlatformConfig.key == "vision_enabled").first()
    old_val = old_cfg.value if old_cfg else None

    set_vision_enabled(db, enabled=True, note=f"re-enabled by user {user.get('id', '?')}")

    _log_config_change(db, "vision_enabled", old_val, "true",
                        user_id=user.get("id"), reason="Vision re-enabled via dashboard",
                        source="api")
    db.commit()

    return {"vision_enabled": True, "message": "Vision processing re-enabled."}


# ── Protection dashboard ──────────────────────────────────────────────────────

@router.get("/vision/protection")
def get_vision_protection(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Return full vision protection status:
    limits, current usage, remaining allowance, kill switch state, historical incident.
    """
    from api.services.vision_guard import (
        vision_enabled, max_vision_calls_per_job, max_vision_cost_per_job,
        max_daily_vision_cost, max_monthly_vision_cost, get_current_vision_spend,
    )
    from api.db.models import PlatformConfig

    now = datetime.now(timezone.utc)
    day_start   = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)

    enabled = vision_enabled(db)
    spend   = get_current_vision_spend(db)

    # Check DB config for last toggle
    cfg_row = db.query(PlatformConfig).filter(PlatformConfig.key == "vision_enabled").first()
    kill_switch_set_at = cfg_row.updated_at.isoformat() if (cfg_row and cfg_row.updated_at) else None

    # Current call counts
    daily_calls = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.created_at >= day_start,
        VisionCostLog.skipped == False,
        VisionCostLog.cache_hit == False,
    ).scalar() or 0
    monthly_calls = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.created_at >= month_start,
        VisionCostLog.skipped == False,
        VisionCostLog.cache_hit == False,
    ).scalar() or 0

    lim_calls  = max_vision_calls_per_job()
    lim_cost_j = max_vision_cost_per_job()
    lim_daily  = max_daily_vision_cost()
    lim_month  = max_monthly_vision_cost()

    return {
        "kill_switch": {
            "vision_enabled": enabled,
            "status": "enabled" if enabled else "disabled",
            "set_at": kill_switch_set_at,
            "note": cfg_row.note if cfg_row else "default (env var or factory default)",
        },
        "limits": {
            "max_calls_per_job":    lim_calls,
            "max_cost_per_job_usd": lim_cost_j,
            "max_daily_cost_usd":   lim_daily,
            "max_monthly_cost_usd": lim_month,
        },
        "current_usage": {
            "daily_cost_usd":   round(spend["daily_usd"], 6),
            "monthly_cost_usd": round(spend["monthly_usd"], 6),
            "daily_calls":      int(daily_calls),
            "monthly_calls":    int(monthly_calls),
        },
        "remaining_allowance": {
            "daily_cost_usd":   round(max(0, lim_daily - spend["daily_usd"]), 6),
            "monthly_cost_usd": round(max(0, lim_month - spend["monthly_usd"]), 6),
            "daily_calls":      max(0, lim_calls - int(daily_calls)),
        },
        "historical_incident": {
            "description":    "Previous Image Captioning incident — auto-captioning ran on every uploaded page without user confirmation, resulting in hundreds of unintended GPT Vision calls.",
            "estimated_cost": "$40–55",
            "period":         "Pre-fix (before vision guard was deployed)",
            "status":         "Historical / Not currently active",
            "root_cause":     "process_rag_image() was called automatically on every image extraction with no kill switch, no per-job limit, and no user confirmation dialog.",
            "resolution":     "vision_guard.py deployed with kill switch, SHA-256 dedup, local pixel filter, and per-job limits. VISION_ENABLED=false by default.",
        },
        "protected_operations": [
            "Image captioning (RAG upload pipeline)",
            "Gallery page reindex",
            "RAG page vision analysis",
            "Any feature calling process_rag_image_guarded()",
        ],
    }


# ── 12 permanent vision categories ───────────────────────────────────────────

@router.get("/vision/categories")
def get_vision_categories(
    period: str = "lifetime",
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Return all 12 mandatory vision cost categories.
    Every category is always present even when its value is $0 — the spec
    forbids hiding any high-risk category due to zero value.
    """
    from api.services.vision_guard import (
        vision_enabled, max_daily_vision_cost, max_monthly_vision_cost,
        get_current_vision_spend,
    )
    from api.db.models import UnifiedUsageLog

    now = datetime.now(timezone.utc)
    day_start   = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)

    # Period bounds
    if period == "today":
        since = day_start
    elif period == "7d":
        since = day_start - timedelta(days=7)
    elif period == "30d":
        since = day_start - timedelta(days=30)
    elif period == "month":
        since = month_start
    else:
        since = None   # lifetime

    def _vcl_filter(q):
        if since:
            q = q.filter(VisionCostLog.created_at >= since)
        return q

    def _ul_filter(q):
        if since:
            q = q.filter(UnifiedUsageLog.created_at >= since)
        return q

    enabled = vision_enabled(db)
    spend   = get_current_vision_spend(db)
    daily_blocked  = spend["daily_usd"]  >= max_daily_vision_cost()
    monthly_blocked = spend["monthly_usd"] >= max_monthly_vision_cost()

    def _status(has_data: bool, is_saving_category: bool = False) -> str:
        if is_saving_category:
            return "Active" if has_data else "No usage"
        if not enabled:
            return "Disabled"
        if daily_blocked or monthly_blocked:
            return "Blocked"
        return "Active" if has_data else "No usage"

    def _last(q, col):
        row = q.order_by(col.desc()).first()
        return row.created_at.isoformat() if row and row.created_at else None

    # ── Category 1: Image Captioning (actual GPT calls) ───────────────────────
    q1 = _vcl_filter(db.query(VisionCostLog)).filter(
        VisionCostLog.skipped == False, VisionCostLog.cache_hit == False)
    c1_calls  = q1.count()
    c1_cost   = float(_vcl_filter(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0))).filter(
        VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
    c1_pt     = int(_vcl_filter(db.query(_f.coalesce(_f.sum(VisionCostLog.prompt_tokens), 0))).filter(
        VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
    c1_ct     = int(_vcl_filter(db.query(_f.coalesce(_f.sum(VisionCostLog.completion_tokens), 0))).filter(
        VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
    c1_last   = _vcl_filter(db.query(VisionCostLog)).filter(
        VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).order_by(
        VisionCostLog.created_at.desc()).first()
    c1_last_at = c1_last.created_at.isoformat() if c1_last else None

    # ── Category 2: Vision Analysis (all real calls, including gallery/RAG) ──
    q2 = _ul_filter(db.query(UnifiedUsageLog)).filter(
        UnifiedUsageLog.sub_feature.ilike("%vision%"))
    c2_calls = q2.count()
    c2_cost  = float(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0))).filter(
        UnifiedUsageLog.sub_feature.ilike("%vision%")).scalar() or 0) + c1_cost
    c2_calls += c1_calls
    c2_pt    = int(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens), 0))).filter(
        UnifiedUsageLog.sub_feature.ilike("%vision%")).scalar() or 0) + c1_pt
    c2_ct    = int(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.completion_tokens), 0))).filter(
        UnifiedUsageLog.sub_feature.ilike("%vision%")).scalar() or 0) + c1_ct

    # ── Category 3: GPT Vision Calls (all calls across unified log) ───────────
    q3 = _ul_filter(db.query(UnifiedUsageLog)).filter(
        (UnifiedUsageLog.sub_feature.ilike("%vision%")) |
        (UnifiedUsageLog.sub_feature.ilike("%image%")) |
        (UnifiedUsageLog.feature.ilike("%image%")) |
        (UnifiedUsageLog.feature.ilike("%vision%")) |
        (UnifiedUsageLog.feature.ilike("%captioning%"))
    )
    c3_calls = q3.count()
    c3_cost  = float(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0))).filter(
        (UnifiedUsageLog.sub_feature.ilike("%vision%")) |
        (UnifiedUsageLog.sub_feature.ilike("%image%")) |
        (UnifiedUsageLog.feature.ilike("%image%")) |
        (UnifiedUsageLog.feature.ilike("%vision%"))).scalar() or 0) + c1_cost

    # ── Category 4: Image OCR (image_label_extraction) ───────────────────────
    q4 = _ul_filter(db.query(UnifiedUsageLog)).filter(
        UnifiedUsageLog.sub_feature == "image_label_extraction")
    c4_calls = q4.count()
    c4_cost  = float(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0))).filter(
        UnifiedUsageLog.sub_feature == "image_label_extraction").scalar() or 0)
    c4_pt    = int(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens), 0))).filter(
        UnifiedUsageLog.sub_feature == "image_label_extraction").scalar() or 0)
    c4_ct    = int(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.completion_tokens), 0))).filter(
        UnifiedUsageLog.sub_feature == "image_label_extraction").scalar() or 0)

    # ── Category 5: Image Embeddings (text-embedding API — not yet tracked) ──
    # Embeddings go through a different API endpoint (embeddings.create) and are
    # not currently wired to the usage recorder. They appear here permanently at
    # $0 until that instrumentation is added.
    c5_calls = 0
    c5_cost  = 0.0

    # ── Category 6: Training Image Analysis ──────────────────────────────────
    q6 = _ul_filter(db.query(UnifiedUsageLog)).filter(
        UnifiedUsageLog.feature == "Training Generator")
    c6_calls = q6.count()
    c6_cost  = float(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0))).filter(
        UnifiedUsageLog.feature == "Training Generator").scalar() or 0)

    # ── Category 7: Learning Hub Image Analysis ──────────────────────────────
    # Learning Hub uses text-only GPT calls; vision not separately tracked.
    c7_calls = 0; c7_cost = 0.0

    # ── Category 8: Innovation Image Analysis ────────────────────────────────
    q8 = _ul_filter(db.query(UnifiedUsageLog)).filter(
        UnifiedUsageLog.feature == "Innovation Engine")
    c8_calls = q8.count()
    c8_cost  = float(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0))).filter(
        UnifiedUsageLog.feature == "Innovation Engine").scalar() or 0)

    # ── Category 9: Untracked Vision Charges ─────────────────────────────────
    # Vision calls in gallery/RAG that go through provider (not VisionCostLog)
    q9 = _ul_filter(db.query(UnifiedUsageLog)).filter(
        (UnifiedUsageLog.feature == "Gallery Reindex") |
        (UnifiedUsageLog.feature == "RAG Vision Analysis"))
    c9_calls = q9.count()
    c9_cost  = float(_ul_filter(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0))).filter(
        (UnifiedUsageLog.feature == "Gallery Reindex") |
        (UnifiedUsageLog.feature == "RAG Vision Analysis")).scalar() or 0)

    # ── Category 10: Blocked Vision Requests ─────────────────────────────────
    q10 = _vcl_filter(db.query(VisionCostLog)).filter(
        VisionCostLog.skipped == True,
        VisionCostLog.skip_reason.in_(["vision_disabled", "daily_limit_exceeded", "monthly_limit_exceeded"]))
    c10_calls  = q10.count()
    c10_saved  = float(_vcl_filter(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0))).filter(
        VisionCostLog.skipped == True,
        VisionCostLog.skip_reason.in_(["vision_disabled", "daily_limit_exceeded", "monthly_limit_exceeded"])).scalar() or 0)
    c10_last   = _vcl_filter(db.query(VisionCostLog)).filter(
        VisionCostLog.skipped == True).order_by(VisionCostLog.created_at.desc()).first()

    # ── Category 11: Vision Cache Savings ────────────────────────────────────
    q11 = _vcl_filter(db.query(VisionCostLog)).filter(VisionCostLog.cache_hit == True)
    c11_hits  = q11.count()
    c11_saved = float(_vcl_filter(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0))).filter(
        VisionCostLog.cache_hit == True).scalar() or 0)

    # ── Category 12: Vision Deduplication Savings ─────────────────────────────
    q12 = _vcl_filter(db.query(VisionCostLog)).filter(
        VisionCostLog.skip_reason == "sha256_cache_hit")
    c12_hits  = q12.count()
    c12_saved = float(_vcl_filter(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0))).filter(
        VisionCostLog.skip_reason == "sha256_cache_hit").scalar() or 0)

    # Total blocked count for all categories
    total_blocked = int(_vcl_filter(db.query(_f.count(VisionCostLog.id))).filter(
        VisionCostLog.skipped == True,
        VisionCostLog.skip_reason.in_(["vision_disabled", "daily_limit_exceeded", "monthly_limit_exceeded"])).scalar() or 0)
    total_cache_hits = int(_vcl_filter(db.query(_f.count(VisionCostLog.id))).filter(
        VisionCostLog.cache_hit == True).scalar() or 0)
    total_dupe_skipped = int(_vcl_filter(db.query(_f.count(VisionCostLog.id))).filter(
        VisionCostLog.skip_reason == "sha256_cache_hit").scalar() or 0)
    total_saved = float(_vcl_filter(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0))).scalar() or 0)

    def _cat(name, cost, requests, images, tokens, cache_hits, dupes_skipped, blocked,
             cost_avoided, last_at, is_saving=False, note=None):
        return {
            "name": name,
            "cost_usd": round(cost, 6),
            "requests": requests,
            "images": images,
            "tokens": tokens,
            "cache_hits": cache_hits,
            "duplicate_images_skipped": dupes_skipped,
            "requests_blocked": blocked,
            "estimated_cost_avoided_usd": round(cost_avoided, 6),
            "last_activity": last_at,
            "status": _status(cost > 0 or requests > 0, is_saving_category=is_saving),
            "note": note,
        }

    categories = [
        _cat("Image Captioning",           c1_cost, c1_calls,  c1_calls, c1_pt+c1_ct,
             total_cache_hits, total_dupe_skipped, total_blocked, total_saved, c1_last_at),
        _cat("Vision Analysis",            c2_cost, c2_calls,  c2_calls, c2_pt+c2_ct,
             total_cache_hits, total_dupe_skipped, total_blocked, total_saved, None),
        _cat("GPT Vision Calls",           c3_cost, c3_calls,  c3_calls, 0,
             total_cache_hits, total_dupe_skipped, total_blocked, total_saved, None),
        _cat("Image OCR",                  c4_cost, c4_calls,  c4_calls, c4_pt+c4_ct,
             0, 0, 0, 0.0, None,
             note="Image text label extraction via gpt-4o-mini in Translation Studio"),
        _cat("Image Embeddings",           c5_cost, c5_calls,  0,        0,
             0, 0, 0, 0.0, None,
             note="text-embedding-3-small calls not yet wired to usage recorder — will be $0 until instrumented"),
        _cat("Training Image Analysis",    c6_cost, c6_calls,  0,        0,
             0, 0, 0, 0.0, None,
             note="Training slide generation may process figures; tracked at feature level"),
        _cat("Learning Hub Image Analysis",c7_cost, c7_calls,  0,        0,
             0, 0, 0, 0.0, None,
             note="Learning Hub uses text-only calls; vision not separately tracked"),
        _cat("Innovation Image Analysis",  c8_cost, c8_calls,  0,        0,
             0, 0, 0, 0.0, None,
             note="Innovation Engine gpt-5.4 calls; may include inline images via API"),
        _cat("Untracked Vision Charges",   c9_cost, c9_calls,  0,        0,
             0, 0, 0, 0.0, None,
             note="Gallery Reindex + RAG Vision now tracked via openai_usage_log since fix"),
        _cat("Blocked Vision Requests",    0.0, c10_calls, c10_calls, 0,
             0, 0, c10_calls, c10_saved, c10_last.created_at.isoformat() if c10_last else None,
             is_saving=True, note="Requests blocked by kill switch or daily/monthly limits"),
        _cat("Vision Cache Savings",       0.0, c11_hits, c11_hits, 0,
             c11_hits, 0, 0, c11_saved, None,
             is_saving=True, note="SHA-256 cache hits reused existing captions"),
        _cat("Vision Deduplication Savings",0.0, c12_hits, c12_hits, 0,
             0, c12_hits, 0, c12_saved, None,
             is_saving=True, note="Identical images detected and skipped via SHA-256 hash"),
    ]

    return {
        "period": period,
        "vision_enabled": enabled,
        "categories": categories,
        "totals": {
            "total_cost_usd":     round(c1_cost, 6),
            "total_saved_usd":    round(total_saved, 6),
            "total_calls":        c1_calls,
            "total_cache_hits":   total_cache_hits,
            "total_dupes_skipped": total_dupe_skipped,
            "total_blocked":      total_blocked,
        },
    }


# ── Vision-specific alerts ────────────────────────────────────────────────────

@router.get("/vision/alerts")
def get_vision_alerts(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Return vision-specific cost alerts per the protection spec."""
    from api.services.vision_guard import (
        vision_enabled, get_current_vision_spend,
        max_daily_vision_cost, max_monthly_vision_cost,
    )

    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    enabled = vision_enabled(db)
    spend   = get_current_vision_spend(db)
    alerts  = []

    # Alert 1: vision disabled while there were blocked calls (informational)
    if not enabled:
        blocked_today = db.query(_f.count(VisionCostLog.id)).filter(
            VisionCostLog.created_at >= day_start,
            VisionCostLog.skip_reason == "vision_disabled",
        ).scalar() or 0
        if blocked_today:
            alerts.append({
                "level": "info", "type": "vision_used_while_disabled",
                "message": f"Vision was called {blocked_today}× today while disabled — {blocked_today} requests blocked.",
                "value": int(blocked_today),
            })

    # Alert 2: vision cost above $0.10 today
    if spend["daily_usd"] > 0.10:
        alerts.append({
            "level": "warning" if spend["daily_usd"] < 1.00 else "error",
            "type": "vision_cost_above_threshold",
            "message": f"Vision cost today: ${spend['daily_usd']:.4f} (threshold: $0.10)",
            "value": spend["daily_usd"],
        })

    # Alert 3: more than 5 vision calls in any single job today
    # Proxy: more than 5 actual vision calls today total (per-job tracking requires job ID)
    calls_today = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.created_at >= day_start,
        VisionCostLog.skipped == False,
        VisionCostLog.cache_hit == False,
    ).scalar() or 0
    if calls_today > 5:
        alerts.append({
            "level": "warning",
            "type": "high_vision_call_count",
            "message": f"{calls_today} GPT Vision calls made today — review if a single job triggered many calls.",
            "value": int(calls_today),
        })

    # Alert 4: duplicate image analysis detected
    dup_count = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.cache_hit == True,
        VisionCostLog.created_at >= day_start,
    ).scalar() or 0
    actual_today = calls_today
    if dup_count > 0 and actual_today > 0:
        alerts.append({
            "level": "info",
            "type": "duplicate_image_analysis",
            "message": f"{dup_count} duplicate image(s) detected and served from cache today — ${dup_count * 0.002:.4f} saved.",
            "value": dup_count,
        })

    # Alert 5: untracked vision request (gallery/RAG from unified log today)
    from api.db.models import UnifiedUsageLog
    untracked_today = db.query(_f.count(UnifiedUsageLog.id)).filter(
        UnifiedUsageLog.created_at >= day_start,
        ((UnifiedUsageLog.feature == "Gallery Reindex") |
         (UnifiedUsageLog.feature == "RAG Vision Analysis")),
    ).scalar() or 0
    if untracked_today > 0:
        untracked_cost = float(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0)).filter(
            UnifiedUsageLog.created_at >= day_start,
            ((UnifiedUsageLog.feature == "Gallery Reindex") |
             (UnifiedUsageLog.feature == "RAG Vision Analysis")),
        ).scalar() or 0)
        alerts.append({
            "level": "info",
            "type": "untracked_vision_request",
            "message": f"{untracked_today} vision call(s) from Gallery Reindex / RAG Vision today (${untracked_cost:.4f}).",
            "value": untracked_today,
        })

    # Alert 6: daily limit approaching / exceeded
    daily_lim = max_daily_vision_cost()
    if spend["daily_usd"] >= daily_lim:
        alerts.append({
            "level": "error",
            "type": "daily_vision_limit_exceeded",
            "message": f"Daily vision limit ${daily_lim:.2f} exceeded — new calls are blocked.",
            "value": spend["daily_usd"],
            "limit": daily_lim,
        })
    elif spend["daily_usd"] > daily_lim * 0.75:
        alerts.append({
            "level": "warning",
            "type": "daily_vision_limit_approaching",
            "message": f"Daily vision spend ${spend['daily_usd']:.4f} is at {round(spend['daily_usd']/daily_lim*100)}% of limit ${daily_lim:.2f}.",
            "value": spend["daily_usd"],
            "limit": daily_lim,
        })

    return {
        "alerts": alerts,
        "vision_enabled": enabled,
        "daily_spend_usd":   round(spend["daily_usd"], 6),
        "monthly_spend_usd": round(spend["monthly_usd"], 6),
    }


@router.get("/vision/logs")
def get_vision_logs(
    limit:  int            = 100,
    doc_id: Optional[str]  = None,
    db:     Session        = Depends(get_db),
):
    """Full audit log of every vision decision (API call / cache hit / skip)."""
    q = db.query(VisionCostLog)
    if doc_id:
        q = q.filter(VisionCostLog.doc_id == doc_id)

    rows = q.order_by(VisionCostLog.created_at.desc()).limit(limit).all()

    return [
        {
            "id":               r.id,
            "image_id":         r.image_id,
            "doc_id":           r.doc_id,
            "doc_filename":     r.doc_filename,
            "page_num":         r.page_num,
            "model":            r.model,
            "prompt_tokens":    r.prompt_tokens,
            "completion_tokens":r.completion_tokens,
            "cost_usd":         r.cost_usd,
            "cache_hit":        r.cache_hit,
            "skipped":          r.skipped,
            "skip_reason":      r.skip_reason,
            "saved_usd":        r.saved_usd,
            "created_at":       r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
