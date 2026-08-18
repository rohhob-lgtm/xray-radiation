"""Phase 2B.6 — Intelligent Knowledge Router.

Pure decision logic for AI Chat's automatic fallback to a bounded live-
research pass through the existing Research Agent
(api.services.research_agent.quick_research) when the platform's own
RAG/graph knowledge is a poor fit for a research-worthy question. No side
effects live here — this module only reads and scores; api.routes.chat.py
decides what to do with the result.

Reuses the exact same retrieval calls api.routes.chat._build_system_prompt
already makes (retrieve_chunks/get_relevant_facts) — no second retrieval
pipeline — and the exact same keyword-classifier style already used by
api.services.document_chat_intent/api.services.research_agent_chat_intent
(deterministic, no LLM call, so classification itself adds ~0ms).
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from api.db import crud
from api.services.rag_service import retrieve_chunks
from api.services.research_brain.graph_query import get_relevant_facts
from api.services.research_brain.research_memory import (
    _PAPER_WORDS, _STANDARDS_WORDS, normalize_topic_key,
)

# Categories a low-confidence question can be classified into.
GENERAL_KNOWLEDGE = "general_knowledge"
LATEST_NEWS = "latest_news"
SCIENTIFIC_UPDATE = "scientific_update"
MANUFACTURER_UPDATE = "manufacturer_update"
STANDARD_UPDATE = "standard_update"
RESEARCH_REQUEST = "research_request"

# Only these categories are worth spending a live-research pass on — a
# conceptual/definitional question (GENERAL_KNOWLEDGE) is already answered
# well by the model's own training, and hitting the web for "what is Compton
# scattering" would be pure latency with no benefit.
LIVE_RESEARCH_CATEGORIES = {
    LATEST_NEWS, SCIENTIFIC_UPDATE, MANUFACTURER_UPDATE, STANDARD_UPDATE, RESEARCH_REQUEST,
}

_RECENCY_RE = re.compile(
    r"\b(latest|newest|new|recent(?:ly)?|update(?:d|s)?|changed?|change|current|"
    r"this\s+year|what.?s\s+new)\b|"
    r"أحدث|الأحدث|جديد(?:ة)?|آخر\s+تحديث|تغيّر|تغير|تغيرات|الحديثة",
    re.IGNORECASE,
)

_RESEARCH_REQUEST_RE = re.compile(
    r"\b(find\s+out|investigate|look\s+into|any\s+new)\b|ابحث\s+عن",
    re.IGNORECASE,
)

_FRESH_STATUSES = {"Fresh"}
_STALE_STATUSES = {"Aging", "Outdated"}


async def assess_knowledge_confidence(db: Session, message: str) -> dict:
    """How well the platform's existing knowledge already covers `message`.

    Returns {"confidence": float 0..~1.2, "topic_memory_id": str|None} —
    the topic_memory_id (if any) is the freshness record for whichever
    matched graph fact ranked highest, so callers can key a duplicate-search
    guard off the exact same topic without a second lookup.
    """
    chunks = await retrieve_chunks(message, db, top_k=3)
    graph_facts = get_relevant_facts(db, message, top_k=3)

    confidence = 0.0
    if chunks:
        confidence = max(confidence, chunks[0].score)

    topic_memory_id: str | None = None
    if graph_facts:
        top = graph_facts[0]
        fact_confidence = float(top.get("match_score", 0.0)) * float(top.get("confidence", 0.5))
        confidence = max(confidence, fact_confidence)

        research_topic_id = top.get("research_topic_id")
        if research_topic_id:
            topic = crud.get_research_topic(db, research_topic_id)
            if topic and topic.topic_memory_id:
                topic_memory_id = topic.topic_memory_id
                memory = crud.get_topic_research_memory(db, topic_memory_id)
                if memory and memory.freshness_status in _STALE_STATUSES:
                    confidence *= 0.5

    # Recency-sensitive phrasing ("what's the newest LINAC tech?") demands a
    # genuinely fresh answer — a stale or absent freshness record means the
    # existing match (if any) can't be trusted to answer a "what's new"
    # question, regardless of its raw keyword/semantic score.
    if _RECENCY_RE.search(message):
        freshness = None
        if topic_memory_id:
            memory = crud.get_topic_research_memory(db, topic_memory_id)
            freshness = memory.freshness_status if memory else None
        if freshness not in _FRESH_STATUSES:
            confidence = min(confidence, 0.2)

    return {"confidence": confidence, "topic_memory_id": topic_memory_id}


def classify_knowledge_gap(message: str) -> str:
    """Deterministic keyword classification of a low-confidence question —
    same philosophy as document_chat_intent.detect_workspace_task_intent:
    no LLM call, broad keyword families, fail toward the safer default
    (GENERAL_KNOWLEDGE, which never triggers live research)."""
    if not message:
        return GENERAL_KNOWLEDGE

    from api.services.research_brain.planner import _detect_manufacturer
    if _detect_manufacturer(message):
        return MANUFACTURER_UPDATE

    lowered = message.lower()
    tokens = set(re.findall(r"[a-z]+", lowered))

    if tokens & _STANDARDS_WORDS or "iec" in tokens or "iso" in tokens or "astm" in tokens or "ansi" in tokens:
        return STANDARD_UPDATE

    if tokens & _PAPER_WORDS:
        return SCIENTIFIC_UPDATE

    if _RESEARCH_REQUEST_RE.search(message):
        return RESEARCH_REQUEST

    if _RECENCY_RE.search(message):
        return LATEST_NEWS

    return GENERAL_KNOWLEDGE


STILL_LEARNING_NOTE = (
    "\n\n_I don't have enough verified, up-to-date information to fully answer this yet — "
    "I've started a quick live-research pass on it. I'll have a more complete, sourced answer "
    "next time you ask about this._"
)


def format_completed_note(db: Session, mission_id: str) -> str:
    """Natural-language trailer for a chat answer backed by a live-research
    pass that finished before the timeout — cites what was verified, a
    confidence estimate, sources, and when it was learned, per the Phase
    2B.6 spec's response-behaviour requirement."""
    from datetime import datetime, timezone

    sources = crud.list_research_sources(db, mission_id)
    if not sources:
        return (
            "\n\n_I ran a quick live-research check on this, but didn't find a source I could "
            "verify — the answer above is from my general knowledge only._"
        )

    accepted = [s for s in sources if s.accepted_into_kb]
    cited = accepted or sources
    lines = [f"- {s.title or s.url} ({s.domain}, quality {round(s.quality_score)}/100)" for s in cited[:3]]
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        "\n\n_Verified just now via a quick live-research check "
        f"({len(cited)} source(s), learned at {timestamp}):_\n" + "\n".join(lines)
    )


def is_recent_duplicate_search(db: Session, message: str, *, min_minutes: int) -> bool:
    """True when the same normalized topic was already researched within
    the last `min_minutes` — the "never repeat identical searches" guard,
    reusing the exact same TopicResearchMemory keying research_memory.py
    already uses for cross-mission freshness tracking."""
    from datetime import datetime, timedelta, timezone

    topic_key = normalize_topic_key(message)
    memory = crud.get_topic_research_memory_by_key(db, topic_key)
    if not memory or not memory.last_research:
        return False
    last_research = memory.last_research
    if last_research.tzinfo is None:
        last_research = last_research.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last_research < timedelta(minutes=min_minutes)
