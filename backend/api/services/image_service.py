"""
Image captioning, embedding, and semantic search for the RAG image pipeline.

Flow:
  upload → extract_images() stores raw bytes
         → process_rag_image() captions via GPT-5.4 vision
                               embeds caption via text-embedding-3-small
                               persists caption + embedding to DB

  query  → search_images_semantic() embeds query
                                    cosine-similarity ranks stored image embeddings
                                    falls back to keyword search on captions + filenames
"""
from __future__ import annotations
import base64
import io
import math
import os
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from api.db.models import RagImage


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _openai_client():
    from openai import AsyncOpenAI
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return AsyncOpenAI(api_key=key)


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def _to_png_bytes(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    """
    Normalise any image format to PNG using Pillow.
    Returns (png_bytes, "image/png").
    Falls back to the original bytes if Pillow cannot decode them.
    """
    try:
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
        out = io.BytesIO()
        img.save(out, format="PNG")
        return out.getvalue(), "image/png"
    except Exception:
        return image_bytes, mime_type


# ──────────────────────────────────────────────────────────
# Caption via GPT-5.4 vision
# ──────────────────────────────────────────────────────────

async def caption_image(
    image_bytes: bytes,
    mime_type: str,
    filename: str,
    doc_filename: str,
    page_num: int,
) -> str:
    """
    Ask GPT-5.4 vision to write a concise, searchable technical caption
    for a figure extracted from a PDF document.
    """
    client = _openai_client()
    # Normalise to PNG first (more reliable for the vision API)
    png_bytes, png_mime = _to_png_bytes(image_bytes, mime_type)
    b64 = base64.b64encode(png_bytes).decode()

    prompt = (
        f"This image was extracted from page {page_num} of the document '{doc_filename}'. "
        "Write a concise technical caption (≤120 words) optimised for retrieval search. "
        "Include: the image type (diagram, photograph, schematic, chart, screenshot, etc.), "
        "exactly what it depicts, any labels or text visible in the image, "
        "and the relevant technical domain (e.g. X-ray security scanner, baggage screening, "
        "vehicle inspection, detector array, etc.). "
        "Start directly with the content — do NOT write 'The image shows' or 'This is a'."
    )

    response = await client.chat.completions.create(
        model="gpt-5.4",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{png_mime};base64,{b64}"}},
            ],
        }],
        max_completion_tokens=200,
    )
    return (response.choices[0].message.content or filename).strip()


# ──────────────────────────────────────────────────────────
# Text embedding
# ──────────────────────────────────────────────────────────

async def embed_text(text: str) -> Optional[List[float]]:
    """Generate a text-embedding-3-small embedding."""
    try:
        client = _openai_client()
        resp = await client.embeddings.create(
            input=text[:8000],
            model="text-embedding-3-small",
        )
        return resp.data[0].embedding
    except Exception:
        return None


# ──────────────────────────────────────────────────────────
# Background processing — called after image is stored
# ──────────────────────────────────────────────────────────

async def process_rag_image(db, image_id: str) -> None:
    """
    Load a stored RagImage, generate a GPT-5.4 caption, embed it, and persist.
    Designed to run as a fire-and-forget background task.
    LEGACY: called directly without vision guard.  Prefer process_rag_image_guarded.
    """
    from api.db.crud import get_rag_image, update_rag_image_embedding

    img = get_rag_image(db, image_id)
    if not img or not img.image_data:
        return

    try:
        caption = await caption_image(
            img.image_data, img.mime_type,
            img.filename, img.doc_filename, img.page_num,
        )
        # Embed "caption + doc name + page" so both content and provenance are searchable
        embed_input = f"{caption}\nDocument: {img.doc_filename}\nPage: {img.page_num}"
        embedding = await embed_text(embed_input)
        update_rag_image_embedding(db, image_id, caption, embedding)
    except Exception:
        pass  # captioning failure must never crash the upload


