"""
Knowledge Evolution Engine (Sub-Phase 2A) tests.

Covers: the deterministic Research Brain planner (manufacturer vs. generic
template, no LLM required), knowledge versioning (evidence bookkeeping,
supersede-never-delete), the Gap Detector's coverage math, graph_query's
Unified Brain read side, Free Mode gating on graph extraction (must never
call the paid study pipeline), and the read-only research-brain API. Network
and LLM calls are monkeypatched throughout — this suite must never hit the
real internet or a real model.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import types
import uuid

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth
from api.db.base import SessionLocal
from api.db.models import User
from api.db import crud

USER = {"id": "research-brain-test-user", "username": "brain-tester@example.com", "name": "Brain Tester"}


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


def _new_mission(db, *, free_mode=True, mission_text="test mission"):
    return crud.create_research_mission(db, user_id=USER["id"], mission_text=mission_text, free_mode=free_mode)


# ──────────────────────────────────────────────────────────
# planner — deterministic, no LLM required
# ──────────────────────────────────────────────────────────

def test_planner_detects_manufacturer_template():
    from api.services.research_brain.planner import _detect_manufacturer
    assert _detect_manufacturer("Learn everything about Rapiscan X-ray systems") == "Rapiscan"
    assert _detect_manufacturer("Learn about generic X-ray detectors") is None


def test_planner_manufacturer_mission_uses_manufacturer_template():
    from api.services.research_brain.planner import build_research_plan, _MANUFACTURER_TOPIC_TEMPLATE
    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="Learn everything about Rapiscan X-ray systems")
        plan = build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        assert plan.normalized_understanding["template"] == "manufacturer"
        assert plan.normalized_understanding["matched_manufacturer"] == "Rapiscan"

        topics = crud.list_research_topics(s, mission.id)
        assert len(topics) > 0
        assert all(t.label in _MANUFACTURER_TOPIC_TEMPLATE for t in topics)
        assert all(t.research_questions for t in topics)
        assert all(t.search_strategy.get("queries") for t in topics)
    finally:
        s.close()


def test_planner_generic_mission_uses_domain_template():
    from api.services.research_brain.planner import build_research_plan
    from api.services.research_agent.query_generator import DOMAIN_SEED_QUERIES
    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="radiation portal monitors and gamma detection")
        plan = build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        assert plan.normalized_understanding["template"] == "generic"
        assert plan.normalized_understanding["matched_manufacturer"] is None

        topics = crud.list_research_topics(s, mission.id)
        assert len(topics) > 0
        assert all(t.label in DOMAIN_SEED_QUERIES for t in topics)
    finally:
        s.close()


def test_planner_deep_research_yields_at_least_as_many_topics_as_quick_scan():
    from api.services.research_brain.planner import build_research_plan
    s = SessionLocal()
    try:
        m1 = _new_mission(s, mission_text="X-ray detector physics")
        build_research_plan(s, m1.id, m1.mission_text, "quick_scan")
        quick_count = len(crud.list_research_topics(s, m1.id))

        m2 = _new_mission(s, mission_text="X-ray detector physics")
        build_research_plan(s, m2.id, m2.mission_text, "deep_research")
        deep_count = len(crud.list_research_topics(s, m2.id))

        assert deep_count >= quick_count
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# knowledge_versioning — evidence bookkeeping + never-delete supersede
# ──────────────────────────────────────────────────────────

def test_record_node_evidence_increments_and_raises_confidence():
    from api.services.research_brain.knowledge_versioning import record_node_evidence
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(s, node_type="System", label=f"Dual Energy {uuid.uuid4()}", approved=True)
        starting_confidence = node.confidence
        record_node_evidence(s, node.id, research_source_id="fake-source-1", supports=True, source_quality_score=90.0)
        updated = crud.get_knowledge_node(s, node.id)
        assert updated.evidence_count == 1
        assert updated.confidence > starting_confidence

        evidence = crud.list_knowledge_evidence(s, node_id=node.id)
        assert len(evidence) == 1
        assert evidence[0].supports is True
    finally:
        s.close()


def test_record_node_evidence_conflicting_lowers_confidence():
    from api.services.research_brain.knowledge_versioning import record_node_evidence
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(s, node_type="System", label=f"Backscatter {uuid.uuid4()}", approved=True, confidence=0.7)
        record_node_evidence(s, node.id, research_source_id="fake-source-2", supports=False, source_quality_score=90.0)
        updated = crud.get_knowledge_node(s, node.id)
        assert updated.confidence < 0.7
        assert updated.evidence_count == 1
    finally:
        s.close()


def test_record_node_evidence_sets_topic_only_if_unset():
    from api.services.research_brain.knowledge_versioning import record_node_evidence
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(s, node_type="System", label=f"LINAC {uuid.uuid4()}", approved=True)
        record_node_evidence(s, node.id, research_source_id="fake-source-3", topic_id="topic-a")
        updated = crud.get_knowledge_node(s, node.id)
        assert updated.research_topic_id == "topic-a"

        # A second piece of evidence with a different topic_id must not overwrite the first.
        record_node_evidence(s, node.id, research_source_id="fake-source-4", topic_id="topic-b")
        updated2 = crud.get_knowledge_node(s, node.id)
        assert updated2.research_topic_id == "topic-a"
    finally:
        s.close()


def test_supersede_node_never_deletes_and_chain_is_walkable():
    from api.services.research_brain.knowledge_versioning import supersede_node
    s = SessionLocal()
    try:
        old = crud.create_knowledge_node(
            s, node_type="Component", label=f"Detector Type A {uuid.uuid4()}", approved=True, confidence=0.6,
        )
        new_id = supersede_node(s, old.id, label="Detector Type B", node_type="Component", description="Newer generation")
        assert new_id is not None
        assert new_id != old.id

        old_reloaded = crud.get_knowledge_node(s, old.id)
        new_node = crud.get_knowledge_node(s, new_id)

        assert old_reloaded.status == "deprecated"
        assert old_reloaded.replaced_by_id == new_id
        assert new_node.status == "current"
        assert new_node.supersedes_id == old.id
        assert new_node.version == old_reloaded.version + 1

        chain = crud.get_knowledge_node_version_chain(s, new_id)
        assert [n.id for n in chain] == [old.id, new_id]
        chain_from_old = crud.get_knowledge_node_version_chain(s, old.id)
        assert [n.id for n in chain_from_old] == [old.id, new_id]
    finally:
        s.close()


def test_supersede_node_unknown_id_returns_none():
    from api.services.research_brain.knowledge_versioning import supersede_node
    s = SessionLocal()
    try:
        assert supersede_node(s, "does-not-exist", label="X", node_type="Component") is None
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# gap_detector — coverage math
# ──────────────────────────────────────────────────────────

def test_compute_coverage_reflects_evidence_count():
    from api.services.research_brain.planner import build_research_plan
    from api.services.research_brain.knowledge_versioning import record_node_evidence
    from api.services.research_brain.gap_detector import compute_coverage
    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="dual energy imaging")
        build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        topics = crud.list_research_topics(s, mission.id)
        topic = topics[0]
        crud.update_research_topic(s, topic.id, estimates={**topic.estimates, "expected_sources": 4})

        node = crud.create_knowledge_node(s, node_type="System", label=f"Fact {uuid.uuid4()}", approved=True)
        record_node_evidence(s, node.id, research_source_id="src-1", topic_id=topic.id)
        record_node_evidence(s, node.id, research_source_id="src-2", topic_id=topic.id)

        results = compute_coverage(s, mission.id)
        this_topic = next(r for r in results if r["topic_id"] == topic.id)
        assert this_topic["coverage_pct"] == 50.0  # 2 evidence / 4 expected

        reloaded = crud.get_research_topic(s, topic.id)
        assert reloaded.coverage_pct == 50.0
        assert reloaded.status == "researching"
    finally:
        s.close()


def test_compute_coverage_caps_at_100():
    from api.services.research_brain.planner import build_research_plan
    from api.services.research_brain.knowledge_versioning import record_node_evidence
    from api.services.research_brain.gap_detector import compute_coverage
    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="LINAC systems")
        build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        topic = crud.list_research_topics(s, mission.id)[0]
        crud.update_research_topic(s, topic.id, estimates={**topic.estimates, "expected_sources": 1})

        node = crud.create_knowledge_node(s, node_type="System", label=f"Fact {uuid.uuid4()}", approved=True)
        for i in range(5):
            record_node_evidence(s, node.id, research_source_id=f"src-{i}", topic_id=topic.id)

        results = compute_coverage(s, mission.id)
        this_topic = next(r for r in results if r["topic_id"] == topic.id)
        assert this_topic["coverage_pct"] == 100.0
        assert this_topic["status"] == "covered"
    finally:
        s.close()


def test_list_low_coverage_topics_includes_suggestion_text():
    from api.services.research_brain.planner import build_research_plan
    from api.services.research_brain.gap_detector import compute_coverage, list_low_coverage_topics
    s = SessionLocal()
    try:
        mission = _new_mission(s, mission_text="backscatter imaging")
        build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
        compute_coverage(s, mission.id)  # no evidence at all -> every topic is 0% / gap

        low = list_low_coverage_topics(s, mission.id, threshold=60.0)
        assert len(low) > 0
        assert all("Would you like me to improve" in item["suggestion"] for item in low)
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# graph_query — Unified Brain read side
# ──────────────────────────────────────────────────────────

def test_get_relevant_facts_matches_and_ranks():
    from api.services.research_brain.graph_query import get_relevant_facts
    s = SessionLocal()
    try:
        label = f"Dual Energy Imaging {uuid.uuid4()}"
        crud.create_knowledge_node(
            s, node_type="System", label=label,
            description="uses two energy spectra for material discrimination", approved=True,
        )
        # top_k generous on purpose: this suite reuses a persistent scratch DB
        # across repeated runs, so identical-scoring nodes from earlier runs
        # of this same test legitimately tie with this run's node — the
        # tokenizer strips uuid-like tokens, so a "make the query unique"
        # trick doesn't help. What's actually under test (matching + ranking
        # works at all) doesn't depend on a tight top_k, so ask for enough
        # results that ties can't push this run's node out entirely.
        facts = get_relevant_facts(s, "dual energy imaging material discrimination", top_k=50)
        assert any(f["label"] == label for f in facts)
    finally:
        s.close()


def test_get_relevant_facts_excludes_deprecated():
    from api.services.research_brain.knowledge_versioning import supersede_node
    from api.services.research_brain.graph_query import get_relevant_facts
    s = SessionLocal()
    try:
        unique = uuid.uuid4()
        old_label = f"Detector Photonique Alpha {unique}"
        new_label = f"Detector Photonique Beta {unique}"
        old = crud.create_knowledge_node(s, node_type="Component", label=old_label, approved=True)
        supersede_node(s, old.id, label=new_label, node_type="Component")

        facts = get_relevant_facts(s, f"Detector Photonique {unique}")
        labels = {f["label"] for f in facts}
        assert old_label not in labels
        assert new_label in labels
    finally:
        s.close()


def test_get_relevant_facts_empty_query_returns_empty():
    from api.services.research_brain.graph_query import get_relevant_facts
    s = SessionLocal()
    try:
        assert get_relevant_facts(s, "") == []
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# graph_extraction — Free Mode must never call the paid study pipeline
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_free_mode_never_calls_paid_graph_extraction_but_graph_still_grows(monkeypatch):
    """Superseded by Phase 2B.0: Free Mode must never touch the paid pipeline,
    but — unlike the old Sub-Phase 2A behavior — it must NOT just skip graph
    extraction either. See tests/test_phase2b_extraction.py for the full
    layered-extraction test suite; this test only re-confirms the Free Mode
    boundary from graph_extraction's entry point."""
    from api.services.research_brain import graph_extraction
    from api.db.crud import create_rag_document

    def _fail_if_called(*args, **kwargs):
        raise AssertionError("run_study_pipeline (paid LLM call) must never run when Free Mode is on")

    monkeypatch.setattr("api.services.study_service.run_study_pipeline", _fail_if_called)

    async def _no_ollama(*args, **kwargs):
        return None  # force the deterministic fallback, no real network call

    monkeypatch.setattr(graph_extraction, "local_ollama_extract", _no_ollama)

    s = SessionLocal()
    try:
        mission = _new_mission(s, free_mode=True)
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/a", domain="example.com")
        file_row = crud.create_research_file(s, mission_id=mission.id, source_id=source.id, filename="a.txt", quality_score=80.0)
        doc = create_rag_document(
            s, user_id=None, filename="a.txt", document_type="research_agent",
            content="Rapiscan Detector calibration procedure per IEC 62463. " * 5,
        )

        await graph_extraction.extract_and_version(s, mission, file_row, doc.id)

        activity = crud.list_research_activity(s, mission.id)
        assert any("Graph updated via deterministic" in a.message for a in activity)
    finally:
        s.close()


