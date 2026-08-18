"""Research Memory & Knowledge Freshness — Phase 2B.4.

Cross-mission memory for a *logical* topic (keyed by a normalized topic
label — normalize_topic_key()), distinct from the per-mission ResearchTopic
bookkeeping row. Every mission that plans "the same" topic links its
ResearchTopic to the SAME TopicResearchMemory row (via topic_memory_id) and
accumulates into it, which is what lets the next research pass check memory
first instead of starting from scratch — see
api.services.research_agent.crawler_orchestrator.process_next_queue_item()
for where downloaded/embedded/graph-extracted activity is recorded.

Freshness is a pure function of stored timestamps/content-type — no network
calls, same "deterministic, Free-Mode-safe" discipline as Phase 2B.3's trust
computation. Refreshing a stale topic (refresh_topic()) spawns an ordinary
child ResearchMission through the exact same
api.services.research_agent.job_runner.start_mission() path
api.services.research_brain.curiosity_engine.queue_question() already uses —
there is no new scheduler or worker class for this job type; the sweep that
finds due topics (sweep_due_refreshes()) is called from the existing
MissionScheduler.tick() alongside its continuous_learning sweep.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone

from api.config import settings
from api.db import crud
from api.db.models import KnowledgeNode, ResearchTopic

log = logging.getLogger(__name__)

_MAX_VISITED_SOURCES = 200
_MAX_SEARCH_QUERIES = 50
_MAX_PROVIDERS = 20

# Direct slot -> category mapping for manufacturer-template topics —
# api.services.research_brain.planner._MANUFACTURER_TOPIC_TEMPLATE already
# names each topic slot literally, so the category is read off which slot
# the topic came from instead of guessing from free text.
_MANUFACTURER_SLOT_CATEGORY: dict[str, str] = {
    "Company History": "Manufacturer Docs",
    "Security Products": "Manufacturer Docs",
    "Baggage Systems": "Manufacturer Docs",
    "Cargo Systems": "Manufacturer Docs",
    "Backscatter": "Manufacturer Docs",
    "Dual Energy": "Manufacturer Docs",
    "Generator": "Manufacturer Docs",
    "Detector": "Manufacturer Docs",
    "Image Processing": "Manufacturer Docs",
    "Maintenance": "Manuals",
    "Calibration": "Manuals",
    "Operator Training": "Manuals",
    "Engineer Training": "Manuals",
    "Service Manuals": "Manuals",
    "Patents": "Manufacturer Docs",
    "Research Papers": "Research Papers",
    "Standards": "Standards",
    "Troubleshooting": "Manuals",
    "Fault Codes": "Manuals",
}

_STANDARDS_WORDS = {"standard", "standards", "regulation", "regulations", "compliance"}
_MANUAL_WORDS = {"manual", "manuals", "maintenance", "troubleshooting", "calibration"}
_PAPER_WORDS = {"research", "paper", "papers", "study", "studies"}

_FRESHNESS_ORDER = ["Unknown", "Fresh", "Acceptable", "Aging", "Outdated"]


def normalize_topic_key(text: str) -> str:
    """Deterministic lowercase/whitespace/punctuation-collapse key, so "the
    same" topic across separate missions maps to one TopicResearchMemory row."""
    lowered = (text or "").strip().lower()
    collapsed = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", collapsed).strip()[:256]


def classify_content_category(label: str, template: str) -> str:
    """Reuses existing signal, never invents new heuristics: manufacturer-
    template topics get their category read directly off the template slot;
    generic topics (plain DOMAIN_SEED_QUERIES strings) are keyword-classified
    against conflict_resolver.SAFETY_KEYWORDS plus a small standards/manual/
    paper keyword set — same "reuse an existing allowlist" principle as
    Phase 2B.3's _MANUFACTURER_DOMAINS."""
    if template == "manufacturer" and label in _MANUFACTURER_SLOT_CATEGORY:
        return _MANUFACTURER_SLOT_CATEGORY[label]

    from api.services.knowledge_governance.conflict_resolver import SAFETY_KEYWORDS

    lowered = label.lower()
    if any(kw in lowered for kw in SAFETY_KEYWORDS):
        return "Safety Documents"
    tokens = set(re.findall(r"[a-z]+", lowered))
    if tokens & _STANDARDS_WORDS:
        return "Standards"
    if tokens & _PAPER_WORDS:
        return "Research Papers"
    if tokens & _MANUAL_WORDS:
        return "Manuals"
    return "Manuals"  # default — most generic X-ray domain tracks are technical/engineering


