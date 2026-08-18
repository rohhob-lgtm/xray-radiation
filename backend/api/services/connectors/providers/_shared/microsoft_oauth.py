"""
Shared Microsoft identity platform (v2.0) OAuth2 config — one Entra app
registration covers OneDrive, SharePoint, and Teams via Microsoft Graph.

Endpoints: https://learn.microsoft.com/entra/identity-platform/v2-oauth2-auth-code-flow
Multi-tenant "common" endpoint so any Microsoft/work/school account can connect.

Microsoft's v2.0 endpoint has no public programmatic token-revocation API
(unlike Google/Canva/Dropbox) — revoke_url is None; disconnect still clears
local credentials, the user revokes app access via myapps.microsoft.com if desired.
"""
from __future__ import annotations

from api.config import settings
from ...auth_strategies.oauth2_pkce import OAuth2Config

AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"


def microsoft_oauth_config(provider: str, scopes: str) -> OAuth2Config:
    # offline_access is required for a refresh_token to be issued.
    full_scopes = scopes if "offline_access" in scopes else f"{scopes} offline_access"
    return OAuth2Config(
        authorize_url=AUTHORIZE_URL,
        token_url=TOKEN_URL,
        revoke_url=None,
        scopes=full_scopes,
        redirect_uri=settings.connector_redirect_uri(provider),
        client_id=settings.microsoft_client_id,
        client_secret=settings.microsoft_client_secret,
        code_challenge_method="S256",
    )
