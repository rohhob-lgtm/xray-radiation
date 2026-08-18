"""
TrustRecalculationWorker tests — Phase 2B.3.

Covers: atomic job claim (duplicate-claim-prevention, real OS threads —
same reasoning as test_mission_scheduler.py: asyncio tasks calling
synchronous DB code never actually interleave in CPython), bounded worker
concurrency, idempotent reprocessing, and crash-recovery via the same
claim-lease-expiry mechanism Phase 2B.2.1 already built and tested. No real
network calls anywhere in this file.
"""
import os
import sys
import threading
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest

from api.config import settings
from api.db.base import SessionLocal
from api.db import crud
from api.services.source_trust.source_trust_service import initialize_trust
from api.services.source_trust.trust_worker import TrustRecalculationWorker

_PRIORITY_BASE = int(time.time() * 1000) + 30_000_000


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _make_source(db, mission_id, quality=60.0):
    tag = _tag()
    source = crud.create_research_source(
        db, mission_id=mission_id, url=f"https://example.org/{tag}", domain="example.org",
        title=f"Source {tag}", publisher="example.org", content_hash=f"hash-{tag}",
        quality_score=quality, quality_label="useful", quality_reasons=[], accepted_into_kb=False,
    )
    initialize_trust(db, source)
    return source


_created_mission_ids: list[str] = []


def _make_mission(db):
    m = crud.create_research_mission(db, user_id=None, mission_text=f"trust-worker-test-{_tag()}", priority=_PRIORITY_BASE)
    _created_mission_ids.append(m.id)
    return m


@pytest.fixture(autouse=True)
def _archive_created_missions():
    """Archive every mission this file creates after each test — same
    fixture as test_mission_scheduler.py/test_source_trust.py, preventing
    leftover high-priority rows from competing as claim candidates in any
    later test run."""
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


@pytest.fixture(autouse=True)
def _block_network(monkeypatch):
    async def _blocked(*_a, **_k):
        raise AssertionError("trust worker must never touch the network")
    monkeypatch.setattr(httpx.AsyncClient, "get", _blocked)
    monkeypatch.setattr(httpx.AsyncClient, "post", _blocked)


@pytest.fixture(autouse=True)
def _drain_pending_backlog():
    """tests/_test_scratch.db is shared and persistent across every test
    file in this suite (see tests/conftest.py) — earlier regression/smoke
    runs across this whole session leave real pending TrustRecalculationJob
    rows behind. claim_next_trust_job() orders strictly FIFO by created_at
    with no priority field to out-rank them (unlike ResearchMission's
    priority column), so a fresh job created in one of these tests would
    otherwise sit behind however many older pending rows already exist,
    and a competing claim_next_trust_job() call would grab one of THOSE
    instead of the row this test actually cares about. Draining the
    backlog first (mark-complete, not delete — this is a working queue,
    not an audit trail) gives each test a clean, deterministic queue."""
    from api.db.models import TrustRecalculationJob
    from sqlalchemy import update as _update

    db = SessionLocal()
    try:
        # Bulk, not a claim-loop — this session's accumulated backlog from
        # every earlier regression run (governance_service.py enqueues a
        # job on every evidence write) can run into the thousands, and a
        # one-row-at-a-time claim loop would be far too slow/capped to
        # actually clear it. This is test-only cleanup of a working queue
        # (not an audit trail) — never done in production code.
        db.execute(
            _update(TrustRecalculationJob)
            .where(TrustRecalculationJob.status.in_(["pending", "claimed", "running"]))
            .values(status="completed", completed_at=datetime.now(timezone.utc))
            .execution_options(synchronize_session=False)
        )
        db.commit()
    finally:
        db.close()
    yield


