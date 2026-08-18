"""
Expert Reasoning Engine (Phase 2B.7) tests.

Covers: classify_reasoning_intent()'s deterministic classification (the
spec's own chat examples, EN+AR), build_reasoning_context()'s graph
traversal (COMPARE/CAUSAL/EVIDENCE, confidence-band classification,
conflict+trust surfacing, no-match returns None), format_reasoning_context()'s
rendering, an end-to-end /api/chat/stream check that the assembled context
and rules actually reach the system_prompt handed to the LLM, and a
regression guard proving this module never interferes with the Phase 2B.6
Knowledge Router. No real network calls anywhere in this file (the resolved
provider is always replaced with a controlled fake).
"""
import os
import random
import string
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth, optional_auth
from api.db.base import SessionLocal
from api.db import crud
from api.db.models import User
from api.services.research_brain import reasoning_engine as re_engine

USER = {"id": "reasoning-engine-test-user", "username": "re-tester@example.com", "name": "RE Tester"}

_created_mission_ids: list[str] = []


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


def _word_tag() -> str:
    """Pure-alphabetic random tag — the keyword tokenizer
    (api.services.retrieval_utils.tokenize) only extracts letter-initial
    tokens, so a hex/uuid tag silently loses its uniqueness for keyword-
    matching functions (discovered while building this module). A random
    lowercase word avoids colliding with the accumulated shared test DB."""
    return "".join(random.choices(string.ascii_lowercase, k=12))


def _ensure_user() -> None:
    s = SessionLocal()
    try:
        if not s.get(User, USER["id"]):
            s.add(User(id=USER["id"], username=USER["username"], name=USER["name"]))
            s.commit()
    finally:
        s.close()


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
    """Same pin as test_knowledge_router.py — the Connector Tool Router is a
    genuine LLM-driven tool-decision loop that can otherwise intercept an
    ordinary question before it reaches the plain-text fallback."""
    async def _no_op(*args, **kwargs):
        return None, []
    monkeypatch.setattr("api.services.connector_chat_router.run_connector_tool_loop", _no_op)


class _FakeProvider:
    """Captures the system_prompt handed to it instead of making a real LLM
    call — decouples these tests from whichever real provider this dev
    environment happens to have configured."""
    provider_name = "Fake Test Provider"

    def __init__(self):
        self.captured_system_prompt: str | None = None

    async def stream_chat(self, messages, system_prompt="", max_tokens=None):
        self.captured_system_prompt = system_prompt
        for word in ["This ", "is ", "a ", "fake ", "answer."]:
            yield word


def _pin_fake_provider(monkeypatch) -> _FakeProvider:
    fake = _FakeProvider()
    monkeypatch.setattr("api.services.ai_providers.registry.provider_registry.get_for_task", lambda *a, **kw: fake)
    return fake


# ──────────────────────────────────────────────────────────
# classify_reasoning_intent — deterministic, no LLM
# ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("message,expected", [
    ("Compare LINAC and Betatron.", re_engine.COMPARE),
    ("Why is dual-energy better than single-energy?", re_engine.COMPARE),
    ("Explain the advantages of photon-counting detectors.", re_engine.TRADEOFF),
    ("Which detector technology is most promising?", re_engine.COMPARE),
    ("What evidence supports this conclusion?", re_engine.EVIDENCE),
    ("What causes false alarms in dual-energy systems?", re_engine.CAUSAL),
    ("What is Compton scattering?", None),
    ("Thanks, that's helpful.", None),
])
def test_classify_reasoning_intent_english(message, expected):
    assert re_engine.classify_reasoning_intent(message) == expected


def test_classify_reasoning_intent_arabic():
    assert re_engine.classify_reasoning_intent("قارن بين LINAC و Betatron") == re_engine.COMPARE
    assert re_engine.classify_reasoning_intent("لماذا تفشل هذه المنظومة؟") == re_engine.CAUSAL
    assert re_engine.classify_reasoning_intent("مرحبا كيف حالك") is None


# ──────────────────────────────────────────────────────────
# build_reasoning_context — graph traversal
# ──────────────────────────────────────────────────────────

