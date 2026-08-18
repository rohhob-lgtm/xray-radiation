"""Read-only routes for Agent Orchestrator runs — lets a run's plan, steps,
and artifacts be independently verified/refetched after a page refresh,
instead of relying only on the chat message's embedded sentinel payload."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from api.db import get_db, crud
from api.middleware.auth import require_auth

router = APIRouter(prefix="/agent-runs", tags=["agent-orchestrator"])


def _run_to_dict(run) -> dict:
    return {
        "id": run.id, "conversation_id": run.conversation_id, "source_module": run.source_module,
        "intent": run.intent, "status": run.status, "progress": run.progress,
        "current_step_id": run.current_step_id, "error_code": run.error_code,
        "error_message": run.error_message, "cost_usd": run.cost_usd, "latency_ms": run.latency_ms,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "steps": [
            {
                "id": s.id, "step_key": s.step_key, "provider": s.provider, "action": s.action,
                "status": s.status, "error_code": s.error_code, "error_message": s.error_message,
                "latency_ms": s.latency_ms,
            }
            for s in run.steps
        ],
        "artifacts": [
            {
                "id": a.id, "step_key": a.step_key, "type": a.type, "provider": a.provider,
                "external_id": a.external_id, "url": a.url, "filename": a.filename,
                "mime_type": a.mime_type, "size_bytes": a.size_bytes,
            }
            for a in run.artifacts
        ],
    }


@router.get("/{run_id}")
def get_agent_run(run_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    run = crud.get_agent_run(db, run_id)
    if not run or run.user_id != user["id"]:
        raise HTTPException(status_code=404, detail="Agent run not found")
    return _run_to_dict(run)


@router.get("")
def list_agent_runs(conversation_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    runs = [r for r in crud.list_agent_runs(db, conversation_id) if r.user_id == user["id"]]
    return {"items": [_run_to_dict(r) for r in runs]}
