"""
Global AI Brain — Phase 1.

Module-agnostic memory core: every function takes a `module` tag and a
MemoryScope so Phase 2 can wire Translation/Training/Research/Patent/
Physics/Education into the exact same API without redesign.

Capture is hybrid, per product decision — NOT an LLM classifier on every
message:
  - remember_explicit()      — the user states something directly, or pins it
  - record_project_event()   — a module completes a concrete piece of work
  - summarize_conversation_if_due() — one LLM call per ~20-30 turns, not per turn
  - automatic document indexing already exists (rag_service / embed_and_store)

search_global_brain() is the single semantic-search-before-every-response
entry point, merging documents, durable memory, conversation summaries, and
(when a workspace is active) workspace-indexed content.
"""
from __future__ import annotations
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from api.db import crud
from api.services.embedding_service import get_embedding
from api.services.identity import MemoryScope
from api.services.retrieval_utils import MemoryResult, tokenize, keyword_score, cosine_similarity

log = logging.getLogger(__name__)

# Minimum combined score for a MemoryItem/ConversationSummary hit to be worth
# surfacing — mirrors the threshold philosophy already used in rag_service's
# chunk scoring so all Global Brain sources are held to the same bar.
_MIN_KEYWORD_SCORE = 0.10
_MIN_SEMANTIC_BOOST = 0.70


# ──────────────────────────────────────────────────────────
# Capture
# ──────────────────────────────────────────────────────────

async def remember_explicit(
    db: Session,
    scope: MemoryScope,
    module: str,
    content: str,
    title: str = "",
    source_ref: Optional[str] = None,
) -> Optional["crud.MemoryItem"]:
    """Explicit user-stated preference/decision/note. No-op for non-persistent scopes."""
    if not scope.is_persistent or not scope.user_id:
        return None
    embedding = await get_embedding(content)
    return crud.create_memory_item(
        db, user_id=scope.user_id, module=module, kind="decision",
        content=content, title=title or content[:80], embedding=embedding,
        source_type="explicit", source_ref=source_ref,
    )


async def record_project_event(
    db: Session,
    scope: MemoryScope,
    module: str,
    title: str,
    content: str,
    source_ref: Optional[str] = None,
) -> Optional["crud.MemoryItem"]:
    """Automatic capture from a concrete module completion (no LLM classification)."""
    if not scope.is_persistent or not scope.user_id:
        return None
    embedding = await get_embedding(content)
    return crud.create_memory_item(
        db, user_id=scope.user_id, module=module, kind="project_event",
        content=content, title=title, embedding=embedding,
        source_type="project_event", source_ref=source_ref,
    )


async def pin_message(
    db: Session,
    scope: MemoryScope,
    conversation_id: str,
    message_id: str,
    module: str = "general",
    note: Optional[str] = None,
    kind: str = "pinned",
) -> Optional["crud.MemoryItem"]:
    """
    Manual pinning of a chat message into durable memory. `kind` defaults to
    "pinned" (unchanged from Phase 1) — Phase 2's Learning Engine reuses this
    same endpoint with kind="solution" to record a proven fix, so pinning a
    solved-problem reply is the explicit capture path (no auto-classifier).
    """
    if not scope.is_persistent or not scope.user_id:
        return None
    msg = crud.get_message(db, message_id)
    if not msg or msg.conversation_id != conversation_id:
        return None
    content = (note + "\n\n" if note else "") + msg.content
    embedding = await get_embedding(content)
    return crud.create_memory_item(
        db, user_id=scope.user_id, module=module, kind=kind,
        content=content, title=msg.content[:80], embedding=embedding, pinned=(kind == "pinned"),
        source_type="explicit", source_ref=conversation_id,
    )


async def summarize_conversation_if_due(db: Session, conversation_id: str, every_n: int = 25) -> None:
    """
    Compress the block of messages since the last summary into one
    ConversationSummary, once >= every_n new messages have accumulated.

    Runs as a fire-and-forget background task after every assistant reply is
    saved — callers MUST pass a session that is safe to use outside the
    request lifecycle (a fresh SessionLocal(), not the request's `db`).
    """
    messages = crud.get_messages(db, conversation_id)
    if not messages:
        return

    latest_summary = crud.get_latest_conversation_summary(db, conversation_id)
    if latest_summary and latest_summary.covers_to_message_id:
        covered_ids = {m.id for m in messages if m.id == latest_summary.covers_to_message_id}
        if covered_ids:
            cutoff_index = next(
                (i for i, m in enumerate(messages) if m.id == latest_summary.covers_to_message_id), -1
            )
            new_messages = messages[cutoff_index + 1:]
        else:
            new_messages = messages
    else:
        new_messages = messages

    if len(new_messages) < every_n:
        return

    from api.services.ai_providers.registry import provider_registry
    provider = provider_registry.get_active()
    if not provider:
        return

    transcript = "\n".join(f"{m.role}: {m.content}" for m in new_messages)
    try:
        summary_text = await provider.chat(
            [{"role": "user", "content": transcript[:12000]}],
            system_prompt=(
                "Summarize this chat excerpt in 3-6 concise bullet points, capturing any "
                "decisions, preferences, facts, or open action items. Do not restate small talk."
            ),
        )
    except Exception:
        log.exception("Conversation summarization failed for conversation_id=%s", conversation_id)
        return

    embedding = await get_embedding(summary_text)
    crud.create_conversation_summary(
        db, conversation_id=conversation_id, summary_text=summary_text, embedding=embedding,
        covers_from_message_id=new_messages[0].id, covers_to_message_id=new_messages[-1].id,
        message_count_covered=len(new_messages),
    )


