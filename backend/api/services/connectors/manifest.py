"""
Static connector metadata — what a connector IS before any user ever
connects to it. Every provider (Canva, Google Drive, SFTP, ...) declares
one ConnectorManifest; the registry, routes, and frontend all read from it
instead of hardcoding per-provider knowledge.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class ConnectorCategory(str, Enum):
    DESIGN = "design"
    FILE_STORAGE = "file_storage"
    CODE_REPO = "code_repo"
    KNOWLEDGE_BASE = "knowledge_base"
    COMMUNICATION = "communication"
    CALENDAR = "calendar"
    CUSTOM = "custom"


class AuthStrategyType(str, Enum):
    OAUTH2_PKCE = "oauth2_pkce"
    API_KEY = "api_key"
    BASIC_AUTH = "basic_auth"
    SSH_KEY = "ssh_key"
    NO_AUTH = "no_auth"
    CUSTOM_HEADER = "custom_header"


@dataclass(frozen=True)
class CapabilityDefinition:
    """One action a connector can perform (e.g. 'canva.list_designs')."""
    action: str
    description: str
    parameters_schema: dict = field(default_factory=dict)
    required_scopes: tuple[str, ...] = ()
    is_destructive: bool = False
    # False for actions the manifest documents as part of the provider's
    # eventual surface but that aren't wired up yet — lets the framework
    # describe a connector's full intended shape without ever claiming an
    # unimplemented action works.
    is_implemented: bool = True


@dataclass(frozen=True)
class ConnectorManifest:
    provider: str
    display_name: str
    category: ConnectorCategory
    auth_strategy_type: AuthStrategyType
    capabilities: tuple[CapabilityDefinition, ...] = ()
    supports_sync: bool = False
    supports_health_check: bool = False
    icon: str = "🔌"

    def get_capability(self, action: str) -> CapabilityDefinition | None:
        return next((c for c in self.capabilities if c.action == action), None)

    def as_dict(self) -> dict:
        return {
            "provider": self.provider,
            "display_name": self.display_name,
            "category": self.category.value,
            "auth_strategy_type": self.auth_strategy_type.value,
            "supports_sync": self.supports_sync,
            "supports_health_check": self.supports_health_check,
            "icon": self.icon,
            "capabilities": [
                {
                    "action": c.action,
                    "description": c.description,
                    "required_scopes": list(c.required_scopes),
                    "is_destructive": c.is_destructive,
                    "is_implemented": c.is_implemented,
                }
                for c in self.capabilities
            ],
        }
