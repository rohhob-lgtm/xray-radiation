"""Phase 2B.9 — Knowledge Health.

A read-only scoring/aggregation layer over signals every prior phase
already produces: coverage (ResearchTopic.coverage_pct, 2B.5), freshness
(TopicResearchMemory.freshness_status, 2B.4), trust
(ResearchSource.effective_trust_score, 2B.3), independent evidence
(ResearchSource.source_family_id, Phase 1), open conflicts
(KnowledgeConflict, 2B.2), provenance (KnowledgeProvenance, 2B.2), failed
extractions (ResearchFile.status, Phase 1), and unresolved curiosity
questions (CuriosityQuestion, 2B.1). Nothing here writes to the knowledge
graph itself — only to this module's own KnowledgeHealthSnapshot cache, via
run_health_audit() on the existing MissionScheduler tick. Chat/API reads are
always cache reads (list_knowledge_health_snapshots), never live
recomputation, so this can never slow down AI Chat.
"""
from __future__ import annotations

import logging

from api.config import settings
from api.db import crud
from api.db.models import (
    CuriosityQuestion, KnowledgeNode, ResearchFile, ResearchSource, ResearchTopic,
)
from api.services.knowledge_governance.conflict_resolver import is_safety_subject
from api.services.research_brain.gap_detector import list_low_coverage_topics

log = logging.getLogger(__name__)

_FRESHNESS_SCORE = {"Fresh": 100.0, "Acceptable": 75.0, "Aging": 40.0, "Outdated": 10.0, "Unknown": 0.0}
_OPEN_QUESTION_STATUSES = ("Suggested", "Approved", "Queued")
_FAILED_FILE_STATUSES = ("rejected", "error")

# Classification bands — deterministic, no ML/LLM.
_CRITICAL_MAX = 25.0
_WEAK_MAX = 45.0
_NEEDS_ATTENTION_MAX = 65.0
_GOOD_MAX = 85.0

# The unconditional safety override (mirrors conflict_resolver's
# human_review_required rule): a safety-subject scope this weak or
# conflicted is Critical regardless of its raw numeric score.
_SAFETY_TRUST_FLOOR = 50.0
_SAFETY_COVERAGE_FLOOR = 50.0


def _independent_and_duplicate_counts(db, node_ids: list[str]) -> tuple[int, int]:
    """Same source_family_id grouping technique
    research_agent_chat_intent.py's single_source_check action already uses
    — families (not raw evidence rows) are what "independent" means, so 5
    pieces of evidence from 1 source family never outscores 2 from distinct
    families."""
    if not node_ids:
        return 0, 0
    total = 0
    families: set[str] = set()
    for node_id in node_ids:
        for e in crud.list_knowledge_evidence(db, node_id=node_id):
            if not e.supports:
                continue
            total += 1
            source = crud.get_research_source(db, e.research_source_id)
            if source:
                families.add(source.source_family_id or source.id)
    return len(families), max(0, total - len(families))


def _avg_trust(db, node_ids: list[str]) -> float | None:
    scores: list[float] = []
    for node_id in node_ids:
        for e in crud.list_knowledge_evidence(db, node_id=node_id):
            if not e.supports:
                continue
            source = crud.get_research_source(db, e.research_source_id)
            if source:
                scores.append(source.effective_trust_score)
    return sum(scores) / len(scores) if scores else None


def _missing_provenance_count(db, node_ids: list[str]) -> int:
    return sum(1 for nid in node_ids if not crud.list_knowledge_provenance(db, node_id=nid))


def _open_conflicts_count(db, node_ids: list[str]) -> int:
    return sum(len(crud.list_knowledge_conflicts(db, status="Open", subject_node_id=nid)) for nid in node_ids)


def _failed_extractions_count(db, mission_ids: set[str]) -> int:
    if not mission_ids:
        return 0
    return (
        db.query(ResearchFile)
        .filter(ResearchFile.mission_id.in_(mission_ids), ResearchFile.status.in_(_FAILED_FILE_STATUSES))
        .count()
    )


def _unresolved_questions_count(db, topic_ids: list[str]) -> int:
    if not topic_ids:
        return 0
    return (
        db.query(CuriosityQuestion)
        .filter(CuriosityQuestion.related_topic_id.in_(topic_ids), CuriosityQuestion.status.in_(_OPEN_QUESTION_STATUSES))
        .count()
    )


