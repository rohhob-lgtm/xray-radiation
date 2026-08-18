"""
Large file upload routes — chunked upload, preflight, job control, config.

Endpoints:
  GET  /api/config/upload-limits                         — live limit settings (no auth)
  POST /api/rag/preflight                                — cost/batch estimate (no file upload)
  POST /api/rag/upload/start                             — start a chunked upload session
  PUT  /api/rag/upload/{session_id}/chunk/{chunk_index}  — upload one chunk (raw binary)
  POST /api/rag/upload/{session_id}/complete             — assemble + queue background job
  GET  /api/rag/jobs/{job_id}/status                     — real-time job progress
  POST /api/rag/jobs/{job_id}/pause                      — pause processing
  POST /api/rag/jobs/{job_id}/resume                     — resume paused job
  POST /api/rag/jobs/{job_id}/cancel                     — cancel job
  POST /api/rag/jobs/{job_id}/approve-cost               — unblock cost gate
  POST /api/rag/jobs/{job_id}/retry                      — retry failed job
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import pathlib
import shutil
import uuid
from typing import Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.db.models import ProcessingJob, RagDocument, UploadSession
from api.db.crud import create_rag_document, rag_document_to_dict
from api.middleware.auth import optional_auth, require_auth

router = APIRouter(tags=["large-upload"])
log = logging.getLogger(__name__)

# ── Temp directory for chunk storage ─────────────────────────────────────────
_TEMP_ROOT = pathlib.Path("/tmp/rag_uploads")
_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

_CHUNK_SIZE_BYTES = settings.upload_chunk_size_mb * 1024 * 1024


# ─────────────────────────────────────────────────────────────────────────────
# 1. Config endpoint
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/config/upload-limits")
def get_upload_limits():
    """Return all configurable upload and cost limits. No auth required."""
    return {
        "max_upload_size_mb": settings.max_upload_size_mb,
        "max_pdf_pages": settings.max_pdf_pages,
        "max_pptx_slides": settings.max_pptx_slides,
        "max_docx_pages": settings.max_docx_pages,
        "max_xlsx_sheets": settings.max_xlsx_sheets,
        "max_zip_uncompressed_size_mb": settings.max_zip_uncompressed_size_mb,
        "max_zip_file_count": settings.max_zip_file_count,
        "max_study_cost_per_file_usd": settings.max_study_cost_per_file_usd,
        "max_ai_calls_per_file": settings.max_ai_calls_per_file,
        "max_tokens_per_batch": settings.max_tokens_per_batch,
        "max_concurrent_study_jobs": settings.max_concurrent_study_jobs,
        "upload_chunk_size_mb": settings.upload_chunk_size_mb,
        "chunked_upload_threshold_mb": settings.chunked_upload_threshold_mb,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 2. Pre-flight analysis (no file upload)
# ─────────────────────────────────────────────────────────────────────────────

# Average page sizes for heuristic estimates (bytes/page)
_AVG_PAGE_BYTES: dict[str, int] = {
    "pdf": 50_000,
    "pptx": 100_000,
    "docx": 3_000,
    "xlsx": 20_000,
    "zip": 500_000,
}
# GPT-4o input cost per token
_COST_PER_INPUT_TOKEN = 0.000005
_COST_PER_OUTPUT_TOKEN = 0.000015
_AVG_CHARS_PER_PAGE = 2_000     # characters per page of text
_CHARS_PER_TOKEN = 4


@router.post("/rag/preflight")
def preflight(body: dict = Body(...)):
    """
    Estimate processing cost and batch count for a file without uploading it.
    Accepts {filename, size_bytes}. Returns estimates. No API calls made.
    """
    filename: str = body.get("filename", "file.pdf")
    size_bytes: int = int(body.get("size_bytes", 0))
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "pdf"

    # Enforce size limit
    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if size_bytes > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size {size_bytes // 1024 // 1024} MB exceeds limit of {settings.max_upload_size_mb} MB",
        )

    # Estimate page / slide / sheet count
    avg_page = _AVG_PAGE_BYTES.get(ext, 50_000)
    pages_estimated = max(1, size_bytes // avg_page)

    # Apply per-type page limits
    limit_map = {
        "pdf": settings.max_pdf_pages,
        "pptx": settings.max_pptx_slides,
        "docx": settings.max_docx_pages,
        "xlsx": settings.max_xlsx_sheets,
    }
    page_limit = limit_map.get(ext, 99999)
    if pages_estimated > page_limit:
        raise HTTPException(
            status_code=413,
            detail=f"Estimated {pages_estimated} pages exceeds the {page_limit}-page limit for .{ext} files",
        )

    # Estimate batches
    from api.services.extraction_service import (
        PDF_PAGES_PER_BATCH, PPTX_SLIDES_PER_BATCH, DOCX_SECTIONS_PER_BATCH
    )
    batch_size_map = {
        "pdf": PDF_PAGES_PER_BATCH,
        "pptx": PPTX_SLIDES_PER_BATCH,
        "docx": DOCX_SECTIONS_PER_BATCH,
        "xlsx": 1,
    }
    batch_size = batch_size_map.get(ext, 25)
    batches_estimated = max(1, (pages_estimated + batch_size - 1) // batch_size)

    # Estimate token usage
    chars_total = pages_estimated * _AVG_CHARS_PER_PAGE
    tokens_total = chars_total // _CHARS_PER_TOKEN
    # Study pipeline: one GPT-4o call on up to 90k chars
    study_input_tokens = min(tokens_total, 22_500)
    study_output_tokens = 8_000

    cost_min = study_input_tokens * _COST_PER_INPUT_TOKEN + study_output_tokens * _COST_PER_OUTPUT_TOKEN
    cost_max = cost_min * 1.5  # upper bound with overhead

    max_cost = settings.max_study_cost_per_file_usd
    exceeds_cost_limit = cost_min > max_cost

    # Estimate vision images
    vision_images = 0
    if ext in ("pdf", "pptx"):
        vision_images = max(0, pages_estimated // 3)  # rough: 1 image per 3 pages

    # Estimate processing time (seconds)
    time_estimate_s = max(30, batches_estimated * 8 + 60)  # 8s/batch + 60s study

    return {
        "filename": filename,
        "ext": ext,
        "size_bytes": size_bytes,
        "size_mb": round(size_bytes / 1024 / 1024, 1),
        "pages_estimated": pages_estimated,
        "batches_estimated": batches_estimated,
        "token_estimate_low": study_input_tokens,
        "token_estimate_high": int(study_input_tokens * 1.5),
        "cost_estimate_min_usd": round(cost_min, 4),
        "cost_estimate_max_usd": round(cost_max, 4),
        "exceeds_cost_limit": exceeds_cost_limit,
        "limit_usd": max_cost,
        "vision_images_estimated": vision_images,
        "estimated_processing_seconds": time_estimate_s,
        "vision_status": "disabled",
    }


# ─────────────────────────────────────────────────────────────────────────────
# 3. Chunked upload — start
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/rag/upload/start", status_code=201)
def start_chunked_upload(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """
    Begin a chunked upload session.
    Accepts {filename, total_size, document_type}.
    Returns {session_id, chunk_size, total_chunks}.
    """
    filename: str = body.get("filename", "upload")
    total_size: int = int(body.get("total_size", 0))
    document_type: str = body.get("document_type", "other")

    if not filename or total_size <= 0:
        raise HTTPException(status_code=400, detail="filename and total_size are required")

    max_bytes = settings.max_upload_size_mb * 1024 * 1024
    if total_size > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"File size {total_size // 1024 // 1024} MB exceeds maximum of {settings.max_upload_size_mb} MB",
        )

    chunk_size = _CHUNK_SIZE_BYTES
    total_chunks = max(1, (total_size + chunk_size - 1) // chunk_size)

    session_id = str(uuid.uuid4())
    temp_dir = str(_TEMP_ROOT / session_id / "chunks")
    pathlib.Path(temp_dir).mkdir(parents=True, exist_ok=True)

    session = UploadSession(
        id=session_id,
        filename=filename,
        total_size=total_size,
        chunk_size=chunk_size,
        total_chunks=total_chunks,
        received_chunks=[False] * total_chunks,
        status="uploading",
        temp_dir=temp_dir,
        document_type=document_type,
    )
    db.add(session)
    db.commit()

    log.info(
        "START_UPLOAD | session_id=%s filename=%s total_size=%d chunk_size=%d total_chunks=%d",
        session_id,
        filename,
        total_size,
        chunk_size,
        total_chunks,
    )
    log.info("Upload session %s started: %s (%d bytes, %d chunks)", session_id, filename, total_size, total_chunks)
    return {
        "session_id": session_id,
        "chunk_size": chunk_size,
        "total_chunks": total_chunks,
    }


# ─────────────────────────────────────────────────────────────────────────────
# 4. Chunked upload — receive one chunk
# ─────────────────────────────────────────────────────────────────────────────

@router.put("/rag/upload/{session_id}/chunk/{chunk_index}")
async def upload_chunk(
    session_id: str,
    chunk_index: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """
    Receive one raw binary chunk and write it to disk.
    Idempotent — if the chunk already exists, returns success without rewriting.
    """
    session = db.query(UploadSession).filter(UploadSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.status != "uploading":
        raise HTTPException(status_code=409, detail=f"Session is in state '{session.status}', not 'uploading'")
    if chunk_index < 0 or chunk_index >= session.total_chunks:
        raise HTTPException(status_code=400, detail=f"chunk_index must be 0–{session.total_chunks - 1}")

    chunk_path = pathlib.Path(session.temp_dir) / f"{chunk_index}.part"

    # Idempotent: if chunk already on disk, return success
    received = list(session.received_chunks)
    if received[chunk_index] and chunk_path.exists():
        return {"received": sum(received), "total": session.total_chunks, "chunk": chunk_index}

    # Read raw body (streaming — doesn't buffer the entire chunk)
    data = await request.body()
    if not data:
        raise HTTPException(status_code=400, detail="Empty chunk body")

    # Write to disk
    with open(chunk_path, "wb") as f:
        f.write(data)

    # Mark received
    received[chunk_index] = True
    session.received_chunks = received
    db.commit()

    log.debug("Chunk %d/%d received for session %s (%d bytes)", chunk_index + 1, session.total_chunks, session_id, len(data))
    return {"received": sum(received), "total": session.total_chunks, "chunk": chunk_index}


# ─────────────────────────────────────────────────────────────────────────────
# 5. Chunked upload — assemble + create job
# ─────────────────────────────────────────────────────────────────────────────

@router.post("/rag/upload/{session_id}/complete", status_code=201)
async def complete_chunked_upload(
    session_id: str,
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """
    Verify all chunks received, assemble the file, SHA-256 dedup check,
    create RagDocument + ProcessingJob, and start background processing.
    """
    session = db.query(UploadSession).filter(UploadSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=404, detail="Upload session not found")
    if session.status == "complete":
        # Fully idempotent — return whatever result was recorded at first completion.
        # This covers three cases:
        #   (a) normal upload → session.job_id set
        #   (b) duplicate detected → session.result_doc_id set, no job
        #   (c) degenerate: session marked complete with nothing stored (should not occur)
        if session.job_id:
            existing_job = db.query(ProcessingJob).filter(ProcessingJob.id == session.job_id).first()
            if existing_job:
                return {"doc_id": existing_job.doc_id, "job_id": existing_job.id}
        if session.result_doc_id:
            # Duplicate path — re-derive the existing filename without touching temp files
            existing_doc = db.query(RagDocument).filter(RagDocument.id == session.result_doc_id).first()
            return {
                "doc_id": session.result_doc_id,
                "job_id": None,
                "duplicate": True,
                "existing_filename": existing_doc.filename if existing_doc else session.filename,
            }
        # Fallback: session marked complete but nothing stored — idempotent 400
        raise HTTPException(
            status_code=400,
            detail="Session is already complete but its result was not recorded; please start a new upload session",
        )

    # Check all chunks received
    received = session.received_chunks
    missing = [i for i, r in enumerate(received) if not r]
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing chunks: {missing[:10]}{'...' if len(missing) > 10 else ''}",
        )

    # Assemble file from parts (streaming — never load all in RAM)
    ext = session.filename.rsplit(".", 1)[-1].lower() if "." in session.filename else "bin"
    assembled_path = _TEMP_ROOT / session_id / f"assembled.{ext}"
    assembled_path.parent.mkdir(parents=True, exist_ok=True)

    sha256 = hashlib.sha256()
    total_written = 0

    try:
        with open(assembled_path, "wb") as out:
            for i in range(session.total_chunks):
                chunk_path = pathlib.Path(session.temp_dir) / f"{i}.part"
                if not chunk_path.exists():
                    raise HTTPException(status_code=500, detail=f"Chunk {i} file missing on disk")
                with open(chunk_path, "rb") as chunk_f:
                    while True:
                        block = chunk_f.read(1024 * 1024)  # 1 MB blocks
                        if not block:
                            break
                        out.write(block)
                        sha256.update(block)
                        total_written += len(block)
    except HTTPException:
        raise
    except Exception as exc:
        log.error("File assembly failed for session %s: %s", session_id, exc)
        raise HTTPException(status_code=500, detail=f"File assembly failed: {exc}")

    file_sha256 = sha256.hexdigest()

    # Duplicate check
    from api.db.models import DocumentHash
    existing_hash = db.query(DocumentHash).filter(DocumentHash.sha256 == file_sha256).first()
    if existing_hash:
        # Duplicate detected — persist result on session BEFORE cleaning up temp files
        # so that idempotent re-delivery can return the same stable response.
        existing_doc = db.query(RagDocument).filter(RagDocument.id == existing_hash.doc_id).first()
        if existing_doc:
            session.status = "complete"
            session.result_doc_id = existing_hash.doc_id  # persisted for re-delivery
            db.commit()
            _cleanup_session_temp(session_id)  # safe to clean up only after commit
            log.info("Duplicate detected for %s — linking to existing doc %s", session.filename, existing_hash.doc_id)
            return {
                "doc_id": existing_hash.doc_id,
                "job_id": None,
                "duplicate": True,
                "existing_filename": existing_doc.filename,
            }

    # Create RagDocument stub
    user_id = user["id"] if user else None
    doc = create_rag_document(
        db,
        user_id=user_id,
        filename=session.filename,
        document_type=session.document_type,
        content="__processing__",
        status="processing",
    )

    # Create ProcessingJob
    job = ProcessingJob(
        doc_id=doc.id,
        filename=session.filename,
        file_path=str(assembled_path),
        status="queued",
        current_stage="Queued for processing",
        total_batches=0,
    )
    db.add(job)
    db.flush()  # get job.id before committing session
    session.status = "complete"
    session.job_id = job.id          # re-delivery key for normal uploads
    session.result_doc_id = doc.id   # re-delivery key for all completions
    db.commit()
    db.refresh(job)

    # Delete chunk parts (assembled file is kept until job completes)
    _cleanup_chunk_parts(session.temp_dir)

    # Launch background job
    from api.services.job_runner import run_processing_job
    asyncio.create_task(run_processing_job(job.id))

    log.info(
        "UPLOAD_OK | session_id=%s doc_id=%s job_id=%s filename=%s total_bytes=%d",
        session_id,
        doc.id,
        job.id,
        session.filename,
        total_written,
    )
    log.info("Upload complete: %s → doc %s, job %s (%d bytes)", session.filename, doc.id, job.id, total_written)
    return {"doc_id": doc.id, "job_id": job.id}


# ─────────────────────────────────────────────────────────────────────────────
# 6. Job status and control
# ─────────────────────────────────────────────────────────────────────────────

@router.get("/rag/jobs/{job_id}/status")
def get_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Real-time job progress for frontend polling.
    Requires authentication; returns 403 if the caller does not own the job.
    """
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _assert_job_owner(db, job, user)

    status = job.status
    stage_map = {
        "queued":                ("uploading",   "Queued for processing…",        15),
        "extracting":            ("extracting",  job.current_stage or "Extracting…", _extraction_pct(job)),
        "studying":              ("studying",    job.current_stage or "Studying document…", 55),
        "integrating":           ("integrating", "Integrating knowledge…",        88),
        "completed":             ("completed",   "Completed",                     100),
        "failed":                ("error",       job.error_message or "Processing failed", 0),
        "cancelled":             ("error",       "Cancelled",                     0),
        "paused":                ("studying",    "Paused",                        _extraction_pct(job)),
        "awaiting_cost_approval":("studying",    "Awaiting cost approval",        50),
    }
    stage, label, pct = stage_map.get(status, ("extracting", job.current_stage or status, 25))

    # Also check underlying study job for more granular status
    from api.db.models import StudyJob
    study_job = (
        db.query(StudyJob)
        .filter(StudyJob.doc_id == job.doc_id)
        .order_by(StudyJob.created_at.desc())
        .first()
    )
    if study_job and status not in ("completed", "failed", "cancelled"):
        if study_job.status in ("integrated", "approved"):
            stage, label, pct = "completed", "Completed", 100
        elif study_job.status == "studying":
            stage, label, pct = "generating", "Generating knowledge…", 65
        elif study_job.status == "validating":
            stage, label, pct = "integrating", "Integrating knowledge…", 88

    response = {
        "job_id": job.id,
        "doc_id": job.doc_id,
        "status": status,
        "stage": stage,
        "label": label,
        "pct": pct,
        "current_batch": job.current_batch,
        "total_batches": job.total_batches,
        "cost_incurred_usd": round(job.cost_incurred_usd or 0, 4),
        "ai_calls_made": job.ai_calls_made or 0,
        "error_message": job.error_message,
        "updated_at": job.updated_at.isoformat() if job.updated_at else None,
    }

    if status == "awaiting_cost_approval":
        checkpoint = job.checkpoint_data or {}
        response["estimated_cost_usd"] = checkpoint.get("estimated_cost_usd", 0)
        response["limit_usd"] = settings.max_study_cost_per_file_usd

    if study_job and study_job.status in ("integrated", "approved"):
        response["nodes"] = study_job.report_graph_nodes_added
        response["edges"] = study_job.report_graph_edges_added

    return response