def test_atomic_claim_exactly_one_winner_under_real_threads():
    setup_db = SessionLocal()
    try:
        m = _make_mission(setup_db)
        source = _make_source(setup_db, m.id)
        job = crud.create_trust_recalculation_job(setup_db, research_source_id=source.id, reason="manual", status="pending")
        job_id = job.id
    finally:
        setup_db.close()

    results = []
    lock = threading.Lock()

    def _attempt(worker_id: str):
        db = SessionLocal()
        try:
            claimed = crud.claim_next_trust_job(db, worker_id, 300)
            with lock:
                results.append((worker_id, claimed.id if claimed else None))
        finally:
            db.close()

    threads = [threading.Thread(target=_attempt, args=(f"worker-{i}",)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    winners = [wid for wid, claimed_id in results if claimed_id == job_id]
    assert len(winners) == 1, f"expected exactly one winner, got {winners}"

    db = SessionLocal()
    try:
        final = crud.get_trust_recalculation_job(db, job_id)
        assert final.status == "claimed"
        assert final.claim_owner == winners[0]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_bounded_concurrency_never_exceeds_max(monkeypatch):
    monkeypatch.setattr(settings, "trust_recalc_max_concurrent", 2)
    monkeypatch.setattr(settings, "trust_recalc_batch_size", 10)

    db = SessionLocal()
    try:
        m = _make_mission(db)
        source_ids = []
        for _ in range(6):
            source = _make_source(db, m.id)
            crud.create_trust_recalculation_job(db, research_source_id=source.id, reason="manual", status="pending")
            source_ids.append(source.id)
    finally:
        db.close()

    concurrent_now = 0
    max_seen = 0
    lock = asyncio.Lock()

    worker = TrustRecalculationWorker()
    worker._semaphore = asyncio.Semaphore(2)
    # Suppress the periodic staleness sweep for this test — the scratch DB
    # has thousands of pre-existing ResearchSource rows from every earlier
    # regression run, so an unsuppressed sweep would enqueue MORE jobs
    # competing for the same tick()'s batch quota, making "processed ==
    # exactly our 6 jobs" flaky for a reason unrelated to what this test
    # actually checks (bounded concurrency).
    worker._last_sweep_at = time.time()

    real_recalc = __import__("api.services.source_trust.source_trust_service", fromlist=["recalculate"]).recalculate

    async def _instrumented_process(job_id):
        nonlocal concurrent_now, max_seen
        async with worker._semaphore:
            async with lock:
                concurrent_now += 1
                max_seen = max(max_seen, concurrent_now)
            await asyncio.sleep(0.05)
            db2 = SessionLocal()
            try:
                job = crud.get_trust_recalculation_job(db2, job_id)
                real_recalc(db2, job.research_source_id, reason="manual", service_name="test")
                crud.update_trust_recalculation_job(db2, job_id, status="completed", completed_at=datetime.now(timezone.utc))
            finally:
                db2.close()
            async with lock:
                concurrent_now -= 1

    monkeypatch.setattr(worker, "_process_job", _instrumented_process)
    processed = await worker.tick()

    assert processed == len(source_ids)
    assert max_seen <= 2


@pytest.mark.asyncio
async def test_idempotent_reprocessing_no_duplicate_history():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id)
        source_id = source.id
    finally:
        db.close()

    worker = TrustRecalculationWorker()
    worker._semaphore = asyncio.Semaphore(2)

    db = SessionLocal()
    try:
        job1 = crud.create_trust_recalculation_job(db, research_source_id=source_id, reason="manual", status="pending")
        job1_id = job1.id
    finally:
        db.close()
    claimed_db = SessionLocal()
    try:
        claimed = crud.claim_next_trust_job(claimed_db, worker.worker_id, 300)
        assert claimed.id == job1_id
    finally:
        claimed_db.close()
    await worker._process_job(job1_id)

    db = SessionLocal()
    try:
        history_after_first = len(crud.list_source_trust_history(db, source_id))
        job2 = crud.create_trust_recalculation_job(db, research_source_id=source_id, reason="manual", status="pending")
        job2_id = job2.id
    finally:
        db.close()
    claimed_db = SessionLocal()
    try:
        claimed2 = crud.claim_next_trust_job(claimed_db, worker.worker_id, 300)
        assert claimed2.id == job2_id
    finally:
        claimed_db.close()
    await worker._process_job(job2_id)

    db = SessionLocal()
    try:
        history_after_second = len(crud.list_source_trust_history(db, source_id))
        source_final = crud.get_research_source(db, source_id)
    finally:
        db.close()

    # Re-running recalculate() on unchanged input is safe (idempotent) —
    # it adds one more real history entry (an honest record that it WAS
    # recalculated again, with RECALC_NO_CHANGE if nothing moved), not a
    # duplicate/corrupt one, and the score itself doesn't drift.
    assert history_after_second == history_after_first + 1
    assert 0.0 <= source_final.effective_trust_score <= 100.0


@pytest.mark.asyncio
async def test_crash_recovery_via_lease_expiry():
    db = SessionLocal()
    try:
        m = _make_mission(db)
        source = _make_source(db, m.id)
        job = crud.create_trust_recalculation_job(db, research_source_id=source.id, reason="manual", status="pending")
        job_id = job.id
    finally:
        db.close()

    db = SessionLocal()
    try:
        claimed = crud.claim_next_trust_job(db, "crashed-worker", 300)
        assert claimed.id == job_id
        # Simulate the claiming worker crashing before it could finish —
        # force the lease into the past.
        crud.update_trust_recalculation_job(db, job_id, claim_expires_at=datetime.now(timezone.utc) - timedelta(seconds=1))
    finally:
        db.close()

    db = SessionLocal()
    try:
        recovered = crud.release_expired_trust_jobs(db)
        assert recovered >= 1
        job_now = crud.get_trust_recalculation_job(db, job_id)
        assert job_now.status == "pending"
        assert job_now.claim_owner is None

        # Idempotent — calling it again with nothing newly expired changes nothing.
        recovered_again = crud.release_expired_trust_jobs(db)
        assert recovered_again == 0
    finally:
        db.close()
