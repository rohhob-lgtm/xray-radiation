"""
Cognitive Layer (Phase 2): Knowledge Graph.

Generic cross-cutting relationship graph over users, projects, files,
modules, bugs, decisions, and documents — deliberately separate from the
admin-curated document-concept graph (KnowledgeNode/KnowledgeEdge in
api.db.models + routes/graph.py). Same authenticated-only gating as
MemoryItem: linking is a no-op for non-persistent (anonymous) scopes.

link() is the single choke point every Phase 2 write-path calls (mirrors
the mark_dirty()-is-the-one-integration-point pattern from Phase 1's
workspace_index.py) — callers never touch CognitiveNode/CognitiveEdge
directly.
"""
from __future__ import annotations
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from api.db import crud
from api.services.embedding_service import get_embedding
from api.services.identity import MemoryScope
from api.services.retrieval_utils import cosine_similarity

Entity = Tuple[str, str]  # (entity_type, entity_ref)


def link_sync(
    db: Session,
    scope: MemoryScope,
    from_entity: Entity,
    to_entity: Entity,
    relationship: str,
    from_label: str = "",
    to_label: str = "",
    module: str = "general",
) -> Optional["crud.CognitiveEdge"]:
    """
    Synchronous core — upserts both endpoint nodes (without embeddings) and
    the edge between them. This is what crud.py's choke points call
    (add_workspace_file, create_rag_document, create_memory_item are plain
    sync functions used throughout the codebase; keeping this sync avoids
    threading async through them, which would be a real redesign). Node
    embeddings for semantic traversal are populated by the async link()
    below when called from already-async contexts (chat.py, timeline_service).
    """
    if not scope.is_persistent or not scope.user_id:
        return None
    from_node = crud.upsert_cognitive_node(
        db, scope.user_id, from_entity[0], from_entity[1], label=from_label, module=module,
    )
    to_node = crud.upsert_cognitive_node(
        db, scope.user_id, to_entity[0], to_entity[1], label=to_label, module=module,
    )
    return crud.create_cognitive_edge(db, from_node.id, to_node.id, relationship)


async def link(
    db: Session,
    scope: MemoryScope,
    from_entity: Entity,
    to_entity: Entity,
    relationship: str,
    from_label: str = "",
    to_label: str = "",
    module: str = "general",
    embed_labels: bool = False,
) -> Optional["crud.CognitiveEdge"]:
    """Async variant — same as link_sync() but can additionally embed node
    labels for semantic traversal. No-op for non-persistent (anonymous)
    scopes — the graph is durable memory."""
    if not scope.is_persistent or not scope.user_id:
        return None

    edge = link_sync(db, scope, from_entity, to_entity, relationship, from_label, to_label, module)
    if edge is None or not embed_labels:
        return edge

    if from_label:
        from_embedding = await get_embedding(from_label)
        if from_embedding:
            crud.upsert_cognitive_node(db, scope.user_id, from_entity[0], from_entity[1], embedding=from_embedding)
    if to_label:
        to_embedding = await get_embedding(to_label)
        if to_embedding:
            crud.upsert_cognitive_node(db, scope.user_id, to_entity[0], to_entity[1], embedding=to_embedding)
    return edge


async def find_related(
    db: Session,
    scope: MemoryScope,
    entity_type: str,
    entity_ref: str,
    depth: int = 2,
    query: Optional[str] = None,
    limit: int = 20,
) -> List[dict]:
    """
    BFS traversal up to `depth` hops from the given entity. When `query` is
    provided, results are ranked by cosine similarity to the query
    (falling back to hop-distance ordering for nodes without an embedding);
    otherwise ordered by hop distance alone.
    """
    if not scope.is_persistent or not scope.user_id:
        return []

    start = crud.get_cognitive_node(db, entity_type, entity_ref)
    if not start:
        return []

    query_embedding = await get_embedding(query) if query else None

    visited = {start.id}
    frontier = [start.id]
    collected: List[dict] = []

    for hop in range(1, depth + 1):
        next_frontier: List[str] = []
        for node_id in frontier:
            for edge in crud.list_edges_for_node(db, node_id):
                other_id = edge.to_node_id if edge.from_node_id == node_id else edge.from_node_id
                if other_id in visited:
                    continue
                visited.add(other_id)
                next_frontier.append(other_id)

                other = crud.get_cognitive_node_by_id(db, other_id)
                if not other or other.user_id != scope.user_id:
                    continue

                score = 1.0 / hop
                if query_embedding and other.embedding:
                    score = max(0.0, cosine_similarity(query_embedding, other.embedding))

                collected.append({
                    "node": crud.cognitive_node_to_dict(other),
                    "relationship": edge.relationship,
                    "hop_distance": hop,
                    "score": score,
                })
        frontier = next_frontier
        if not frontier:
            break

    collected.sort(key=lambda r: r["score"], reverse=True)
    return collected[:limit]
