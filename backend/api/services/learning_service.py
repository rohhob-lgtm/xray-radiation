"""
Cognitive Layer (Phase 2): Learning Engine.

Reuses MemoryItem with kind="solution" — no schema change (kind already
accepts arbitrary strings). Capture stays explicit/event-driven, matching
Phase 1's "no LLM classifier per message" decision: a solution is recorded
only when a user explicitly pins one (POST /api/memory/pin with
kind="solution") or a ProjectTask completes with a linked conversation —
never guessed from every reply.
"""
from __future__ import annotations
from typing import List, Optional

from sqlalchemy.orm import Session

from api.db import crud
from api.services.embedding_service import get_embedding
from api.services.identity import MemoryScope
from api.services.retrieval_utils import MemoryResult, tokenize, keyword_score, cosine_similarity

# Higher bar than general memory search (0.10) — a "proven solution" surfaced
# ahead of fresh generation needs real confidence, not loose relevance.
_MIN_SOLUTION_SCORE = 0.35


async def record_solution(
    db: Session,
    scope: MemoryScope,
    module: str,
    problem_summary: str,
    solution_summary: str,
    source_ref: Optional[str] = None,
) -> Optional["crud.MemoryItem"]:
    if not scope.is_persistent or not scope.user_id:
        return None
    content = f"PROBLEM: {problem_summary}\n\nSOLUTION: {solution_summary}"
    embedding = await get_embedding(content)
    return crud.create_memory_item(
        db, user_id=scope.user_id, module=module, kind="solution",
        content=content, title=problem_summary[:80], embedding=embedding,
        source_type="explicit", source_ref=source_ref,
    )


async def find_proven_solution(
    db: Session, scope: MemoryScope, module: Optional[str], problem_query: str,
    min_score: float = _MIN_SOLUTION_SCORE,
) -> Optional[MemoryResult]:
    """Best matching proven solution above the confidence bar, or None.
    "Reuse before generating new" means callers check this before asking
    the LLM to solve the problem from scratch."""
    if not scope.is_persistent or not scope.user_id:
        return None

    query_tokens = tokenize(problem_query)
    if not query_tokens:
        return None
    query_embedding = await get_embedding(problem_query)

    items = crud.list_memory_items(db, scope.user_id, module=module, kind="solution")
    best: Optional[MemoryResult] = None
    for item in items:
        kw = keyword_score(query_tokens, item.content)
        boost = 0.0
        if query_embedding and item.embedding:
            boost = max(0.0, cosine_similarity(query_embedding, item.embedding))
        score = kw + boost * 0.3
        if score < min_score:
            continue
        if best is None or score > best.score:
            best = MemoryResult(
                source_kind="solution", title=item.title, content=item.content,
                score=score, meta={"id": item.id, "module": item.module},
            )
    return best
