"""Bounded, DB-backed resume queue — Phase 2B.2.1.

Replaces job_runner.py's old unbounded pattern:

    for mission in crud.list_resumable_research_missions(db):   # ALL rows
        await asyncio.sleep(2)
        asyncio.create_task(run_mission(mission.id))            # unbounded fan-out

with: claim a small batch at a time (crud.claim_next_mission, an atomic
per-row UPDATE — see api.db.crud), hand claimed mission ids to a bounded
asyncio.Queue (backpressure — the loader blocks once the queue is full
rather than piling up unbounded work in memory), and run at most
settings.research_max_active_missions missions concurrently via a fixed
pool of worker coroutines.

run_mission() itself (api.services.research_agent.job_runner) is NOT
modified — its crawl loop, checkpoint handling, and status-guard
(`mission.status not in ("queued", "running")`) stay exactly as they were.
This module's worker flips a claimed mission to "running" immediately
before handing it to run_mission(), and runs a companion heartbeat task
alongside it (not inside it) so a long crawl doesn't have its lease
reclaimed by release_expired_leases() mid-run without needing any change
to run_mission()'s internals.
"""
from __future__ import annotations

import asyncio
import logging
import socket
import uuid
from datetime import datetime, timezone
from typing import Awaitable, Callable

from api.config import settings
from api.db.base import SessionLocal
from api.db import crud

log = logging.getLogger(__name__)

# Terminal / non-resumable statuses — never claimed, listed here (rather than
# only implicitly via claim_next_mission's WHERE clause) so
# classify_resumability() below can explain *why* for the preview endpoint.
_TERMINAL_STATUSES = {"completed", "stopped", "failed", "cancelled", "archived"}
_ACTIVE_STATUSES = {"claimed", "running"}


def _new_worker_prefix() -> str:
    host = socket.gethostname()
    return f"{host}-{uuid.uuid4().hex[:8]}"


def classify_resumability(mission, now: datetime | None = None) -> tuple[bool, str]:
    """Pure classification function — same rules claim_next_mission()'s SQL
    WHERE clause enforces, expressed here for the resume-preview endpoint so
    it can explain *why* a mission would or wouldn't be picked up without
    actually claiming anything.

    Policy (per the product spec's §11):
      - origin="test" never auto-resumes (real stored fact, not inferred).
      - terminal statuses (completed/stopped/failed/cancelled/archived)
        never auto-resume — a user/admin must explicitly retry.
      - "paused" never auto-resumes — requires explicit user resume.
      - "claimed"/"running" are already active — not resume candidates.
      - "retry_waiting" only resumes once next_retry_at has elapsed.
      - "queued" is always eligible.
    """
    now = now or datetime.now(timezone.utc)
    if mission.origin == "test":
        return False, "test-generated mission — never auto-resumed"
    if mission.status in _TERMINAL_STATUSES:
        return False, f"terminal status '{mission.status}' — requires explicit retry"
    if mission.status == "paused":
        return False, "paused — requires explicit user resume"
    if mission.status in _ACTIVE_STATUSES:
        return False, f"already active ('{mission.status}')"
    if mission.status == "retry_waiting":
        next_retry_at = mission.next_retry_at
        # SQLite drops tzinfo on round-trip — treat a naive value as UTC
        # (every write path in this codebase stores UTC) rather than raise.
        if next_retry_at is not None and next_retry_at.tzinfo is None:
            next_retry_at = next_retry_at.replace(tzinfo=timezone.utc)
        if next_retry_at and next_retry_at > now:
            return False, f"retry backoff not yet elapsed (next_retry_at={next_retry_at.isoformat()})"
        return True, "retry backoff elapsed — eligible"
    if mission.status == "queued":
        return True, "queued — eligible"
    return False, f"unrecognized status '{mission.status}'"


class QueueMetrics:
    def __init__(self) -> None:
        self.claimed_total = 0
        self.started_total = 0
        self.completed_total = 0
        self.lease_recoveries_total = 0
        self.duplicate_claims_prevented_total = 0
        self.startup_resume_candidates = 0


