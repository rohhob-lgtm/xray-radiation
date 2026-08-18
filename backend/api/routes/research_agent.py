"""
Autonomous Radiation & X-Ray Research Agent — mission API.

Endpoints:
  POST /research-agent/missions               — create + start a mission
  POST /research-agent/missions/{id}/pause     — pause a running mission
  POST /research-agent/missions/{id}/resume    — resume a paused mission
  POST /research-agent/missions/{id}/stop      — stop a mission permanently
  GET  /research-agent/missions                — list missions
  GET  /research-agent/missions/{id}            — mission status (dashboard poll target)
  GET  /research-agent/missions/{id}/sources    — discovered sources, ranked by quality
  GET  /research-agent/missions/{id}/files      — ingested/rejected files
  GET  /research-agent/missions/{id}/activity   — activity log / errors

This is one more Learning Hub feature, not a separate research system — it
reuses the same shared knowledge base (RagDocument / retrieve_chunks) that
chat and every other platform section already query. The existing
`POST /learning/teach/website` single-URL flow (api/routes/study.py) is
untouched.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.db import crud
from api.middleware.auth import require_auth
from api.routes.study import _require_admin
from api.services.research_agent.job_runner import (
    start_mission, pause_mission, resume_mission, stop_mission, mission_scheduler,
)
from api.services.research_agent.mission_queue import classify_resumability
from api.services.research_agent.provider_throttle import get_provider_status
from api.services.research_agent.startup import readiness, db_pool_metrics
from api.services.source_trust import jobs as trust_jobs
from api.services.source_trust.source_trust_service import CURRENT_TRUST_ALGORITHM_VERSION, submit_user_review, reset_user_review

log = logging.getLogger(__name__)
router = APIRouter(tags=["research-agent"])

VALID_MODES = {"quick_scan", "deep_research", "continuous_learning"}
VALID_FREQUENCIES = {"manual", "6h", "daily", "weekly"}


class MissionCreateRequest(BaseModel):
    mission_text: str
    mode: str = "quick_scan"
    languages: list[str] = ["en"]
    content_types: list[str] = ["web_pages"]
    free_mode: bool = True
    max_pages: int = 30
    max_files: int = 30
    max_storage_mb: int = 200
    max_depth: int = 1
    min_relevance_score: float = 0.15
    min_quality_score: float = 45.0
    schedule_frequency: str = "manual"
    # Phase 2B.5 — mission-level coverage-target auto-continue loop.
    coverage_target: float = 70.0
    max_coverage_rounds: int = 3


@router.post("/research-agent/missions")
async def create_mission(
    body: MissionCreateRequest,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    _require_admin(user)

    mission_text = (body.mission_text or "").strip()
    if not mission_text:
        raise HTTPException(status_code=422, detail="mission_text is required")
    if body.mode not in VALID_MODES:
        raise HTTPException(status_code=422, detail=f"mode must be one of {sorted(VALID_MODES)}")
    if body.schedule_frequency not in VALID_FREQUENCIES:
        raise HTTPException(status_code=422, detail=f"schedule_frequency must be one of {sorted(VALID_FREQUENCIES)}")

    limits = {
        "max_pages": max(1, min(body.max_pages, 500)),
        "max_files": max(1, min(body.max_files, 500)),
        "max_storage_mb": max(1, min(body.max_storage_mb, 5000)),
        "max_depth": max(0, min(body.max_depth, 5)),
        "min_relevance_score": max(0.0, min(1.0, body.min_relevance_score)),
        "min_quality_score": max(0.0, min(100.0, body.min_quality_score)),
    }
    schedule = {"frequency": body.schedule_frequency, "next_run_at": None} if body.mode == "continuous_learning" else None

    mission = crud.create_research_mission(
        db,
        user_id=user["id"],
        mission_text=mission_text,
        mode=body.mode,
        languages=body.languages or ["en"],
        content_types=body.content_types or ["web_pages"],
        free_mode=body.free_mode,
        limits=limits,
        schedule=schedule,
        coverage_target=max(0.0, min(100.0, body.coverage_target)),
        max_coverage_rounds=max(1, min(10, body.max_coverage_rounds)),
    )
    start_mission(mission.id)

    log.info("Research mission created: id=%s mode=%s free_mode=%s", mission.id, mission.mode, mission.free_mode)
    return {
        "ok": True,
        "mission": crud.research_mission_to_dict(mission),
        "message": (
            f"Mission started — {'Free Mode ON (Estimated Cost = $0.00)' if body.free_mode else 'Free Mode OFF'}, "
            f"max {limits['max_pages']} pages / {limits['max_files']} files / {limits['max_storage_mb']} MB."
        ),
    }


@router.get("/research-agent/missions")
def list_missions(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    missions = crud.list_research_missions(db, user_id=user["id"])
    return {"missions": [crud.research_mission_to_dict(m) for m in missions]}


def _get_mission_or_404(db: Session, mission_id: str):
    mission = crud.get_research_mission(db, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.get("/research-agent/missions/{mission_id}")
def get_mission(mission_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    mission = _get_mission_or_404(db, mission_id)
    return {"mission": crud.research_mission_to_dict(mission)}


@router.post("/research-agent/missions/{mission_id}/pause")
async def pause(mission_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _require_admin(user)
    _get_mission_or_404(db, mission_id)
    mission = await pause_mission(mission_id)
    return {"ok": True, "mission": crud.research_mission_to_dict(mission)}


@router.post("/research-agent/missions/{mission_id}/resume")
async def resume(mission_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _require_admin(user)
    _get_mission_or_404(db, mission_id)
    mission = await resume_mission(mission_id)
    return {"ok": True, "mission": crud.research_mission_to_dict(mission)}


@router.post("/research-agent/missions/{mission_id}/stop")
async def stop(mission_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _require_admin(user)
    _get_mission_or_404(db, mission_id)
    mission = await stop_mission(mission_id)
    return {"ok": True, "mission": crud.research_mission_to_dict(mission)}


@router.get("/research-agent/missions/{mission_id}/queue")
def list_queue(
    mission_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    _get_mission_or_404(db, mission_id)
    items = crud.list_research_queue_items(db, mission_id, status=status)
    return {
        "queue": [
            {
                "id": item.id,
                "url": item.url,
                "source_domain": item.source_domain,
                "discovered_via": item.discovered_via,
                "depth": item.depth,
                "status": item.status,
                "attempts": item.attempts,
                "last_error": item.last_error,
                "created_at": item.created_at.isoformat(),
                "updated_at": item.updated_at.isoformat(),
            }
            for item in items
        ]
    }


@router.get("/research-agent/missions/{mission_id}/sources")
def list_sources(
    mission_id: str,
    quality_label: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    _get_mission_or_404(db, mission_id)
    sources = crud.list_research_sources(db, mission_id, quality_label=quality_label)
    return {"sources": [crud.research_source_to_dict(s) for s in sources]}


@router.get("/research-agent/missions/{mission_id}/files")
def list_files(
    mission_id: str,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    _get_mission_or_404(db, mission_id)
    files = crud.list_research_files(db, mission_id, status=status)
    return {"files": [crud.research_file_to_dict(f) for f in files]}


@router.get("/research-agent/missions/{mission_id}/activity")
def list_activity(
    mission_id: str,
    level: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    _get_mission_or_404(db, mission_id)
    entries = crud.list_research_activity(db, mission_id, level=level)
    return {"activity": [crud.research_activity_to_dict(e) for e in entries]}


# ──────────────────────────────────────────────────────────────────────────
# Scheduler / bounded resume queue / provider throttling — Phase 2B.2.1
#
# Extends this SAME router rather than a second dashboard/API surface, per
# the product spec's "لا تنشئ scheduler ثانياً موازياً" instruction. All
# reads are cheap in-memory/indexed-query lookups — no heavy work runs
# inside a request handler; bulk mutations (resume-selected, archive-stale)
# only flip mission status rows and let the already-running bounded queue
# (mission_scheduler.queue_manager) pick the work up on its own schedule.
# ──────────────────────────────────────────────────────────────────────────

class MissionIdsRequest(BaseModel):
    mission_ids: list[str]


@router.get("/research-agent/scheduler/status")
def scheduler_status(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    qm = mission_scheduler.queue_manager
    return {
        "bootstrap": readiness.to_dict(),
        "queue_manager_state": qm.state,
        "active_missions": qm.active_count,
        "max_active_missions": settings.research_max_active_missions,
        "queue_depth": qm.queue_depth,
        "db_pool": db_pool_metrics(),
        "metrics": {
            "claimed_total": qm.metrics.claimed_total,
            "started_total": qm.metrics.started_total,
            "completed_total": qm.metrics.completed_total,
        },
        "status_counts": crud.count_research_missions_by_status(db),
    }


@router.get("/research-agent/scheduler/queue")
def scheduler_queue(limit: int = 50, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    limit = max(1, min(limit, 200))
    upcoming = crud.list_resumable_research_missions(db, limit=limit)
    return {
        "queue_depth_in_memory": mission_scheduler.queue_manager.queue_depth,
        "upcoming": [crud.research_mission_to_dict(m) for m in upcoming],
    }


@router.get("/research-agent/scheduler/providers")
def scheduler_providers(user: dict = Depends(require_auth)):
    return {"providers": get_provider_status()}


@router.get("/research-agent/scheduler/resume-preview")
def scheduler_resume_preview(limit: int = 500, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    """Read-only — classifies every mission (bounded by `limit`) into why it
    would or wouldn't be auto-resumed, WITHOUT claiming or mutating
    anything. Required before any bulk action per the product spec."""
    limit = max(1, min(limit, 2000))
    missions = crud.list_research_missions(db)[:limit]
    buckets: dict[str, list[str]] = {}
    reasons: dict[str, str] = {}
    for m in missions:
        eligible, reason = classify_resumability(m)
        bucket = "resumable" if eligible else reason.split(" ", 1)[0]
        buckets.setdefault(bucket, []).append(m.id)
        reasons[m.id] = reason
    return {
        "total_considered": len(missions),
        "counts": {k: len(v) for k, v in buckets.items()},
        "sample_ids": {k: v[:20] for k, v in buckets.items()},
    }


@router.post("/research-agent/scheduler/resume-selected")
def scheduler_resume_selected(body: MissionIdsRequest, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _require_admin(user)
    requeued = 0
    for mission_id in body.mission_ids:
        mission = crud.get_research_mission(db, mission_id)
        if not mission or mission.status not in ("failed", "stopped", "cancelled"):
            continue
        crud.update_research_mission(
            db, mission_id, status="queued", current_phase="queued",
            queued_at=datetime.now(timezone.utc), last_error=None,
        )
        requeued += 1
    return {"ok": True, "requeued": requeued}


@router.post("/research-agent/scheduler/archive-stale")
def scheduler_archive_stale(body: MissionIdsRequest, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _require_admin(user)
    archived = crud.archive_research_missions(db, body.mission_ids)
    return {"ok": True, "archived": archived}


@router.post("/research-agent/scheduler/pause")
def scheduler_pause(user: dict = Depends(require_auth)):
    _require_admin(user)
    mission_scheduler.queue_manager.drain()
    return {"ok": True, "state": mission_scheduler.queue_manager.state}


@router.post("/research-agent/scheduler/resume")
def scheduler_resume_claiming(user: dict = Depends(require_auth)):
    _require_admin(user)
    mission_scheduler.queue_manager.resume_claiming()
    return {"ok": True, "state": mission_scheduler.queue_manager.state}


@router.post("/research-agent/scheduler/drain")
def scheduler_drain(user: dict = Depends(require_auth)):
    _require_admin(user)
    mission_scheduler.queue_manager.drain()
    return {"ok": True, "state": mission_scheduler.queue_manager.state}


# ──────────────────────────────────────────────────────────────────────────
# Dynamic Source Trust — Phase 2B.3
#
# static/dynamic/effective scores + trust_status live on ResearchSource
# itself (research_source_to_dict already includes them — see api/db/crud.py).
# All mutations go through SourceTrustService; recalculation is always
# enqueued (TrustRecalculationJob), never run synchronously inside a
# request handler.
# ──────────────────────────────────────────────────────────────────────────

def _get_source_or_404(db: Session, source_id: str):
    source = crud.get_research_source(db, source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


class SourceReviewRequest(BaseModel):
    status: str  # Trusted | Useful | Questionable | Rejected
    reason: str = ""
    note: str = ""


class SourceIdsRequest(BaseModel):
    source_ids: list[str]


@router.get("/research-agent/sources/{source_id}/trust")
def get_source_trust(source_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    source = _get_source_or_404(db, source_id)
    return {"source": crud.research_source_to_dict(source)}


@router.get("/research-agent/sources/{source_id}/trust/history")
def get_source_trust_history(source_id: str, limit: int = 100, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _get_source_or_404(db, source_id)
    history = crud.list_source_trust_history(db, source_id, limit=max(1, min(limit, 500)))
    return {"history": [crud.source_trust_history_to_dict(h) for h in history]}


@router.get("/research-agent/sources/{source_id}/trust/signals")
def get_source_trust_signals(source_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    source = _get_source_or_404(db, source_id)
    return {
        "trust_signal_summary": source.trust_signal_summary,
        "last_trust_calculated_at": source.last_trust_calculated_at.isoformat() if source.last_trust_calculated_at else None,
        "trust_algorithm_version": source.trust_algorithm_version,
    }


@router.post("/research-agent/sources/{source_id}/review")
def review_source(source_id: str, body: SourceReviewRequest, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _get_source_or_404(db, source_id)
    try:
        updated = submit_user_review(db, source_id, user["id"], body.status, reason=body.reason, note=body.note)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"ok": True, "source": crud.research_source_to_dict(updated)}


@router.post("/research-agent/sources/{source_id}/review/reset")
def reset_source_review(source_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _get_source_or_404(db, source_id)
    updated = reset_user_review(db, source_id, user["id"])
    return {"ok": True, "source": crud.research_source_to_dict(updated)}


@router.post("/research-agent/sources/{source_id}/recalculate")
def recalculate_source(source_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _get_source_or_404(db, source_id)
    trust_jobs.enqueue_recalculation(db, source_id, reason="manual")
    return {"ok": True, "enqueued": True}


@router.post("/research-agent/sources/recalculate-selected")
def recalculate_selected_sources(body: SourceIdsRequest, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _require_admin(user)
    enqueued = 0
    for source_id in body.source_ids:
        if crud.get_research_source(db, source_id):
            trust_jobs.enqueue_recalculation(db, source_id, reason="manual")
            enqueued += 1
    return {"ok": True, "enqueued": enqueued}


@router.get("/research-agent/trust/algorithm-version")
def get_trust_algorithm_version(user: dict = Depends(require_auth)):
    return {"algorithm_version": CURRENT_TRUST_ALGORITHM_VERSION}


@router.get("/research-agent/trust/recalculation-jobs")
def list_trust_jobs(status: Optional[str] = None, limit: int = 200, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    jobs = crud.list_trust_recalculation_jobs(db, status=status, limit=max(1, min(limit, 500)))
    return {"jobs": [crud.trust_recalculation_job_to_dict(j) for j in jobs]}


@router.get("/research-agent/sources/low-trust")
def list_low_trust_sources(limit: int = 50, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    sources = crud.list_research_sources_by_trust(db, status="low_trust", order="asc", limit=max(1, min(limit, 200)))
    return {"sources": [crud.research_source_to_dict(s) for s in sources]}


@router.get("/research-agent/sources/unproven")
def list_unproven_sources(limit: int = 50, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    sources = crud.list_research_sources_by_trust(db, status="unproven", limit=max(1, min(limit, 200)))
    return {"sources": [crud.research_source_to_dict(s) for s in sources]}


@router.get("/research-agent/sources/needing-verification")
def list_sources_needing_verification(limit: int = 50, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    """Sources whose evidence never had independent (different-family)
    corroboration for anything they support — bounded scan over the most
    recently fetched sources, not a full-table pass."""
    limit = max(1, min(limit, 200))
    candidates = crud.list_research_sources_by_trust(db, limit=200)
    out = []
    for source in candidates:
        evidence = crud.list_knowledge_evidence_by_source(db, source.id)
        supporting = [e for e in evidence if e.supports and e.node_id]
        if not supporting:
            continue
        needs_verification = True
        for e in supporting:
            other_families = {
                (crud.get_research_source(db, ev2.research_source_id).source_family_id
                 or ev2.research_source_id)
                for ev2 in crud.list_knowledge_evidence(db, node_id=e.node_id)
                if ev2.supports and crud.get_research_source(db, ev2.research_source_id)
            } - {source.source_family_id or source.id}
            if other_families:
                needs_verification = False
                break
        if needs_verification:
            out.append(source)
        if len(out) >= limit:
            break
    return {"sources": [crud.research_source_to_dict(s) for s in out]}


# ── Research Memory & Knowledge Freshness (Phase 2B.4) ──────────────────────

def _get_topic_memory_or_404(db: Session, topic_memory_id: str):
    memory = crud.get_topic_research_memory(db, topic_memory_id)
    if not memory:
        raise HTTPException(status_code=404, detail="Topic memory not found")
    return memory


@router.get("/research-agent/topics/{topic_memory_id}/memory")
def get_topic_memory(topic_memory_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    memory = _get_topic_memory_or_404(db, topic_memory_id)
    return crud.topic_research_memory_to_dict(memory)


@router.get("/research-agent/topics/{topic_memory_id}/freshness")
def get_topic_freshness(topic_memory_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    from api.services.research_brain.research_memory import compute_freshness
    memory = _get_topic_memory_or_404(db, topic_memory_id)
    status = compute_freshness(db, topic_memory_id)
    db.refresh(memory)
    return {
        "topic_memory_id": memory.id,
        "freshness_status": status,
        "content_category": memory.content_category,
        "last_update": memory.last_update.isoformat() if memory.last_update else None,
        "next_refresh": memory.next_refresh.isoformat() if memory.next_refresh else None,
    }


@router.post("/research-agent/topics/{topic_memory_id}/refresh")
def refresh_topic_route(topic_memory_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    from api.services.research_brain.research_memory import refresh_topic
    _get_topic_memory_or_404(db, topic_memory_id)
    try:
        mission = refresh_topic(db, topic_memory_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "mission_id": mission.id}


@router.get("/research-agent/topics/{topic_memory_id}/refresh/status")
def refresh_topic_status(topic_memory_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    memory = _get_topic_memory_or_404(db, topic_memory_id)
    return {
        "topic_memory_id": memory.id,
        "freshness_status": memory.freshness_status,
        "last_research": memory.last_research.isoformat() if memory.last_research else None,
        "next_refresh": memory.next_refresh.isoformat() if memory.next_refresh else None,
    }


@router.get("/research-agent/topics/{topic_memory_id}/refresh/history")
def refresh_topic_history(topic_memory_id: str, limit: int = 50, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    memory = _get_topic_memory_or_404(db, topic_memory_id)
    topics = (
        db.query(crud.ResearchTopic)
        .filter(crud.ResearchTopic.topic_memory_id == topic_memory_id)
        .order_by(crud.ResearchTopic.created_at.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    missions = []
    for topic in topics:
        mission = crud.get_research_mission(db, topic.mission_id)
        if mission:
            missions.append(crud.research_mission_to_dict(mission))
    return {"topic_memory_id": memory.id, "missions": missions}


@router.get("/research-agent/topics/outdated")
def list_outdated_topics(limit: int = 200, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    memories = crud.list_outdated_topic_memories(db, limit=max(1, min(limit, 500)))
    return {"topics": [crud.topic_research_memory_to_dict(m) for m in memories]}
