"""Knowledge Governance Layer — Phase 2B.2.

KnowledgeGovernanceService (governance_service.py) is the ONLY path allowed
to write to KnowledgeNode/KnowledgeEdge. Both existing write sites —
api.services.research_brain.knowledge_versioning (Phase 2A/2B.0/2B.1) and
api.services.study_service.approve_study_job (the original, pre-Phase-1
Learning Hub flow) — are retrofitted to delegate to it rather than writing
directly, so neither the data model nor any of the 95 tests written for
those two paths needed to change.

Every governance write also records:
  - provenance.py    — where the fact/edge came from (mission/source/
                        provider/extractor/parser version/document hash/...,
                        never inventing fields the extractor didn't supply)
  - conflict_resolver.py — detects and records disagreements between claims
                        without ever deleting either claim
  - an append-only KnowledgeAuditLog row (who/service/when/why/old/new)
"""
