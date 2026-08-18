"""
Self-Learning Study Pipeline routes.

Endpoints:
  GET  /study/jobs              — list all study jobs (admin)
  GET  /study/jobs/{id}         — single job detail
  POST /study/jobs/{id}/approve — approve, materialise into knowledge graph
  POST /study/jobs/{id}/reject  — reject with reason
  GET  /study/knowledge         — approved knowledge summary
  GET  /study/graph             — persistent knowledge graph (nodes + edges)
  GET  /study/report            — platform-wide learning report
  POST /study/trigger/{doc_id}  — manually trigger study on an already-uploaded doc
"""
from __future__ import annotations
import asyncio
import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func as _f, or_

from api.db import get_db
from api.db.models import (
    StudyJob, KnowledgeNode, KnowledgeEdge,
    RagDocument, DocumentHash,
    TerminologyEntry, ImageClassification, LayoutStyle, ExamPattern,
)
from api.middleware.auth import require_auth
from api.services.study_service import (
    approve_study_job, get_knowledge_context, run_study_pipeline, compute_sha256,
    _call_gpt, _STUDY_PROMPT, _MAX_DOC_CHARS, _validate_study_json, StudyAIError,  # used by in-place retry
)
from api.services.terminology_service import search_terminology
from api.services.exam_learner import list_patterns as list_exam_patterns
from api.services.layout_learner import list_styles, set_default_style, get_style
from api.services.learning_report_service import (
    generate_and_store, get_latest as get_latest_report
)

log = logging.getLogger(__name__)
router = APIRouter(tags=["study"])


# ── helpers ────────────────────────────────────────────────────────────────────

def _require_admin(user: dict) -> None:
    allowed = {
        a.strip() for a in (os.environ.get("ADMIN_USER_IDS") or "").split(",") if a.strip()
    }
    if not allowed:
        return  # no admin list = all authenticated users are admins
    ident = {str(user.get("id") or ""), str(user.get("email") or "")}
    if not (ident & allowed):
        raise HTTPException(status_code=403, detail="Admin access required")


def _job_to_dict(job: StudyJob) -> dict:
    return {
        "id": job.id,
        "doc_id": job.doc_id,
        "filename": job.filename,
        "status": job.status,
        "started_at": job.started_at.isoformat() if getattr(job, "started_at", None) else None,
        "stalled_reason": job.rejection_reason if job.status in ("stalled", "failed", "error") else None,
        "difficulty_level": job.difficulty_level,
        "intended_audience": job.intended_audience,
        "document_purpose": job.document_purpose,
        "confidence_score": job.confidence_score,
        "scores": {
            "educational_value": job.score_educational_value,
            "technical_quality": job.score_technical_quality,
            "image_quality": job.score_image_quality,
            "diagram_quality": job.score_diagram_quality,
            "reference_quality": job.score_reference_quality,
            "safety_coverage": job.score_safety_coverage,
            "maintenance_coverage": job.score_maintenance_coverage,
            "overall": job.score_overall,
        },
        "report": {
            "concepts": job.report_concepts or 0,
            "systems": job.report_systems or 0,
            "components": job.report_components or 0,
            "procedures": job.report_procedures or 0,
            "troubleshooting": job.report_troubleshooting or 0,
            "safety_rules": len(job.extracted_warnings or []),
            "exam_questions": len(job.quiz_ideas or []),
            "figures": job.report_images_understood or 0,
            "references": job.report_new_info_count or 0,
            "pptx_layout": (job.filename or "").lower().endswith(".pptx"),
            "animations": (job.filename or "").lower().endswith(".pptx"),
            "graph_nodes_added": job.report_graph_nodes_added or 0,
            "graph_edges_added": job.report_graph_edges_added or 0,
        },
        "extracted": {
            "systems": job.extracted_systems,
            "components": job.extracted_components,
            "procedures": job.extracted_procedures,
            "terminology": job.extracted_terminology,
            "warnings": job.extracted_warnings,
            "specs": job.extracted_specs,
            "fault_codes": job.extracted_fault_codes,
            "abbreviations": job.extracted_abbreviations,
        },
        "understanding": {
            "purpose": job.document_purpose,
            "audience": job.intended_audience,
            "difficulty": job.difficulty_level,
            "prerequisites": job.prerequisite_knowledge,
            "new_information": job.new_information,
            "missing_topics": job.missing_topics,
            "contradictions": job.contradictions,
        },
        "training_profile": {
            "learning_objectives": job.learning_objectives,
            "instructor_notes": job.instructor_notes,
            "quiz_ideas": job.quiz_ideas,
            "practical_scenarios": job.practical_scenarios,
            "common_mistakes": job.common_mistakes,
            "hands_on_exercises": job.hands_on_exercises,
            "field_tips": job.field_tips,
        },
        "graph": {
            "nodes": job.graph_nodes,
            "edges": job.graph_edges,
        },
        "approved_by": job.approved_by,
        "approved_at": job.approved_at.isoformat() if job.approved_at else None,
        "rejection_reason": job.rejection_reason,
        "archived": getattr(job, "archived", False),
        "model_used": job.model_used,
        "input_tokens": job.input_tokens or 0,
        "output_tokens": job.output_tokens or 0,
        # GPT-4o pricing: $2.50/1M in, $10.00/1M out
        "cost_usd": round(
            ((job.input_tokens or 0) * 2.50 + (job.output_tokens or 0) * 10.00) / 1_000_000, 4
        ),
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
    }


# ── routes ─────────────────────────────────────────────────────────────────────

