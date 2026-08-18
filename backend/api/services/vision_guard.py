"""
Vision Cost Protection System.

Guards GPT Vision calls with:
1. Local pixel analysis  — classify images without any API call (Pillow)
2. SHA-256 deduplication — reuse captions for identical images
3. Hard per-job limit    — stop at MAX_VISION_CALLS_PER_JOB (default 20)
4. Pre-flight estimation — cost estimate before any call is made
5. Full audit log        — every decision written to vision_cost_log table
"""
from __future__ import annotations

import hashlib
import io
import logging
import math
import os
from collections import Counter
from typing import Optional

log = logging.getLogger(__name__)

# ── Model pricing (USD per 1M tokens: input, output) ─────────────────────────

_VISION_PRICES: dict[str, tuple[float, float]] = {
    "gpt-4o":      (2.50,  10.00),
    "gpt-4o-mini": (0.15,   0.60),
    "gpt-4.1":     (2.00,   8.00),
    "gpt-5.4":     (21.50, 85.00),   # conservative — override via VISION_INPUT_PRICE / VISION_OUTPUT_PRICE
    "gpt-4-turbo": (10.00, 30.00),
}
_DEFAULT_PRICE = (21.50, 85.00)


def _vision_model() -> str:
    return (os.environ.get("VISION_CAPTION_MODEL") or "gpt-4o").strip() or "gpt-4o"


def _price_for(model: str) -> tuple[float, float]:
    # Allow env overrides
    custom_in  = os.environ.get("VISION_INPUT_PRICE")
    custom_out = os.environ.get("VISION_OUTPUT_PRICE")
    if custom_in and custom_out:
        try:
            return float(custom_in), float(custom_out)
        except ValueError:
            pass
    for key, price in _VISION_PRICES.items():
        if model.startswith(key):
            return price
    return _DEFAULT_PRICE


def vision_enabled(db=None) -> bool:
    """
    Global Vision kill switch.

    Priority order:
    1. PlatformConfig DB table (key="vision_enabled") — set by the emergency button.
    2. VISION_ENABLED environment variable.
    3. Default: False (Vision is OFF by default).
    """
    if db is not None:
        try:
            from api.db.models import PlatformConfig
            row = db.query(PlatformConfig).filter(PlatformConfig.key == "vision_enabled").first()
            if row is not None:
                return (row.value or "").strip().lower() == "true"
        except Exception as exc:
            log.debug("PlatformConfig vision_enabled check failed: %s", exc)
    env = os.environ.get("VISION_ENABLED", "false").strip().lower()
    return env == "true"


def set_vision_enabled(db, enabled: bool, note: str = "") -> None:
    """Write the vision_enabled toggle to the DB config table."""
    try:
        from api.db.models import PlatformConfig
        from datetime import datetime, timezone
        row = db.query(PlatformConfig).filter(PlatformConfig.key == "vision_enabled").first()
        if row is None:
            row = PlatformConfig(key="vision_enabled")
            db.add(row)
        row.value = "true" if enabled else "false"
        row.note  = note or ("enabled" if enabled else "disabled via kill switch")
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
    except Exception as exc:
        log.error("set_vision_enabled failed: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass


def max_vision_calls_per_job() -> int:
    try:
        return max(1, int(os.environ.get("MAX_VISION_CALLS_PER_JOB") or 10))
    except ValueError:
        return 10


def max_vision_cost_per_job() -> float:
    try:
        return max(0.01, float(os.environ.get("MAX_VISION_COST_PER_JOB_USD") or 0.50))
    except ValueError:
        return 0.50


def max_daily_vision_cost() -> float:
    try:
        return max(0.01, float(os.environ.get("MAX_DAILY_VISION_COST_USD") or 2.00))
    except ValueError:
        return 2.00


def max_monthly_vision_cost() -> float:
    try:
        return max(0.01, float(os.environ.get("MAX_MONTHLY_VISION_COST_USD") or 10.00))
    except ValueError:
        return 10.00


def get_current_vision_spend(db) -> dict:
    """Query VisionCostLog for today's and this month's actual spend."""
    try:
        from datetime import datetime, timezone, timedelta
        from api.db.models import VisionCostLog
        from sqlalchemy import func as _f

        now = datetime.now(timezone.utc)
        day_start   = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)

        daily = float(
            db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0))
            .filter(VisionCostLog.created_at >= day_start, VisionCostLog.skipped == False)
            .scalar() or 0
        )
        monthly = float(
            db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0))
            .filter(VisionCostLog.created_at >= month_start, VisionCostLog.skipped == False)
            .scalar() or 0
        )
        return {"daily_usd": round(daily, 6), "monthly_usd": round(monthly, 6)}
    except Exception as exc:
        log.debug("get_current_vision_spend failed: %s", exc)
        return {"daily_usd": 0.0, "monthly_usd": 0.0}


