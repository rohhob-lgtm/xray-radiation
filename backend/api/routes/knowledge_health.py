"""
Knowledge Health — Phase 2B.9 API.

Endpoints:
  GET /knowledge-health/overview         — overall score + top recommendations
  GET /knowledge-health/topics           — per-topic snapshots (filterable by classification)
  GET /knowledge-health/manufacturers    — per-manufacturer snapshots
  GET /knowledge-health/conflicts        — open KnowledgeConflicts (thin wrapper, unchanged 2B.2 store)
  GET /knowledge-health/recommendations  — recommended next actions

Pure read surface over api.services.research_brain.knowledge_health's cache
(KnowledgeHealthSnapshot) — no endpoint here triggers recomputation; the
audit runs only on the existing MissionScheduler tick (job_runner.py).
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.db import get_db, crud
from api.middleware.auth import require_auth
from api.services.research_brain import knowledge_health as kh

router = APIRouter(tags=["knowledge-health"])


@router.get("/knowledge-health/overview")
def get_overview(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    overall = kh.get_overall_health(db)
    return {
        "overall": crud.knowledge_health_snapshot_to_dict(overall) if overall else None,
        "outdated_topics": [crud.knowledge_health_snapshot_to_dict(s) for s in kh.get_outdated_topics(db)],
        "low_trust_topics": [crud.knowledge_health_snapshot_to_dict(s) for s in kh.get_low_trust_topics(db)],
        "safety_critical_gaps": [crud.knowledge_health_snapshot_to_dict(s) for s in kh.get_safety_critical_gaps(db)],
        "weak_manufacturer_coverage": [crud.knowledge_health_snapshot_to_dict(s) for s in kh.get_weak_manufacturer_coverage(db)],
    }


@router.get("/knowledge-health/topics")
def get_topics(
    classification: str | None = None, db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    rows = crud.list_knowledge_health_snapshots(db, scope_type="Topic", classification=classification, limit=200)
    return {"topics": [crud.knowledge_health_snapshot_to_dict(s) for s in rows]}


@router.get("/knowledge-health/manufacturers")
def get_manufacturers(
    classification: str | None = None, db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    rows = crud.list_knowledge_health_snapshots(db, scope_type="Manufacturer", classification=classification, limit=200)
    return {"manufacturers": [crud.knowledge_health_snapshot_to_dict(s) for s in rows]}


@router.get("/knowledge-health/conflicts")
def get_conflicts(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    conflicts = kh.get_unresolved_conflicts_summary(db, limit=50)
    return {"conflicts": [crud.knowledge_conflict_to_dict(c) for c in conflicts]}


@router.get("/knowledge-health/recommendations")
def get_recommendations(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    return {"recommended_actions": kh.get_recommended_actions(db)}
