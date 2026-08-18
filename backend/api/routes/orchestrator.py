"""Cognitive Layer (Phase 2): AI Orchestrator debug endpoint.

Exposes plan_request()'s computed RequestPlan so the heuristics can be
verified without a full chat round-trip. Not used by the chat pipeline
itself — routes/chat.py calls orchestrator_service.plan_request() directly.
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter

from api.services.orchestrator_service import plan_request

router = APIRouter(prefix="/orchestrator", tags=["orchestrator"])


@router.get("/plan")
def get_plan_endpoint(message: str, workspace_id: Optional[str] = None, has_image: bool = False):
    plan = plan_request(message, workspace_id=workspace_id, has_image=has_image)
    return plan.to_dict()
