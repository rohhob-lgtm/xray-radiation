"""Capability Registry + platform identity awareness.

Covers the acceptance journeys the identity/capability phase cares about:
the registry is read-only and truthful, the /capabilities endpoint reports it,
disabling a capability flag removes it from what AI Chat claims (Test 7), and
the identity prompt is model-independent and enforces scientific integrity
(Test 1 / Test 8).
"""
from __future__ import annotations

import importlib

from fastapi.testclient import TestClient

from main import app
from api.config import Settings
from api.services import platform_capabilities as caps
from api.services.xray_knowledge import build_platform_identity_prompt


client = TestClient(app)


def _settings(**overrides):
    """A Settings instance with the given flag overrides, everything else
    at its declared default."""
    base = {
        "knowledge_router_enabled": True,
        "reasoning_engine_enabled": True,
        "ai_scientist_enabled": True,
        "knowledge_health_enabled": True,
        "image_retrieval_enabled": True,
    }
    base.update(overrides)
    # Settings() reads env/.env for other fields; overrides win.
    return Settings(**base)


def test_registry_services_are_real_import_paths():
    """Every capability must map to a genuinely importable service module —
    the registry must never claim a capability that has no code behind it."""
    for c in caps.all_capabilities():
        module_path = c.service
        # Every service string is a dotted path into api.* — the module (not
        # necessarily an attribute) must import.
        assert module_path.startswith("api."), c.key
        importlib.import_module(module_path)


def test_flagged_capabilities_reference_existing_settings_fields():
    s = _settings()
    for c in caps.all_capabilities():
        if c.enabled_flag is not None:
            assert hasattr(s, c.enabled_flag), c.key


def test_endpoint_reports_registry():
    resp = client.get("/api/capabilities")
    assert resp.status_code == 200
    body = resp.json()
    assert body["platform"] == "X-Ray Academy AI"
    keys = {c["key"] for c in body["capabilities"]}
    # A representative spread of the mapped platform capabilities.
    for expected in ("knowledge_retrieval", "deep_research", "canva_design",
                     "expert_reasoning", "internet_image_retrieval"):
        assert expected in keys


def test_disabling_flag_removes_capability_from_awareness(monkeypatch):
    """Test 7: disable one capability -> AI Chat must no longer claim it."""
    enabled = _settings(image_retrieval_enabled=True)
    disabled = _settings(image_retrieval_enabled=False)

    on = build_platform_identity_prompt(enabled)
    off = build_platform_identity_prompt(disabled)

    assert "Internet Image Retrieval" in on
    assert "Internet Image Retrieval" not in off
    # Structural, unflagged capabilities are unaffected.
    assert "Knowledge Retrieval (RAG)" in on
    assert "Knowledge Retrieval (RAG)" in off


def test_identity_is_model_independent_and_integrity_bound():
    """Test 1 / Test 8: identity describes the PLATFORM and enforces
    scientific integrity, independent of the underlying model."""
    prompt = build_platform_identity_prompt(_settings())
    assert "X-Ray Academy AI" in prompt
    assert "PLATFORM" in prompt
    # Foundation-model independence rule.
    assert "Foundation-model independence" in prompt
    # Scientific-integrity rule.
    assert "Never fabricate" in prompt
    # No mention of a specific foundation model in the identity itself.
    lowered = prompt.lower()
    for model_name in ("gemini", "openai", "gpt-4", "claude", "ollama"):
        assert model_name not in lowered
