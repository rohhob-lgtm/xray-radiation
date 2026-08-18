"""GoogleCalendarConnector — real Google Calendar API v3 over OAuth2PkceAuthStrategy."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy
from .._shared.google_oauth import google_oauth_config
from . import client as calendar_client

_READ_SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
_EVENTS_SCOPE = "https://www.googleapis.com/auth/calendar.events"
_SCOPES = f"{_READ_SCOPE} {_EVENTS_SCOPE}"

GOOGLE_CALENDAR_MANIFEST = ConnectorManifest(
    provider="google_calendar", display_name="Google Calendar", icon="📅",
    category=ConnectorCategory.CALENDAR, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("google_calendar.list_events", "List upcoming events", required_scopes=(_READ_SCOPE,)),
        CapabilityDefinition("google_calendar.create_event", "Create an event", required_scopes=(_EVENTS_SCOPE,),
                              is_destructive=True,
                              parameters_schema={"summary": {"type": "string", "required": True},
                                                  "start_iso": {"type": "string", "required": True},
                                                  "end_iso": {"type": "string", "required": True}}),
    ),
)


class GoogleCalendarConnector(PlatformConnector):
    manifest = GOOGLE_CALENDAR_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(lambda: google_oauth_config("google_calendar", _SCOPES))

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")

        try:
            if action == "google_calendar.list_events":
                data = await calendar_client.list_events(access_token, max_results=parameters.get("max_results", 25))
            elif action == "google_calendar.create_event":
                summary, start_iso, end_iso = parameters.get("summary"), parameters.get("start_iso"), parameters.get("end_iso")
                if not summary or not start_iso or not end_iso:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="summary, start_iso, and end_iso are required")
                data = await calendar_client.create_event(access_token, summary, start_iso, end_iso)
            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except calendar_client.GoogleCalendarApiError as exc:
            return ConnectorActionResult(success=False, action=action,
                                          error_code=f"CALENDAR_API_ERROR_{exc.status_code}", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            await calendar_client.get_calendar(access_token)
            return HealthStatus(healthy=True)
        except calendar_client.GoogleCalendarApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


google_calendar_connector = GoogleCalendarConnector()