@router.get("/study/jobs")
def list_study_jobs(
    status: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """List study jobs, optionally filtered by status."""
    _require_admin(user)
    q = db.query(StudyJob).order_by(StudyJob.created_at.desc())
    if status:
        q = q.filter(StudyJob.status == status)
    jobs = q.limit(limit).all()
    return [_job_to_dict(j) for j in jobs]


@router.get("/study/jobs/{job_id}")
def get_study_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    job = db.query(StudyJob).filter(StudyJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Study job not found")
    return _job_to_dict(job)


class ApproveBody(BaseModel):
    pass  # no body required; user identity comes from session


class RejectBody(BaseModel):
    reason: str = ""


@router.post("/study/jobs/{job_id}/approve")
def approve_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Phase 8 — Approve study job and materialise knowledge into the graph."""
    _require_admin(user)

    job = db.query(StudyJob).filter(StudyJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Study job not found")
    if job.status not in ("awaiting_approval", "scored", "rejected"):
        raise HTTPException(
            status_code=400,
            detail=f"Job status is '{job.status}' — only awaiting_approval or scored jobs can be approved",
        )

    approved_by = user.get("name") or user.get("email") or user.get("id") or "admin"
    job = approve_study_job(db, job, approved_by)

    # Register hash so the document is never reprocessed
    if job.sha256:
        from api.services.study_service import register_hash
        register_hash(db, job.sha256, job.doc_id, job.filename)

    return {"ok": True, "status": job.status, "graph_nodes_added": job.report_graph_nodes_added}


@router.post("/study/jobs/approve-all")
def approve_all_jobs(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Approve every job currently in awaiting_approval status."""
    _require_admin(user)
    approved_by = user.get("name") or user.get("email") or user.get("id") or "admin"
    jobs = (
        db.query(StudyJob)
        .filter(StudyJob.status.in_(["awaiting_approval", "scored"]))
        .all()
    )
    total_nodes = 0
    approved_ids = []
    for job in jobs:
        try:
            job = approve_study_job(db, job, approved_by)
            if job.sha256:
                from api.services.study_service import register_hash
                register_hash(db, job.sha256, job.doc_id, job.filename)
            total_nodes += job.report_graph_nodes_added or 0
            approved_ids.append(job.id)
        except Exception as exc:
            log.warning("approve-all: skipping job %s — %s", job.id, exc)
    return {
        "ok": True,
        "approved_count": len(approved_ids),
        "graph_nodes_added": total_nodes,
    }


@router.post("/study/jobs/retry-all")
async def retry_all_failed(
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Re-queue all error/failed/stalled study jobs using existing document text.
    The analysis resumes directly from AI extraction using existing text.
    It automatically retries and falls back between OpenAI and Gemini.
    """
    _require_admin(user)
    jobs = db.query(StudyJob).filter(StudyJob.status.in_(["error", "failed", "stalled"])).all()
    queued = []
    for job in jobs:
        rag_doc = db.query(RagDocument).filter(RagDocument.id == job.doc_id).first()
        if not rag_doc:
            log.warning("retry-all: no rag_document for job %s (%s) — skipping", job.id, job.filename)
            continue
        job.status = "studying"
        db.commit()
        bg.add_task(_run_retry_job, job.id, rag_doc.content)
        queued.append({"id": job.id, "filename": job.filename})
    return {"ok": True, "queued": queued, "count": len(queued)}


async def _run_retry_job(job_id: str, doc_text: str) -> None:
    """
    Background coroutine that runs the full GPT study pipeline on an existing job,
    updating it in-place rather than creating a new record.
    Uses its own SessionLocal so it is independent of the request session.
    """
    from api.db.base import SessionLocal

    db = SessionLocal()
    try:
        job = db.query(StudyJob).filter(StudyJob.id == job_id).first()
        if not job:
            return

        # Build prompt and call AI directly on existing extracted text.
        if not (doc_text or "").strip():
            raise StudyAIError("Parser error", "Extracted text is empty")

        prompt = _STUDY_PROMPT.replace("{document_text}", doc_text[:_MAX_DOC_CHARS])
        log.info(
            "AI_ANALYSIS_START | retry_job_id=%s doc_id=%s filename=%s text_chars=%d",
            job.id,
            job.doc_id,
            job.filename,
            len(doc_text[:_MAX_DOC_CHARS]),
        )
        result = await _call_gpt(prompt, doc_id=job.doc_id, filename=job.filename, job_id=job.id)
        log.info("AI_RESPONSE_RECEIVED | retry_job_id=%s doc_id=%s filename=%s", job.id, job.doc_id, job.filename)

        gpt_json, in_tok, out_tok, model, _provider = result
        gpt_json = _validate_study_json(gpt_json)
        p2 = gpt_json.get("phase2", {})
        p3 = gpt_json.get("phase3", {})
        p4 = gpt_json.get("phase4", {})
        p6 = gpt_json.get("phase6", {})
        p7 = gpt_json.get("phase7", {})

        job.extracted_systems     = p2.get("systems", []) + p2.get("subsystems", [])
        job.extracted_components  = p2.get("components", [])
        job.extracted_procedures  = p2.get("operating_procedures", []) + p2.get("maintenance_procedures", [])
        job.extracted_terminology = p2.get("terminology", [])
        job.extracted_warnings    = p2.get("safety_warnings", [])
        job.extracted_specs       = p2.get("specifications", [])
        job.extracted_fault_codes = p2.get("fault_codes", []) + p2.get("alarms", [])
        job.extracted_abbreviations = p2.get("abbreviations", [])

        job.document_purpose       = p3.get("document_purpose")
        job.intended_audience      = p3.get("intended_audience")
        job.difficulty_level       = p3.get("difficulty_level")
        job.prerequisite_knowledge = p3.get("prerequisite_knowledge", [])
        job.new_information        = p3.get("new_information", [])
        job.contradictions         = p3.get("contradictions", [])
        job.missing_topics         = p3.get("missing_topics", [])
        job.overlapping_docs       = []

        job.graph_nodes = p4.get("nodes", [])
        job.graph_edges = p4.get("edges", [])

        job.learning_objectives  = p6.get("learning_objectives", [])
        job.instructor_notes     = p6.get("instructor_notes", [])
        job.quiz_ideas           = p6.get("quiz_ideas", [])
        job.practical_scenarios  = p6.get("practical_scenarios", [])
        job.common_mistakes      = p6.get("common_mistakes", [])
        job.hands_on_exercises   = p6.get("hands_on_exercises", [])
        job.field_tips           = p6.get("field_tips", [])

        job.score_educational_value  = p7.get("educational_value")
        job.score_technical_quality  = p7.get("technical_quality")
        job.score_image_quality      = p7.get("image_quality")
        job.score_diagram_quality    = p7.get("diagram_quality")
        job.score_reference_quality  = p7.get("reference_quality")
        job.score_safety_coverage    = p7.get("safety_coverage")
        job.score_maintenance_coverage = p7.get("maintenance_coverage")
        job.score_overall            = p7.get("overall")
        job.confidence_score         = float(p3.get("confidence_score", 0.75))

        job.report_concepts        = len(job.extracted_terminology or []) + len(job.extracted_abbreviations or [])
        job.report_systems         = len(job.extracted_systems or [])
        job.report_components      = len(job.extracted_components or [])
        job.report_procedures      = len(job.extracted_procedures or [])
        job.report_troubleshooting = len(p2.get("troubleshooting", []))
        job.report_new_info_count  = len(job.new_information or [])
        job.report_graph_nodes_added = len(job.graph_nodes or [])
        job.report_graph_edges_added = len(job.graph_edges or [])
        job.input_tokens  = in_tok
        job.output_tokens = out_tok
        job.model_used    = model
        job.rejection_reason = None
        job.status = "validating"
        log.info(
            "DATABASE_SAVE | retry_job_id=%s doc_id=%s filename=%s model=%s input_tokens=%d output_tokens=%d",
            job.id,
            job.doc_id,
            job.filename,
            model,
            in_tok,
            out_tok,
        )
        db.commit()

        # Auto-integrate
        try:
            job = approve_study_job(db, job, "auto")
            if job.report_graph_nodes_added == 0 and not (job.graph_nodes or []):
                job.status = "awaiting_approval"
            else:
                job.status = "integrated"
            db.commit()
            db.refresh(job)
            log.info("ANALYSIS_COMPLETED | retry_job_id=%s doc_id=%s filename=%s", job.id, job.doc_id, job.filename)
            log.info("Retry-integrated %s: %d nodes, %d edges", job.filename,
                     job.report_graph_nodes_added, job.report_graph_edges_added)
        except Exception as int_exc:
            log.error("Retry auto-integration failed for %s: %s", job_id, int_exc, exc_info=True)
            job.status = "awaiting_approval"
            job.rejection_reason = f"Database error: Auto-integration failed: {int_exc}"
            db.commit()

    except StudyAIError as exc:
        log.error("Retry pipeline failed for job %s at %s: %s", job_id, exc.stage, exc.message, exc_info=True)
        job = db.query(StudyJob).filter(StudyJob.id == job_id).first()
        if job:
            job.status = "failed"
            job.rejection_reason = f"{exc.stage}: {exc.message}"
            db.commit()
    except Exception as exc:
        log.error("Retry pipeline failed for job %s: %s", job_id, exc, exc_info=True)
        try:
            job = db.query(StudyJob).filter(StudyJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.rejection_reason = f"Unexpected error: {exc}"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()


@router.post("/study/jobs/process-pending")
def process_pending_jobs(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Auto-integrate all awaiting_approval jobs (owner trusted workflow).
    Also detects and marks any jobs that have been stuck in 'studying' for
    more than 5 minutes with no progress — these are orphaned asyncio tasks
    that were killed by a server restart and must be retried explicitly.
    """
    _require_admin(user)

    # ── Stale job detection ────────────────────────────────────────────────────
    # A job stuck in 'studying' for >5 min with updated_at == created_at means
    # the asyncio task was killed before it could start the GPT call.
    stale_cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
    stalled_jobs = (
        db.query(StudyJob)
        .filter(
            StudyJob.status == "studying",
            StudyJob.updated_at <= stale_cutoff,
        )
        .all()
    )
    stalled_count = 0
    for j in stalled_jobs:
        age_min = int((datetime.now(timezone.utc) - j.updated_at).total_seconds() // 60)
        j.status = "stalled"
        j.rejection_reason = (
            f"Job orphaned: no progress for {age_min} minutes (server likely restarted "
            f"while study pipeline was queued). Input tokens: {j.input_tokens}. "
            "Document text is available in rag_documents — safe to retry."
        )
        stalled_count += 1
        log.warning(
            "Stale study job detected: id=%s filename=%r — stuck for %d min, marking stalled",
            j.id, j.filename, age_min,
        )
    if stalled_count:
        db.commit()

    approved_by = user.get("name") or user.get("email") or user.get("id") or "auto"
    jobs = (
        db.query(StudyJob)
        .filter(StudyJob.status.in_(["awaiting_approval", "scored"]))
        .all()
    )
    total_nodes = 0
    processed_ids = []
    for job in jobs:
        try:
            job = approve_study_job(db, job, approved_by)
            job.status = "integrated"
            if job.sha256:
                from api.services.study_service import register_hash
                register_hash(db, job.sha256, job.doc_id, job.filename)
            db.commit()
            total_nodes += job.report_graph_nodes_added or 0
            processed_ids.append(job.id)
        except Exception as exc:
            log.warning("process-pending: skipping job %s — %s", job.id, exc)
    return {
        "ok": True,
        "processed_count": len(processed_ids),
        "graph_nodes_added": total_nodes,
        "stalled_detected": stalled_count,
    }


@router.post("/study/jobs/{job_id}/undo")
def undo_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Undo a single integrated learning import.
    Removes only the KnowledgeNodes/Edges materialised from this job.
    Preserves the original file and audit record.
    """
    _require_admin(user)
    job = db.query(StudyJob).filter(StudyJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Study job not found")
    if job.status not in ("integrated", "approved"):
        raise HTTPException(
            status_code=400,
            detail=f"Job status is '{job.status}' — only integrated jobs can be undone",
        )

    # Collect nodes that were created by this job
    nodes = db.query(KnowledgeNode).filter(KnowledgeNode.study_job_id == job_id).all()
    node_ids = [n.id for n in nodes]

    if node_ids:
        # Remove edges referencing these nodes first
        db.query(KnowledgeEdge).filter(
            or_(
                KnowledgeEdge.from_node_id.in_(node_ids),
                KnowledgeEdge.to_node_id.in_(node_ids),
            )
        ).delete(synchronize_session=False)
        # Remove the nodes
        db.query(KnowledgeNode).filter(KnowledgeNode.study_job_id == job_id).delete(
            synchronize_session=False
        )

    job.status = "undone"
    db.commit()

    log.info("Undo: removed %d nodes and their edges from job %s", len(node_ids), job_id)
    return {"ok": True, "nodes_removed": len(node_ids), "job_id": job_id}


@router.post("/study/jobs/{job_id}/retry")
async def retry_study_job(
    job_id: str,
    bg: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Re-run the full study pipeline for a single error/failed job using existing
    document text.  Does NOT re-upload the file.  WILL call OpenAI.
    """
    _require_admin(user)
    job = db.query(StudyJob).filter(StudyJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Study job not found")
    if job.status not in ("error", "failed", "stalled"):
        raise HTTPException(
            status_code=400,
            detail=f"Job status is '{job.status}' — only error/failed/stalled jobs can be retried",
        )
    rag_doc = db.query(RagDocument).filter(RagDocument.id == job.doc_id).first()
    if not rag_doc:
        raise HTTPException(
            status_code=422,
            detail="Source document text not found in database — please re-upload the file",
        )
    job.status = "studying"
    db.commit()
    bg.add_task(_run_retry_job, job_id, rag_doc.content)
    return {"ok": True, "job_id": job_id, "filename": job.filename,
            "message": "Analysis resumed from extracted text with automatic AI fallback"}


@router.post("/study/jobs/{job_id}/archive")
def archive_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Archive a learning source.
    Deactivates its knowledge nodes so they are excluded from future generation,
    without deleting the source file or the job record.
    """
    _require_admin(user)
    job = db.query(StudyJob).filter(StudyJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Study job not found")

    job.archived = True
    # Deactivate associated knowledge nodes
    db.query(KnowledgeNode).filter(KnowledgeNode.study_job_id == job_id).update(
        {"approved": False}, synchronize_session=False
    )
    db.commit()

    log.info("Archived study job %s — knowledge nodes deactivated", job_id)
    return {"ok": True, "archived": True, "job_id": job_id}


@router.post("/study/jobs/{job_id}/reject")
def reject_job(
    job_id: str,
    body: RejectBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Reject a study job — knowledge will NOT be added to the graph."""
    _require_admin(user)

    job = db.query(StudyJob).filter(StudyJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="Study job not found")

    job.status = "rejected"
    job.rejection_reason = body.reason or "Rejected by admin"
    db.commit()
    return {"ok": True, "status": "rejected"}


@router.post("/study/trigger/{doc_id}")
async def trigger_study(
    doc_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Manually (re-)trigger the study pipeline for an already-uploaded document."""
    _require_admin(user)

    doc = db.query(RagDocument).filter(RagDocument.id == doc_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")

    text = doc.content or ""
    if not text or text == "__processing__":
        raise HTTPException(status_code=400, detail="Document is still processing — try again later")

    # Check if already has a pending/studying job
    existing = (
        db.query(StudyJob)
        .filter(StudyJob.doc_id == doc_id, StudyJob.status.in_(["studying", "awaiting_approval", "validating", "approved", "integrated"]))
        .first()
    )
    if existing:
        return {"ok": False, "message": f"Document already has a study job in status '{existing.status}'", "job_id": existing.id}

    sha256 = compute_sha256(text.encode())
    asyncio.create_task(_study_bg(doc_id, doc.filename, text, sha256))
    return {"ok": True, "message": "Study pipeline started in background", "doc_id": doc_id}


class _TeachWebsiteBody(BaseModel):
    url: str = ""
    urls: list[str] = []              # for selected_urls mode
    knowledge_source: str = "entire_website"
    max_pages: int = 10
    max_depth: int = 3
    blocked_paths: Optional[list[str]] = None  # None → use crawler defaults
    file_types: list[str] = ["html", "pdf", "docx", "pptx", "xlsx", "markdown"]
    include_sitemap: bool = True
    min_relevance_score: float = 0.0


class _TeachProjectBody(BaseModel):
    project_id: str


@router.post("/learning/teach/website")
async def teach_from_website(
    body: _TeachWebsiteBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Crawl a website and feed its text into the AI study pipeline.

    Uses a full Chrome browser User-Agent + standard headers. Falls back to
    Playwright headless Chromium on 403 / anti-bot responses.  Reports the
    exact HTTP status, detected blocking mechanism, and whether browser
    rendering succeeded.
    """
    _require_admin(user)
    import uuid
    import hashlib
    from urllib.parse import urlparse
    from api.services.web_crawler import crawl as _crawl

    url = body.url.strip() if body.url else ""
    max_pages = max(1, min(body.max_pages, 50))   # raised cap: 50 pages

    # selected_urls mode passes an explicit list of URLs
    seed_urls = (
        [u.strip() for u in body.urls if u.strip()]
        if body.knowledge_source == "selected_urls"
        else None
    )
    if not url and not seed_urls:
        raise HTTPException(status_code=422, detail="Provide a URL or a list of URLs.")
    if seed_urls and not url:
        url = seed_urls[0]

    log.info(
        "Website crawl: source=%s url=%s max_pages=%d depth=%d",
        body.knowledge_source, url, max_pages, body.max_depth,
    )

    # ── Run crawler ────────────────────────────────────────────────────────────
    try:
        report = await _crawl(
            url,
            max_pages=max_pages,
            max_depth=max(1, min(body.max_depth, 5)),
            blocked_paths=body.blocked_paths,       # None = use crawler defaults
            knowledge_source=body.knowledge_source,
            include_sitemap=body.include_sitemap,
            min_relevance_score=max(0.0, min(1.0, body.min_relevance_score)),
            seed_urls=seed_urls,
        )
    except Exception as exc:
        log.error("Crawler raised unexpected error for %s: %s", url, exc, exc_info=True)
        raise HTTPException(status_code=422, detail=f"Crawler error: {exc}")

    # ── Build per-page diagnostic payload for the frontend ────────────────────
    page_diagnostics = []
    for pr in report.page_results:
        page_diagnostics.append({
            "url": pr.url,
            "http_status": pr.http_status,
            "http_reason": pr.http_reason,
            "accessible": pr.accessible,
            "blocking_mechanism": pr.blocking_mechanism,
            "browser_rendering_attempted": pr.browser_rendering_attempted,
            "browser_rendering_succeeded": pr.browser_rendering_succeeded,
            "text_length": len(pr.text),
            "technical_relevance": pr.technical_relevance,
            "depth": pr.depth,
            "error": pr.error,
        })

    # ── Fail if no content retrieved at all ───────────────────────────────────
    if report.pages_indexed == 0 or len(report.combined_text) < 100:
        # Build a helpful error message from the seed page result
        seed_result = report.page_results[0] if report.page_results else None
        if seed_result:
            status_str = f"HTTP {seed_result.http_status} {seed_result.http_reason}" if seed_result.http_status else "Connection failed"
            block_str = f" — {seed_result.blocking_mechanism} protection detected" if seed_result.blocking_mechanism else ""
            br_str = ""
            if seed_result.browser_rendering_attempted:
                br_str = (
                    " Browser rendering was attempted but could not bypass the restriction."
                    if not seed_result.browser_rendering_succeeded
                    else " Browser rendering succeeded but content was still inaccessible."
                )
            elif seed_result.blocking_mechanism in ("cloudflare", "captcha") and not report.playwright_available:
                br_str = " Headless browser (Playwright) is installed but Chromium could not be launched in this environment."
            detail = (
                f"{status_str}{block_str}.{br_str} "
                f"0 of {report.pages_attempted} page(s) were publicly accessible."
            )
        else:
            detail = "Could not retrieve any content from that URL."

        raise HTTPException(status_code=422, detail=detail)

    # ── Store and kick off study pipeline ─────────────────────────────────────
    text = report.combined_text
    doc_id = str(uuid.uuid4())
    sha = hashlib.sha256(text.encode()).hexdigest()
    domain = urlparse(url).netloc.replace("www.", "")
    filename = f"{domain}_webcrawl.txt"

    doc = RagDocument(
        id=doc_id,
        filename=filename,
        content=text,
        document_type="web_crawl",
        status="ready",
    )
    try:
        doc.content_hash = sha  # type: ignore[attr-defined]
    except Exception:
        pass
    db.add(doc)
    db.commit()

    asyncio.create_task(_study_bg(doc_id, filename, text, sha))

    log.info(
        "Website crawl complete: domain=%s pages_indexed=%d/%d text_len=%d playwright=%s",
        domain, report.pages_indexed, report.pages_attempted, len(text), report.playwright_available,
    )

    source_label = body.knowledge_source.replace("_", " ").title()
    return {
        "ok": True,
        "doc_id": doc_id,
        "filename": filename,
        "knowledge_source": body.knowledge_source,
        "text_length": len(text),
        "pages_indexed": report.pages_indexed,
        "pages_attempted": report.pages_attempted,
        "robots_txt_honored": report.robots_txt_honored,
        "playwright_available": report.playwright_available,
        "sitemap_urls_found": report.sitemap_urls_found,
        "avg_technical_relevance": report.avg_technical_relevance,
        "page_diagnostics": page_diagnostics,
        "message": (
            f"Crawled {report.pages_indexed} of {report.pages_attempted} page(s) "
            f"({source_label}) — AI is studying the content"
        ),
    }


@router.post("/learning/teach/pptx")
async def teach_from_pptx(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Dedicated endpoint: extract a LayoutStyle profile from a .pptx file.

    Runs synchronously (no API cost — pure python-pptx analysis) and returns
    the extracted style profile immediately, without creating a StudyJob.
    This is separate from the generic document-upload pipeline so the UI can
    show PPTX-specific stages and immediately display the result card.
    """
    _require_admin(user)
    import io

    from api.security.uploads import validate_upload
    from api.security.sanitize import sanitize_filename

    data = await file.read()
    # Enforce extension + declared MIME + magic bytes (rejects a renamed
    # non-PPTX) and a 100 MB ceiling.
    validate_upload(
        file.filename,
        data,
        declared_content_type=file.content_type,
        allowed_extensions={".pptx"},
        max_size=100 * 1024 * 1024,
    )
    filename = sanitize_filename(file.filename or "upload.pptx", default="upload.pptx")

    # ── Extract layout style (no API cost) ───────────────────────────────────
    from api.services.layout_learner import extract_layout
    from api.db.models import LayoutStyle

    loop = asyncio.get_event_loop()
    props = await loop.run_in_executor(None, extract_layout, filename, data)
    if not props:
        raise HTTPException(
            status_code=422,
            detail="Could not extract style from this file. Ensure it is a valid .pptx presentation."
        )

    # ── Persist LayoutStyle (idempotent: update if same filename already exists) ─
    style_name = filename.replace(".pptx", "").replace("_", " ").replace("-", " ")[:80].strip()

    existing = (
        db.query(LayoutStyle)
        .filter(LayoutStyle.source_filename == filename)
        .order_by(LayoutStyle.created_at.desc())
        .first()
    )
    if existing:
        existing.properties = props
        existing.name = style_name
        db.commit()
        style_id = existing.id
        log.info("Updated layout style '%s' from %s", style_name, filename)
    else:
        from api.db.crud import create_rag_document
        # Create a lightweight stub document so LayoutStyle.source_doc_id has a valid FK
        doc = create_rag_document(
            db,
            user_id=user["id"],
            filename=filename,
            document_type="pptx_style",
            content=f"[PPTX style reference — {props.get('slide_count', 0)} slides]",
            status="ready",
        )
        style = LayoutStyle(
            name=style_name,
            source_filename=filename,
            source_doc_id=doc.id,
            properties=props,
            is_default=False,
        )
        db.add(style)
        try:
            db.commit()
            style_id = style.id
            log.info("Saved layout style '%s' from %s", style_name, filename)
        except Exception as exc:
            db.rollback()
            log.error("Layout style save failed for %s: %s", filename, exc)
            raise HTTPException(status_code=500, detail=f"Failed to save style profile: {exc}")

    # ── Count detected features for the result card ─────────────────────────
    fonts_detected = len({f for f in [props.get("title_font_name"), props.get("body_font_name")] if f})
    colors_detected = len(props.get("theme_colors") or [])
    layouts_detected = len(props.get("placeholder_positions") or [])

    return {
        "ok": True,
        "style_id": style_id,
        "style_name": style_name,
        "filename": filename,
        "slides_analyzed": props.get("slide_count", 0),
        "layouts_detected": layouts_detected,
        "fonts_detected": fonts_detected,
        "colors_detected": colors_detected,
        "properties": props,
        "message": (
            f"Style profile '{style_name}' extracted — "
            f"{props.get('slide_count', 0)} slides, "
            f"{fonts_detected} font(s), "
            f"{colors_detected} color(s)"
        ),
    }


@router.post("/learning/teach/project")
async def teach_from_project(
    body: _TeachProjectBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Extract knowledge from a translation project's bilingual segment content."""
    _require_admin(user)  # owner-only learning route
    import uuid
    import hashlib
    from api.db.models import TranslationProject

    proj = db.query(TranslationProject).filter(TranslationProject.id == body.project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    segments = proj.segments or []
    lines: list[str] = []
    for seg in segments:
        src = (seg.get("source") or "").strip()
        tgt = (seg.get("target") or "").strip()
        if src:
            lines.append(src)
        if tgt and tgt != src:
            lines.append(tgt)

    if not lines:
        raise HTTPException(status_code=422, detail="Project has no content to learn from")

    text = "\n".join(lines)
    if len(text) < 50:
        raise HTTPException(status_code=422, detail="Project content is too short to study")

    doc_id = str(uuid.uuid4())
    sha = hashlib.sha256(text.encode()).hexdigest()
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in proj.name[:40])
    filename = f"project_{safe_name}.txt"

    doc = RagDocument(
        id=doc_id,
        filename=filename,
        content=text,
        document_type="project_extract",
        status="ready",
    )
    try:
        doc.content_hash = sha  # type: ignore[attr-defined]
    except Exception:
        pass
    db.add(doc)
    db.commit()

    asyncio.create_task(_study_bg(doc_id, filename, text, sha))

    return {
        "ok": True,
        "doc_id": doc_id,
        "segment_count": len(segments),
        "message": f"Extracted {len(lines)} text segments — study pipeline started",
    }


async def _study_bg(doc_id: str, filename: str, text: str, sha256: str) -> None:
    from api.db.base import SessionLocal
    bg_db = SessionLocal()
    try:
        await run_study_pipeline(bg_db, doc_id, filename, text, sha256=sha256)
    finally:
        bg_db.close()


# ── Knowledge summary ──────────────────────────────────────────────────────────

@router.get("/study/knowledge")
def get_knowledge_summary(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Return approved knowledge context — used by generation routes."""
    ctx = get_knowledge_context(db)
    return ctx


# ── Persistent knowledge graph ─────────────────────────────────────────────────

@router.get("/study/graph")
def get_knowledge_graph(
    approved_only: bool = True,
    limit: int = 500,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Return the persistent knowledge graph (nodes + edges) for visualisation."""
    node_q = db.query(KnowledgeNode).order_by(KnowledgeNode.weight.desc())
    if approved_only:
        node_q = node_q.filter(KnowledgeNode.approved == True)
    nodes = node_q.limit(limit).all()
    node_ids = {n.id for n in nodes}

    edge_q = db.query(KnowledgeEdge)
    if approved_only:
        edge_q = edge_q.filter(KnowledgeEdge.approved == True)
    edges = edge_q.filter(
        KnowledgeEdge.from_node_id.in_(node_ids),
        KnowledgeEdge.to_node_id.in_(node_ids),
    ).all()

    return {
        "nodes": [
            {
                "id": n.id,
                "label": n.label,
                "type": n.node_type,
                "description": n.description,
                "weight": n.weight,
                "source_doc_id": n.source_doc_id,
                "approved": n.approved,
            }
            for n in nodes
        ],
        "edges": [
            {
                "id": e.id,
                "from": e.from_node_id,
                "to": e.to_node_id,
                "relationship": e.relationship,
                "weight": e.weight,
            }
            for e in edges
        ],
    }


# ── Platform-wide learning report ──────────────────────────────────────────────

@router.get("/study/report")
def get_learning_report(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Aggregate learning report across all study jobs."""
    _require_admin(user)

    all_jobs = db.query(StudyJob).all()
    approved = [j for j in all_jobs if j.status == "approved"]
    pending  = [j for j in all_jobs if j.status == "awaiting_approval"]
    rejected = [j for j in all_jobs if j.status == "rejected"]

    total_concepts = sum(j.report_concepts for j in approved)
    total_systems = sum(j.report_systems for j in approved)
    total_components = sum(j.report_components for j in approved)
    total_procedures = sum(j.report_procedures for j in approved)
    total_troubleshooting = sum(j.report_troubleshooting for j in approved)

    # Unique terminology across all approved jobs
    all_terms: set[str] = set()
    all_abbrevs: set[str] = set()
    all_warnings: list[str] = []
    all_objectives: list[str] = []
    for j in approved:
        for t in (j.extracted_terminology or []):
            term = t.get("term", "") if isinstance(t, dict) else str(t)
            all_terms.add(term)
        for a in (j.extracted_abbreviations or []):
            abbr = a.get("abbr", "") if isinstance(a, dict) else str(a)
            all_abbrevs.add(abbr)
        all_warnings.extend(j.extracted_warnings or [])
        all_objectives.extend(j.learning_objectives or [])

    graph_nodes = db.query(_f.count(KnowledgeNode.id)).filter(KnowledgeNode.approved == True).scalar() or 0
    graph_edges = db.query(_f.count(KnowledgeEdge.id)).filter(KnowledgeEdge.approved == True).scalar() or 0

    avg_confidence = (
        round(sum(j.confidence_score or 0 for j in approved) / len(approved), 3)
        if approved else 0
    )
    avg_score = (
        round(sum(j.score_overall or 0 for j in approved) / len(approved), 1)
        if approved else 0
    )

    total_input_tokens = sum(j.input_tokens for j in all_jobs)
    total_output_tokens = sum(j.output_tokens for j in all_jobs)

    return {
        "summary": {
            "total_documents_studied": len(all_jobs),
            "approved": len(approved),
            "awaiting_approval": len(pending),
            "rejected": len(rejected),
        },
        "knowledge_bank": {
            "unique_terms": len(all_terms),
            "unique_abbreviations": len(all_abbrevs),
            "total_concepts": total_concepts,
            "total_systems": total_systems,
            "total_components": total_components,
            "total_procedures": total_procedures,
            "total_troubleshooting_cases": total_troubleshooting,
            "safety_warnings": len(all_warnings),
            "learning_objectives": len(all_objectives),
        },
        "knowledge_graph": {
            "nodes": graph_nodes,
            "edges": graph_edges,
        },
        "quality": {
            "avg_confidence_score": avg_confidence,
            "avg_overall_score": avg_score,
        },
        "api_usage": {
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "estimated_cost_usd": round(
                total_input_tokens * 0.0000025 + total_output_tokens * 0.00001, 4
            ),
        },
        "recent_approved": [
            {
                "filename": j.filename,
                "approved_at": j.approved_at.isoformat() if j.approved_at else None,
                "score_overall": j.score_overall,
                "confidence": j.confidence_score,
                "nodes_added": j.report_graph_nodes_added,
            }
            for j in sorted(approved, key=lambda x: x.approved_at or x.created_at, reverse=True)[:10]
        ],
    }


# ── Terminology bank ───────────────────────────────────────────────────────────

@router.get("/learning/terminology")
def get_terminology(
    query: str = "",
    category: str = "",
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Browse the platform's extracted terminology bank."""
    return search_terminology(db, query=query, category=category, limit=limit, offset=offset)


# ── Layout styles ──────────────────────────────────────────────────────────────

@router.get("/learning/styles")
def get_layout_styles(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """List all learned PPTX layout styles."""
    return {"styles": list_styles(db)}


class SetDefaultBody(BaseModel):
    style_id: str


@router.post("/learning/styles/default")
def set_default_layout(
    body: SetDefaultBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Set a layout style as the platform default for course generation."""
    _require_admin(user)
    ok = set_default_style(db, body.style_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Style not found")
    return {"ok": True}


# ── Style management endpoints ────────────────────────────────────────────────

@router.get("/learning/styles/{style_id}")
def get_layout_style(
    style_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Return a single LayoutStyle by ID."""
    style = get_style(db, style_id)
    if style is None:
        raise HTTPException(status_code=404, detail="Style not found")
    return style


class UpdateStyleBody(BaseModel):
    name: Optional[str] = None
    organisation: Optional[str] = None
    department: Optional[str] = None
    language: Optional[str] = None


@router.patch("/learning/styles/{style_id}")
def update_layout_style(
    style_id: str,
    body: UpdateStyleBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Update name and/or org/dept/lang metadata on a LayoutStyle."""
    from api.db.models import LayoutStyle as _LayoutStyle
    from sqlalchemy.orm.attributes import flag_modified as _fm

    style = db.query(_LayoutStyle).filter(_LayoutStyle.id == style_id).first()
    if style is None:
        raise HTTPException(status_code=404, detail="Style not found")

    if body.name is not None:
        style.name = body.name.strip()[:256]

    # Store org/dept/lang inside the properties JSON so no schema migration is needed
    props = dict(style.properties or {})
    if body.organisation is not None:
        props["organisation"] = body.organisation.strip()[:128]
    if body.department is not None:
        props["department"] = body.department.strip()[:128]
    if body.language is not None:
        props["language"] = body.language.strip()[:32]

    style.properties = props
    _fm(style, "properties")
    db.commit()

    from api.services.layout_learner import _style_to_dict
    return _style_to_dict(style)


@router.delete("/learning/styles/{style_id}", status_code=204)
def delete_layout_style(
    style_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Delete a LayoutStyle record."""
    _require_admin(user)
    from api.db.models import LayoutStyle as _LayoutStyle

    style = db.query(_LayoutStyle).filter(_LayoutStyle.id == style_id).first()
    if style is None:
        raise HTTPException(status_code=404, detail="Style not found")
    db.delete(style)
    db.commit()
    return None


# ── Exam patterns ──────────────────────────────────────────────────────────────

@router.get("/learning/exam-patterns")
def get_exam_patterns(
    topic: str = "",
    bloom: str = "",
    difficulty: str = "",
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Browse extracted exam question patterns."""
    return list_exam_patterns(db, topic=topic, bloom=bloom, difficulty=difficulty,
                               limit=limit, offset=offset)


# ── Learning report ────────────────────────────────────────────────────────────

@router.get("/learning/report")
def get_platform_learning_report(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Return the most recent learning report, or generate one on demand."""
    _require_admin(user)
    report = get_latest_report(db)
    if not report:
        report = generate_and_store(db)
    return report


@router.post("/learning/report/generate")
def force_generate_report(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Force-generate a new learning report for the last 7 days."""
    _require_admin(user)
    report = generate_and_store(db)
    return report


# ── Image classifications ──────────────────────────────────────────────────────

@router.get("/learning/image-classifications")
def get_image_classifications(
    category: str = "",
    limit: int = 100,
    offset: int = 0,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """List image classification results."""
    from api.db.models import ImageClassification, RagImage

    q = db.query(ImageClassification)
    if category:
        q = q.filter(ImageClassification.category == category)
    total = q.count()
    rows = q.order_by(ImageClassification.created_at.desc()).offset(offset).limit(limit).all()

    results = []
    for ic in rows:
        img = db.query(RagImage).filter(RagImage.id == ic.image_id).first()
        results.append({
            "id": ic.id,
            "image_id": ic.image_id,
            "category": ic.category,
            "confidence": ic.confidence,
            "model": ic.model,
            "doc_filename": img.doc_filename if img else None,
            "page_num": img.page_num if img else None,
            "caption": img.caption if img else None,
            "created_at": ic.created_at.isoformat() if ic.created_at else None,
        })

    return {"total": total, "classifications": results}


# ── Platform dashboard stats ───────────────────────────────────────────────────

@router.get("/learning/stats")
def get_learning_stats(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Dashboard stat cards for the Learning Hub overview page."""
    from api.db.models import (
        TerminologyEntry, ImageClassification, LayoutStyle, ExamPattern,
        SlideCorrection, KnowledgeNode, KnowledgeEdge, StudyJob, RagDocument,
    )
    from sqlalchemy import func

    def cnt(model):
        return db.query(func.count(model.id)).scalar() or 0

    total_jobs = cnt(StudyJob)
    approved_jobs = db.query(StudyJob).filter(StudyJob.status == "approved").count()
    pending_jobs = db.query(StudyJob).filter(StudyJob.status == "awaiting_approval").count()

    return {
        "documents_studied": total_jobs,
        "awaiting_approval": pending_jobs,
        "approved_knowledge_items": approved_jobs,
        "terminology_entries": cnt(TerminologyEntry),
        "layout_styles": cnt(LayoutStyle),
        "exam_patterns": cnt(ExamPattern),
        "slide_corrections": cnt(SlideCorrection),
        "image_classifications": cnt(ImageClassification),
        "knowledge_nodes": db.query(
            func.count(KnowledgeNode.id)
        ).filter(KnowledgeNode.approved == True).scalar() or 0,
        "knowledge_edges": db.query(
            func.count(KnowledgeEdge.id)
        ).filter(KnowledgeEdge.approved == True).scalar() or 0,
    }
