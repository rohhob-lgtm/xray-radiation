"""
Urgent regression fix — AI Chat denying platform capabilities it actually
has, for Arabic requests.

Root cause: detect_canva_intent()'s mention regex was `\bcanva\b` (Latin
script only). A live Arabic request naming Canva phonetically
("من كانفا ولد صوره لولد" — "from Canva, generate a picture of a boy") never
matched, so canva_action stayed None, the Canva keyword-fallback branch in
chat.py was skipped entirely, and the message fell through to plain Gemini
chat — which correctly reported that *it* (the base LLM) has no image tool,
but that answer misrepresented the platform, which has a real, already-
connected Canva integration. AI Chat must reason about what the platform
can do, not what the underlying model can do on its own.

Fix: canva_chat_intent.py's mention regex now also matches the Arabic
transliterations of "Canva" (كانفا / كانڤا / كانفه), routing these messages
into the existing canva_connector / connector_service pipeline exactly like
the English "canva" case already did.
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
from api.services.canva_chat_intent import detect_canva_intent

USER = {"id": "canva-arabic-test-user", "username": "canva-arabic-tester@example.com", "name": "Canva Arabic Tester"}


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


@pytest.mark.parametrize("message,expected", [
    ("من كانفا ولد صوره لولد", "list_designs"),  # the exact live-reproduced message
    ("افتح تصاميمي في كانفا", "list_designs"),
    ("افصل حسابي عن كانفا", "disconnect"),
    ("Generate an image using Canva", "list_designs"),
    ("Disconnect Canva", "disconnect"),
    ("مرحبا كيف حالك", None),
    ("ما هي احدث تقنيات الفحص بالأشعة السينية", None),
])
def test_detect_canva_intent_arabic_and_english(message, expected):
    assert detect_canva_intent(message) == expected


def test_e2e_arabic_canva_request_reaches_real_canva_not_llm_denial(client, monkeypatch):
    """The exact regression: Gemini must never be allowed to answer an
    Arabic Canva request on its own — the real platform Canva connector
    must be consulted first, whatever its connection state turns out to
    be."""
    async def _fail_if_reached(*args, **kwargs):
        raise AssertionError("plain provider.stream_chat must not be reached for a Canva request")

    monkeypatch.setattr("api.routes.chat._leak_guarded_stream_chat", _fail_if_reached)

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "من كانفا ولد صوره لولد", "conversation_id": conv_id},
    )
    assert resp.status_code == 200
    # Either a real design list/connect-required/error payload — never a
    # plain-text denial that the platform has no such capability.
    assert '"type": "canva_' in resp.text
