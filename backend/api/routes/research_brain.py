"""
Knowledge Evolution Engine — Sub-Phases 2A + 2B.1 API.

Endpoints:
  GET  /research-brain/missions/{id}/plan       — the topic tree with estimates/questions/strategy
  GET  /research-brain/missions/{id}/coverage    — gap detector output per topic
  GET  /research-brain/nodes/{id}                — one fact with its version chain + evidence
  GET  /research-brain/missions/{id}/curiosity   — self-generated questions for a mission
  POST /research-brain/curiosity/{id}/approve    — manually approve + queue a question (spawns a mission)
  POST /research-brain/curiosity/{id}/reject     — reject a question

Mostly a read surface over data written by api.services.research_brain and
api.services.research_agent.job_runner (2A/2B.1 wiring) — the only mutation
endpoints are the curiosity approve/reject actions; missions themselves are
still created/paused/resumed/stopped through api/routes/research_agent.py
(Phase 1), unchanged.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db import get_db
from api.db import crud
from api.middleware.auth import require_auth
from api.services.research_brain.gap_detector import list_low_coverage_topics
from api.services.research_brain.curiosity_engine import queue_question

router = APIRouter(tags=["research-brain"])


def _get_mission_or_404(db: Session, mission_id: str):
    mission = crud.get_research_mission(db, mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Mission not found")
    return mission


@router.get("/research-brain/missions/{mission_id}/plan")
def get_plan(mission_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _get_mission_or_404(db, mission_id)
    plan = crud.get_research_plan_by_mission(db, mission_id)
    topics = crud.list_research_topics(db, mission_id)
    return {
        "plan": crud.research_plan_to_dict(plan) if plan else None,
        "topics": [crud.research_topic_to_dict(t) for t in topics],
    }


@router.get("/research-brain/missions/{mission_id}/coverage")
def get_coverage(mission_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _get_mission_or_404(db, mission_id)
    topics = crud.list_research_topics(db, mission_id)
    coverage = [
        {"topic_id": t.id, "label": t.label, "coverage_pct": t.coverage_pct, "status": t.status}
        for t in topics
    ]
    low_coverage = list_low_coverage_topics(db, mission_id)
    return {"coverage": coverage, "suggestions": low_coverage}


@router.get("/research-brain/nodes/{node_id}")
def get_node(node_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    node = crud.get_knowledge_node(db, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")

    chain = crud.get_knowledge_node_version_chain(db, node_id)
    evidence = crud.list_knowledge_evidence(db, node_id=node_id)
    supporting = [e for e in evidence if e.supports]
    conflicting = [e for e in evidence if not e.supports]

    return {
        "node": crud.knowledge_node_to_dict(node),
        "version_chain": [crud.knowledge_node_to_dict(n) for n in chain],
        "supporting_sources": [crud.knowledge_evidence_to_dict(e) for e in supporting],
        "conflicting_sources": [crud.knowledge_evidence_to_dict(e) for e in conflicting],
    }


@router.get("/research-brain/missions/{mission_id}/curiosity")
def list_curiosity(
    mission_id: str,
    status: str | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    _get_mission_or_404(db, mission_id)
    questions = crud.list_curiosity_questions(db, mission_id=mission_id, status=status)
    return {"questions": [crud.curiosity_question_to_dict(q) for q in questions]}


def _get_curiosity_question_or_404(db: Session, question_id: str):
    question = crud.get_curiosity_question(db, question_id)
    if not question:
        raise HTTPException(status_code=404, detail="Curiosity question not found")
    return question


@router.post("/research-brain/curiosity/{question_id}/approve")
def approve_curiosity(question_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    question = _get_curiosity_question_or_404(db, question_id)
    if question.status != "Suggested":
        raise HTTPException(status_code=422, detail=f"Question is '{question.status}', not 'Suggested' — nothing to approve")
    mission = crud.get_research_mission(db, question.mission_id)
    if not mission:
        raise HTTPException(status_code=404, detail="Parent mission not found")
    # Manual approval IS the gate here — bypasses the auto-queue settings
    # thresholds (min_priority/min_knowledge_gain/limits) that only apply to
    # automatic queuing.
    updated = queue_question(db, mission, question)
    return {"ok": True, "question": crud.curiosity_question_to_dict(updated)}


@router.post("/research-brain/curiosity/{question_id}/reject")
def reject_curiosity(question_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    question = _get_curiosity_question_or_404(db, question_id)
    if question.status not in ("Suggested", "Approved"):
        raise HTTPException(status_code=422, detail=f"Question is '{question.status}' — cannot reject")
    updated = crud.update_curiosity_question(db, question_id, status="Rejected")
    return {"ok": True, "question": crud.curiosity_question_to_dict(updated)}
