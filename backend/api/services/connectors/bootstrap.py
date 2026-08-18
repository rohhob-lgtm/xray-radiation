"""
Single source of truth for "which connectors exist" — both DB seeding
(db/base.py) and the runtime registry (registry.py) read from here, so a
provider's name/category/capabilities never has to be typed out twice.
"""
from __future__ import annotations

from .manifest import ConnectorManifest
from .registry import ConnectorRegistry

# Providers with a real PlatformConnector implementation wired up (not just
# a declarative manifest). Every other manifest returned by
# get_all_manifests() is seeded as a real, honest "coming soon" row —
# enabled=False, never claimed to work.
IMPLEMENTED_PROVIDERS: frozenset[str] = frozenset({"canva", "local_folder", "google_drive"})


def get_all_manifests() -> list[ConnectorManifest]:
    from .providers.canva.connector import CANVA_MANIFEST
    from .providers.local_folder.connector import LOCAL_FOLDER_MANIFEST
    from .providers.google_drive.connector import GOOGLE_DRIVE_MANIFEST
    from .providers.placeholders import PLACEHOLDER_MANIFESTS

    return [CANVA_MANIFEST, LOCAL_FOLDER_MANIFEST, GOOGLE_DRIVE_MANIFEST, *PLACEHOLDER_MANIFESTS]


def register_all_connectors(registry: ConnectorRegistry) -> None:
    """Register every implemented connector instance. Idempotent."""
    from .providers.canva.connector import canva_connector
    from .providers.local_folder.connector import local_folder_connector
    from .providers.google_drive.connector import google_drive_connector

    for connector in (canva_connector, local_folder_connector, google_drive_connector):
        if not registry.is_registered(connector.manifest.provider):
            registry.register(connector)
