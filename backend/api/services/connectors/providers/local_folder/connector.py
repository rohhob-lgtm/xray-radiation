"""
LocalFolderConnector — a file-storage connector with no remote credential at
all. Exists to prove the PlatformConnector/AuthStrategy split genuinely
generalizes beyond OAuth: "connecting" just means picking a local directory
via NoAuthStrategy, and every list/read action is scoped under that root
using the same path-traversal guard the AI Chat Workspace already relies on
(api.utils.workspace_storage.sanitize_relative_path) rather than
reinventing path safety.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from api.utils.workspace_storage import sanitize_relative_path, UnsafePathError

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.no_auth import NoAuthStrategy

_MAX_READ_BYTES = 2_000_000  # 2 MB — a generous cap for a text-preview read

LOCAL_FOLDER_MANIFEST = ConnectorManifest(
    provider="local_folder",
    display_name="Local Folder",
    category=ConnectorCategory.FILE_STORAGE,
    auth_strategy_type=AuthStrategyType.NO_AUTH,
    icon="📁",
    supports_sync=False,
    supports_health_check=True,
    capabilities=(
        CapabilityDefinition("local_folder.list_files", "List files/folders under the configured root",
                              parameters_schema={"relative_path": {"type": "string", "required": False}}),
        CapabilityDefinition("local_folder.read_file", "Read a text file's contents",
                              parameters_schema={"relative_path": {"type": "string", "required": True}}),
    ),
)


def _resolve_under_root(root: Path, relative_path: str) -> Path:
    clean = sanitize_relative_path(relative_path) if relative_path else ""
    candidate = (root / clean).resolve() if clean else root.resolve()
    root_resolved = root.resolve()
    if candidate != root_resolved and root_resolved not in candidate.parents:
        raise UnsafePathError(f"Path escapes the configured root: {relative_path!r}")
    return candidate


class LocalFolderConnector(PlatformConnector):
    manifest = LOCAL_FOLDER_MANIFEST

    def __init__(self):
        self.auth_strategy = NoAuthStrategy()

    async def _root_path(self, db: Session, user_id: str) -> Path | None:
        connector_row = self._connector_row(db)
        ctx = await self.auth_strategy.build_auth_context(db, user_id, connector_row)
        root = (ctx.extra.get("root_path") if ctx else None)
        if not root:
            return None
        return Path(root)

    async def execute_action(
        self, db: Session, user_id: str, action: str, parameters: dict[str, Any]
    ) -> ConnectorActionResult:
        root = await self._root_path(db, user_id)
        if not root:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")
        if not root.is_dir():
            return ConnectorActionResult(success=False, action=action, error_code="ROOT_PATH_MISSING",
                                          error_message=f"Configured folder no longer exists: {root}")

        try:
            if action == "local_folder.list_files":
                target = _resolve_under_root(root, parameters.get("relative_path", ""))
                if not target.is_dir():
                    return ConnectorActionResult(success=False, action=action, error_code="NOT_A_DIRECTORY")
                entries = [
                    {"name": p.name, "is_dir": p.is_dir(), "size_bytes": p.stat().st_size if p.is_file() else 0}
                    for p in sorted(target.iterdir(), key=lambda p: p.name.lower())
                ]
                data = {"root": str(root), "relative_path": parameters.get("relative_path", ""), "entries": entries}

            elif action == "local_folder.read_file":
                relative_path = parameters.get("relative_path")
                if not relative_path:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="relative_path is required")
                target = _resolve_under_root(root, relative_path)
                if not target.is_file():
                    return ConnectorActionResult(success=False, action=action, error_code="NOT_A_FILE")
                if target.stat().st_size > _MAX_READ_BYTES:
                    return ConnectorActionResult(success=False, action=action, error_code="FILE_TOO_LARGE")
                content = target.read_text(encoding="utf-8", errors="replace")
                data = {"relative_path": relative_path, "content": content, "size_bytes": target.stat().st_size}

            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except UnsafePathError as exc:
            return ConnectorActionResult(success=False, action=action, error_code="UNSAFE_PATH", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        root = await self._root_path(db, user_id)
        if not root:
            return HealthStatus(healthy=False, detail="Not connected")
        if not root.is_dir():
            return HealthStatus(healthy=False, detail=f"Folder no longer exists: {root}")
        return HealthStatus(healthy=True)


local_folder_connector = LocalFolderConnector()