# ──────────────────────────────────────────────────────────
# Retrieval
# ──────────────────────────────────────────────────────────

def _score_text(
    query_tokens: List[str], query_embedding: Optional[List[float]], content: str, item_embedding,
) -> Optional[float]:
    kw = keyword_score(query_tokens, content)
    boost = 0.0
    if query_embedding and item_embedding:
        boost = max(0.0, cosine_similarity(query_embedding, item_embedding))
    combined = kw + boost * 0.2
    if kw >= _MIN_KEYWORD_SCORE or (boost >= _MIN_SEMANTIC_BOOST and combined > 0.05):
        return combined
    return None


async def _search_memory_items(
    db: Session, scope: MemoryScope, query_tokens: List[str], query_embedding, module: Optional[str], top_k: int,
) -> List[MemoryResult]:
    if not scope.is_persistent or not scope.user_id:
        return []
    items = crud.list_memory_items(db, scope.user_id, module=module)
    results: List[MemoryResult] = []
    for item in items:
        score = _score_text(query_tokens, query_embedding, item.content, item.embedding)
        if score is None:
            continue
        # Pinned memories get a small deliberate boost — they were explicitly
        # flagged as important, not just incidentally relevant.
        if item.pinned:
            score += 0.05
        results.append(MemoryResult(
            source_kind="memory", title=item.title or item.content[:60], content=item.content,
            score=score, meta={"module": item.module, "kind": item.kind, "id": item.id},
        ))
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]


async def _search_summaries(
    db: Session, scope: MemoryScope, query_tokens: List[str], query_embedding, top_k: int,
) -> List[MemoryResult]:
    conv_ids: List[str]
    if scope.is_persistent and scope.user_id:
        conv_ids = [c.id for c in crud.list_conversations(db, user_id=scope.user_id)]
    elif scope.anon_session_id:
        conv_ids = [c.id for c in crud.list_conversations(db, anon_session_id=scope.anon_session_id)]
    else:
        return []

    summaries = crud.list_summaries_for_conversations(db, conv_ids)
    results: List[MemoryResult] = []
    for s in summaries:
        score = _score_text(query_tokens, query_embedding, s.summary_text, s.embedding)
        if score is None:
            continue
        results.append(MemoryResult(
            source_kind="summary", title="Earlier conversation summary", content=s.summary_text,
            score=score, meta={"conversation_id": s.conversation_id, "id": s.id},
        ))
    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]


async def search_global_brain(
    db: Session,
    scope: MemoryScope,
    query: str,
    workspace_id: Optional[str] = None,
    module: Optional[str] = None,
    top_k: int = 8,
) -> List[MemoryResult]:
    """
    The Global AI Brain's unified retrieval entry point — call this instead
    of rag_service.retrieve_chunks() directly wherever a response needs
    "search everything before answering."
    """
    from api.services import rag_service

    query_tokens = tokenize(query)
    query_embedding = await get_embedding(query) if query_tokens else None

    results: List[MemoryResult] = []

    # Documents (existing RAG pipeline — automatic document indexing)
    chunks = await rag_service.retrieve_chunks(query, db, top_k=top_k)
    for c in chunks:
        results.append(MemoryResult(
            source_kind="doc", title=f"{c.filename} p.{c.page_num}", content=c.content,
            score=c.score, meta={"filename": c.filename, "page": c.page_num, "doc_id": c.doc_id},
        ))

    if query_tokens:
        results += await _search_memory_items(db, scope, query_tokens, query_embedding, module, top_k)
        results += await _search_summaries(db, scope, query_tokens, query_embedding, top_k)

        if workspace_id:
            from api.services.workspace_index import search_workspace
            results += await search_workspace(db, workspace_id, query, top_k=top_k)

    results.sort(key=lambda r: r.score, reverse=True)
    return results[:top_k]
