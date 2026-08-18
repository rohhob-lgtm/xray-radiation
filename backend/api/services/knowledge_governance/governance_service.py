"""KnowledgeGovernanceService — the only path allowed to write to
KnowledgeNode/KnowledgeEdge.

Both existing write sites delegate here:
  - api.services.research_brain.knowledge_versioning (Phase 2A/2B.0/2B.1) —
    confidence/evidence_count-based reinforcement, used by the autonomous
    research pipeline (graph_extraction.py).
  - api.services.study_service.approve_study_job (pre-Phase-1) —
    weight-based reinforcement, used by the original manual Learning Hub
    teach-and-approve flow.

Every method follows the same shape: validate -> lookup -> conflict-check
(conflict_resolver.py) -> version-decide -> write node/edge -> write
evidence -> write provenance (provenance.py) -> write an append-only audit
row -> return. If anything after the first write raises, `_compensate()`
deletes exactly the rows this call inserted before re-raising — see the
plan doc for why this is compensating-action rollback rather than a DB
SAVEPOINT (this codebase has never used nested transactions, and every
crud.py function commits immediately by long-established convention).

Operations NOT implemented this round (disclosed, not silently missing):
Merge Nodes, Split Nodes.

Phase 2B.3 (Dynamic Source Trust) adds `update_node_confidence_from_trust()`
— the only place a node's confidence is derived from a source's *dynamic*
trust rather than a flat per-evidence delta. Every evidence-recording
method below also enqueues a bounded trust-recalculation job (via
api.services.source_trust.jobs — deliberately dependency-free, no import
of the trust scoring service itself, to avoid a circular import) so a
source's trust score reflects the evidence it's actually contributing to.
"""
from __future__ import annotations

from api.db import crud
from api.services.knowledge_governance import provenance as provenance_mod
from api.services.knowledge_governance import conflict_resolver
from api.services.source_trust import jobs as trust_jobs

_BASE_DELTA = 0.05
_MAX_QUALITY_BONUS = 0.10
_WEIGHT_REINFORCEMENT = 0.1


def _recompute_confidence(current: float, supports: bool, source_quality_score: float) -> float:
    quality_factor = max(0.0, min(1.0, source_quality_score / 100.0))
    delta = _BASE_DELTA + _MAX_QUALITY_BONUS * quality_factor
    if not supports:
        delta = -delta
    return round(max(0.0, min(1.0, current + delta)), 4)