class MissionQueueManager:
    """Owns the bounded queue + worker pool. One instance lives on
    MissionScheduler (job_runner.py) — not a second parallel scheduler."""

    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] | None = None
        self._loader_task: asyncio.Task | None = None
        self._worker_tasks: list[asyncio.Task] = []
        self._stop_event: asyncio.Event | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._active_count = 0
        self._active_lock = asyncio.Lock()
        self.metrics = QueueMetrics()
        self.worker_prefix = _new_worker_prefix()
        self.state = "initializing"  # see startup.SchedulerReadiness for the full vocabulary
        self._draining = False

    @property
    def active_count(self) -> int:
        return self._active_count

    @property
    def queue_depth(self) -> int:
        return self._queue.qsize() if self._queue is not None else 0

    def drain(self) -> None:
        """Stop claiming NEW work; missions already running are left to
        finish naturally (unlike stop(), which cancels in-flight workers).
        Reversible via resume_claiming() — used for both the drain-for-
        shutdown and the operational pause/resume admin endpoints, since
        both are "stop claiming new work" at heart."""
        self._draining = True
        self.state = "degraded"
        log.info("MissionQueueManager draining — no new claims until resume_claiming() is called")

    def resume_claiming(self) -> None:
        self._draining = False
        self.state = "ready"
        log.info("MissionQueueManager resumed claiming")

    async def start(self, run_mission_fn: Callable[[str], Awaitable[None]]) -> None:
        if self._loader_task is not None:
            return
        self._queue = asyncio.Queue(maxsize=max(1, settings.research_max_pending_in_memory))
        self._semaphore = asyncio.Semaphore(max(1, settings.research_max_active_missions))
        self._stop_event = asyncio.Event()
        self.state = "resume_queue_loading"

        # Controlled warm startup: the delay lives INSIDE this background
        # task, never blocking main.py's startup handler / the main thread.
        self._loader_task = asyncio.create_task(self._load_loop())
        self._worker_tasks = [
            asyncio.create_task(self._worker_loop(i, run_mission_fn))
            for i in range(max(1, settings.research_max_active_missions))
        ]
        log.info(
            "MissionQueueManager started: max_active=%d batch_size=%d max_pending=%d startup_delay=%ds",
            settings.research_max_active_missions, settings.research_resume_batch_size,
            settings.research_max_pending_in_memory, settings.research_scheduler_startup_delay_s,
        )

    async def stop(self) -> None:
        """Graceful shutdown: stop accepting new work, cancel the loader and
        worker loops, let run_mission() finish its own commit/checkpoint on
        cancellation (it already closes its session in a finally: block —
        see job_runner.run_mission), never leave a mission falsely
        "running" in the DB — release_expired_leases() on the next startup
        recovers anything genuinely interrupted mid-flight."""
        if self._stop_event is not None:
            self._stop_event.set()
        tasks = [t for t in ([self._loader_task] + self._worker_tasks) if t is not None]
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        self._loader_task = None
        self._worker_tasks = []
        self.state = "initializing"
        log.info("MissionQueueManager stopped")

    async def _load_loop(self) -> None:
        assert self._stop_event is not None and self._queue is not None
        if settings.research_scheduler_startup_delay_s > 0:
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=settings.research_scheduler_startup_delay_s
                )
                return  # stop() was called during the startup delay
            except asyncio.TimeoutError:
                pass

        self.state = "ready"
        while not self._stop_event.is_set():
            if self._draining:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    pass
                continue

            claimed_this_round = 0
            db = SessionLocal()
            try:
                for _ in range(settings.research_resume_batch_size):
                    if self._queue.full():
                        break
                    mission = crud.claim_next_mission(
                        db, worker_id=f"{self.worker_prefix}-loader",
                        lease_seconds=settings.research_claim_lease_seconds,
                    )
                    if not mission:
                        break
                    claimed_this_round += 1
                    self.metrics.claimed_total += 1
                    try:
                        await self._queue.put(mission.id)
                    except asyncio.CancelledError:
                        raise
            finally:
                db.close()

            wait = 1.0 if claimed_this_round else 5.0
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass

    async def _worker_loop(self, index: int, run_mission_fn: Callable[[str], Awaitable[None]]) -> None:
        assert self._stop_event is not None and self._queue is not None and self._semaphore is not None
        worker_id = f"{self.worker_prefix}-w{index}"
        while not self._stop_event.is_set():
            try:
                mission_id = await asyncio.wait_for(self._queue.get(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise

            async with self._semaphore:
                async with self._active_lock:
                    self._active_count += 1
                heartbeat_task = asyncio.create_task(self._heartbeat_loop(mission_id, worker_id))
                try:
                    if await self._prepare_for_run(mission_id, worker_id):
                        self.metrics.started_total += 1
                        await run_mission_fn(mission_id)
                        self.metrics.completed_total += 1
                except asyncio.CancelledError:
                    raise
                except Exception:
                    log.exception("mission_id=%s worker_id=%s run_mission failed unexpectedly", mission_id, worker_id)
                finally:
                    heartbeat_task.cancel()
                    try:
                        await heartbeat_task
                    except (asyncio.CancelledError, Exception):
                        pass
                    async with self._active_lock:
                        self._active_count -= 1
                    self._queue.task_done()

    async def _prepare_for_run(self, mission_id: str, worker_id: str) -> bool:
        """Flip claimed -> running right before handing off to run_mission()
        (which itself only accepts status "queued"/"running" — left
        unmodified). Returns False (skip) if the mission is no longer in a
        runnable state — e.g. a user paused/stopped it while it sat in the
        in-memory queue between being claimed and a worker picking it up."""
        db = SessionLocal()
        try:
            mission = crud.get_research_mission(db, mission_id)
            if not mission or mission.claim_owner != f"{self.worker_prefix}-loader" or mission.status != "claimed":
                log.info("mission_id=%s worker_id=%s no longer claimable at handoff (status=%s) — skipping",
                          mission_id, worker_id, mission.status if mission else "missing")
                return False
            crud.update_research_mission(db, mission_id, status="running", claim_owner=worker_id)
            return True
        finally:
            db.close()

    async def _heartbeat_loop(self, mission_id: str, worker_id: str) -> None:
        """Keeps the DB lease alive while run_mission() is executing, without
        run_mission() itself needing any awareness of leases — a periodic
        sibling task, not code inside the crawl loop."""
        interval = max(5, settings.research_claim_lease_seconds // 3)
        try:
            while True:
                await asyncio.sleep(interval)
                db = SessionLocal()
                try:
                    ok = crud.heartbeat_mission_claim(db, mission_id, worker_id, settings.research_claim_lease_seconds)
                    if not ok:
                        log.warning("mission_id=%s worker_id=%s heartbeat failed — claim may have been reclaimed", mission_id, worker_id)
                finally:
                    db.close()
        except asyncio.CancelledError:
            return