@pytest.mark.asyncio
async def test_non_free_mode_versions_nodes_from_study_pipeline(monkeypatch):
    from api.services.research_brain import graph_extraction

    s = SessionLocal()
    try:
        mission = _new_mission(s, free_mode=False)
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/b", domain="example.com")
        file_row = crud.create_research_file(s, mission_id=mission.id, source_id=source.id, filename="b.txt", quality_score=80.0)

        label = f"Fact From Pipeline {uuid.uuid4()}"
        # Pre-create the node exactly as approve_study_job's dedupe-and-reinforce
        # write path would have (graph_extraction looks it up by label+type,
        # it does not create nodes itself).
        crud.create_knowledge_node(s, node_type="Component", label=label, approved=True)

        fake_job = types.SimpleNamespace(
            status="approved",
            graph_nodes=[{"label": label, "type": "Component", "description": "x"}],
            graph_edges=[],
        )

        async def _fake_run_study_pipeline(db, doc_id, filename, text, sha256=None, image_count=0):
            return fake_job

        monkeypatch.setattr("api.services.study_service.run_study_pipeline", _fake_run_study_pipeline)

        from api.db.crud import create_rag_document
        doc = create_rag_document(s, user_id=None, filename="b.txt", document_type="research_agent", content="some content " * 20)

        await graph_extraction.extract_and_version(s, mission, file_row, doc.id)

        node = crud.get_knowledge_node_by_label(s, label, "Component")
        assert node is not None
        assert node.evidence_count == 1

        activity = crud.list_research_activity(s, mission.id)
        assert any("Graph updated" in a.message for a in activity)
    finally:
        s.close()


