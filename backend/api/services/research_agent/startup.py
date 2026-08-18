"""Startup orchestration for the research-agent scheduler — Phase 2B.2.1.

bootstrap() runs the ordered pre-flight sequence the product spec requires
BEFORE any network research is allowed to fire: DB health check, stale-lease
cleanup, and a summary of what's sitting in the mission table. It does NOT
start the worker pool or claim any missions itself — main.py calls this
first, then calls mission_scheduler.start() (job_runner.py) separately,
which owns the actual bounded claim/worker-pool lifecycle
(mission_queue.MissionQueueManager). Splitting these two steps is what lets
main.py's on_startup_async() finish and the app become HTTP-ready before any
mission resume work begins.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import text

from api.db.base import SessionLocal, engine
from api.db import crud

log = logging.getLogger(__name__)

# Readiness vocabulary — the bootstrap()-owned phases. The finer
# resume_queue_loading -> ready progression is owned by
# api.services.research_agent.job_runner.mission_scheduler.queue_manager
# (MissionQueueManager.state) and composed with this at the route/health
# layer — see api.routes.research_agent's scheduler/status endpoint and
# api.routes.health.
STATE_INITIALIZING = "initializing"
STATE_DATABASE_READY = "database_ready"
STATE_WORKERS_READY = "workers_ready"
STATE_FAILED = "failed"
STATE_DEGRADED = "degraded"


class SchedulerReadiness:
    def __init__(self) -> None:
        self.state = STATE_INITIALIZING
        self.started_at: datetime | None = None
        self.finished_at: datetime | None = None
        self.duration_s: float | None = None
        self.last_error: str | None = None
        self.resume_candidates = 0
        self.lease_recoveries = 0
        self.status_counts: dict[str, int] = {}

    def to_dict(self) -> dict:
        return {
            "state": self.state,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "duration_s": self.duration_s,
            "last_error": self.last_error,
            "resume_candidates": self.resume_candidates,
            "lease_recoveries": self.lease_recoveries,
            "status_counts": self.status_counts,
        }


readiness = SchedulerReadiness()


async def bootstrap() -> None:
    """1. DB health check  2. migration/table sanity check  3. cleanup of
    stale execution locks (expired leases)  4. detect + summarize
    interrupted/pending missions. Never fires network research — that only
    starts once mission_scheduler.start() is called separately by main.py,
    itself delayed by research_scheduler_startup_delay_s inside its own
    background task (see mission_queue.MissionQueueManager._load_loop)."""
    readiness.started_at = datetime.now(timezone.utc)
    t0 = time.monotonic()
    db = SessionLocal()
    try:
        # 1. Database health check.
        db.execute(text("SELECT 1"))
        readiness.state = STATE_DATABASE_READY

        # 2. Migrations already ran in main.py's earlier on_startup() handler
        # (create_all_tables() + _apply_migrations(), registration order
        # guarantees it runs first) — this query verifies the new columns
        # this phase depends on are actually present/queryable, not just
        # assumed applied.
        crud.count_research_missions_by_status(db)

        # 3. Cleanup of stale execution locks — missions whose lease expired
        # while no process was alive to renew it (crash, kill -9, deploy).
        recovered = crud.release_expired_leases(db)
        readiness.lease_recoveries = recovered
        if recovered:
            log.info("Startup lease recovery: %d mission(s) requeued (expired lease)", recovered)

        # 4. Detect + classify what's sitting in the mission table — pure
        # observability at this stage (no claiming happens here yet).
        counts = crud.count_research_missions_by_status(db)
        readiness.status_counts = counts
        candidates = counts.get("queued", 0) + counts.get("retry_waiting", 0)
        readiness.resume_candidates = candidates
        log.info("Startup resume candidates: %d (status breakdown: %s)", candidates, counts)

        readiness.state = STATE_WORKERS_READY
    except Exception as exc:
        readiness.state = STATE_FAILED
        readiness.last_error = str(exc)
        log.error("Scheduler bootstrap failed: %s", exc)
        raise
    finally:
        db.close()
        readiness.finished_at = datetime.now(timezone.utc)
        readiness.duration_s = round(time.monotonic() - t0, 4)
        log.info("Scheduler bootstrap finished: state=%s duration_s=%.3f", readiness.state, readiness.duration_s)


def db_pool_metrics() -> dict:
    """Read-only snapshot of the SQLAlchemy pool — checked-out connections,
    size, overflow — exposed on the scheduler-status endpoint per the
    product spec's Database Connection Safety observability requirement."""
    pool = engine.pool
    try:
        return {
            "checked_out": pool.checkedout(),
            "size": pool.size(),
            "overflow": pool.overflow(),
        }
    except Exception:
        # NullPool / some SQLite pool classes don't implement all of these.
        return {"checked_out": None, "size": None, "overflow": None}
