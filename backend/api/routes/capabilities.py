"""Read-only Capability Registry endpoint.

Exposes the descriptive registry in api.services.platform_capabilities so the
UI and any client can see the platform's true capability surface and each
capability's current enabled/disabled state. This endpoint owns no business
logic and mutates nothing — it only reports.
"""
from fastapi import APIRouter

from api.config import settings
from api.services.platform_capabilities import get_capabilities

router = APIRouter(tags=["capabilities"])


@router.get("/capabilities")
async def list_capabilities():
    """The platform's capabilities resolved against current runtime config.

    ``enabled`` reflects the live kill-switch state (config flag) for flagged
    capabilities; always-on structural capabilities report ``enabled: true``
    with ``enabled_flag: null``.
    """
    caps = get_capabilities(settings)
    return {
        "platform": "X-Ray Academy AI",
        "count": len(caps),
        "enabled_count": sum(1 for c in caps if c["enabled"]),
        "capabilities": caps,
    }