async def process_rag_image_guarded(
    db,
    image_id: str,
    *,
    doc_id: str = "",
    doc_filename: str = "",
) -> None:
    """
    Vision-guard-aware caption pipeline:
    1. KILL SWITCH — abort immediately if vision_enabled is False.
    2. Skip if already captioned or locally marked as skipped.
    3. DAILY / MONTHLY LIMIT — abort if spend ceiling is reached.
    4. Check SHA-256 cache — reuse caption for duplicate images.
    5. Call GPT Vision.
    6. Write a VisionCostLog audit record for every decision.
    """
    import logging as _log
    log = _log.getLogger(__name__)

    from api.db.crud import get_rag_image, update_rag_image_embedding
    from api.db.models import RagImage
    from api.services.vision_guard import (
        find_cached_caption, log_vision_decision,
        estimate_vision_tokens, _vision_model, _price_for,
        vision_enabled, get_current_vision_spend,
        max_daily_vision_cost, max_monthly_vision_cost,
    )

    # ── 1. Kill switch ────────────────────────────────────────────────────────
    if not vision_enabled(db):
        log.info("Vision processing blocked: vision_enabled=false (image %s)", image_id)
        # Log the block so the dashboard can count it
        img_block = get_rag_image(db, image_id)
        if img_block:
            log_vision_decision(
                db,
                image_id=image_id,
                doc_id=doc_id or getattr(img_block, "doc_id", ""),
                doc_filename=doc_filename or getattr(img_block, "doc_filename", ""),
                page_num=getattr(img_block, "page_num", 0),
                image_sha256=getattr(img_block, "image_sha256", "") or "",
                model=_vision_model(),
                prompt_tokens=0, completion_tokens=0,
                cost_usd=0.0, cache_hit=False,
                skipped=True, skip_reason="vision_disabled",
                saved_usd=0.0,
            )
        return

    img = get_rag_image(db, image_id)
    if not img or not img.image_data:
        return

    # Already captioned — nothing to do
    if img.caption:
        return

    # Locally skipped during pre-flight — honour the decision
    if getattr(img, "vision_skipped", False):
        return

    sha    = getattr(img, "image_sha256", None) or ""
    model  = _vision_model()
    tok    = estimate_vision_tokens(img.image_data)
    pin, pout = _price_for(model)

    _doc_id       = doc_id or img.doc_id
    _doc_filename = doc_filename or img.doc_filename

    # ── 3. Daily / monthly spend guard ───────────────────────────────────────
    spend = get_current_vision_spend(db)
    if spend["daily_usd"] >= max_daily_vision_cost():
        log.warning("Vision blocked: daily limit $%.4f reached (image %s)", max_daily_vision_cost(), image_id)
        log_vision_decision(
            db, image_id=image_id, doc_id=_doc_id, doc_filename=_doc_filename,
            page_num=img.page_num, image_sha256=sha, model=model,
            prompt_tokens=0, completion_tokens=0, cost_usd=0.0,
            cache_hit=False, skipped=True, skip_reason="daily_limit_exceeded",
            saved_usd=tok["cost_usd"],
        )
        return
    if spend["monthly_usd"] >= max_monthly_vision_cost():
        log.warning("Vision blocked: monthly limit $%.4f reached (image %s)", max_monthly_vision_cost(), image_id)
        log_vision_decision(
            db, image_id=image_id, doc_id=_doc_id, doc_filename=_doc_filename,
            page_num=img.page_num, image_sha256=sha, model=model,
            prompt_tokens=0, completion_tokens=0, cost_usd=0.0,
            cache_hit=False, skipped=True, skip_reason="monthly_limit_exceeded",
            saved_usd=tok["cost_usd"],
        )
        return

    # ── 4. SHA-256 cache ─────────────────────────────────────────────────────
    if sha:
        cached = find_cached_caption(db, sha)
        if cached:
            embed_input = f"{cached}\nDocument: {img.doc_filename}\nPage: {img.page_num}"
            embedding   = await embed_text(embed_input)
            update_rag_image_embedding(db, image_id, cached, embedding)
            log_vision_decision(
                db,
                image_id=image_id,
                doc_id=_doc_id,
                doc_filename=_doc_filename,
                page_num=img.page_num,
                image_sha256=sha,
                model=model,
                prompt_tokens=0,
                completion_tokens=0,
                cost_usd=0.0,
                cache_hit=True,
                skipped=False,
                skip_reason="sha256_cache_hit",
                saved_usd=tok["cost_usd"],
            )
            return

    # ── 5. GPT Vision call ────────────────────────────────────────────────────
    try:
        import time as _time
        _t0 = _time.monotonic()
        caption = await caption_image(
            img.image_data, img.mime_type,
            img.filename, img.doc_filename, img.page_num,
        )
        _dur_ms = int((_time.monotonic() - _t0) * 1000)
        embed_input = f"{caption}\nDocument: {img.doc_filename}\nPage: {img.page_num}"
        embedding   = await embed_text(embed_input)
        update_rag_image_embedding(db, image_id, caption, embedding)

        actual_cost = tok["cost_usd"]
        log_vision_decision(
            db,
            image_id=image_id,
            doc_id=_doc_id,
            doc_filename=_doc_filename,
            page_num=img.page_num,
            image_sha256=sha,
            model=model,
            prompt_tokens=tok["prompt_tokens"],
            completion_tokens=tok["completion_tokens"],
            cost_usd=actual_cost,
            cache_hit=False,
            skipped=False,
            skip_reason="",
            saved_usd=0.0,
        )

        # Also record in unified usage log
        try:
            from api.utils.usage_recorder import record_usage
            record_usage(
                "Image Captioning", model,
                tok["prompt_tokens"], tok["completion_tokens"],
                duration_ms=_dur_ms,
                sub_feature="rag_image_caption",
                meta={"doc": _doc_filename, "image_id": image_id},
                db=db,
            )
        except Exception:
            pass

        # Persist cost on the image row itself (best-effort)
        try:
            img_row = db.query(RagImage).filter(RagImage.id == image_id).first()
            if img_row:
                img_row.vision_cost_usd = actual_cost
                db.commit()
        except Exception:
            pass

    except Exception as exc:
        log.warning("Vision caption failed for image %s: %s", image_id, exc)


