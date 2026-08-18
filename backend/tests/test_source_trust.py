"""
Dynamic Source Trust (Phase 2B.3) tests.

Covers: static/dynamic/effective score separation, append-only trust
history, independence detection (content_hash/DOI collapsing to one
family), corroboration raising trust, bounded conflict-loss penalty,
historical-correctness non-punishment, safety-critical confidence caps,
manufacturer-claim independence requirement, bounded user-review effect
(reject never deletes, reset recomputes), new-source "Unproven" default,
algorithm versioning, governance-only confidence writes, Free Mode (zero
network calls anywhere in the trust path), and chat/API responses backed
by real numbers. No real network calls anywhere in this file.
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth
from api.db.base import SessionLocal
from api.db.models import User
from api.db import crud
from api.services.knowledge_governance.governance_service import governance
from api.services.source_trust import source_trust_service as sts

USER = {"id": "trust-test-user", "username": "trust@example.com", "name": "Trust Tester"}
_TAG_BASE = int(time.time() * 1000) + 20_000_000  # dominant margin, see test_mission_scheduler.py's note


def _ensure_user() -> None:
    s = SessionLocal()
    try:
        if not s.get(User, USER["id"]):
            s.add(User(id=USER["id"], username=USER["username"], name=USER["name"]))
            s.commit()
    finally:
        s.close()


@pytest.fixture
def client(monkeypatch):
    _ensure_user()

    async def _blocked(*_a, **_k):
        raise AssertionError("trust calculation must never make a network call")
    monkeypatch.setattr(httpx.AsyncClient, "get", _blocked)
    monkeypatch.setattr(httpx.AsyncClient, "post", _blocked)

    monkeypatch.setattr("api.routes.research_agent.start_mission", lambda mission_id: None)
    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)
    app.dependency_overrides[require_auth] = lambda: USER
    yield TestClient(app)
    app.dependency_overrides.pop(require_auth, None)


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _make_source(db, mission_id, *, quality=60.0, domain="example.org", content_hash=None, url=None, doi=None):
    tag = _tag()
    source = crud.create_research_source(
        db, mission_id=mission_id, url=url or f"https://{domain}/{tag}", domain=domain,
        title=f"Source {tag}", publisher=domain, content_hash=content_hash,
        quality_score=quality, quality_label="useful", quality_reasons=[], accepted_into_kb=False,
        source_doi=doi,
    )
    sts.initialize_trust(db, source)
    return crud.get_research_source(db, source.id)


_created_mission_ids: list[str] = []


def _make_mission(db):
    m = crud.create_research_mission(db, user_id=USER["id"], mission_text=f"trust-test-{_tag()}", priority=_TAG_BASE)
    _created_mission_ids.append(m.id)
    return m


@pytest.fixture(autouse=True)
def _archive_created_missions():
    """Archive every mission this file creates after each test — leftover
    high-priority rows must never compete as claim candidates for a later
    test run, in this file or any other (see test_mission_scheduler.py's
    identical fixture for the incident this prevents)."""
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


# ── 1. Static/dynamic/effective are genuinely separate fields ──────────────

def test_scores_are_separate_fields():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id, quality=95.0)
        assert source.quality_score == 95.0
        assert source.dynamic_trust_score == 50.0  # neutral start, independent of static
        assert source.effective_trust_score != source.quality_score
        assert source.effective_trust_score != source.dynamic_trust_score
    finally:
        db.close()


# ── 2. Every score change writes a SourceTrustHistory row ──────────────────

def test_recalculate_writes_history_row():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id)
        before = len(crud.list_source_trust_history(db, source.id))
        sts.recalculate(db, source.id, reason="manual", service_name="test")
        after = crud.list_source_trust_history(db, source.id)
        assert len(after) == before + 1
        assert after[0].calculation_version == sts.CURRENT_TRUST_ALGORITHM_VERSION
    finally:
        db.close()


# ── 3/4. Independence detection: content_hash and DOI collapse to one family ─

def test_duplicate_content_hash_collapses_to_one_family():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        tag = _tag()
        s1 = _make_source(db, m.id, content_hash=f"samehash-{tag}")
        s2 = _make_source(db, m.id, content_hash=f"samehash-{tag}")
        assert s1.source_family_id == s2.source_family_id
    finally:
        db.close()


def test_same_doi_different_hosts_collapses_to_one_family():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        tag = _tag()
        doi = f"10.1234/{tag}"
        s1 = _make_source(db, m.id, domain="hosta.org", url=f"https://doi.org/{doi}", doi=doi)
        s2 = _make_source(db, m.id, domain="hostb.org", url=f"https://hostb.org/paper-{tag}", doi=doi)
        assert s1.source_family_id == s2.source_family_id == f"doi:{doi}"
    finally:
        db.close()


def test_extract_doi_never_invents_one():
    assert sts.extract_doi("https://example.org/no-doi-here") is None
    assert sts.extract_doi("https://doi.org/10.1000/xyz123") == "10.1000/xyz123"


# ── 5. Independent corroboration raises dynamic trust ───────────────────────

def test_independent_corroboration_raises_dynamic_trust():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        tag = _tag()
        s1 = _make_source(db, m.id, domain="nist.gov", quality=90.0)
        s2 = _make_source(db, m.id, domain="arxiv.org", quality=70.0)

        node = governance.upsert_node_with_evidence(
            db, label=f"Corroborated Fact {tag}", node_type="Component", description="x",
            research_source_id=s1.id, provider_used="deterministic", extractor_confidence=0.5,
            supports=True, source_quality_score=90.0,
        )
        # Snapshot as a plain float immediately — sts.recalculate() returns a
        # freshly-queried ORM object, but SQLAlchemy's identity map means a
        # LATER query for the same row (inside the second recalculate call
        # below) returns this exact same Python instance, so reading
        # `before.dynamic_trust_score` after that second call would silently
        # reflect the NEW value too.
        before_score = sts.recalculate(db, s1.id, reason="manual", service_name="test").dynamic_trust_score

        governance.record_node_evidence(db, node.id, s2.id, supports=True, source_quality_score=70.0, created_by_service="test")
        after = sts.recalculate(db, s1.id, reason="manual", service_name="test")

        assert after.dynamic_trust_score > before_score
        codes = {sig["reason_code"] for sig in (after.trust_signal_summary or [])}
        assert "INDEPENDENT_CORROBORATION" in codes
    finally:
        db.close()


# ── 6. Losing a conflict to a stronger source lowers trust by a bounded amount ─

def test_conflict_loss_to_stronger_source_bounded_penalty():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        tag = _tag()
        weak = _make_source(db, m.id, quality=40.0)
        strong = _make_source(db, m.id, quality=95.0)
        sts.recalculate(db, weak.id, reason="manual", service_name="test")
        sts.recalculate(db, strong.id, reason="manual", service_name="test")

        node = governance.upsert_node_with_evidence(
            db, label=f"Disputed Fact {tag}", node_type="Component", description="value is 5 mSv",
            research_source_id=weak.id, provider_used="deterministic", extractor_confidence=0.5,
            supports=True, source_quality_score=40.0,
        )
        from api.services.knowledge_governance import conflict_resolver
        conflict_resolver.detect_conflict(
            db, existing_node=crud.get_knowledge_node(db, node.id),
            new_claim_description="value is 12 mSv",
            new_source_id=strong.id, existing_source_id=weak.id,
        )
        before_dynamic = crud.get_research_source(db, weak.id).dynamic_trust_score
        after = sts.recalculate(db, weak.id, reason="conflict", service_name="test")
        assert after.dynamic_trust_score < before_dynamic
        assert (before_dynamic - after.dynamic_trust_score) <= 10.0  # bounded, not a collapse to zero
    finally:
        db.close()


# ── 7. Historically-correct-but-old source is not penalized for age alone ──

def test_old_source_not_penalized_without_supersession():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id, quality=80.0)
        crud.update_research_source(db, source.id, fetched_at=datetime.now(timezone.utc) - timedelta(days=1000))
        result = sts.recalculate(db, source.id, reason="staleness_sweep", service_name="test")
        codes = {sig["reason_code"] for sig in (result.trust_signal_summary or [])}
        assert "SUPERSEDED_BY_NEWER_VERSION" not in codes
    finally:
        db.close()


# ── 8. Safety-critical node capped below high-confidence with one source ───

def test_safety_critical_fact_capped_with_single_source():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        tag = _tag()
        source = _make_source(db, m.id, domain="nist.gov", quality=95.0)
        sts.recalculate(db, source.id, reason="manual", service_name="test")
        node = governance.upsert_node_with_evidence(
            db, label=f"Radiation dose limit {tag}", node_type="Component",
            description="the maximum permissible dose is 20 mSv/year",
            research_source_id=source.id, provider_used="deterministic", extractor_confidence=0.9,
            supports=True, source_quality_score=95.0,
        )
        governance.update_node_confidence_from_trust(db, node.id, reason="test", created_by_service="test")
        updated = crud.get_knowledge_node(db, node.id)
        assert updated.confidence <= 0.6
    finally:
        db.close()


def test_two_independent_sources_can_exceed_safety_cap():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        tag = _tag()
        s1 = _make_source(db, m.id, domain="nist.gov", quality=95.0)
        s2 = _make_source(db, m.id, domain="iaea.org", quality=95.0)
        sts.recalculate(db, s1.id, reason="manual", service_name="test")
        sts.recalculate(db, s2.id, reason="manual", service_name="test")
        node = governance.upsert_node_with_evidence(
            db, label=f"Dose limit corroborated {tag}", node_type="Component",
            description="the maximum permissible dose is 20 mSv/year",
            research_source_id=s1.id, provider_used="deterministic", extractor_confidence=0.9,
            supports=True, source_quality_score=95.0,
        )
        governance.record_node_evidence(db, node.id, s2.id, supports=True, source_quality_score=95.0, created_by_service="test")
        governance.update_node_confidence_from_trust(db, node.id, reason="test", created_by_service="test")
        updated = crud.get_knowledge_node(db, node.id)
        assert updated.confidence > 0.6
    finally:
        db.close()


# ── 9. Manufacturer claim needs independent corroboration for high trust ───

def test_manufacturer_domain_capped_without_independent_corroboration():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id, domain="rapiscansystems.com", quality=95.0, url="https://rapiscansystems.com/spec")
        result = sts.recalculate(db, source.id, reason="manual", service_name="test")
        assert result.trust_status != "authoritative"
    finally:
        db.close()


def test_is_manufacturer_domain_detects_known_manufacturers():
    assert sts.is_manufacturer_domain("https://rapiscansystems.com/x") is True
    assert sts.is_manufacturer_domain("https://nist.gov/x") is False


# ── 10/11/12. User review: bounded effect, reject never deletes, reset recomputes ─

def test_user_review_has_bounded_effect():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id, quality=50.0)
        before = crud.get_research_source(db, source.id).dynamic_trust_score
        updated = sts.submit_user_review(db, source.id, "reviewer-1", "Trusted")
        assert updated.dynamic_trust_score > before
        assert updated.dynamic_trust_score - before <= 10.0
    finally:
        db.close()


def test_rejected_review_never_deletes_source_or_evidence():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        tag = _tag()
        source = _make_source(db, m.id, quality=50.0)
        node = governance.upsert_node_with_evidence(
            db, label=f"Rejectable Fact {tag}", node_type="Component", description="x",
            research_source_id=source.id, provider_used="deterministic", extractor_confidence=0.5,
            supports=True, source_quality_score=50.0,
        )
        updated = sts.submit_user_review(db, source.id, "reviewer-1", "Rejected")
        assert updated.trust_status == "rejected"
        assert crud.get_research_source(db, source.id) is not None
        assert crud.list_knowledge_evidence(db, node_id=node.id)  # evidence still present
        assert crud.get_knowledge_node(db, node.id) is not None
    finally:
        db.close()


def test_reset_review_recomputes():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id, quality=50.0)
        sts.submit_user_review(db, source.id, "reviewer-1", "Rejected")
        assert crud.get_research_source(db, source.id).trust_status == "rejected"
        restored = sts.reset_user_review(db, source.id, "reviewer-1")
        assert restored.trust_status != "rejected"
        review = crud.get_source_user_review(db, source.id, "reviewer-1")
        assert review.review_status is None
    finally:
        db.close()


# ── 13. A brand-new source starts "Unproven," not "Low Trust" ──────────────

def test_new_source_starts_unproven():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id, quality=10.0)  # even a LOW static score
        assert source.trust_status == "unproven"
    finally:
        db.close()


# ── 14. trust_algorithm_version is stamped and preserved ────────────────────

def test_algorithm_version_stamped():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id)
        assert source.trust_algorithm_version == sts.CURRENT_TRUST_ALGORITHM_VERSION
        updated = sts.recalculate(db, source.id, reason="manual", service_name="test")
        assert updated.trust_algorithm_version == sts.CURRENT_TRUST_ALGORITHM_VERSION
    finally:
        db.close()


# ── 15. Recalculation touches only the given source, not others ────────────

def test_recalculate_is_scoped_to_one_source():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        s1 = _make_source(db, m.id, quality=60.0)
        s2 = _make_source(db, m.id, quality=60.0)
        before_s2 = crud.get_research_source(db, s2.id).last_trust_calculated_at
        sts.recalculate(db, s1.id, reason="manual", service_name="test")
        after_s2 = crud.get_research_source(db, s2.id).last_trust_calculated_at
        assert before_s2 == after_s2  # untouched
    finally:
        db.close()


# ── 16. update_node_confidence_from_trust is the only path used ────────────

def test_governance_is_the_only_confidence_write_path(monkeypatch):
    db = SessionLocal()
    try:
        m = _make_mission(db)
        tag = _tag()
        source = _make_source(db, m.id, quality=80.0)
        node = governance.upsert_node_with_evidence(
            db, label=f"Bypass Check Fact {tag}", node_type="Component", description="x",
            research_source_id=source.id, provider_used="deterministic", extractor_confidence=0.5,
            supports=True, source_quality_score=80.0,
        )
        called = {"n": 0}
        real = governance.update_node_confidence_from_trust
        def _spy(*a, **k):
            called["n"] += 1
            return real(*a, **k)
        monkeypatch.setattr(governance, "update_node_confidence_from_trust", _spy)
        sts.recalculate(db, source.id, reason="manual", service_name="test")
        assert called["n"] >= 1
    finally:
        db.close()


# ── 17. Free Mode: zero network calls anywhere in the trust path ───────────

@pytest.mark.asyncio
async def test_trust_recalculation_never_calls_network(monkeypatch):
    async def _blocked(*_a, **_k):
        raise AssertionError("trust path must never touch the network")
    monkeypatch.setattr(httpx.AsyncClient, "get", _blocked)
    monkeypatch.setattr(httpx.AsyncClient, "post", _blocked)

    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id, quality=70.0)
        sts.recalculate(db, source.id, reason="manual", service_name="test")  # must not raise
    finally:
        db.close()


# ── 18. Chat responses are backed by real DB numbers ────────────────────────

@pytest.mark.asyncio
async def test_chat_why_trust_reflects_real_scores():
    from api.services.research_agent_chat_intent import handle_research_agent_intent, detect_research_agent_intent

    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id, quality=88.0)
        sts.recalculate(db, source.id, reason="manual", service_name="test")

        intent = detect_research_agent_intent("why do you trust this source")
        assert intent == {"action": "why_trust"}
        result = await handle_research_agent_intent(db, USER["id"], intent)
        assert result["type"] == "research_source_trust"
        assert result["source"]["quality_score"] == 88.0
        assert result["source"]["effective_trust_score"] == crud.get_research_source(db, result["source"]["id"]).effective_trust_score
    finally:
        db.close()


def test_api_trust_endpoint_returns_real_history(client):
    db = SessionLocal()
    m = _make_mission(db)
    source = _make_source(db, m.id, quality=75.0)
    sts.recalculate(db, source.id, reason="manual", service_name="test")
    db.close()

    resp = client.get(f"/api/research-agent/sources/{source.id}/trust")
    assert resp.status_code == 200
    body = resp.json()["source"]
    assert body["quality_score"] == 75.0

    hist_resp = client.get(f"/api/research-agent/sources/{source.id}/trust/history")
    assert hist_resp.status_code == 200
    assert len(hist_resp.json()["history"]) >= 1
