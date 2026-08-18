"""
study_service.approve_study_job() governance retrofit tests.

This function had NO automated test coverage before Phase 2B.2 (confirmed
by grep — every existing reference to study_service only mocks
run_study_pipeline, never exercises approve_study_job's own node/edge
writes). Phase 2B.2 retrofits its two raw KnowledgeNode/KnowledgeEdge
construction blocks to route through KnowledgeGovernanceService while
preserving the exact pre-existing dedupe-by-(label,node_type) +
weight += 0.1 reinforcement behavior — this suite proves both: the old
behavior is bit-for-bit preserved, and provenance/audit are now recorded.
"""
import os
import sys
import types
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

from api.db.base import SessionLocal
from api.db import crud
from api.db.models import StudyJob
from api.services import study_service


def _fake_job(db, nodes, edges, **extra):
    """A real, committed StudyJob row — approve_study_job() calls
    db.commit()/db.refresh(job) internally, which requires a mapped ORM
    instance, not a plain object."""
    job = StudyJob(
        id=str(uuid.uuid4()), doc_id=str(uuid.uuid4()), status="awaiting_approval",
        graph_nodes=nodes, graph_edges=edges,
    )
    for key, value in extra.items():
        setattr(job, key, value)
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def test_approve_study_job_creates_nodes_and_edges():
    s = SessionLocal()
    try:
        label_a = f"Study Node A {uuid.uuid4()}"
        label_b = f"Study Node B {uuid.uuid4()}"
        job = _fake_job(
            s,
            nodes=[
                {"label": label_a, "type": "Component", "description": "a"},
                {"label": label_b, "type": "Component", "description": "b"},
            ],
            edges=[{"from": label_a, "to": label_b, "relationship": "contains"}],
        )
        approved = study_service.approve_study_job(s, job, "tester")

        assert approved.status == "approved"
        assert approved.report_graph_nodes_added == 2
        assert approved.report_graph_edges_added == 1

        node_a = crud.get_knowledge_node_by_label(s, label_a, "Component")
        node_b = crud.get_knowledge_node_by_label(s, label_b, "Component")
        assert node_a is not None and node_b is not None
        edge = crud.get_knowledge_edge_by_relationship(s, node_a.id, node_b.id, "contains")
        assert edge is not None
        assert edge.approved is True
    finally:
        s.close()


def test_approve_study_job_reinforces_existing_node_weight_not_recreate():
    s = SessionLocal()
    try:
        label = f"Reinforce Me {uuid.uuid4()}"
        job1 = _fake_job(s, nodes=[{"label": label, "type": "Component", "description": "first"}], edges=[])
        approved1 = study_service.approve_study_job(s, job1, "tester")
        assert approved1.report_graph_nodes_added == 1

        node_after_first = crud.get_knowledge_node_by_label(s, label, "Component")
        weight_after_first = node_after_first.weight

        job2 = _fake_job(s, nodes=[{"label": label, "type": "Component", "description": "second"}], edges=[])
        approved2 = study_service.approve_study_job(s, job2, "tester")
        assert approved2.report_graph_nodes_added == 0  # reinforced, not recreated

        node_after_second = crud.get_knowledge_node_by_label(s, label, "Component")
        assert node_after_second.id == node_after_first.id
        assert round(node_after_second.weight - weight_after_first, 4) == 0.1
        assert node_after_second.approved is True
    finally:
        s.close()


def test_approve_study_job_skips_edges_with_unknown_or_self_referencing_nodes():
    s = SessionLocal()
    try:
        label_a = f"Edge Guard A {uuid.uuid4()}"
        job = _fake_job(
            s,
            nodes=[{"label": label_a, "type": "Component", "description": "a"}],
            edges=[
                {"from": label_a, "to": "does-not-exist", "relationship": "contains"},
                {"from": label_a, "to": label_a, "relationship": "contains"},
            ],
        )
        approved = study_service.approve_study_job(s, job, "tester")
        assert approved.report_graph_edges_added == 0
    finally:
        s.close()


def test_approve_study_job_records_provenance_and_audit():
    s = SessionLocal()
    try:
        label = f"Provenance Check {uuid.uuid4()}"
        job = _fake_job(s, nodes=[{"label": label, "type": "Component", "description": "d"}], edges=[])
        study_service.approve_study_job(s, job, "tester")

        node = crud.get_knowledge_node_by_label(s, label, "Component")
        prov = crud.list_knowledge_provenance(s, node_id=node.id)
        assert len(prov) == 1
        assert prov[0].created_by_service == "study_service"
        assert prov[0].provider_used == "paid_provider"

        audit = crud.list_knowledge_audit_log(s, node_id=node.id)
        assert any(a.operation == "create_fact" for a in audit)
    finally:
        s.close()


def test_approve_study_job_ignores_blank_labels():
    s = SessionLocal()
    try:
        job = _fake_job(s, nodes=[{"label": "   ", "type": "Component", "description": "d"}], edges=[])
        approved = study_service.approve_study_job(s, job, "tester")
        assert approved.report_graph_nodes_added == 0
    finally:
        s.close()
