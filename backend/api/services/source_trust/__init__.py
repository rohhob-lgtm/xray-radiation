"""Dynamic Source Trust — Phase 2B.3.

SourceTrustService (source_trust_service.py) is the ONLY path allowed to
write ResearchSource.dynamic_trust_score / effective_trust_score /
trust_status / SourceTrustHistory — mirrors knowledge_governance's
"sole gateway" role for its own tables.

Reuses, never duplicates:
  - the existing Static Quality Score (ResearchSource.quality_score,
    api.services.research_agent.quality_scorer) — untouched by this package.
  - KnowledgeGovernanceService for the one thing this feature is allowed to
    change outside its own tables: KnowledgeNode/Edge.confidence, via the
    new update_node_confidence_from_trust() method there.

jobs.py is deliberately dependency-free (no import of
source_trust_service.py) so governance_service.py and conflict_resolver.py
can enqueue a recalculation after recording evidence/conflicts without a
circular import — the actual scoring logic is only imported by the worker
and the API/chat layer.
"""
