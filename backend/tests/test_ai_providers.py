"""
Multi-Provider AI architecture tests: Claude registered alongside Gemini
(never replacing it as the default), the OpenAI-format <-> Claude-format
message conversion used by both ClaudeProvider.chat_with_tools() and the
Translation Studio OpenAI-compat shim, and task-routing persistence.

Live network calls to the real Anthropic API are NOT exercised here — no
ANTHROPIC_API_KEY is available in this environment. is_configured is
asserted to be honest about that (never a fabricated "it works").
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest

from api.services.ai_providers.registry import provider_registry
from api.services.ai_providers.claude_provider import ClaudeProvider
from api.services.ai_providers.claude_openai_compat import ClaudeOpenAICompatClient
from api.db.base import SessionLocal
from api.db.models import AppSetting


# ── Registration ──────────────────────────────────────────────────────────

def test_claude_registered_alongside_gemini():
    ids = [p.provider_id for p in provider_registry.all_providers()]
    assert "gemini" in ids
    assert "claude" in ids


def test_claude_does_not_replace_gemini_as_default():
    # Bootstrap (module import time, before any DB restore) must prefer
    # Gemini over Claude when both — or neither — are configured.
    assert provider_registry.active_id == "gemini"


def test_claude_is_configured_reflects_real_env_state():
    claude = provider_registry.get("claude")
    assert claude is not None
    assert claude.provider_id == "claude"
    assert claude.provider_name == "Anthropic Claude"
    # Honest reporting — no ANTHROPIC_API_KEY is set in this test environment.
    if not (os.environ.get("ANTHROPIC_API_KEY") or "").strip():
        assert claude.is_configured is False


def test_claude_provider_requires_key_to_build_client():
    provider = ClaudeProvider(api_key="")
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        provider._effective_key()


# ── OpenAI-format <-> Claude-format message conversion ──────────────────────

def test_to_claude_messages_strips_system_role():
    provider = ClaudeProvider(api_key="test-key")
    messages = [
        {"role": "system", "content": "ignored — carried separately"},
        {"role": "user", "content": "hello"},
    ]
    converted = provider._to_claude_messages(messages)
    assert converted == [{"role": "user", "content": "hello"}]


def test_to_claude_messages_converts_tool_calls_and_results():
    provider = ClaudeProvider(api_key="test-key")
    messages = [
        {"role": "user", "content": "list my designs"},
        {
            "role": "assistant", "content": "",
            "tool_calls": [{
                "id": "call_1", "type": "function",
                "function": {"name": "canva_list_designs", "arguments": '{"limit": 5}'},
            }],
        },
        {"role": "tool", "tool_call_id": "call_1", "content": '{"items": []}'},
    ]
    converted = provider._to_claude_messages(messages)
    assert converted[0] == {"role": "user", "content": "list my designs"}

    assistant_block = converted[1]
    assert assistant_block["role"] == "assistant"
    tool_use = next(b for b in assistant_block["content"] if b["type"] == "tool_use")
    assert tool_use["id"] == "call_1"
    assert tool_use["name"] == "canva_list_designs"
    assert tool_use["input"] == {"limit": 5}

    tool_result_block = converted[2]
    assert tool_result_block["role"] == "user"
    assert tool_result_block["content"][0]["type"] == "tool_result"
    assert tool_result_block["content"][0]["tool_use_id"] == "call_1"


def test_to_claude_messages_converts_vision_image_blocks():
    provider = ClaudeProvider(api_key="test-key")
    messages = [{
        "role": "user",
        "content": [
            {"type": "text", "text": "what's in this image?"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,QUJD"}},
        ],
    }]
    converted = provider._to_claude_messages(messages)
    blocks = converted[0]["content"]
    assert blocks[0] == {"type": "text", "text": "what's in this image?"}
    assert blocks[1]["type"] == "image"
    assert blocks[1]["source"] == {"type": "base64", "media_type": "image/png", "data": "QUJD"}


# ── Translation Studio OpenAI-compat shim ────────────────────────────────

def test_claude_openai_compat_client_exposes_chat_completions_surface():
    client = ClaudeOpenAICompatClient(api_key="test-key")
    assert hasattr(client, "chat")
    assert hasattr(client.chat, "completions")
    assert hasattr(client.chat.completions, "create")


# ── Task-routing persistence ─────────────────────────────────────────────

def test_task_route_persists_and_restores(monkeypatch):
    db = SessionLocal()
    try:
        # Clean slate for this one hint so the test is order-independent.
        db.query(AppSetting).filter(AppSetting.key == "ai.task_route.__test_hint__").delete()
        db.commit()

        ok = provider_registry.persist_task_route(db, "__test_hint__", "gemini")
        assert ok is True
        assert provider_registry.list_task_routes()["__test_hint__"] == "gemini"

        row = db.query(AppSetting).filter(AppSetting.key == "ai.task_route.__test_hint__").first()
        assert row is not None
        assert row.value == "gemini"

        # Simulate a restart: clear in-memory state, restore from DB.
        provider_registry.clear_task_route("__test_hint__")
        assert "__test_hint__" not in provider_registry.list_task_routes()
        provider_registry.restore_and_seed_task_routes(db)
        assert provider_registry.list_task_routes()["__test_hint__"] == "gemini"

        provider_registry.persist_clear_task_route(db, "__test_hint__")
        assert "__test_hint__" not in provider_registry.list_task_routes()
    finally:
        db.query(AppSetting).filter(AppSetting.key == "ai.task_route.__test_hint__").delete()
        db.commit()
        db.close()
