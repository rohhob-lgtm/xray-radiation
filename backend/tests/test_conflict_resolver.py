"""
Conflict Resolver (Phase 2B.2) tests.

Covers: no conflict when claims match/empty, Numerical vs. Terminology
classification, the safety-keyword rule forcing human_review_required
unconditionally (even for a low-severity Version conflict), the
evidence-only "Source" disagreement path (record_node_evidence with
supports=False, where no competing claim text exists), and — the one rule
that must never break — a conflict record is NEVER a substitute for
deleting a claim: both claim_a and claim_b persist, and the underlying
KnowledgeNode/KnowledgeEvidence rows are untouched by conflict detection.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

from api.db.base import SessionLocal
from api.db import crud
from api.services.knowledge_governance import conflict_resolver


def test_detect_conflict_returns_none_when_claims_match():
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(
            s, node_type="Component", label=f"Match {uuid.uuid4()}", approved=True, description="same claim",
        )
        result = conflict_resolver.detect_conflict(s, existing_node=node, new_claim_description="same claim")
        assert result is None
    finally:
        s.close()


def test_detect_conflict_returns_none_when_no_new_claim():
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(s, node_type="Component", label=f"NoNewClaim {uuid.uuid4()}", approved=True)
        assert conflict_resolver.detect_conflict(s, existing_node=node, new_claim_description=None) is None
        assert conflict_resolver.detect_conflict(s, existing_node=node, new_claim_description="   ") is None
    finally:
        s.close()


def test_detect_conflict_numerical_type_and_high_severity():
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(
            s, node_type="Component", label=f"Numeric {uuid.uuid4()}", approved=True,
            description="operates at 160 kVp",
        )
        conflict = conflict_resolver.detect_conflict(s, existing_node=node, new_claim_description="operates at 200 kVp")
        assert conflict is not None
        assert conflict.conflict_type == "Numerical"
        assert conflict.severity == "high"
        assert conflict.resolution_status == "Open"
    finally:
        s.close()


def test_detect_conflict_terminology_fallback_for_generic_type():
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(
            s, node_type="Component", label=f"Generic {uuid.uuid4()}", approved=True,
            description="a scintillator-based detector",
        )
        conflict = conflict_resolver.detect_conflict(s, existing_node=node, new_claim_description="a semiconductor-based detector")
        assert conflict is not None
        assert conflict.conflict_type == "Terminology"
        assert conflict.severity == "medium"
    finally:
        s.close()


def test_safety_keyword_forces_human_review_even_on_version_conflict():
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(
            s, node_type="Component", label=f"Safety {uuid.uuid4()}", approved=True,
            description="maximum permissible dose is 1 mSv/year",
        )
        conflict = conflict_resolver.detect_conflict(
            s, existing_node=node, new_claim_description="maximum permissible dose is 5 mSv/year",
            conflict_type_override="Version",
        )
        assert conflict is not None
        assert conflict.conflict_type == "Version"
        # Version normally auto-resolves and is low severity — safety overrides both.
        assert conflict.severity == "critical"
        assert conflict.human_review_required is True
    finally:
        s.close()


def test_conflict_never_deletes_prior_claim():
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(
            s, node_type="Component", label=f"Preserve {uuid.uuid4()}", approved=True,
            description="claim A text",
        )
        conflict = conflict_resolver.detect_conflict(s, existing_node=node, new_claim_description="claim B text")
        assert conflict.claim_a == "claim A text"
        assert conflict.claim_b == "claim B text"

        # The underlying node's own description is untouched by conflict detection alone.
        reloaded = crud.get_knowledge_node(s, node.id)
        assert reloaded.description == "claim A text"
    finally:
        s.close()


def test_detect_source_disagreement_creates_source_type_conflict_without_claim_text():
    from api.services.research_brain.knowledge_versioning import record_node_evidence
    s = SessionLocal()
    try:
        node = crud.create_knowledge_node(
            s, node_type="Component", label=f"Disputed {uuid.uuid4()}", approved=True,
            description="original claim", confidence=0.7, evidence_count=0,
        )
        record_node_evidence(s, node.id, research_source_id="disputing-source", supports=False, source_quality_score=90.0)

        conflicts = crud.list_knowledge_conflicts(s, subject_node_id=node.id)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "Source"
        assert conflicts[0].claim_a == "original claim"

        # Evidence recording itself never deletes the fact — it's still there, just less confident.
        reloaded = crud.get_knowledge_node(s, node.id)
        assert reloaded.evidence_count == 1
        assert reloaded.confidence < 0.7
    finally:
        s.close()


def test_upsert_node_with_evidence_flags_version_conflict_on_supersede_with_changed_description():
    from api.services.research_brain.knowledge_versioning import supersede_node
    s = SessionLocal()
    try:
        old = crud.create_knowledge_node(
            s, node_type="Component", label=f"Supersede Conflict {uuid.uuid4()}", approved=True,
            description="old description text",
        )
        supersede_node(s, old.id, label="New Label", node_type="Component", description="new description text")

        conflicts = crud.list_knowledge_conflicts(s, subject_node_id=old.id)
        assert len(conflicts) == 1
        assert conflicts[0].conflict_type == "Version"
        assert conflicts[0].resolution_status == "Automatically Resolved"
        assert conflicts[0].claim_a == "old description text"
        assert conflicts[0].claim_b == "new description text"
    finally:
        s.close()
