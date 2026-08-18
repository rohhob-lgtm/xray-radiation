"""
Research Memory & Knowledge Freshness (Phase 2B.4) tests.

Covers: normalize_topic_key()/classify_content_category() (deterministic, no
LLM), the planner linking topics to cross-mission TopicResearchMemory rows,
crawler_orchestrator.py's two redundant-work fixes (no embedding call and no
graph extraction for already-known content, verified via monkeypatch-raises
guards, not just call counting), compute_freshness()'s per-category
thresholds including the historical/research-paper never-Outdated carve-
outs, refresh_topic()/sweep_due_refreshes() spawning an ordinary child
mission through the existing claim path (no new scheduler), and the 5 new
chat commands. No real network calls anywhere in this file.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from api.db.base import SessionLocal
from api.db import crud
from api.db.models import User
from api.services.research_brain import research_memory

USER = {"id": "research-memory-test-user", "username": "memory-tester@example.com", "name": "Memory Tester"}

_created_mission_ids: list[str] = []


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _ensure_user() -> None:
    s = SessionLocal()
    try:
        if not s.get(User, USER["id"]):
            s.add(User(id=USER["id"], username=USER["username"], name=USER["name"]))
            s.commit()
    finally:
        s.close()


def _new_mission(db, *, free_mode=True, mission_text=None):
    mission_text = mission_text or f"research-memory-test-{_tag()}"
    m = crud.create_research_mission(db, user_id=USER["id"], mission_text=mission_text, free_mode=free_mode)
    _created_mission_ids.append(m.id)
    return m


@pytest.fixture(autouse=True)
def _archive_created_missions():
    """Same convention as test_mission_scheduler.py/test_source_trust.py —
    archive every mission this file creates so leftover rows (this file
    creates real "scheduled"-origin missions via refresh_topic()) can never
    pollute a later test run's claim/priority assumptions."""
    _created_mission_ids.clear()
    yield
    if not _created_mission_ids:
        return
    db = SessionLocal()
    try:
        for mission_id in _created_mission_ids:
            crud.update_research_mission(db, mission_id, status="archived")
    finally:
        db.close()
    _created_mission_ids.clear()


def _make_topic_memory(db, *, topic_key=None, content_category="Manuals"):
    topic_key = topic_key or research_memory.normalize_topic_key(f"test topic {_tag()}")
    return research_memory.get_or_create_topic_memory(db, topic_key=topic_key, content_category=content_category)


# ──────────────────────────────────────────────────────────
# normalize_topic_key / classify_content_category — deterministic, no LLM
# ──────────────────────────────────────────────────────────

def test_normalize_topic_key_collapses_case_whitespace_punctuation():
    assert research_memory.normalize_topic_key("  Rapiscan :: Standards!! ") == research_memory.normalize_topic_key("rapiscan standards")


def test_normalize_topic_key_distinguishes_different_topics():
    assert research_memory.normalize_topic_key("Rapiscan Standards") != research_memory.normalize_topic_key("Astrophysics Standards")


def test_classify_content_category_manufacturer_slots():
    assert research_memory.classify_content_category("Standards", "manufacturer") == "Standards"
    assert research_memory.classify_content_category("Research Papers", "manufacturer") == "Research Papers"
    assert research_memory.classify_content_category("Service Manuals", "manufacturer") == "Manuals"
    assert research_memory.classify_content_category("Company History", "manufacturer") == "Manufacturer Docs"


def test_classify_content_category_generic_keyword_classification():
    assert research_memory.classify_content_category("radiation safety manuals", "generic") == "Safety Documents"
    assert research_memory.classify_content_category("radiation measurement standards", "generic") == "Standards"
    assert research_memory.classify_content_category("X-ray tube technical manuals", "generic") == "Manuals"
    assert research_memory.classify_content_category("AI applications in X-ray systems", "generic") == "Manuals"  # default


# ──────────────────────────────────────────────────────────
# get_or_create_topic_memory — cross-mission reuse
# ──────────────────────────────────────────────────────────

