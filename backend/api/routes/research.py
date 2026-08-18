"""
Research generation routes — streaming AI-powered academic content generation.
Supports: IEEE papers, Elsevier papers, literature reviews, research ideas,
          research gaps, experiment plans, patent analysis, technical reports,
          security algorithm design.
"""
from __future__ import annotations
import json
import logging
import uuid
from typing import Optional, List, AsyncGenerator

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.db.crud import (
    create_research_output,
    list_research_outputs,
    delete_research_output, research_output_to_dict,
    list_research_pipeline_runs,
    get_research_pipeline_run,
)
from api.middleware.auth import optional_auth
from api.services.research_service import RESEARCH_MODE_LABELS
from api.services.research_pipeline import (
    build_phase2_research_document,
    run_phase1_research_pipeline,
    research_pipeline_run_to_dict,
)
from api.services.ai_providers.registry import provider_registry

log = logging.getLogger(__name__)

router = APIRouter(tags=["research"])

VALID_MODES = set(RESEARCH_MODE_LABELS.keys())


class ResearchInput(BaseModel):
    mode: str
    topic: str
    context: Optional[str] = None
    keywords: Optional[List[str]] = None
    depth: Optional[str] = None
    word_count: Optional[int] = None


class ResearchOutputResponse(BaseModel):
    id: str
    mode: str
    mode_label: str
    topic: str
    content: str
    word_count: int
    created_at: str


class ResearchExportRequest(BaseModel):
    lang: str = "en"
    layout: str = "sequential"


# ──────────────────────────────────────────────────────────
# Generate (streaming SSE)
# ──────────────────────────────────────────────────────────