def _gather_signals(db, topics: list[ResearchTopic], label_hint: str) -> dict:
    """The shared core: given a set of ResearchTopic rows representing one
    scope (a topic, a domain's topics, a manufacturer's, a product's),
    gather every raw signal. coverage=None / total_nodes=0 means "no data
    yet" — the caller classifies that as Unknown, never a false Critical."""
    topic_ids = [t.id for t in topics]
    mission_ids = {t.mission_id for t in topics}

    coverage_pct = round(sum(t.coverage_pct for t in topics) / len(topics), 1) if topics else None

    nodes: list[KnowledgeNode] = []
    for topic in topics:
        nodes.extend(crud.list_knowledge_nodes_by_topic(db, topic.id, status="current"))
    node_ids = [n.id for n in nodes]

    independent_count, duplicate_count = _independent_and_duplicate_counts(db, node_ids)
    avg_trust = _avg_trust(db, node_ids)
    open_conflicts = _open_conflicts_count(db, node_ids)
    missing_provenance = _missing_provenance_count(db, node_ids)
    failed_extractions = _failed_extractions_count(db, mission_ids)
    unresolved_questions = _unresolved_questions_count(db, topic_ids)

    combined_label = label_hint + " " + " ".join(t.label for t in topics)
    is_safety = is_safety_subject(combined_label, None, None)

    return {
        "coverage_pct": coverage_pct,
        "total_nodes": len(nodes),
        "independent_evidence_count": independent_count,
        "duplicate_evidence_count": duplicate_count,
        "avg_trust": round(avg_trust, 1) if avg_trust is not None else None,
        "open_conflicts": open_conflicts,
        "missing_provenance_count": missing_provenance,
        "failed_extractions": failed_extractions,
        "unresolved_questions": unresolved_questions,
        "is_safety_subject": is_safety,
    }


def score_and_classify(signals: dict) -> tuple[float, str]:
    """One deterministic weighted formula, banded into the 6
    classifications. Independent evidence (not raw evidence_count) drives
    the evidence sub-score, so duplicate evidence never inflates health."""
    coverage_pct = signals.get("coverage_pct")
    total_nodes = signals.get("total_nodes", 0)

    if coverage_pct is None and total_nodes == 0:
        return 0.0, "Unknown"

    coverage_score = coverage_pct if coverage_pct is not None else 0.0
    freshness_score = _FRESHNESS_SCORE.get(signals.get("freshness_status", "Unknown"), 0.0)
    trust_score = signals.get("avg_trust") if signals.get("avg_trust") is not None else 0.0
    evidence_score = min(100.0, signals.get("independent_evidence_count", 0) * 25.0)
    provenance_score = (
        100.0 * (1 - signals.get("missing_provenance_count", 0) / total_nodes) if total_nodes else 100.0
    )
    failed = signals.get("failed_extractions", 0)
    extraction_score = 100.0 if failed == 0 else max(0.0, 100.0 - failed * 20.0)
    conflict_penalty = min(100.0, signals.get("open_conflicts", 0) * 30.0)
    question_penalty = min(30.0, signals.get("unresolved_questions", 0) * 5.0)

    base = (
        0.25 * coverage_score + 0.20 * freshness_score + 0.20 * trust_score
        + 0.15 * evidence_score + 0.10 * provenance_score + 0.10 * extraction_score
    )
    score = max(0.0, min(100.0, base - conflict_penalty - question_penalty))

    if score < _CRITICAL_MAX:
        classification = "Critical"
    elif score < _WEAK_MAX:
        classification = "Weak"
    elif score < _NEEDS_ATTENTION_MAX:
        classification = "Needs Attention"
    elif score < _GOOD_MAX:
        classification = "Good"
    else:
        classification = "Healthy"

    # Unconditional safety override — never a scoring coincidence.
    if signals.get("is_safety_subject") and classification != "Critical":
        weak_trust = trust_score < _SAFETY_TRUST_FLOOR
        weak_coverage = coverage_score < _SAFETY_COVERAGE_FLOOR
        has_conflicts = signals.get("open_conflicts", 0) > 0
        if has_conflicts or weak_trust or weak_coverage:
            classification = "Critical"

    return round(score, 1), classification


