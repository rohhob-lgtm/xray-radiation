"""SourceTrustService — Phase 2B.3.

The ONLY path allowed to write ResearchSource.dynamic_trust_score /
effective_trust_score / trust_status / trust_signal_summary /
source_family_id / last_trust_calculated_at, and the only path allowed to
create SourceTrustHistory rows. Mirrors KnowledgeGovernanceService's
"sole gateway" role for its own tables.

Static Quality Score (ResearchSource.quality_score) is reused as-is —
computed once by api.services.research_agent.quality_scorer and never
touched here. Dynamic Trust Score starts neutral (50.0 — "Unproven", never
a low default for a brand-new source) and moves with real DB-backed
signals: independent corroboration, extraction outcomes, conflicts, and
bounded user review. Effective Trust Score blends the two, then applies the
structural safety caps from the product spec (§7): a source cannot reach
"Authoritative" on dynamic behavior alone if its static score never
qualified structurally, and a manufacturer-domain source needs independent
corroboration to get there at all.

Every calculation is deterministic (DB queries + arithmetic) — no LLM, no
paid provider, fully Free-Mode compliant by construction, not by a guard
that could be bypassed.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from urllib.parse import urlparse

from api.config import settings
from api.db import crud
from api.services.research_agent.discovery import TRUSTED_DOMAINS

CURRENT_TRUST_ALGORITHM_VERSION = 1

# Ordered high -> low; _status_for() walks this to find the first threshold met.
_STATUS_THRESHOLDS: list[tuple[float, str]] = [
    (85.0, "authoritative"),
    (70.0, "high_trust"),
    (55.0, "trusted"),
    (40.0, "useful"),
    (25.0, "questionable"),
    (0.0, "low_trust"),
]
_AUTHORITATIVE_FLOOR = _STATUS_THRESHOLDS[0][0]

# quality_scorer._QUALITY_LABELS' own "authoritative" threshold — a source
# whose STATIC score never reached this band can never be promoted to
# Authoritative by dynamic behavior alone (product spec §7).
_STATIC_AUTHORITATIVE_FLOOR = 85.0

# Reused verbatim from discovery.py's own manufacturer entries — never a
# separately-invented list.
_MANUFACTURER_DOMAINS = {
    d for d in TRUSTED_DOMAINS
    if any(m in d for m in ("rapiscansystems", "smithsdetection", "nuctech", "leidos", "astrophysicsinc"))
}

_DOI_RE = re.compile(r"doi\.org/(10\.\d{4,9}/[^\s?#]+)", re.IGNORECASE)

# Bounded per-signal deltas — every one logged to SourceTrustHistory's
# reason_code/trust_signal_summary, never silent.
_DELTA: dict[str, float] = {
    "EXTRACTION_SUCCESS": 2.0,
    "EXTRACTION_FAILURE": -3.0,
    "INDEPENDENT_CORROBORATION": 4.0,  # per distinct corroborating family, capped below
    "CONFLICT_LOST_TO_STRONGER": -6.0,
    "CONFLICT_WON": 3.0,
    "SUPERSEDED_BY_NEWER_VERSION": -4.0,
    "USER_REVIEW_TRUSTED": 5.0,
    "USER_REVIEW_USEFUL": 2.0,
    "USER_REVIEW_QUESTIONABLE": -5.0,
    "USER_REVIEW_REJECTED": -10.0,
}
_MAX_CORROBORATION_BONUS = 15.0
_MAX_REVIEW_CONTRIBUTION = 10.0  # bounded regardless of how many users reviewed


def _slugify(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def is_manufacturer_domain(url: str, manufacturer_name: str | None = None) -> bool:
    """Phase 2B.5: generalized beyond the hardcoded 5-name _MANUFACTURER_DOMAINS
    set — a brand-new manufacturer's own site (discovered via the now-widened
    discovery.py, not pre-listed) is still recognized as a manufacturer
    domain when the mission's detected manufacturer name slug-matches the
    host, so the "manufacturer domain needs independent corroboration"
    safety cap below still applies to it. Existing callers with no
    manufacturer_name arg are unaffected (identical behavior)."""
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host in _MANUFACTURER_DOMAINS:
        return True
    if manufacturer_name:
        slug = _slugify(manufacturer_name)
        return bool(slug) and slug in host.replace("-", "")
    return False


def extract_doi(url: str) -> str | None:
    """Never invents a DOI — only extracts one already present in the URL text."""
    m = _DOI_RE.search(url)
    return m.group(1).rstrip("/") if m else None


def compute_source_family_id(source) -> str:
    """Deterministic independence-grouping key. content_hash (exact same
    file) beats source_doi (same paper, different host) beats the source's
    own id (a family of one) — never a fuzzy/invented grouping."""
    if source.content_hash:
        return source.content_hash
    if source.source_doi:
        return f"doi:{source.source_doi}"
    return source.id


def _status_for(effective: float, *, evidence_count: int, capped: bool, review_status: str | None) -> str:
    if review_status == "Rejected":
        return "rejected"
    if evidence_count == 0:
        return "unproven"
    score = min(effective, _AUTHORITATIVE_FLOOR - 0.01) if capped else effective
    for threshold, label in _STATUS_THRESHOLDS:
        if score >= threshold:
            return label
    return "low_trust"


def _independent_evidence_families(db, node_id: str) -> set[str]:
    """Distinct source_family_id values among a node's SUPPORTING evidence
    — 10 rows citing the same content_hash count as 1."""
    families: set[str] = set()
    for ev in crud.list_knowledge_evidence(db, node_id=node_id):
        if not ev.supports:
            continue
        src = crud.get_research_source(db, ev.research_source_id)
        if not src:
            continue
        families.add(src.source_family_id or src.id)
    return families


def initialize_trust(db, source) -> None:
    """Called once at source creation (crawler_orchestrator.py, right after
    create_research_source) — cheap and synchronous since a brand-new
    source has zero evidence yet, no DB scan needed. Never writes a
    SourceTrustHistory row for this initial snapshot — history starts at
    the first real recalculation."""
    family_id = compute_source_family_id(source)
    effective = round(settings.trust_static_weight * source.quality_score + settings.trust_dynamic_weight * 50.0, 2)
    if source.quality_score < _STATIC_AUTHORITATIVE_FLOOR:
        effective = min(effective, _AUTHORITATIVE_FLOOR - 0.01)
    crud.update_research_source(
        db, source.id,
        source_family_id=family_id,
        dynamic_trust_score=50.0,
        effective_trust_score=round(max(0.0, min(100.0, effective)), 2),
        trust_status="unproven",
        trust_algorithm_version=CURRENT_TRUST_ALGORITHM_VERSION,
        last_trust_calculated_at=datetime.now(timezone.utc),
        trust_signal_summary=[],
    )


def recalculate(
    db, source_id: str, *, reason: str, service_name: str,
    related_mission_id: str | None = None, related_evidence_id: str | None = None,
    related_conflict_id: str | None = None, related_user_id: str | None = None,
):
    """The real scoring pass. Idempotent — a pure function of current DB
    state, safe to run twice with no drift (dynamic score is recomputed
    from scratch each time, not accumulated). Cascades to node confidence
    via governance.update_node_confidence_from_trust() — never touches
    KnowledgeNode itself."""
    from api.services.knowledge_governance.governance_service import governance

    source = crud.get_research_source(db, source_id)
    if not source:
        return None

    old_static, old_dynamic, old_effective = source.quality_score, source.dynamic_trust_score, source.effective_trust_score

    family_id = compute_source_family_id(source)

    signals: list[dict] = []
    dynamic = 50.0

    own_evidence = crud.list_knowledge_evidence_by_source(db, source.id)
    supporting_node_ids = {e.node_id for e in own_evidence if e.supports and e.node_id}

    if own_evidence:
        dynamic += _DELTA["EXTRACTION_SUCCESS"]
        signals.append({"reason_code": "EXTRACTION_SUCCESS", "delta": _DELTA["EXTRACTION_SUCCESS"]})
    else:
        dynamic += _DELTA["EXTRACTION_FAILURE"]
        signals.append({"reason_code": "EXTRACTION_FAILURE", "delta": _DELTA["EXTRACTION_FAILURE"]})

    corroboration_bonus = 0.0
    for node_id in supporting_node_ids:
        other_families = _independent_evidence_families(db, node_id) - {family_id}
        if other_families:
            corroboration_bonus += _DELTA["INDEPENDENT_CORROBORATION"] * min(len(other_families), 3)
    corroboration_bonus = min(corroboration_bonus, _MAX_CORROBORATION_BONUS)
    if corroboration_bonus:
        dynamic += corroboration_bonus
        signals.append({"reason_code": "INDEPENDENT_CORROBORATION", "delta": round(corroboration_bonus, 2)})

    conflicts = [
        c for c in crud.list_knowledge_conflicts(db)
        if c.source_a_id == source.id or c.source_b_id == source.id
    ]
    for c in conflicts:
        if c.conflict_type == "Version":
            continue  # supersession is its own signal below, not a generic conflict penalty
        other_id = c.source_b_id if c.source_a_id == source.id else c.source_a_id
        other = crud.get_research_source(db, other_id) if other_id else None
        if other and other.effective_trust_score > source.effective_trust_score:
            dynamic += _DELTA["CONFLICT_LOST_TO_STRONGER"]
            signals.append({"reason_code": "CONFLICT_LOST_TO_STRONGER", "delta": _DELTA["CONFLICT_LOST_TO_STRONGER"]})
        elif other and other.effective_trust_score <= source.effective_trust_score:
            dynamic += _DELTA["CONFLICT_WON"]
            signals.append({"reason_code": "CONFLICT_WON", "delta": _DELTA["CONFLICT_WON"]})

    reviews = crud.list_source_user_reviews(db, source_id=source.id)
    review_delta = 0.0
    rejected_review = False
    for r in reviews:
        if not r.review_status:
            continue
        if r.review_status == "Rejected":
            rejected_review = True
        code = f"USER_REVIEW_{r.review_status.upper()}"
        if code in _DELTA:
            review_delta += _DELTA[code]
    review_delta = max(-_MAX_REVIEW_CONTRIBUTION, min(_MAX_REVIEW_CONTRIBUTION, review_delta))
    if review_delta:
        dynamic += review_delta
        signals.append({"reason_code": "USER_REVIEW_AGGREGATE", "delta": round(review_delta, 2)})

    dynamic = round(max(0.0, min(100.0, dynamic)), 2)

    effective = settings.trust_static_weight * source.quality_score + settings.trust_dynamic_weight * dynamic
    # Phase 2B.5: pass the mission's detected manufacturer (novel names
    # included, not just the hardcoded 5-domain list) so a brand-new
    # manufacturer's own site still gets the Authoritative-without-
    # corroboration cap below.
    mission = crud.get_research_mission(db, source.mission_id) if source.mission_id else None
    manufacturer_name = getattr(mission, "detected_manufacturer", None) if mission else None
    capped = source.quality_score < _STATIC_AUTHORITATIVE_FLOOR or (
        is_manufacturer_domain(source.url, manufacturer_name) and not corroboration_bonus
    )
    if capped:
        effective = min(effective, _AUTHORITATIVE_FLOOR - 0.01)
    effective = round(max(0.0, min(100.0, effective)), 2)

    status = _status_for(
        effective, evidence_count=len(own_evidence), capped=capped,
        review_status="Rejected" if rejected_review else None,
    )

    if signals:
        dominant = max(signals, key=lambda s: abs(s["delta"]))
        reason_code = dominant["reason_code"] if len(signals) == 1 else "COMPOSITE_RECALC"
        description = f"Recalculated ({reason}): " + "; ".join(f"{s['reason_code']}({s['delta']:+.1f})" for s in signals)
    else:
        reason_code = "RECALC_NO_CHANGE"
        description = f"Recalculated ({reason}): no active signals"

    crud.update_research_source(
        db, source.id,
        source_family_id=family_id,
        dynamic_trust_score=dynamic,
        effective_trust_score=effective,
        trust_status=status,
        trust_algorithm_version=CURRENT_TRUST_ALGORITHM_VERSION,
        last_trust_calculated_at=datetime.now(timezone.utc),
        trust_signal_summary=signals[:10],
    )

    crud.create_source_trust_history(
        db,
        source_id=source.id,
        old_static_score=old_static, new_static_score=source.quality_score,
        old_dynamic_score=old_dynamic, new_dynamic_score=dynamic,
        old_effective_score=old_effective, new_effective_score=effective,
        delta=round(effective - old_effective, 2),
        reason_code=reason_code,
        reason_description=description,
        related_mission_id=related_mission_id,
        related_evidence_id=related_evidence_id,
        related_conflict_id=related_conflict_id,
        related_user_id=related_user_id,
        service_name=service_name,
        calculation_version=CURRENT_TRUST_ALGORITHM_VERSION,
    )

    for node_id in supporting_node_ids:
        governance.update_node_confidence_from_trust(
            db, node_id, reason=f"source {source.id} trust recalculated ({reason})",
            created_by_service="source_trust_service",
        )

    return crud.get_research_source(db, source.id)


def submit_user_review(db, source_id: str, user_id: str, status: str, reason: str = "", note: str = ""):
    valid = {"Trusted", "Useful", "Questionable", "Rejected"}
    if status not in valid:
        raise ValueError(f"review status must be one of {sorted(valid)}")
    source = crud.get_research_source(db, source_id)
    if not source:
        return None
    crud.upsert_source_user_review(db, source_id, user_id, review_status=status, reason=reason, note=note)
    return recalculate(db, source_id, reason="user_review", service_name="source_trust_service", related_user_id=user_id)


def reset_user_review(db, source_id: str, user_id: str):
    source = crud.get_research_source(db, source_id)
    if not source:
        return None
    existing = crud.get_source_user_review(db, source_id, user_id)
    if not existing or existing.review_status is None:
        return source
    crud.upsert_source_user_review(db, source_id, user_id, review_status=None, reason="", note="")
    return recalculate(db, source_id, reason="user_review_reset", service_name="source_trust_service", related_user_id=user_id)
