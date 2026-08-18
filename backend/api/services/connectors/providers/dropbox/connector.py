"""DropboxConnector — real Dropbox API v2 over OAuth2PkceAuthStrategy."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from api.config import settings

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy, OAuth2Config
from . import client as dropbox_client

_SCOPES = "files.metadata.read files.content.read"

DROPBOX_MANIFEST = ConnectorManifest(
    provider="dropbox", display_name="Dropbox", icon="📦",
    category=ConnectorCategory.FILE_STORAGE, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("dropbox.list_files", "List files in a folder", required_scopes=(_SCOPES,),
                              parameters_schema={"path": {"type": "string", "required": False}}),
        CapabilityDefinition("dropbox.read_file", "Download a file's content", required_scopes=(_SCOPES,),
                              parameters_schema={"path": {"type": "string", "required": True}}),
    ),
)


def _dropbox_oauth_config() -> OAuth2Config:
    return OAuth2Config(
        authorize_url="https://www.dropbox.com/oauth2/authorize",
        token_url="https://api.dropboxapi.com/oauth2/token",
        revoke_url="https://api.dropboxapi.com/2/auth/token/revoke",
        scopes=_SCOPES,
        redirect_uri=settings.connector_redirect_uri("dropbox"),
        client_id=settings.dropbox_client_id,
        client_secret=settings.dropbox_client_secret,
        code_challenge_method="S256",
        extra_authorize_params={"token_access_type": "offline"},
        revoke_style="bearer_self",
    )


class DropboxConnector(PlatformConnector):
    manifest = DROPBOX_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(_dropbox_oauth_config)

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")

        try:
            if action == "dropbox.list_files":
                data = await dropbox_client.list_folder(access_token, path=parameters.get("path", ""))
            elif action == "dropbox.read_file":
                path = parameters.get("path")
                if not path:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                content = await dropbox_client.download_file(access_token, path)
                data = {"path": path, "size_bytes": len(content)}
            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except dropbox_client.DropboxApiError as exc:
            return ConnectorActionResult(success=False, action=action,
                                          error_code=f"DROPBOX_API_ERROR_{exc.status_code}", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            await dropbox_client.get_current_account(access_token)
            return HealthStatus(healthy=True)
        except dropbox_client.DropboxApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


dropbox_connector = DropboxConnector()
