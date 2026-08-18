"""Knowledge Gap Detector — per-topic coverage % over a mission's ResearchTopic tree.

coverage_pct = min(100, evidence gathered for the topic / the plan's own
estimate for that topic * 100) — reuses ResearchTopic.estimates (Sub-Phase
2A planner.py) and KnowledgeNode.evidence_count (knowledge_versioning.py)
rather than a fourth ad-hoc scoring mechanism.
"""
from __future__ import annotations

from api.db import crud

_COVERED_THRESHOLD = 80.0
_GAP_THRESHOLD = 40.0


def _status_for_coverage(pct: float) -> str:
    if pct >= _COVERED_THRESHOLD:
        return "covered"
    if pct < _GAP_THRESHOLD:
        return "gap"
    return "researching"


def compute_coverage(db, mission_id: str) -> list[dict]:
    """Recompute and persist coverage_pct for every topic in a mission's plan."""
    results: list[dict] = []
    for topic in crud.list_research_topics(db, mission_id):
        estimated = max(1, int((topic.estimates or {}).get("expected_sources", 5)))
        evidence = crud.sum_evidence_count_for_topic(db, topic.id)
        pct = round(min(100.0, (evidence / estimated) * 100.0), 1)
        status = _status_for_coverage(pct)
        crud.update_research_topic(db, topic.id, coverage_pct=pct, status=status)
        results.append({"topic_id": topic.id, "label": topic.label, "coverage_pct": pct, "status": status})
    return results


def aggregate_coverage(results: list[dict]) -> float:
    """Phase 2B.5 — mission-level coverage-target auto-continue loop
    (api.services.research_agent.job_runner.run_mission()). Mean of
    per-topic coverage_pct, not min: a single stubborn low-coverage topic
    shouldn't force endless rounds against the mission's own page/file/
    storage caps. 100.0 for a mission with no topics (nothing to cover)."""
    if not results:
        return 100.0
    return round(sum(r["coverage_pct"] for r in results) / len(results), 1)


def list_low_coverage_topics(db, mission_id: str, threshold: float = 60.0) -> list[dict]:
    """Powers the "Would you like me to improve X knowledge?" suggestion."""
    topics = crud.list_research_topics(db, mission_id)
    low = [t for t in topics if t.coverage_pct < threshold]
    return [
        {
            "topic_id": t.id,
            "label": t.label,
            "coverage_pct": t.coverage_pct,
            "suggestion": f"Would you like me to improve {t.label} knowledge?",
        }
        for t in low
    ]
