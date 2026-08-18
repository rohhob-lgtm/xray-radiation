"""
AuthStrategy — the pluggable authentication mechanism a connector composes.

This is what lets CanvaConnector, a future GitHubConnector, and a
LocalFolderConnector all implement the exact same PlatformConnector
lifecycle (connect/disconnect/status/refresh) without OAuth mechanics
leaking into connectors that don't use OAuth, and without local-filesystem
config leaking into connectors that do.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from ..manifest import AuthStrategyType


@dataclass
class AuthInitiation:
    """What the route layer hands back to the frontend to start a connection.

    mode="redirect": the frontend does a full navigation to authorize_url (OAuth).
    mode="form": the frontend renders credential_fields and POSTs the values
    to /connectors/{provider}/credentials (API key, SSH key, folder path, ...).
    """
    success: bool
    mode: str = "redirect"  # "redirect" | "form"
    authorize_url: Optional[str] = None
    pkce_verifier: Optional[str] = None
    oauth_state: Optional[str] = None
    credential_fields: list[dict] = field(default_factory=list)
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class CredentialResult:
    success: bool
    external_account_label: Optional[str] = None
    granted_scopes: list[str] = field(default_factory=list)
    token_expiry: Optional[datetime] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


@dataclass
class AuthContext:
    """Ready-to-use auth material for a connector's HTTP client (or filesystem root)."""
    headers: dict[str, str] = field(default_factory=dict)
    params: dict[str, str] = field(default_factory=dict)
    extra: dict[str, Any] = field(default_factory=dict)


class AuthStrategy(ABC):
    strategy_type: AuthStrategyType

    def is_configured(self) -> bool:
        """
        Whether the *app-level* setup (e.g. an OAuth client_id/secret) is
        present — independent of whether any particular user has connected.
        Drives the "Configuration Required" card state in the UI.

        Strategies where the user supplies their own credential at connect
        time (API key, SSH key, basic auth, no-auth, custom header) have
        nothing app-level to configure, so they default to True.
        """
        return True

    @abstractmethod
    async def initiate(self, db: Session, user_id: str, connector_row) -> AuthInitiation:
        """Begin a connection: an OAuth redirect, or a credential-form schema."""

    @abstractmethod
    async def complete(self, db: Session, user_id: str, connector_row, payload: dict) -> CredentialResult:
        """Finish a connection: OAuth code exchange, or store a submitted credential."""

    @abstractmethod
    async def refresh(self, db: Session, user_id: str, connector_row) -> CredentialResult:
        """Refresh an expiring credential. Strategies with no expiry just return success=True (no-op)."""

    @abstractmethod
    async def revoke(self, db: Session, user_id: str, connector_row) -> bool:
        """Best-effort remote revocation. Local state is always cleared by the caller regardless of the result."""

    @abstractmethod
    async def build_auth_context(self, db: Session, user_id: str, connector_row) -> Optional[AuthContext]:
        """Ready-to-use auth for the connector's client. None if not connected."""
