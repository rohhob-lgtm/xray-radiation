"""Knowledge base (RAG) routes — documents, extracted images, and ColPali-indexed pages."""
from __future__ import annotations
import asyncio
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File, Form, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.db.crud import (
    create_rag_document, list_rag_documents, delete_rag_document,
    update_rag_document, rag_document_to_dict,
    store_rag_image, get_rag_image,
    create_rag_page, get_rag_page,
)
from api.middleware.auth import optional_auth
from api.services.rag_service import embed_and_store
from api.services.doc_parser import extract_text, extract_images, render_pdf_pages
from api.services.image_service import process_rag_image
from api.services.colpali_service import process_rag_page, get_backend

router = APIRouter(tags=["rag"])


class PptxSourceControlBody(BaseModel):
    source_status: Optional[str] = None
    trusted: Optional[bool] = None
    manufacturer_approved: Optional[bool] = None
    internal_training_reference: Optional[bool] = None
    visual_template: Optional[bool] = None
    arabic_formatting_example: Optional[bool] = None
    obsolete: Optional[bool] = None
    do_not_use: Optional[bool] = None
    course_type: Optional[str] = None
    target_audience: Optional[str] = None
    equipment_family: Optional[str] = None
    manufacturer: Optional[str] = None
    equipment_model: Optional[str] = None
    language: Optional[str] = None


# ──────────────────────────────────────────────────────────
# Documents
# ──────────────────────────────────────────────────────────

