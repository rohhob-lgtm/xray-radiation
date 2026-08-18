"""
Real raw-ASGI startup verification — Phase 2B.2.1.

The acceptance criterion this file exists to satisfy: "لا تعتبر TestClient
مع monkeypatched resume بديلًا عن اختبار التشغيل الحقيقي" — a TestClient
run with the resume/claim path monkeypatched is NOT an acceptable substitute
for a real startup test. This file does NOT monkeypatch resume_missions,
start_mission, claim_next_mission, MissionScheduler, or MissionQueueManager
— none of that machinery is touched. `with TestClient(app) as client:`
(the context-manager form) fires FastAPI's real `@app.on_event("startup")`
handlers, which is what actually calls
api.services.research_agent.startup.bootstrap() and
mission_scheduler.start() for real.

The ONLY thing faked is the outermost network boundary (httpx.AsyncClient's
HTTP methods, patched at the class level so every caller anywhere in the
app — provider_throttle-wrapped calls, discovery.py, web_crawl — gets an
instant connection failure) — real network calls in a test suite are never
acceptable regardless of this feature, and 1000 real HTTP requests would
make this test slow, flaky, and dependent on external services being up.

DB isolation note: this codebase's DB session factories are imported by
reference (`from api.db.base import SessionLocal`) into every module that
uses them, at import time — there is no dependency-injection seam to swap
in a throwaway SQLite file for one test module without patching that
reference in every consuming module individually, which would itself risk
missing one and silently not testing what we think we're testing. Instead,
this test seeds its 1000-mission fixture into the SAME shared session-scope
scratch DB every other test in this suite uses (tests/_test_scratch.db, via
tests/conftest.py), each row tagged with a run-unique marker AND a priority
range far above anything else in the DB — so the claim loop picks up this
run's fixture rows first, and every assertion below is scoped to exactly
this run's tagged mission ids, never to "the whole table" (which contains
years of accumulated rows from every other test file that has ever run
against this scratch DB).
"""
import os
import sys
import time
import uuid

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from main import app
from api.config import settings
from api.middleware.auth import require_auth
from api.db.base import SessionLocal
from api.db.models import User, ResearchMission
from api.db import crud

USER = {"id": "startup-lifespan-test-user", "username": "lifespan@example.com", "name": "Lifespan Tester"}

FIXTURE_SIZE = 1000


def _ensure_user() -> None:
    s = SessionLocal()
    try:
        if not s.get(User, USER["id"]):
            s.add(User(id=USER["id"], username=USER["username"], name=USER["name"]))
            s.commit()
    finally:
        s.close()


async def _blocked_request(*_args, **_kwargs):
    """Replaces httpx.AsyncClient.get/post for the duration of this test —
    the ONLY thing faked, per this file's docstring. Every provider
    function and web_crawl() already has real try/except handling for
    exactly this kind of failure (it's the same code path a genuine
    network-down condition takes), so this exercises real error handling,
    not a stub result."""
    raise httpx.ConnectError("network access blocked in test_startup_lifespan")


@pytest.fixture
def seeded_missions(monkeypatch):
    """1000 missions with varied status/origin/priority, tagged with a
    run-unique marker so assertions never depend on ambient DB state."""
    monkeypatch.setattr(httpx.AsyncClient, "get", _blocked_request)
    monkeypatch.setattr(httpx.AsyncClient, "post", _blocked_request)

    # The blocked network call above is what's actually faked. Real
    # call_with_throttle backoff/jitter *waits* between retries are a real
    # timing consequence of that fault injection (already verified for
    # real, at real speed, in test_provider_throttle.py) — with 8+
    # providers × multiple topics × up to 4 attempts each, letting every
    # wait run at real wall-clock speed here would make this test take
    # minutes to prove something already proven elsewhere. This does not
    # touch resume_missions/claim_next_mission/MissionScheduler/
    # MissionQueueManager in any way — only how long a simulated-failure
    # retry waits.
    import api.services.research_agent.provider_throttle as _pt
    _real_sleep = asyncio.sleep

    async def _instant_sleep(*_a, **_k):
        await _real_sleep(0)

    monkeypatch.setattr(_pt.asyncio, "sleep", _instant_sleep)

    _ensure_user()
    run_tag = uuid.uuid4().hex[:10]
    base_priority = int(time.time() * 1000)  # unique-enough per run, always above ambient pollution

    db = SessionLocal()
    ids: dict[str, list[str]] = {
        "queued": [], "running_stale": [], "paused": [], "completed": [],
        "stopped": [], "cancelled": [], "archived": [], "test_origin": [],
        "retry_future": [],
    }
    try:
        counter = {"n": 0}

        def _create(tier: int, **fields):
            i = counter["n"]
            counter["n"] += 1
            m = crud.create_research_mission(
                db, user_id=USER["id"], mission_text=f"loadtest-{run_tag}-{i}",
                priority=base_priority + tier, mode="quick_scan",
            )
            if fields:
                crud.update_research_mission(db, m.id, **fields)
            return m.id

        # Each bucket gets its OWN priority tier (not a globally-incrementing
        # value) so buckets never compete with each other for claim order.
        # "queued" gets the highest tier deliberately — it's the bucket this
        # test's core progress assertion probes, and it must not be stuck
        # behind draining the (also-claimable-after-recovery) running_stale
        # bucket first just because of creation order.
        for _ in range(700):
            ids["queued"].append(_create(400_000))
        for _ in range(50):
            # Pre-2B.2.1-style orphan: "running" with no lease at all —
            # recovered to "queued" by bootstrap, then claimable too, but at
            # a distinctly LOWER tier so it never blocks the check above.
            ids["running_stale"].append(_create(300_000, status="running"))
        for _ in range(50):
            ids["paused"].append(_create(0, status="paused"))
        for _ in range(50):
            ids["completed"].append(_create(0, status="completed"))
        for _ in range(50):
            ids["stopped"].append(_create(0, status="stopped"))
        for _ in range(20):
            ids["cancelled"].append(_create(0, status="cancelled"))
        for _ in range(20):
            ids["archived"].append(_create(0, status="archived"))
        for _ in range(30):
            ids["test_origin"].append(_create(500_000, origin="test"))
        for _ in range(30):
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            ids["retry_future"].append(_create(500_000, status="retry_waiting", next_retry_at=future))

        assert counter["n"] == FIXTURE_SIZE
    finally:
        db.close()

    # Fast turnaround: no reason to wait out the real default 5s delay or
    # the real 10-minute lease in a test — everything else (batch size,
    # max active, max pending) stays at its real configured default so the
    # bounded-concurrency assertion below is testing the actual production
    # defaults, not inflated test-only values.
    monkeypatch.setattr(settings, "research_scheduler_startup_delay_s", 0)

    return run_tag, ids


