"""
Curiosity Engine (Phase 2B.1) tests.

Covers: gap-driven and term-driven question generation, settings gating
(auto-queue on/off, priority/knowledge-gain thresholds, per-mission and
daily limits enforced against real DB rows), the queue-question path
spawning a real child mission through the ordinary research_agent path, and
the read/approve/reject API + chat command. `start_mission` is monkeypatched
throughout to prevent any test from spawning a real background mission with
real network calls — same convention as tests/test_research_agent.py.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth
from api.db.base import SessionLocal
from api.db.models import User
from api.db import crud

USER = {"id": "curiosity-test-user", "username": "curiosity@example.com", "name": "Curiosity Tester"}


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
    monkeypatch.setattr("api.routes.research_agent.start_mission", lambda mission_id: None)
    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)
    app.dependency_overrides[require_auth] = lambda: USER
    yield TestClient(app)
    app.dependency_overrides.pop(require_auth, None)


def _generous_daily_limit(db) -> int:
    """A daily_curiosity_limit value guaranteed not to already be exhausted —
    for tests that aren't specifically testing the daily-limit gate itself.
    daily_curiosity_limit is a deliberately platform-wide throttle backed by
    real DB rows (crud.count_curiosity_spawned_missions_since), so it
    persists across this suite's repeated runs against a shared scratch DB; a
    fixed constant here would eventually be exceeded by accumulated runs."""
    from datetime import datetime, timezone
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    return crud.count_curiosity_spawned_missions_since(db, today_start) + 100


def _new_mission(db, **kwargs):
    kwargs.setdefault("user_id", USER["id"])
    kwargs.setdefault("mission_text", "test mission")
    # curiosity_settings isn't one of create_research_mission()'s explicit
    # kwargs (it predates Phase 2B.1) — set it via update_research_mission()
    # right after creation instead.
    curiosity_settings = kwargs.pop("curiosity_settings", None)
    mission = crud.create_research_mission(db, **kwargs)
    if curiosity_settings is not None:
        mission = crud.update_research_mission(db, mission.id, curiosity_settings=curiosity_settings)
    return mission


# ──────────────────────────────────────────────────────────
# Gap-driven generation
# ──────────────────────────────────────────────────────────

def test_gap_driven_questions_from_low_coverage_topic(monkeypatch):
    from api.services.research_brain.planner import build_research_plan
    from api.services.research_brain.curiosity_engine import _generate_gap_driven_questions

    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="backscatter imaging systems")
        build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        # No evidence recorded -> every topic sits at 0% coverage -> all qualify as gaps.

        questions = _generate_gap_driven_questions(s, mission)
        assert len(questions) > 0
        assert all(q.category in ("Missing", "Weakly Covered") for q in questions)
        assert all(q.mission_id == mission.id for q in questions)
        assert all(q.related_topic_id is not None for q in questions)
        assert all(q.status == "Suggested" for q in questions)
    finally:
        s.close()


def test_gap_driven_questions_skip_well_covered_topics():
    from api.services.research_brain.planner import build_research_plan
    from api.services.research_brain.knowledge_versioning import record_node_evidence
    from api.services.research_brain.gap_detector import compute_coverage
    from api.services.research_brain.curiosity_engine import _generate_gap_driven_questions

    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="radiation portal monitors")
        build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        topics = crud.list_research_topics(s, mission.id)
        covered_topic = topics[0]
        crud.update_research_topic(s, covered_topic.id, estimates={**covered_topic.estimates, "expected_sources": 1})

        node = crud.create_knowledge_node(s, node_type="System", label=f"Fact {uuid.uuid4()}", approved=True)
        record_node_evidence(s, node.id, research_source_id="src-1", topic_id=covered_topic.id)
        compute_coverage(s, mission.id)

        questions = _generate_gap_driven_questions(s, mission)
        topic_ids_with_questions = {q.related_topic_id for q in questions}
        assert covered_topic.id not in topic_ids_with_questions
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# Term-driven generation ("Mentioned but Unexplained")
# ──────────────────────────────────────────────────────────

def test_term_driven_questions_detect_unexplained_phrases():
    from api.services.research_brain.curiosity_engine import _generate_term_driven_questions
    from api.db.crud import create_rag_document

    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="cargo inspection")
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/x", domain="example.com")
        doc = create_rag_document(
            s, user_id=None, filename="x.txt", document_type="research_agent",
            content=(
                "Adaptive Beam Hardening is a technique used in Cargo Inspection systems. "
                "Adaptive Beam Hardening improves image quality significantly. "
            ),
        )
        crud.create_research_file(
            s, mission_id=mission.id, source_id=source.id, filename="x.txt",
            status="ingested", rag_document_id=doc.id,
        )

        questions = _generate_term_driven_questions(s, mission)
        texts = {q.question_text for q in questions}
        assert any("Adaptive Beam Hardening" in t for t in texts)
        assert all(q.category == "Mentioned but Unexplained" for q in questions)
    finally:
        s.close()


def test_term_driven_questions_skip_known_facts():
    from api.services.research_brain.curiosity_engine import _generate_term_driven_questions
    from api.db.crud import create_rag_document

    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="known term test")
        # Already in the graph -> must not be treated as "unexplained".
        crud.create_knowledge_node(s, node_type="System", label="Photon Counting Detector", approved=True)

        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/y", domain="example.com")
        doc = create_rag_document(
            s, user_id=None, filename="y.txt", document_type="research_agent",
            content="Photon Counting Detector technology is used here. Photon Counting Detector again.",
        )
        crud.create_research_file(
            s, mission_id=mission.id, source_id=source.id, filename="y.txt",
            status="ingested", rag_document_id=doc.id,
        )

        questions = _generate_term_driven_questions(s, mission)
        texts = {q.question_text for q in questions}
        assert not any("Photon Counting Detector" in t for t in texts)
    finally:
        s.close()


def test_term_driven_questions_require_no_ingested_files_is_empty():
    from api.services.research_brain.curiosity_engine import _generate_term_driven_questions
    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="no files yet")
        assert _generate_term_driven_questions(s, mission) == []
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# Settings gating — real DB rows, not in-memory counters
# ──────────────────────────────────────────────────────────

def test_auto_queue_off_leaves_question_suggested():
    from api.services.research_brain.curiosity_engine import apply_curiosity_settings

    s = SessionLocal()
    try:
        mission = _new_mission(s, curiosity_settings={"auto_queue_curiosity": False})
        question = crud.create_curiosity_question(
            s, mission_id=mission.id, question_text="What is X?", category="Missing",
            priority_score=0.9, expected_knowledge_gain=0.9, status="Suggested",
        )
        updated = apply_curiosity_settings(s, mission, question)
        assert updated.status == "Suggested"
        assert updated.spawned_mission_id is None
    finally:
        s.close()


def test_auto_queue_on_within_limits_spawns_mission(monkeypatch):
    from api.services.research_brain import curiosity_engine

    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)

    s = SessionLocal()
    try:
        mission = _new_mission(s, curiosity_settings={
            "auto_queue_curiosity": True, "min_priority": 0.5, "min_knowledge_gain": 0.5,
            "max_curiosity_jobs_per_mission": 3, "daily_curiosity_limit": _generous_daily_limit(s),
        })
        question = crud.create_curiosity_question(
            s, mission_id=mission.id, question_text="What is Y?", category="Missing",
            priority_score=0.9, expected_knowledge_gain=0.9, status="Suggested",
        )
        updated = curiosity_engine.apply_curiosity_settings(s, mission, question)
        assert updated.status == "Queued"
        assert updated.spawned_mission_id is not None
        child = crud.get_research_mission(s, updated.spawned_mission_id)
        assert child is not None
        assert child.mission_text == "What is Y?"
    finally:
        s.close()


def test_auto_queue_respects_min_priority_threshold(monkeypatch):
    from api.services.research_brain import curiosity_engine
    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)

    s = SessionLocal()
    try:
        mission = _new_mission(s, curiosity_settings={"auto_queue_curiosity": True, "min_priority": 0.8})
        low_priority_question = crud.create_curiosity_question(
            s, mission_id=mission.id, question_text="Low priority?", category="Missing",
            priority_score=0.1, expected_knowledge_gain=0.9, status="Suggested",
        )
        updated = curiosity_engine.apply_curiosity_settings(s, mission, low_priority_question)
        assert updated.status == "Suggested"
    finally:
        s.close()


def test_auto_queue_respects_per_mission_limit(monkeypatch):
    from api.services.research_brain import curiosity_engine
    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)

    s = SessionLocal()
    try:
        mission = _new_mission(s, curiosity_settings={
            "auto_queue_curiosity": True, "min_priority": 0.0, "min_knowledge_gain": 0.0,
            "max_curiosity_jobs_per_mission": 1, "daily_curiosity_limit": _generous_daily_limit(s),
        })
        q1 = crud.create_curiosity_question(
            s, mission_id=mission.id, question_text="First?", category="Missing",
            priority_score=0.9, expected_knowledge_gain=0.9, status="Suggested",
        )
        q2 = crud.create_curiosity_question(
            s, mission_id=mission.id, question_text="Second?", category="Missing",
            priority_score=0.9, expected_knowledge_gain=0.9, status="Suggested",
        )
        u1 = curiosity_engine.apply_curiosity_settings(s, mission, q1)
        u2 = curiosity_engine.apply_curiosity_settings(s, mission, q2)
        assert u1.status == "Queued"
        assert u2.status == "Suggested"  # per-mission limit of 1 already hit
    finally:
        s.close()


def test_auto_queue_respects_daily_limit_across_missions(monkeypatch):
    from datetime import datetime, timezone
    from api.services.research_brain import curiosity_engine
    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)

    s = SessionLocal()
    try:
        # daily_curiosity_limit is deliberately a platform-wide throttle backed
        # by real DB rows (crud.count_curiosity_spawned_missions_since), not an
        # in-memory counter — so it correctly persists across this suite's
        # repeated runs against a shared scratch DB. To keep this test
        # self-contained regardless of how many other tests already queued a
        # question "today", set the limit to exactly one more than whatever
        # has already been spawned today, rather than assuming a fresh count.
        today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        already_today = crud.count_curiosity_spawned_missions_since(s, today_start)
        settings = {
            "auto_queue_curiosity": True, "min_priority": 0.0, "min_knowledge_gain": 0.0,
            "max_curiosity_jobs_per_mission": 10, "daily_curiosity_limit": already_today + 1,
        }
        mission_a = _new_mission(s, mission_text="mission A", curiosity_settings=settings)
        mission_b = _new_mission(s, mission_text="mission B", curiosity_settings=settings)

        qa = crud.create_curiosity_question(
            s, mission_id=mission_a.id, question_text="A question?", category="Missing",
            priority_score=0.9, expected_knowledge_gain=0.9, status="Suggested",
        )
        qb = crud.create_curiosity_question(
            s, mission_id=mission_b.id, question_text="B question?", category="Missing",
            priority_score=0.9, expected_knowledge_gain=0.9, status="Suggested",
        )
        ua = curiosity_engine.apply_curiosity_settings(s, mission_a, qa)
        ub = curiosity_engine.apply_curiosity_settings(s, mission_b, qb)
        assert ua.status == "Queued"
        # Global daily_curiosity_limit=1 already consumed by mission A's question,
        # backed by a real DB count (count_curiosity_spawned_missions_since),
        # not an in-memory counter that would reset between calls.
        assert ub.status == "Suggested"
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# End-to-end: generate_questions() wired into a mission
# ──────────────────────────────────────────────────────────

def test_generate_questions_returns_empty_for_unknown_mission():
    from api.services.research_brain.curiosity_engine import generate_questions
    s = SessionLocal()
    try:
        assert generate_questions(s, "does-not-exist") == []
    finally:
        s.close()


def test_generate_questions_end_to_end():
    from api.services.research_brain.planner import build_research_plan
    from api.services.research_brain.curiosity_engine import generate_questions

    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="LINAC systems")
        build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        questions = generate_questions(s, mission.id)
        assert len(questions) > 0
        stored = crud.list_curiosity_questions(s, mission_id=mission.id)
        assert len(stored) == len(questions)
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────────────────

def test_list_curiosity_endpoint(client):
    from api.services.research_brain.planner import build_research_plan
    created = client.post("/api/research-agent/missions", json={"mission_text": "gamma detection"}).json()
    mission_id = created["mission"]["id"]

    s = SessionLocal()
    try:
        mission = crud.get_research_mission(s, mission_id)
        build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        from api.services.research_brain.curiosity_engine import generate_questions
        generate_questions(s, mission_id)
    finally:
        s.close()

    resp = client.get(f"/api/research-brain/missions/{mission_id}/curiosity")
    assert resp.status_code == 200
    assert len(resp.json()["questions"]) > 0


def test_list_curiosity_endpoint_404_for_unknown_mission(client):
    resp = client.get("/api/research-brain/missions/does-not-exist/curiosity")
    assert resp.status_code == 404


def test_approve_curiosity_endpoint_queues_and_spawns_mission(client):
    s = SessionLocal()
    try:
        mission = _new_mission(s)
        question = crud.create_curiosity_question(
            s, mission_id=mission.id, question_text="Approve me?", category="Missing",
            priority_score=0.1, expected_knowledge_gain=0.1, status="Suggested",
        )
        question_id = question.id
    finally:
        s.close()

    resp = client.post(f"/api/research-brain/curiosity/{question_id}/approve")
    assert resp.status_code == 200
    data = resp.json()["question"]
    assert data["status"] == "Queued"
    assert data["spawned_mission_id"] is not None


def test_approve_curiosity_endpoint_rejects_non_suggested(client):
    s = SessionLocal()
    try:
        mission = _new_mission(s)
        question = crud.create_curiosity_question(
            s, mission_id=mission.id, question_text="Already resolved?", category="Missing",
            priority_score=0.1, expected_knowledge_gain=0.1, status="Resolved",
        )
        question_id = question.id
    finally:
        s.close()

    resp = client.post(f"/api/research-brain/curiosity/{question_id}/approve")
    assert resp.status_code == 422


def test_reject_curiosity_endpoint(client):
    s = SessionLocal()
    try:
        mission = _new_mission(s)
        question = crud.create_curiosity_question(
            s, mission_id=mission.id, question_text="Reject me?", category="Missing",
            priority_score=0.1, expected_knowledge_gain=0.1, status="Suggested",
        )
        question_id = question.id
    finally:
        s.close()

    resp = client.post(f"/api/research-brain/curiosity/{question_id}/reject")
    assert resp.status_code == 200
    assert resp.json()["question"]["status"] == "Rejected"


def test_curiosity_endpoint_404_for_unknown_question(client):
    resp = client.post("/api/research-brain/curiosity/does-not-exist/approve")
    assert resp.status_code == 404


# ──────────────────────────────────────────────────────────
# Chat command
# ──────────────────────────────────────────────────────────

def test_chat_intent_detects_curiosity_command():
    from api.services.research_agent_chat_intent import detect_research_agent_intent
    assert detect_research_agent_intent("show me the questions you discovered by yourself") == {"action": "list_curiosity"}
    assert detect_research_agent_intent("اعرض الأسئلة التي اكتشفتها بنفسك") == {"action": "list_curiosity"}


@pytest.mark.asyncio
async def test_chat_intent_list_curiosity_returns_questions():
    from api.services.research_agent_chat_intent import handle_research_agent_intent
    from api.services.research_brain.planner import build_research_plan
    from api.services.research_brain.curiosity_engine import generate_questions

    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="explosives detection systems")
        build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        generate_questions(s, mission.id)
    finally:
        s.close()

    s2 = SessionLocal()
    try:
        payload = await handle_research_agent_intent(s2, USER["id"], {"action": "list_curiosity"})
        assert payload["type"] == "research_curiosity_questions"
        assert len(payload["questions"]) > 0
    finally:
        s2.close()
