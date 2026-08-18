"""Curiosity Engine — Phase 2B.1, extended Phase 2B.3.

After a mission completes, generates real research questions from three
deterministic (no-LLM) sources:
  1. Gap-driven — low-coverage topics from gap_detector.list_low_coverage_topics()
  2. Term-driven — technical-looking phrases mentioned in the mission's
     ingested content that don't yet exist anywhere in the knowledge graph
     ("Mentioned but Unexplained")
  3. Trust-driven (Phase 2B.3) — facts resting on a single source family,
     low-trust-only evidence, a safety topic with no authoritative source,
     or a manufacturer claim with no independent corroboration

Questions are never auto-executed without limits. apply_curiosity_settings()
gates auto-queueing against mission.curiosity_settings (falling back to
DEFAULT_CURIOSITY_SETTINGS below), checked against real DB rows — not an
in-memory counter — so daily/per-mission limits survive restarts. A
Queued question spawns an ordinary ResearchMission through the exact same
api.services.research_agent.job_runner.start_mission() path any
user-started mission uses — there is no separate execution system.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone

from api.db import crud
from api.db.models import CuriosityQuestion, RagDocument
from api.services.research_brain import gap_detector

# Conservative by default: curiosity questions are always generated and
# visible, but nothing gets auto-executed unless the mission (or platform
# default) explicitly opts in — mirrors Phase 1's "Free Mode ON by default"
# safe-default philosophy.
DEFAULT_CURIOSITY_SETTINGS: dict = {
    "auto_queue_curiosity": False,
    "max_curiosity_jobs_per_mission": 3,
    "min_knowledge_gain": 0.4,
    "min_priority": 0.5,
    "daily_curiosity_limit": 5,
}

_LOW_COVERAGE_THRESHOLD = 60.0

# Two-to-four-word Title Case phrases — the same "sparse but real" heuristic
# family as deterministic_extraction.py's heading detector, applied here to
# spot technical-looking terms rather than section headings.
_PHRASE_RE = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b")
_MIN_MENTIONS = 2
_MAX_TERM_QUESTIONS = 5

_MAX_TRUST_QUESTIONS = 5
_LOW_TRUST_AVG_THRESHOLD = 40.0


def _effective_settings(mission) -> dict:
    return {**DEFAULT_CURIOSITY_SETTINGS, **(mission.curiosity_settings or {})}


def _generate_gap_driven_questions(db, mission) -> list[CuriosityQuestion]:
    out = []
    for item in gap_detector.list_low_coverage_topics(db, mission.id, threshold=_LOW_COVERAGE_THRESHOLD):
        topic = crud.get_research_topic(db, item["topic_id"])
        if not topic:
            continue
        category = "Missing" if item["coverage_pct"] <= 0 else "Weakly Covered"
        gain = round(max(0.0, 1.0 - item["coverage_pct"] / 100.0), 3)
        question = crud.create_curiosity_question(
            db,
            mission_id=mission.id,
            related_topic_id=topic.id,
            question_text=f"What is {topic.label}, and how well is it currently understood?",
            reason=f"Coverage for '{topic.label}' is {item['coverage_pct']}%, below the {_LOW_COVERAGE_THRESHOLD:.0f}% gap threshold.",
            source_reference=f"topic:{topic.label}",
            category=category,
            priority_score=round(topic.rank, 3),
            expected_knowledge_gain=gain,
            estimated_research_cost=dict(topic.estimates or {}),
            estimated_storage_mb=round(float((topic.estimates or {}).get("expected_sources", 5)) * 0.5, 2),
            status="Suggested",
        )
        out.append(question)
    return out


def _generate_term_driven_questions(db, mission) -> list[CuriosityQuestion]:
    files = crud.list_research_files(db, mission.id, status="ingested")
    if not files:
        return []

    phrase_counts: dict[str, int] = {}
    phrase_source: dict[str, str] = {}
    for file_row in files:
        if not file_row.rag_document_id:
            continue
        doc = db.query(RagDocument).filter(RagDocument.id == file_row.rag_document_id).first()
        if not doc or not doc.content:
            continue
        for m in _PHRASE_RE.finditer(doc.content):
            phrase = m.group(1).strip()
            if len(phrase) < 6:
                continue
            phrase_counts[phrase] = phrase_counts.get(phrase, 0) + 1
            phrase_source.setdefault(phrase, file_row.filename)

    ranked = sorted(phrase_counts.items(), key=lambda kv: kv[1], reverse=True)

    out: list[CuriosityQuestion] = []
    for phrase, count in ranked:
        if count < _MIN_MENTIONS:
            continue
        if crud.label_exists_in_graph(db, phrase):
            continue  # already a known fact — not "unexplained"
        priority = round(min(1.0, count / 10.0), 3)
        question = crud.create_curiosity_question(
            db,
            mission_id=mission.id,
            related_topic_id=None,
            question_text=f"What is {phrase}?",
            reason=f"'{phrase}' was mentioned {count} time(s) in ingested content but does not yet exist in the knowledge graph.",
            source_reference=phrase_source.get(phrase, ""),
            category="Mentioned but Unexplained",
            priority_score=priority,
            expected_knowledge_gain=0.5,
            estimated_research_cost={"expected_sources": 3},
            estimated_storage_mb=1.5,
            status="Suggested",
        )
        out.append(question)
        if len(out) >= _MAX_TERM_QUESTIONS:
            break
    return out


def _generate_trust_driven_questions(db, mission) -> list[CuriosityQuestion]:
    """Phase 2B.3 — scans this mission's current-status facts for ones that
    should not yet be treated as settled: single-source-family evidence,
    low-trust-only evidence, a safety topic with no authoritative source,
    or a manufacturer claim with no independent (non-manufacturer)
    corroboration. Explicit dedup by source_reference across ALL missions
    (not just this one) before creating — neither of the other two
    generators in this file guard against this, a real gap fixed here
    rather than copied."""
    from api.services.knowledge_governance.conflict_resolver import is_safety_subject
    from api.services.source_trust.source_trust_service import is_manufacturer_domain

    out: list[CuriosityQuestion] = []
    seen_node_ids: set[str] = set()

    for topic in crud.list_research_topics(db, mission.id):
        if len(out) >= _MAX_TRUST_QUESTIONS:
            break
        for node in crud.list_knowledge_nodes_by_topic(db, topic.id, status="current"):
            if len(out) >= _MAX_TRUST_QUESTIONS or node.id in seen_node_ids:
                continue
            seen_node_ids.add(node.id)

            supporting = [e for e in crud.list_knowledge_evidence(db, node_id=node.id) if e.supports]
            sources = [s for s in (crud.get_research_source(db, e.research_source_id) for e in supporting) if s]
            if not sources:
                continue
            families = {s.source_family_id or s.id for s in sources}
            if len(families) > 1:
                continue  # already independently corroborated — nothing to ask

            is_safety = is_safety_subject(node.label, node.description, None)
            is_manufacturer_only = all(is_manufacturer_domain(s.url) for s in sources)
            has_authoritative = any(s.trust_status == "authoritative" for s in sources)
            avg_trust = sum(s.effective_trust_score for s in sources) / len(sources)

            if is_safety and not has_authoritative:
                reason = f"'{node.label}' is a safety-related fact with no authoritative independent source backing it."
            elif is_manufacturer_only:
                reason = f"'{node.label}' relies only on manufacturer-provided source(s) — needs independent verification."
            elif avg_trust < _LOW_TRUST_AVG_THRESHOLD:
                reason = f"'{node.label}' is supported only by low-trust source(s) (avg effective trust {avg_trust:.0f}/100)."
            else:
                reason = f"'{node.label}' depends on a single source family — no independent corroboration yet."

            source_ref = f"trust:{node.id}"
            already_asked = [
                q for q in crud.list_curiosity_questions(db, mission_id=None)
                if q.source_reference == source_ref and q.status not in ("Rejected", "Resolved")
            ]
            if already_asked:
                continue

            question = crud.create_curiosity_question(
                db, mission_id=mission.id, related_topic_id=topic.id,
                question_text=f"Find an independent source to verify: {node.label}.",
                reason=reason,
                source_reference=source_ref,
                category="Needs Verification",
                priority_score=0.8 if is_safety else 0.5,
                expected_knowledge_gain=0.4,
                estimated_research_cost={"expected_sources": 2},
                estimated_storage_mb=1.0,
                status="Suggested",
            )
            out.append(question)
    return out


def apply_curiosity_settings(db, mission, question: CuriosityQuestion) -> CuriosityQuestion:
    """Gate a single Suggested question against the mission's (or platform
    default) curiosity settings. Queues a real child mission through the
    normal research_agent path if it qualifies; otherwise leaves it Suggested
    for manual approval via POST /research-brain/curiosity/{id}/approve."""
    settings = _effective_settings(mission)

    if not settings["auto_queue_curiosity"]:
        return question
    if question.priority_score < settings["min_priority"]:
        return question
    if question.expected_knowledge_gain < settings["min_knowledge_gain"]:
        return question

    per_mission_queued = len(crud.list_curiosity_questions(db, mission_id=mission.id, status="Queued"))
    if per_mission_queued >= settings["max_curiosity_jobs_per_mission"]:
        return question

    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    daily_count = crud.count_curiosity_spawned_missions_since(db, today_start)
    if daily_count >= settings["daily_curiosity_limit"]:
        return question

    return queue_question(db, mission, question)


def queue_question(db, mission, question: CuriosityQuestion) -> CuriosityQuestion:
    """Spawn a real child mission for this question and mark it Queued.

    Called both by apply_curiosity_settings() (automatic path, gated by
    settings) and by the manual approve endpoint (POST
    /research-brain/curiosity/{id}/approve) — approval is itself the gate in
    the manual case, so it calls this directly.
    """
    from api.services.research_agent.job_runner import start_mission

    child = crud.create_research_mission(
        db,
        user_id=mission.user_id,
        mission_text=question.question_text,
        mode="quick_scan",
        free_mode=mission.free_mode,
    )
    start_mission(child.id)
    updated = crud.update_curiosity_question(db, question.id, status="Queued", spawned_mission_id=child.id)
    crud.add_research_activity(
        db, mission.id, "info",
        f"Curiosity question auto-queued as a new mission: {question.question_text}",
    )
    return updated


def generate_questions(db, mission_id: str) -> list[CuriosityQuestion]:
    """Called once a mission completes (research_agent.job_runner.run_mission,
    right after gap_detector.compute_coverage()). Returns every question
    generated this round, each already run through apply_curiosity_settings()."""
    mission = crud.get_research_mission(db, mission_id)
    if not mission:
        return []

    candidates = (
        _generate_gap_driven_questions(db, mission)
        + _generate_term_driven_questions(db, mission)
        + _generate_trust_driven_questions(db, mission)
    )
    return [apply_curiosity_settings(db, mission, q) for q in candidates]