def _recommended_actions(signals: dict, low_coverage_suggestions: list[dict], top_question: str | None) -> list[str]:
    """Never invents new advice — only surfaces text gap_detector/curiosity
    already produced, plus short factual statements about the signals."""
    actions: list[str] = []
    for s in low_coverage_suggestions[:3]:
        actions.append(s.get("suggestion", f"Improve coverage of {s.get('label')}"))
    if signals.get("open_conflicts"):
        actions.append(f"Resolve {signals['open_conflicts']} open conflict(s) before treating this as settled.")
    if signals.get("missing_provenance_count"):
        actions.append(f"{signals['missing_provenance_count']} fact(s) are missing source provenance.")
    if top_question:
        actions.append(top_question)
    return actions


def compute_topic_health(db, memory) -> dict:
    topics = db.query(ResearchTopic).filter(ResearchTopic.topic_memory_id == memory.id).all()
    signals = _gather_signals(db, topics, memory.topic_key)
    signals["freshness_status"] = memory.freshness_status
    score, classification = score_and_classify(signals)

    low_coverage: list[dict] = []
    for topic in topics:
        low_coverage.extend(list_low_coverage_topics(db, topic.mission_id, threshold=settings.ai_scientist_low_coverage_threshold))
    questions = crud.list_curiosity_questions(db, status="Suggested")
    top_question = next(
        (q.question_text for q in questions if q.related_topic_id in {t.id for t in topics}), None,
    )
    actions = _recommended_actions(signals, low_coverage, top_question)

    return {
        "scope_type": "Topic", "scope_key": memory.topic_key, "scope_label": memory.topic_key,
        "score": score, "classification": classification, "signals": signals, "recommended_actions": actions,
    }


def compute_domain_health(db, content_category: str) -> dict:
    memories = db.query(crud.TopicResearchMemory).filter(crud.TopicResearchMemory.content_category == content_category).all()
    topics: list[ResearchTopic] = []
    for memory in memories:
        topics.extend(db.query(ResearchTopic).filter(ResearchTopic.topic_memory_id == memory.id).all())
    signals = _gather_signals(db, topics, content_category)
    fresh_scores = [_FRESHNESS_SCORE.get(m.freshness_status, 0.0) for m in memories]
    signals["freshness_status"] = "Fresh" if fresh_scores and (sum(fresh_scores) / len(fresh_scores)) >= 85 else (
        "Unknown" if not fresh_scores else "Aging"
    )
    score, classification = score_and_classify(signals)
    actions = _recommended_actions(signals, [], None)
    return {
        "scope_type": "Domain", "scope_key": content_category, "scope_label": content_category,
        "score": score, "classification": classification, "signals": signals, "recommended_actions": actions,
    }


def _health_for_typed_node(db, node: KnowledgeNode, scope_type: str) -> dict:
    topic_ids = [node.research_topic_id] if node.research_topic_id else []
    topics = db.query(ResearchTopic).filter(ResearchTopic.id.in_(topic_ids)).all() if topic_ids else []
    signals = _gather_signals(db, topics, node.label)
    # A single node's own trust/provenance/conflicts still matter even with
    # no linked ResearchTopic (e.g. a Product node reached via extraction,
    # not planning) — fold the node itself in alongside whatever topics it has.
    if node.id not in [n.id for t in topics for n in crud.list_knowledge_nodes_by_topic(db, t.id, status="current")]:
        extra_independent, extra_dup = _independent_and_duplicate_counts(db, [node.id])
        signals["independent_evidence_count"] += extra_independent
        signals["duplicate_evidence_count"] += extra_dup
        signals["total_nodes"] += 1
        signals["open_conflicts"] += _open_conflicts_count(db, [node.id])
        signals["missing_provenance_count"] += _missing_provenance_count(db, [node.id])
    signals["freshness_status"] = "Unknown"
    if signals["coverage_pct"] is None:
        signals["coverage_pct"] = 50.0 if signals["total_nodes"] else None  # neutral prior — no topic-level coverage concept for a single node
    score, classification = score_and_classify(signals)
    actions = _recommended_actions(signals, [], None)
    return {
        "scope_type": scope_type, "scope_key": node.id, "scope_label": node.label,
        "score": score, "classification": classification, "signals": signals, "recommended_actions": actions,
    }


def compute_manufacturer_health(db, manufacturer_node: KnowledgeNode) -> dict:
    return _health_for_typed_node(db, manufacturer_node, "Manufacturer")