class KnowledgeGovernanceService:

    # ── compensating rollback ────────────────────────────────────────────

    def _compensate(self, db, inserted: dict) -> None:
        """Undo exactly what THIS call inserted, in reverse order. Node/edge
        creations are intentionally NOT deleted here (a partially-reinforced
        or newly-created node is left in place rather than risking deleting
        a fact another concurrent operation may already be referencing) —
        only the auxiliary rows (evidence/provenance/conflict) this call
        added are removed, and the caller sees the exception either way."""
        if inserted.get("provenance_id"):
            try:
                crud.delete_knowledge_provenance(db, inserted["provenance_id"])
            except Exception:
                pass

    # ── evidence-only reinforcement (Phase 2A shape) ────────────────────

    def record_node_evidence(
        self, db, node_id: str, research_source_id: str, *,
        supports: bool = True, source_quality_score: float = 50.0, topic_id: str | None = None,
        mission_id: str | None = None, provider_used: str | None = None,
        extractor_used: str | None = None, parser_version: str | None = None,
        created_by_service: str = "unknown",
    ):
        node = crud.get_knowledge_node(db, node_id)
        if not node:
            return None

        inserted: dict = {}
        try:
            if not supports:
                conflict_resolver.detect_source_disagreement(db, existing_node=node, disputing_source_id=research_source_id)

            crud.create_knowledge_evidence(db, node_id=node_id, research_source_id=research_source_id, supports=supports)
            trust_jobs.enqueue_recalculation(db, research_source_id, reason="new_evidence")

            fields = {
                "evidence_count": node.evidence_count + 1,
                "confidence": _recompute_confidence(node.confidence, supports, source_quality_score),
            }
            if topic_id and not node.research_topic_id:
                fields["research_topic_id"] = topic_id
            updated = crud.update_knowledge_node(db, node_id, **fields)

            prov = provenance_mod.record_provenance(
                db, node_id=node_id, mission_id=mission_id, source_id=research_source_id,
                provider_used=provider_used, extractor_used=extractor_used, parser_version=parser_version,
                knowledge_version=updated.version, created_by_service=created_by_service,
                confidence_at_write=updated.confidence,
            )
            inserted["provenance_id"] = prov.id

            crud.create_knowledge_audit_log(
                db, node_id=node_id, service=created_by_service, operation="register_evidence",
                reason="Evidence recorded" if supports else "Conflicting evidence recorded",
                old_value={"confidence": node.confidence, "evidence_count": node.evidence_count},
                new_value={"confidence": updated.confidence, "evidence_count": updated.evidence_count},
                mission_id=mission_id,
            )
            return updated
        except Exception:
            self._compensate(db, inserted)
            raise

    def record_edge_evidence(
        self, db, edge_id: str, research_source_id: str, *,
        supports: bool = True, source_quality_score: float = 50.0,
        mission_id: str | None = None, provider_used: str | None = None,
        extractor_used: str | None = None, parser_version: str | None = None,
        created_by_service: str = "unknown",
    ):
        edge = crud.get_knowledge_edge(db, edge_id)
        if not edge:
            return None

        inserted: dict = {}
        try:
            crud.create_knowledge_evidence(db, edge_id=edge_id, research_source_id=research_source_id, supports=supports)
            trust_jobs.enqueue_recalculation(db, research_source_id, reason="new_evidence")

            updated = crud.update_knowledge_edge(
                db, edge_id,
                evidence_count=edge.evidence_count + 1,
                confidence=_recompute_confidence(edge.confidence, supports, source_quality_score),
            )

            prov = provenance_mod.record_provenance(
                db, edge_id=edge_id, mission_id=mission_id, source_id=research_source_id,
                provider_used=provider_used, extractor_used=extractor_used, parser_version=parser_version,
                knowledge_version=updated.version, created_by_service=created_by_service,
                confidence_at_write=updated.confidence,
            )
            inserted["provenance_id"] = prov.id

            crud.create_knowledge_audit_log(
                db, edge_id=edge_id, service=created_by_service, operation="register_evidence",
                reason="Edge evidence recorded" if supports else "Conflicting edge evidence recorded",
                old_value={"confidence": edge.confidence, "evidence_count": edge.evidence_count},
                new_value={"confidence": updated.confidence, "evidence_count": updated.evidence_count},
                mission_id=mission_id,
            )
            return updated
        except Exception:
            self._compensate(db, inserted)
            raise

    # ── create-or-reinforce, confidence style (2A/2B.0/2B.1 callers) ────

    def upsert_node_with_evidence(
        self, db, *, label: str, node_type: str, description: str | None,
        research_source_id: str, provider_used: str, extractor_confidence: float,
        supports: bool = True, source_quality_score: float = 50.0, topic_id: str | None = None,
        mission_id: str | None = None, extractor_used: str | None = None,
        parser_version: str | None = None, created_by_service: str = "graph_extraction",
    ):
        existing = crud.get_knowledge_node_by_label(db, label, node_type)
        if existing:
            if description and description.strip():
                conflict_resolver.detect_conflict(
                    db, existing_node=existing, new_claim_description=description,
                    new_source_id=research_source_id,
                )
            return self.record_node_evidence(
                db, existing.id, research_source_id,
                supports=supports, source_quality_score=source_quality_score, topic_id=topic_id,
                mission_id=mission_id, provider_used=provider_used, extractor_used=extractor_used,
                parser_version=parser_version, created_by_service=created_by_service,
            )

        inserted: dict = {}
        try:
            node = crud.create_knowledge_node(
                db, node_type=node_type, label=label, description=description,
                approved=True, confidence=max(0.0, min(1.0, extractor_confidence)),
                evidence_count=1, provider_used=provider_used, research_topic_id=topic_id,
            )
            inserted["node_id"] = node.id
            crud.create_knowledge_evidence(db, node_id=node.id, research_source_id=research_source_id, supports=supports)
            trust_jobs.enqueue_recalculation(db, research_source_id, reason="new_evidence")

            prov = provenance_mod.record_provenance(
                db, node_id=node.id, mission_id=mission_id, source_id=research_source_id,
                provider_used=provider_used, extractor_used=extractor_used, parser_version=parser_version,
                knowledge_version=node.version, created_by_service=created_by_service,
                confidence_at_write=node.confidence,
            )
            inserted["provenance_id"] = prov.id

            crud.create_knowledge_audit_log(
                db, node_id=node.id, service=created_by_service, operation="create_fact",
                reason=f"New fact created: {label}", old_value=None,
                new_value={"label": label, "node_type": node_type, "description": description},
                mission_id=mission_id,
            )
            return node
        except Exception:
            self._compensate(db, inserted)
            raise

    def upsert_edge_with_evidence(
        self, db, *, from_node_id: str, to_node_id: str, relationship: str,
        research_source_id: str, provider_used: str, extractor_confidence: float,
        supports: bool = True, source_quality_score: float = 50.0,
        mission_id: str | None = None, extractor_used: str | None = None,
        parser_version: str | None = None, created_by_service: str = "graph_extraction",
    ):
        if from_node_id == to_node_id:
            return None

        existing = crud.get_knowledge_edge_by_relationship(db, from_node_id, to_node_id, relationship)
        if existing:
            return self.record_edge_evidence(
                db, existing.id, research_source_id, supports=supports, source_quality_score=source_quality_score,
                mission_id=mission_id, provider_used=provider_used, extractor_used=extractor_used,
                parser_version=parser_version, created_by_service=created_by_service,
            )

        inserted: dict = {}
        try:
            edge = crud.create_knowledge_edge(
                db, from_node_id=from_node_id, to_node_id=to_node_id, relationship=relationship,
                approved=True, confidence=max(0.0, min(1.0, extractor_confidence)),
                evidence_count=1, provider_used=provider_used,
            )
            inserted["edge_id"] = edge.id
            crud.create_knowledge_evidence(db, edge_id=edge.id, research_source_id=research_source_id, supports=supports)
            trust_jobs.enqueue_recalculation(db, research_source_id, reason="new_evidence")

            prov = provenance_mod.record_provenance(
                db, edge_id=edge.id, mission_id=mission_id, source_id=research_source_id,
                provider_used=provider_used, extractor_used=extractor_used, parser_version=parser_version,
                knowledge_version=edge.version, created_by_service=created_by_service,
                confidence_at_write=edge.confidence,
            )
            inserted["provenance_id"] = prov.id

            crud.create_knowledge_audit_log(
                db, edge_id=edge.id, service=created_by_service, operation="create_edge",
                reason=f"New edge created: {relationship}", old_value=None,
                new_value={"from_node_id": from_node_id, "to_node_id": to_node_id, "relationship": relationship},
                mission_id=mission_id,
            )
            return edge
        except Exception:
            self._compensate(db, inserted)
            raise

    # ── version / supersede (never delete) ───────────────────────────────

    def supersede_node(
        self, db, old_node_id: str, *, label: str, node_type: str, description: str | None = None,
        mission_id: str | None = None, created_by_service: str = "graph_extraction", reason: str = "",
    ) -> str | None:
        old = crud.get_knowledge_node(db, old_node_id)
        if not old:
            return None

        inserted: dict = {}
        try:
            if description and description.strip():
                conflict_resolver.detect_conflict(
                    db, existing_node=old, new_claim_description=description,
                    conflict_type_override="Version",
                )

            new_node = crud.create_knowledge_node(
                db, node_type=node_type, label=label, description=description, approved=True,
                version=old.version + 1, confidence=old.confidence, evidence_count=0,
                status="current", supersedes_id=old.id, research_topic_id=old.research_topic_id,
            )
            inserted["node_id"] = new_node.id
            crud.update_knowledge_node(db, old.id, status="deprecated", replaced_by_id=new_node.id)

            prov = provenance_mod.record_provenance(
                db, node_id=new_node.id, mission_id=mission_id, created_by_service=created_by_service,
                knowledge_version=new_node.version, confidence_at_write=new_node.confidence,
            )
            inserted["provenance_id"] = prov.id

            crud.create_knowledge_audit_log(
                db, node_id=new_node.id, service=created_by_service, operation="version_fact",
                reason=reason or f"Superseded {old_node_id}",
                old_value={"id": old.id, "description": old.description, "version": old.version},
                new_value={"id": new_node.id, "description": description, "version": new_node.version},
                mission_id=mission_id,
            )
            return new_node.id
        except Exception:
            self._compensate(db, inserted)
            raise

    # ── weight-based reinforcement (study_service.py caller) ─────────────

    def upsert_node_with_reinforcement(
        self, db, *, label: str, node_type: str, description: str | None,
        source_doc_id: str | None = None, study_job_id: str | None = None,
        mission_id: str | None = None, provider_used: str = "paid_provider",
        extractor_used: str | None = None, parser_version: str | None = None,
        created_by_service: str = "study_service",
    ):
        """Preserves study_service.approve_study_job()'s exact pre-existing
        dedupe-by-(label,node_type) + weight += 0.1 reinforcement behavior —
        this is NOT the confidence/evidence_count model the other methods
        use; deliberately kept separate so each caller's established
        semantics stay exactly what they were before this retrofit."""
        existing = crud.get_knowledge_node_by_label(db, label, node_type)
        if existing:
            inserted: dict = {}
            try:
                old_weight = existing.weight
                updated = crud.update_knowledge_node(db, existing.id, approved=True, weight=existing.weight + _WEIGHT_REINFORCEMENT)

                prov = provenance_mod.record_provenance(
                    db, node_id=existing.id, mission_id=mission_id, provider_used=provider_used,
                    extractor_used=extractor_used, parser_version=parser_version,
                    knowledge_version=updated.version, created_by_service=created_by_service,
                    confidence_at_write=updated.confidence,
                )
                inserted["provenance_id"] = prov.id

                crud.create_knowledge_audit_log(
                    db, node_id=existing.id, service=created_by_service, operation="update_fact",
                    reason="Reinforced by repeat study extraction",
                    old_value={"weight": old_weight}, new_value={"weight": updated.weight},
                    mission_id=mission_id,
                )
                return updated
            except Exception:
                self._compensate(db, inserted)
                raise

        inserted = {}
        try:
            node = crud.create_knowledge_node(
                db, node_type=node_type, label=label, description=description or None,
                source_doc_id=source_doc_id, study_job_id=study_job_id, approved=True,
                provider_used=provider_used,
            )
            inserted["node_id"] = node.id

            prov = provenance_mod.record_provenance(
                db, node_id=node.id, mission_id=mission_id, provider_used=provider_used,
                extractor_used=extractor_used, parser_version=parser_version,
                knowledge_version=node.version, created_by_service=created_by_service,
                confidence_at_write=node.confidence,
            )
            inserted["provenance_id"] = prov.id

            crud.create_knowledge_audit_log(
                db, node_id=node.id, service=created_by_service, operation="create_fact",
                reason=f"New fact created from study pipeline: {label}", old_value=None,
                new_value={"label": label, "node_type": node_type, "description": description},
                mission_id=mission_id,
            )
            return node
        except Exception:
            self._compensate(db, inserted)
            raise

    def upsert_edge_with_reinforcement(
        self, db, *, from_node_id: str, to_node_id: str, relationship: str,
        mission_id: str | None = None, provider_used: str = "paid_provider",
        extractor_used: str | None = None, parser_version: str | None = None,
        created_by_service: str = "study_service",
    ):
        if from_node_id == to_node_id:
            return None

        existing = crud.get_knowledge_edge_by_relationship(db, from_node_id, to_node_id, relationship)
        if existing:
            inserted: dict = {}
            try:
                old_weight = existing.weight
                updated = crud.update_knowledge_edge(db, existing.id, approved=True, weight=existing.weight + _WEIGHT_REINFORCEMENT)

                prov = provenance_mod.record_provenance(
                    db, edge_id=existing.id, mission_id=mission_id, provider_used=provider_used,
                    extractor_used=extractor_used, parser_version=parser_version,
                    knowledge_version=updated.version, created_by_service=created_by_service,
                    confidence_at_write=updated.confidence,
                )
                inserted["provenance_id"] = prov.id

                crud.create_knowledge_audit_log(
                    db, edge_id=existing.id, service=created_by_service, operation="update_edge",
                    reason="Reinforced by repeat study extraction",
                    old_value={"weight": old_weight}, new_value={"weight": updated.weight},
                    mission_id=mission_id,
                )
                return updated
            except Exception:
                self._compensate(db, inserted)
                raise

        inserted = {}
        try:
            edge = crud.create_knowledge_edge(
                db, from_node_id=from_node_id, to_node_id=to_node_id, relationship=relationship,
                approved=True, provider_used=provider_used,
            )
            inserted["edge_id"] = edge.id

            prov = provenance_mod.record_provenance(
                db, edge_id=edge.id, mission_id=mission_id, provider_used=provider_used,
                extractor_used=extractor_used, parser_version=parser_version,
                knowledge_version=edge.version, created_by_service=created_by_service,
                confidence_at_write=edge.confidence,
            )
            inserted["provenance_id"] = prov.id

            crud.create_knowledge_audit_log(
                db, edge_id=edge.id, service=created_by_service, operation="create_edge",
                reason=f"New edge created from study pipeline: {relationship}", old_value=None,
                new_value={"from_node_id": from_node_id, "to_node_id": to_node_id, "relationship": relationship},
                mission_id=mission_id,
            )
            return edge
        except Exception:
            self._compensate(db, inserted)
            raise

    # ── archive (soft delete) + rollback ─────────────────────────────────

    def archive_fact(self, db, node_id: str, *, reason: str, created_by_service: str = "unknown", mission_id: str | None = None):
        """Soft-delete: status -> 'deprecated', no replacement, no row
        removed. Distinct from supersede_node() (which links a replacement)."""
        node = crud.get_knowledge_node(db, node_id)
        if not node:
            return None
        old_status = node.status
        updated = crud.update_knowledge_node(db, node_id, status="deprecated")
        crud.create_knowledge_audit_log(
            db, node_id=node_id, service=created_by_service, operation="archive_fact",
            reason=reason, old_value={"status": old_status}, new_value={"status": "deprecated"},
            mission_id=mission_id,
        )
        return updated

    def rollback_fact(self, db, node_id: str, *, reason: str = "", created_by_service: str = "unknown", mission_id: str | None = None):
        """Revert to the immediately-previous version in the supersede
        chain: the given node is demoted to 'deprecated', the version it
        superseded is restored to 'current'. Uses the existing, already-
        tested version-chain data (crud.get_knowledge_node_version_chain) —
        no new storage, purely a status flip on both ends."""
        node = crud.get_knowledge_node(db, node_id)
        if not node or not node.supersedes_id:
            return None
        previous = crud.get_knowledge_node(db, node.supersedes_id)
        if not previous:
            return None

        crud.update_knowledge_node(db, node.id, status="deprecated")
        restored = crud.update_knowledge_node(db, previous.id, status="current", replaced_by_id=None)

        crud.create_knowledge_audit_log(
            db, node_id=previous.id, service=created_by_service, operation="rollback",
            reason=reason or f"Rolled back from version {node.version} to {previous.version}",
            old_value={"id": node.id, "version": node.version, "status": "current"},
            new_value={"id": previous.id, "version": previous.version, "status": "current"},
            mission_id=mission_id,
        )
        return restored

    # ── Dynamic Source Trust (Phase 2B.3) ────────────────────────────────

    def update_node_confidence_from_trust(self, db, node_id: str, *, reason: str, created_by_service: str) -> None:
        """The only path allowed to derive a node's confidence from its
        evidence sources' CURRENT effective trust (as opposed to the flat
        per-evidence delta record_node_evidence() uses). Called by
        source_trust_service.recalculate() after a source's trust changes
        — never called directly by anything outside that cascade.

        Independent-evidence count uses source_family_id grouping (10
        copies of one paper = 1 family, never 10 independent votes).
        Safety-critical nodes (conflict_resolver.is_safety_subject) are
        hard-capped below high confidence with fewer than 2 independent
        families, regardless of how high any single source's trust is —
        the concrete mechanism behind "a single source cannot make a
        safety fact highly confident."
        """
        from api.services.source_trust.source_trust_service import compute_source_family_id

        node = crud.get_knowledge_node(db, node_id)
        if not node:
            return

        supporting = [e for e in crud.list_knowledge_evidence(db, node_id=node_id) if e.supports]
        if not supporting:
            return

        families: dict[str, float] = {}
        for e in supporting:
            src = crud.get_research_source(db, e.research_source_id)
            if not src:
                continue
            fam = src.source_family_id or compute_source_family_id(src)
            families[fam] = max(families.get(fam, 0.0), src.effective_trust_score)
        if not families:
            return

        independent_count = len(families)
        avg_trust = sum(families.values()) / independent_count

        has_open_conflict = any(
            c.resolution_status == "Open" for c in crud.list_knowledge_conflicts(db, subject_node_id=node_id)
        )

        base = avg_trust / 100.0
        corroboration_bonus = min(0.15, 0.05 * (independent_count - 1))
        conflict_penalty = 0.1 if has_open_conflict else 0.0
        confidence = max(0.0, min(1.0, base + corroboration_bonus - conflict_penalty))

        if conflict_resolver.is_safety_subject(node.label, node.description, None) and independent_count < 2:
            confidence = min(confidence, 0.6)

        old_confidence = node.confidence
        updated = crud.update_knowledge_node(db, node_id, confidence=round(confidence, 4))

        crud.create_knowledge_audit_log(
            db, node_id=node_id, service=created_by_service, operation="update_fact",
            reason=reason,
            old_value={"confidence": old_confidence},
            new_value={
                "confidence": updated.confidence,
                "independent_evidence_count": independent_count,
                "avg_source_trust": round(avg_trust, 2),
            },
            mission_id=None,
        )


governance = KnowledgeGovernanceService()
