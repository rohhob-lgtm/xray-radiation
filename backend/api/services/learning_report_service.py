"""
Learning report service — generates periodic platform intelligence summaries.

Reports include:
  - New terminology entries added in the period
  - New images classified
  - New layout styles learned
  - Instructor corrections recorded
  - Knowledge graph growth (node/edge delta)
  - Slide approvals
  - Confidence score trend (approvals vs corrections)
  - OpenAI call delta vs prior period
"""
from __future__ import annotations
import logging
from datetime import datetime, timezone, timedelta
from typing import Optional

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def generate_report(
    db: Session,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
) -> dict:
    """
    Generate a learning report for the given period (defaults to last 7 days).
    Returns the report dict — caller is responsible for persisting if desired.
    """
    from api.db.models import (
        TerminologyEntry, ImageClassification, LayoutStyle, ExamPattern,
        SlideCorrection, KnowledgeNode, KnowledgeEdge, StudyJob,
        LearningReport,
    )

    now = _now()
    if period_end is None:
        period_end = now
    if period_start is None:
        period_start = period_end - timedelta(days=7)

    def _count_in_period(model, date_col="created_at") -> int:
        col = getattr(model, date_col, None)
        if col is None:
            return 0
        return db.query(model).filter(
            col >= period_start, col <= period_end
        ).count()

    def _count_all(model) -> int:
        return db.query(model).count()

    # ── Period counts ──────────────────────────────────────────────────────
    new_terms = _count_in_period(TerminologyEntry)
    new_images_classified = _count_in_period(ImageClassification)
    new_layout_styles = _count_in_period(LayoutStyle)
    new_exam_patterns = _count_in_period(ExamPattern)
    new_corrections = _count_in_period(SlideCorrection)
    new_nodes = _count_in_period(KnowledgeNode)
    new_edges = _count_in_period(KnowledgeEdge)

    study_jobs_period = db.query(StudyJob).filter(
        StudyJob.created_at >= period_start,
        StudyJob.created_at <= period_end,
    ).all()

    approved_jobs = [j for j in study_jobs_period if j.status == "approved"]
    rejected_jobs = [j for j in study_jobs_period if j.status == "rejected"]
    pending_jobs  = [j for j in study_jobs_period if j.status == "awaiting_approval"]

    # ── Slide approvals (education_outputs.approved) ───────────────────────
    try:
        from api.db.models import EducationOutput
        approved_outputs = db.query(EducationOutput).filter(
            EducationOutput.approved == True,
        ).count()
    except Exception:
        approved_outputs = 0

    try:
        from api.db.models import TrainingSlide
        approved_slides = db.query(TrainingSlide).filter(
            TrainingSlide.approval_status == "approved"  # type: ignore[attr-defined]
        ).count()
    except Exception:
        approved_slides = 0

    # ── Confidence score ───────────────────────────────────────────────────
    total_reviews = len(approved_jobs) + len(rejected_jobs)
    confidence_score = (
        round(len(approved_jobs) / total_reviews * 100)
        if total_reviews > 0 else 0
    )

    # ── API cost for this period ───────────────────────────────────────────
    period_tokens_in  = sum(j.input_tokens  or 0 for j in study_jobs_period)
    period_tokens_out = sum(j.output_tokens or 0 for j in study_jobs_period)
    period_cost_usd   = (period_tokens_in * 2.5 + period_tokens_out * 10) / 1_000_000

    # Prior period for comparison
    prior_start = period_start - (period_end - period_start)
    prior_jobs = db.query(StudyJob).filter(
        StudyJob.created_at >= prior_start,
        StudyJob.created_at < period_start,
    ).all()
    prior_tokens_in  = sum(j.input_tokens  or 0 for j in prior_jobs)
    prior_tokens_out = sum(j.output_tokens or 0 for j in prior_jobs)
    prior_cost_usd   = (prior_tokens_in * 2.5 + prior_tokens_out * 10) / 1_000_000

    cost_delta_pct = (
        round((period_cost_usd - prior_cost_usd) / max(prior_cost_usd, 0.001) * 100, 1)
        if prior_cost_usd > 0 else 0
    )

    # ── Cumulative platform totals ─────────────────────────────────────────
    total_terms      = _count_all(TerminologyEntry)
    total_classified = _count_all(ImageClassification)
    total_styles     = _count_all(LayoutStyle)
    total_patterns   = _count_all(ExamPattern)
    total_nodes      = _count_all(KnowledgeNode)
    total_edges      = _count_all(KnowledgeEdge)
    total_jobs       = _count_all(StudyJob)

    all_study_jobs = db.query(StudyJob).all()
    all_approved   = [j for j in all_study_jobs if j.status == "approved"]
    all_corrections = _count_all(SlideCorrection)

    return {
        "period_start": period_start.isoformat(),
        "period_end":   period_end.isoformat(),
        "period_label": _period_label(period_start, period_end),

        # This period
        "period": {
            "new_terminology":    new_terms,
            "new_images_classified": new_images_classified,
            "new_layout_styles":  new_layout_styles,
            "new_exam_patterns":  new_exam_patterns,
            "new_corrections":    new_corrections,
            "new_graph_nodes":    new_nodes,
            "new_graph_edges":    new_edges,
            "study_jobs_total":   len(study_jobs_period),
            "approved":           len(approved_jobs),
            "rejected":           len(rejected_jobs),
            "pending":            len(pending_jobs),
            "confidence_score":   confidence_score,
            "api_cost_usd":       round(period_cost_usd, 4),
            "api_tokens_in":      period_tokens_in,
            "api_tokens_out":     period_tokens_out,
            "cost_delta_pct":     cost_delta_pct,
        },

        # Platform totals
        "totals": {
            "terminology_entries": total_terms,
            "images_classified":   total_classified,
            "layout_styles":       total_styles,
            "exam_patterns":       total_patterns,
            "knowledge_nodes":     total_nodes,
            "knowledge_edges":     total_edges,
            "study_jobs":          total_jobs,
            "approved_jobs":       len(all_approved),
            "slide_corrections":   all_corrections,
            "approved_outputs":    approved_outputs,
            "approved_slides":     approved_slides,
        },
    }


def _period_label(start: datetime, end: datetime) -> str:
    diff = end - start
    if diff.days <= 1:
        return "Last 24 hours"
    if diff.days <= 7:
        return f"Last {diff.days} days"
    if diff.days <= 31:
        return f"Last {diff.days // 7} weeks"
    return f"Last {diff.days // 30} months"


def generate_and_store(
    db: Session,
    period_start: Optional[datetime] = None,
    period_end: Optional[datetime] = None,
) -> dict:
    """Generate a report and persist it to LearningReport table."""
    from api.db.models import LearningReport

    now = _now()
    if period_end is None:
        period_end = now
    if period_start is None:
        period_start = period_end - timedelta(days=7)

    report_data = generate_report(db, period_start, period_end)

    record = LearningReport(
        period_start=period_start,
        period_end=period_end,
        report_json=report_data,
    )
    db.add(record)
    try:
        db.commit()
        report_data["id"] = record.id
    except Exception as exc:
        db.rollback()
        log.warning("LearningReport persist failed: %s", exc)

    return report_data


def get_latest(db: Session) -> Optional[dict]:
    """Return the most recently generated report, or None."""
    from api.db.models import LearningReport
    row = db.query(LearningReport).order_by(LearningReport.created_at.desc()).first()
    if not row:
        return None
    d = row.report_json or {}
    d["id"] = row.id
    return d