def test_build_reasoning_context_compare_pulls_both_entities_and_conflict():
    db = SessionLocal()
    try:
        tag_a, tag_b = _word_tag(), _word_tag()
        node_a = crud.create_knowledge_node(
            db, node_type="Equipment", label=f"Zylophex {tag_a}",
            description="Linear accelerator", approved=True, confidence=0.85, evidence_count=3,
        )
        node_b = crud.create_knowledge_node(
            db, node_type="Equipment", label=f"Wibrathon {tag_b}",
            description="Circular electron accelerator", approved=True, confidence=0.4,
            evidence_count=1, status="experimental",
        )
        crud.create_knowledge_edge(db, from_node_id=node_a.id, to_node_id=node_b.id, relationship="connected_to", approved=True)
        crud.create_knowledge_conflict(
            db, subject_node_id=node_a.id, claim_a="Output is 6 MeV", claim_b="Output is 9 MeV",
            conflict_type="Numerical", severity="high", resolution_status="Open", confidence=0.6,
        )

        message = f"Compare Zylophex {tag_a} and Wibrathon {tag_b}"
        context = re_engine.build_reasoning_context(db, message, re_engine.COMPARE)
        assert context is not None
        all_node_ids = {n.id for e in context.entities for n in e["nodes"]}
        assert node_a.id in all_node_ids
        assert node_b.id in all_node_ids

        rendered = re_engine.format_reasoning_context(db, context)
        assert "KNOWN FACTS" in rendered
        assert "HYPOTHESES" in rendered  # node_b is experimental
        assert "RELATIONSHIPS" in rendered
        assert "OPEN CONFLICTS" in rendered
        assert "connected_to" in rendered
    finally:
        db.close()


def test_build_reasoning_context_causal_follows_edge_direction():
    db = SessionLocal()
    try:
        tag_cause, tag_effect = _word_tag(), _word_tag()
        cause = crud.create_knowledge_node(db, node_type="Cause", label=f"Voltjinx {tag_cause}", approved=True, confidence=0.8, evidence_count=2)
        effect = crud.create_knowledge_node(db, node_type="Failure", label=f"Sparkolex {tag_effect}", approved=True, confidence=0.8, evidence_count=2)
        crud.create_knowledge_edge(db, from_node_id=cause.id, to_node_id=effect.id, relationship="causes", approved=True)

        message = f"Why does Voltjinx {tag_cause} happen"
        context = re_engine.build_reasoning_context(db, message, re_engine.CAUSAL)
        assert context is not None
        rendered = re_engine.format_reasoning_context(db, context)
        assert "causes" in rendered
        assert f"Sparkolex {tag_effect}" in rendered
    finally:
        db.close()


def test_build_reasoning_context_evidence_surfaces_trust_snapshot():
    db = SessionLocal()
    try:
        tag = _word_tag()
        node = crud.create_knowledge_node(db, node_type="System", label=f"Quorvexi {tag}", approved=True, confidence=0.75, evidence_count=2)
        mission = crud.create_research_mission(db, user_id=USER["id"], mission_text=f"reasoning-engine-test-{tag}", free_mode=True)
        _created_mission_ids.append(mission.id)
        source = crud.create_research_source(
            db, mission_id=mission.id, url=f"https://example.org/{tag}", domain="example.org",
            title="Test source", publisher="Example", content_hash=None,
            quality_score=70.0, quality_label="useful", quality_reasons=[], accepted_into_kb=True, source_doi=None,
        )
        crud.create_knowledge_conflict(
            db, subject_node_id=node.id, claim_a="Value is A", claim_b="Value is B",
            source_a_id=source.id, conflict_type="Terminology", severity="medium",
            resolution_status="Open", confidence=0.5,
        )
        message = f"What evidence supports Quorvexi {tag}"
        context = re_engine.build_reasoning_context(db, message, re_engine.EVIDENCE)
        assert context is not None
        rendered = re_engine.format_reasoning_context(db, context)
        assert "OPEN CONFLICTS" in rendered
        assert "trust" in rendered.lower()
    finally:
        db.close()


def test_build_reasoning_context_returns_none_when_nothing_matches():
    db = SessionLocal()
    try:
        tag = _word_tag()
        context = re_engine.build_reasoning_context(db, f"Compare {tag}alpha and {tag}beta", re_engine.COMPARE)
        assert context is None
    finally:
        db.close()


def test_confidence_band_classification():
    db = SessionLocal()
    try:
        tag = _word_tag()
        strong = crud.create_knowledge_node(db, node_type="System", label=f"Ferroquint {tag}", approved=True, confidence=0.9, evidence_count=5)
        weak = crud.create_knowledge_node(db, node_type="System", label=f"Ferroquint {tag} weak", approved=True, confidence=0.3, evidence_count=1)
        hypo = crud.create_knowledge_node(db, node_type="System", label=f"Ferroquint {tag} hypo", approved=True, confidence=0.5, evidence_count=1, status="experimental")
        assert re_engine._confidence_band(strong) == "KNOWN FACTS"
        assert re_engine._confidence_band(weak) == "TENTATIVE FACTS"
        assert re_engine._confidence_band(hypo) == "HYPOTHESES"
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# End-to-end /api/chat/stream — reaches the real system_prompt
# ──────────────────────────────────────────────────────────