# ──────────────────────────────────────────────────────────
# Semantic image search
# ──────────────────────────────────────────────────────────

async def search_images_semantic(query: str, db, top_k: int = 5) -> List["RagImage"]:
    """
    Find the most visually/semantically relevant images for a query.

    Strategy:
      1. If any images have embeddings: embed query, cosine-rank, return top-k.
      2. Fallback: keyword search over captions + filenames.
      3. If still nothing: return up to 3 images so the user always sees something.
    """
    from api.db.crud import get_all_rag_images

    images = get_all_rag_images(db)
    if not images:
        return []

    # ── Embedding path ─────────────────────────────────────
    images_with_embeddings = [i for i in images if i.embedding]
    if images_with_embeddings:
        query_embedding = await embed_text(query)
        if query_embedding:
            scored = [
                (img, _cosine(query_embedding, img.embedding))
                for img in images_with_embeddings
            ]
            scored.sort(key=lambda x: x[1], reverse=True)
            top = [img for img, score in scored if score > 0.15]
            if top:
                return top[:top_k]
            # If best score < 0.15 but the user explicitly asked for an image,
            # still return the best match rather than nothing
            return [scored[0][0]] if scored else []

    # ── Keyword fallback ───────────────────────────────────
    from api.services.rag_service import _tokenize, _keyword_score

    query_tokens = _tokenize(query)
    scored_kw = []
    for img in images:
        haystack = " ".join(filter(None, [
            img.filename, img.doc_filename, img.caption or "",
        ]))
        score = _keyword_score(query_tokens, haystack)
        scored_kw.append((img, score))

    scored_kw.sort(key=lambda x: x[1], reverse=True)
    best = [img for img, s in scored_kw if s > 0] or [img for img, _ in scored_kw[:3]]
    return best[:top_k]
