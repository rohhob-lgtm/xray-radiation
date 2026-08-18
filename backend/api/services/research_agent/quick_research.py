"""Phase 2B.6 — bounded, chat-triggered live research.

Deliberately NOT api.services.research_agent.job_runner.run_mission(): that
function builds a full multi-topic tree via
api.services.research_brain.planner.build_research_plan() (several topics,
each with its own query set) and loops coverage-target rounds — the right
shape for "research and learn everything about X", far too heavy for
answering one chat question. This module reuses the exact same building
blocks (discover_sources / enqueue_research_urls / process_next_queue_item /
TopicResearchMemory) around a single, tightly-bounded topic instead of
building any new search/crawl/extraction logic.
"""
from __future__ import annotations

import logging

from api.db import crud
from api.db.base import SessionLocal
from api.services.research_agent.discovery import discover_sources
from api.services.research_agent.crawler_orchestrator import process_next_queue_item
from api.services.research_agent.query_generator import generate_mission_queries
from api.services.research_brain import research_memory

log = logging.getLogger(__name__)

_DOMAIN_LABEL = "X-ray, radiation, and security-screening research"

_CATEGORY_CONTENT_CATEGORY = {
    "manufacturer_update": "Manufacturer Docs",
    "standard_update": "Standards",
    "scientific_update": "Research Papers",
    "latest_news": "Manuals",
    "research_request": "Manuals",
}


def maybe_start_chat_live_research(db, user_id: str, message: str, category: str):
    """Create one bounded ResearchMission + ResearchTopic for `message`, or
    return None if the same topic was researched too recently (duplicate-
    search guard — "never repeat identical searches").

    Returns (mission, topic, topic_memory) on success. Synchronous DB work
    only — the caller launches run_chat_quick_research() as a background task.
    """
    from api.config import settings
    from api.services.knowledge_router import is_recent_duplicate_search
    from api.services.research_brain.research_memory import normalize_topic_key
    from api.services.research_brain.planner import _detect_manufacturer

    if is_recent_duplicate_search(db, message, min_minutes=settings.knowledge_router_min_reresearch_minutes):
        return None

    max_sources = settings.knowledge_router_max_sources
    mission = crud.create_research_mission(
        db, user_id=user_id, mission_text=f"[chat-live] {message[:200]}", mode="quick_scan",
        languages=["en"], content_types=["web_pages"],
        # Forced True — same "an unattended background job never spends real
        # money on its own" rule research_memory.refresh_topic() already
        # applies. This mission is triggered automatically, not by an
        # explicit user research command, so it gets the same safety posture.
        free_mode=True,
        limits={
            "max_pages": max_sources, "max_files": max_sources, "max_storage_mb": 20,
            "max_depth": 0, "min_relevance_score": 0.1, "min_quality_score": 40.0,
        },
        priority=200, origin="chat_live_research",
    )

    manufacturer = _detect_manufacturer(message)
    plan = crud.create_research_plan(
        db, mission_id=mission.id,
        normalized_understanding={
            "normalized_topic": message[:256], "template": "chat_quick", "matched_manufacturer": manufacturer,
        },
    )

    topic_key = normalize_topic_key(message)
    content_category = _CATEGORY_CONTENT_CATEGORY.get(category, "Manuals")
    topic_memory = research_memory.get_or_create_topic_memory(db, topic_key=topic_key, content_category=content_category)

    topic = crud.create_research_topic(
        db, plan_id=plan.id, mission_id=mission.id, label=message[:256], rank=1.0,
        status="researching", topic_memory_id=topic_memory.id,
        search_strategy={"queries": [message]},
    )

    crud.add_research_activity(
        db, mission.id, "info", f"Chat-triggered live research started (category={category}): {message[:200]}",
    )
    return mission, topic, topic_memory


async def run_chat_quick_research(mission_id: str, topic_id: str, max_sources: int) -> None:
    """Discover a handful of sources for the single topic created by
    maybe_start_chat_live_research(), then crawl/ingest/graph-extract up to
    max_sources of them — opens its own DB session (job_runner.run_mission's
    same pattern) because this may keep running in the background after the
    chat request that launched it has already returned."""
    db = SessionLocal()
    try:
        mission = crud.get_research_mission(db, mission_id)
        topic = crud.get_research_topic(db, topic_id)
        if not mission or not topic:
            return

        queries = (topic.search_strategy or {}).get("queries") or [topic.label]
        _, ranked_queries = generate_mission_queries(topic.label, mission.mode)
        all_queries = (queries + ranked_queries)[:2]

        discovered = await discover_sources(all_queries, _DOMAIN_LABEL, mission.content_types)
        discovered = discovered[:max_sources]
        for item in discovered:
            item["topic_id"] = topic.id
        crud.enqueue_research_urls(db, mission.id, discovered)
        crud.update_research_topic(db, topic.id, status="researching")

        for _ in range(max_sources):
            db.refresh(mission)
            has_more = await process_next_queue_item(db, mission)
            if not has_more:
                break

        crud.update_research_topic(db, topic.id, status="covered")
        crud.update_research_mission(db, mission.id, status="completed", current_phase="completed")
        crud.add_research_activity(db, mission.id, "info", "Chat-triggered live research completed")
    except Exception as exc:
        log.exception("Chat live research failed for mission %s", mission_id)
        try:
            crud.update_research_mission(db, mission_id, status="failed", last_error=str(exc))
        except Exception:
            pass
    finally:
        db.close()