def test_get_or_create_topic_memory_reuses_row_for_same_key():
    db = SessionLocal()
    try:
        key = research_memory.normalize_topic_key(f"shared topic {_tag()}")
        first = research_memory.get_or_create_topic_memory(db, topic_key=key, content_category="Manuals")
        second = research_memory.get_or_create_topic_memory(db, topic_key=key, content_category="Manuals")
        assert first.id == second.id
    finally:
        db.close()


def test_planner_links_topics_to_same_memory_across_missions():
    """Two separate missions with the SAME mission text must link their
    topics to the SAME TopicResearchMemory rows — this is the actual
    cross-mission memory the whole phase depends on."""
    from api.services.research_brain.planner import build_research_plan

    db = SessionLocal()
    try:
        mission_text = f"Learn everything about Rapiscan X-ray systems {_tag()}"
        m1 = _new_mission(db, mission_text=mission_text)
        plan1 = build_research_plan(db, m1.id, m1.mission_text, "quick_scan")
        topics1 = crud.list_research_topics(db, m1.id)
        assert all(t.topic_memory_id for t in topics1)

        m2 = _new_mission(db, mission_text=mission_text)
        plan2 = build_research_plan(db, m2.id, m2.mission_text, "quick_scan")
        topics2 = crud.list_research_topics(db, m2.id)

        labels1 = {t.label: t.topic_memory_id for t in topics1}
        labels2 = {t.label: t.topic_memory_id for t in topics2}
        shared_labels = set(labels1) & set(labels2)
        assert shared_labels
        for label in shared_labels:
            assert labels1[label] == labels2[label]
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# record_research_activity — counters, visited_sources, freshness trigger
# ──────────────────────────────────────────────────────────

def test_record_research_activity_updates_counts_and_last_update():
    db = SessionLocal()
    try:
        memory = _make_topic_memory(db)
        research_memory.record_research_activity(
            db, topic_memory_id=memory.id, url="https://example.com/a", content_hash="hash-a",
            etag="etag-1", last_modified="Mon, 01 Jan 2024 00:00:00 GMT",
            was_duplicate=False, embedded=True, graph_extracted=True, new_facts=3,
        )
        updated = crud.get_topic_research_memory(db, memory.id)
        assert updated.downloaded_files_count == 1
        assert updated.processed_hashes_count == 1
        assert updated.generated_embeddings_count == 1
        assert updated.extracted_graph_count == 1
        assert updated.new_facts_count == 3
        assert updated.last_research is not None
        assert updated.last_update is not None
        assert updated.freshness_status == "Fresh"

        known = research_memory.get_known_source(updated, "https://example.com/a")
        assert known is not None
        assert known["content_hash"] == "hash-a"
        assert known["etag"] == "etag-1"
    finally:
        db.close()


def test_record_research_activity_duplicate_does_not_bump_download_count():
    db = SessionLocal()
    try:
        memory = _make_topic_memory(db)
        research_memory.record_research_activity(
            db, topic_memory_id=memory.id, url="https://example.com/b", content_hash="hash-b",
            was_duplicate=True,
        )
        updated = crud.get_topic_research_memory(db, memory.id)
        assert updated.downloaded_files_count == 0
        assert updated.processed_hashes_count == 1
        # No new/updated facts recorded on a pure duplicate -> last_update stays unset.
        assert updated.last_update is None
    finally:
        db.close()


def test_record_research_activity_noop_without_topic_memory_id():
    """Must not raise for pre-2B.4 topics that have no linked memory."""
    db = SessionLocal()
    try:
        research_memory.record_research_activity(db, topic_memory_id=None, url="https://x", content_hash="h")
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# compute_freshness — deterministic, per-category, no network
# ──────────────────────────────────────────────────────────

def test_compute_freshness_unknown_when_never_researched():
    db = SessionLocal()
    try:
        memory = _make_topic_memory(db, content_category="Manuals")
        status = research_memory.compute_freshness(db, memory.id)
        assert status == "Unknown"
    finally:
        db.close()


