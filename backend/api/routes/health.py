"""Health check endpoint."""
from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def health_check():
    """"status": "ok" alone means only "process alive" — the additional
    fields (Phase 2B.2.1) let a caller distinguish process-alive from
    application-ready/scheduler-ready/providers-degraded, per the product
    spec. Import failures here must never take the health endpoint down —
    if the research-agent scheduler itself is broken, that IS what
    scheduler_ready=False is supposed to report, not a 500."""
    scheduler_ready = False
    providers_degraded = False
    try:
        from api.services.research_agent.startup import readiness as _readiness, STATE_WORKERS_READY
        from api.services.research_agent.job_runner import mission_scheduler as _mission_scheduler
        from api.services.research_agent.provider_throttle import get_provider_status

        scheduler_ready = (
            _readiness.state == STATE_WORKERS_READY
            and _mission_scheduler.queue_manager.state == "ready"
        )
        providers_degraded = any(
            p["state"] != "closed" for p in get_provider_status().values()
        )
    except Exception:
        pass

    return {
        "status": "ok",
        "application_ready": True,
        "scheduler_ready": scheduler_ready,
        "providers_degraded": providers_degraded,
    }