@router.get("/rag/documents")
def list_documents(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    user_id = user["id"] if user else None
    docs = list_rag_documents(db, user_id=user_id)
    return [rag_document_to_dict(d) for d in docs]


@router.post("/rag/documents", status_code=201)
async def upload_document(
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """Ingest plain text or JSON content into the knowledge base."""
    content = body.get("content", "").strip()
    filename = body.get("filename", "document.txt").strip()
    document_type = body.get("document_type", "other")

    if not content:
        raise HTTPException(status_code=400, detail="Document content is required")
    if len(content) > 500_000:
        raise HTTPException(status_code=400, detail="Document too large (max 500k characters)")

    user_id = user["id"] if user else None
    doc = create_rag_document(
        db, user_id=user_id, filename=filename,
        document_type=document_type, content=content,
    )
    asyncio.create_task(embed_and_store(db, doc))
    return rag_document_to_dict(doc)


@router.post("/rag/documents/upload", status_code=201)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("other"),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """
    Accept a binary file (PDF, DOCX, PPTX, TXT, etc.).

    Returns immediately with status='processing'. A background task runs the
    CPU-heavy extraction and indexing pipelines without blocking the HTTP response:
      1. Text extraction  (pypdf / python-docx / python-pptx)
      2. Text embedding   (text-embedding-3-small on chunked content)
      3. Figure captioning (GPT vision → caption → embedding)
      4. ColPali visual indexing (OpenCLIP embeddings on rendered page images)
    """
    from api.security.uploads import validate_upload
    from api.security.sanitize import sanitize_filename

    data = await file.read()
    # Validate extension + declared MIME + size + magic bytes before doing any
    # work, and normalize the filename (strips path components / unsafe chars).
    validate_upload(
        file.filename,
        data,
        declared_content_type=file.content_type,
        category="document",
        request=request,
    )
    import logging
    logging.getLogger(__name__).info(
        "START_UPLOAD | filename=%s size_bytes=%d document_type=%s",
        file.filename or "upload",
        len(data),
        document_type,
    )

    filename = sanitize_filename(file.filename or "upload")
    user_id = user["id"] if user else None

    # Create a stub document immediately so the UI can show the card at once.
    # Content is a placeholder; the background task will replace it.
    doc = create_rag_document(
        db, user_id=user_id, filename=filename,
        document_type=document_type,
        content="__processing__",
        status="processing",
    )
    logging.getLogger(__name__).info(
        "UPLOAD_OK | doc_id=%s filename=%s size_bytes=%d",
        doc.id,
        filename,
        len(data),
    )

    # Launch background processing — passes data bytes directly so no DB
    # storage of raw bytes is needed. The task holds the reference until done.
    asyncio.create_task(_process_rag_bg(doc.id, filename, data, document_type))

    result = rag_document_to_dict(doc)
    result["images_queued"] = 0
    result["pages_queued"] = 0
    return result


async def _process_rag_bg(doc_id: str, filename: str, data: bytes, document_type: str) -> None:
    """
    Background coroutine: run all CPU-heavy RAG pipelines without blocking the
    event loop. Uses run_in_executor for synchronous work and a fresh DB session
    (the request-scoped session is already closed by the time this runs).
    """
    import logging
    from api.db.base import SessionLocal
    from api.db.models import RagDocument

    log = logging.getLogger(__name__)
    pipe_db = SessionLocal()
    loop = asyncio.get_event_loop()

    try:
        # ── Step 1: text extraction in thread pool ───────────────────────────
        try:
            content = await loop.run_in_executor(None, extract_text, filename, data)
            log.info("PARSER_OK | doc_id=%s filename=%s", doc_id, filename)
        except (ValueError, RuntimeError) as exc:
            log.error("RAG text extraction failed for %s: %s", filename, exc)
            doc = pipe_db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if doc:
                doc.status = "error"
                doc.content = f"Extraction failed: {exc}"
                pipe_db.commit()
            return

        if not content.strip():
            doc = pipe_db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if doc:
                doc.status = "error"
                doc.content = "No extractable text found in this file."
                pipe_db.commit()
            return
        log.info(
            "TEXT_EXTRACTION_OK | doc_id=%s filename=%s chars=%d words=%d",
            doc_id,
            filename,
            len(content),
            len(content.split()),
        )

        # ── Update document with real content ────────────────────────────────
        doc = pipe_db.query(RagDocument).filter(RagDocument.id == doc_id).first()
        if not doc:
            return
        doc.content = content
        doc.word_count = len(content.split())
        doc.status = "extracting"   # intermediate: text extracted, pipeline continues
        pipe_db.commit()
        pipe_db.refresh(doc)

        # ── Step 2: text embedding (async, already non-blocking) ─────────────
        asyncio.create_task(embed_and_store(pipe_db, doc))

        # ── Step 3: figure extraction + Vision Cost pre-flight ───────────────
        # Images are stored with their SHA-256 and local-filter decisions.
        # Vision captioning does NOT start automatically — the frontend shows
        # a confirmation dialog showing cost/savings before the user proceeds.
        # Captioning starts only when the user calls POST /api/vision/start/{doc_id}.
        try:
            img_records = await loop.run_in_executor(None, extract_images, filename, data)

            # Pre-flight: local analysis + cost estimate (no API cost)
            from api.services.vision_guard import (
                estimate_batch, analyze_image_locally, compute_image_sha256
            )
            vision_est = await loop.run_in_executor(None, estimate_batch, img_records)
            eligible_names = {e["name"] for e in vision_est.get("eligible_images", [])}

            for rec in img_records:
                local_result = analyze_image_locally(rec["data"], rec["name"])
                sha = compute_image_sha256(rec["data"])
                is_eligible = rec["name"] in eligible_names
                store_rag_image(
                    pipe_db,
                    doc_id=doc_id,
                    doc_filename=filename,
                    filename=rec["name"],
                    page_num=rec["page_num"],
                    image_index=rec["image_index"],
                    image_data=rec["data"],
                    mime_type=rec["mime_type"],
                    image_sha256=sha,
                    vision_skipped=not is_eligible,
                    skip_reason=local_result["reason"] if not is_eligible else None,
                )

            # Persist estimate on the document (excluding large eligible_images list)
            est_to_store = {k: v for k, v in vision_est.items() if k != "eligible_images"}
            est_to_store["eligible_image_count"] = len(vision_est.get("eligible_images", []))
            doc_upd = pipe_db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if doc_upd:
                doc_upd.vision_estimate = est_to_store
                pipe_db.commit()

            log.info(
                "Vision pre-flight %s: %d eligible / %d skipped / est $%.4f",
                filename,
                vision_est["vision_eligible"],
                vision_est["vision_skipped_local"],
                vision_est["estimated_cost_usd"],
            )
        except Exception as exc:
            log.warning("RAG image extraction skipped for %s: %s", filename, exc)

        # ── Step 4: page rendering in thread pool ────────────────────────────
        try:
            page_renders = await loop.run_in_executor(
                None, render_pdf_pages, data, 150
            )
            for render in page_renders:
                pg = create_rag_page(
                    pipe_db,
                    doc_id=doc_id,
                    doc_filename=filename,
                    page_num=render["page_num"],
                    image_data=render["data"],
                )
                asyncio.create_task(process_rag_page(pipe_db, pg.id))
        except Exception as exc:
            log.warning("RAG page rendering skipped for %s: %s", filename, exc)

        # ── Mark as ready ────────────────────────────────────────────────────
        doc = pipe_db.query(RagDocument).filter(RagDocument.id == doc_id).first()
        if doc:
            doc.status = "ready"
            pipe_db.commit()
        log.info("RAG background processing complete for %s (%s)", filename, doc_id)

        # ── Step 5: terminology extraction (local, zero API cost) ───────────
        # Each background task gets its own DB session — Session is not thread-safe.
        try:
            from api.services.terminology_service import extract_and_store as extract_terms
            from api.db.base import SessionLocal as _SL

            _doc_id_5, _content_5 = doc_id, content

            def _run_terminology():
                _db = _SL()
                try:
                    extract_terms(_db, _doc_id_5, _content_5)
                finally:
                    _db.close()

            loop.run_in_executor(None, _run_terminology)
        except Exception as te:
            log.debug("Terminology extraction skipped: %s", te)

        # ── Step 6: exam pattern extraction (local, zero API cost) ───────────
        try:
            from api.services.exam_learner import extract_and_store as extract_exams
            from api.db.base import SessionLocal as _SL

            _doc_id_6, _filename_6, _content_6 = doc_id, filename, content

            def _run_exams():
                _db = _SL()
                try:
                    extract_exams(_db, _doc_id_6, _filename_6, _content_6)
                finally:
                    _db.close()

            loop.run_in_executor(None, _run_exams)
        except Exception as ee:
            log.debug("Exam extraction skipped: %s", ee)

        # ── Step 7: layout style learning for PPTX files ─────────────────────
        if filename.lower().endswith(".pptx"):
            try:
                from api.services.layout_learner import learn_and_store as learn_style
                from api.db.base import SessionLocal as _SL

                _doc_id_7, _filename_7, _data_7 = doc_id, filename, data

                def _run_layout():
                    _db = _SL()
                    try:
                        learn_style(_db, _doc_id_7, _filename_7, _data_7)
                    finally:
                        _db.close()

                loop.run_in_executor(None, _run_layout)
            except Exception as le:
                log.debug("Layout learning skipped: %s", le)

            # ── Step 7b: PPTX slide-level reference indexing ─────────────────
            try:
                from api.services.ppt_reference_service import extract_pptx_index, store_pptx_index

                extracted = await loop.run_in_executor(None, extract_pptx_index, filename, data)
                store_info = store_pptx_index(pipe_db, doc_id, filename, extracted)
                log.info(
                    "PPTX_REFERENCE_INDEXED | doc_id=%s filename=%s slides=%d",
                    doc_id,
                    filename,
                    int(store_info.get("slide_count") or 0),
                )
            except Exception as pe:
                log.warning("PPTX reference indexing skipped for %s: %s", filename, pe)

        # ── Step 8: image classification (local OpenCLIP, zero API cost) ─────
        try:
            from api.db.models import RagImage
            from api.services.image_classifier import classify_and_store
            from api.db.base import SessionLocal as _SL

            # Snapshot image IDs + captions/data — don't share pipe_db across async tasks
            imgs = pipe_db.query(RagImage).filter(RagImage.doc_id == doc_id).all()
            img_snapshots = [
                (img_rec.id, bytes(img_rec.image_data) if img_rec.image_data else b"", img_rec.caption or "")
                for img_rec in imgs
            ]

            async def _classify_all(snapshots: list) -> None:
                for img_id, img_bytes, caption in snapshots:
                    _db = _SL()
                    try:
                        await classify_and_store(_db, img_id, img_bytes, caption)
                    finally:
                        _db.close()

            if img_snapshots:
                asyncio.create_task(_classify_all(img_snapshots))
        except Exception as ce:
            log.debug("Image classification skipped: %s", ce)

        # ── Step 9: auto-trigger study pipeline (non-blocking) ───────────────
        # IMPORTANT: run_study_pipeline is an async coroutine that makes GPT
        # calls and can take 30-120s.  We must NOT pass pipe_db to it because
        # _process_rag_bg's finally-block closes pipe_db the moment this
        # coroutine returns.  Instead we spawn an independent async task that
        # opens its own SessionLocal so it can outlive this background job.
        try:
            from api.services.study_service import (
                compute_sha256, is_duplicate, run_study_pipeline
            )
            from api.db.base import SessionLocal as _StudySL
            sha = compute_sha256(data)
            existing_doc_id = is_duplicate(pipe_db, sha)
            if existing_doc_id and existing_doc_id != doc_id:
                log.info("Study pipeline skipped — duplicate of doc %s", existing_doc_id)
            else:
                from api.db.models import RagImage
                img_count = pipe_db.query(RagImage).filter(
                    RagImage.doc_id == doc_id
                ).count()
                # Capture loop-local copies so the closure doesn't close over
                # mutable vars that might change before the task runs.
                _sdoc, _sfn, _sct, _ssha, _simg = doc_id, filename, content, sha, img_count

                async def _study_task(_d=_sdoc, _f=_sfn, _c=_sct, _s=_ssha, _i=_simg):
                    study_db = _StudySL()
                    try:
                        await run_study_pipeline(
                            study_db, _d, _f, _c, sha256=_s, image_count=_i
                        )
                    except Exception as _e:
                        log.warning("Study pipeline task failed for %s: %s", _f, _e, exc_info=True)
                    finally:
                        study_db.close()

                asyncio.create_task(_study_task())
                log.info("AI_ANALYSIS_START | doc_id=%s filename=%s", doc_id, filename)
                log.info("Study pipeline task scheduled for %s", filename)
        except Exception as study_exc:
            log.warning("Study pipeline could not start for %s: %s", filename, study_exc)

    except Exception as exc:
        log.error("RAG background task failed for %s: %s", filename, exc, exc_info=True)
        try:
            doc = pipe_db.query(RagDocument).filter(RagDocument.id == doc_id).first()
            if doc:
                doc.status = "error"
                pipe_db.commit()
        except Exception:
            pass
    finally:
        pipe_db.close()


@router.get("/rag/documents/{document_id}/status")
def get_document_status(
    document_id: str,
    db: Session = Depends(get_db),
):
    """Lightweight polling endpoint — returns id + status only."""
    from api.db.models import RagDocument
    doc = db.query(RagDocument).filter(RagDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"id": doc.id, "status": getattr(doc, "status", "ready"), "word_count": doc.word_count}


@router.get("/rag/documents/{document_id}/pipeline-status")
def get_pipeline_status(
    document_id: str,
    db: Session = Depends(get_db),
):
    """
    Combined pipeline status for real-time upload progress.
    Returns stage label + percent (0-100) based on actual DB state.
    No auth required — safe to poll from the browser.
    """
    from api.db.models import RagDocument, StudyJob

    doc = db.query(RagDocument).filter(RagDocument.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    doc_status  = getattr(doc, "status", "processing")
    word_count  = doc.word_count or 0

    # Look up the latest study job for this doc
    job = (
        db.query(StudyJob)
        .filter(StudyJob.doc_id == document_id)
        .order_by(StudyJob.created_at.desc())
        .first()
    )
    study_status = job.status if job else None

    # ── Map to frontend stage ───────────────────────────────────────────────
    if doc_status == "error":
        return {"stage": "error",     "label": "Upload failed",         "pct": 0,   "study_status": None}

    if study_status in ("integrated", "approved"):
        return {"stage": "completed", "label": "Completed",             "pct": 100, "study_status": study_status,
                "nodes": job.report_graph_nodes_added, "edges": job.report_graph_edges_added}

    if study_status == "awaiting_approval":
        return {"stage": "completed", "label": "Pending review",        "pct": 100, "study_status": study_status}

    if study_status in ("failed", "error", "stalled"):
        reason = (
            (job.rejection_reason or "").strip()
            if job is not None
            else ""
        )
        label = reason[:180] if reason else "AI analysis failed"
        return {
            "stage": "error",
            "label": label,
            "pct": 80,
            "study_status": study_status,
            "error_stage": reason.split(":", 1)[0] if reason else "AI analysis",
        }

    if study_status == "validating":
        return {"stage": "integrating","label": "Integrating knowledge…","pct": 88,  "study_status": study_status}

    if study_status == "studying":
        return {"stage": "generating", "label": "Generating knowledge…", "pct": 65,  "study_status": study_status}

    # Study job not yet created
    if doc_status == "ready":
        return {"stage": "studying",   "label": "Studying document…",    "pct": 52,  "study_status": None}

    if doc_status == "extracting" or (doc_status == "processing" and word_count > 0):
        return {"stage": "extracting", "label": "Extracting text…",      "pct": 32,  "study_status": None}

    # status == "processing", word_count == 0 — still receiving/reading file
    return     {"stage": "uploading",  "label": "Uploading…",            "pct": 10,  "study_status": None}


@router.patch("/rag/documents/{document_id}")
def edit_document(
    document_id: str,
    body: dict,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    filename = body.get("filename")
    document_type = body.get("document_type")
    content = body.get("content")

    doc = update_rag_document(
        db, doc_id=document_id,
        filename=filename, document_type=document_type, content=content,
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    if content is not None:
        asyncio.create_task(embed_and_store(db, doc))

    return rag_document_to_dict(doc)


@router.delete("/rag/documents/{document_id}", status_code=204)
def delete_document(
    document_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    if not delete_rag_document(db, document_id):
        raise HTTPException(status_code=404, detail="Document not found")


# ──────────────────────────────────────────────────────────
# Extracted figures (legacy pipeline)
# ──────────────────────────────────────────────────────────

@router.get("/rag/images/{image_id}")
def get_image(
    image_id: str,
    db: Session = Depends(get_db),
):
    """Serve a raw PNG figure extracted from an uploaded document."""
    img = get_rag_image(db, image_id)
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    return Response(
        content=img.image_data,
        media_type=img.mime_type,
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'inline; filename="{img.filename}"',
        },
    )


# ──────────────────────────────────────────────────────────
# ColPali-indexed pages (visual search pipeline)
# ──────────────────────────────────────────────────────────

@router.get("/rag/pages")
def list_pages(
    doc_filename: str = "",
    limit: int = 60,
    offset: int = 0,
    db: Session = Depends(get_db),
):
    """List indexed pages (metadata only, no binary) for the gallery."""
    from api.db.models import RagPage
    q = db.query(RagPage)
    if doc_filename:
        q = q.filter(RagPage.doc_filename.ilike(f"%{doc_filename}%"))
    total = q.count()
    pages = q.order_by(RagPage.doc_filename, RagPage.page_num).offset(offset).limit(limit).all()
    return {
        "total": total,
        "pages": [
            {
                "id": p.id,
                "doc_filename": p.doc_filename,
                "page_num": p.page_num,
                "indexed": p.colpali_vecs is not None,
                "backend": p.backend,
            }
            for p in pages
        ],
    }


@router.get("/rag/pages/{page_id}")
def get_page(
    page_id: str,
    db: Session = Depends(get_db),
):
    """Serve a rendered PDF page image retrieved by ColPali visual search."""
    page = get_rag_page(db, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")
    return Response(
        content=page.image_data,
        media_type="image/png",
        headers={
            "Cache-Control": "public, max-age=86400",
            "Content-Disposition": f'inline; filename="page_{page.page_num}.png"',
        },
    )


@router.post("/rag/pages/{page_id}/identify")
async def identify_page(
    page_id: str,
    db: Session = Depends(get_db),
):
    """Use GPT Vision to describe the content of a gallery page image."""
    import base64
    from api.services.ai_providers.registry import provider_registry

    page = get_rag_page(db, page_id)
    if not page:
        raise HTTPException(status_code=404, detail="Page not found")

    provider = provider_registry.get_active()
    if not provider:
        raise HTTPException(status_code=503, detail="No AI provider available")

    # Convert stored PNG bytes → base64
    img_b64 = base64.b64encode(page.image_data).decode()

    system_prompt = (
        "You are an expert X-ray imaging scientist and technical analyst with deep knowledge of "
        "security screening, cargo inspection, medical imaging, and radiation physics. "
        "Your role is to carefully examine the provided document page or X-ray image and produce a "
        "structured, accurate description for a professional research platform."
    )
    user_prompt = (
        f"Please analyse this page from the document '{page.doc_filename}', page {page.page_num}.\n\n"
        "Provide a structured response with these sections:\n\n"
        "**📄 Page Type**\n"
        "Identify what kind of page this is (e.g. X-ray scan, CT slice, diagram, data table, "
        "schematic, photograph, text page, chart, etc.).\n\n"
        "**🔍 Content Description**\n"
        "Describe in detail what is visible — objects, materials, structures, labels, measurements, "
        "annotations, or key text. For X-ray images: describe the subject, density patterns, "
        "notable features, and any areas of interest.\n\n"
        "**🧪 Technical Observations**\n"
        "Note any technical details: imaging parameters visible, scale bars, energy levels, "
        "equipment identifiers, colour coding, or data values shown.\n\n"
        "**📌 Key Information**\n"
        "Summarise the 3–5 most important facts or findings from this page that would be "
        "useful to a researcher or security operator.\n\n"
        "Be factual and precise. Do not speculate beyond what is visible."
    )

    # Use the provider's vision API directly via chat completions
    client = provider._client()  # type: ignore[attr-defined]
    model = provider._model()    # type: ignore[attr-defined]

    try:
        response = await client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{img_b64}"},
                        },
                    ],
                },
            ],
            max_completion_tokens=1200,
        )
        try:
            from api.utils.usage_recorder import record_usage_from_response
            record_usage_from_response(
                "RAG Vision Analysis", response,
                sub_feature="page_vision",
                meta={"page_id": page_id},
            )
        except Exception:
            pass
        description = response.choices[0].message.content or "No description returned."
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Vision analysis failed: {e}")

    return {
        "page_id": page_id,
        "doc_filename": page.doc_filename,
        "page_num": page.page_num,
        "description": description,
    }


@router.get("/rag/status")
async def rag_status(db: Session = Depends(get_db)):
    """Report the active ColPali backend and indexing progress."""
    from api.db.crud import get_all_rag_pages, get_all_rag_images
    from api.db.models import RagPage

    backend = await get_backend()
    pages = get_all_rag_pages(db)
    images = get_all_rag_images(db)

    return {
        "colpali_backend": backend,
        "pages_total": len(pages),
        "pages_indexed": sum(1 for p in pages if p.colpali_vecs),
        "images_total": len(images),
        "images_captioned": sum(1 for i in images if i.caption),
    }


@router.patch("/rag/pptx/{doc_id}/source-control")
def update_pptx_source_control(
    doc_id: str,
    body: PptxSourceControlBody,
    db: Session = Depends(get_db),
):
    """Update source-control flags for an indexed PPTX reference file."""
    from api.services.ppt_reference_service import update_source_control

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    try:
        return update_source_control(db, doc_id, updates)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