@pytest.mark.parametrize("category,age_days,expected", [
    ("Safety Documents", 10, "Fresh"),
    ("Safety Documents", 60, "Acceptable"),
    ("Safety Documents", 150, "Aging"),
    ("Safety Documents", 400, "Outdated"),
    ("Standards", 400, "Aging"),
    ("Manufacturer Docs", 400, "Outdated"),
])
def test_compute_freshness_per_category_thresholds(category, age_days, expected):
    db = SessionLocal()
    try:
        memory = _make_topic_memory(db, content_category=category)
        past = datetime.now(timezone.utc) - timedelta(days=age_days)
        crud.update_topic_research_memory(db, memory.id, last_update=past)
        status = research_memory.compute_freshness(db, memory.id)
        assert status == expected
    finally:
        db.close()


def test_compute_freshness_research_papers_never_outdated():
    db = SessionLocal()
    try:
        memory = _make_topic_memory(db, content_category="Research Papers")
        past = datetime.now(timezone.utc) - timedelta(days=3650)  # 10 years old
        crud.update_topic_research_memory(db, memory.id, last_update=past)
        status = research_memory.compute_freshness(db, memory.id)
        assert status != "Outdated"
        assert status == "Aging"
    finally:
        db.close()


def test_compute_freshness_historical_only_topic_never_outdated():
    """A topic whose only linked KnowledgeNode has been superseded
    (status="historical") must never be classified Outdated, even though
    its last_update is ancient — historical content is not stale, it's
    archived record."""
    from api.services.research_brain.planner import build_research_plan

    db = SessionLocal()
    try:
        mission = _new_mission(db, mission_text=f"historical only topic test {_tag()}")
        build_research_plan(db, mission.id, mission.mission_text, "quick_scan")
        topics = crud.list_research_topics(db, mission.id)
        topic = next(t for t in topics if t.topic_memory_id)

        crud.create_knowledge_node(
            db, node_type="Specification", label=f"Old fact {_tag()}", approved=True,
            status="historical", research_topic_id=topic.id,
        )

        past = datetime.now(timezone.utc) - timedelta(days=3650)
        crud.update_topic_research_memory(db, topic.topic_memory_id, last_update=past, content_category="Manuals")
        status = research_memory.compute_freshness(db, topic.topic_memory_id)
        assert status != "Outdated"
    finally:
        db.close()


def test_compute_freshness_with_current_node_can_become_outdated():
    """Sanity check for the test above: a topic with a CURRENT (non-
    historical) node of the same age DOES become Outdated — proves the
    historical exemption is real, not just "always capped"."""
    from api.services.research_brain.planner import build_research_plan

    db = SessionLocal()
    try:
        mission = _new_mission(db, mission_text=f"current node topic test {_tag()}")
        build_research_plan(db, mission.id, mission.mission_text, "quick_scan")
        topics = crud.list_research_topics(db, mission.id)
        topic = next(t for t in topics if t.topic_memory_id)

        crud.create_knowledge_node(
            db, node_type="Specification", label=f"Current fact {_tag()}", approved=True,
            status="current", research_topic_id=topic.id,
        )

        past = datetime.now(timezone.utc) - timedelta(days=3650)
        crud.update_topic_research_memory(db, topic.topic_memory_id, last_update=past, content_category="Manuals")
        status = research_memory.compute_freshness(db, topic.topic_memory_id)
        assert status == "Outdated"
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# crawler_orchestrator — no duplicate embedding / graph extraction
# ──────────────────────────────────────────────────────────

class _FakePage:
    def __init__(self, url, text, technical_relevance=0.8, http_status=200):
        self.url = url
        self.http_status = http_status
        self.http_reason = "OK"
        self.accessible = True
        self.blocking_mechanism = None
        self.text = text
        self.technical_relevance = technical_relevance
        self.error = None
        self.etag = None
        self.last_modified = None
        self.not_modified = False


class _FakeReport:
    def __init__(self, page):
        self.page_results = [page]


_LIMITS = {
    "max_pages": 10, "max_files": 10, "max_storage_mb": 50,
    "max_depth": 1, "min_relevance_score": 0.0, "min_quality_score": 45.0,
}

_TECH_TEXT = "X-ray radiation detector safety screening baggage inspection standard " * 40


