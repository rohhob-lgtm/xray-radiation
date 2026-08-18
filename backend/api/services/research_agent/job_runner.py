"""Mission run/pause/resume/stop state machine + continuous-learning scheduler.

Modeled directly on api.services.job_runner's ProcessingJob pattern
(checkpoint after each unit of work, `_RUNNING_JOBS`-style in-memory set to
prevent duplicate runners, `resume_queued_jobs()`-style startup recovery) and
on api.services.connectors.sync_engine.SyncScheduler's in-process asyncio
polling loop for continuous_learning scheduling — no new infra (no Celery/
APScheduler), consistent with every other background job in this codebase.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from api.config import settings
from api.db.base import SessionLocal
from api.db import crud
from api.db.models import ResearchMission
from api.services.research_agent.discovery import discover_sources
from api.services.research_agent.crawler_orchestrator import process_next_queue_item, _limits_exceeded
from api.services.research_agent.mission_queue import MissionQueueManager
from api.services.research_agent.query_generator import generate_mission_queries
from api.services.research_brain.planner import build_research_plan
from api.services.research_brain.gap_detector import compute_coverage, aggregate_coverage, list_low_coverage_topics
from api.services.research_brain.curiosity_engine import generate_questions

log = logging.getLogger(__name__)

# In-memory set of running mission IDs — prevents duplicate runners, exactly
# like job_runner.py's _RUNNING_JOBS.
_RUNNING_MISSIONS: set[str] = set()

_SCHEDULE_INTERVALS = {"6h": timedelta(hours=6), "daily": timedelta(days=1), "weekly": timedelta(days=7)}

_DOMAIN_LABEL = "X-ray, radiation, and security-screening research"


def _schedule_next_run(mission: ResearchMission) -> None:
    frequency = (mission.schedule or {}).get("frequency", "manual")
    delta = _SCHEDULE_INTERVALS.get(frequency)
    if not delta:
        return
    next_run = datetime.now(timezone.utc) + delta
    mission.schedule = {**(mission.schedule or {}), "next_run_at": next_run.isoformat()}


async def run_mission(mission_id: str) -> None:
    """Run (or resume) one mission to completion, a limit, a pause, or a stop.

    Safe to call multiple times — duplicate calls for the same mission_id
    are no-ops while one is already running.
    """
    if mission_id in _RUNNING_MISSIONS:
        log.info("Mission %s already running — skipping duplicate", mission_id)
        return

    _RUNNING_MISSIONS.add(mission_id)
    db = SessionLocal()
    try:
        mission = crud.get_research_mission(db, mission_id)
        if not mission or mission.status not in ("queued", "running"):
            return

        mission.status = "running"
        checkpoint = mission.checkpoint or {}
        mission.current_phase = "planning" if not checkpoint.get("plan_built") else "crawling"
        db.commit()
        crud.add_research_activity(db, mission.id, "info", f"Mission started: {mission.mission_text[:200]}")

        # ── AI Research Brain: think before searching ────────────────────────
        # Builds a ranked topic tree (api.services.research_brain.planner) before
        # any discovery/crawl happens, then discovers sources per topic instead
        # of once for the whole mission — discovery/crawl/ingestion themselves
        # (discover_sources/process_next_queue_item) are unchanged from Phase 1.
        if not checkpoint.get("plan_built"):
            plan = build_research_plan(db, mission.id, mission.mission_text, mission.mode)
            plan_meta = plan.normalized_understanding or {}
            mission.normalized_topic = plan_meta.get("normalized_topic", mission.normalized_topic)
            # Phase 2B.5 — generalized manufacturer detection (planner.py's
            # _detect_manufacturer() now recognizes novel names, not just the
            # hardcoded KNOWN_MANUFACTURERS list); threaded into graph
            # extraction's manufacturer hint and the trust cap below.
            mission.detected_manufacturer = plan_meta.get("matched_manufacturer")
            mission.checkpoint = {**checkpoint, "plan_built": True}
            db.commit()

            topics = crud.list_research_topics(db, mission.id)
            crud.add_research_activity(
                db, mission.id, "info",
                f"Research plan built: {len(topics)} topic(s) ({plan_meta.get('template', 'generic')} template)"
                + (f", matched manufacturer: {plan_meta['matched_manufacturer']}" if plan_meta.get("matched_manufacturer") else ""),
            )

            mission.current_phase = "discovering"
            db.commit()

            total_discovered = 0
            for topic in topics:
                queries = (topic.search_strategy or {}).get("queries") or [topic.label]
                discovered = await discover_sources(queries, _DOMAIN_LABEL, mission.content_types)
                for item in discovered:
                    item["topic_id"] = topic.id
                crud.enqueue_research_urls(db, mission.id, discovered)
                crud.update_research_topic(db, topic.id, status="researching")
                total_discovered += len(discovered)

            mission.pages_discovered = total_discovered
            mission.checkpoint = {**mission.checkpoint, "discovery_done": True}
            db.commit()
            crud.add_research_activity(
                db, mission.id, "info",
                f"Discovered {total_discovered} candidate source(s) across {len(topics)} topic(s)",
            )

        mission.current_phase = "crawling"
        db.commit()

        # Phase 2B.5 — mission-level coverage-target auto-continue loop.
        # The crawl-to-empty-queue loop below is UNCHANGED; it's now wrapped
        # in a bounded outer loop that, after each pass, checks aggregate
        # coverage against mission.coverage_target and — if still short and
        # rounds/limits remain — generates refined queries for the
        # still-low-coverage topics and re-runs discover+crawl for another
        # round, all within this SAME mission (no child missions spawned
        # here — that's the separate, human-gated curiosity-question flow
        # below, which still runs exactly once, after this loop exits).
        while True:
            while True:
                db.refresh(mission)
                if mission.status != "running":
                    break
                has_more = await process_next_queue_item(db, mission)
                if not has_more:
                    break
                await asyncio.sleep(1.0)  # politeness delay between fetches

            db.refresh(mission)
            if mission.status != "running":
                break  # paused/stopped mid-run — exit the outer loop too

            coverage_results = compute_coverage(db, mission.id)
            avg_coverage = aggregate_coverage(coverage_results)
            mission.coverage_rounds_completed += 1
            db.commit()

            below_target = avg_coverage < mission.coverage_target
            rounds_left = mission.coverage_rounds_completed < mission.max_coverage_rounds
            limits_exhausted = _limits_exceeded(mission) is not None

            if not (below_target and rounds_left) or limits_exhausted:
                break

            low_topics = list_low_coverage_topics(db, mission.id, threshold=mission.coverage_target)
            crud.add_research_activity(
                db, mission.id, "info",
                f"Coverage round {mission.coverage_rounds_completed}: {avg_coverage}% < target "
                f"{mission.coverage_target}% — refining queries for {len(low_topics)} topic(s)",
            )
            mission.current_phase = "discovering"
            db.commit()

            newly_discovered = 0
            for low in low_topics:
                topic = crud.get_research_topic(db, low["topic_id"])
                if not topic:
                    continue
                _, refined_queries = generate_mission_queries(
                    f"{mission.normalized_topic} {topic.label} round {mission.coverage_rounds_completed}",
                    mission.mode,
                )
                discovered = await discover_sources(refined_queries, _DOMAIN_LABEL, mission.content_types)
                for item in discovered:
                    item["topic_id"] = topic.id
                crud.enqueue_research_urls(db, mission.id, discovered)
                newly_discovered += len(discovered)
            mission.pages_discovered += newly_discovered
            db.commit()
            crud.add_research_activity(
                db, mission.id, "info",
                f"Coverage round {mission.coverage_rounds_completed}: discovered {newly_discovered} more source(s)",
            )
            mission.current_phase = "crawling"
            db.commit()

        if mission.status == "running":
            # Curiosity Engine: self-generated follow-up questions from the
            # gaps just computed plus unexplained terms in what was ingested
            # — runs exactly once, after coverage-seeking above is fully
            # exhausted, kept fully separate from the loop above.
            generate_questions(db, mission.id)

            # Proactive AI Scientist (Phase 2B.8): classify what THIS mission
            # produced into documented, deduplicated alerts — best-effort,
            # wrapped so a bug here can never fail mission completion itself,
            # same discipline crawler_orchestrator.py already uses around
            # graph extraction.
            try:
                from api.services.research_brain.ai_scientist import classify_and_alert
                classify_and_alert(db, mission.id)
            except Exception:
                log.exception("AI Scientist classify_and_alert failed for mission %s", mission.id)

            mission.status = "completed"
            mission.current_phase = "completed"
            mission.last_run_at = datetime.now(timezone.utc)
            if mission.mode == "continuous_learning":
                _schedule_next_run(mission)
            db.commit()
            crud.add_research_activity(db, mission.id, "info", "Mission completed")
    except Exception as exc:
        log.exception("Mission %s failed", mission_id)
        try:
            crud.update_research_mission(db, mission_id, status="failed", last_error=str(exc))
            crud.add_research_activity(db, mission_id, "error", f"Mission failed: {exc}")
        except Exception:
            pass
    finally:
        _RUNNING_MISSIONS.discard(mission_id)
        db.close()


def start_mission(mission_id: str) -> None:
    asyncio.create_task(run_mission(mission_id))


async def pause_mission(mission_id: str) -> ResearchMission | None:
    db = SessionLocal()
    try:
        mission = crud.get_research_mission(db, mission_id)
        if not mission:
            return None
        crud.add_research_activity(db, mission_id, "info", "Mission paused by user")
        # update_research_mission's own commit+refresh must be the LAST write on
        # this session — SQLAlchemy expires an object's attributes on every
        # commit() on its session (expire_on_commit=True), so a commit issued
        # after the final refresh (e.g. from add_research_activity) would leave
        # `mission` expired right as the session closes below, and the caller's
        # later attribute access would raise DetachedInstanceError.
        return crud.update_research_mission(db, mission_id, status="paused", current_phase="paused")
    finally:
        db.close()


async def resume_mission(mission_id: str) -> ResearchMission | None:
    db = SessionLocal()
    try:
        existing = crud.get_research_mission(db, mission_id)
        if not existing:
            return None
        crud.add_research_activity(db, mission_id, "info", "Mission resumed by user")
        mission = crud.update_research_mission(db, mission_id, status="queued", current_phase="queued")
    finally:
        db.close()
    if mission:
        start_mission(mission_id)
    return mission


async def stop_mission(mission_id: str) -> ResearchMission | None:
    db = SessionLocal()
    try:
        mission = crud.get_research_mission(db, mission_id)
        if not mission:
            return None
        crud.add_research_activity(db, mission_id, "info", "Mission stopped by user")
        return crud.update_research_mission(db, mission_id, status="stopped", current_phase="stopped")
    finally:
        db.close()


async def resume_missions() -> int:
    """One-shot, BOUNDED claim-and-launch batch (at most
    settings.research_resume_batch_size missions) — a manual/utility entry
    point, not the startup path. main.py's startup no longer calls this:
    mission_scheduler.start() (below) owns startup recovery now, via its
    MissionQueueManager's continuously-running claim loop, which is what
    replaces the old unbounded "resume every queued/running mission at
    once" behavior that caused the 775-mission request storm. Kept for
    direct/manual/test use — e.g. a future "resume selected now" admin
    action — using the exact same atomic crud.claim_next_mission() every
    other claim path uses, so it can never bypass the bounded/atomic
    guarantees those provide.
    """
    db = SessionLocal()
    claimed = 0
    try:
        worker_id = "manual-resume_missions"
        for _ in range(settings.research_resume_batch_size):
            mission = crud.claim_next_mission(db, worker_id=worker_id, lease_seconds=settings.research_claim_lease_seconds)
            if not mission:
                break
            crud.update_research_mission(db, mission.id, status="running", claim_owner=worker_id)
            asyncio.create_task(run_mission(mission.id))
            claimed += 1
        if claimed:
            log.info("resume_missions(): claimed and launched %d mission(s)", claimed)
    except Exception as exc:
        log.warning("resume_missions() failed: %s", exc)
    finally:
        db.close()
    return claimed


class MissionScheduler:
    """Polls for due continuous_learning missions, AND (Phase 2B.2.1) owns
    the bounded resume queue/worker pool via MissionQueueManager.

    This is the single scheduler for research missions — extended in place,
    not replaced by a second parallel one. Same in-process asyncio pattern
    as connectors/sync_engine.py's SyncScheduler — no new infra. Research
    cycles are much longer than connector syncs, so the poll interval is
    coarser (5 min vs. 60s).
    """

    _POLL_INTERVAL_SECONDS = 300

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self.queue_manager = MissionQueueManager()

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        # Bounded claim/worker-pool loop — this IS the startup-recovery path
        # now (replaces the old unbounded resume_missions() call in
        # main.py). Scheduled via create_task so MissionScheduler.start()
        # itself stays synchronous and non-blocking, matching every sibling
        # scheduler's .start() call convention in main.py.
        asyncio.create_task(self.queue_manager.start(run_mission))
        log.info("MissionScheduler started (poll every %ds)", self._POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        await self.queue_manager.stop()
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
        log.info("MissionScheduler stopped")

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("MissionScheduler tick failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=self._POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> int:
        """Run one sweep of due continuous-learning missions. Public so tests
        can call it directly without waiting on the poll interval.

        Phase 2B.2.1: this no longer launches run_mission() itself — it only
        flips due missions back to "queued". The bounded queue_manager (a
        continuously-running background loop, started once in start() above)
        picks them up on its next claim batch, same as any other queued
        mission — routing continuous_learning resumes through the SAME
        bounded path instead of a second unbounded create_task() fan-out."""
        db = SessionLocal()
        processed = 0
        try:
            now_iso = datetime.now(timezone.utc).isoformat()
            for mission in crud.list_due_scheduled_missions(db, now_iso):
                # Reset for a fresh cycle — a new discovery round may surface
                # new content; already-processed URLs are skipped automatically
                # since enqueue_research_urls() only inserts genuinely new ones.
                mission.status = "queued"
                mission.current_phase = "queued"
                mission.checkpoint = {}
                mission.queued_at = datetime.now(timezone.utc)
                db.commit()
                processed += 1

            # Knowledge Refresh (Phase 2B.4) — same sweep, same scheduler, one
            # more bounded query: topics due for a freshness refresh each spawn
            # an ordinary child ResearchMission (research_memory.refresh_topic),
            # which flows through the SAME queue_manager claim path above —
            # no new scheduler or worker class for this job type.
            from api.services.research_brain.research_memory import sweep_due_refreshes
            processed += sweep_due_refreshes(db)

            # Proactive AI Scientist (Phase 2B.8) — same sweep, same
            # scheduler, same bounded-batch discipline as the freshness
            # sweep above. Each call is independently wrapped so a bug in
            # either can never break this tick or the freshness sweep.
            try:
                from api.services.research_brain.ai_scientist import (
                    maybe_generate_weekly_brief, sweep_for_new_missions,
                )
                processed += sweep_for_new_missions(db)
                maybe_generate_weekly_brief(db)
            except Exception:
                log.exception("AI Scientist sweep failed")

            # Knowledge Health (Phase 2B.9) — same sweep, same scheduler,
            # same bounded-batch discipline. Read-only aggregation over
            # existing signals into its own KnowledgeHealthSnapshot cache;
            # wrapped independently so a bug here can never break this tick
            # or either sweep above.
            try:
                from api.services.research_brain.knowledge_health import run_health_audit
                run_health_audit(db)
            except Exception:
                log.exception("Knowledge Health audit failed")
        finally:
            db.close()
        return processed


mission_scheduler = MissionScheduler()