@pytest.mark.asyncio
async def test_unapproved_study_job_is_not_versioned(monkeypatch):
    from api.services.research_brain import graph_extraction

    s = SessionLocal()
    try:
        mission = _new_mission(s, free_mode=False)
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/c", domain="example.com")
        file_row = crud.create_research_file(s, mission_id=mission.id, source_id=source.id, filename="c.txt", quality_score=80.0)

        fake_job = types.SimpleNamespace(status="awaiting_approval", graph_nodes=[], graph_edges=[])

        async def _fake_run_study_pipeline(db, doc_id, filename, text, sha256=None, image_count=0):
            return fake_job

        monkeypatch.setattr("api.services.study_service.run_study_pipeline", _fake_run_study_pipeline)

        from api.db.crud import create_rag_document
        doc = create_rag_document(s, user_id=None, filename="c.txt", document_type="research_agent", content="some content " * 20)

        # Must return cleanly without error even though nothing gets versioned.
        await graph_extraction.extract_and_version(s, mission, file_row, doc.id)
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# API endpoints
# ──────────────────────────────────────────────────────────

def test_plan_endpoint_returns_topics(client):
    created = client.post("/api/research-agent/missions", json={"mission_text": "Learn everything about Nuctech scanners"}).json()
    mission_id = created["mission"]["id"]

    resp = client.get(f"/api/research-brain/missions/{mission_id}/plan")
    assert resp.status_code == 200
    data = resp.json()
    # Mission creation itself doesn't build a plan (that happens in run_mission,
    # which is monkeypatched to a no-op in this fixture) — the endpoint must
    # still respond cleanly with an empty plan rather than erroring.
    assert data["plan"] is None
    assert data["topics"] == []