def get_or_create_topic_memory(db, *, topic_key: str, content_category: str):
    existing = crud.get_topic_research_memory_by_key(db, topic_key)
    if existing:
        return existing
    return crud.create_topic_research_memory(
        db, topic_key=topic_key, content_category=content_category, freshness_status="Unknown",
    )


def get_known_source(memory, url: str) -> dict | None:
    """A previously-visited URL's stored hash/etag/last_modified, if any —
    used by the refresh path to send a conditional GET instead of a blind
    re-fetch. Not the source of truth for dedup (DocumentHash/ResearchSource
    are) — just enough to skip known-unchanged URLs."""
    for entry in (memory.visited_sources or []):
        if entry.get("url") == url:
            return entry
    return None


def _visited_entry(url: str, content_hash: str, etag: str | None, last_modified: str | None) -> dict:
    return {
        "url": url, "content_hash": content_hash, "etag": etag,
        "last_modified": last_modified, "visited_at": datetime.now(timezone.utc).isoformat(),
    }


def record_research_activity(
    db, *, topic_memory_id: str | None, url: str, content_hash: str,
    etag: str | None = None, last_modified: str | None = None,
    was_duplicate: bool = False, embedded: bool = False, graph_extracted: bool = False,
    new_facts: int = 0, updated_facts: int = 0, conflicts_found: int = 0,
    search_queries: list[str] | None = None, provider_used: str | None = None,
) -> None:
    """Called once per processed crawl item (crawler_orchestrator.py) to
    accumulate this mission's activity into the topic's cross-mission
    memory. A no-op when the topic has no linked memory (pre-2B.4 topics) —
    additive, never required for a mission to function."""
    if not topic_memory_id:
        return
    memory = crud.get_topic_research_memory(db, topic_memory_id)
    if not memory:
        return

    visited = [e for e in (memory.visited_sources or []) if e.get("url") != url]
    visited.append(_visited_entry(url, content_hash, etag, last_modified))
    visited = visited[-_MAX_VISITED_SOURCES:]

    queries = list(memory.search_queries or [])
    for q in (search_queries or []):
        if q not in queries:
            queries.append(q)
    queries = queries[-_MAX_SEARCH_QUERIES:]

    providers = list(memory.providers_used or [])
    if provider_used and provider_used not in providers:
        providers.append(provider_used)
    providers = providers[-_MAX_PROVIDERS:]

    now = datetime.now(timezone.utc)
    fields: dict = dict(
        last_research=now,
        visited_sources=visited,
        search_queries=queries,
        providers_used=providers,
        downloaded_files_count=memory.downloaded_files_count + (0 if was_duplicate else 1),
        processed_hashes_count=memory.processed_hashes_count + 1,
        new_facts_count=memory.new_facts_count + new_facts,
        updated_facts_count=memory.updated_facts_count + updated_facts,
        conflicts_found_count=memory.conflicts_found_count + conflicts_found,
    )
    if embedded:
        fields["generated_embeddings_count"] = memory.generated_embeddings_count + 1
    if graph_extracted:
        fields["extracted_graph_count"] = memory.extracted_graph_count + 1
    if new_facts or updated_facts:
        fields["last_update"] = now
        fields["knowledge_gain"] = round(memory.knowledge_gain + 0.01 * (new_facts + updated_facts), 4)

    crud.update_topic_research_memory(db, topic_memory_id, **fields)
    compute_freshness(db, topic_memory_id)


