"""
Shared Google OAuth2 config — one Google Cloud OAuth client covers Drive,
Gmail, and Calendar (each just requests different scopes and has its own
registered redirect URI under the same client).

Endpoints are Google's standard, stable OAuth2 endpoints:
https://developers.google.com/identity/protocols/oauth2/web-server
"""
from __future__ import annotations

from api.config import settings
from ...auth_strategies.oauth2_pkce import OAuth2Config

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"


def google_oauth_config(provider: str, scopes: str) -> OAuth2Config:
    # GOOGLE_REDIRECT_URI only overrides google_drive today (the one Google
    # connector actually enabled) — once gmail/google_calendar are enabled
    # too, each needs its own distinct registered callback path, so a single
    # shared override would incorrectly apply to all three at once.
    redirect_override = settings.google_redirect_uri if provider == "google_drive" else ""
    return OAuth2Config(
        authorize_url=AUTHORIZE_URL,
        token_url=TOKEN_URL,
        revoke_url=REVOKE_URL,
        scopes=scopes,
        redirect_uri=redirect_override or settings.connector_redirect_uri(provider),
        client_id=settings.google_client_id,
        client_secret=settings.google_client_secret,
        code_challenge_method="S256",
        # access_type=offline + prompt=consent are required for Google to
        # actually return a refresh_token (otherwise only an access_token
        # comes back, and silently on repeat authorizations no refresh_token
        # is issued at all).
        extra_authorize_params={"access_type": "offline", "prompt": "consent"},
    )
