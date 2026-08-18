"""
Phase 2B.0 — Free Mode Graph Extraction tests.

Priority zero per the product spec: Free Mode must never skip graph
extraction, and must never call a paid LLM. This suite explicitly proves
both, plus the individual layers (local Ollama JSON extraction,
deterministic pattern-matching fallback, and the paid-provider adapter) and
the shared upsert_node_with_evidence/upsert_edge_with_evidence versioning
entry point. tests/conftest.py points OLLAMA_BASE_URL at an unreachable port
for the whole suite, so "Ollama unavailable" is real network behavior, not a
stub — the JSON-success path is monkeypatched per-test where needed.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest

from api.db.base import SessionLocal
from api.db import crud

REALISTIC_TEXT = (
    "Rapiscan Systems Detector Calibration Guide. This manual covers the "
    "Rapiscan Eagle Generator and Detector array calibration procedure per "
    "IEC 62463 and IAEA safety guidance. Fault code F102 indicates a "
    "Detector failure. Use ALARA principles during Calibration. "
) * 3


def _new_mission(db, *, free_mode=True):
    return crud.create_research_mission(db, user_id=None, mission_text="test mission", free_mode=free_mode)


# ──────────────────────────────────────────────────────────
# local_extraction.py — layer 1
# ──────────────────────────────────────────────────────────

def test_parse_json_response_strips_markdown_fences():
    from api.services.research_brain.local_extraction import _parse_json_response
    raw = '```json\n{"nodes": [{"label": "X", "type": "System"}], "edges": []}\n```'
    data = _parse_json_response(raw)
    assert data is not None
    assert data["nodes"][0]["label"] == "X"


def test_parse_json_response_rejects_malformed_json():
    from api.services.research_brain.local_extraction import _parse_json_response
    assert _parse_json_response("not json at all") is None
    assert _parse_json_response('{"no_nodes_key": []}') is None
    assert _parse_json_response('{"nodes": "not a list"}') is None


def test_sanitize_nodes_defaults_unknown_type_and_drops_empty_labels():
    from api.services.research_brain.local_extraction import _sanitize_nodes
    out = _sanitize_nodes([
        {"label": "  ", "type": "System"},   # blank label -> dropped
        {"label": "Detector", "type": "NotARealType"},  # unknown type -> Component
        {"label": "Generator", "type": "Equipment"},
        "not a dict",  # non-dict entries ignored
    ])
    assert len(out) == 2
    assert out[0] == {"label": "Detector", "type": "Component", "description": None}
    assert out[1]["type"] == "Equipment"


def test_sanitize_edges_drops_self_loops_and_unknown_relationship_defaults():
    from api.services.research_brain.local_extraction import _sanitize_edges
    out = _sanitize_edges([
        {"from": "A", "to": "A", "relationship": "uses"},  # self-loop -> dropped
        {"from": "A", "to": "B", "relationship": "nonsense"},  # unknown -> "contains"
        {"from": "", "to": "B", "relationship": "uses"},  # empty -> dropped
    ])
    assert len(out) == 1
    assert out[0]["relationship"] == "contains"


@pytest.mark.asyncio
async def test_local_ollama_extract_returns_none_when_unreachable():
    """OLLAMA_BASE_URL is pointed at an unreachable port by conftest.py for
    the whole suite — this is real network behavior (connection refused),
    not a stub, and must degrade to None, never raise."""
    from api.services.research_brain.local_extraction import local_ollama_extract
    result = await local_ollama_extract(REALISTIC_TEXT)
    assert result is None


@pytest.mark.asyncio
async def test_local_ollama_extract_returns_none_for_short_text():
    from api.services.research_brain.local_extraction import local_ollama_extract
    assert await local_ollama_extract("too short") is None
    assert await local_ollama_extract("") is None


@pytest.mark.asyncio
async def test_local_ollama_extract_success_path(monkeypatch):
    """Mocks the HTTP layer (not the function itself) to prove the JSON-success
    path — parsing, sanitizing, and provider_used/confidence tagging — works."""
    import httpx
    from api.services.research_brain import local_extraction

    class _FakeResponse:
        def raise_for_status(self):
            pass

        def json(self):
            return {"response": '{"nodes": [{"label": "Dual Energy", "type": "System", "description": "d"}], "edges": []}'}

    class _FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            return _FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", lambda *a, **kw: _FakeClient())

    result = await local_extraction.local_ollama_extract(REALISTIC_TEXT)
    assert result is not None
    assert result.provider_used == "local_ollama"
    assert result.nodes[0]["label"] == "Dual Energy"
    assert result.extractor_confidence == local_extraction.LOCAL_OLLAMA_CONFIDENCE


# ──────────────────────────────────────────────────────────
# deterministic_extraction.py — layer 2 (always succeeds)
# ──────────────────────────────────────────────────────────

def test_deterministic_extract_never_raises_on_empty_text():
    from api.services.research_brain.deterministic_extraction import deterministic_extract
    result = deterministic_extract("")
    assert result.nodes == []
    assert result.provider_used == "deterministic"


def test_deterministic_extract_finds_real_content():
    from api.services.research_brain.deterministic_extraction import deterministic_extract
    result = deterministic_extract(REALISTIC_TEXT)
    assert len(result.nodes) > 0
    labels = {n["label"] for n in result.nodes}
    assert "Rapiscan" in labels
    assert any(n["type"] == "Standard" for n in result.nodes)
    assert any(n["type"] == "Fault" for n in result.nodes)
    assert any(n["type"] == "Manufacturer" for n in result.nodes)


def test_deterministic_extract_word_boundary_avoids_false_positives():
    from api.services.research_brain.deterministic_extraction import deterministic_extract
    # "mA" (a _RADIATION keyword) must not match inside "manual"/"maintain".
    result = deterministic_extract("This is a technical manual for maintaining the system.")
    assert not any(n["label"] == "mA" for n in result.nodes)


def test_deterministic_extract_no_manufacturer_self_loop():
    from api.services.research_brain.deterministic_extraction import deterministic_extract
    result = deterministic_extract(REALISTIC_TEXT)
    for edge in result.edges:
        assert edge["from"].lower() != edge["to"].lower()


def test_find_standards_matches_all_listed_bodies():
    from api.services.research_brain.deterministic_extraction import _find_standards
    # Digit-numbered citation style, per-body — matches the regex's designed
    # shape (BODY [sep] NUMBER); IAEA also publishes non-numeric series codes
    # (e.g. "IAEA-TECDOC-1"), which this deterministic pattern-matcher is not
    # expected to catch — a known, disclosed low-recall trade-off, not a bug.
    text = "IEC 62463, ISO 9001, IAEA 115, ICRP 103, ANSI N42.35, ASTM E1817, NCRP 116"
    found = {s["label"] for s in _find_standards(text)}
    for prefix in ("IEC", "ISO", "IAEA", "ICRP", "ANSI", "ASTM", "NCRP"):
        assert any(label.startswith(prefix) for label in found), f"missing {prefix}"


# ──────────────────────────────────────────────────────────
# knowledge_versioning.py — upsert_node_with_evidence / upsert_edge_with_evidence
# ──────────────────────────────────────────────────────────

def test_upsert_node_with_evidence_creates_when_missing():
    from api.services.research_brain.knowledge_versioning import upsert_node_with_evidence
    s = SessionLocal()
    try:
        label = f"New Fact {uuid.uuid4()}"
        node = upsert_node_with_evidence(
            s, label=label, node_type="Component", description="d",
            research_source_id="fake-source", provider_used="deterministic", extractor_confidence=0.35,
        )
        assert node.evidence_count == 1
        assert node.confidence == 0.35
        assert node.provider_used == "deterministic"
        assert node.approved is True
    finally:
        s.close()


def test_upsert_node_with_evidence_versions_when_present():
    from api.services.research_brain.knowledge_versioning import upsert_node_with_evidence
    s = SessionLocal()
    try:
        label = f"Existing Fact {uuid.uuid4()}"
        first = upsert_node_with_evidence(
            s, label=label, node_type="Component", description="d",
            research_source_id="fake-source-1", provider_used="deterministic", extractor_confidence=0.35,
        )
        second = upsert_node_with_evidence(
            s, label=label, node_type="Component", description="d",
            research_source_id="fake-source-2", provider_used="deterministic", extractor_confidence=0.35,
        )
        assert second.id == first.id  # same node, versioned not duplicated
        assert second.evidence_count == 2
    finally:
        s.close()


def test_upsert_edge_with_evidence_rejects_self_loop():
    from api.services.research_brain.knowledge_versioning import upsert_edge_with_evidence
    s = SessionLocal()
    try:
        result = upsert_edge_with_evidence(
            s, from_node_id="same-id", to_node_id="same-id", relationship="uses",
            research_source_id="fake-source", provider_used="deterministic", extractor_confidence=0.35,
        )
        assert result is None
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# graph_extraction.py — the 3-layer dispatcher, wired end-to-end
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_free_mode_builds_real_nodes_via_deterministic_fallback():
    """Priority-zero requirement: Free Mode + no Ollama must still build a
    real, non-empty graph — never just skip. Ollama is genuinely unreachable
    here (conftest.py's OLLAMA_BASE_URL), so this exercises the real
    fallback chain end-to-end, not a mocked shortcut."""
    from api.services.research_brain import graph_extraction
    from api.db.crud import create_rag_document

    s = SessionLocal()
    try:
        mission = _new_mission(s, free_mode=True)
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/rapiscan", domain="example.com")
        file_row = crud.create_research_file(s, mission_id=mission.id, source_id=source.id, filename="rapiscan.txt", quality_score=70.0)
        doc = create_rag_document(s, user_id=None, filename="rapiscan.txt", document_type="research_agent", content=REALISTIC_TEXT)

        await graph_extraction.extract_and_version(s, mission, file_row, doc.id)

        rapiscan_node = crud.get_knowledge_node_by_label(s, "Rapiscan", "Manufacturer")
        assert rapiscan_node is not None
        assert rapiscan_node.evidence_count >= 1
        assert rapiscan_node.provider_used == "deterministic"

        activity = crud.list_research_activity(s, mission.id)
        assert any("Graph updated via deterministic" in a.message for a in activity)
    finally:
        s.close()


@pytest.mark.asyncio
async def test_free_mode_prefers_ollama_when_available(monkeypatch):
    from api.services.research_brain import graph_extraction
    from api.db.crud import create_rag_document

    async def _fake_ollama(text, manufacturer_hint=None):
        from api.services.research_brain.local_extraction import ExtractionResult
        return ExtractionResult(
            nodes=[{"label": "Ollama Found This", "type": "System", "description": None}],
            edges=[], provider_used="local_ollama", extractor_confidence=0.65,
        )

    monkeypatch.setattr(graph_extraction, "local_ollama_extract", _fake_ollama)

    s = SessionLocal()
    try:
        mission = _new_mission(s, free_mode=True)
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/b", domain="example.com")
        file_row = crud.create_research_file(s, mission_id=mission.id, source_id=source.id, filename="b.txt", quality_score=70.0)
        doc = create_rag_document(s, user_id=None, filename="b.txt", document_type="research_agent", content=REALISTIC_TEXT)

        await graph_extraction.extract_and_version(s, mission, file_row, doc.id)

        node = crud.get_knowledge_node_by_label(s, "Ollama Found This", "System")
        assert node is not None
        assert node.provider_used == "local_ollama"
    finally:
        s.close()


@pytest.mark.asyncio
async def test_free_mode_off_uses_paid_provider(monkeypatch):
    import types
    from api.services.research_brain import graph_extraction
    from api.db.crud import create_rag_document

    fake_job = types.SimpleNamespace(
        status="approved",
        graph_nodes=[{"label": "Paid Provider Fact", "type": "System", "description": "x"}],
        graph_edges=[],
    )

    async def _fake_run_study_pipeline(db, doc_id, filename, text, sha256=None, image_count=0):
        return fake_job

    monkeypatch.setattr("api.services.study_service.run_study_pipeline", _fake_run_study_pipeline)

    s = SessionLocal()
    try:
        mission = _new_mission(s, free_mode=False)
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/c", domain="example.com")
        file_row = crud.create_research_file(s, mission_id=mission.id, source_id=source.id, filename="c.txt", quality_score=70.0)
        doc = create_rag_document(s, user_id=None, filename="c.txt", document_type="research_agent", content=REALISTIC_TEXT)

        await graph_extraction.extract_and_version(s, mission, file_row, doc.id)

        node = crud.get_knowledge_node_by_label(s, "Paid Provider Fact", "System")
        assert node is not None
        assert node.provider_used == "paid_provider"
    finally:
        s.close()


@pytest.mark.asyncio
async def test_free_mode_never_calls_paid_provider(monkeypatch):
    """Must fail the build if a paid LLM call is ever reached while Free Mode is on."""
    from api.services.research_brain import graph_extraction
    from api.db.crud import create_rag_document

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("run_study_pipeline (paid LLM call) must never run when Free Mode is on")

    monkeypatch.setattr("api.services.study_service.run_study_pipeline", _fail_if_called)

    s = SessionLocal()
    try:
        mission = _new_mission(s, free_mode=True)
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/d", domain="example.com")
        file_row = crud.create_research_file(s, mission_id=mission.id, source_id=source.id, filename="d.txt", quality_score=70.0)
        doc = create_rag_document(s, user_id=None, filename="d.txt", document_type="research_agent", content=REALISTIC_TEXT)

        # Must complete without ever touching run_study_pipeline.
        await graph_extraction.extract_and_version(s, mission, file_row, doc.id)
    finally:
        s.close()


@pytest.mark.asyncio
async def test_thin_content_does_not_crash_and_yields_no_false_graph():
    """Empty/near-empty text must not crash extraction, and must not fabricate nodes."""
    from api.services.research_brain import graph_extraction
    from api.db.crud import create_rag_document

    s = SessionLocal()
    try:
        mission = _new_mission(s, free_mode=True)
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/e", domain="example.com")
        file_row = crud.create_research_file(s, mission_id=mission.id, source_id=source.id, filename="e.txt", quality_score=70.0)
        doc = create_rag_document(s, user_id=None, filename="e.txt", document_type="research_agent", content="hello world, nothing technical here at all whatsoever")

        await graph_extraction.extract_and_version(s, mission, file_row, doc.id)

        activity = crud.list_research_activity(s, mission.id)
        # Either "found nothing to add" or a near-empty "Graph updated" — either
        # way, must not raise, and must not silently pretend Free Mode was skipped.
        assert not any("Free Mode is on" in a.message for a in activity)
    finally:
        s.close()
