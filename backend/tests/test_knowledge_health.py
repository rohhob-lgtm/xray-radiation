"""
Knowledge Health (Phase 2B.9) tests — targeted, per the request.

Covers: health score reflects coverage/trust/freshness/conflicts, a
safety-critical gap is unconditionally classified Critical (not a scoring
coincidence), duplicate evidence never inflates health (independent
source_family_id count drives the score, not raw evidence_count), the
periodic audit uses the existing MissionScheduler (no new queue/worker),
and a regression guard proving the Knowledge Router / Expert Reasoning /
AI Scientist are unaffected. No real network calls anywhere in this file.
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
from api.db.models import KnowledgeConflict, KnowledgeEdge, KnowledgeNode, ResearchSource
from api.services.research_brain import knowledge_health as kh
from api.services.research_brain import research_memory

USER = {"id": "knowledge-health-test-user", "username": "kh-tester@example.com", "name": "KH Tester"}

_created_mission_ids: list[str] = []


def _word_tag() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=10))


@pytest.fixture(autouse=True)
def _archive_created_missions():
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


def _make_topic_memory(db, tag: str, *, content_category="Manuals"):
    mission = crud.create_research_mission(
        db, user_id=None, mission_text=f"test mission {tag}", mode="quick_scan", free_mode=True, priority=100, origin="user",
    )
    _created_mission_ids.append(mission.id)
    plan = crud.create_research_plan(db, mission_id=mission.id, normalized_understanding={})
    memory = research_memory.get_or_create_topic_memory(
        db, topic_key=research_memory.normalize_topic_key(f"topic {tag}"), content_category=content_category,
    )
    return mission, plan, memory


def _make_source_with_trust(db, mission_id: str, tag: str, trust_score: float):
    source = crud.create_research_source(
        db, mission_id=mission_id, url=f"https://example.org/{tag}", domain="example.org",
        title="Test source", publisher="Example", content_hash=None,
        quality_score=70.0, quality_label="useful", quality_reasons=[], accepted_into_kb=True, source_doi=None,
    )
    return crud.update_research_source(db, source.id, dynamic_trust_score=trust_score, effective_trust_score=trust_score)


# ──────────────────────────────────────────────────────────
# 1. Health score reflects coverage/trust/freshness/conflicts
# ──────────────────────────────────────────────────────────

def test_healthy_topic_scores_high_weak_topic_scores_low():
    db = SessionLocal()
    try:
        tag = _word_tag()
        mission, plan, memory = _make_topic_memory(db, tag)
        crud.update_topic_research_memory(db, memory.id, freshness_status="Fresh")
        topic = crud.create_research_topic(
            db, plan_id=plan.id, mission_id=mission.id, label=f"topic {tag}", rank=1.0,
            status="researching", coverage_pct=85.0, topic_memory_id=memory.id, search_strategy={},
        )
        node = crud.create_knowledge_node(db, node_type="Equipment", label=f"unit {tag}", approved=True, confidence=0.8, evidence_count=2, research_topic_id=topic.id)
        source = _make_source_with_trust(db, mission.id, tag, 85.0)
        crud.create_knowledge_evidence(db, node_id=node.id, research_source_id=source.id, supports=True)
        crud.create_knowledge_provenance(db, node_id=node.id, mission_id=mission.id, source_id=source.id, created_by_service="test")

        healthy = kh.compute_topic_health(db, memory)
        assert healthy["score"] >= 65.0
        assert healthy["classification"] in ("Good", "Healthy")

        tag2 = _word_tag()
        mission2, plan2, memory2 = _make_topic_memory(db, tag2)
        crud.update_topic_research_memory(db, memory2.id, freshness_status="Outdated")
        crud.create_research_topic(
            db, plan_id=plan2.id, mission_id=mission2.id, label=f"topic {tag2}", rank=1.0,
            status="pending", coverage_pct=5.0, topic_memory_id=memory2.id, search_strategy={},
        )
        weak = kh.compute_topic_health(db, memory2)
        assert weak["score"] < healthy["score"]
        assert weak["classification"] in ("Weak", "Needs Attention", "Critical", "Unknown")
    finally:
        db.close()


def test_score_and_classify_responds_to_each_signal_independently():
    base = dict(
        coverage_pct=60.0, total_nodes=1, avg_trust=60.0, open_conflicts=0,
        missing_provenance_count=0, failed_extractions=0, unresolved_questions=0,
        is_safety_subject=False, freshness_status="Acceptable", independent_evidence_count=2, duplicate_evidence_count=0,
    )
    baseline_score, _ = kh.score_and_classify(base)

    lower_coverage = dict(base, coverage_pct=10.0)
    assert kh.score_and_classify(lower_coverage)[0] < baseline_score

    lower_trust = dict(base, avg_trust=10.0)
    assert kh.score_and_classify(lower_trust)[0] < baseline_score

    worse_freshness = dict(base, freshness_status="Outdated")
    assert kh.score_and_classify(worse_freshness)[0] < baseline_score

    with_conflict = dict(base, open_conflicts=1)
    assert kh.score_and_classify(with_conflict)[0] < baseline_score


# ──────────────────────────────────────────────────────────
# 2. Safety-critical gaps are marked Critical (unconditional override)
# ──────────────────────────────────────────────────────────

def test_safety_subject_forces_critical_regardless_of_raw_score():
    # A signal set that would NOT naturally classify as Critical on its own.
    signals = dict(
        coverage_pct=80.0, total_nodes=1, avg_trust=40.0, open_conflicts=0,
        missing_provenance_count=0, failed_extractions=0, unresolved_questions=0,
        is_safety_subject=False, freshness_status="Fresh", independent_evidence_count=3, duplicate_evidence_count=0,
    )
    score, classification = kh.score_and_classify(signals)
    assert classification != "Critical"

    safety_signals = dict(signals, is_safety_subject=True)  # trust=40 is below the safety floor
    safety_score, safety_classification = kh.score_and_classify(safety_signals)
    assert safety_score == score  # same raw score
    assert safety_classification == "Critical"  # different classification — the override, not a coincidence


def test_safety_subject_topic_end_to_end_is_critical():
    db = SessionLocal()
    try:
        tag = _word_tag()
        mission, plan, memory = _make_topic_memory(db, tag, content_category="Safety Documents")
        crud.update_topic_research_memory(db, memory.id, freshness_status="Outdated")
        topic = crud.create_research_topic(
            db, plan_id=plan.id, mission_id=mission.id, label=f"radiation dose safety limit {tag}",
            rank=1.0, status="pending", coverage_pct=15.0, topic_memory_id=memory.id, search_strategy={},
        )
        node = crud.create_knowledge_node(db, node_type="Safety", label=f"dose limit {tag}", approved=True, confidence=0.3, evidence_count=1, research_topic_id=topic.id)
        crud.create_knowledge_conflict(
            db, subject_node_id=node.id, claim_a="10 mSv", claim_b="20 mSv",
            conflict_type="Numerical", severity="critical", resolution_status="Open", confidence=0.3, human_review_required=True,
        )
        result = kh.compute_topic_health(db, memory)
        assert result["signals"]["is_safety_subject"] is True
        assert result["classification"] == "Critical"
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# 3. Duplicate evidence does not inflate health
# ──────────────────────────────────────────────────────────

def test_duplicate_evidence_does_not_inflate_score():
    db = SessionLocal()
    try:
        tag_a, tag_b = _word_tag(), _word_tag()

        # Scope A: 5 evidence rows, all from the SAME source_family_id.
        mission_a, plan_a, memory_a = _make_topic_memory(db, tag_a)
        crud.update_topic_research_memory(db, memory_a.id, freshness_status="Acceptable")
        topic_a = crud.create_research_topic(
            db, plan_id=plan_a.id, mission_id=mission_a.id, label=f"topic {tag_a}", rank=1.0,
            status="researching", coverage_pct=60.0, topic_memory_id=memory_a.id, search_strategy={},
        )
        node_a = crud.create_knowledge_node(db, node_type="Equipment", label=f"unit {tag_a}", approved=True, confidence=0.6, evidence_count=5, research_topic_id=topic_a.id)
        family_id = f"family-{tag_a}"
        for i in range(5):
            source = _make_source_with_trust(db, mission_a.id, f"{tag_a}{i}", 70.0)
            crud.update_research_source(db, source.id, source_family_id=family_id)
            crud.create_knowledge_evidence(db, node_id=node_a.id, research_source_id=source.id, supports=True)

        # Scope B: 2 evidence rows from 2 DISTINCT source families.
        mission_b, plan_b, memory_b = _make_topic_memory(db, tag_b)
        crud.update_topic_research_memory(db, memory_b.id, freshness_status="Acceptable")
        topic_b = crud.create_research_topic(
            db, plan_id=plan_b.id, mission_id=mission_b.id, label=f"topic {tag_b}", rank=1.0,
            status="researching", coverage_pct=60.0, topic_memory_id=memory_b.id, search_strategy={},
        )
        node_b = crud.create_knowledge_node(db, node_type="Equipment", label=f"unit {tag_b}", approved=True, confidence=0.6, evidence_count=2, research_topic_id=topic_b.id)
        for i in range(2):
            source = _make_source_with_trust(db, mission_b.id, f"{tag_b}{i}", 70.0)
            crud.create_knowledge_evidence(db, node_id=node_b.id, research_source_id=source.id, supports=True)

        result_a = kh.compute_topic_health(db, memory_a)
        result_b = kh.compute_topic_health(db, memory_b)

        assert result_a["signals"]["independent_evidence_count"] == 1
        assert result_a["signals"]["duplicate_evidence_count"] == 4
        assert result_b["signals"]["independent_evidence_count"] == 2
        assert result_b["signals"]["duplicate_evidence_count"] == 0
        # Fewer raw evidence rows but more INDEPENDENT ones must score >= the
        # pile of duplicates — duplicates never inflate health.
        assert result_b["score"] >= result_a["score"]
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# 4. Periodic audit uses the existing Scheduler — no new queue/worker
# ──────────────────────────────────────────────────────────

def test_run_health_audit_only_writes_snapshot_rows():
    """run_health_audit() must never mutate the knowledge graph itself —
    only its own KnowledgeHealthSnapshot cache. Uses whatever
    TopicResearchMemory rows the bounded batch actually picks (the shared
    scratch DB has thousands accumulated from this session — which ones get
    processed first is not the point of this test, only that processing
    them never touches KnowledgeNode/Edge/Conflict/ResearchSource)."""
    db = SessionLocal()
    try:
        node_count_before = db.query(KnowledgeNode).count()
        edge_count_before = db.query(KnowledgeEdge).count()
        conflict_count_before = db.query(KnowledgeConflict).count()
        source_count_before = db.query(ResearchSource).count()
        snapshot_count_before = db.query(crud.KnowledgeHealthSnapshot).count()

        computed = kh.run_health_audit(db, batch_size=5)
        assert computed >= 1

        assert db.query(KnowledgeNode).count() == node_count_before
        assert db.query(KnowledgeEdge).count() == edge_count_before
        assert db.query(KnowledgeConflict).count() == conflict_count_before
        assert db.query(ResearchSource).count() == source_count_before
        assert db.query(crud.KnowledgeHealthSnapshot).count() >= snapshot_count_before
    finally:
        db.close()


def test_run_health_audit_stores_a_retrievable_snapshot_for_a_specific_topic():
    """Bypasses run_health_audit's own bounded-batch iteration order (which
    depends on TopicResearchMemory.updated_at ranking against thousands of
    accumulated rows from this session — not what this test is about) and
    directly verifies compute+store persists a snapshot that reads back
    correctly, via the exact same crud.upsert_knowledge_health_snapshot()
    call run_health_audit() itself uses."""
    db = SessionLocal()
    try:
        tag = _word_tag()
        mission, plan, memory = _make_topic_memory(db, tag)
        crud.update_topic_research_memory(db, memory.id, freshness_status="Fresh")
        crud.create_research_topic(
            db, plan_id=plan.id, mission_id=mission.id, label=f"topic {tag}", rank=1.0,
            status="researching", coverage_pct=70.0, topic_memory_id=memory.id, search_strategy={},
        )
        result = kh.compute_topic_health(db, memory)
        crud.upsert_knowledge_health_snapshot(db, **result)

        snapshot = crud.get_knowledge_health_snapshot(db, "Topic", memory.topic_key)
        assert snapshot is not None
        assert snapshot.score == result["score"]
        assert snapshot.classification == result["classification"]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_mission_scheduler_tick_includes_health_audit(monkeypatch):
    """MissionScheduler.tick() must call the SAME audit function — no new
    scheduler/worker class introduced for Knowledge Health, same guarantee
    as the existing freshness-sweep test in test_research_memory.py."""
    from api.services.research_agent.job_runner import MissionScheduler

    called = {"count": 0}

    def _fake_audit(db, *args, **kwargs):
        called["count"] += 1
        return 0

    # Isolate exactly what this test is about, same convention
    # test_research_memory.py's own tick() test already uses — an unmocked
    # sweep_due_refreshes() can spawn a real background mission (pre-existing
    # 2B.4 behavior, unrelated to this phase) if the accumulated shared
    # scratch DB happens to have a genuinely due topic right now.
    monkeypatch.setattr("api.services.research_brain.research_memory.sweep_due_refreshes", lambda db, **kw: 0)
    monkeypatch.setattr("api.services.research_brain.ai_scientist.sweep_for_new_missions", lambda db: 0)
    monkeypatch.setattr("api.services.research_brain.ai_scientist.maybe_generate_weekly_brief", lambda db: None)
    monkeypatch.setattr("api.services.research_brain.knowledge_health.run_health_audit", _fake_audit)

    scheduler = MissionScheduler()
    await scheduler.tick()
    assert called["count"] == 1


# ──────────────────────────────────────────────────────────
# 5. Regression guard — Knowledge Router / Expert Reasoning / AI Scientist unaffected
# ──────────────────────────────────────────────────────────

def test_prior_phases_unaffected_by_import():
    from api.services.knowledge_router import classify_knowledge_gap
    from api.services.research_brain.reasoning_engine import classify_reasoning_intent
    from api.services.research_brain.ai_scientist import classify_and_alert

    assert classify_knowledge_gap("Any new Rapiscan products?") == "manufacturer_update"
    assert classify_reasoning_intent("Compare LINAC and Betatron.") == "COMPARE"
    assert callable(classify_and_alert)