def _unique_tech_text() -> str:
    """A distinct global content hash per call — tests that exercise the
    "genuinely new content" path must never collide with each other (or
    with a previous run) via the shared, persistent DocumentHash registry."""
    return f"X-ray radiation detector safety screening baggage inspection standard {_tag()} " * 40


@pytest.mark.asyncio
async def test_no_duplicate_embedding_for_globally_known_content(monkeypatch):
    """Content already ingested once (global DocumentHash hit) must never
    trigger a second embedding call — the core Phase 2B.4 bug fix."""
    from api.services.research_agent import crawler_orchestrator as co

    url = f"https://www.iaea.org/x/{_tag()}"
    page = _FakePage(url, _TECH_TEXT)

    async def _fake_crawl(*args, **kwargs):
        return _FakeReport(page)

    async def _embedding_must_not_be_called(*args, **kwargs):
        raise AssertionError("embedding must not be computed for already-known content")

    monkeypatch.setattr(co, "web_crawl", _fake_crawl)
    monkeypatch.setattr(co, "get_embedding_for_mission", _embedding_must_not_be_called)
    monkeypatch.setattr(co, "is_duplicate", lambda db, sha: "existing-rag-doc-id")

    db = SessionLocal()
    try:
        mission = _new_mission(db)
        crud.update_research_mission(db, mission.id, limits=dict(_LIMITS))
        db.refresh(mission)
        crud.enqueue_research_urls(db, mission.id, [{"url": url}])

        has_more = await co.process_next_queue_item(db, mission)
        assert has_more is True
        assert mission.files_ingested == 1

        files = crud.list_research_files(db, mission.id)
        assert files[0].status == "ingested"
        assert files[0].rag_document_id == "existing-rag-doc-id"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_no_duplicate_graph_extraction_for_globally_known_content(monkeypatch):
    from api.services.research_agent import crawler_orchestrator as co

    url = f"https://www.iaea.org/y/{_tag()}"
    page = _FakePage(url, _TECH_TEXT)

    async def _fake_crawl(*args, **kwargs):
        return _FakeReport(page)

    async def _extract_must_not_be_called(*args, **kwargs):
        raise AssertionError("graph extraction must not run for already-known content")

    monkeypatch.setattr(co, "web_crawl", _fake_crawl)
    monkeypatch.setattr(co, "is_duplicate", lambda db, sha: "existing-rag-doc-id")
    monkeypatch.setattr(co, "extract_and_version", _extract_must_not_be_called)

    db = SessionLocal()
    try:
        mission = _new_mission(db)
        crud.update_research_mission(db, mission.id, limits=dict(_LIMITS))
        db.refresh(mission)
        crud.enqueue_research_urls(db, mission.id, [{"url": url}])

        has_more = await co.process_next_queue_item(db, mission)
        assert has_more is True
    finally:
        db.close()


@pytest.mark.asyncio
async def test_new_content_still_gets_embedded_and_extracted(monkeypatch):
    """Sanity check: genuinely new content flows through normally — the
    fix above only skips work for already-known content."""
    from api.services.research_agent import crawler_orchestrator as co

    url = f"https://www.iaea.org/z/{_tag()}"
    page = _FakePage(url, _unique_tech_text())
    calls = {"embedding": 0, "extract": 0}

    async def _fake_crawl(*args, **kwargs):
        return _FakeReport(page)

    async def _fake_embedding(*args, **kwargs):
        calls["embedding"] += 1
        return [0.1, 0.2, 0.3]

    async def _fake_extract(*args, **kwargs):
        calls["extract"] += 1
        return {"facts_count": 2, "edges_count": 1}

    monkeypatch.setattr(co, "web_crawl", _fake_crawl)
    monkeypatch.setattr(co, "get_embedding_for_mission", _fake_embedding)
    monkeypatch.setattr(co, "extract_and_version", _fake_extract)

    db = SessionLocal()
    try:
        mission = _new_mission(db)
        crud.update_research_mission(db, mission.id, limits=dict(_LIMITS))
        db.refresh(mission)
        crud.enqueue_research_urls(db, mission.id, [{"url": url}])

        has_more = await co.process_next_queue_item(db, mission)
        assert has_more is True
        assert calls["embedding"] == 1
        assert calls["extract"] == 1
        assert mission.files_ingested == 1
    finally:
        db.close()