def test_compare_question_injects_reasoning_context_into_system_prompt(client, monkeypatch):
    _pin_no_connector_tool(monkeypatch)
    fake_provider = _pin_fake_provider(monkeypatch)

    db = SessionLocal()
    try:
        tag_a, tag_b = _word_tag(), _word_tag()
        node_a = crud.create_knowledge_node(
            db, node_type="Equipment", label=f"Halbrenix {tag_a}",
            description="High-energy imaging system", approved=True, confidence=0.9, evidence_count=4,
        )
        node_b = crud.create_knowledge_node(
            db, node_type="Equipment", label=f"Tornquil {tag_b}",
            description="Alternative imaging system", approved=True, confidence=0.9, evidence_count=4,
        )
        crud.create_knowledge_edge(db, from_node_id=node_a.id, to_node_id=node_b.id, relationship="connected_to", approved=True)
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    message = f"Compare Halbrenix {tag_a} and Tornquil {tag_b}"
    resp = client.post("/api/chat/stream", json={"message": message, "conversation_id": conv_id})
    assert resp.status_code == 200
    assert fake_provider.captured_system_prompt is not None
    assert "REASONING CONTEXT" in fake_provider.captured_system_prompt
    assert "never invent" in fake_provider.captured_system_prompt.lower()
    assert f"Halbrenix {tag_a}" in fake_provider.captured_system_prompt
    assert f"Tornquil {tag_b}" in fake_provider.captured_system_prompt


def test_plain_question_does_not_inject_reasoning_context(client, monkeypatch):
    _pin_no_connector_tool(monkeypatch)
    fake_provider = _pin_fake_provider(monkeypatch)

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    tag = _word_tag()
    resp = client.post(
        "/api/chat/stream",
        json={"message": f"Thanks for the update on {tag}, that's clear.", "conversation_id": conv_id},
    )
    assert resp.status_code == 200
    assert fake_provider.captured_system_prompt is not None
    assert "REASONING CONTEXT" not in fake_provider.captured_system_prompt


# ──────────────────────────────────────────────────────────
# Regression guard — Phase 2B.6 Knowledge Router is untouched
# ──────────────────────────────────────────────────────────

def test_knowledge_router_still_fires_independently_of_reasoning_engine(client, monkeypatch):
    """A question that is BOTH a reasoning question (COMPARE, entities exist)
    AND a Knowledge Router category (manufacturer_update, via a recognized
    manufacturer name) must trigger both layers independently — proves 2B.7
    adds context without altering 2B.6's own decision at all."""
    _pin_no_connector_tool(monkeypatch)
    _pin_fake_provider(monkeypatch)

    calls = {"count": 0}

    def _spy_maybe_start(*args, **kwargs):
        calls["count"] += 1
        return None  # duplicate-guard-style no-op; we only care that it was invoked

    monkeypatch.setattr("api.services.research_agent.quick_research.maybe_start_chat_live_research", _spy_maybe_start)
    # Force low confidence deterministically — the shared test-scratch DB has
    # accumulated many "Rapiscan"-mentioning fixtures across this session's
    # other test files, which could otherwise push real confidence above
    # threshold and skip the Knowledge Router entirely, making this
    # regression guard flaky for reasons unrelated to what it's testing.
    async def _force_low_confidence(*args, **kwargs):
        return {"confidence": 0.0, "topic_memory_id": None}

    monkeypatch.setattr("api.services.knowledge_router.assess_knowledge_confidence", _force_low_confidence)

    db = SessionLocal()
    try:
        tag_a, tag_b = _word_tag(), _word_tag()
        crud.create_knowledge_node(db, node_type="Equipment", label=f"Plexinor {tag_a}", approved=True, confidence=0.9, evidence_count=4)
        crud.create_knowledge_node(db, node_type="Equipment", label=f"Nebulyte {tag_b}", approved=True, confidence=0.9, evidence_count=4)
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    message = f"Any new Rapiscan products — compare Plexinor {tag_a} and Nebulyte {tag_b}?"
    resp = client.post("/api/chat/stream", json={"message": message, "conversation_id": conv_id})
    assert resp.status_code == 200
    assert calls["count"] == 1, "Knowledge Router's live-research entry point should still fire normally"
