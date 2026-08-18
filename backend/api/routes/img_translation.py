"""
Image translation routes — Professional Translation Studio.

Handles full in-image OCR→translate→render pipeline, per-region editing,
ZIP package export, and HTML quality report.
"""
from __future__ import annotations

import copy
import io
import json
import logging
import os
import zipfile
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from api.db import get_db
from api.db.models import TranslationProject, TranslationImage, CustomDictionaryEntry
from api.middleware.auth import require_auth
from api.utils.file_storage import get_source_bytes, has_source_file

log = logging.getLogger(__name__)
router = APIRouter(tags=["image-translation"])


# ── helpers ───────────────────────────────────────────────────────────────────

def _uid(user: dict) -> str:
    return user["id"]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_project(db: Session, project_id: str, user: dict) -> TranslationProject:
    p = db.query(TranslationProject).filter(
        TranslationProject.id == project_id,
        TranslationProject.user_id == _uid(user),
    ).first()
    if not p:
        raise HTTPException(404, "Project not found")
    return p


def _get_image(db: Session, project_id: str, img_id: str, user: dict) -> TranslationImage:
    img = db.query(TranslationImage).filter(
        TranslationImage.id == img_id,
        TranslationImage.project_id == project_id,
        TranslationImage.user_id == _uid(user),
    ).first()
    if not img:
        raise HTTPException(404, "Image not found")
    return img


def _image_summary(img: TranslationImage) -> dict:
    return {
        "id": img.id,
        "project_id": img.project_id,
        "doc_page": img.doc_page,
        "doc_type": img.doc_type,
        "image_index": img.image_index,
        "width_px": img.width_px,
        "height_px": img.height_px,
        "region_count": len(img.regions or []),
        "status": img.status,
        "error_msg": img.error_msg,
        "has_original": img.original_bytes is not None,
        "has_rendered": img.rendered_bytes is not None,
        "created_at": img.created_at.isoformat() if img.created_at else None,
        "updated_at": img.updated_at.isoformat() if img.updated_at else None,
    }


def _image_detail(img: TranslationImage) -> dict:
    d = _image_summary(img)
    d["regions"] = copy.deepcopy(img.regions or [])
    return d


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ── GET images list ───────────────────────────────────────────────────────────