def test_plan_endpoint_404_for_unknown_mission(client):
    resp = client.get("/api/research-brain/missions/does-not-exist/plan")
    assert resp.status_code == 404


def test_coverage_endpoint_404_for_unknown_mission(client):
    resp = client.get("/api/research-brain/missions/does-not-exist/coverage")
    assert resp.status_code == 404


def test_coverage_endpoint_with_real_plan(client):
    from api.services.research_brain.planner import build_research_plan
    created = client.post("/api/research-agent/missions", json={"mission_text": "radiation safety standards"}).json()
    mission_id = created["mission"]["id"]

    s = SessionLocal()
    try:
        mission = crud.get_research_mission(s, mission_id)
        build_research_plan(s, mission.id, mission.mission_text, "quick_scan")
    finally:
        s.close()

    resp = client.get(f"/api/research-brain/missions/{mission_id}/coverage")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["coverage"]) > 0


def test_node_endpoint_returns_evidence_and_version_chain(client):
    s = SessionLocal()
    try:
        mission = _new_mission(s)
        source = crud.create_research_source(s, mission_id=mission.id, url="https://example.com/node-test", domain="example.com")
        node = crud.create_knowledge_node(s, node_type="System", label=f"Node Endpoint Test {uuid.uuid4()}", approved=True)
        crud.create_knowledge_evidence(s, node_id=node.id, research_source_id=source.id, supports=True)
        node_id = node.id
    finally:
        s.close()

    resp = client.get(f"/api/research-brain/nodes/{node_id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["node"]["id"] == node_id
    assert len(data["supporting_sources"]) == 1
    assert len(data["version_chain"]) == 1


def test_node_endpoint_404_for_unknown_node(client):
    resp = client.get("/api/research-brain/nodes/does-not-exist")
    assert resp.status_code == 404
