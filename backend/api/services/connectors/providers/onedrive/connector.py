"""OneDriveConnector — real Microsoft Graph API over OAuth2PkceAuthStrategy."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy
from .._shared.microsoft_oauth import microsoft_oauth_config
from . import client as onedrive_client

_SCOPES = "Files.Read"

ONEDRIVE_MANIFEST = ConnectorManifest(
    provider="onedrive", display_name="OneDrive", icon="☁️",
    category=ConnectorCategory.FILE_STORAGE, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("onedrive.list_files", "List files in the user's OneDrive", required_scopes=(_SCOPES,),
                              parameters_schema={"folder_path": {"type": "string", "required": False}}),
        CapabilityDefinition("onedrive.read_file", "Download a file's raw content", required_scopes=(_SCOPES,),
                              parameters_schema={"item_id": {"type": "string", "required": True}}),
    ),
)


class OneDriveConnector(PlatformConnector):
    manifest = ONEDRIVE_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(lambda: microsoft_oauth_config("onedrive", _SCOPES))

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")

        try:
            if action == "onedrive.list_files":
                data = await onedrive_client.list_files(access_token, folder_path=parameters.get("folder_path"))
            elif action == "onedrive.read_file":
                item_id = parameters.get("item_id")
                if not item_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                content = await onedrive_client.download_file(access_token, item_id)
                data = {"item_id": item_id, "size_bytes": len(content)}
            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except onedrive_client.GraphApiError as exc:
            return ConnectorActionResult(success=False, action=action,
                                          error_code=f"GRAPH_API_ERROR_{exc.status_code}", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            await onedrive_client.get_drive(access_token)
            return HealthStatus(healthy=True)
        except onedrive_client.GraphApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


onedrive_connector = OneDriveConnector()
