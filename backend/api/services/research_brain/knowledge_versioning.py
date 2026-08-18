"""Evidence-aware versioning for the existing KnowledgeNode/KnowledgeEdge graph.

Phase 2B.2: these 5 functions are now thin wrappers around
api.services.knowledge_governance.governance_service.governance — the only
path allowed to write to the graph. Signatures and return shapes are
UNCHANGED from Phase 2A/2B.0/2B.1 on purpose: graph_extraction.py,
curiosity_engine.py, and all existing tests call these functions exactly as
before and require zero changes, which is the regression-safety guarantee
this retrofit depends on.

mission_id/extractor_used/parser_version aren't part of these functions'
existing signatures, so governance records them as null for this call path
rather than inventing values — a disclosed, deliberate limitation of
keeping the call sites unchanged this round.

Facts are still never deleted. supersede_node() still creates a new
KnowledgeNode and marks the old one "deprecated" — linked both ways via
supersedes_id/replaced_by_id — so the full history stays queryable
(api.db.crud.get_knowledge_node_version_chain). This module remains
additive: api.services.study_service.approve_study_job()'s own
dedupe-and-reinforce write path is a separate, independently-retrofitted
caller of the same governance layer (see
knowledge_governance.governance_service.upsert_node_with_reinforcement /
upsert_edge_with_reinforcement).
"""
from __future__ import annotations

from api.services.knowledge_governance.governance_service import governance

_SERVICE = "graph_extraction"


def record_node_evidence(
    db, node_id: str, research_source_id: str, *,
    supports: bool = True, source_quality_score: float = 50.0, topic_id: str | None = None,
) -> None:
    """Attach one piece of evidence to an existing KnowledgeNode and update
    its confidence/evidence_count. No-op if the node doesn't exist."""
    governance.record_node_evidence(
        db, node_id, research_source_id, supports=supports,
        source_quality_score=source_quality_score, topic_id=topic_id, created_by_service=_SERVICE,
    )


def record_edge_evidence(
    db, edge_id: str, research_source_id: str, *,
    supports: bool = True, source_quality_score: float = 50.0,
) -> None:
    """Attach one piece of evidence to an existing KnowledgeEdge — same
    confidence/evidence_count bookkeeping as record_node_evidence()."""
    governance.record_edge_evidence(
        db, edge_id, research_source_id, supports=supports,
        source_quality_score=source_quality_score, created_by_service=_SERVICE,
    )


def upsert_node_with_evidence(
    db, *, label: str, node_type: str, description: str | None,
    research_source_id: str, provider_used: str, extractor_confidence: float,
    supports: bool = True, source_quality_score: float = 50.0, topic_id: str | None = None,
):
    """Create-or-version a KnowledgeNode from an extraction result.

    Unlike record_node_evidence() (which only ever versions a node that
    already exists — the shape needed for the paid study_service.py path,
    which creates its own nodes via approve_study_job()), this is the entry
    point for the local_ollama/deterministic layers, which have no separate
    creator: if the node doesn't exist yet, this creates it (seeded with the
    extractor's own confidence and provider_used) before recording evidence.
    """
    return governance.upsert_node_with_evidence(
        db, label=label, node_type=node_type, description=description,
        research_source_id=research_source_id, provider_used=provider_used,
        extractor_confidence=extractor_confidence, supports=supports,
        source_quality_score=source_quality_score, topic_id=topic_id, created_by_service=_SERVICE,
    )


def upsert_edge_with_evidence(
    db, *, from_node_id: str, to_node_id: str, relationship: str,
    research_source_id: str, provider_used: str, extractor_confidence: float,
    supports: bool = True, source_quality_score: float = 50.0,
):
    """Create-or-version a KnowledgeEdge — same rationale as upsert_node_with_evidence()."""
    return governance.upsert_edge_with_evidence(
        db, from_node_id=from_node_id, to_node_id=to_node_id, relationship=relationship,
        research_source_id=research_source_id, provider_used=provider_used,
        extractor_confidence=extractor_confidence, supports=supports,
        source_quality_score=source_quality_score, created_by_service=_SERVICE,
    )


def supersede_node(
    db, old_node_id: str, *, label: str, node_type: str, description: str | None = None,
) -> str | None:
    """Create a new version of a fact. The old node is deprecated, never
    deleted — item #3 of the product spec ("لا يحذف القديمة، بل يحدث النسخة").
    Returns the new node's id, or None if old_node_id doesn't exist."""
    return governance.supersede_node(
        db, old_node_id, label=label, node_type=node_type, description=description, created_by_service=_SERVICE,
    )