def _extraction_pct(job: ProcessingJob) -> int:
    if job.total_batches <= 0:
        return 20
    raw = job.current_batch / max(1, job.total_batches / 2)  # extraction is first half
    return max(20, min(50, int(10 + raw * 40)))


@router.post("/rag/jobs/{job_id}/pause")
def pause_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    job = _get_owned_job(db, job_id, user)
    if job.status not in ("queued", "extracting", "studying"):
        raise HTTPException(status_code=409, detail=f"Cannot pause job in state '{job.status}'")
    job.status = "paused"
    db.commit()
    return {"job_id": job_id, "status": "paused"}


@router.post("/rag/jobs/{job_id}/resume")
def resume_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    job = _get_owned_job(db, job_id, user)
    if job.status != "paused":
        raise HTTPException(status_code=409, detail=f"Cannot resume job in state '{job.status}'")
    job.status = "queued"
    db.commit()
    from api.services.job_runner import run_processing_job
    asyncio.create_task(run_processing_job(job_id))
    return {"job_id": job_id, "status": "queued"}


@router.post("/rag/jobs/{job_id}/cancel")
def cancel_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    job = _get_owned_job(db, job_id, user)
    if job.status in ("completed", "failed"):
        raise HTTPException(status_code=409, detail=f"Cannot cancel job in terminal state '{job.status}'")
    job.status = "cancelled"
    job.error_message = "Cancelled by user"
    db.commit()
    _cleanup_session_by_job(job)
    return {"job_id": job_id, "status": "cancelled"}


