"""Conflict Resolver — built ON the Knowledge Governance Layer, not a
standalone service. Only ever called from governance_service.py, which is
itself the only path allowed to write to the knowledge graph.

Detects disagreements between an existing node's current claim and a new one
arriving through governance, without ever deleting either claim — both
persist in the resulting KnowledgeConflict row regardless of how it's later
resolved. Safety-critical subjects always require human review,
unconditionally — severity/type classification never overrides that rule.

Classification is intentionally disclosed as heuristic, not semantic:
Numerical detection (regex-extracted values differ) and the safety-keyword
rule are the two reliable classifiers; Procedural/Manufacturer/Standard are
inferred from the subject node's node_type; everything else falls back to
Terminology. detect_source_disagreement() covers the evidence-only
(supports=False, no competing claim text) case as its own "Source" type.
Historical is not automatically distinguished today — a known, disclosed
limitation, not a silent gap.
"""
from __future__ import annotations

import re

from api.db import crud
from api.services.source_trust import jobs as trust_jobs

# Any subject whose label/description touches one of these forces
# human_review_required=True unconditionally, regardless of conflict type or
# severity — per the product spec's explicit safety rule.
SAFETY_KEYWORDS: frozenset[str] = frozenset({
    "dose", "dosage", "exposure", "msv", "mgy", "radiation limit", "safety limit",
    "alara", "shielding", "safe distance", "maximum permissible", "occupational limit",
    "public limit", "lethal", "hazard", "danger", "radiation safety",
})

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?\s*(?:mSv|mGy|keV|MeV|kVp|mA|%|kg|mm|cm)?", re.IGNORECASE)

_TYPE_BY_NODE_TYPE: dict[str, str] = {
    "Procedure": "Procedural",
    "Manufacturer": "Manufacturer",
    "Standard": "Standard",
    # Phase 2B.5 — a Product disagreement is a manufacturer-intelligence
    # conflict, consistent with the existing Manufacturer classification.
    "Product": "Manufacturer",
}


def is_safety_subject(label: str, description_a: str | None, description_b: str | None) -> bool:
    blob = f"{label} {description_a or ''} {description_b or ''}".lower()
    return any(kw in blob for kw in SAFETY_KEYWORDS)


def _extract_numbers(text: str | None) -> set[str]:
    return {m.strip().lower() for m in _NUMBER_RE.findall(text or "") if m.strip()}


def _classify_type(node_type: str, description_a: str, description_b: str) -> str:
    numbers_a = _extract_numbers(description_a)
    numbers_b = _extract_numbers(description_b)
    if numbers_a and numbers_b and numbers_a != numbers_b:
        return "Numerical"
    return _TYPE_BY_NODE_TYPE.get(node_type, "Terminology")


def _severity_for(conflict_type: str, is_safety: bool) -> str:
    if is_safety:
        return "critical"
    if conflict_type == "Numerical":
        return "high"
    if conflict_type == "Version":
        return "low"
    return "medium"


def detect_conflict(
    db,
    *,
    existing_node,
    new_claim_description: str | None,
    new_source_id: str | None = None,
    existing_source_id: str | None = None,
    conflict_type_override: str | None = None,
):
    """Compare an existing node's current claim against a new one. Returns
    the created KnowledgeConflict (both claims persisted) or None when
    there's genuinely nothing to record (no new claim, or claims match)."""
    old_description = (existing_node.description or "").strip()
    new_description = (new_claim_description or "").strip()
    if not new_description or old_description.lower() == new_description.lower():
        return None

    conflict_type = conflict_type_override or _classify_type(existing_node.node_type, old_description, new_description)
    safety = is_safety_subject(existing_node.label, old_description, new_description)
    severity = _severity_for(conflict_type, safety)

    conflict = crud.create_knowledge_conflict(
        db,
        subject_node_id=existing_node.id,
        predicate="description",
        claim_a=old_description,
        claim_b=new_description,
        source_a_id=existing_source_id,
        source_b_id=new_source_id,
        conflict_type=conflict_type,
        severity=severity,
        # Superseding a fact IS the resolution mechanism for a Version
        # conflict — every other type starts Open, awaiting either automatic
        # confidence-weighted evidence accumulation or human review.
        resolution_status="Automatically Resolved" if conflict_type == "Version" else "Open",
        confidence=existing_node.confidence,
        human_review_required=safety,
    )
    # Losing/winning a conflict is a trust signal for both sides — enqueued,
    # never recalculated synchronously inside this call.
    for source_id in (existing_source_id, new_source_id):
        if source_id:
            trust_jobs.enqueue_recalculation(db, source_id, reason="conflict")
    return conflict


def detect_source_disagreement(db, *, existing_node, disputing_source_id: str | None):
    """Fires when evidence arrives explicitly marked supports=False through
    the evidence-only call shape (record_node_evidence/record_edge_evidence
    take a bool, not a competing claim's text) — claim_b is a true statement
    of what happened (a source disagreed), not a fabricated alternative
    claim, since no alternative claim text is available at this call site."""
    safety = is_safety_subject(existing_node.label, existing_node.description, None)
    conflict = crud.create_knowledge_conflict(
        db,
        subject_node_id=existing_node.id,
        predicate="evidence",
        claim_a=existing_node.description or existing_node.label,
        claim_b=f"A newly evaluated source did not support this fact (source_id={disputing_source_id or 'unknown'}).",
        source_a_id=None,
        source_b_id=disputing_source_id,
        conflict_type="Source",
        severity="critical" if safety else "medium",
        resolution_status="Open",
        confidence=existing_node.confidence,
        human_review_required=safety,
    )
    if disputing_source_id:
        trust_jobs.enqueue_recalculation(db, disputing_source_id, reason="conflict")
    return conflict


def get_conflict_trust_snapshot(db, conflict) -> dict:
    """Read-time (not persisted/frozen) lookup of both sides' CURRENT
    effective trust for chat/API display — trust changes over time, so
    freezing it into the conflict row at creation would go stale; this
    always reflects the latest recalculation."""
    from api.db.models import ResearchSource

    def _trust(source_id: str | None) -> dict | None:
        if not source_id:
            return None
        src = db.query(ResearchSource).filter(ResearchSource.id == source_id).first()
        if not src:
            return None
        return {
            "source_id": src.id,
            "domain": src.domain,
            "static_quality_score": src.quality_score,
            "dynamic_trust_score": src.dynamic_trust_score,
            "effective_trust_score": src.effective_trust_score,
            "trust_status": src.trust_status,
        }

    return {
        "source_a": _trust(conflict.source_a_id),
        "source_b": _trust(conflict.source_b_id),
    }
