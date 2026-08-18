"""TrustRecalculationWorker — Phase 2B.3.

Same bounded claim/worker-pool PATTERN as
api.services.research_agent.mission_queue.MissionQueueManager (Phase
2B.2.1) — atomic single-row claim (crud.claim_next_trust_job), bounded
concurrency, no unbounded fan-out, crash-recovery via lease expiry
(crud.release_expired_trust_jobs) — but a distinct, smaller worker rather
than forcing this unrelated job type through MissionQueueManager itself,
which is tightly coupled to ResearchMission's own state machine.

recalculate() is a pure function of current DB state (see
source_trust_service.py) — reprocessing the same job twice is always safe,
which is what makes crash-recovery via lease expiry correct here: a
recovered job just runs recalculate() again with no side effect beyond a
fresh SourceTrustHistory row (an accurate record that it *was*
recalculated again, not a bug).
"""
from __future__ import annotations

import asyncio
import logging
import socket
import uuid
from datetime import datetime, timedelta, timezone

from api.config import settings
from api.db.base import SessionLocal
from api.db import crud

log = logging.getLogger(__name__)

_STALENESS_SWEEP_INTERVAL_S = 3600  # hourly


def _new_worker_id() -> str:
    return f"{socket.gethostname()}-trust-{uuid.uuid4().hex[:8]}"


class TrustRecalculationWorker:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self.worker_id = _new_worker_id()
        self._last_sweep_at: float = 0.0
        self.processed_total = 0
        self.failed_total = 0

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._semaphore = asyncio.Semaphore(max(1, settings.trust_recalc_max_concurrent))
        self._task = asyncio.create_task(self._run())
        log.info(
            "TrustRecalculationWorker started (max_concurrent=%d batch=%d)",
            settings.trust_recalc_max_concurrent, settings.trust_recalc_batch_size,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        assert self._stop_event is not None
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        log.info("TrustRecalculationWorker stopped")

    async def _run(self) -> None:
        assert self._stop_event is not None
        db = SessionLocal()
        try:
            recovered = crud.release_expired_trust_jobs(db)
            if recovered:
                log.info("TrustRecalculationWorker: recovered %d orphaned job(s) at startup", recovered)
        finally:
            db.close()

        while not self._stop_event.is_set():
            try:
                processed = await self.tick()
            except Exception:
                log.exception("TrustRecalculationWorker tick failed")
                processed = 0
            wait = 2.0 if processed else 10.0
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=wait)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> int:
        """One bounded round: release expired leases, sweep for staleness,
        claim + process up to trust_recalc_batch_size jobs with bounded
        concurrency. Public so tests can call it directly without waiting."""
        db = SessionLocal()
        try:
            crud.release_expired_trust_jobs(db)
            self._maybe_sweep_stale_sources(db)
        finally:
            db.close()

        claimed_ids: list[str] = []
        for _ in range(settings.trust_recalc_batch_size):
            db = SessionLocal()
            try:
                job = crud.claim_next_trust_job(db, self.worker_id, settings.trust_recalc_claim_lease_seconds)
            finally:
                db.close()
            if not job:
                break
            claimed_ids.append(job.id)

        if claimed_ids:
            await asyncio.gather(*(self._process_job(jid) for jid in claimed_ids), return_exceptions=True)
        return len(claimed_ids)

    def _maybe_sweep_stale_sources(self, db) -> None:
        now = datetime.now(timezone.utc)
        if (now.timestamp() - self._last_sweep_at) < _STALENESS_SWEEP_INTERVAL_S:
            return
        self._last_sweep_at = now.timestamp()
        cutoff = now - timedelta(days=settings.trust_recalc_staleness_days)
        stale = crud.list_stale_research_sources(db, cutoff, limit=settings.trust_recalc_batch_size)
        for source in stale:
            from api.services.source_trust.jobs import enqueue_recalculation
            enqueue_recalculation(db, source.id, reason="staleness_sweep")
        if stale:
            log.info("TrustRecalculationWorker: staleness sweep enqueued %d job(s)", len(stale))

    async def _process_job(self, job_id: str) -> None:
        assert self._semaphore is not None
        async with self._semaphore:
            from api.services.source_trust.source_trust_service import recalculate

            db = SessionLocal()
            try:
                job = crud.get_trust_recalculation_job(db, job_id)
                if not job or job.claim_owner != self.worker_id:
                    return
                crud.update_trust_recalculation_job(db, job_id, status="running")
                try:
                    recalculate(db, job.research_source_id, reason=job.reason, service_name="trust_worker")
                    crud.update_trust_recalculation_job(
                        db, job_id, status="completed", completed_at=datetime.now(timezone.utc),
                    )
                    self.processed_total += 1
                except Exception as exc:
                    attempts = job.attempts + 1
                    status = "failed" if attempts >= settings.trust_recalc_max_attempts else "pending"
                    crud.update_trust_recalculation_job(
                        db, job_id, status=status, attempts=attempts, error=str(exc),
                        claim_owner=None, claim_expires_at=None,
                    )
                    self.failed_total += 1
                    log.warning("TrustRecalculationWorker: job %s failed (attempt %d): %s", job_id, attempts, exc)
            finally:
                db.close()


trust_worker = TrustRecalculationWorker()
