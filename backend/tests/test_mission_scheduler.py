"""
Bounded mission resume queue tests — Phase 2B.2.1.

Covers: classify_resumability() policy (test-origin/terminal/paused/retry-
waiting never auto-resume), MissionQueueManager bounded concurrency +
backpressure against real DB rows, atomic claim (concurrent claim attempts
on the same candidate — exactly one wins, using real OS threads since
asyncio tasks calling synchronous DB code never actually interleave),
expired-lease recovery (idempotent), and clean shutdown / crash-recovery via
release_expired_leases(). No real network calls anywhere in this file —
run_mission() itself is never invoked; a fake stand-in is used throughout,
same convention as tests/test_research_agent.py's `start_mission`
monkeypatching.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import asyncio
import threading
import time
from datetime import datetime, timedelta, timezone

import pytest

from api.config import settings
from api.db.base import SessionLocal
from api.db import crud
from api.services.research_agent.mission_queue import MissionQueueManager, classify_resumability

# Tests share the persistent tests/_test_scratch.db across repeated runs
# (see tests/conftest.py). Two complementary defenses, not one:
#   1. _make_mission() registers every mission it creates, and the autouse
#      fixture below archives them all after each test — this file's OWN
#      leftover rows can never compete as claim candidates in a LATER run.
#   2. A priority margin comfortably above the largest margin any OTHER
#      test file in this suite uses on the same time-based scheme — not
#      every file cleans up after itself (test_startup_lifespan.py's
#      1000-mission fixture deliberately leaves its rows in place as
#      startup-verification evidence, up to +500_000), so this file's own
#      priorities must still outrank those on the rare occasion two test
#      files run within the same real-time window.
_PRIORITY_BASE = int(time.time() * 1000) + 1_000_000
_created_mission_ids: list[str] = []


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _make_mission(db, *, priority=None, status="queued", origin="user", **fields):
    if priority is None:
        priority = _PRIORITY_BASE
    m = crud.create_research_mission(
        db, user_id=None, mission_text=f"scheduler-test-{_tag()}", priority=priority, origin=origin,
    )
    _created_mission_ids.append(m.id)
    if status != "queued" or fields:
        crud.update_research_mission(db, m.id, status=status, **fields)
        db.refresh(m)
    return m


@pytest.fixture(autouse=True)
def _archive_created_missions():
    """Every mission this test file creates is archived after the test
    completes — status="archived" is excluded from claim_next_mission()'s
    candidate query, so leftover rows can never win (or lose) a future
    test's claim race regardless of priority. Cleanup, not a bigger number,
    is what actually makes these tests deterministic against a shared,
    ever-growing scratch DB."""
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


# ── classify_resumability() — pure policy function ──────────────────────────

def test_classify_test_origin_never_resumes():
    db = SessionLocal()
    try:
        m = _make_mission(db, origin="test")
        eligible, reason = classify_resumability(m)
        assert eligible is False
        assert "test" in reason.lower()
    finally:
        db.close()


@pytest.mark.parametrize("status", ["completed", "stopped", "failed", "cancelled", "archived"])
def test_classify_terminal_statuses_never_resume(status):
    db = SessionLocal()
    try:
        m = _make_mission(db, status=status)
        eligible, _ = classify_resumability(m)
        assert eligible is False
    finally:
        db.close()


def test_classify_paused_never_auto_resumes():
    db = SessionLocal()
    try:
        m = _make_mission(db, status="paused")
        eligible, reason = classify_resumability(m)
        assert eligible is False
        assert "user" in reason.lower()
    finally:
        db.close()


def test_classify_retry_waiting_respects_next_retry_at():
    db = SessionLocal()
    try:
        future = datetime.now(timezone.utc) + timedelta(minutes=5)
        m = _make_mission(db, status="retry_waiting", next_retry_at=future)
        eligible, reason = classify_resumability(m)
        assert eligible is False
        assert "backoff" in reason.lower()

        past = datetime.now(timezone.utc) - timedelta(minutes=5)
        crud.update_research_mission(db, m.id, next_retry_at=past)
        db.refresh(m)
        eligible2, _ = classify_resumability(m)
        assert eligible2 is True
    finally:
        db.close()


def test_classify_queued_is_eligible():
    db = SessionLocal()
    try:
        m = _make_mission(db, status="queued")
        eligible, _ = classify_resumability(m)
        assert eligible is True
    finally:
        db.close()


# ── claim_next_mission() — atomic claim, exclusions ─────────────────────────

def test_claim_excludes_test_origin_and_terminal_and_paused():
    db = SessionLocal()
    try:
        excluded = [
            _make_mission(db, origin="test"),
            _make_mission(db, status="completed"),
            _make_mission(db, status="stopped"),
            _make_mission(db, status="paused"),
            _make_mission(db, status="archived"),
        ]
        eligible = _make_mission(db, priority=_PRIORITY_BASE + 10)  # highest priority — would win any race

        claimed = crud.claim_next_mission(db, worker_id="test-worker", lease_seconds=600)
        assert claimed is not None
        assert claimed.id == eligible.id
        assert claimed.id not in {m.id for m in excluded}
    finally:
        db.close()


def test_concurrent_claim_same_candidate_exactly_one_wins():
    """Real OS threads, each with its own SessionLocal() — asyncio tasks
    calling synchronous DB code never actually interleave in CPython, so
    this uses threading to produce a genuine race on the same row."""
    setup_db = SessionLocal()
    try:
        mission = _make_mission(setup_db, priority=_PRIORITY_BASE + 9)
        mission_id = mission.id
    finally:
        setup_db.close()

    results = []
    lock = threading.Lock()

    def _attempt(worker_id: str):
        db = SessionLocal()
        try:
            claimed = crud.claim_next_mission(db, worker_id=worker_id, lease_seconds=600, exclude_ids=None)
            with lock:
                results.append((worker_id, claimed.id if claimed else None))
        finally:
            db.close()

    threads = [threading.Thread(target=_attempt, args=(f"worker-{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    winners = [wid for wid, claimed_id in results if claimed_id == mission_id]
    assert len(winners) == 1, f"expected exactly one winner for mission {mission_id}, got {winners}"

    db = SessionLocal()
    try:
        final = crud.get_research_mission(db, mission_id)
        assert final.status == "claimed"
        assert final.claim_owner == winners[0]
    finally:
        db.close()


# ── release_expired_leases() — idempotent recovery ──────────────────────────

def test_expired_lease_recovered_exactly_once():
    db = SessionLocal()
    try:
        m = _make_mission(db, priority=_PRIORITY_BASE + 8)
        claimed = crud.claim_next_mission(db, worker_id="w1", lease_seconds=600)
        assert claimed.id == m.id
        crud.update_research_mission(db, m.id, claim_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))

        first = crud.release_expired_leases(db)
        assert first >= 1
        db.refresh(m)
        assert m.status == "queued"
        assert m.resume_count == 1

        second = crud.release_expired_leases(db)
        assert second == 0  # idempotent — nothing left to recover for this row
        db.refresh(m)
        assert m.resume_count == 1  # not double-incremented
    finally:
        db.close()


def test_orphaned_running_mission_with_no_lease_is_recovered():
    """Pre-2B.2.1 "running" rows never had a lease at all (claim_expires_at
    NULL) — release_expired_leases() must treat that the same as expired,
    not skip it forever."""
    db = SessionLocal()
    try:
        m = _make_mission(db, status="running")
        assert m.claim_expires_at is None
        recovered = crud.release_expired_leases(db)
        assert recovered >= 1
        db.refresh(m)
        assert m.status == "queued"
    finally:
        db.close()


# ── MissionQueueManager — bounded concurrency, backpressure, shutdown ───────

@pytest.mark.asyncio
async def test_bounded_concurrency_never_exceeds_max_active(monkeypatch):
    monkeypatch.setattr(settings, "research_max_active_missions", 2)
    monkeypatch.setattr(settings, "research_resume_batch_size", 5)
    monkeypatch.setattr(settings, "research_max_pending_in_memory", 10)
    monkeypatch.setattr(settings, "research_scheduler_startup_delay_s", 0)

    db = SessionLocal()
    try:
        tagged_ids = {_make_mission(db, priority=_PRIORITY_BASE + 20 + i).id for i in range(8)}
    finally:
        db.close()

    max_concurrent_seen = 0
    concurrent_now = 0
    started_ids: set[str] = set()
    lock = asyncio.Lock()

    async def fake_run_mission(mission_id: str) -> None:
        nonlocal max_concurrent_seen, concurrent_now
        async with lock:
            concurrent_now += 1
            max_concurrent_seen = max(max_concurrent_seen, concurrent_now)
        started_ids.add(mission_id)
        await asyncio.sleep(0.05)
        db2 = SessionLocal()
        try:
            crud.update_research_mission(db2, mission_id, status="completed")
        finally:
            db2.close()
        async with lock:
            concurrent_now -= 1

    qm = MissionQueueManager()
    await qm.start(fake_run_mission)
    try:
        for _ in range(100):
            await asyncio.sleep(0.05)
            if tagged_ids.issubset(started_ids):
                break
    finally:
        await qm.stop()

    assert max_concurrent_seen <= 2
    assert tagged_ids.issubset(started_ids)


@pytest.mark.asyncio
async def test_queue_manager_stop_is_clean_and_recoverable(monkeypatch):
    """A mission still mid-flight when stop() cancels its worker is left in
    "running" with a real lease — recoverable on the next bootstrap via
    release_expired_leases(), never silently lost."""
    monkeypatch.setattr(settings, "research_max_active_missions", 1)
    monkeypatch.setattr(settings, "research_resume_batch_size", 1)
    monkeypatch.setattr(settings, "research_max_pending_in_memory", 5)
    monkeypatch.setattr(settings, "research_scheduler_startup_delay_s", 0)
    monkeypatch.setattr(settings, "research_claim_lease_seconds", 600)

    db = SessionLocal()
    try:
        m = _make_mission(db, priority=_PRIORITY_BASE + 30)
        mission_id = m.id
    finally:
        db.close()

    started = asyncio.Event()

    async def slow_run_mission(mid: str) -> None:
        started.set()
        await asyncio.sleep(30)  # cancelled by stop() long before this elapses

    qm = MissionQueueManager()
    await qm.start(slow_run_mission)
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
    finally:
        await qm.stop()

    db = SessionLocal()
    try:
        m = crud.get_research_mission(db, mission_id)
        assert m.status == "running"
        assert m.claim_expires_at is not None
        # Simulate time passing past the lease with no process alive to renew it.
        crud.update_research_mission(db, mission_id, claim_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
        recovered = crud.release_expired_leases(db)
        assert recovered >= 1
        db.refresh(m)
        assert m.status == "queued"
    finally:
        db.close()