@router.post("/rag/jobs/{job_id}/approve-cost")
def approve_cost(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    job = _get_owned_job(db, job_id, user)
    if job.status != "awaiting_cost_approval":
        raise HTTPException(status_code=409, detail=f"Job is not awaiting cost approval (status: '{job.status}')")
    checkpoint = job.checkpoint_data or {}
    checkpoint["cost_approved"] = True
    job.checkpoint_data = checkpoint
    job.status = "queued"
    db.commit()
    from api.services.job_runner import run_processing_job
    asyncio.create_task(run_processing_job(job_id))
    return {"job_id": job_id, "status": "queued", "message": "Cost approved — processing resumed"}


@router.post("/rag/jobs/{job_id}/retry")
def retry_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    job = _get_owned_job(db, job_id, user)
    if job.status not in ("failed", "cancelled"):
        raise HTTPException(status_code=409, detail=f"Cannot retry job in state '{job.status}'")
    job.status = "queued"
    job.error_message = None
    db.commit()
    from api.services.job_runner import run_processing_job
    asyncio.create_task(run_processing_job(job_id))
    return {"job_id": job_id, "status": "queued"}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _resolve_job_owner(db: Session, job: ProcessingJob) -> Optional[str]:
    """
    Look up the user_id of the RagDocument linked to this job via a direct
    DB query (not lazy relationship — avoids session state issues).

    Returns:
      - str user_id if the document has an owner
      - None if the document explicitly has no user_id (pre-auth upload)

    Raises HTTPException(500) on unexpected DB/load failure (fail-closed).
    """
    try:
        doc = db.query(RagDocument).filter(RagDocument.id == job.doc_id).first()
        if doc is None:
            # Document was deleted — deny access
            raise HTTPException(status_code=404, detail="Associated document not found")
        return doc.user_id  # may be None for pre-auth uploads
    except HTTPException:
        raise
    except Exception as exc:
        log.error("Failed to resolve owner for job %s: %s", job.id, exc)
        # Fail-closed: any unexpected error during ownership resolution is a 500
        raise HTTPException(status_code=500, detail="Could not verify job ownership — please try again")


def _assert_job_owner(db: Session, job: ProcessingJob, user: dict) -> None:
    """
    Raise 403 if the authenticated user doesn't own this job's document.

    Fails closed: resolution errors become 500, never silently allow access.
    Allows access only when owner_id is explicitly None (document has no owner in DB),
    which is a known case for documents uploaded before per-user auth was enforced.
    """
    owner_id = _resolve_job_owner(db, job)
    # owner_id is None → document was created without a user (pre-auth path), allow any authenticated user
    if owner_id is None:
        return
    if user.get("id") != owner_id:
        raise HTTPException(status_code=403, detail="Access denied — this job belongs to another user")


def _get_owned_job(db: Session, job_id: str, user: dict) -> ProcessingJob:
    """Fetch job and verify ownership. Raises 404, 403, or 500 as appropriate."""
    job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    _assert_job_owner(db, job, user)
    return job


def _cleanup_session_temp(session_id: str) -> None:
    """Remove all temp files for a session."""
    session_dir = _TEMP_ROOT / session_id
    try:
        if session_dir.exists():
            shutil.rmtree(session_dir, ignore_errors=True)
    except Exception as exc:
        log.debug("Temp cleanup failed for session %s: %s", session_id, exc)


def _cleanup_chunk_parts(temp_dir: str) -> None:
    """Remove individual chunk .part files after assembly (keep assembled file)."""
    try:
        chunk_dir = pathlib.Path(temp_dir)
        for part in chunk_dir.glob("*.part"):
            part.unlink(missing_ok=True)
    except Exception as exc:
        log.debug("Chunk parts cleanup failed: %s", exc)


def _cleanup_session_by_job(job: ProcessingJob) -> None:
    """Remove assembled file and temp dir for a job."""
    try:
        if job.file_path:
            assembled = pathlib.Path(job.file_path)
            if assembled.exists():
                assembled.unlink(missing_ok=True)
            # Remove parent session dir
            parent = assembled.parent.parent
            if parent.exists() and str(_TEMP_ROOT) in str(parent):
                shutil.rmtree(parent, ignore_errors=True)
    except Exception as exc:
        log.debug("Session cleanup by job failed: %s", exc)