@router.post("/research/generate")
async def generate_research(
    body: ResearchInput,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """Run Phase 1 of the research pipeline and stream structured artifacts."""
    if body.mode not in VALID_MODES:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid mode '{body.mode}'. Valid modes: {', '.join(sorted(VALID_MODES))}",
        )

    user_id = user["id"] if user else None
    run_id = str(uuid.uuid4())

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            yield f"data: {json.dumps({'type': 'start', 'run_id': run_id, 'phase': 'phase1', 'mode': body.mode, 'topic': body.topic})}\n\n"

            result = await run_phase1_research_pipeline(
                db,
                user_id=user_id,
                mode=body.mode,
                topic=body.topic,
                context=body.context,
                keywords=body.keywords,
                depth=body.depth,
                word_count=body.word_count,
            )
            artifacts = result["artifacts"]

            stage_order = [
                ("topic_normalization", "Topic normalization"),
                ("keyword_expansion", "Keyword expansion"),
                ("academic_search_planning", "Academic search planning"),
                ("external_evidence_retrieval", "External evidence retrieval"),
                ("official_standards_retrieval", "Official standards retrieval"),
                ("manufacturer_documentation_retrieval", "Manufacturer documentation retrieval"),
                ("duplicate_removal", "Duplicate removal"),
                ("evidence_ranking", "Evidence ranking"),
                ("literature_clustering", "Literature clustering"),
                ("scientific_synthesis", "Scientific synthesis"),
                ("gap_analysis", "Gap analysis"),
                ("methodology_generation", "Methodology generation"),
                ("mathematical_model", "Mathematical model"),
                ("figures_tables_planning", "Figures & tables planning"),
                ("section_by_section_writing", "Section-by-section writing"),
                ("citation_validation", "Citation validation"),
                ("scientific_integrity_validation", "Scientific integrity validation"),
                ("final_doc_assembly", "Final DOCX/PDF assembly"),
            ]

            for stage_key, stage_name in stage_order:
                stage_artifact = artifacts.get("stages", {}).get(stage_key, {})
                yield f"data: {json.dumps({'type': 'stage', 'stage': stage_key, 'name': stage_name, 'status': 'done', 'artifact': stage_artifact})}\n\n"

            phase2 = await build_phase2_research_document(
                artifacts=artifacts,
                mode=body.mode,
                topic=body.topic,
                context=body.context,
                keywords=body.keywords,
                depth=body.depth,
                word_count=body.word_count,
                # `request.app.state.llm_provider` was never set anywhere in the
                # app — this always evaluated to None, silently forcing every
                # paper through the deterministic template fallback. Use the
                # same active-provider lookup chat.py/translation.py already
                # rely on.
                provider=provider_registry.get_active(),
                run_id=run_id,
            )
            validation_artifact = phase2.get("scientific_integrity_validation", {
                "verified_reference_count": len(artifacts.get("unified_sources", artifacts.get("sources_accepted", []))),
                "rejected_reference_count": len(artifacts.get("sources_rejected", [])),
            })
            export_artifact = phase2.get("final_doc_assembly", {
                "paper_title": phase2["paper_title"],
                "docx_filename": f"{phase2['paper_title']}.docx",
                "pdf_filename": f"{phase2['paper_title']}.pdf",
                "filename_policy": "exact_title_only",
            })
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'scientific_writing', 'name': 'Scientific Writing', 'status': 'done', 'artifact': {'paper_title': phase2['paper_title'], 'document_type': phase2['document_type'], 'total_target_words': phase2['total_target_words']}})}\n\n"
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'citation_validation', 'name': 'Citation validation', 'status': 'done', 'artifact': phase2.get('citation_validation', {})})}\n\n"
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'scientific_integrity_validation', 'name': 'Scientific integrity validation', 'status': 'done', 'artifact': validation_artifact})}\n\n"
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'final_doc_assembly', 'name': 'Final DOCX/PDF assembly', 'status': 'done', 'artifact': export_artifact})}\n\n"

            # Final readiness check happens *before* saving — a draft with
            # critical defects (thin evidence, title/content mismatch, leaked
            # placeholders, etc.) is never persisted as a finished output.
            # The retrieval-retry loop in run_phase1_research_pipeline already
            # tried hard to avoid this; this is the last-resort safety net.
            # Scores/percentages are logged for engineers, never shown to the
            # user — they only ever see either a finished paper or one plain
            # explanation of why generation didn't succeed.
            from api.utils.research_quality import generate_publication_readiness_report
            readiness = generate_publication_readiness_report(
                phase2["content"],
                mode=body.mode,
                reference_meta=phase2.get("reference_meta", []),
                has_real_experiment=bool(phase2.get("has_real_results", False)),
            )
            log.info(
                "Research generation readiness: run_id=%s ready=%s refs=%d peer_reviewed_ratio=%.2f alignment=%.2f issues=%s",
                run_id, readiness.is_publication_ready, readiness.reference_count,
                readiness.peer_reviewed_ratio, readiness.title_content_alignment, readiness.critical_issues,
            )
            if not readiness.is_publication_ready:
                yield f"data: {json.dumps({'type': 'error', 'error': 'We could not find enough reliable, well-matched sources to produce a publication-ready paper for this topic. Try rephrasing it to be more specific about the X-ray application area (e.g. security screening, source/detector physics, explosives, or radiological threat detection).'})}\n\n"
                return

            saved_output = create_research_output(
                db,
                output_id=str(uuid.uuid4()),
                user_id=user_id,
                mode=body.mode,
                topic=phase2["paper_title"],
                content=phase2["content"],
                kb_chunks_used=len(artifacts.get("kb_chunks", [])),
                readiness_meta={
                    "reference_meta": phase2.get("reference_meta", []),
                    "has_real_experiment": bool(phase2.get("has_real_results", False)),
                },
            )
            yield f"data: {json.dumps({'type': 'done', 'run_id': result['run'].id, 'status': result['run'].status, 'current_stage': 'export', 'artifacts': {**artifacts, 'phase2': phase2, 'validation': validation_artifact, 'export': export_artifact}, 'paper_title': phase2['paper_title'], 'content': phase2['content'], 'output_id': saved_output.id, 'word_count': saved_output.word_count, 'kb_chunks': saved_output.kb_chunks_used})}\n\n"

        except Exception as exc:
            log.exception("Research generation failed: run_id=%s", run_id)
            yield f"data: {json.dumps({'type': 'error', 'error': 'Research generation did not complete. Please try again, or rephrase the topic if this keeps happening.'})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/research/pipeline/runs")