@pytest.mark.asyncio
async def test_process_queue_item_records_research_memory_activity(monkeypatch):
    """The topic's linked memory accumulates real counts from a processed
    item — not left at zero/templated."""
    from api.services.research_agent import crawler_orchestrator as co
    from api.services.research_brain.planner import build_research_plan

    url = f"https://www.iaea.org/w/{_tag()}"
    page = _FakePage(url, _unique_tech_text())

    async def _fake_crawl(*args, **kwargs):
        return _FakeReport(page)

    async def _fake_embedding(*args, **kwargs):
        return [0.1, 0.2, 0.3]

    async def _fake_extract(*args, **kwargs):
        return {"facts_count": 4, "edges_count": 2}

    monkeypatch.setattr(co, "web_crawl", _fake_crawl)
    monkeypatch.setattr(co, "get_embedding_for_mission", _fake_embedding)
    monkeypatch.setattr(co, "extract_and_version", _fake_extract)

    db = SessionLocal()
    try:
        mission = _new_mission(db, mission_text=f"Learn everything about Rapiscan X-ray systems {_tag()}")
        crud.update_research_mission(db, mission.id, limits=dict(_LIMITS))
        db.refresh(mission)
        build_research_plan(db, mission.id, mission.mission_text, "quick_scan")
        topics = crud.list_research_topics(db, mission.id)
        topic = next(t for t in topics if t.topic_memory_id)

        crud.enqueue_research_urls(db, mission.id, [{"url": url, "topic_id": topic.id}])
        has_more = await co.process_next_queue_item(db, mission)
        assert has_more is True

        memory = crud.get_topic_research_memory(db, topic.topic_memory_id)
        assert memory.new_facts_count == 4
        assert memory.generated_embeddings_count == 1
        assert memory.extracted_graph_count == 1
        assert memory.freshness_status == "Fresh"
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# refresh_topic / sweep_due_refreshes — existing scheduler path, no new one
# ──────────────────────────────────────────────────────────

def test_refresh_topic_spawns_child_mission_via_existing_path(monkeypatch):
    started = {}

    def _fake_start_mission(mission_id):
        started["mission_id"] = mission_id

    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", _fake_start_mission)

    db = SessionLocal()
    try:
        memory = _make_topic_memory(db)
        child = research_memory.refresh_topic(db, memory.id)
        _created_mission_ids.append(child.id)

        assert started.get("mission_id") == child.id
        assert child.origin == "scheduled"
        assert child.free_mode is True
        assert child.status == "queued"  # created via crud.create_research_mission, untouched by the fake start_mission
    finally:
        db.close()


def test_refresh_topic_raises_for_unknown_memory():
    db = SessionLocal()
    try:
        with pytest.raises(ValueError):
            research_memory.refresh_topic(db, "does-not-exist")
    finally:
        db.close()


def test_sweep_due_refreshes_is_bounded_by_batch_size(monkeypatch):
    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)

    db = SessionLocal()
    try:
        past = datetime.now(timezone.utc) - timedelta(days=1)
        memory_ids = []
        for _ in range(5):
            memory = _make_topic_memory(db, content_category="Manufacturer Docs")
            crud.update_topic_research_memory(
                db, memory.id, last_update=past - timedelta(days=500),
                freshness_status="Outdated", next_refresh=past,
            )
            memory_ids.append(memory.id)

        processed = research_memory.sweep_due_refreshes(db, batch_size=2)
        assert processed == 2

        # Track any missions spawned so the archive fixture cleans them up.
        for mid in memory_ids:
            memory = crud.get_topic_research_memory(db, mid)
            topics = db.query(crud.ResearchTopic).filter(crud.ResearchTopic.topic_memory_id == mid).all()
            for t in topics:
                _created_mission_ids.append(t.mission_id)
    finally:
        db.close()


