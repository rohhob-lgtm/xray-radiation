"""
LEARN_TOPIC — a comprehensive-learning intent distinct from plain
Question-Answering.

"Learn everything about X" / "تعلم كل شيء عن X" / "Study X" / "Research X"
must NOT be answered immediately from existing knowledge — they launch a
broader deep_research mission (bigger coverage_target/max_coverage_rounds/
limits than the existing quick-scan chat "start research" command) that
sweeps manufacturers, manuals, academic papers, patents, standards, and
technical reports via the *existing* Research Agent/discovery/extraction/
trust/governance/memory pipeline — no second research architecture.

Covers: exact user-quoted trigger phrases route to learn_topic with
deep_research mode and expanded limits; common false positives ("Research
shows that...", "Study found...") are correctly rejected; the pre-existing
"research and learn about X" quick-start command is unaffected (still
quick_scan); end-to-end /api/chat/stream never answers immediately for a
LEARN_TOPIC message.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth, optional_auth
from api.db.base import SessionLocal
from api.db.models import User
from api.db import crud
from api.services.research_agent_chat_intent import detect_research_agent_intent

USER = {"id": "learn-topic-test-user", "username": "learn-topic-tester@example.com", "name": "Learn Topic Tester"}

_created_mission_ids: list[str] = []


@pytest.fixture(autouse=True)
def _archive_created_missions():
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


def _ensure_user():
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


# ──────────────────────────────────────────────────────────
# 1. detect_research_agent_intent — classification
# ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("message,expected", [
    # The exact user-specified trigger phrases.
    ("Learn everything about magnetron", {"action": "learn_topic", "topic": "magnetron"}),
    ("تعلم كل شيء عن الماجنترون", {"action": "learn_topic", "topic": "الماجنترون"}),
    ("تعلّم كل شيء عن الماجنترون", {"action": "learn_topic", "topic": "الماجنترون"}),
    ("Study LINAC", {"action": "learn_topic", "topic": "LINAC"}),
    ("Research Dual Energy Detectors", {"action": "learn_topic", "topic": "Dual Energy Detectors"}),
    # False positives — ordinary sentences that happen to start with
    # "Research"/"Study" but aren't commands.
    ("Research shows that dual energy imaging improves detection.", None),
    ("Study found no correlation between dose and image quality.", None),
    ("Research on this topic is ongoing.", None),
    # Pre-existing quick-start command must be unaffected (still "start",
    # not "learn_topic" — different, smaller mission).
    ("research and learn about baggage scanners", {"action": "start", "mission_text": "baggage scanners"}),
    ("search the web and learn about detectors", {"action": "start", "mission_text": "detectors"}),
    # Unrelated commands unaffected.
    ("What sources did you use?", {"action": "list_sources"}),
    ("stop the current research", {"action": "stop"}),
])
def test_detect_learn_topic(message, expected):
    assert detect_research_agent_intent(message) == expected


# ──────────────────────────────────────────────────────────
# 2. handle_research_agent_intent — mission creation
# ──────────────────────────────────────────────────────────

def test_learn_topic_creates_deep_research_mission_with_expanded_limits():
    from api.services.research_agent_chat_intent import handle_research_agent_intent
    import asyncio

    db = SessionLocal()
    try:
        result = asyncio.get_event_loop().run_until_complete(
            handle_research_agent_intent(db, USER["id"], {"action": "learn_topic", "topic": "magnetron"})
        )
        assert result["type"] == "research_mission_started"
        mission_dict = result["mission"]
        _created_mission_ids.append(mission_dict["id"])

        assert mission_dict["mode"] == "deep_research"
        assert mission_dict["free_mode"] is True
        assert mission_dict["coverage_target"] == 85.0
        assert mission_dict["max_coverage_rounds"] == 5
        limits = mission_dict["limits"]
        assert limits["max_pages"] == 60
        assert limits["max_files"] == 60
        assert limits["max_depth"] == 2

        mission = crud.get_research_mission(db, mission_dict["id"])
        assert mission.origin == "chat_learn_topic"
        assert "magnetron" in mission.mission_text.lower()
    finally:
        db.close()


def test_plain_start_still_creates_quick_scan_mission():
    """Regression guard: the pre-existing quick "start research" command
    must still create the smaller quick_scan mission, unaffected by the
    LEARN_TOPIC addition."""
    from api.services.research_agent_chat_intent import handle_research_agent_intent
    import asyncio

    db = SessionLocal()
    try:
        result = asyncio.get_event_loop().run_until_complete(
            handle_research_agent_intent(db, USER["id"], {"action": "start", "mission_text": "vehicle scanners"})
        )
        mission_dict = result["mission"]
        _created_mission_ids.append(mission_dict["id"])
        assert mission_dict["mode"] == "quick_scan"
        assert mission_dict["limits"]["max_pages"] == 20
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# 3. End-to-end /api/chat/stream — never answers immediately
# ──────────────────────────────────────────────────────────

def test_e2e_learn_topic_never_answers_immediately(client, monkeypatch):
    """A LEARN_TOPIC message must never reach plain QA / the Knowledge
    Router's immediate-answer path — it launches a mission and confirms
    that, nothing else, in this same turn."""
    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("Knowledge Router must not fire for a LEARN_TOPIC message")

    monkeypatch.setattr(
        "api.services.knowledge_router.assess_knowledge_confidence", _fail_if_called,
    )

    def _fake_start_mission(mission_id):
        return None

    monkeypatch.setattr("api.services.research_agent_chat_intent.start_mission", _fake_start_mission)

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "Learn everything about magnetron", "conversation_id": conv_id},
    )
    assert resp.status_code == 200
    assert '"deep_research"' in resp.text
    assert '"research_mission_started"' in resp.text
    assert '"chat_learn_topic"' in resp.text
    # The confirmation text streams word-by-word as separate SSE chunk
    # events, not one contiguous string — reassemble it to confirm the
    # actual rendered sentence, not just the raw payload fields above.
    import json
    chunks = "".join(
        json.loads(line[len("data: "):])["chunk"]
        for line in resp.text.splitlines()
        if line.startswith("data: ") and '"type": "chunk"' in line
    )
    assert "Started a research mission" in chunks

    db = SessionLocal()
    try:
        missions = crud.list_research_missions(db, user_id=USER["id"])
        for m in missions:
            if m.origin == "chat_learn_topic" and m.mission_text and "magnetron" in m.mission_text.lower():
                _created_mission_ids.append(m.id)
    finally:
        db.close()
