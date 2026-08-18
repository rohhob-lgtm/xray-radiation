"""
Connector registry — resolves a provider name to its PlatformConnector
instance. Nothing (routes, the future AI tool router, the sync/health
schedulers) may call a connector without going through this registry
first, which is what enforces "unregistered connectors can never be
invoked." Manifests are validated at register() time so a malformed
connector fails loudly at startup, not on the first real request.
"""
from __future__ import annotations

import logging

from .base import PlatformConnector

log = logging.getLogger(__name__)


class ConnectorNotRegisteredError(Exception):
    """Raised when resolving a provider that has no registered connector implementation."""


class InvalidManifestError(Exception):
    """Raised when a connector's manifest fails validation at register() time."""


def _validate_manifest(connector: PlatformConnector) -> None:
    manifest = connector.manifest
    if not manifest.provider:
        raise InvalidManifestError("Connector manifest is missing a provider id")
    if manifest.provider != connector.manifest.provider:
        raise InvalidManifestError("Connector.manifest.provider mismatch")
    actions = [c.action for c in manifest.capabilities]
    if len(actions) != len(set(actions)):
        raise InvalidManifestError(f"Duplicate capability actions declared for '{manifest.provider}'")
    if connector.auth_strategy is None:
        raise InvalidManifestError(f"Connector '{manifest.provider}' has no auth_strategy composed")
    if connector.auth_strategy.strategy_type != manifest.auth_strategy_type:
        raise InvalidManifestError(
            f"Connector '{manifest.provider}' manifest.auth_strategy_type "
            f"({manifest.auth_strategy_type}) does not match its composed AuthStrategy "
            f"({connector.auth_strategy.strategy_type})"
        )


class ConnectorRegistry:
    def __init__(self) -> None:
        self._connectors: dict[str, PlatformConnector] = {}

    def register(self, connector: PlatformConnector) -> None:
        _validate_manifest(connector)
        self._connectors[connector.manifest.provider] = connector
        log.info("Connector registered: %s", connector.manifest.provider)

    def get(self, provider: str) -> PlatformConnector:
        connector = self._connectors.get(provider)
        if connector is None:
            raise ConnectorNotRegisteredError(
                f"No connector is registered for provider '{provider}'"
            )
        return connector

    def is_registered(self, provider: str) -> bool:
        return provider in self._connectors

    def list_registered_providers(self) -> list[str]:
        return list(self._connectors.keys())


# Singleton — populated via bootstrap.register_all_connectors() at import time
# of routes/connectors.py.
connector_registry = ConnectorRegistry()