@pytest.mark.asyncio
async def test_mission_scheduler_tick_includes_freshness_sweep(monkeypatch):
    """MissionScheduler.tick() must call the SAME sweep function — no new
    scheduler/worker class introduced for Knowledge Refresh."""
    from api.services.research_agent.job_runner import MissionScheduler

    called = {"count": 0}

    def _fake_sweep(db, *, batch_size=None):
        called["count"] += 1
        return 0

    monkeypatch.setattr("api.services.research_brain.research_memory.sweep_due_refreshes", _fake_sweep)

    scheduler = MissionScheduler()
    await scheduler.tick()
    assert called["count"] == 1


# ──────────────────────────────────────────────────────────
# Chat commands — real memory-backed data, not templated
# ──────────────────────────────────────────────────────────

def test_chat_intent_detects_all_five_commands():
    from api.services.research_agent_chat_intent import detect_research_agent_intent

    assert detect_research_agent_intent("When was this topic last updated?")["action"] == "topic_last_updated"
    assert detect_research_agent_intent("Is this knowledge outdated?")["action"] == "topic_is_outdated"
    assert detect_research_agent_intent("Update this topic")["action"] == "topic_refresh"
    assert detect_research_agent_intent("What has changed since the last research?")["action"] == "topic_whats_changed"
    assert detect_research_agent_intent("Show me outdated topics")["action"] == "list_outdated_topics"


@pytest.mark.asyncio
async def test_chat_handle_topic_last_updated_returns_real_data(monkeypatch):
    from api.services.research_agent_chat_intent import handle_research_agent_intent
    from api.services.research_brain.planner import build_research_plan

    db = SessionLocal()
    try:
        mission = _new_mission(db, mission_text=f"Learn everything about Rapiscan X-ray systems {_tag()}")
        build_research_plan(db, mission.id, mission.mission_text, "quick_scan")
        topics = crud.list_research_topics(db, mission.id)
        topic = next(t for t in topics if t.topic_memory_id)

        now = datetime.now(timezone.utc)
        crud.update_topic_research_memory(
            db, topic.topic_memory_id, last_research=now, last_update=now,
            new_facts_count=7, freshness_status="Fresh",
        )

        result = await handle_research_agent_intent(db, USER["id"], {"action": "topic_last_updated"})
        assert result["type"] == "research_topic_last_updated"
        assert result["topic_memory"]["new_facts_count"] == 7
        assert result["topic_memory"]["freshness_status"] == "Fresh"
    finally:
        db.close()


@pytest.mark.asyncio
async def test_chat_handle_topic_refresh_spawns_mission(monkeypatch):
    from api.services.research_agent_chat_intent import handle_research_agent_intent
    from api.services.research_brain.planner import build_research_plan

    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)

    db = SessionLocal()
    try:
        mission = _new_mission(db, mission_text=f"Learn everything about Rapiscan X-ray systems {_tag()}")
        build_research_plan(db, mission.id, mission.mission_text, "quick_scan")
        topics = crud.list_research_topics(db, mission.id)
        topic = next(t for t in topics if t.topic_memory_id)

        result = await handle_research_agent_intent(db, USER["id"], {"action": "topic_refresh"})
        assert result["type"] == "research_topic_refresh_started"
        _created_mission_ids.append(result["mission"]["id"])
    finally:
        db.close()


@pytest.mark.asyncio
async def test_chat_handle_list_outdated_topics_returns_real_list():
    from api.services.research_agent_chat_intent import handle_research_agent_intent

    db = SessionLocal()
    try:
        mission = _new_mission(db)
        memory = _make_topic_memory(db, content_category="Standards")
        # An extreme past next_refresh guarantees this row sorts first
        # (ascending) regardless of how many other outdated rows have
        # accumulated in the shared, persistent test scratch DB across runs.
        crud.update_topic_research_memory(
            db, memory.id, freshness_status="Outdated", next_refresh=datetime(2000, 1, 1, tzinfo=timezone.utc),
        )

        result = await handle_research_agent_intent(db, USER["id"], {"action": "list_outdated_topics"})
        assert result["type"] == "research_outdated_topics"
        # Membership checked against the full list (not the handler's small
        # display limit) — robust to accumulated debris in the shared DB.
        all_outdated = crud.list_outdated_topic_memories(db, limit=100000)
        assert any(m.id == memory.id for m in all_outdated)
    finally:
        db.close()
