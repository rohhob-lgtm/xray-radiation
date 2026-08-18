"""
AI Tool Router / Design Orchestrator tests: deterministic intent detection,
the LLM spec-generation fallback, brand-template field mapping, and the
mode-cascade (autofill -> render_and_import -> render_only -> local_render_only)
with connector_service.execute_action monkeypatched at the boundary — same
convention as test_connectors.py's Canva tests.
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest

from api.services.design_content import (
    detect_design_intent, detect_design_edit_intent, generate_design_spec, _extract_json_object,
)
from api.services.design_orchestrator import DesignOrchestrator, _map_spec_to_dataset_fields
from api.services.connectors.providers.canva import connector as canva_connector_module
from api.services.connectors import service as connector_service_module


# ──────────────────────────────────────────────────────────
# Intent detection
# ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("message,expected", [
    ("Can you make me a poster about radiation safety?", "poster"),
    ("I need an infographic showing scanner types", "infographic"),
    ("Design a certificate of completion", "certificate"),
    ("Write up a brochure for the new course", "brochure"),
    ("Make a flyer for the open house", "flyer"),
    ("We need a banner for the lobby screen", "banner"),
    ("Design a course cover for X-ray Basics", "course_cover"),
    ("Prepare a training visual for module 3", "training_visual"),
    ("Create a social media post announcing the course", "social_media"),
    ("Draft a presentation cover for tomorrow's briefing", "presentation_cover"),
])
def test_detect_design_intent_matches_all_routed_types(message, expected):
    assert detect_design_intent(message) == expected


@pytest.mark.parametrize("message", [
    "What's a good lunch spot near the office?",
    "Explain how a backscatter scanner works.",
    "",
])
def test_detect_design_intent_negative_cases(message):
    assert detect_design_intent(message) is None


def test_detect_design_edit_intent_requires_prior_workflow():
    assert detect_design_edit_intent("change the title to Safety First", False) is None


def test_detect_design_edit_intent_title_change():
    edits = detect_design_edit_intent("change the title to Safety First Always", True)
    assert edits == {"title": "Safety First Always"}


def test_detect_design_edit_intent_language_switch_sets_direction():
    edits = detect_design_edit_intent("please switch to arabic", True)
    assert edits["language"] == "ar"
    assert edits["direction"] == "rtl"


def test_detect_design_edit_intent_new_template():
    edits = detect_design_edit_intent("use another template please", True)
    assert edits == {"new_template": True}


def test_detect_design_edit_intent_no_match_returns_none():
    assert detect_design_edit_intent("what time is it", True) is None


# ──────────────────────────────────────────────────────────
# LLM spec generation — strict JSON with a safe fallback
# ──────────────────────────────────────────────────────────

def test_extract_json_object_handles_markdown_fence():
    assert _extract_json_object('```json\n{"title": "Hi"}\n```') == {"title": "Hi"}


def test_extract_json_object_returns_none_for_garbage():
    assert _extract_json_object("not json at all") is None


@pytest.mark.asyncio
async def test_generate_design_spec_falls_back_when_provider_raises():
    class BoomProvider:
        async def chat(self, messages, system_prompt=""):
            raise RuntimeError("provider down")

    spec = await generate_design_spec(BoomProvider(), "Poster about radiation safety", "poster")
    assert spec["title"]
    assert spec["direction"] == "ltr"
    assert spec["palette"] == "blue"


@pytest.mark.asyncio
async def test_generate_design_spec_parses_real_json_reply():
    class FakeProvider:
        async def chat(self, messages, system_prompt=""):
            return '{"title": "Stay Safe", "subtitle": "Annual Review", "bullets": ["Wear your badge"], "palette": "teal", "language": "en", "direction": "ltr"}'

    spec = await generate_design_spec(FakeProvider(), "poster about safety", "poster")
    assert spec["title"] == "Stay Safe"
    assert spec["palette"] == "teal"
    assert spec["bullets"] == ["Wear your badge"]


# ──────────────────────────────────────────────────────────
# Brand template field mapping (Mode 1)
# ──────────────────────────────────────────────────────────

def test_map_spec_to_dataset_fields_uses_real_field_names_only():
    dataset = {"Heading": {"type": "text"}, "Body": {"type": "text"}, "Photo": {"type": "image"}}
    spec = {"title": "Safety First", "subtitle": "Annual Review", "bullets": ["Point A"]}
    data = _map_spec_to_dataset_fields(spec, dataset)
    assert data == {
        "Heading": {"type": "text", "text": "Safety First"},
        "Body": {"type": "text", "text": "Annual Review"},
    }
    assert "Photo" not in data  # image fields never guessed at


def test_map_spec_to_dataset_fields_empty_when_no_text_fields():
    dataset = {"Photo": {"type": "image"}}
    assert _map_spec_to_dataset_fields({"title": "X"}, dataset) == {}


# ──────────────────────────────────────────────────────────
# Mode cascade
# ──────────────────────────────────────────────────────────

class _FakeConnectionStatus:
    def __init__(self, connection_status):
        self.connection_status = connection_status


class _FakeResult:
    def __init__(self, success, data=None, error_code=None, error_message=None):
        self.success = success
        self.data = data or {}
        self.error_code = error_code
        self.error_message = error_message


@pytest.fixture
def orchestrator():
    return DesignOrchestrator()


@pytest.mark.asyncio
async def test_plan_returns_unsupported_when_canva_not_connected(monkeypatch, orchestrator):
    async def fake_status(db, user_id):
        return _FakeConnectionStatus("disconnected")
    monkeypatch.setattr(canva_connector_module.canva_connector, "get_connection_status", fake_status)

    decision = await orchestrator.plan(None, "user-1")
    assert decision.mode == "unsupported"


@pytest.mark.asyncio
async def test_run_falls_back_to_local_render_when_canva_not_connected(monkeypatch, orchestrator):
    async def fake_status(db, user_id):
        return _FakeConnectionStatus("disconnected")
    monkeypatch.setattr(canva_connector_module.canva_connector, "get_connection_status", fake_status)
    monkeypatch.setattr(orchestrator, "_persist", lambda *a, **k: None)

    result = await orchestrator.run(None, "user-1", "conv-1", "poster", {"title": "Safety First"})
    assert result.success
    assert result.mode == "local_render_only"
    assert result.thumbnail_url.startswith("data:image/png;base64,")
    assert result.connect_required
    assert "download_png" in result.available_actions


@pytest.mark.asyncio
async def test_run_cascades_from_render_and_import_to_render_only_on_import_failure(monkeypatch, orchestrator):
    async def fake_status(db, user_id):
        return _FakeConnectionStatus("connected")
    monkeypatch.setattr(canva_connector_module.canva_connector, "get_connection_status", fake_status)
    monkeypatch.setattr(orchestrator, "_persist", lambda *a, **k: None)

    async def fake_execute_action(db, user_id, provider, action, parameters):
        if action == "canva.get_user_capabilities":
            return _FakeResult(True, {"capabilities": []})  # no autofill capability on this plan
        if action == "canva.import_design":
            return _FakeResult(False, error_code="INSUFFICIENT_SCOPE", error_message="missing design:content:write")
        if action == "canva.create_design":
            return _FakeResult(True, {"design": {
                "id": "design-1", "title": parameters.get("title"),
                "thumbnail": {"url": "https://canva.example/thumb.png"},
                "urls": {"edit_url": "https://canva.com/design/design-1/edit"},
            }})
        raise AssertionError(f"unexpected action {action}")

    monkeypatch.setattr(connector_service_module.connector_service, "execute_action", fake_execute_action)

    result = await orchestrator.run(None, "user-1", "conv-1", "poster", {"title": "Safety First"})
    assert result.success
    assert result.mode == "render_only"
    assert result.canva_design_id == "design-1"
    assert "export_png" in result.available_actions


@pytest.mark.asyncio
async def test_run_uses_autofill_when_compatible_template_found(monkeypatch, orchestrator):
    async def fake_status(db, user_id):
        return _FakeConnectionStatus("connected")
    monkeypatch.setattr(canva_connector_module.canva_connector, "get_connection_status", fake_status)
    monkeypatch.setattr(orchestrator, "_persist", lambda *a, **k: None)

    async def fake_execute_action(db, user_id, provider, action, parameters):
        if action == "canva.get_user_capabilities":
            return _FakeResult(True, {"capabilities": ["autofill", "brand_template"]})
        if action == "canva.list_brand_templates":
            return _FakeResult(True, {"items": [{"id": "tmpl-1", "title": "Safety Poster Template"}]})
        if action == "canva.get_brand_template_dataset":
            assert parameters["brand_template_id"] == "tmpl-1"
            return _FakeResult(True, {"dataset": {"Heading": {"type": "text"}}})
        if action == "canva.create_design_autofill_job":
            assert parameters["brand_template_id"] == "tmpl-1"
            assert parameters["data"] == {"Heading": {"type": "text", "text": "Safety First"}}
            return _FakeResult(True, {"status": "success", "job_id": "job-1", "design": {
                "id": "design-2", "title": "Safety First",
                "thumbnail": {"url": "https://canva.example/thumb2.png"},
                "urls": {"edit_url": "https://canva.com/design/design-2/edit"},
            }})
        raise AssertionError(f"unexpected action {action}")

    monkeypatch.setattr(connector_service_module.connector_service, "execute_action", fake_execute_action)

    result = await orchestrator.run(None, "user-1", "conv-1", "poster", {"title": "Safety First"})
    assert result.success
    assert result.mode == "autofill_brand_template"
    assert result.canva_design_id == "design-2"
    assert result.canva_brand_template_id == "tmpl-1"
    assert "change_template" not in result.available_actions  # only one candidate template
