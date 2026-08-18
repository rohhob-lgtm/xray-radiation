"""Trust-recalculation job enqueueing — deliberately dependency-free.

No import of source_trust_service.py here on purpose: governance_service.py
and conflict_resolver.py call enqueue_recalculation() after recording
evidence/conflicts, and if this module pulled in the scoring service (which
itself imports governance_service for update_node_confidence_from_trust),
that would be a circular import. This module only ever writes a
TrustRecalculationJob row — the actual scoring logic lives one layer up in
source_trust_service.py, imported only by the worker and the API/chat layer.
"""
from __future__ import annotations

from api.db import crud


def enqueue_recalculation(db, research_source_id: str, reason: str) -> None:
    """Enqueue a bounded-worker job rather than recalculating inline —
    callers (governance_service, conflict_resolver) run inside a request/
    mission-processing path and must never do heavy work synchronously.
    Duplicate-pending-job suppression: if this source already has a
    pending/claimed job, don't pile up another one for the same reason."""
    existing = [
        j for j in crud.list_trust_recalculation_jobs(db, status="pending")
        if j.research_source_id == research_source_id and j.reason == reason
    ]
    if existing:
        return
    crud.create_trust_recalculation_job(
        db, research_source_id=research_source_id, reason=reason, status="pending",
    )