# ── SHA-256 ───────────────────────────────────────────────────────────────────

def compute_image_sha256(image_bytes: bytes) -> str:
    return hashlib.sha256(image_bytes).hexdigest()


# ── Local image analysis ──────────────────────────────────────────────────────

def analyze_image_locally(image_bytes: bytes, filename: str) -> dict:
    """
    Classify an image without any API call using Pillow pixel analysis.

    Returns:
        {
            "should_caption": bool,
            "reason": str,      — machine label for the decision
            "width": int,
            "height": int,
        }
    """
    try:
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
        base = {"width": w, "height": h}

        # ── SKIP rules ───────────────────────────────────────────────────────

        # R1: Tiny images — icons, bullets, shape markers
        if w < 80 or h < 80:
            return {**base, "should_caption": False, "reason": "icon_too_small"}

        if w * h < 8_000:
            return {**base, "should_caption": False, "reason": "pixel_area_tiny"}

        # R2: Divider / line-separator (very elongated)
        long_side  = max(w, h)
        short_side = min(w, h)
        if long_side / max(short_side, 1) > 8:
            return {**base, "should_caption": False, "reason": "divider_shape"}

        # R3: Downsample to 64×64 for fast pixel analysis (4096 pixels)
        small = img.resize((64, 64)).convert("RGB")
        pixels = list(small.getdata())
        n = len(pixels)  # always 4096

        # R4: Mostly white — text slide background / blank area
        white = sum(1 for r, g, b in pixels if r > 220 and g > 220 and b > 220)
        if white / n > 0.88:
            return {**base, "should_caption": False, "reason": "mostly_white_text_slide"}

        # R5: Dominant single bucket — solid shape / section divider
        # Bin each channel to 8 buckets (>> 5), then count most common
        bucketed = [(r >> 5, g >> 5, b >> 5) for r, g, b in pixels]
        top_count = Counter(bucketed).most_common(1)[0][1]
        if top_count / n > 0.65:
            return {**base, "should_caption": False, "reason": "solid_color_shape"}

        # R6: Very low colour variety — simple icon / logo
        unique_colors = len(set(pixels))
        if unique_colors < 25:
            return {**base, "should_caption": False, "reason": "low_color_variety_icon"}

        # ── SEND rules ───────────────────────────────────────────────────────

        # R7: Grayscale dominant — X-ray, radiographic, CT scan
        gray = sum(
            1 for r, g, b in pixels
            if abs(int(r) - int(g)) < 20 and abs(int(g) - int(b)) < 20
        )
        if gray / n > 0.72:
            return {**base, "should_caption": True, "reason": "xray_grayscale_dominant"}

        # R8: Filename keyword hints
        name = filename.lower()
        xray_kw = ["xray", "x-ray", "scan", "ct_", "_ct", "radiograph", "backscatter"]
        if any(kw in name for kw in xray_kw):
            return {**base, "should_caption": True, "reason": "filename_xray_keyword"}
        diag_kw = ["diagram", "schematic", "drawing", "blueprint", "circuit", "wiring"]
        if any(kw in name for kw in diag_kw):
            return {**base, "should_caption": True, "reason": "filename_diagram_keyword"}

        # R9: Complex — high colour variety + adequate dimensions
        if unique_colors > 500 and w >= 200 and h >= 200:
            return {**base, "should_caption": True, "reason": "complex_diagram_photo"}

        # R10: Medium complexity — enough non-white content to warrant captioning
        if unique_colors > 150 and w >= 150 and h >= 150:
            non_white = n - white
            if non_white / n > 0.30:
                return {**base, "should_caption": True, "reason": "content_rich_image"}

        # Default: not complex enough
        return {**base, "should_caption": False, "reason": "simple_content_below_threshold"}

    except Exception as exc:
        log.warning("Local image analysis failed for %s: %s", filename, exc)
        return {"width": 0, "height": 0, "should_caption": True, "reason": "analysis_error_fallback"}


# ── Token / cost estimation ───────────────────────────────────────────────────

