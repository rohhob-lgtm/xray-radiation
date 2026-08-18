"""
OAuth2PkceAuthStrategy — a single, provider-agnostic implementation of the
OAuth 2.0 Authorization Code + PKCE flow.

This is the generalized form of what Phase 1 hardcoded directly into
CanvaConnector. Any OAuth2/PKCE provider (Google Drive, OneDrive, Dropbox,
GitHub, GitLab, Notion, Confluence, Gmail, Google Calendar, Slack, Teams,
SharePoint, and Canva) is wired up by constructing this strategy with a
provider-specific OAuth2Config — never by writing new OAuth code.

State/PKCE-verifier storage: the caller (routes/connectors.py) owns the
request session and is responsible for persisting {state, verifier} between
initiate() and complete() — this strategy is transport-agnostic and never
touches Starlette's Request/session itself, so it works the same whether
the future AI tool router or a REST route drives it.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional
from urllib.parse import urlencode, quote

import httpx
from sqlalchemy.orm import Session

from ..manifest import AuthStrategyType
from ..credential_store import save_credentials
from .base import AuthStrategy, AuthInitiation, CredentialResult, AuthContext


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class OAuth2Config:
    authorize_url: str
    token_url: str
    revoke_url: Optional[str]
    scopes: str  # space-separated
    redirect_uri: str
    client_id: str
    client_secret: str
    code_challenge_method: str = "S256"  # per-provider casing; Canva specifically wants lowercase "s256"
    # Provider-specific authorize-request params beyond the standard OAuth2/PKCE
    # set — e.g. Google's access_type=offline + prompt=consent (to actually get
    # a refresh_token back), Atlassian's audience=api.atlassian.com.
    extra_authorize_params: dict = None  # type: ignore[assignment]
    # "client_basic": POST revoke_url with Basic client_id:client_secret auth
    #   and the token to revoke as a `token` form param (Canva, Google).
    # "bearer_self": POST revoke_url with `Authorization: Bearer {access_token}`
    #   and no body — the endpoint revokes whichever token authenticated the
    #   call (Dropbox). Only the access token is sent in this mode.
    revoke_style: str = "client_basic"
    # Most providers accept form-encoded token requests with client
    # credentials as an HTTP Basic header. Atlassian instead requires a JSON
    # body with client_id/client_secret included in that same JSON payload.
    token_request_format: str = "form"  # "form" | "json"
    client_auth_in_body: bool = False  # True: put client_id/secret in the request body instead of Basic auth

    def __post_init__(self):
        if self.extra_authorize_params is None:
            object.__setattr__(self, "extra_authorize_params", {})


class OAuth2PkceError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


class OAuth2PkceAuthStrategy(AuthStrategy):
    strategy_type = AuthStrategyType.OAUTH2_PKCE

    def __init__(self, config_provider: Callable[[], OAuth2Config]):
        """config_provider is called fresh on every use so it always reflects
        current settings (e.g. Settings loaded from a just-edited .env)."""
        self._config_provider = config_provider

    def is_configured(self) -> bool:
        cfg = self._config_provider()
        return bool(cfg.client_id and cfg.client_secret)

    def _config(self) -> OAuth2Config:
        return self._config_provider()

    def _require_credentials(self, cfg: OAuth2Config) -> None:
        if not cfg.client_id or not cfg.client_secret:
            raise OAuth2PkceError(
                "OAuth client_id/client_secret are not configured for this connector."
            )

    async def initiate(self, db: Session, user_id: str, connector_row) -> AuthInitiation:
        cfg = self._config()
        try:
            self._require_credentials(cfg)
        except OAuth2PkceError as exc:
            return AuthInitiation(success=False, mode="redirect", error_code="NOT_CONFIGURED", error_message=str(exc))

        verifier = secrets.token_urlsafe(64)[:128]
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        state = secrets.token_urlsafe(32)

        params = {
            "client_id": cfg.client_id,
            "response_type": "code",
            "redirect_uri": cfg.redirect_uri,
            "scope": cfg.scopes,
            "code_challenge": challenge,
            "code_challenge_method": cfg.code_challenge_method,
            "state": state,
            **cfg.extra_authorize_params,
        }
        # quote_via=quote (RFC 3986 percent-encoding, space -> %20) rather than
        # urlencode's default quote_plus (space -> '+'). Canva's authorize
        # endpoint rejects a '+'-encoded scope separator with invalid_scope —
        # it does not decode '+' back to a space the way form-urlencoded
        # bodies do, so the space-delimited scope list must use %20.
        authorize_url = f"{cfg.authorize_url}?{urlencode(params, quote_via=quote)}"
        return AuthInitiation(
            success=True, mode="redirect", authorize_url=authorize_url,
            pkce_verifier=verifier, oauth_state=state,
        )

    async def complete(self, db: Session, user_id: str, connector_row, payload: dict) -> CredentialResult:
        """payload = {"code": str, "code_verifier": str}. The caller has already
        validated `state` before invoking this (state never reaches the strategy)."""
        cfg = self._config()
        try:
            self._require_credentials(cfg)
        except OAuth2PkceError as exc:
            return CredentialResult(success=False, error_code="NOT_CONFIGURED", error_message=str(exc))

        code = payload.get("code")
        code_verifier = payload.get("code_verifier")
        if not code or not code_verifier:
            return CredentialResult(success=False, error_code="MISSING_CODE", error_message="Missing authorization code")

        try:
            token = await self._exchange(cfg, code, code_verifier, grant_type="authorization_code")
        except OAuth2PkceError as exc:
            return CredentialResult(success=False, error_code="TOKEN_EXCHANGE_FAILED", error_message=str(exc))

        expiry = _now() + timedelta(seconds=token["expires_in"]) if token.get("expires_in") else None
        credentials = {"access_token": token["access_token"], "refresh_token": token.get("refresh_token")}
        scopes = token.get("scope", "").split() if token.get("scope") else cfg.scopes.split()

        save_credentials(
            db, user_id, connector_row.id, credentials,
            granted_scopes=scopes, token_expiry=expiry,
        )
        return CredentialResult(success=True, granted_scopes=scopes, token_expiry=expiry)

    async def refresh(self, db: Session, user_id: str, connector_row) -> CredentialResult:
        from .. import credential_store
        cfg = self._config()
        try:
            self._require_credentials(cfg)
        except OAuth2PkceError as exc:
            return CredentialResult(success=False, error_code="NOT_CONFIGURED", error_message=str(exc))

        stored = credential_store.load_credentials(db, user_id, connector_row.id)
        refresh_token = (stored or {}).get("refresh_token")
        if not refresh_token:
            return CredentialResult(success=False, error_code="NOT_CONNECTED", error_message="No refresh token on file")

        try:
            token = await self._exchange(cfg, refresh_token, None, grant_type="refresh_token")
        except OAuth2PkceError as exc:
            return CredentialResult(success=False, error_code="REFRESH_FAILED", error_message=str(exc))

        expiry = _now() + timedelta(seconds=token["expires_in"]) if token.get("expires_in") else None
        credentials = {
            "access_token": token["access_token"],
            "refresh_token": token.get("refresh_token") or refresh_token,
        }
        save_credentials(db, user_id, connector_row.id, credentials, token_expiry=expiry)
        return CredentialResult(success=True, token_expiry=expiry)

    async def revoke(self, db: Session, user_id: str, connector_row) -> bool:
        from .. import credential_store
        cfg = self._config()
        if not cfg.revoke_url or not cfg.client_id or not cfg.client_secret:
            return False
        stored = credential_store.load_credentials(db, user_id, connector_row.id)
        if not stored:
            return False

        if cfg.revoke_style == "bearer_self":
            access_token = stored.get("access_token")
            if not access_token:
                return False
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(cfg.revoke_url, headers={"Authorization": f"Bearer {access_token}"})
                return resp.status_code == 200
            except Exception:
                return False

        ok = True
        for token in (stored.get("access_token"), stored.get("refresh_token")):
            if not token:
                continue
            try:
                async with httpx.AsyncClient(timeout=15.0) as client:
                    resp = await client.post(
                        cfg.revoke_url,
                        headers={
                            **self._basic_auth_header(cfg),
                            "Content-Type": "application/x-www-form-urlencoded",
                        },
                        data={"token": token},
                    )
                ok = ok and resp.status_code == 200
            except Exception:
                ok = False
        return ok

    async def build_auth_context(self, db: Session, user_id: str, connector_row) -> Optional[AuthContext]:
        from .. import credential_store
        stored = credential_store.load_credentials(db, user_id, connector_row.id)
        access_token = (stored or {}).get("access_token")
        if not access_token:
            return None
        return AuthContext(headers={"Authorization": f"Bearer {access_token}"})

    # ── Internal HTTP mechanics ──────────────────────────────────────────────

    def _basic_auth_header(self, cfg: OAuth2Config) -> dict[str, str]:
        raw = f"{cfg.client_id}:{cfg.client_secret}".encode("utf-8")
        return {"Authorization": f"Basic {base64.b64encode(raw).decode('ascii')}"}

    async def _exchange(
        self, cfg: OAuth2Config, code_or_refresh: str, code_verifier: Optional[str], grant_type: str
    ) -> dict:
        data = {"grant_type": grant_type}
        if grant_type == "authorization_code":
            data.update({"code": code_or_refresh, "code_verifier": code_verifier, "redirect_uri": cfg.redirect_uri})
        else:
            data["refresh_token"] = code_or_refresh

        headers: dict[str, str] = {}
        if cfg.client_auth_in_body:
            data["client_id"] = cfg.client_id
            data["client_secret"] = cfg.client_secret
        else:
            headers.update(self._basic_auth_header(cfg))

        async with httpx.AsyncClient(timeout=15.0) as client:
            if cfg.token_request_format == "json":
                resp = await client.post(cfg.token_url, headers=headers, json=data)
            else:
                resp = await client.post(
                    cfg.token_url, headers={**headers, "Content-Type": "application/x-www-form-urlencoded"}, data=data,
                )
        if resp.status_code != 200:
            raise OAuth2PkceError(f"Token request failed: {resp.text[:500]}", resp.status_code)
        return resp.json()
