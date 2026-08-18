"""
SlackConnector — real Slack Web API over OAuth2 (Slack does not require or
document PKCE support since apps are always confidential clients, but
sending the standard code_challenge/code_verifier params through the same
generic strategy is harmless — Slack ignores unrecognized params).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.config import settings

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy, OAuth2Config
from . import client as slack_client

_SCOPES = "channels:read chat:write"

SLACK_MANIFEST = ConnectorManifest(
    provider="slack", display_name="Slack", icon="💬",
    category=ConnectorCategory.COMMUNICATION, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("slack.list_channels", "List channels", required_scopes=("channels:read",)),
        CapabilityDefinition("slack.send_message", "Send a message to a channel", required_scopes=("chat:write",),
                              is_destructive=True,
                              parameters_schema={"channel": {"type": "string", "required": True},
                                                  "text": {"type": "string", "required": True}}),
    ),
)


def _slack_oauth_config() -> OAuth2Config:
    return OAuth2Config(
        authorize_url="https://slack.com/oauth/v2/authorize",
        token_url="https://slack.com/api/oauth.v2.access",
        revoke_url="https://slack.com/api/auth.revoke",
        scopes=_SCOPES,
        redirect_uri=settings.connector_redirect_uri("slack"),
        client_id=settings.slack_client_id,
        client_secret=settings.slack_client_secret,
        code_challenge_method="S256",
        token_request_format="form",
        client_auth_in_body=True,
        revoke_style="bearer_self",
    )


class SlackConnector(PlatformConnector):
    manifest = SLACK_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(_slack_oauth_config)

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")

        try:
            if action == "slack.list_channels":
                data = await slack_client.list_channels(access_token)
            elif action == "slack.send_message":
                channel, text = parameters.get("channel"), parameters.get("text")
                if not channel or not text:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await slack_client.send_message(access_token, channel, text)
            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except slack_client.SlackApiError as exc:
            return ConnectorActionResult(success=False, action=action, error_code="SLACK_API_ERROR", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            await slack_client.auth_test(access_token)
            return HealthStatus(healthy=True)
        except slack_client.SlackApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


slack_connector = SlackConnector()
