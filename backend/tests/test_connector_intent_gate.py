"""
Connector Tool Router intent gate — regression tests.

Root cause covered: run_connector_tool_loop (a genuine LLM tool-decision
call) used to be invoked unconditionally on every eligible chat turn, and
its own system prompt told the model to call a tool "even if they don't
name the tool explicitly" — appropriate for ambiguous platform requests,
wrong for an ordinary research question, which the model sometimes
misrouted to the Google Drive connector (observed live: "اذكر لي اخر تقنيات
صناعه اجهزه مسح الحقائب باشعه اكس" opened a "Connect your Google Drive
account" card instead of answering).

detect_connector_tool_intent() is the deterministic pre-gate added to fix
this — covers: research questions never reach the connector router at all,
internet research (Knowledge Router) still works, workspace/translation
routing is unaffected (it's decided earlier and returns before this gate),
and explicit connector requests still work correctly.
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
from api.services.connector_chat_router import detect_connector_tool_intent

USER = {"id": "connector-gate-test-user", "username": "gate-tester@example.com", "name": "Gate Tester"}


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
# detect_connector_tool_intent — deterministic classification
# ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("message,expected", [
    # The exact live-reproduced regression case.
    ("اذكر لي اخر تقنيات صناعه اجهزه مسح الحقائب باشعه اكس", False),
    ("What is the newest LINAC technology?", False),
    ("Compare LINAC and Betatron.", False),
    ("What evidence supports this conclusion?", False),
    ("Any new research papers on photon counting?", False),
    ("Translate this document to Arabic.", False),
    ("Summarize the document in my workspace.", False),
    ("Thanks, that's helpful.", False),
    # Genuine connector requests must still match.
    ("Connect my Google Drive", True),
    ("show me my drive files", True),
    ("upload this report", True),
    ("open my canva designs", True),
    ("find the documents stored in drive", True),
])
def test_detect_connector_tool_intent_english(message, expected):
    assert detect_connector_tool_intent(message) is expected


def test_detect_connector_tool_intent_arabic():
    assert detect_connector_tool_intent("ارفع هذا الملف") is True
    assert detect_connector_tool_intent("اربط حسابي في جوجل درايف") is True
    assert detect_connector_tool_intent("مرحبا كيف حالك") is False


# ──────────────────────────────────────────────────────────
# End-to-end /api/chat/stream
# ──────────────────────────────────────────────────────────

def test_research_question_never_reaches_connector_router(client, monkeypatch):
    """The exact regression: a plain research question must never even
    attempt the connector tool-decision call, let alone get routed to
    Google Drive."""
    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("run_connector_tool_loop must not be called for a plain research question")

    monkeypatch.setattr("api.services.connector_chat_router.run_connector_tool_loop", _fail_if_called)

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={
            "message": "اذكر لي اخر تقنيات صناعه اجهزه مسح الحقائب باشعه اكس",
            "conversation_id": conv_id,
        },
    )
    assert resp.status_code == 200
    assert "google_drive" not in resp.text
    assert "Connect your Google Drive" not in resp.text


def test_internet_research_knowledge_router_still_works(client, monkeypatch):
    """Knowledge Router (Phase 2B.6) must still fire normally for a
    low-confidence, research-worthy question once the connector router is
    correctly skipped."""
    from api.config import settings

    async def _no_op_connector(*args, **kwargs):
        raise AssertionError("connector router must not be reached for this research question")

    monkeypatch.setattr("api.services.connector_chat_router.run_connector_tool_loop", _no_op_connector)

    calls = {"count": 0}

    def _spy_maybe_start(*args, **kwargs):
        calls["count"] += 1
        return None

    monkeypatch.setattr("api.services.research_agent.quick_research.maybe_start_chat_live_research", _spy_maybe_start)

    async def _force_low_confidence(*args, **kwargs):
        return {"confidence": 0.0, "topic_memory_id": None}

    monkeypatch.setattr("api.services.knowledge_router.assess_knowledge_confidence", _force_low_confidence)

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "Any new Rapiscan products for baggage scanning?", "conversation_id": conv_id},
    )
    assert resp.status_code == 200
    assert calls["count"] == 1, "Knowledge Router's live-research entry point should still fire normally"


def test_workspace_and_translation_routing_unaffected(client, monkeypatch):
    """Workspace Agent / document-generation routing is decided BEFORE the
    connector gate and returns early — confirms this fix doesn't change
    that priority. A genuine file/translation request on a workspace-linked
    conversation must still reach the Workspace Agent, not the connector
    router (which should never even be attempted here)."""
    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("connector router must not be reached for a workspace file request")

    monkeypatch.setattr("api.services.connector_chat_router.run_connector_tool_loop", _fail_if_called)

    async def _fake_run_workspace_turn(db, workspace, conversation, message, history, provider, model_name):
        yield {"type": "done", "content": "Translation complete.", "task_id": "t1", "status": "completed"}

    monkeypatch.setattr("api.services.workspace_agent.agent.run_workspace_turn", _fake_run_workspace_turn)

    db = SessionLocal()
    try:
        ws = crud.create_workspace(db, USER["id"], name="Documents")
        conv = crud.create_conversation(db, user_id=USER["id"], anon_session_id=None)
        crud.link_conversation_workspace(db, conv.id, ws.id)
        conv_id, ws_id = conv.id, ws.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "Translate this document to Arabic.", "conversation_id": conv_id, "workspace_id": ws_id},
    )
    assert resp.status_code == 200
    assert '"task_id": "t1"' in resp.text


def test_explicit_connector_request_still_works(client, monkeypatch):
    """An explicit connector request must still reach run_connector_tool_loop
    and have its result rendered — the gate must not be so strict that it
    blocks genuine connector usage."""
    async def _fake_run_connector_tool_loop(db, user_id, history, provider):
        return {"type": "canva_designs", "items": []}, []

    monkeypatch.setattr(
        "api.services.connector_chat_router.run_connector_tool_loop", _fake_run_connector_tool_loop,
    )

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "Show me my Canva designs", "conversation_id": conv_id},
    )
    assert resp.status_code == 200
    assert '"type": "canva_results"' in resp.text
