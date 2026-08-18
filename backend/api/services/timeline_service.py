"""
Cognitive Layer (Phase 2): Project Timeline.

A read layer over MemoryItem, not a new event store — MemoryItem.kind
already accepts arbitrary strings, so "project_event" needed no schema
change. Phase 1 defined memory_service.record_project_event() but never
wired a real caller; this module is that real wiring plus the "what
changed?" query.
"""
from __future__ import annotations
from typing import List, Optional

from sqlalchemy.orm import Session

from api.db import crud
from api.services import memory_service
from api.services.identity import MemoryScope
from api.services.retrieval_utils import MemoryResult
from api.services.graph_service import Entity, link as graph_link

_TIMELINE_KINDS = ["project_event", "decision"]


async def record_event(
    db: Session,
    scope: MemoryScope,
    module: str,
    event_type: str,
    title: str,
    description: str = "",
    source_ref: Optional[str] = None,
    related_entity: Optional[Entity] = None,
) -> Optional["crud.MemoryItem"]:
    """
    Record one timeline entry (module completion, task transition, pin,
    decision, ...). No-op for non-persistent (anonymous) scopes, same
    gating as the rest of the Global AI Brain.

    When related_entity is given (e.g. ("task", task_id)), the event is
    also linked into the Knowledge Graph — one write feeds both systems.
    """
    item = await memory_service.record_project_event(
        db, scope, module, title=f"[{event_type}] {title}", content=description or title, source_ref=source_ref,
    )
    if item and related_entity:
        await graph_link(
            db, scope, ("decision", item.id), related_entity, relationship="discussed_in",
            from_label=title, module=module,
        )
    return item


def get_timeline(
    db: Session, scope: MemoryScope, module: Optional[str] = None, since=None, limit: int = 50,
) -> List[dict]:
    if not scope.is_persistent or not scope.user_id:
        return []
    items = crud.list_memory_items_by_kinds(db, scope.user_id, _TIMELINE_KINDS, module=module, since=since, limit=limit)
    return [crud.memory_item_to_dict(i) for i in items]


async def answer_what_changed(db: Session, scope: MemoryScope, query: str, since=None) -> str:
    """One LLM call synthesizing recent timeline entries into a "what
    changed" narrative — same one-call-not-a-classifier pattern as
    memory_service.summarize_conversation_if_due()."""
    entries = get_timeline(db, scope, since=since, limit=50)
    if not entries:
        return "No recorded project events yet."

    from api.services.ai_providers.registry import provider_registry
    provider = provider_registry.get_active()
    if not provider:
        return "No AI provider available to summarize the timeline."

    transcript = "\n".join(f"- [{e['created_at']}] {e['title']}: {e['content']}" for e in reversed(entries))
    return await provider.chat(
        [{"role": "user", "content": f"Question: {query}\n\nTimeline entries (oldest first):\n{transcript[:12000]}"}],
        system_prompt=(
            "You are summarizing a project's recent history for a returning team member. "
            "Answer the question using only the timeline entries provided, in a few concise "
            "bullet points ordered chronologically. If the entries don't answer the question, say so."
        ),
    )


def timeline_search_results(entries: List[dict]) -> List[MemoryResult]:
    """Adapt raw timeline dicts into MemoryResult for merging into
    memory_service.search_global_brain (source_kind="timeline")."""
    return [
        MemoryResult(
            source_kind="timeline", title=e["title"], content=e["content"], score=0.0,
            meta={"id": e["id"], "module": e["module"]},
        )
        for e in entries
    ]
