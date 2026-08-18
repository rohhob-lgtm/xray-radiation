"""GmailConnector — real Gmail API v1 over OAuth2PkceAuthStrategy."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy
from .._shared.google_oauth import google_oauth_config
from . import client as gmail_client

_READ_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
_SEND_SCOPE = "https://www.googleapis.com/auth/gmail.send"
_SCOPES = f"{_READ_SCOPE} {_SEND_SCOPE}"

GMAIL_MANIFEST = ConnectorManifest(
    provider="gmail", display_name="Gmail", icon="📧",
    category=ConnectorCategory.COMMUNICATION, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("gmail.list_messages", "List messages", required_scopes=(_READ_SCOPE,)),
        CapabilityDefinition("gmail.read_message", "Read a message", required_scopes=(_READ_SCOPE,),
                              parameters_schema={"message_id": {"type": "string", "required": True}}),
        CapabilityDefinition("gmail.send_message", "Send a message", required_scopes=(_SEND_SCOPE,),
                              is_destructive=True,
                              parameters_schema={"to": {"type": "string", "required": True},
                                                  "subject": {"type": "string", "required": True},
                                                  "body": {"type": "string", "required": True}}),
    ),
)


class GmailConnector(PlatformConnector):
    manifest = GMAIL_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(lambda: google_oauth_config("gmail", _SCOPES))

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")

        try:
            if action == "gmail.list_messages":
                data = await gmail_client.list_messages(access_token, query=parameters.get("query"))
            elif action == "gmail.read_message":
                message_id = parameters.get("message_id")
                if not message_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await gmail_client.get_message(access_token, message_id)
            elif action == "gmail.send_message":
                to, subject, body = parameters.get("to"), parameters.get("subject"), parameters.get("body")
                if not to or not subject or body is None:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="to, subject, and body are required")
                data = await gmail_client.send_message(access_token, to, subject, body)
            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except gmail_client.GmailApiError as exc:
            return ConnectorActionResult(success=False, action=action,
                                          error_code=f"GMAIL_API_ERROR_{exc.status_code}", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            await gmail_client.get_profile(access_token)
            return HealthStatus(healthy=True)
        except gmail_client.GmailApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


gmail_connector = GmailConnector()