def list_pipeline_runs(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    user_id = user["id"] if user else None
    runs = list_research_pipeline_runs(db, user_id=user_id)
    return [research_pipeline_run_to_dict(run) for run in runs]


@router.get("/research/pipeline/runs/{run_id}")
def get_pipeline_run(
    run_id: str,
    db: Session = Depends(get_db),
):
    run = get_research_pipeline_run(db, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Research pipeline run not found")
    return research_pipeline_run_to_dict(run)


# ──────────────────────────────────────────────────────────
# CRUD — saved outputs
# ──────────────────────────────────────────────────────────

@router.get("/research/outputs")
def list_outputs(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    user_id = user["id"] if user else None
    outputs = list_research_outputs(db, user_id=user_id)
    return [research_output_to_dict(o) for o in outputs]


@router.delete("/research/outputs/{output_id}", status_code=204)
def delete_output(
    output_id: str,
    db: Session = Depends(get_db),
):
    if not delete_research_output(db, output_id):
        raise HTTPException(status_code=404, detail="Research output not found")


@router.get("/research/modes")
def list_modes():
    """Return available research generation modes with labels."""
    return [{"id": k, "label": v} for k, v in RESEARCH_MODE_LABELS.items()]


# ──────────────────────────────────────────────────────────
# Export — Word (.docx) and PDF
# ──────────────────────────────────────────────────────────

def _get_research_record(output_id: str, db: Session):
    """Fetch ResearchOutput and raise 404 if not found."""
    from api.db.models import ResearchOutput
    obj = db.query(ResearchOutput).filter(ResearchOutput.id == output_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Research output not found")
    return obj


class _ResearchAdapter:
    """Thin adapter so ResearchOutput works with build_docx / build_pdf."""
    def __init__(self, obj):
        self.id = obj.id
        self.topic = obj.topic
        self.mode = obj.mode
        self.domain_label = RESEARCH_MODE_LABELS.get(obj.mode, obj.mode.replace("_", " ").title())
        self.kb_chunks_used = getattr(obj, "kb_chunks_used", 0)
        self.word_count = obj.word_count


def _enforce_publication_readiness(obj, content: str) -> None:
    """Block DOCX/PDF export on named, specific manuscript defects.

    Unlike the old 0-100 aggregate quality score (deliberately kept
    non-blocking — an arbitrary bar is easy to fail for reasons that don't
    matter), this checks the acceptance-test list directly: reference count,
    peer-review ratio, title/content alignment, placeholder leakage, mermaid
    leakage, figure rendering, and unsupported claims.

    The full technical breakdown (scores, percentages, per-check reasons) is
    logged server-side only. The user only ever sees one plain sentence —
    this system should read like a research scientist declining to publish
    a draft, not a QA report.
    """
    from api.utils.research_quality import generate_publication_readiness_report

    readiness_meta = getattr(obj, "readiness_meta", None) or {}
    report = generate_publication_readiness_report(
        content,
        mode=obj.mode,
        reference_meta=readiness_meta.get("reference_meta"),
        has_real_experiment=bool(readiness_meta.get("has_real_experiment", False)),
    )
    if report.critical_issues:
        log.info(
            "Export blocked for research output %s: refs=%d peer_reviewed_ratio=%.2f alignment=%.2f issues=%s",
            getattr(obj, "id", "?"), report.reference_count, report.peer_reviewed_ratio,
            report.title_content_alignment, report.critical_issues,
        )
        raise HTTPException(
            status_code=422,
            detail={
                "error": "not_publication_ready",
                "message": "This draft isn't ready for export yet. Try regenerating the paper, or rephrase the topic to be more specific.",
            },
        )


@router.post("/research/outputs/{output_id}/export/docx")
def export_research_docx(
    output_id: str,
    body: ResearchExportRequest,
    db: Session = Depends(get_db),
):
    """Download a research output as a Word (.docx) document."""
    from api.utils.docgen import build_docx, extract_paper_title, sanitize_export_filename, _strip_offer_footer
    from api.utils.filename_helper import content_disposition
    obj = _get_research_record(output_id, db)
    content = _strip_offer_footer(obj.content or "")
    _enforce_publication_readiness(obj, content)
    paper_title = extract_paper_title(content, fallback=obj.topic)
    docx_bytes = build_docx(
        record=_ResearchAdapter(obj),
        content=content,
        lang=body.lang,
        layout=body.layout,
    )
    filename = sanitize_export_filename(paper_title, ".docx")
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": content_disposition(filename)},
    )


@router.post("/research/outputs/{output_id}/export/pdf")
def export_research_pdf(
    output_id: str,
    body: ResearchExportRequest,
    db: Session = Depends(get_db),
):
    """Download a research output as a PDF document."""
    from api.utils.docgen import build_pdf, extract_paper_title, sanitize_export_filename, _strip_offer_footer
    from api.utils.filename_helper import content_disposition
    obj = _get_research_record(output_id, db)
    content = _strip_offer_footer(obj.content or "")
    _enforce_publication_readiness(obj, content)
    paper_title = extract_paper_title(content, fallback=obj.topic)
    pdf_bytes = build_pdf(
        record=_ResearchAdapter(obj),
        content=content,
        lang=body.lang,
        layout=body.layout,
    )
    filename = sanitize_export_filename(paper_title, ".pdf")
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": content_disposition(filename)},
    )