def _has_only_historical_facts(db, topic_memory_id: str) -> bool:
    """True when every KnowledgeNode linked to this topic (across all its
    mission-scoped ResearchTopic rows) has been superseded (status ==
    "historical") — i.e. there is no longer any *current* fact for this
    topic to be stale about. Historical content must never be classified
    Outdated (product requirement); a topic with zero linked nodes at all
    is NOT historical, just unresearched, so this returns False for it."""
    topic_ids = [row[0] for row in db.query(ResearchTopic.id).filter(ResearchTopic.topic_memory_id == topic_memory_id).all()]
    if not topic_ids:
        return False
    total = db.query(KnowledgeNode).filter(KnowledgeNode.research_topic_id.in_(topic_ids)).count()
    if total == 0:
        return False
    non_historical = (
        db.query(KnowledgeNode)
        .filter(KnowledgeNode.research_topic_id.in_(topic_ids), KnowledgeNode.status != "historical")
        .count()
    )
    return non_historical == 0


def compute_freshness(db, topic_memory_id: str) -> str:
    """Deterministic, per content_category, using last_update age — no
    network calls. Research Papers and historical-only topics are exempt
    from ever being classified Outdated (capped at Aging instead)."""
    memory = crud.get_topic_research_memory(db, topic_memory_id)
    if not memory:
        return "Unknown"
    if not memory.last_update:
        crud.update_topic_research_memory(db, topic_memory_id, freshness_status="Unknown", next_refresh=None)
        return "Unknown"

    thresholds = settings.freshness_thresholds_days.get(memory.content_category, (180, 365, 730))
    fresh_days, acceptable_days, aging_days = thresholds
    last_update = memory.last_update
    if last_update.tzinfo is None:
        last_update = last_update.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - last_update).total_seconds() / 86400.0

    if age_days <= fresh_days:
        status = "Fresh"
    elif age_days <= acceptable_days:
        status = "Acceptable"
    elif age_days <= aging_days:
        status = "Aging"
    else:
        status = "Outdated"

    never_outdated = memory.content_category == "Research Papers" or _has_only_historical_facts(db, topic_memory_id)
    if never_outdated and status == "Outdated":
        status = "Aging"

    next_refresh = last_update + timedelta(days=acceptable_days)
    crud.update_topic_research_memory(db, topic_memory_id, freshness_status=status, next_refresh=next_refresh)
    return status


def refresh_topic(db, topic_memory_id: str, *, priority: int = 50):
    """Spawns an ordinary child ResearchMission for this stale topic through
    the exact same api.services.research_agent.job_runner.start_mission()
    path curiosity_engine.queue_question() already uses — no new execution
    system. Forced free_mode=True: an unattended background refresh must
    never make a paid API call on its own, matching this codebase's
    Free-Mode-by-default safety posture."""
    from api.services.research_agent.job_runner import start_mission

    memory = crud.get_topic_research_memory(db, topic_memory_id)
    if not memory:
        raise ValueError(f"No TopicResearchMemory with id={topic_memory_id}")

    child = crud.create_research_mission(
        db, user_id=None, mission_text=f"Knowledge refresh: {memory.topic_key}",
        mode="quick_scan", free_mode=True, priority=priority, origin="scheduled",
    )
    start_mission(child.id)
    crud.add_research_activity(
        db, child.id, "info",
        f"Spawned as a scheduled Knowledge Refresh for topic_memory_id={topic_memory_id} "
        f"(freshness was {memory.freshness_status})",
    )
    return child


def sweep_due_refreshes(db, *, batch_size: int | None = None) -> int:
    """Bounded batch of topic refreshes per MissionScheduler.tick() call —
    same "never fan out unbounded" discipline as every other scheduler
    sweep in this codebase (Phase 2B.2.1's mission resume, 2B.3's trust
    worker). Called from job_runner.MissionScheduler.tick(), not a new
    scheduler."""
    limit = batch_size if batch_size is not None else settings.knowledge_refresh_sweep_batch_size
    due = crud.list_due_topic_memories(db, datetime.now(timezone.utc), limit)
    count = 0
    for memory in due:
        try:
            refresh_topic(db, memory.id)
            count += 1
        except Exception:
            log.exception("Knowledge refresh failed to spawn for topic_memory_id=%s", memory.id)
    return count