def estimate_vision_tokens(image_bytes: bytes) -> dict:
    """
    Estimate prompt/completion tokens for one vision caption call.
    Follows OpenAI's tile-counting formula for auto-detail mode.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        w, h = img.size
    except Exception:
        w, h = 512, 512  # safe fallback

    # Step 1 — fit inside 2048×2048
    max_dim = max(w, h)
    if max_dim > 2048:
        scale = 2048 / max_dim
        w, h = int(w * scale), int(h * scale)

    # Step 2 — scale short side to ≤ 768
    short_side = min(w, h)
    if short_side > 768:
        scale = 768 / short_side
        w, h = int(w * scale), int(h * scale)

    # Step 3 — count 512×512 tiles (OpenAI high-detail formula)
    tiles = math.ceil(w / 512) * math.ceil(h / 512)
    image_tokens   = 85 + 170 * tiles
    prompt_tokens  = image_tokens + 100   # ~100 tokens for fixed text prompt
    completion_tokens = 150               # ~120 words output

    model = _vision_model()
    pin, pout = _price_for(model)
    cost_usd = (prompt_tokens * pin + completion_tokens * pout) / 1_000_000

    return {
        "prompt_tokens":     prompt_tokens,
        "completion_tokens": completion_tokens,
        "cost_usd":          round(cost_usd, 6),
        "model":             model,
    }


# ── Pre-flight batch estimate ─────────────────────────────────────────────────

def estimate_batch(image_records: list[dict]) -> dict:
    """
    Run local analysis on all extracted images from one document.
    Returns a pre-flight estimate dict (safe to JSON-serialise and store on RagDocument).

    ``image_records`` should have at minimum: "name" (str), "data" (bytes), "page_num" (int).
    """
    limit  = max_vision_calls_per_job()
    model  = _vision_model()
    pin, pout = _price_for(model)
    # Estimated cost-per-call if a locally-skipped image had NOT been filtered
    avg_skipped_cost = ((800 * pin) + (150 * pout)) / 1_000_000

    vision_eligible: list[dict] = []
    skipped_local:   list[dict] = []

    for rec in image_records:
        result = analyze_image_locally(rec["data"], rec["name"])
        sha    = compute_image_sha256(rec["data"])
        entry  = {
            "name":     rec["name"],
            "page_num": rec.get("page_num", 0),
            "sha256":   sha,
            "width":    result["width"],
            "height":   result["height"],
            "reason":   result["reason"],
        }
        if result["should_caption"]:
            tok = estimate_vision_tokens(rec["data"])
            entry.update(tok)
            vision_eligible.append(entry)
        else:
            entry.update({"cost_usd": 0.0, "prompt_tokens": 0, "completion_tokens": 0})
            skipped_local.append(entry)

    vision_count  = len(vision_eligible)
    est_cost      = sum(e["cost_usd"] for e in vision_eligible)
    saved_by_filter = len(skipped_local) * avg_skipped_cost

    # Strip raw bytes from eligible_images list; keep metadata only
    eligible_meta = [
        {k: v for k, v in e.items() if k not in ("data",)}
        for e in vision_eligible
    ]

    return {
        "model":                       model,
        "total_images":                len(image_records),
        "vision_eligible":             vision_count,
        "vision_skipped_local":        len(skipped_local),
        "estimated_prompt_tokens":     sum(e["prompt_tokens"]     for e in vision_eligible),
        "estimated_completion_tokens": sum(e["completion_tokens"] for e in vision_eligible),
        "estimated_cost_usd":          round(est_cost,        4),
        "saved_by_filter_usd":         round(saved_by_filter, 4),
        "over_limit":                  vision_count > limit,
        "limit":                       limit,
        "status":                      "pending_confirmation" if vision_count > 0 else "no_vision_needed",
        "eligible_images":             eligible_meta,
    }


# ── SHA-256 cache lookup ──────────────────────────────────────────────────────

def find_cached_caption(db, sha256: str) -> Optional[str]:
    """
    Return an existing caption for any RagImage with the same SHA-256 hash.
    Returns None if no cached caption exists.
    """
    if not sha256:
        return None
    try:
        from api.db.models import RagImage
        existing = (
            db.query(RagImage)
            .filter(
                RagImage.image_sha256 == sha256,
                RagImage.caption.isnot(None),
                RagImage.caption != "",
            )
            .first()
        )
        return existing.caption if existing else None
    except Exception as exc:
        log.debug("Cache lookup failed for sha256 %s: %s", sha256[:8], exc)
        return None


# ── Audit log write ───────────────────────────────────────────────────────────

def log_vision_decision(
    db,
    *,
    image_id:          str,
    doc_id:            str,
    doc_filename:      str,
    page_num:          int,
    image_sha256:      str,
    model:             str,
    prompt_tokens:     int,
    completion_tokens: int,
    cost_usd:          float,
    cache_hit:         bool,
    skipped:           bool,
    skip_reason:       str,
    saved_usd:         float,
) -> None:
    """Write a VisionCostLog record.  Best-effort — never raises."""
    try:
        import uuid
        from api.db.models import VisionCostLog
        row = VisionCostLog(
            id=str(uuid.uuid4()),
            image_id=image_id,
            doc_id=doc_id,
            doc_filename=doc_filename,
            page_num=page_num,
            image_sha256=image_sha256,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=cost_usd,
            cache_hit=cache_hit,
            skipped=skipped,
            skip_reason=skip_reason,
            saved_usd=saved_usd,
        )
        db.add(row)
        db.commit()
    except Exception as exc:
        log.warning("VisionCostLog write failed (non-fatal): %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
