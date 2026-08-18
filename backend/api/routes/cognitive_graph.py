"""
Cognitive Layer (Phase 2): Knowledge Graph routes.

Mounted at /api/cognitive-graph — deliberately a distinct prefix from the
existing /api/graph/data (admin-curated document-concept graph in
routes/graph.py). This is the generic users/projects/files/modules/bugs/
decisions/documents relationship graph.
"""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from api.db import get_db
from api.middleware.auth import require_auth
from api.services import graph_service
from api.services.identity import MemoryScope

router = APIRouter(prefix="/cognitive-graph", tags=["cognitive-graph"])


@router.get("/related/{entity_type}/{entity_ref}")
async def get_related_endpoint(
    entity_type: str,
    entity_ref: str,
    depth: int = 2,
    query: Optional[str] = None,
    limit: int = 20,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    scope = MemoryScope(user_id=user["id"], anon_session_id=None, is_persistent=True)
    results = await graph_service.find_related(
        db, scope, entity_type, entity_ref, depth=min(depth, 5), query=query, limit=min(limit, 100),
    )
    return {"entity_type": entity_type, "entity_ref": entity_ref, "related": results}
