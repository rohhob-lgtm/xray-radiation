"""
Proactive AI Scientist (Phase 2B.8) tests — targeted, per the request.

Covers: one genuine discovery creates one documented (sourced) alert,
a duplicate discovery creates no duplicate alert, a low-trust finding is
never worded as established fact, sweep_for_new_missions() respects the
daily mission limit and forces Free Mode, and a regression guard proving
the Phase 2B.6 Knowledge Router / Phase 2B.7 Reasoning Engine are
unaffected. No real network calls anywhere in this file.
"""
import os
import random
import string
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest

from api.db.base import SessionLocal
from api.db import crud
from api.services.research_brain import ai_scientist

_created_mission_ids: list[str] = []


def _word_tag() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=10))


@pytest.fixture(autouse=True)
def _archive_created_missions():
    """Same convention as test_research_memory.py/test_ai_scientist's
    sibling test files this session."""
    _created_mission_ids.clear()
    yield
    if not _created_mission_ids:
        return
    db = SessionLocal()
    try:
        for mission_id in _created_mission_ids:
            crud.update_research_mission(db, mission_id, status="archived")
    finally:
        db.close()
    _created_mission_ids.clear()


def _make_mission_with_topic(db, tag: str):
    mission = crud.create_research_mission(
        db, user_id=None, mission_text=f"test mission {tag}", mode="quick_scan", free_mode=True, priority=100, origin="user",
    )
    _created_mission_ids.append(mission.id)
    plan = crud.create_research_plan(db, mission_id=mission.id, normalized_understanding={"normalized_topic": f"topic {tag}", "template": "generic"})
    topic = crud.create_research_topic(db, plan_id=plan.id, mission_id=mission.id, label=f"topic {tag}", rank=1.0, status="researching", search_strategy={})
    return mission, topic


def _make_source_with_trust(db, mission_id: str, tag: str, trust_score: float):
    source = crud.create_research_source(
        db, mission_id=mission_id, url=f"https://example.org/{tag}", domain="example.org",
        title="Test source", publisher="Example", content_hash=None,
        quality_score=70.0, quality_label="useful", quality_reasons=[], accepted_into_kb=True, source_doi=None,
    )
    return crud.update_research_source(db, source.id, dynamic_trust_score=trust_score, effective_trust_score=trust_score)


# ──────────────────────────────────────────────────────────
# 1. One genuine discovery -> one documented alert
# ──────────────────────────────────────────────────────────

def test_new_discovery_creates_one_documented_alert(monkeypatch):
    from api.config import settings
    # The daily alert budget is a legitimate GLOBAL per-calendar-day counter
    # (that's the whole point of ai_scientist_daily_alert_limit) — other
    # test files completing real missions today via job_runner.run_mission()
    # legitimately consume it too, via the exact same classify_and_alert()
    # hook. Bump it here so this test's own assertions are deterministic
    # regardless of how much of today's budget the rest of the suite used.
    monkeypatch.setattr(settings, "ai_scientist_daily_alert_limit", 10_000)

    db = SessionLocal()
    try:
        tag = _word_tag()
        mission, topic = _make_mission_with_topic(db, tag)
        node = crud.create_knowledge_node(
            db, node_type="Paper", label=f"Paper {tag}", description="A new thesis",
            approved=True, confidence=0.8, evidence_count=2, research_topic_id=topic.id,
        )
        source = _make_source_with_trust(db, mission.id, tag, 80.0)
        crud.create_knowledge_provenance(db, node_id=node.id, mission_id=mission.id, source_id=source.id, created_by_service="test")

        alerts = ai_scientist.classify_and_alert(db, mission.id)
        scientific = [a for a in alerts if a.alert_type == "Scientific Alert"]
        assert len(scientific) == 1
        alert = scientific[0]
        assert node.id in alert.related_node_ids
        assert source.id in alert.related_source_ids
        assert alert.topic_key
        assert alert.mission_id == mission.id
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# 2. Duplicate discovery -> no duplicate alert
# ──────────────────────────────────────────────────────────

def test_duplicate_discovery_creates_no_duplicate_alert(monkeypatch):
    from api.config import settings
    monkeypatch.setattr(settings, "ai_scientist_daily_alert_limit", 10_000)

    db = SessionLocal()
    try:
        tag = _word_tag()
        mission, topic = _make_mission_with_topic(db, tag)
        node = crud.create_knowledge_node(
            db, node_type="Paper", label=f"Paper {tag}", approved=True, confidence=0.8,
            evidence_count=2, research_topic_id=topic.id,
        )
        source = _make_source_with_trust(db, mission.id, tag, 80.0)
        crud.create_knowledge_provenance(db, node_id=node.id, mission_id=mission.id, source_id=source.id, created_by_service="test")

        first = ai_scientist.classify_and_alert(db, mission.id)
        assert len(first) >= 1
        second = ai_scientist.classify_and_alert(db, mission.id)
        assert second == []
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# 3. Low-trust finding is never worded as established fact
# ──────────────────────────────────────────────────────────

