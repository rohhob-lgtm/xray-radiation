"""
Autonomous Research Agent (Phase 1) tests.

Covers: mission API + pause/resume/stop lifecycle, Free Mode never calling a
paid embedding API, deterministic quality scoring, query generation, queue
dedup, and the crawl-orchestration pipeline (network calls monkeypatched —
this suite must never hit the real internet).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth
from api.db.base import SessionLocal
from api.db.models import User
from api.db import crud

USER = {"id": "research-agent-test-user", "username": "researcher@example.com", "name": "Researcher"}


def _ensure_user() -> None:
    s = SessionLocal()
    try:
        if not s.get(User, USER["id"]):
            s.add(User(id=USER["id"], username=USER["username"], name=USER["name"]))
            s.commit()
    finally:
        s.close()


@pytest.fixture
def client(monkeypatch):
    _ensure_user()
    # Never let an endpoint test spin up a real background mission (real
    # network discovery/crawl) — these tests only exercise the DB/API layer.
    # Both bindings must be patched: the routes module imported its own
    # `start_mission` name (used by POST /missions), and job_runner.resume_mission
    # calls its own module-local `start_mission` (used by POST /resume) — patching
    # only one leaves the other endpoint free to spawn a real background task.
    monkeypatch.setattr("api.routes.research_agent.start_mission", lambda mission_id: None)
    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)
    app.dependency_overrides[require_auth] = lambda: USER
    yield TestClient(app)
    app.dependency_overrides.pop(require_auth, None)


# ──────────────────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────────────────

def test_create_mission_defaults_to_free_mode(client):
    resp = client.post("/api/research-agent/missions", json={"mission_text": "X-ray tube manufacturing"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["mission"]["free_mode"] is True
    assert data["mission"]["estimated_cost_usd"] == 0.0
    assert "$0.00" in data["message"]


def test_create_mission_rejects_empty_text(client):
    resp = client.post("/api/research-agent/missions", json={"mission_text": "   "})
    assert resp.status_code == 422


def test_create_mission_rejects_invalid_mode(client):
    resp = client.post("/api/research-agent/missions", json={"mission_text": "topic", "mode": "bogus"})
    assert resp.status_code == 422


def test_pause_resume_stop_lifecycle(client):
    created = client.post("/api/research-agent/missions", json={"mission_text": "radiation portal monitors"}).json()
    mission_id = created["mission"]["id"]

    paused = client.post(f"/api/research-agent/missions/{mission_id}/pause").json()
    assert paused["mission"]["status"] == "paused"

    resumed = client.post(f"/api/research-agent/missions/{mission_id}/resume").json()
    assert resumed["mission"]["status"] == "queued"

    stopped = client.post(f"/api/research-agent/missions/{mission_id}/stop").json()
    assert stopped["mission"]["status"] == "stopped"


def test_get_mission_404_for_unknown_id(client):
    resp = client.get("/api/research-agent/missions/does-not-exist")
    assert resp.status_code == 404


def test_list_endpoints_return_empty_for_fresh_mission(client):
    created = client.post("/api/research-agent/missions", json={"mission_text": "backscatter X-ray systems"}).json()
    mission_id = created["mission"]["id"]
    for path, key in (("queue", "queue"), ("sources", "sources"), ("files", "files"), ("activity", "activity")):
        resp = client.get(f"/api/research-agent/missions/{mission_id}/{path}")
        assert resp.status_code == 200
        assert resp.json()[key] == []


def test_unauthenticated_request_is_rejected():
    resp = TestClient(app).get("/api/research-agent/missions")
    assert resp.status_code == 401


# ──────────────────────────────────────────────────────────
# query_generator
# ──────────────────────────────────────────────────────────

def test_generate_mission_queries_quick_scan_bounds():
    from api.services.research_agent.query_generator import generate_mission_queries
    topic, queries = generate_mission_queries("AI-based X-ray baggage screening", "quick_scan")
    assert topic
    assert 1 <= len(queries) <= 6


def test_generate_mission_queries_deep_research_at_least_quick_scan():
    from api.services.research_agent.query_generator import generate_mission_queries
    _, quick = generate_mission_queries("radiation portal monitors", "quick_scan")
    _, deep = generate_mission_queries("radiation portal monitors", "deep_research")
    assert len(deep) >= len(quick)


def test_generate_mission_queries_handles_short_generic_mission():
    from api.services.research_agent.query_generator import generate_mission_queries
    topic, queries = generate_mission_queries("xray", "quick_scan")
    assert topic
    assert len(queries) >= 1


# ──────────────────────────────────────────────────────────
# quality_scorer
# ──────────────────────────────────────────────────────────

def test_quality_scorer_trusted_domain_scores_higher():
    from api.services.research_agent.quality_scorer import score_source
    text = "x-ray radiation detector safety screening baggage inspection " * 30
    trusted = score_source("https://www.iaea.org/publications/safety", text, 200, None)
    untrusted = score_source("https://example.com/blog/post", text, 200, None)
    assert trusted["score"] > untrusted["score"]


def test_quality_scorer_http_error_penalized():
    from api.services.research_agent.quality_scorer import score_source
    text = "x-ray radiation detector safety screening " * 20
    ok = score_source("https://www.nist.gov/page", text, 200, None)
    broken = score_source("https://www.nist.gov/page", text, 404, None)
    assert broken["score"] < ok["score"]


def test_quality_scorer_low_content_is_review_required():
    from api.services.research_agent.quality_scorer import score_source, REVIEW_REQUIRED_LABELS
    empty = score_source("https://example.com/", "", 200, None)
    assert empty["label"] in REVIEW_REQUIRED_LABELS


# ──────────────────────────────────────────────────────────
# discovery — trusted-domain filter
# ──────────────────────────────────────────────────────────

def test_is_trusted_domain():
    from api.services.research_agent.discovery import is_trusted_domain
    assert is_trusted_domain("https://www.iaea.org/publications/x") is True
    assert is_trusted_domain("https://www.nrc.gov/reading-rm") is True
    assert is_trusted_domain("https://random-blog.example.com/post") is False


# ──────────────────────────────────────────────────────────
# ingestion — Free Mode must never call a paid embedding API
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_free_mode_never_calls_paid_embedding(monkeypatch):
    from api.services.research_agent import ingestion

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("Paid OpenAI embedding must never be called when Free Mode is on")

    monkeypatch.setattr("api.services.embedding_service.get_embedding", _fail_if_called)

    async def _no_ollama(*args, **kwargs):
        return None

    monkeypatch.setattr(ingestion, "_local_ollama_embedding", _no_ollama)

    result = await ingestion.get_embedding_for_mission("some text", free_mode=True)
    assert result is None  # gracefully degrades to keyword-only retrieval, no exception


@pytest.mark.asyncio
async def test_non_free_mode_uses_paid_embedding(monkeypatch):
    from api.services.research_agent import ingestion

    called = {}

    async def _fake_get_embedding(text):
        called["yes"] = True
        return [0.1, 0.2]

    monkeypatch.setattr("api.services.embedding_service.get_embedding", _fake_get_embedding)

    result = await ingestion.get_embedding_for_mission("some text", free_mode=False)
    assert called.get("yes") is True
    assert result == [0.1, 0.2]


def test_ingest_short_content_is_skipped():
    from api.services.research_agent.ingestion import ingest_research_content
    s = SessionLocal()
    try:
        doc_id, was_duplicate = ingest_research_content(s, filename="tiny.txt", text="too short", embedding=None)
        assert doc_id is None
        assert was_duplicate is False
    finally:
        s.close()


def test_ingest_dedupes_identical_content():
    from api.services.research_agent.ingestion import ingest_research_content
    import uuid
    s = SessionLocal()
    try:
        # Unique per test run (not just per test) — this suite runs against a
        # persistent scratch DB across invocations, so fixed text would only
        # look "new" the very first time the suite ever ran.
        text = f"Radiation portal monitors detect gamma and neutron sources at border crossings. Run {uuid.uuid4()}. " * 5
        first_id, first_dup = ingest_research_content(s, filename="a.txt", text=text, embedding=None)
        second_id, second_dup = ingest_research_content(s, filename="b.txt", text=text, embedding=None)
        assert first_id is not None
        assert first_dup is False
        assert second_id == first_id
        assert second_dup is True
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# CRUD — queue dedup
# ──────────────────────────────────────────────────────────

def test_enqueue_research_urls_dedupes():
    s = SessionLocal()
    try:
        mission = crud.create_research_mission(s, user_id=USER["id"], mission_text="dedup test topic")
        first = crud.enqueue_research_urls(s, mission.id, [
            {"url": "https://example.com/a", "discovered_via": "q1"},
            {"url": "https://example.com/b", "discovered_via": "q1"},
        ])
        assert len(first) == 2

        second = crud.enqueue_research_urls(s, mission.id, [
            {"url": "https://example.com/a", "discovered_via": "q2"},  # duplicate
            {"url": "https://example.com/c", "discovered_via": "q2"},  # new
        ])
        assert len(second) == 1
        assert second[0].url == "https://example.com/c"

        all_items = crud.list_research_queue_items(s, mission.id)
        assert len(all_items) == 3
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# crawler_orchestrator — full per-item pipeline, network mocked
# ──────────────────────────────────────────────────────────

class _FakePage:
    def __init__(self, url: str, text: str, technical_relevance: float = 0.5, http_status: int = 200):
        self.url = url
        self.http_status = http_status
        self.http_reason = "OK"
        self.accessible = True
        self.blocking_mechanism = None
        self.text = text
        self.technical_relevance = technical_relevance
        self.error = None


class _FakeReport:
    def __init__(self, page):
        self.page_results = [page]


_DEFAULT_TEST_LIMITS = {
    "max_pages": 10, "max_files": 10, "max_storage_mb": 50,
    "max_depth": 1, "min_relevance_score": 0.0, "min_quality_score": 45.0,
}


@pytest.mark.asyncio
async def test_process_next_queue_item_ingests_high_quality_source(monkeypatch):
    from api.services.research_agent import crawler_orchestrator as co

    url = "https://www.iaea.org/safety/x-ray-portal-monitor"
    page = _FakePage(url, "X-ray radiation detector safety screening baggage inspection standard " * 40, 0.8)

    async def _fake_crawl(*args, **kwargs):
        return _FakeReport(page)

    async def _fake_embedding(*args, **kwargs):
        return None  # keyword-only path — no network, no cost

    monkeypatch.setattr(co, "web_crawl", _fake_crawl)
    monkeypatch.setattr(co, "get_embedding_for_mission", _fake_embedding)

    s = SessionLocal()
    try:
        mission = crud.create_research_mission(
            s, user_id=USER["id"], mission_text="iaea safety", free_mode=True, limits=dict(_DEFAULT_TEST_LIMITS),
        )
        crud.enqueue_research_urls(s, mission.id, [{"url": url}])

        has_more = await co.process_next_queue_item(s, mission)
        assert has_more is True
        assert mission.pages_processed == 1
        assert mission.files_ingested == 1
        assert mission.files_rejected == 0

        sources = crud.list_research_sources(s, mission.id)
        assert len(sources) == 1
        assert sources[0].accepted_into_kb is True

        files = crud.list_research_files(s, mission.id)
        assert files[0].status == "ingested"
        assert files[0].rag_document_id is not None
    finally:
        s.close()


@pytest.mark.asyncio
async def test_process_next_queue_item_holds_low_quality_for_review(monkeypatch):
    from api.services.research_agent import crawler_orchestrator as co

    url = "https://example.com/generic-blog-post"
    page = _FakePage(url, "Welcome to our blog about cats and gardening tips.", 0.0)

    async def _fake_crawl(*args, **kwargs):
        return _FakeReport(page)

    monkeypatch.setattr(co, "web_crawl", _fake_crawl)

    s = SessionLocal()
    try:
        mission = crud.create_research_mission(
            s, user_id=USER["id"], mission_text="unrelated topic", free_mode=True, limits=dict(_DEFAULT_TEST_LIMITS),
        )
        crud.enqueue_research_urls(s, mission.id, [{"url": url}])

        has_more = await co.process_next_queue_item(s, mission)
        assert has_more is True
        assert mission.files_ingested == 0
        assert mission.files_rejected == 1

        sources = crud.list_research_sources(s, mission.id)
        assert sources[0].accepted_into_kb is False

        files = crud.list_research_files(s, mission.id)
        assert files[0].status == "rejected"
        assert files[0].rag_document_id is None
    finally:
        s.close()


@pytest.mark.asyncio
async def test_process_next_queue_item_stops_when_page_limit_reached():
    from api.services.research_agent import crawler_orchestrator as co

    s = SessionLocal()
    try:
        limits = dict(_DEFAULT_TEST_LIMITS)
        limits["max_pages"] = 0
        mission = crud.create_research_mission(
            s, user_id=USER["id"], mission_text="limit test", free_mode=True, limits=limits,
        )
        crud.enqueue_research_urls(s, mission.id, [{"url": "https://example.com/a"}])

        has_more = await co.process_next_queue_item(s, mission)
        assert has_more is False
    finally:
        s.close()


@pytest.mark.asyncio
async def test_process_next_queue_item_empty_queue_returns_false():
    from api.services.research_agent import crawler_orchestrator as co

    s = SessionLocal()
    try:
        mission = crud.create_research_mission(s, user_id=USER["id"], mission_text="empty queue test")
        has_more = await co.process_next_queue_item(s, mission)
        assert has_more is False
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# Chat natural-language command detection
# ──────────────────────────────────────────────────────────

def test_chat_intent_start_english():
    from api.services.research_agent_chat_intent import detect_research_agent_intent
    intent = detect_research_agent_intent("research and learn about dual-energy X-ray systems")
    assert intent == {"action": "start", "mission_text": "dual-energy X-ray systems"}


def test_chat_intent_start_arabic():
    from api.services.research_agent_chat_intent import detect_research_agent_intent
    intent = detect_research_agent_intent("ابحث وتعلم كل ما يتعلق بأنظمة X-Ray الأمنية")
    assert intent is not None
    assert intent["action"] == "start"
    assert intent["mission_text"]


def test_chat_intent_stop():
    from api.services.research_agent_chat_intent import detect_research_agent_intent
    assert detect_research_agent_intent("stop the current research job") == {"action": "stop"}
    assert detect_research_agent_intent("أوقف مهمة البحث الحالية") == {"action": "stop"}


def test_chat_intent_resume():
    from api.services.research_agent_chat_intent import detect_research_agent_intent
    assert detect_research_agent_intent("resume the research") == {"action": "resume"}
    assert detect_research_agent_intent("استأنف التعلّم") == {"action": "resume"}


def test_chat_intent_show_sources():
    from api.services.research_agent_chat_intent import detect_research_agent_intent
    assert detect_research_agent_intent("show me the sources") == {"action": "list_sources"}


def test_chat_intent_none_for_unrelated_message():
    from api.services.research_agent_chat_intent import detect_research_agent_intent
    assert detect_research_agent_intent("what is the capital of France") is None


@pytest.mark.asyncio
async def test_chat_intent_start_creates_free_mode_mission(monkeypatch):
    from api.services.research_agent_chat_intent import handle_research_agent_intent
    # Chat must never spin up a real background mission (real network calls)
    # as a side effect of a unit test.
    monkeypatch.setattr("api.services.research_agent_chat_intent.start_mission", lambda mission_id: None)
    s = SessionLocal()
    try:
        payload = await handle_research_agent_intent(
            s, USER["id"], {"action": "start", "mission_text": "gamma and neutron detection"},
        )
        assert payload["type"] == "research_mission_started"
        assert payload["mission"]["free_mode"] is True
    finally:
        s.close()


@pytest.mark.asyncio
async def test_chat_intent_sources_with_no_missions_is_a_clear_error():
    from api.services.research_agent_chat_intent import handle_research_agent_intent
    s = SessionLocal()
    try:
        payload = await handle_research_agent_intent(
            s, "user-with-no-missions-ever", {"action": "list_sources"},
        )
        assert payload["type"] == "research_error"
    finally:
        s.close()
