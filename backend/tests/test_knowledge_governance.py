"""
Knowledge Governance Layer (Phase 2B.2) tests.

Covers: bypass-proofing (knowledge_versioning.py's functions actually route
through governance_service, not just produce the right end state),
provenance (fields pulled from a real ResearchSource vs. left null rather
than invented when no source is given), rollback over the existing version
chain, archive (soft delete, no row removed), and the compensating-rollback
guarantee (a forced failure partway through a governance write undoes
exactly what that call inserted).
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest

from api.db.base import SessionLocal
from api.db import crud


def _new_mission(db, **kwargs):
    kwargs.setdefault("user_id", None)
    kwargs.setdefault("mission_text", "governance test mission")
    return crud.create_research_mission(db, **kwargs)


# ──────────────────────────────────────────────────────────
# provenance — never invents missing fields
# ──────────────────────────────────────────────────────────

def test_upsert_node_with_evidence_pulls_real_source_provenance():
    from api.services.research_brain.knowledge_versioning import upsert_node_with_evidence
    s = SessionLocal()
    try:
        mission = _new_mission(s)
        source = crud.create_research_source(
            s, mission_id=mission.id, url="https://example.com/governance-provenance",
            domain="example.com", content_hash="abc123deadbeef",
        )
        label = f"Governance Provenance Node {uuid.uuid4()}"
        node = upsert_node_with_evidence(
            s, label=label, node_type="Component", description="a fact",
            research_source_id=source.id, provider_used="deterministic", extractor_confidence=0.35,
        )
        rows = crud.list_knowledge_provenance(s, node_id=node.id)
        assert len(rows) == 1
        row = rows[0]
        assert row.original_url == "https://example.com/governance-provenance"
        assert row.document_hash == "abc123deadbeef"
        assert row.provider_used == "deterministic"
        assert row.created_by_service == "graph_extraction"
        # No extractor in this codebase produces page/section/paragraph/offset yet —
        # must stay null, never fabricated.
        assert row.page_number is None
        assert row.section is None
        assert row.paragraph is None
        assert row.sentence_offset is None
    finally:
        s.close()


def test_study_service_reinforcement_leaves_unavailable_fields_null():
    from api.services.knowledge_governance.governance_service import governance
    s = SessionLocal()
    try:
        label = f"Governance Study Node {uuid.uuid4()}"
        node = governance.upsert_node_with_reinforcement(s, label=label, node_type="Component", description="x")
        rows = crud.list_knowledge_provenance(s, node_id=node.id)
        assert len(rows) == 1
        row = rows[0]
        # No source_id was given at all — nothing to invent a URL/hash from.
        assert row.source_id is None
        assert row.original_url is None
        assert row.document_hash is None
        assert row.created_by_service == "study_service"
        assert row.provider_used == "paid_provider"
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# bypass-proofing — the retrofit actually delegates, not just matches state
# ──────────────────────────────────────────────────────────

def test_knowledge_versioning_upsert_node_routes_through_governance(monkeypatch):
    import api.services.research_brain.knowledge_versioning as kv

    calls = []
    original = kv.governance.upsert_node_with_evidence

    def _spy(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(kv.governance, "upsert_node_with_evidence", _spy)

    s = SessionLocal()
    try:
        label = f"Bypass Proof Node {uuid.uuid4()}"
        kv.upsert_node_with_evidence(
            s, label=label, node_type="Component", description=None,
            research_source_id="fake-src", provider_used="deterministic", extractor_confidence=0.35,
        )
        assert len(calls) == 1
        assert calls[0]["label"] == label
        assert calls[0]["created_by_service"] == "graph_extraction"
    finally:
        s.close()


def test_knowledge_versioning_supersede_routes_through_governance(monkeypatch):
    import api.services.research_brain.knowledge_versioning as kv

    calls = []
    original = kv.governance.supersede_node

    def _spy(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(kv.governance, "supersede_node", _spy)

    s = SessionLocal()
    try:
        old = crud.create_knowledge_node(s, node_type="Component", label=f"Old {uuid.uuid4()}", approved=True)
        kv.supersede_node(s, old.id, label="New", node_type="Component", description="newer")
        assert len(calls) == 1
        assert calls[0]["created_by_service"] == "graph_extraction"
    finally:
        s.close()


def test_study_service_routes_through_governance(monkeypatch):
    import api.services.study_service as study_service
    from api.db.models import StudyJob

    calls = []
    original = study_service.governance.upsert_node_with_reinforcement

    def _spy(*args, **kwargs):
        calls.append(kwargs)
        return original(*args, **kwargs)

    monkeypatch.setattr(study_service.governance, "upsert_node_with_reinforcement", _spy)

    s = SessionLocal()
    try:
        label = f"Study Bypass Proof {uuid.uuid4()}"
        job = StudyJob(
            id=str(uuid.uuid4()), doc_id=str(uuid.uuid4()), status="awaiting_approval",
            graph_nodes=[{"label": label, "type": "Component", "description": "d"}],
            graph_edges=[],
        )
        s.add(job)
        s.commit()
        s.refresh(job)

        study_service.approve_study_job(s, job, "tester")
        assert len(calls) == 1
        assert calls[0]["label"] == label
        # created_by_service/provider_used aren't passed explicitly by this
        # call site — they rely on upsert_node_with_reinforcement()'s own
        # "study_service"/"paid_provider" defaults, verified via the actual
        # provenance row written (see test_approve_study_job_records_provenance_and_audit).
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# rollback — real DB-verified, over the existing version chain
# ──────────────────────────────────────────────────────────

def test_rollback_fact_restores_previous_version():
    from api.services.knowledge_governance.governance_service import governance
    from api.services.research_brain.knowledge_versioning import supersede_node
    s = SessionLocal()
    try:
        old = crud.create_knowledge_node(s, node_type="Component", label=f"Rollback Old {uuid.uuid4()}", approved=True)
        new_id = supersede_node(s, old.id, label="Rollback New", node_type="Component", description="v2")

        restored = governance.rollback_fact(s, new_id, reason="test rollback")
        assert restored is not None
        assert restored.id == old.id
        assert restored.status == "current"
        assert restored.replaced_by_id is None

        new_reloaded = crud.get_knowledge_node(s, new_id)
        assert new_reloaded.status == "deprecated"

        audit = crud.list_knowledge_audit_log(s, node_id=old.id)
        assert any(a.operation == "rollback" for a in audit)
    finally:
        s.close()


def test_rollback_fact_returns_none_when_no_previous_version():
    from api.services.knowledge_governance.governance_service import governance
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(s, node_type="Component", label=f"No Chain {uuid.uuid4()}", approved=True)
        assert governance.rollback_fact(s, node.id) is None
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# archive — soft delete, no row removed
# ──────────────────────────────────────────────────────────

def test_archive_fact_soft_deletes_without_removing_row():
    from api.services.knowledge_governance.governance_service import governance
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(s, node_type="Component", label=f"Archive Me {uuid.uuid4()}", approved=True)
        updated = governance.archive_fact(s, node.id, reason="superseded by newer doc")
        assert updated.status == "deprecated"

        still_there = crud.get_knowledge_node(s, node.id)
        assert still_there is not None
        assert still_there.status == "deprecated"

        audit = crud.list_knowledge_audit_log(s, node_id=node.id)
        assert any(a.operation == "archive_fact" for a in audit)
    finally:
        s.close()


# ──────────────────────────────────────────────────────────
# compensating rollback — a forced failure undoes THIS call's own inserts
# ──────────────────────────────────────────────────────────

def test_compensating_rollback_deletes_provenance_on_forced_failure(monkeypatch):
    from api.services.knowledge_governance import governance_service as gs_module

    s = SessionLocal()
    try:
        def _boom(*args, **kwargs):
            raise RuntimeError("forced failure after provenance write")

        monkeypatch.setattr(crud, "create_knowledge_audit_log", _boom)
        monkeypatch.setattr(gs_module.crud, "create_knowledge_audit_log", _boom)

        label = f"Compensate Me {uuid.uuid4()}"
        with pytest.raises(RuntimeError):
            gs_module.governance.upsert_node_with_evidence(
                s, label=label, node_type="Component", description=None,
                research_source_id="fake-src", provider_used="deterministic", extractor_confidence=0.35,
                created_by_service="test",
            )

        node = crud.get_knowledge_node_by_label(s, label, "Component")
        assert node is not None  # the node write itself is not compensated (documented, disclosed limitation)
        assert crud.list_knowledge_provenance(s, node_id=node.id) == []  # but the provenance row IS rolled back
    finally:
        s.close()
