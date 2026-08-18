"""
Cognitive Layer (Phase 2): Task Memory + Project Timeline routes.

ProjectTask is a human work-item (Open/In Progress/Blocked/Completed) —
distinct from WorkspaceTask (one agent execution run). Status transitions
are the real timeline/graph wiring point: they call timeline_service and
graph_service so a task's history feeds both the Timeline and the Knowledge
Graph from one write.
"""
from __future__ import annotations
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db, crud
from api.middleware.auth import require_auth
from api.services import timeline_service, graph_service, learning_service
from api.services.identity import MemoryScope

router = APIRouter(tags=["tasks"])

_VALID_STATUSES = {"open", "in_progress", "blocked", "completed"}


def _scope(user: dict) -> MemoryScope:
    return MemoryScope(user_id=user["id"], anon_session_id=None, is_persistent=True)


def _owned_task(db: Session, task_id: str, user_id: str) -> "crud.ProjectTask":
    task = crud.get_project_task(db, task_id, user_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


class CreateTaskInput(BaseModel):
    module: str = "general"
    title: str
    description: str = ""
    conversation_id: Optional[str] = None
    workspace_id: Optional[str] = None
    linked_file_ids: List[str] = []
    linked_commit_refs: List[str] = []


class UpdateTaskInput(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    linked_file_ids: Optional[List[str]] = None
    linked_commit_refs: Optional[List[str]] = None


class UpdateStatusInput(BaseModel):
    status: str
    blocked_reason: Optional[str] = None
    # Used as the Learning Engine's solution_summary when status="completed";
    # falls back to the task's description if omitted.
    resolution_note: Optional[str] = None


@router.post("/tasks", status_code=201)
def create_task_endpoint(
    body: CreateTaskInput, db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    task = crud.create_project_task(
        db, user["id"], body.module, body.title, description=body.description,
        conversation_id=body.conversation_id, workspace_id=body.workspace_id,
        linked_file_ids=body.linked_file_ids, linked_commit_refs=body.linked_commit_refs,
    )
    return crud.project_task_to_dict(task)


@router.get("/tasks")
def list_tasks_endpoint(
    status: Optional[str] = None, module: Optional[str] = None,
    db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    tasks = crud.list_project_tasks(db, user["id"], status=status, module=module)
    return [crud.project_task_to_dict(t) for t in tasks]


@router.get("/tasks/{task_id}")
def get_task_endpoint(task_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    return crud.project_task_to_dict(_owned_task(db, task_id, user["id"]))


@router.patch("/tasks/{task_id}")
def update_task_endpoint(
    task_id: str, body: UpdateTaskInput, db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    _owned_task(db, task_id, user["id"])
    task = crud.update_project_task(
        db, task_id, user["id"], title=body.title, description=body.description,
        linked_file_ids=body.linked_file_ids, linked_commit_refs=body.linked_commit_refs,
    )
    return crud.project_task_to_dict(task)


@router.patch("/tasks/{task_id}/status")
async def update_task_status_endpoint(
    task_id: str, body: UpdateStatusInput, db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    if body.status not in _VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"status must be one of {sorted(_VALID_STATUSES)}")
    task = _owned_task(db, task_id, user["id"])
    scope = _scope(user)

    updated = crud.update_project_task_status(db, task_id, user["id"], body.status, blocked_reason=body.blocked_reason)

    # Real Timeline + Knowledge Graph wiring — one write feeds both.
    await timeline_service.record_event(
        db, scope, module=task.module, event_type=body.status,
        title=f"Task {body.status}: {task.title}",
        description=body.blocked_reason or body.resolution_note or task.description,
        source_ref=task.id,
        related_entity=("task", task.id),
    )

    if task.conversation_id:
        await graph_service.link(
            db, scope, ("task", task.id), ("conversation", task.conversation_id), relationship="discussed_in",
            from_label=task.title,
        )
    for file_id in (task.linked_file_ids or []):
        await graph_service.link(db, scope, ("task", task.id), ("file", file_id), relationship="references", from_label=task.title)

    # Learning Engine capture path (b): completing a task with a linked
    # conversation auto-records the fix — explicit signal (a status
    # transition the user made), not a guess from every reply.
    if body.status == "completed" and task.conversation_id:
        solution_summary = body.resolution_note or task.description or task.title
        await learning_service.record_solution(
            db, scope, task.module, problem_summary=task.title, solution_summary=solution_summary,
            source_ref=task.conversation_id,
        )

    return crud.project_task_to_dict(updated)


@router.get("/timeline")
def get_timeline_endpoint(
    module: Optional[str] = None, limit: int = 50,
    db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    scope = _scope(user)
    return timeline_service.get_timeline(db, scope, module=module, limit=limit)


@router.get("/timeline/what-changed")
async def what_changed_endpoint(
    query: str = "What changed recently?", since: Optional[datetime] = None,
    db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    scope = _scope(user)
    answer = await timeline_service.answer_what_changed(db, scope, query, since=since)
    return {"query": query, "answer": answer}