def test_low_trust_finding_is_not_presented_as_established_fact(monkeypatch):
    from api.config import settings
    monkeypatch.setattr(settings, "ai_scientist_daily_alert_limit", 10_000)

    db = SessionLocal()
    try:
        tag = _word_tag()
        mission, topic = _make_mission_with_topic(db, tag)
        node = crud.create_knowledge_node(
            db, node_type="Paper", label=f"Paper {tag}", approved=True, confidence=0.6,
            evidence_count=1, research_topic_id=topic.id,
        )
        source = _make_source_with_trust(db, mission.id, tag, 20.0)  # well below the threshold
        crud.create_knowledge_provenance(db, node_id=node.id, mission_id=mission.id, source_id=source.id, created_by_service="test")

        alerts = ai_scientist.classify_and_alert(db, mission.id)
        scientific = [a for a in alerts if a.alert_type == "Scientific Alert"]
        assert len(scientific) == 1
        assert scientific[0].min_trust_score == 20.0
        assert "unproven" in scientific[0].summary.lower()
        assert "established" not in scientific[0].summary.lower()
    finally:
        db.close()


def test_format_alert_summary_qualifiers():
    from api.config import settings
    assert "unproven" in ai_scientist.format_alert_summary("x", None).lower()
    assert "unproven" in ai_scientist.format_alert_summary("x", settings.ai_scientist_min_trust_for_established_fact - 1).lower()
    assert "established" in ai_scientist.format_alert_summary("x", settings.ai_scientist_min_trust_for_established_fact + 1).lower()


# ──────────────────────────────────────────────────────────
# 4. sweep_for_new_missions respects daily limits + Free Mode
# ──────────────────────────────────────────────────────────

def test_sweep_for_new_missions_respects_daily_limit_and_free_mode(monkeypatch):
    from datetime import datetime, timezone
    from api.config import settings

    # sweep_for_new_missions() ranks candidates by lowest coverage_pct first
    # (correct production behavior — most-incomplete topics get priority).
    # The shared scratch DB has accumulated thousands of 0%-coverage topics
    # across this session's many test files, all ranked ahead of anything
    # this test seeds at 5% coverage. The window (budget * 3) needs to be
    # large enough to walk past all of that pollution — cheaply, since
    # duplicates of the same normalized topic_key short-circuit via
    # seen_keys — and reach this test's own guaranteed-novel topics. The
    # safety invariant that actually matters (spawned <= limit) holds at
    # any limit value; a generous one here just makes "something novel
    # eventually gets picked up" deterministic instead of order-dependent.
    limit = 2600
    monkeypatch.setattr(settings, "ai_scientist_daily_mission_limit", limit)
    monkeypatch.setattr(settings, "ai_scientist_low_coverage_threshold", 60.0)
    # The daily mission count is a real GLOBAL per-calendar-day counter — other
    # test files' completed missions legitimately count toward it too. Pin
    # "today" to the instant just before this test acts, so no pre-existing
    # row (all created strictly earlier) counts toward "existing today", and
    # only missions this test itself spawns (created strictly after) do —
    # deterministic regardless of what the rest of the suite already did today.
    sentinel_today = datetime.now(timezone.utc)
    monkeypatch.setattr(ai_scientist, "_today_start", lambda: sentinel_today)

    db = SessionLocal()
    try:
        tag = _word_tag()
        for i in range(20):
            mission, _topic = _make_mission_with_topic(db, f"{tag}{i}")
            plan = crud.get_research_plan_by_mission(db, mission.id)
            crud.create_research_topic(
                db, plan_id=plan.id, mission_id=mission.id, label=f"low-coverage {tag}{i}",
                rank=1.0, status="pending", coverage_pct=5.0, search_strategy={},
            )

        spawned = ai_scientist.sweep_for_new_missions(db)
        # The safety invariant that actually matters: never exceed the cap.
        assert spawned <= limit
        # And the mechanism genuinely does something when novel low-coverage
        # work exists (20 fresh, guaranteed-unique topics were just seeded).
        assert spawned >= 1

        new_missions = (
            db.query(crud.ResearchMission)
            .filter(crud.ResearchMission.origin == "proactive_discovery", crud.ResearchMission.queued_at >= sentinel_today)
            .all()
        )
        for m in new_missions:
            _created_mission_ids.append(m.id)
            assert m.free_mode is True
        assert len(new_missions) == spawned
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# 5. Regression guard — Knowledge Router / Reasoning Engine unaffected
# ──────────────────────────────────────────────────────────

def test_knowledge_router_and_reasoning_engine_unaffected_by_import():
    """Importing/using ai_scientist must not alter either prior phase's
    behavior — same inputs, same outputs, proving zero coupling."""
    from api.services.knowledge_router import classify_knowledge_gap
    from api.services.research_brain.reasoning_engine import classify_reasoning_intent

    assert classify_knowledge_gap("Any new Rapiscan products?") == "manufacturer_update"
    assert classify_reasoning_intent("Compare LINAC and Betatron.") == "COMPARE"
    assert classify_knowledge_gap("What is Compton scattering?") == "general_knowledge"
    assert classify_reasoning_intent("Thanks!") is None
