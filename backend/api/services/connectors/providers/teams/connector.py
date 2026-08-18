"""TeamsConnector — real Microsoft Graph API over OAuth2PkceAuthStrategy."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy
from .._shared.microsoft_oauth import microsoft_oauth_config
from . import client as teams_client

_READ_SCOPE = "Team.ReadBasic.All Channel.ReadBasic.All"
_SEND_SCOPE = "ChannelMessage.Send"
_SCOPES = f"{_READ_SCOPE} {_SEND_SCOPE}"

TEAMS_MANIFEST = ConnectorManifest(
    provider="teams", display_name="Microsoft Teams", icon="🟪",
    category=ConnectorCategory.COMMUNICATION, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("teams.list_channels", "List channels in a joined team",
                              required_scopes=("Channel.ReadBasic.All",),
                              parameters_schema={"team_id": {"type": "string", "required": True}}),
        CapabilityDefinition("teams.send_message", "Send a channel message", required_scopes=(_SEND_SCOPE,),
                              is_destructive=True,
                              parameters_schema={"team_id": {"type": "string", "required": True},
                                                  "channel_id": {"type": "string", "required": True},
                                                  "content": {"type": "string", "required": True}}),
    ),
)


class TeamsConnector(PlatformConnector):
    manifest = TEAMS_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(lambda: microsoft_oauth_config("teams", _SCOPES))

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")

        try:
            if action == "teams.list_channels":
                team_id = parameters.get("team_id")
                if not team_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await teams_client.list_channels(access_token, team_id)
            elif action == "teams.send_message":
                team_id, channel_id, content = parameters.get("team_id"), parameters.get("channel_id"), parameters.get("content")
                if not team_id or not channel_id or not content:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await teams_client.send_channel_message(access_token, team_id, channel_id, content)
            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except teams_client.GraphApiError as exc:
            return ConnectorActionResult(success=False, action=action,
                                          error_code=f"GRAPH_API_ERROR_{exc.status_code}", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            await teams_client.list_joined_teams(access_token)
            return HealthStatus(healthy=True)
        except teams_client.GraphApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


teams_connector = TeamsConnector()
