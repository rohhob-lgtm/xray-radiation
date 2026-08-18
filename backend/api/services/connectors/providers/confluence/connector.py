"""ConfluenceConnector — real Confluence Cloud REST API over Atlassian 3LO OAuth2+PKCE."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from api.config import settings

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy, OAuth2Config
from ... import credential_store
from . import client as confluence_client

log = logging.getLogger(__name__)

_SCOPES = "read:confluence-content.all read:confluence-space.summary offline_access"

CONFLUENCE_MANIFEST = ConnectorManifest(
    provider="confluence", display_name="Confluence", icon="📘",
    category=ConnectorCategory.KNOWLEDGE_BASE, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("confluence.list_spaces", "List spaces", required_scopes=(_SCOPES,)),
        CapabilityDefinition("confluence.read_page", "Read a page's content", required_scopes=(_SCOPES,),
                              parameters_schema={"page_id": {"type": "string", "required": True}}),
        CapabilityDefinition("confluence.search", "Search across spaces (CQL)", required_scopes=(_SCOPES,),
                              parameters_schema={"cql": {"type": "string", "required": True}}),
    ),
)


def _confluence_oauth_config() -> OAuth2Config:
    return OAuth2Config(
        authorize_url="https://auth.atlassian.com/authorize",
        token_url="https://auth.atlassian.com/oauth/token",
        revoke_url=None,  # Atlassian offers no public token-revocation endpoint
        scopes=_SCOPES,
        redirect_uri=settings.connector_redirect_uri("confluence"),
        client_id=settings.atlassian_client_id,
        client_secret=settings.atlassian_client_secret,
        code_challenge_method="S256",
        extra_authorize_params={"audience": "api.atlassian.com", "prompt": "consent"},
        token_request_format="json",
        client_auth_in_body=True,
    )


class ConfluenceConnector(PlatformConnector):
    manifest = CONFLUENCE_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(_confluence_oauth_config)

    async def on_connected(self, db: Session, user_id: str) -> None:
        """Resolve and cache the Confluence Cloud id — every API call needs it."""
        connector_row = self._connector_row(db)
        stored = credential_store.load_credentials(db, user_id, connector_row.id)
        access_token = (stored or {}).get("access_token")
        if not access_token:
            return
        try:
            # accessible-resources only ever returns sites the token's granted
            # (Confluence-only) scopes cover, so the first result is a valid site.
            resources = await confluence_client.get_accessible_resources(access_token)
            if resources:
                merged = {**stored, "cloud_id": resources[0]["id"]}
                credential_store.save_credentials(db, user_id, connector_row.id, merged)
        except confluence_client.ConfluenceApiError as exc:
            log.warning("Confluence accessible-resources lookup failed for user=%s: %s", user_id, exc)

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        connector_row = self._connector_row(db)
        stored = credential_store.load_credentials(db, user_id, connector_row.id)
        access_token = (stored or {}).get("access_token")
        cloud_id = (stored or {}).get("cloud_id")
        if not access_token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")
        if not cloud_id:
            return ConnectorActionResult(success=False, action=action, error_code="NO_ACCESSIBLE_SITE",
                                          error_message="No accessible Confluence site was found for this account")

        try:
            if action == "confluence.list_spaces":
                data = await confluence_client.list_spaces(access_token, cloud_id)
            elif action == "confluence.read_page":
                page_id = parameters.get("page_id")
                if not page_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await confluence_client.get_page(access_token, cloud_id, page_id)
            elif action == "confluence.search":
                cql = parameters.get("cql")
                if not cql:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await confluence_client.search(access_token, cloud_id, cql)
            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except confluence_client.ConfluenceApiError as exc:
            return ConnectorActionResult(success=False, action=action,
                                          error_code=f"CONFLUENCE_API_ERROR_{exc.status_code}", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        connector_row = self._connector_row(db)
        stored = credential_store.load_credentials(db, user_id, connector_row.id)
        access_token = (stored or {}).get("access_token")
        if not access_token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            resources = await confluence_client.get_accessible_resources(access_token)
            return HealthStatus(healthy=bool(resources))
        except confluence_client.ConfluenceApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


confluence_connector = ConfluenceConnector()