@router.get("/translation/projects/{project_id}/images")
def list_images(
    project_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """List all images extracted from this project."""
    _get_project(db, project_id, user)  # ownership check
    imgs = (
        db.query(TranslationImage)
        .filter(
            TranslationImage.project_id == project_id,
            TranslationImage.user_id == _uid(user),
        )
        .order_by(TranslationImage.doc_page, TranslationImage.image_index)
        .all()
    )
    return {"images": [_image_summary(i) for i in imgs]}


# ── GET single image detail ───────────────────────────────────────────────────

@router.get("/translation/projects/{project_id}/images/{img_id}")
def get_image(
    project_id: str,
    img_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    img = _get_image(db, project_id, img_id, user)
    return _image_detail(img)


# ── Serve image bytes ─────────────────────────────────────────────────────────

@router.get("/translation/projects/{project_id}/images/{img_id}/original")
def get_original_image(
    project_id: str,
    img_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    img = _get_image(db, project_id, img_id, user)
    if not img.original_bytes:
        raise HTTPException(404, "Original image not stored")
    return Response(content=img.original_bytes, media_type="image/png")


@router.get("/translation/projects/{project_id}/images/{img_id}/rendered")
def get_rendered_image(
    project_id: str,
    img_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    img = _get_image(db, project_id, img_id, user)
    if not img.rendered_bytes:
        # Fall back to original if not yet rendered
        if img.original_bytes:
            return Response(content=img.original_bytes, media_type="image/png")
        raise HTTPException(404, "Rendered image not available")
    return Response(content=img.rendered_bytes, media_type="image/png")


# ── Analyze SSE endpoint ──────────────────────────────────────────────────────

@router.post("/translation/projects/{project_id}/images/analyze")
async def analyze_images(
    project_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    SSE pipeline: extract all images from the source document, detect text
    regions with GPT-4o Vision, translate them, and render the result.

    Stream format:
      {"type": "start",          "total_images": N}
      {"type": "extract_done",   "found": N}
      {"type": "image_start",    "num": i, "total": N, "page": P}
      {"type": "image_done",     "image_id": "...", "regions": N, "has_text": bool}
      {"type": "image_skip",     "num": i, "reason": "..."}
      {"type": "done",           "total": N, "with_text": M}
      {"type": "error",          "error": "..."}
    """
    p = _get_project(db, project_id, user)
    if not has_source_file(p):
        raise HTTPException(400, "No source document attached to project")

    from openai import AsyncOpenAI
    from api.utils.image_translator import (
        extract_document_images,
        detect_and_translate_regions,
        render_translated_image,
        check_image_quality,
    )

    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))

    # Load glossary for terminology injection hints
    glossary_entries = (
        db.query(CustomDictionaryEntry)
        .filter(
            CustomDictionaryEntry.source_lang == p.source_lang,
            CustomDictionaryEntry.target_lang == p.target_lang,
            (CustomDictionaryEntry.user_id == _uid(user)) |
            (CustomDictionaryEntry.user_id.is_(None)),
        )
        .limit(50)
        .all()
    )
    _glossary_hint = "; ".join(f"{e.source_term}={e.target_term}" for e in glossary_entries[:20])

    async def _stream():
        # Delete old images for this project before re-analyzing
        old = db.query(TranslationImage).filter(
            TranslationImage.project_id == project_id,
            TranslationImage.user_id == _uid(user),
        ).all()
        for o in old:
            db.delete(o)
        db.commit()

        yield _sse({"type": "start", "total_images": 0})

        # Step 1: Extract images
        try:
            raw_images = extract_document_images(get_source_bytes(p), p.source_file_type)
        except Exception as e:
            yield _sse({"type": "error", "error": f"Image extraction failed: {e}"})
            return

        yield _sse({"type": "extract_done", "found": len(raw_images)})

        if not raw_images:
            yield _sse({"type": "done", "total": 0, "with_text": 0,
                        "message": "No images found in document."})
            return

        # Step 2: Process each image
        with_text = 0
        for i, img_data in enumerate(raw_images, start=1):
            yield _sse({
                "type": "image_start",
                "num": i,
                "total": len(raw_images),
                "page": img_data["doc_page"],
            })

            img_bytes: bytes = img_data["image_bytes"]
            if len(img_bytes) < 200:
                yield _sse({"type": "image_skip", "num": i, "reason": "too small"})
                continue

            # Create DB record
            import uuid
            img_rec = TranslationImage(
                id=str(uuid.uuid4()),
                project_id=project_id,
                user_id=_uid(user),
                doc_page=img_data["doc_page"],
                doc_type=img_data["doc_type"],
                image_index=img_data["image_index"],
                original_bytes=img_bytes,
                original_mime=img_data.get("mime", "image/png"),
                width_px=img_data.get("width", 0),
                height_px=img_data.get("height", 0),
                status="processing",
            )
            db.add(img_rec)
            db.commit()

            try:
                # Step 3: GPT-4o Vision detect + translate
                regions = await detect_and_translate_regions(
                    image_bytes=img_bytes,
                    source_lang=p.source_lang,
                    target_lang=p.target_lang,
                    style=p.style,
                    client=client,
                )

                if not regions:
                    img_rec.status = "no_text"
                    img_rec.regions = []
                    db.commit()
                    yield _sse({"type": "image_done", "image_id": img_rec.id,
                                "regions": 0, "has_text": False})
                    continue

                # Step 4: Render translated image
                rendered = render_translated_image(
                    image_bytes=img_bytes,
                    regions=regions,
                    target_lang=p.target_lang,
                )

                # Step 5: Quality check for this image
                qissues = check_image_quality(regions, img_data.get("width", 100), img_data.get("height", 100))
                for r in regions:
                    r["quality_issues"] = [qi for qi in qissues if qi["region_id"] == r["id"]]

                img_rec.regions = regions
                img_rec.rendered_bytes = rendered
                img_rec.status = "done"
                flag_modified(img_rec, "regions")
                db.commit()

                with_text += 1
                yield _sse({
                    "type": "image_done",
                    "image_id": img_rec.id,
                    "regions": len(regions),
                    "has_text": True,
                })

            except Exception as e:
                log.error("Image %s processing failed: %s", img_rec.id, e)
                img_rec.status = "error"
                img_rec.error_msg = str(e)
                db.commit()
                yield _sse({"type": "image_error", "num": i, "error": str(e)})

        yield _sse({"type": "done", "total": len(raw_images), "with_text": with_text})

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── Edit a region ─────────────────────────────────────────────────────────────

class RegionPatch(BaseModel):
    translated_text: Optional[str] = None
    bbox: Optional[dict] = None
    font_size: Optional[int] = None
    font_color: Optional[str] = None
    keep_english: Optional[bool] = None
    approved: Optional[bool] = None


@router.patch("/translation/projects/{project_id}/images/{img_id}/regions/{region_id}")
def patch_region(
    project_id: str,
    img_id: str,
    region_id: str,
    body: RegionPatch,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    img = _get_image(db, project_id, img_id, user)
    regions = copy.deepcopy(img.regions or [])
    updated = False
    for r in regions:
        if r.get("id") == region_id:
            if body.translated_text is not None:
                r["translated_text"] = body.translated_text
                r["edited"] = True
            if body.bbox is not None:
                r["bbox"] = body.bbox
            if body.font_size is not None:
                r["font_size"] = body.font_size
            if body.font_color is not None:
                r["font_color"] = body.font_color
            if body.keep_english is not None:
                r["keep_english"] = body.keep_english
            if body.approved is not None:
                r["approved"] = body.approved
            updated = True
            break

    if not updated:
        raise HTTPException(404, "Region not found")

    img.regions = regions
    flag_modified(img, "regions")
    db.commit()
    return {"updated": region_id}


# ── Re-render single image ────────────────────────────────────────────────────

@router.post("/translation/projects/{project_id}/images/{img_id}/render")
def render_image(
    project_id: str,
    img_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Re-render translated image after region edits."""
    from api.utils.image_translator import render_translated_image
    img = _get_image(db, project_id, img_id, user)
    if not img.original_bytes:
        raise HTTPException(400, "Original image bytes not stored")

    rendered = render_translated_image(
        image_bytes=img.original_bytes,
        regions=img.regions or [],
        target_lang=(
            db.query(TranslationProject)
            .filter(TranslationProject.id == project_id)
            .first()
            or type("P", (), {"target_lang": "ar"})()
        ).target_lang,
    )
    img.rendered_bytes = rendered
    img.status = "done"
    db.commit()
    return {"rendered": img_id}


# ── Add new region ────────────────────────────────────────────────────────────

class NewRegion(BaseModel):
    bbox: dict
    source_text: str = ""
    translated_text: str = ""
    font_size: int = 14
    font_color: str = "#000000"


@router.post("/translation/projects/{project_id}/images/{img_id}/regions")
def add_region(
    project_id: str,
    img_id: str,
    body: NewRegion,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    import uuid as _uuid
    img = _get_image(db, project_id, img_id, user)
    regions = copy.deepcopy(img.regions or [])
    new_r = {
        "id": _uuid.uuid4().hex[:8],
        "bbox": body.bbox,
        "source_text": body.source_text,
        "translated_text": body.translated_text,
        "confidence": 1.0,
        "is_technical_code": False,
        "font_size": body.font_size,
        "font_color": body.font_color,
        "edited": True,
        "approved": False,
        "keep_english": False,
    }
    regions.append(new_r)
    img.regions = regions
    flag_modified(img, "regions")
    db.commit()
    return {"added": new_r["id"], "region": new_r}


# ── Delete region ─────────────────────────────────────────────────────────────

@router.delete("/translation/projects/{project_id}/images/{img_id}/regions/{region_id}")
def delete_region(
    project_id: str,
    img_id: str,
    region_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    img = _get_image(db, project_id, img_id, user)
    regions = copy.deepcopy(img.regions or [])
    before = len(regions)
    regions = [r for r in regions if r.get("id") != region_id]
    if len(regions) == before:
        raise HTTPException(404, "Region not found")
    img.regions = regions
    flag_modified(img, "regions")
    db.commit()
    return {"deleted": region_id}


# ── Regenerate one region via GPT-4o Vision ───────────────────────────────────

@router.post("/translation/projects/{project_id}/images/{img_id}/regions/{region_id}/retranslate")
async def retranslate_region(
    project_id: str,
    img_id: str,
    region_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Re-translate a single region using GPT-4o (useful when initial translation is wrong)."""
    import copy as _copy
    from openai import AsyncOpenAI
    from api.utils.image_translator import detect_and_translate_regions
    from PIL import Image as _PIL
    import io as _io

    img = _get_image(db, project_id, img_id, user)
    p = _get_project(db, project_id, user)

    region = next((r for r in (img.regions or []) if r.get("id") == region_id), None)
    if not region:
        raise HTTPException(404, "Region not found")

    if not img.original_bytes:
        raise HTTPException(400, "Original image bytes not stored")

    # Crop the region from the original image and re-query
    try:
        image = _PIL.open(_io.BytesIO(img.original_bytes))
        W, H = image.size
        bbox = region.get("bbox", {})
        x = max(0, int(float(bbox.get("x", 0)) * W / 100))
        y = max(0, int(float(bbox.get("y", 0)) * H / 100))
        bw = max(10, int(float(bbox.get("w", 10)) * W / 100))
        bh = max(10, int(float(bbox.get("h", 5)) * H / 100))
        crop = image.crop((x, y, min(W, x + bw), min(H, y + bh)))
        buf = _io.BytesIO()
        crop.save(buf, "PNG")
        crop_bytes = buf.getvalue()
    except Exception as e:
        raise HTTPException(500, f"Could not crop image: {e}")

    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    new_regions = await detect_and_translate_regions(
        image_bytes=crop_bytes,
        source_lang=p.source_lang,
        target_lang=p.target_lang,
        style=p.style,
        client=client,
    )

    new_text = new_regions[0]["translated_text"] if new_regions else region.get("translated_text", "")

    regions = _copy.deepcopy(img.regions or [])
    for r in regions:
        if r.get("id") == region_id:
            r["translated_text"] = new_text
            r["edited"] = True
            break

    img.regions = regions
    flag_modified(img, "regions")
    db.commit()
    return {"region_id": region_id, "translated_text": new_text}


# ── ZIP export ────────────────────────────────────────────────────────────────

@router.get("/translation/projects/{project_id}/export/zip")
def export_zip(
    project_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Build and return a ZIP package containing:
      original/         — source document
      translated/       — DOCX and/or PPTX output
      images/original/  — all extracted source images
      images/translated/— all rendered translated images
      ocr_text.txt      — all detected text by page
      glossary.tsv      — custom dictionary entries for this language pair
      quality_report.html
      metadata.json
    """
    p = _get_project(db, project_id, user)
    imgs = (
        db.query(TranslationImage)
        .filter(
            TranslationImage.project_id == project_id,
            TranslationImage.user_id == _uid(user),
        )
        .order_by(TranslationImage.doc_page, TranslationImage.image_index)
        .all()
    )

    from api.utils.filename_helper import (
        build_translated_filename_from_code,
        content_disposition,
    )

    buf = io.BytesIO()
    safe_name = "".join(c if c.isalnum() or c in "._- " else "_" for c in p.name)[:60]
    prefix = f"translation-{safe_name}/"

    # Pre-compute translated base name for internal ZIP entries
    _tl_base = build_translated_filename_from_code(p.source_filename, p.target_lang)

    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:

        # Original document
        if has_source_file(p):
            zf.writestr(f"{prefix}original/{p.source_filename}", get_source_bytes(p) or b"")

        # Translated DOCX
        if p.output_docx:
            docx_name = (_tl_base.rsplit(".", 1)[0] + ".docx") if "." in _tl_base else (_tl_base + ".docx")
            zf.writestr(f"{prefix}translated/{docx_name}", p.output_docx)

        # Translated PPTX
        if p.output_pptx:
            pptx_name = (_tl_base.rsplit(".", 1)[0] + ".pptx") if "." in _tl_base else (_tl_base + ".pptx")
            zf.writestr(f"{prefix}translated/{pptx_name}", p.output_pptx)

        # Images
        ocr_lines = [f"# OCR Text — {p.name}", f"# Source: {p.source_filename}", ""]
        for img in imgs:
            tag = f"page{img.doc_page:02d}_img{img.image_index:02d}"
            if img.original_bytes:
                zf.writestr(f"{prefix}images/original/{tag}.png", img.original_bytes)
            if img.rendered_bytes:
                zf.writestr(f"{prefix}images/translated/{tag}.png", img.rendered_bytes)
            # OCR text
            ocr_lines.append(f"## Page {img.doc_page}, Image {img.image_index}")
            for r in (img.regions or []):
                if r.get("source_text"):
                    ocr_lines.append(f"  [{r.get('id','')}] {r['source_text']}")
                    ocr_lines.append(f"       → {r.get('translated_text','')}")
            ocr_lines.append("")

        zf.writestr(f"{prefix}ocr_text.txt", "\n".join(ocr_lines))

        # Glossary TSV
        gloss_entries = (
            db.query(CustomDictionaryEntry)
            .filter(
                CustomDictionaryEntry.source_lang == p.source_lang,
                CustomDictionaryEntry.target_lang == p.target_lang,
                (CustomDictionaryEntry.user_id == _uid(user)) |
                (CustomDictionaryEntry.user_id.is_(None)),
            )
            .all()
        )
        gloss_lines = ["source_term\ttarget_term\tdomain\tnotes"]
        for e in gloss_entries:
            gloss_lines.append(f"{e.source_term}\t{e.target_term}\t{e.domain or ''}\t{e.notes or ''}")
        zf.writestr(f"{prefix}glossary.tsv", "\n".join(gloss_lines))

        # Quality report HTML
        qr_html = _build_quality_report_html(p, imgs)
        zf.writestr(f"{prefix}quality_report.html", qr_html)

        # Metadata JSON
        meta = {
            "project_id": p.id,
            "name": p.name,
            "source_filename": p.source_filename,
            "source_file_type": p.source_file_type,
            "source_lang": p.source_lang,
            "target_lang": p.target_lang,
            "style": p.style,
            "quality_score": p.quality_score,
            "segment_count": len(p.segments or []),
            "image_count": len(imgs),
            "images_with_text": sum(1 for i in imgs if i.status == "done" and len(i.regions or []) > 0),
            "exported_at": _now_iso(),
        }
        zf.writestr(f"{prefix}metadata.json", json.dumps(meta, indent=2, ensure_ascii=False))

    buf.seek(0)
    zip_dl_name = build_translated_filename_from_code(p.source_filename, p.target_lang)
    # Always serve as .zip regardless of original extension
    zip_base = zip_dl_name.rsplit(".", 1)[0] if "." in zip_dl_name else zip_dl_name
    zip_final_name = f"{zip_base}.zip"
    zip_content = buf.read()
    return Response(
        content=zip_content,
        media_type="application/zip",
        headers={
            "Content-Disposition": content_disposition(zip_final_name),
            "Content-Length": str(len(zip_content)),
            "Cache-Control": "private, no-store",
        },
    )


# ── Quality report ────────────────────────────────────────────────────────────

@router.get("/translation/projects/{project_id}/export/quality-report")
def export_quality_report(
    project_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Serve standalone HTML quality report."""
    p = _get_project(db, project_id, user)
    imgs = (
        db.query(TranslationImage)
        .filter(
            TranslationImage.project_id == project_id,
            TranslationImage.user_id == _uid(user),
        )
        .order_by(TranslationImage.doc_page, TranslationImage.image_index)
        .all()
    )
    from api.utils.filename_helper import (
        build_translated_filename_from_code,
        content_disposition,
    )
    html = _build_quality_report_html(p, imgs)
    html_bytes = html.encode()
    qr_base = build_translated_filename_from_code(p.source_filename, p.target_lang)
    qr_base = qr_base.rsplit(".", 1)[0] if "." in qr_base else qr_base
    qr_name = f"{qr_base}-quality-report.html"
    return Response(
        content=html_bytes,
        media_type="text/html; charset=utf-8",
        headers={
            "Content-Disposition": content_disposition(qr_name),
            "Content-Length": str(len(html_bytes)),
            "Cache-Control": "private, no-store",
        },
    )


def _build_quality_report_html(p: TranslationProject, imgs: list) -> str:
    from api.utils.image_translator import check_image_quality

    # Segment-level issues
    seg_errors = [i for i in (p.quality_issues or []) if i.get("severity") == "error"]
    seg_warns  = [i for i in (p.quality_issues or []) if i.get("severity") == "warning"]

    # Image-level issues
    all_img_issues: list[dict] = []
    for img in imgs:
        issues = check_image_quality(img.regions or [], img.width_px or 100, img.height_px or 100)
        for qi in issues:
            qi["page"] = img.doc_page
            qi["image_index"] = img.image_index
        all_img_issues.extend(issues)

    img_errors = [i for i in all_img_issues if i.get("severity") == "error"]
    img_warns  = [i for i in all_img_issues if i.get("severity") == "warning"]

    total_errors = len(seg_errors) + len(img_errors)
    total_warns  = len(seg_warns)  + len(img_warns)
    score_color  = "#22c55e" if (p.quality_score or 0) >= 90 else \
                   "#f59e0b" if (p.quality_score or 0) >= 70 else "#ef4444"

    def _issue_rows(issues, has_page=False):
        rows = ""
        for iss in issues:
            sev = iss.get("severity", "warning")
            color = "#ef4444" if sev == "error" else "#f59e0b"
            page_col = f"<td>p.{iss.get('page','?')} img.{iss.get('image_index','?')}</td>" if has_page else ""
            rows += (
                f"<tr>"
                f"<td style='color:{color};font-weight:600'>{sev.upper()}</td>"
                f"{page_col}"
                f"<td>{iss.get('type','').replace('_',' ')}</td>"
                f"<td>{iss.get('message','')}</td>"
                f"</tr>"
            )
        return rows or "<tr><td colspan='4' style='color:#6b7280'>No issues</td></tr>"

    return f"""<!DOCTYPE html>
<html lang="en" dir="ltr">
<head>
<meta charset="UTF-8">
<title>Quality Report — {p.name}</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #111827; color: #f9fafb; margin: 0; padding: 2rem; }}
  h1 {{ color: #60a5fa; }} h2 {{ color: #9ca3af; border-bottom: 1px solid #374151; padding-bottom: .5rem; }}
  .score {{ font-size: 3rem; font-weight: 800; color: {score_color}; }}
  .meta {{ display: grid; grid-template-columns: repeat(auto-fit,minmax(180px,1fr)); gap: 1rem; margin: 1.5rem 0; }}
  .card {{ background: #1f2937; border: 1px solid #374151; border-radius: .75rem; padding: 1rem; }}
  .card-label {{ font-size: .75rem; color: #9ca3af; text-transform: uppercase; letter-spacing: .05em; }}
  .card-value {{ font-size: 1.5rem; font-weight: 700; margin-top: .25rem; }}
  table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; }}
  th {{ background: #1f2937; padding: .5rem .75rem; text-align: left; font-size: .75rem; color: #9ca3af; text-transform: uppercase; }}
  td {{ padding: .5rem .75rem; font-size: .85rem; border-bottom: 1px solid #1f2937; }}
  tr:hover td {{ background: #1f2937; }}
  .badge-ok {{ background: #052e16; color: #22c55e; padding: .2rem .6rem; border-radius: 999px; font-size: .75rem; }}
  .badge-warn {{ background: #431407; color: #f59e0b; padding: .2rem .6rem; border-radius: 999px; font-size: .75rem; }}
  .badge-err {{ background: #450a0a; color: #ef4444; padding: .2rem .6rem; border-radius: 999px; font-size: .75rem; }}
</style>
</head>
<body>
<h1>Quality Control Report</h1>
<p style="color:#9ca3af">{p.name} &mdash; {p.source_filename} &mdash; Generated {_now_iso()[:19]} UTC</p>

<div class="meta">
  <div class="card">
    <div class="card-label">Quality Score</div>
    <div class="card-value" style="color:{score_color}">{p.quality_score or '—'}/100</div>
  </div>
  <div class="card">
    <div class="card-label">Segments</div>
    <div class="card-value">{len(p.segments or [])}</div>
  </div>
  <div class="card">
    <div class="card-label">Images Translated</div>
    <div class="card-value">{len([i for i in imgs if i.status=='done'])}/{len(imgs)}</div>
  </div>
  <div class="card">
    <div class="card-label">Total Errors</div>
    <div class="card-value" style="color:#ef4444">{total_errors}</div>
  </div>
  <div class="card">
    <div class="card-label">Total Warnings</div>
    <div class="card-value" style="color:#f59e0b">{total_warns}</div>
  </div>
  <div class="card">
    <div class="card-label">Language Pair</div>
    <div class="card-value" style="font-size:1rem">{p.source_lang.upper()} → {p.target_lang.upper()}</div>
  </div>
</div>

<h2>Text Segment Issues ({len(seg_errors)} errors, {len(seg_warns)} warnings)</h2>
<table>
  <thead><tr><th>Severity</th><th>Type</th><th>Message</th></tr></thead>
  <tbody>{_issue_rows(seg_errors + seg_warns)}</tbody>
</table>

<h2>Image Region Issues ({len(img_errors)} errors, {len(img_warns)} warnings)</h2>
<table>
  <thead><tr><th>Severity</th><th>Location</th><th>Type</th><th>Message</th></tr></thead>
  <tbody>{_issue_rows(img_errors + img_warns, has_page=True)}</tbody>
</table>

<h2>Image Summary ({len(imgs)} images)</h2>
<table>
  <thead><tr><th>Page</th><th>Index</th><th>Type</th><th>Regions</th><th>Status</th></tr></thead>
  <tbody>
    {''.join(
      f"<tr><td>{i.doc_page}</td><td>{i.image_index}</td><td>{i.doc_type}</td>"
      f"<td>{len(i.regions or [])}</td>"
      f"<td><span class='badge-ok'>done</span></td></tr>"
      if i.status == 'done' else
      f"<tr><td>{i.doc_page}</td><td>{i.image_index}</td><td>{i.doc_type}</td>"
      f"<td>{len(i.regions or [])}</td>"
      f"<td><span class='{'badge-warn' if i.status=='no_text' else 'badge-err'}'>{i.status}</span></td></tr>"
      for i in imgs
    ) or "<tr><td colspan='5' style='color:#6b7280'>No images</td></tr>"}
  </tbody>
</table>
</body></html>"""
