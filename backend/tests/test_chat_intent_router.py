"""
AI Chat responsiveness — lightweight Intent Router tests.

Covers: detect_workspace_task_intent()'s keyword classification (the exact
regression case — "explain your capabilities" must not route into the
Workspace Agent — plus genuine file/document requests still matching), and
an end-to-end /api/chat/stream check that a conversation carrying a
workspace_id from an earlier turn skips the full Workspace Agent pipeline
for ordinary conversation but still uses it for a genuine file request.
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

USER = {"id": "chat-router-test-user", "username": "router-tester@example.com", "name": "Router Tester"}


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


# ──────────────────────────────────────────────────────────
# detect_workspace_task_intent — keyword classification
# ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("message,expected", [
    # The exact reported regression case.
    ("Yes, explain your capabilities regarding learning.", False),
    ("What can you do?", False),
    ("Hello, how are you?", False),
    ("What is the capital of France?", False),
    ("Thanks!", False),
    # Genuine file/workspace requests must still match.
    ("Translate this file to Arabic.", True),
    ("Summarize the document.", True),
    ("What is in this file?", True),
    ("Create a Word document about safety procedures.", True),
    ("List the files in my workspace.", True),
])
def test_detect_workspace_task_intent_english(message, expected):
    from api.services.document_chat_intent import detect_workspace_task_intent
    assert detect_workspace_task_intent(message) is expected


def test_detect_workspace_task_intent_arabic():
    from api.services.document_chat_intent import detect_workspace_task_intent
    assert detect_workspace_task_intent("لخص هذا الملف") is True
    assert detect_workspace_task_intent("مرحبا كيف حالك") is False


# ──────────────────────────────────────────────────────────
# /api/chat/stream routing — sticky workspace_id, plain vs. file message
# ──────────────────────────────────────────────────────────

def _make_conversation_with_workspace(db):
    ws = crud.create_workspace(db, USER["id"], name="Documents")
    conv = crud.create_conversation(db, user_id=USER["id"], anon_session_id=None)
    crud.link_conversation_workspace(db, conv.id, ws.id)
    return conv, ws


def test_plain_message_skips_workspace_agent_despite_sticky_workspace_id(client, monkeypatch):
    """The exact regression scenario: a conversation already linked to a
    workspace (from an earlier, unrelated file request) must NOT route an
    ordinary conversational follow-up through the Workspace Agent pipeline."""
    db = SessionLocal()
    try:
        conv, ws = _make_conversation_with_workspace(db)
        conv_id, ws_id = conv.id, ws.id
    finally:
        db.close()

    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("run_workspace_turn must not be invoked for a plain conversational message")
        yield  # pragma: no cover - keeps this an async generator

    monkeypatch.setattr("api.services.workspace_agent.agent.run_workspace_turn", _fail_if_called)

    resp = client.post(
        "/api/chat/stream",
        json={
            "message": "Yes, explain your capabilities regarding learning.",
            "conversation_id": conv_id,
            "workspace_id": ws_id,
        },
    )
    assert resp.status_code == 200
    body = resp.text
    assert "route=WORKSPACE_AGENT" not in body
    # Regression guard: a plain message reaching the regular chat path must
    # not surface an SSE error frame (e.g. the `history` local-variable
    # shadowing bug in event_generator's research_source_trust_history
    # branch, which UnboundLocalError'd on every non-matching turn).
    assert '"type": "error"' not in body


def test_file_message_still_uses_workspace_agent(client, monkeypatch):
    """A genuine file-related message on the same kind of sticky-workspace
    conversation must still get the full Workspace Agent pipeline."""
    db = SessionLocal()
    try:
        conv, ws = _make_conversation_with_workspace(db)
        conv_id, ws_id = conv.id, ws.id
    finally:
        db.close()

    async def _fake_run_workspace_turn(db, workspace, conversation, message, history, provider, model_name):
        yield {"type": "done", "content": "Here is your summary.", "task_id": "t1", "status": "completed"}

    monkeypatch.setattr("api.services.workspace_agent.agent.run_workspace_turn", _fake_run_workspace_turn)

    resp = client.post(
        "/api/chat/stream",
        json={
            "message": "Summarize the document in my workspace.",
            "conversation_id": conv_id,
            "workspace_id": ws_id,
        },
    )
    assert resp.status_code == 200
    # The workspace-agent path was genuinely used: its "done" event metadata
    # (task_id/status, only emitted by _stream_workspace_turn) shows up in
    # the SSE stream, and its content was persisted as the assistant message
    # (the content string itself isn't echoed in the "done" SSE frame —
    # only in the saved DB message, same as the real agent's behavior).
    assert '"task_id": "t1"' in resp.text
    assert '"status": "completed"' in resp.text
    db = SessionLocal()
    try:
        msgs = crud.get_messages(db, conv_id)
        assert any(m.role == "assistant" and m.content == "Here is your summary." for m in msgs)
    finally:
        db.close()
