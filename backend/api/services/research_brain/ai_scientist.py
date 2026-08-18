"""Phase 2B.8 — Proactive AI Scientist.

Deliberately not a new discovery engine: a thin classification + alerting
layer over infrastructure that already exists —
api.services.research_brain.gap_detector (knowledge gaps),
api.services.research_brain.curiosity_engine (self-generated questions),
api.services.research_brain.research_memory (freshness/staleness),
api.services.knowledge_governance (provenance, written on every graph
write), and api.services.source_trust (trust scores). Every mission this
module spawns goes through the exact same
api.services.research_agent.job_runner.start_mission() /
MissionQueueManager bounded claim path every other mission already uses —
no new crawler, queue, or LLM pipeline.

Two hook points, both additive, both wrapped so a bug here can never break
the pipeline they're called from:
  - classify_and_alert() is called from job_runner.run_mission() right next
    to the existing curiosity_engine.generate_questions() call.
  - sweep_for_new_missions() / maybe_generate_weekly_brief() are called from
    job_runner.MissionScheduler.tick() right next to the existing
    research_memory.sweep_due_refreshes() call.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from api.config import settings
from api.db import crud
from api.db.models import KnowledgeNode, ResearchMission, ResearchTopic
from api.services.knowledge_governance.conflict_resolver import is_safety_subject
from api.services.research_brain import gap_detector
from api.services.research_brain.research_memory import normalize_topic_key

log = logging.getLogger(__name__)

_TECH_NODE_TYPES = ("Product", "Patent")
_TRAINING_NODE_TYPES = ("Training", "Procedure")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


def _today_start() -> datetime:
    now = _now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _resolve_trust_for_nodes(db, nodes: list[KnowledgeNode]) -> tuple[list[str], float | None]:
    """Every cited source's effective_trust_score, resolved via the same
    KnowledgeProvenance rows every governance write already creates — the
    MIN across sources (not the max) is used, so one weak source can't hide
    behind a stronger one when deciding whether to word a finding as
    established fact."""
    source_ids: set[str] = set()
    trust_scores: list[float] = []
    for node in nodes:
        for prov in crud.list_knowledge_provenance(db, node_id=node.id):
            if not prov.source_id:
                continue
            source_ids.add(prov.source_id)
            source = crud.get_research_source(db, prov.source_id)
            if source is not None:
                trust_scores.append(source.effective_trust_score)
    min_trust = min(trust_scores) if trust_scores else None
    return list(source_ids), min_trust


def format_alert_summary(base_summary: str, min_trust_score: float | None) -> str:
    """The "low-trust finding is never presented as established fact" rule.
    A missing trust score (no resolvable source at all) is treated as
    unproven too — silence is not evidence."""
    if min_trust_score is None:
        qualifier = "(unproven — no verified source trust data yet)"
    elif min_trust_score < settings.ai_scientist_min_trust_for_established_fact:
        qualifier = f"(unproven — low source trust: {round(min_trust_score)}%)"
    else:
        qualifier = f"(established — source trust: {round(min_trust_score)}%)"
    return f"{qualifier} {base_summary}"


def classify_and_alert(db, mission_id: str) -> list:
    """Called once a mission completes. Looks at what THIS mission actually
    produced and creates at most a handful of alerts, each deduplicated
    against recent alerts for the same topic_key + alert_type and capped by
    the platform-wide daily alert budget."""
    if not settings.ai_scientist_enabled:
        return []
    mission = crud.get_research_mission(db, mission_id)
    if not mission:
        return []

    alert_budget = settings.ai_scientist_daily_alert_limit - crud.count_scientific_alerts_since(db, _today_start())
    if alert_budget <= 0:
        return []

    created: list = []

    def _try_create(alert_type: str, topic_key: str, title: str, summary_base: str, node_ids: list[str]) -> None:
        nonlocal alert_budget
        if alert_budget <= 0:
            return
        if crud.get_recent_scientific_alert_by_key(db, topic_key, alert_type, settings.ai_scientist_dedup_window_days):
            return
        nodes = [n for n in (crud.get_knowledge_node(db, nid) for nid in node_ids) if n]
        source_ids, min_trust = _resolve_trust_for_nodes(db, nodes)
        alert = crud.create_scientific_alert(
            db, alert_type=alert_type, title=title,
            summary=format_alert_summary(summary_base, min_trust),
            topic_key=topic_key, mission_id=mission_id,
            related_node_ids=node_ids, related_source_ids=source_ids, min_trust_score=min_trust,
        )
        created.append(alert)
        alert_budget -= 1

    subject = mission.normalized_topic or mission.mission_text or ""
    topics = crud.list_research_topics(db, mission_id)
    new_nodes: list[KnowledgeNode] = []
    for topic in topics:
        new_nodes.extend(crud.list_knowledge_nodes_by_topic(db, topic.id, status="current"))

    tech_nodes = [n for n in new_nodes if n.node_type in _TECH_NODE_TYPES]
    if tech_nodes:
        key = normalize_topic_key(mission.detected_manufacturer or subject)
        _try_create(
            "Technology Update", key,
            f"New manufacturer intelligence: {mission.detected_manufacturer or subject[:80]}",
            f"Discovered {len(tech_nodes)} new product/patent record(s): "
            + "; ".join(n.label for n in tech_nodes[:5]),
            [n.id for n in tech_nodes],
        )

    paper_nodes = [n for n in new_nodes if n.node_type == "Paper"]
    if paper_nodes:
        key = normalize_topic_key(subject)
        _try_create(
            "Scientific Alert", key,
            f"New research found: {subject[:80]}",
            f"Discovered {len(paper_nodes)} new paper/thesis record(s): "
            + "; ".join(n.label for n in paper_nodes[:5]),
            [n.id for n in paper_nodes],
        )

    training_nodes = [
        n for n in new_nodes
        if n.node_type in _TRAINING_NODE_TYPES or is_safety_subject(n.label, n.description, None)
    ]
    if training_nodes:
        key = normalize_topic_key(subject)
        _try_create(
            "Training Impact", key,
            f"Training-relevant update: {subject[:80]}",
            f"{len(training_nodes)} newly learned fact(s) may be worth adding to training material: "
            + "; ".join(n.label for n in training_nodes[:5]),
            [n.id for n in training_nodes],
        )

    low_coverage = gap_detector.list_low_coverage_topics(db, mission_id, threshold=settings.ai_scientist_low_coverage_threshold)
    if low_coverage:
        key = normalize_topic_key(subject)
        _try_create(
            "Knowledge Gap", key,
            f"Knowledge gaps remain: {subject[:80]}",
            f"{len(low_coverage)} topic(s) still below target coverage: "
            + "; ".join(f"{t['label']} ({t['coverage_pct']}%)" for t in low_coverage[:5]),
            [],
        )

    questions = crud.list_curiosity_questions(db, mission_id=mission_id, status="Suggested")
    if questions:
        top = questions[0]  # already ranked by priority_score desc
        key = normalize_topic_key(top.question_text)
        _try_create(
            "Suggested Research Question", key,
            "New research question suggested",
            f"{top.question_text} — {top.reason}" if top.reason else top.question_text,
            [],
        )

    return created


def sweep_for_new_missions(db) -> int:
    """Bounded, scheduler-driven proactive discovery — creates mission rows
    exactly as crud.create_research_mission() always has (status="queued"),
    then leaves them for the existing MissionQueueManager claim loop to pick
    up — no immediate asyncio.create_task() here (see the comment at the
    call site below for why). Never exceeds ai_scientist_daily_mission_limit
    missions per calendar day."""
    if not settings.ai_scientist_enabled:
        return 0

    existing_today = (
        db.query(ResearchMission)
        .filter(ResearchMission.origin == "proactive_discovery", ResearchMission.queued_at >= _today_start())
        .count()
    )
    budget = settings.ai_scientist_daily_mission_limit - existing_today
    if budget <= 0:
        return 0

    candidates = (
        db.query(ResearchTopic)
        .filter(ResearchTopic.coverage_pct < settings.ai_scientist_low_coverage_threshold, ResearchTopic.status != "covered")
        .order_by(ResearchTopic.coverage_pct.asc())
        .limit(budget * 3)
        .all()
    )

    spawned = 0
    seen_keys: set[str] = set()
    dedup_cutoff = _now() - timedelta(days=settings.ai_scientist_dedup_window_days)
    for topic in candidates:
        if spawned >= budget:
            break
        topic_key = normalize_topic_key(topic.label)
        if topic_key in seen_keys:
            continue
        seen_keys.add(topic_key)
        # Already alerted on this exact gap recently -> don't spawn another
        # mission for it yet (the alert IS the "we noticed" signal).
        if crud.get_recent_scientific_alert_by_key(db, topic_key, "Knowledge Gap", settings.ai_scientist_dedup_window_days):
            continue
        # Disclosed simplification (no dedicated topic_key column on
        # ResearchMission today): a substring match on mission_text is
        # enough to catch "we already just spawned this" within the dedup
        # window without a new schema column — same "resolved consistently,
        # disclosed, not silently guessed" convention as
        # research_agent_chat_intent.py's _resolve_focus_topic_memory().
        recent_duplicate = (
            db.query(ResearchMission)
            .filter(
                ResearchMission.origin == "proactive_discovery",
                ResearchMission.mission_text.like(f"%{topic.label}%"),
                ResearchMission.queued_at >= dedup_cutoff,
            )
            .first()
        )
        if recent_duplicate:
            continue

        # Deliberately NOT start_mission() (an immediate asyncio.create_task
        # firing real discovery/crawl work right now, bypassing the bounded
        # worker pool) — crud.create_research_mission() already leaves the
        # mission in status="queued", which is all a mission needs to be
        # picked up by the SAME bounded MissionQueueManager claim loop every
        # other mission already flows through (mission_queue.py, started
        # once by MissionScheduler.start() in the real running app). This
        # also means calling tick() directly (as several existing tests do,
        # to exercise the freshness sweep) can never trigger real background
        # network work merely by discovering a low-coverage topic exists.
        mission = crud.create_research_mission(
            db, user_id=None, mission_text=f"[AI Scientist] {topic.label}",
            mode="quick_scan", free_mode=True, priority=150, origin="proactive_discovery",
        )
        crud.add_research_activity(
            db, mission.id, "info",
            f"Proactively spawned by AI Scientist for low-coverage topic: {topic.label} ({topic.coverage_pct}%)",
        )
        spawned += 1
    return spawned


def maybe_generate_weekly_brief(db):
    """No new scheduling primitive — bucketed by comparing created_at on
    the same ScientificAlert table every other alert already uses."""
    if not settings.ai_scientist_enabled:
        return None

    last_brief = crud.list_scientific_alerts(db, alert_type="Weekly Research Brief", limit=1)
    if last_brief and _now() - _aware(last_brief[0].created_at) < timedelta(days=7):
        return None

    since = _aware(last_brief[0].created_at) if last_brief else _now() - timedelta(days=7)
    recent = [a for a in crud.list_scientific_alerts(db, since=since, limit=50) if a.alert_type != "Weekly Research Brief"]
    if not recent:
        return None

    lines = [f"- [{a.alert_type}] {a.title}" for a in recent[:15]]
    summary = f"{len(recent)} finding(s) since the last brief:\n" + "\n".join(lines)
    return crud.create_scientific_alert(
        db, alert_type="Weekly Research Brief", title="Weekly Research Brief",
        summary=summary, topic_key=f"weekly-brief-{_now().date().isoformat()}",
        mission_id=None, related_node_ids=[], related_source_ids=[], min_trust_score=None,
    )
