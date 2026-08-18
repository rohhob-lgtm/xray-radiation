"""
Intelligent Knowledge Router (Phase 2B.6) tests.

Covers: assess_knowledge_confidence()'s high/low-confidence scoring,
classify_knowledge_gap()'s deterministic classification (EN+AR, including
the spec's own example questions), the duplicate-search guard, end-to-end
/api/chat/stream behavior when live research completes within the timeout
vs. exceeds it (and that a timeout does NOT cancel the background task —
asyncio.shield's whole point), and a regression guard proving a
high-confidence question never touches the Research Agent at all. No real
network calls anywhere in this file.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import asyncio
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth, optional_auth
from api.db.base import SessionLocal
from api.db import crud
from api.db.models import User
from api.services import knowledge_router as kr

USER = {"id": "knowledge-router-test-user", "username": "kr-tester@example.com", "name": "KR Tester"}

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


@pytest.fixture(autouse=True)
def _archive_created_missions():
    """Same convention as test_research_memory.py/test_source_trust.py."""
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


@pytest.fixture
def client():
    _ensure_user()
    app.dependency_overrides[require_auth] = lambda: USER
    app.dependency_overrides[optional_auth] = lambda: USER
    yield TestClient(app)
    app.dependency_overrides.pop(require_auth, None)
    app.dependency_overrides.pop(optional_auth, None)


def _make_conversation(db):
    return crud.create_conversation(db, user_id=USER["id"], anon_session_id=None)


def _pin_no_connector_tool(monkeypatch):
    """The Connector Tool Router (connector_chat_router.run_connector_tool_loop)
    is a genuine LLM-driven tool-decision loop, deliberately not keyword-gated
    — with a real provider configured in this environment it can and does
    decide (unpredictably) that an ordinary question warrants a connector
    tool call, which would intercept the request before it ever reaches the
    plain-text fallback branch this file is testing. Pinned to its documented
    no-op return so these tests exercise the Knowledge Router deterministically."""
    async def _no_op(*args, **kwargs):
        return None, []
    monkeypatch.setattr("api.services.connector_chat_router.run_connector_tool_loop", _no_op)


# ──────────────────────────────────────────────────────────
# classify_knowledge_gap — deterministic, no LLM
# ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("message,expected", [
    ("What is the newest LINAC technology?", kr.LATEST_NEWS),
    ("What changed in IEC standards?", kr.STANDARD_UPDATE),
    ("Any new Rapiscan products?", kr.MANUFACTURER_UPDATE),
    ("Latest research on photon counting detectors.", kr.SCIENTIFIC_UPDATE),
    ("What is Compton scattering?", kr.GENERAL_KNOWLEDGE),
    ("Thanks, that's helpful.", kr.GENERAL_KNOWLEDGE),
])
def test_classify_knowledge_gap_english(message, expected):
    assert kr.classify_knowledge_gap(message) == expected


def test_classify_knowledge_gap_arabic():
    assert kr.classify_knowledge_gap("ما الجديد في معايير IEC؟") == kr.STANDARD_UPDATE
    assert kr.classify_knowledge_gap("ما هو أحدث تقنيات الفحص؟") == kr.LATEST_NEWS
    assert kr.classify_knowledge_gap("مرحبا كيف حالك") == kr.GENERAL_KNOWLEDGE


def test_general_knowledge_never_triggers_live_research():
    assert kr.GENERAL_KNOWLEDGE not in kr.LIVE_RESEARCH_CATEGORIES
    for cat in (kr.LATEST_NEWS, kr.SCIENTIFIC_UPDATE, kr.MANUFACTURER_UPDATE, kr.STANDARD_UPDATE, kr.RESEARCH_REQUEST):
        assert cat in kr.LIVE_RESEARCH_CATEGORIES


# ──────────────────────────────────────────────────────────
# assess_knowledge_confidence — reuses retrieve_chunks/get_relevant_facts
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_assess_knowledge_confidence_high_when_matching_document_exists():
    db = SessionLocal()
    try:
        tag = _tag()
        phrase = f"Zephyrion-{tag} dual-energy backscatter calibration procedure"
        crud.create_rag_document(
            db, user_id=USER["id"], filename=f"manual-{tag}.txt",
            document_type="manual", content=phrase * 3,
        )
        result = await kr.assess_knowledge_confidence(db, phrase)
        assert result["confidence"] >= 0.35
    finally:
        db.close()


@pytest.mark.asyncio
async def test_assess_knowledge_confidence_low_when_nothing_matches():
    db = SessionLocal()
    try:
        tag = _tag()
        result = await kr.assess_knowledge_confidence(db, f"totally-unindexed-topic-{tag}")
        assert result["confidence"] < 0.35
        assert result["topic_memory_id"] is None
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# Duplicate-search guard
# ──────────────────────────────────────────────────────────

def test_duplicate_search_guard_blocks_recent_repeat():
    from api.services.research_agent.quick_research import maybe_start_chat_live_research

    db = SessionLocal()
    try:
        tag = _tag()
        message = f"Any new Rapiscan-{tag} products?"
        first = maybe_start_chat_live_research(db, USER["id"], message, kr.MANUFACTURER_UPDATE)
        assert first is not None
        mission, topic, topic_memory = first
        _created_mission_ids.append(mission.id)
        # Simulate the background research having already run once.
        crud.update_topic_research_memory(db, topic_memory.id, last_research=__import__("datetime").datetime.now(__import__("datetime").timezone.utc))

        second = maybe_start_chat_live_research(db, USER["id"], message, kr.MANUFACTURER_UPDATE)
        assert second is None
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# End-to-end /api/chat/stream — completed vs. timed-out live research
# ──────────────────────────────────────────────────────────

def test_high_confidence_question_never_touches_research_agent(client, monkeypatch):
    """Regression guard: an ordinary, well-covered question must not create
    any ResearchMission — same defensive style as the sticky-workspace-id
    test in test_chat_intent_router.py."""
    db = SessionLocal()
    try:
        tag = _tag()
        phrase = f"Xylonite-{tag} sensor housing torque specification is 12 Nm"
        crud.create_rag_document(
            db, user_id=USER["id"], filename=f"spec-{tag}.txt", document_type="manual", content=phrase * 3,
        )
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    _pin_no_connector_tool(monkeypatch)

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("maybe_start_chat_live_research must not be called for a high-confidence question")

    monkeypatch.setattr("api.services.research_agent.quick_research.maybe_start_chat_live_research", _fail_if_called)

    resp = client.post(
        "/api/chat/stream",
        json={"message": phrase, "conversation_id": conv_id},
    )
    assert resp.status_code == 200


def test_live_research_completes_within_timeout_adds_note_and_stores_knowledge(client, monkeypatch):
    from api import config as config_module

    _pin_no_connector_tool(monkeypatch)
    monkeypatch.setattr(config_module.settings, "knowledge_router_timeout_seconds", 3.0)

    created_source_ids: list[str] = []

    async def _fake_run_chat_quick_research(mission_id, topic_id, max_sources):
        db = SessionLocal()
        try:
            source = crud.create_research_source(
                db, mission_id=mission_id, url="https://example-standards.org/doc",
                domain="example-standards.org", title="Fake standards update",
                publisher="Example Standards Org", content_hash=None,
                quality_score=80.0, quality_label="useful", quality_reasons=["test"],
                accepted_into_kb=True, source_doi=None,
            )
            created_source_ids.append(source.id)
            crud.update_research_mission(db, mission_id, status="completed", current_phase="completed")
        finally:
            db.close()

    monkeypatch.setattr(
        "api.services.research_agent.quick_research.run_chat_quick_research", _fake_run_chat_quick_research,
    )

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    tag = _tag()
    message = f"What changed in IEC-{tag} standards?"
    resp = client.post("/api/chat/stream", json={"message": message, "conversation_id": conv_id})
    assert resp.status_code == 200
    # The trailer is streamed word-by-word as separate SSE "chunk" events
    # (same convention as every other appended note in chat.py), so a
    # contiguous phrase never appears verbatim in resp.text — check for a
    # single-token marker plus the cited source's domain instead.
    assert '"live-research' in resp.text
    assert "example-standards.org" in resp.text
    assert created_source_ids, "the fake research function should have created a ResearchSource"


def test_live_research_timeout_tells_user_and_keeps_task_running(client, monkeypatch):
    from api import config as config_module

    _pin_no_connector_tool(monkeypatch)
    monkeypatch.setattr(config_module.settings, "knowledge_router_timeout_seconds", 0.05)

    finished = {"value": False}

    async def _slow_fake_run_chat_quick_research(mission_id, topic_id, max_sources):
        await asyncio.sleep(0.3)
        finished["value"] = True

    monkeypatch.setattr(
        "api.services.research_agent.quick_research.run_chat_quick_research", _slow_fake_run_chat_quick_research,
    )

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    tag = _tag()
    message = f"Any new Rapiscan-{tag} products?"
    resp = client.post("/api/chat/stream", json={"message": message, "conversation_id": conv_id})
    assert resp.status_code == 200
    assert '"live-research' in resp.text

    # asyncio.shield() means the timeout must NOT have cancelled the task —
    # give it real wall-clock time to finish in the background and confirm.
    time.sleep(0.6)
    assert finished["value"] is True
