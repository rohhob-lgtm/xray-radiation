"""
Persistent background job runner for large file processing.

ProcessingJob records survive server restarts (unlike asyncio.create_task).
The runner reads file from disk in batches, updates checkpoint after each,
and calls the study pipeline with cost tracking.

Job lifecycle:
  queued → extracting → studying → integrating → completed
                     ↘ failed (at any stage)
                     ↘ paused (user-requested)
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import pathlib
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from api.db.base import SessionLocal
from api.db.models import ProcessingJob, RagDocument
from api.config import settings

log = logging.getLogger(__name__)

# ── In-memory set of running job IDs (prevents duplicate runners) ─────────────
_RUNNING_JOBS: set[str] = set()

# Cost per 1k tokens (gpt-4o)
_GPT4O_INPUT_COST_PER_1K = 0.005
_GPT4O_OUTPUT_COST_PER_1K = 0.015


def _pipeline_log(event: str, job: ProcessingJob, **meta) -> None:
    payload = {
        "job_id": job.id,
        "doc_id": job.doc_id,
        "filename": job.filename,
        **meta,
    }
    try:
        log.info("%s | %s", event, json.dumps(payload, ensure_ascii=True, default=str))
    except Exception:
        log.info("%s | %s", event, payload)


def _extraction_complete(job: ProcessingJob) -> bool:
    """
    Return True if extraction has already been completed for this job,
    so the runner should skip directly to the study phase.

    Conditions that indicate extraction is done:
      - checkpoint has extraction_complete=True (set at extraction end)
      - job status is 'studying', 'integrating', or 'awaiting_cost_approval'
        (these states are only entered after extraction finishes)
    """
    checkpoint = job.checkpoint_data or {}
    if checkpoint.get("extraction_complete"):
        return True
    if job.status in ("studying", "integrating", "awaiting_cost_approval"):
        return True
    return False


async def run_processing_job(job_id: str) -> None:
    """
    Phase-aware job runner coroutine.

    Determines which phase to start from based on job status and checkpoint:
      - queued / extracting / paused-during-extraction → Phase 1 (extraction) then Phase 2 (study)
      - studying / integrating / awaiting_cost_approval / paused-after-extraction → Phase 2 only

    Safe to call multiple times — duplicate calls are no-ops.
    """
    if job_id in _RUNNING_JOBS:
        log.info("Job %s already running — skipping duplicate", job_id)
        return

    _RUNNING_JOBS.add(job_id)
    db = SessionLocal()

    try:
        job = db.query(ProcessingJob).filter(ProcessingJob.id == job_id).first()
        if not job:
            log.error("Job %s not found in DB", job_id)
            return

        if job.status in ("completed", "failed", "cancelled"):
            log.info("Job %s already in terminal state '%s'", job_id, job.status)
            return

        log.info(
            "Starting job %s for file %s (status=%s, extraction_complete=%s)",
            job_id, job.filename, job.status, _extraction_complete(job),
        )
        _pipeline_log("PIPELINE_START", job, status=job.status, extraction_complete=_extraction_complete(job))

        # ── Phase 1: extraction (skip if already done) ─────────────────────────
        if not _extraction_complete(job):
            await _run_extraction_phase(db, job)

            # Reload after extraction
            db.refresh(job)
            if job.status in ("failed", "cancelled", "paused"):
                return

        # ── Phase 2: study pipeline ────────────────────────────────────────────
        await _run_study_phase(db, job)

    except Exception as exc:
        log.error("Job %s runner failed: %s", job_id, exc, exc_info=True)
        try:
            db.refresh(job)
            if job.status not in ("completed", "failed", "cancelled"):
                _fail_job(db, job, f"Unexpected runner error: {exc}")
        except Exception:
            pass
    finally:
        db.close()
        _RUNNING_JOBS.discard(job_id)


def _text_accumulator_path(job: ProcessingJob) -> pathlib.Path:
    """
    Per-job file that accumulates extracted text on disk.
    Stored next to the assembled file so it survives server restarts.
    Using a file avoids storing large blobs in the checkpoint JSON column.
    """
    return pathlib.Path(job.file_path).parent / "extracted_text.txt"


async def _run_extraction_phase(db: Session, job: ProcessingJob) -> None:
    """
    Extract text from the assembled file in batches, appending each batch to
    a per-job text file on disk.  The checkpoint stores only the last-completed
    batch index; the on-disk file is the authoritative accumulated text.

    On pause/restart, processing resumes from `last_extraction_batch` and
    appends to the existing file — no text is ever lost.
    """
    from api.services.extraction_service import extract_batches

    file_path = pathlib.Path(job.file_path)
    if not file_path.exists():
        _fail_job(db, job, f"Assembled file not found: {job.file_path}", stage="Upload")
        return

    # Checkpoint stores only the batch offset (no text blobs)
    checkpoint = job.checkpoint_data or {}
    start_batch = checkpoint.get("last_extraction_batch", 0)
    text_file = _text_accumulator_path(job)

    # On a fresh start, truncate any stale accumulator; on resume keep it
    if start_batch == 0:
        text_file.write_text("", encoding="utf-8")

    job.status = "extracting"
    job.current_stage = "Extracting text"
    db.commit()
    _pipeline_log("PARSER_OK", job, file_path=str(file_path))

    loop = asyncio.get_event_loop()
    batch_found = False

    # Use an unbounded queue (maxsize=0) so the producer thread can never block
    # on put(). This eliminates the deadlock that would occur if the consumer
    # exits early (pause/cancel) while the producer is blocked on a full queue.
    # Per-batch memory is bounded by extraction batch size (~120 KB each), not
    # total file size, because text is written to disk immediately per batch.
    import queue as _queue
    _SENTINEL = object()
    batch_queue: _queue.Queue = _queue.Queue(maxsize=0)  # unbounded — no put() blocking
    _extraction_error: list[Exception] = []

    def _produce():
        try:
            for b in extract_batches(file_path, start_batch=start_batch):
                batch_queue.put(b)  # never blocks (unbounded queue)
        except Exception as exc:
            _extraction_error.append(exc)
        finally:
            batch_queue.put(_SENTINEL)  # always signals consumer to stop

    producer_future = loop.run_in_executor(None, _produce)

    try:
        while True:
            batch = await loop.run_in_executor(None, batch_queue.get)
            if batch is _SENTINEL:
                break

            batch_found = True

            # Re-fetch to check for pause/cancel
            db.refresh(job)
            if job.status in ("cancelled", "failed"):
                # Producer can no longer block — safe to exit and await
                return
            if job.status == "paused":
                # Checkpoint offset only — text file on disk is authoritative
                job.checkpoint_data = {
                    "last_extraction_batch": batch.batch_index,
                    "has_text_file": True,
                }
                db.commit()
                return

            # Append batch text to disk file (O(1) memory per batch)
            if batch.text.strip():
                with open(text_file, "a", encoding="utf-8") as tf:
                    tf.write(batch.text)
                    tf.write("\n\n")

            total_b = batch.total_batches
            cur_b = batch.batch_index + 1
            job.current_batch = cur_b
            job.total_batches = total_b * 2  # extraction + study phases
            job.current_stage = f"Extracting batch {cur_b} of {total_b}"
            # Checkpoint: offset only, no text blob
            job.checkpoint_data = {
                "last_extraction_batch": batch.batch_index + 1,
                "has_text_file": True,
            }
            db.commit()
    finally:
        # Always wait for producer thread to exit (it exits promptly because
        # put() never blocks on an unbounded queue).
        await producer_future

    if _extraction_error:
        _fail_job(db, job, f"Extraction failed: {_extraction_error[0]}", stage="Text extraction")
        return

    if not batch_found and start_batch == 0:
        _fail_job(db, job, "No text could be extracted from this file", stage="Parser error")
        return

    # Read full text back from the accumulator file
    try:
        full_text = text_file.read_text(encoding="utf-8")
    except Exception as exc:
        _fail_job(db, job, f"Could not read extracted text file: {exc}", stage="Text extraction")
        return

    if not full_text.strip():
        _fail_job(db, job, "No text extracted from any batch", stage="Parser error")
        return

    _pipeline_log("TEXT_EXTRACTION_OK", job, text_chars=len(full_text), words=len(full_text.split()))

    # Update the RagDocument with extracted content
    try:
        doc = db.query(RagDocument).filter(RagDocument.id == job.doc_id).first()
        if doc:
            doc.content = full_text[:500_000]
            doc.word_count = len(full_text.split())
            doc.status = "extracting"
            db.commit()
    except Exception as exc:
        log.warning("Could not update doc content for job %s: %s", job.id, exc)

    # Checkpoint: mark extraction done with a typed boolean (not a sentinel string).
    # extraction_complete=True is the authoritative signal for run_processing_job
    # to skip Phase 1 on any resume path (startup recovery, cost-gate resume, retry).
    job.checkpoint_data = {
        "extraction_complete": True,   # boolean — never a sentinel string
        "last_extraction_batch": -1,   # -1 = done; numeric for consistent typing
        "text_file_path": str(text_file),
    }
    db.commit()


async def _run_study_phase(db: Session, job: ProcessingJob) -> None:
    """Run the study pipeline on extracted text with cost tracking."""
    from api.services.study_service import (
        run_study_pipeline, compute_sha256, is_duplicate, register_hash
    )

    checkpoint = job.checkpoint_data or {}
    full_text = ""

    # Primary: read from the on-disk text accumulator file (survives restarts)
    text_file_path = checkpoint.get("text_file_path") or str(_text_accumulator_path(job))
    text_file = pathlib.Path(text_file_path)
    if text_file.exists():
        try:
            full_text = text_file.read_text(encoding="utf-8")
        except Exception as exc:
            log.warning("Could not read text file for job %s: %s", job.id, exc)

    # Fallback: RagDocument.content (set during extraction, capped at 500k chars)
    if not full_text:
        doc = db.query(RagDocument).filter(RagDocument.id == job.doc_id).first()
        if doc and doc.content and doc.content != "__processing__":
            full_text = doc.content
        else:
            _fail_job(db, job, "No extracted text available for study pipeline", stage="Parser error")
            return

    job.status = "studying"
    job.current_stage = "Studying document"
    db.commit()

    # Cost gate check — estimate cost and require approval if over limit
    estimated_cost = _estimate_study_cost(full_text)
    max_cost = getattr(settings, "max_study_cost_per_file_usd", 2.00)

    if estimated_cost > max_cost and not checkpoint.get("cost_approved"):
        job.status = "awaiting_cost_approval"
        job.current_stage = "Awaiting cost approval"
        job.checkpoint_data = {**checkpoint, "estimated_cost_usd": estimated_cost}
        db.commit()
        log.info(
            "Job %s paused for cost approval: estimated $%.4f exceeds limit $%.2f",
            job.id, estimated_cost, max_cost,
        )
        _pipeline_log("AI_ANALYSIS_PAUSED_COST_GATE", job, estimated_cost_usd=estimated_cost, limit_usd=max_cost)
        return

    # Check duplicate — stream full file for SHA-256 so the hash matches the
    # one computed at upload-completion time (full-file, not first-10MB).
    file_path = pathlib.Path(job.file_path)
    if file_path.exists():
        try:
            import hashlib as _hashlib
            _sha = _hashlib.sha256()
            with open(file_path, "rb") as f:
                while True:
                    block = f.read(1024 * 1024)
                    if not block:
                        break
                    _sha.update(block)
            sha = _sha.hexdigest()
            existing = is_duplicate(db, sha)
            if existing and existing != job.doc_id:
                job.status = "completed"
                job.current_stage = "Completed (duplicate detected)"
                job.checkpoint_data = {**checkpoint, "duplicate_of": existing}
                db.commit()
                _finalize_doc(db, job)
                _pipeline_log("ANALYSIS_COMPLETED", job, duplicate_of=existing)
                return
            register_hash(db, sha, job.doc_id, job.filename)
        except Exception as exc:
            log.debug("Hash check failed: %s", exc)
            sha = None
    else:
        sha = None

    # Run study pipeline
    try:
        _pipeline_log("AI_ANALYSIS_START", job, text_chars=len(full_text))
        job.current_stage = "Generating knowledge"
        db.commit()

        study_db = SessionLocal()
        try:
            study_job = await run_study_pipeline(
                study_db,
                job.doc_id,
                job.filename,
                full_text,
                sha256=sha,
                image_count=0,
            )

            # Track cost
            input_tok = study_job.input_tokens or 0
            output_tok = study_job.output_tokens or 0
            cost = (input_tok / 1000 * _GPT4O_INPUT_COST_PER_1K +
                    output_tok / 1000 * _GPT4O_OUTPUT_COST_PER_1K)
            job.cost_incurred_usd = (job.cost_incurred_usd or 0.0) + cost
            job.ai_calls_made = (job.ai_calls_made or 0) + 1

            if study_job.status in ("failed", "error", "stalled"):
                reason = (study_job.rejection_reason or "AI analysis failed").strip()
                stage = reason.split(":", 1)[0] if reason else "AI analysis"
                _fail_job(db, job, reason, stage=stage)
                return

        finally:
            study_db.close()

        job.status = "integrating"
        job.current_stage = "Integrating knowledge"
        db.commit()

        # Give the integration a moment to complete
        await asyncio.sleep(2)

        job.status = "completed"
        job.current_stage = "Completed"
        job.checkpoint_data = {
            **checkpoint,
            "completed_at": datetime.now(timezone.utc).isoformat(),
        }
        db.commit()

        _finalize_doc(db, job)
        _pipeline_log(
            "ANALYSIS_COMPLETED",
            job,
            cost_incurred_usd=round(job.cost_incurred_usd or 0.0, 4),
            ai_calls_made=job.ai_calls_made or 0,
        )
        log.info("Job %s completed for %s — cost $%.4f", job.id, job.filename, job.cost_incurred_usd or 0)

    except Exception as exc:
        log.error("Job %s study phase failed: %s", job.id, exc, exc_info=True)
        _fail_job(db, job, f"Study pipeline error: {exc}", stage="AI analysis")


def _finalize_doc(db: Session, job: ProcessingJob) -> None:
    """Mark the RagDocument as ready when the job completes."""
    try:
        doc = db.query(RagDocument).filter(RagDocument.id == job.doc_id).first()
        if doc and doc.status not in ("ready", "error"):
            doc.status = "ready"
            db.commit()
    except Exception as exc:
        log.warning("Could not finalize doc for job %s: %s", job.id, exc)


def _fail_job(db: Session, job: ProcessingJob, error: str, stage: str = "Processing") -> None:
    try:
        job.status = "failed"
        job.current_stage = stage
        job.error_message = f"{stage}: {error}"[:1000]
        db.commit()
        _pipeline_log("PIPELINE_FAILED", job, stage=stage, error=error[:500])
        # Also mark the doc as error
        doc = db.query(RagDocument).filter(RagDocument.id == job.doc_id).first()
        if doc:
            doc.status = "error"
            db.commit()
    except Exception as exc:
        log.warning("Could not record job failure for %s: %s", job.id, exc)


def _estimate_study_cost(text: str) -> float:
    """Rough cost estimate for studying a document (single GPT-4o call)."""
    tokens_est = len(text) / 4  # ~4 chars per token
    return max(0, tokens_est / 1000 * _GPT4O_INPUT_COST_PER_1K) + 0.02  # add output estimate


async def resume_queued_jobs() -> None:
    """
    Called on startup — resume any non-terminal jobs that survived a server restart.
    The runner is phase-aware: jobs in 'studying'/'integrating'/'awaiting_cost_approval'
    skip extraction and jump directly to the study phase.

    Note: 'paused' jobs are not auto-resumed — they require explicit user action.
    """
    db = SessionLocal()
    try:
        resumable_statuses = [
            "queued",
            "extracting",
            "studying",
            "integrating",
            "awaiting_cost_approval",
        ]
        pending = (
            db.query(ProcessingJob)
            .filter(ProcessingJob.status.in_(resumable_statuses))
            .all()
        )
        if not pending:
            return
        log.info("Startup recovery: found %d pending job(s) to resume", len(pending))
        for job in pending:
            await asyncio.sleep(2)  # stagger to avoid thundering herd
            asyncio.create_task(run_processing_job(job.id))
    except Exception as exc:
        log.warning("Startup job recovery failed: %s", exc)
    finally:
        db.close()