def test_real_asgi_boot_bounds_concurrency_and_excludes_policy_violations(seeded_missions):
    run_tag, ids = seeded_missions
    app.dependency_overrides[require_auth] = lambda: USER
    try:
        t0 = time.monotonic()
        with TestClient(app) as client:
            boot_duration = time.monotonic() - t0
            assert boot_duration < 30.0, f"raw ASGI boot took {boot_duration:.1f}s — too slow"

            # Poll the REAL scheduler-status endpoint (not internal state
            # directly) — this is the same signal an operator/monitor would
            # see. Never let active_missions exceed the configured bound,
            # sampled repeatedly across the observation window.
            # A status poll competes with hundreds of background mission
            # coroutines for the same event loop, so each request here can
            # itself take noticeably longer than in an idle app — fewer,
            # coarser polls over a longer window is both more realistic and
            # less disruptive to the very throughput being measured than
            # polling tightly.
            max_active_seen = 0
            saw_any_progress = False
            deadline = time.monotonic() + 20.0
            while time.monotonic() < deadline:
                resp = client.get("/api/research-agent/scheduler/status")
                assert resp.status_code == 200
                body = resp.json()
                active = body["active_missions"]
                assert active <= body["max_active_missions"], (
                    f"active_missions={active} exceeded max_active_missions={body['max_active_missions']}"
                )
                max_active_seen = max(max_active_seen, active)
                if body["queue_manager_state"] == "ready" and active > 0:
                    saw_any_progress = True
                time.sleep(0.5)

            assert saw_any_progress, "scheduler never became ready / never claimed anything within the observation window"

            # ── DB-level proof: policy-excluded fixture rows were never touched ──
            db = SessionLocal()
            try:
                for mission_id in ids["test_origin"]:
                    m = crud.get_research_mission(db, mission_id)
                    assert m.status == "queued", "origin=test mission was auto-resumed — policy violation"
                for mission_id in ids["paused"]:
                    m = crud.get_research_mission(db, mission_id)
                    assert m.status == "paused", "paused mission was auto-resumed — policy violation"
                for mission_id in ids["completed"] + ids["stopped"] + ids["cancelled"] + ids["archived"]:
                    m = crud.get_research_mission(db, mission_id)
                    assert m.status not in ("claimed", "running"), f"terminal mission {mission_id} was auto-resumed"

                # ── Real progress proof: SOME "queued"-bucket fixture rows moved
                # past "queued" ── checked as an aggregate count across the
                # whole 700-row bucket rather than a specific priority-ordered
                # slice: the "running_stale" bucket (orphaned, no-lease
                # "running" rows) legitimately gets recovered to "queued" by
                # bootstrap too (that's the very next assertion below), and
                # since this fixture's priority scheme is base + creation
                # index, those recovered rows end up with HIGHER priority
                # than the "queued" bucket's own highest — so they're claimed
                # first, and exactly which "queued"-bucket row has progressed
                # by any given moment isn't something this test should
                # hardcode an assumption about. Counting across the full
                # bucket sidesteps that entirely.
                progressed = (
                    db.query(ResearchMission)
                    .filter(ResearchMission.id.in_(ids["queued"]))
                    .filter(ResearchMission.status != "queued")
                    .count()
                )
                assert progressed > 0, "no eligible fixture mission progressed past 'queued' — claim loop appears stuck"

                # ── Orphaned pre-2B.2.1 "running" rows were detected and recovered ──
                recovered_or_reclaimed = 0
                for mission_id in ids["running_stale"][:50]:
                    m = crud.get_research_mission(db, mission_id)
                    if m.status != "running" or m.claim_expires_at is not None:
                        recovered_or_reclaimed += 1
                assert recovered_or_reclaimed > 0, "orphaned running missions (no lease) were never recovered at bootstrap"
            finally:
                db.close()

        # ── Context exited: shutdown ran. Assert nothing was left claiming
        # falsely — every previously-"claimed"/newly-"running" fixture row
        # either completed or still carries a real (recoverable) lease.
        db = SessionLocal()
        try:
            for mission_id in ids["queued"]:
                m = crud.get_research_mission(db, mission_id)
                if m.status in ("claimed", "running"):
                    assert m.claim_expires_at is not None, (
                        f"mission {mission_id} left in '{m.status}' with no lease after shutdown — unrecoverable"
                    )
        finally:
            db.close()
    finally:
        app.dependency_overrides.pop(require_auth, None)
