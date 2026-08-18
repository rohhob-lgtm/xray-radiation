"""SharePointConnector — real Microsoft Graph API over OAuth2PkceAuthStrategy."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy
from .._shared.microsoft_oauth import microsoft_oauth_config
from . import client as sharepoint_client

_SCOPES = "Sites.Read.All"

SHAREPOINT_MANIFEST = ConnectorManifest(
    provider="sharepoint", display_name="SharePoint", icon="🏢",
    category=ConnectorCategory.FILE_STORAGE, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("sharepoint.list_sites", "Search accessible SharePoint sites", required_scopes=(_SCOPES,),
                              parameters_schema={"query": {"type": "string", "required": True}}),
        CapabilityDefinition("sharepoint.list_files", "List files in a site's document library", required_scopes=(_SCOPES,),
                              parameters_schema={"site_id": {"type": "string", "required": True}}),
    ),
)


class SharePointConnector(PlatformConnector):
    manifest = SHAREPOINT_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(lambda: microsoft_oauth_config("sharepoint", _SCOPES))

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")

        try:
            if action == "sharepoint.list_sites":
                query = parameters.get("query")
                if not query:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await sharepoint_client.list_sites(access_token, query)
            elif action == "sharepoint.list_files":
                site_id = parameters.get("site_id")
                if not site_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await sharepoint_client.list_files(access_token, site_id)
            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except sharepoint_client.GraphApiError as exc:
            return ConnectorActionResult(success=False, action=action,
                                          error_code=f"GRAPH_API_ERROR_{exc.status_code}", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            await sharepoint_client.get_root_site(access_token)
            return HealthStatus(healthy=True)
        except sharepoint_client.GraphApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


sharepoint_connector = SharePointConnector()
