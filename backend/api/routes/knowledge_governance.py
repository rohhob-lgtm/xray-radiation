"""
Knowledge Governance Layer — Phase 2B.2 API.

A read/administer surface over the governance tables written by
api.services.knowledge_governance.governance_service (the only path allowed
to write to the knowledge graph):

  GET  /governance/nodes/{id}/provenance   — full provenance history for a fact
  GET  /governance/nodes/{id}/audit        — audit log entries for a fact
  GET  /governance/conflicts               — list (filters: status, severity, human_review_required)
  GET  /governance/conflicts/{id}          — one conflict, both claims + sources
  POST /governance/conflicts/{id}/resolve  — human sets resolution_status/recommended_interpretation
                                              (never touches claim_a/claim_b — those persist regardless)
  POST /governance/nodes/{id}/rollback     — revert a node to its immediately-previous version
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.db import crud
from api.middleware.auth import require_auth
from api.services.knowledge_governance.governance_service import governance

router = APIRouter(prefix="/governance", tags=["knowledge-governance"])


def _get_node_or_404(db: Session, node_id: str):
    node = crud.get_knowledge_node(db, node_id)
    if not node:
        raise HTTPException(status_code=404, detail="Node not found")
    return node


def _get_conflict_or_404(db: Session, conflict_id: str):
    conflict = crud.get_knowledge_conflict(db, conflict_id)
    if not conflict:
        raise HTTPException(status_code=404, detail="Conflict not found")
    return conflict


@router.get("/nodes/{node_id}/provenance")
def get_node_provenance(node_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _get_node_or_404(db, node_id)
    rows = crud.list_knowledge_provenance(db, node_id=node_id)
    return {"provenance": [crud.knowledge_provenance_to_dict(r) for r in rows]}


@router.get("/nodes/{node_id}/audit")
def get_node_audit(node_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _get_node_or_404(db, node_id)
    rows = crud.list_knowledge_audit_log(db, node_id=node_id)
    return {"audit": [crud.knowledge_audit_log_to_dict(r) for r in rows]}


@router.get("/conflicts")
def list_conflicts(
    status: str | None = None,
    severity: str | None = None,
    human_review_required: bool | None = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    rows = crud.list_knowledge_conflicts(db, status=status, severity=severity, human_review_required=human_review_required)
    return {"conflicts": [crud.knowledge_conflict_to_dict(r) for r in rows]}


@router.get("/conflicts/{conflict_id}")
def get_conflict(conflict_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    conflict = _get_conflict_or_404(db, conflict_id)
    return {"conflict": crud.knowledge_conflict_to_dict(conflict)}


class ResolveConflictRequest(BaseModel):
    resolution_status: str
    recommended_interpretation: str | None = None


@router.post("/conflicts/{conflict_id}/resolve")
def resolve_conflict(
    conflict_id: str, body: ResolveConflictRequest,
    db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    _get_conflict_or_404(db, conflict_id)
    # Only resolution metadata changes here — claim_a/claim_b are never
    # touched by this endpoint, so both original claims remain queryable
    # regardless of how the conflict is resolved.
    updated = crud.update_knowledge_conflict(
        db, conflict_id,
        resolution_status=body.resolution_status,
        recommended_interpretation=body.recommended_interpretation,
    )
    return {"ok": True, "conflict": crud.knowledge_conflict_to_dict(updated)}


class RollbackRequest(BaseModel):
    reason: str = ""


@router.post("/nodes/{node_id}/rollback")
def rollback_node(
    node_id: str, body: RollbackRequest,
    db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    node = _get_node_or_404(db, node_id)
    if not node.supersedes_id:
        raise HTTPException(status_code=422, detail="Node has no previous version to roll back to")
    restored = governance.rollback_fact(db, node_id, reason=body.reason, created_by_service="governance_api")
    if not restored:
        raise HTTPException(status_code=422, detail="Rollback failed — previous version not found")
    return {"ok": True, "restored_node": crud.knowledge_node_to_dict(restored)}
