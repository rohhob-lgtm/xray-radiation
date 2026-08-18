"""
Urgent regression fix — image intent routing + tool-call JSON leak guard.

Two related live bugs, reproduced and fixed together:

1. Arabic reference-image requests ("اعرض صورة للـ LINAC", "اعرض لي صوره
   للماجنترون ابحث في الانترنت او في قاعده البيانات") never matched
   gallery_service.py's English-only _GALLERY_INTENT_RE, so they fell
   through past IMAGE_SEARCH into plain general chat.
2. Plain chat has no tools registered at all (see gemini_provider.py —
   only chat_with_tools does), yet Google Gemini sometimes answered a
   request it had no real capability for by hallucinating a fake
   tool-call-shaped JSON blob (e.g. {"action": "dalle.text2im", ...}) as
   literal answer text, which streamed straight through to the user
   uncaught.

Fix: gallery_service.detect_intent()/extract_gallery_query() now also
recognise Arabic reference-image lookups (excluding generation verbs like
ارسم/صمم, which must not trigger a gallery/internet search for the word
"draw" itself) and route them to IMAGE_SEARCH (Knowledge Base + Internet
Retrieval, Phase K). chat.py's _leak_guarded_stream_chat() wraps every
plain-chat provider.stream_chat() call and substitutes a graceful fallback
message for any reply that looks like a tool-call JSON blob, regardless of
language or provider.
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
from api.services.gallery_service import detect_intent, extract_gallery_query
from api.routes.chat import _leak_guarded_stream_chat, _TOOL_CALL_LEAK_FALLBACK

USER = {"id": "leak-guard-test-user", "username": "leak-guard-tester@example.com", "name": "Leak Guard Tester"}


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
# 1. Arabic reference-image intent detection
# ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("message,expected_intent,expected_query_contains", [
    # The two exact live-reproduced regression messages.
    ("اعرض صورة للـ LINAC", "IMAGE_SEARCH", "LINAC"),
    ("اعرض لي صوره للماجنترون ابحث في الانترنت او في قاعده البيانات", "IMAGE_SEARCH", "ماجنترون"),
    ("أرني صوره للماجنترون", "IMAGE_SEARCH", "ماجنترون"),
    ("وريني رسم توضيحي لجهاز LZBV-S", "IMAGE_SEARCH", "LZBV-S"),
    # Generation verbs must NOT be swept into a gallery/internet lookup.
    ("ارسم لي صورة توضيحية للماجنترون", "GENERAL_CHAT", None),
    ("صمم لي صورة لجهاز فحص الحقائب", "GENERAL_CHAT", None),
    # Plain conversation / research questions unaffected.
    ("مرحبا كيف حالك", "GENERAL_CHAT", None),
    ("ما هي احدث تقنيات الفحص بالأشعة السينية", "GENERAL_CHAT", None),
    # English behaviour unchanged (pre-existing coverage, regression guard).
    ("Show me a LINAC diagram", "IMAGE_SEARCH", "LINAC"),
    ("Draw me a futuristic LINAC", "GENERAL_CHAT", None),
    # Bare elliptical "show me a/an X" (no explicit "photo/image/picture") —
    # the exact live-reproduced regression: reference-image priority must
    # beat plain knowledge-base text answers.
    ("Show me a magnetron", "IMAGE_SEARCH", "magnetron"),
    ("Show me a detector", "IMAGE_SEARCH", "detector"),
    ("Show me a summary", "GENERAL_CHAT", None),
    ("Show me a comparison of LINAC types", "GENERAL_CHAT", None),
])
def test_arabic_and_english_image_intent(message, expected_intent, expected_query_contains):
    intent = detect_intent(message)
    assert intent == expected_intent
    if expected_intent == "IMAGE_SEARCH":
        query = extract_gallery_query(message)
        assert query is not None
        assert expected_query_contains in query
        # Never leak the "search the internet/database" meta-instruction
        # into the actual search subject.
        assert "ابحث" not in query
        assert "الانترنت" not in query


# ──────────────────────────────────────────────────────────
# 2. _leak_guarded_stream_chat — unit coverage
# ──────────────────────────────────────────────────────────

class _FakeLeakingProvider:
    """Simulates a provider that hallucinates a fake tool-call JSON blob,
    split across several small chunks (as real token-by-token streaming
    would deliver it) — the guard must catch it even when the leading
    '{ "action":' prefix is split across chunk boundaries."""

    async def stream_chat(self, history, system_prompt="", max_tokens=None):
        pieces = [
            '{ "action": "dall',
            'e.text2im", "action_input": "{\\"prompt\\": \\"cavity magnetron',
            ' cross-section\\"}", ',
            '"thought": "generating an illustrative image"}',
        ]
        for p in pieces:
            yield p


class _FakeNormalProviderShort:
    """A normal reply short enough that the stream ends before the sniff
    threshold is ever reached — exercises the end-of-stream flush path."""

    async def stream_chat(self, history, system_prompt="", max_tokens=None):
        for w in ["Hello", " world", ", this", " is", " fine."]:
            yield w


class _FakeNormalProviderLong:
    """A normal reply long enough to cross the sniff threshold without
    matching the leak pattern — exercises the sniffed-but-clean path."""

    async def stream_chat(self, history, system_prompt="", max_tokens=None):
        text = (
            "The magnetron is the RF power source for most linear "
            "accelerators used in cargo and vehicle scanning systems. "
        )
        for i in range(0, len(text), 7):
            yield text[i:i + 7]


async def _collect(agen):
    return "".join([chunk async for chunk in agen])


@pytest.mark.asyncio
async def test_leak_guarded_stream_chat_replaces_hallucinated_tool_call():
    out = await _collect(_leak_guarded_stream_chat(_FakeLeakingProvider(), [], "", 100))
    assert out == _TOOL_CALL_LEAK_FALLBACK
    assert "action" not in out
    assert "dalle" not in out.lower()
    assert "{" not in out


@pytest.mark.asyncio
async def test_leak_guarded_stream_chat_passes_through_short_normal_reply():
    out = await _collect(_leak_guarded_stream_chat(_FakeNormalProviderShort(), [], "", 100))
    assert out == "Hello world, this is fine."


@pytest.mark.asyncio
async def test_leak_guarded_stream_chat_passes_through_long_normal_reply():
    provider = _FakeNormalProviderLong()
    expected = "".join([chunk async for chunk in provider.stream_chat([])])
    out = await _collect(_leak_guarded_stream_chat(_FakeNormalProviderLong(), [], "", 100))
    assert out == expected


# ──────────────────────────────────────────────────────────
# 3. End-to-end /api/chat/stream
# ──────────────────────────────────────────────────────────

def test_e2e_hallucinated_tool_call_never_reaches_user(client, monkeypatch):
    """A generation-verb request ("Draw me...") has no design-type keyword
    match, no connector match, no gallery match — it reaches plain chat.
    If the configured provider hallucinates a fake tool-call JSON blob (as
    observed live with Gemini), the response the user receives must never
    contain it. This test environment has a real GEMINI_API_KEY configured
    (confirmed: an unpatched run makes a genuine Gemini call), so the
    provider itself is stubbed via _resolve_provider rather than relying on
    MockProvider being selected."""
    from api.config import settings

    monkeypatch.setattr(settings, "knowledge_router_enabled", False)
    monkeypatch.setattr(settings, "reasoning_engine_enabled", False)

    class _LeakingProvider:
        provider_name = "Fake Leaking Provider"
        model_name = "fake"

        async def stream_chat(self, messages, system_prompt="", max_tokens=None):
            for p in ['{ "action": "dalle.text2im", ', '"action_input": "{...}" }']:
                yield p

    monkeypatch.setattr("api.routes.chat._resolve_provider", lambda *a, **k: _LeakingProvider())

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "Draw me a futuristic LINAC", "conversation_id": conv_id},
    )
    assert resp.status_code == 200
    assert '"action"' not in resp.text
    assert "dalle" not in resp.text.lower()
    assert "I don't have a built-in tool to generate a custom image" in resp.text


def test_e2e_arabic_reference_image_request_routes_to_gallery(client, monkeypatch):
    """The exact live-reproduced regression: a plain Arabic reference-image
    request must now be classified as IMAGE_SEARCH and rendered through the
    gallery_results payload — never reaching plain chat (and therefore
    never at risk of the hallucination bug at all). Internet fallback is
    stubbed out (network-bound, already covered by test_image_discovery.py)
    so this test stays fast and deterministic."""
    async def _no_images(*args, **kwargs):
        return []

    monkeypatch.setattr(
        "api.services.research_agent.image_discovery.discover_public_images", _no_images,
    )

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={
            "message": "اعرض لي صوره للماجنترون ابحث في الانترنت او في قاعده البيانات",
            "conversation_id": conv_id,
        },
    )
    assert resp.status_code == 200
    assert '"type": "gallery_results"' in resp.text
    assert '"action"' not in resp.text