def compute_product_health(db, product_node: KnowledgeNode) -> dict:
    return _health_for_typed_node(db, product_node, "Product")


def run_health_audit(db, batch_size: int | None = None) -> int:
    """The scheduler hook — bounded per tick, same discipline as
    research_memory.sweep_due_refreshes / ai_scientist's sweeps. Only ever
    writes KnowledgeHealthSnapshot rows."""
    if not settings.knowledge_health_enabled:
        return 0
    limit = batch_size if batch_size is not None else settings.knowledge_health_audit_batch_size
    computed = 0

    memories = crud.list_topic_research_memories(db, limit=limit)
    topic_results = []
    for memory in memories:
        result = compute_topic_health(db, memory)
        crud.upsert_knowledge_health_snapshot(db, **result)
        topic_results.append(result)
        computed += 1

    categories = {row[0] for row in db.query(crud.TopicResearchMemory.content_category).distinct().all()}
    for category in categories:
        result = compute_domain_health(db, category)
        crud.upsert_knowledge_health_snapshot(db, **result)
        computed += 1

    manufacturers = db.query(KnowledgeNode).filter(KnowledgeNode.node_type == "Manufacturer", KnowledgeNode.status == "current").limit(limit).all()
    for node in manufacturers:
        result = compute_manufacturer_health(db, node)
        crud.upsert_knowledge_health_snapshot(db, **result)
        computed += 1

    products = db.query(KnowledgeNode).filter(KnowledgeNode.node_type == "Product", KnowledgeNode.status == "current").limit(limit).all()
    for node in products:
        result = compute_product_health(db, node)
        crud.upsert_knowledge_health_snapshot(db, **result)
        computed += 1

    if topic_results:
        overall_score = round(sum(r["score"] for r in topic_results) / len(topic_results), 1)
        _, overall_classification = score_and_classify({"coverage_pct": overall_score, "total_nodes": 1, "avg_trust": overall_score, "freshness_status": "Unknown"})
        crud.upsert_knowledge_health_snapshot(
            db, scope_type="Overall", scope_key="overall", scope_label="Overall Knowledge Health",
            score=overall_score, classification=overall_classification,
            signals={"topics_scored": len(topic_results)},
            recommended_actions=[a for r in topic_results for a in r["recommended_actions"]][:10],
        )
        computed += 1

    return computed


# ── Read helpers — cache reads only, backing both the API and chat commands ──

def get_overall_health(db):
    return crud.get_knowledge_health_snapshot(db, "Overall", "overall")


def get_outdated_topics(db, limit: int = 20):
    return [
        s for s in crud.list_knowledge_health_snapshots(db, scope_type="Topic", limit=200)
        if (s.signals or {}).get("freshness_status") in ("Aging", "Outdated")
    ][:limit]


def get_low_trust_topics(db, limit: int = 20):
    threshold = settings.knowledge_health_low_trust_threshold
    rows = crud.list_knowledge_health_snapshots(db, scope_type="Topic", limit=200)
    scored = [s for s in rows if (s.signals or {}).get("avg_trust") is not None and s.signals["avg_trust"] < threshold]
    return scored[:limit]


def get_safety_critical_gaps(db, limit: int = 20):
    rows = crud.list_knowledge_health_snapshots(db, classification="Critical", limit=200)
    return [s for s in rows if (s.signals or {}).get("is_safety_subject")][:limit]


def get_unresolved_conflicts_summary(db, limit: int = 20):
    """Thin wrapper over the existing, unchanged 2B.2 conflict store."""
    return crud.list_knowledge_conflicts(db, status="Open")[:limit]


def get_weak_manufacturer_coverage(db, limit: int = 20):
    rows = crud.list_knowledge_health_snapshots(db, scope_type="Manufacturer", limit=200)
    return [s for s in rows if s.classification in ("Weak", "Critical")][:limit]


def get_recommended_actions(db, limit: int = 15) -> list[str]:
    overall = get_overall_health(db)
    if overall and overall.recommended_actions:
        return overall.recommended_actions[:limit]
    actions: list[str] = []
    for s in crud.list_knowledge_health_snapshots(db, scope_type="Topic", limit=20):
        actions.extend(s.recommended_actions or [])
    return actions[:limit]
