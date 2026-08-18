"""Disk storage helpers for AI Chat Workspace files.

Every uploaded/extracted/generated workspace file is written under a single
root directory, laid out as:

    {workspace_storage_dir}/{user_id}/{workspace_id}/{originals,extracted,generated,temp}/...

This module is the single choke point for path-traversal defense: every
caller that writes or reads a workspace file goes through
``sanitize_relative_path`` + ``_resolve_within`` here, never touching the
filesystem with a raw, unchecked path.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path, PurePosixPath

from api.config import settings

# Windows reserved device names — rejected as any path segment (case-insensitive).
_RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


class UnsafePathError(ValueError):
    """Raised when a relative path fails traversal/sanitization checks."""


def _storage_root() -> Path:
    path = Path(settings.workspace_storage_dir or "backend/uploads/workspaces")
    path.mkdir(parents=True, exist_ok=True)
    return path


def sanitize_relative_path(relative_path: str) -> str:
    """Validate and normalize a browser-supplied relative path (e.g. webkitRelativePath).

    Raises UnsafePathError on anything resembling path traversal, an absolute
    path, a NUL byte, a reserved device name, or a path that is too deep/long.
    Returns a normalized POSIX-style relative path safe to join under a
    workspace root.
    """
    if relative_path is None:
        raise UnsafePathError("Missing path")
    if "\x00" in relative_path:
        raise UnsafePathError("Path contains a NUL byte")

    # Normalize Windows-style separators to POSIX for consistent handling.
    normalized = relative_path.replace("\\", "/").strip()
    if not normalized:
        raise UnsafePathError("Empty path")

    # Reject absolute paths of any flavor (POSIX '/', Windows 'C:\', UNC '\\\\host\\share').
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise UnsafePathError(f"Absolute paths are not allowed: {relative_path!r}")

    parts = [p for p in normalized.split("/") if p not in ("", ".")]
    if not parts:
        raise UnsafePathError("Empty path")

    max_depth = settings.max_workspace_path_depth
    if len(parts) > max_depth:
        raise UnsafePathError(f"Path exceeds max depth of {max_depth}: {relative_path!r}")

    for part in parts:
        if part == "..":
            raise UnsafePathError(f"Path traversal segment '..' is not allowed: {relative_path!r}")
        bare = part.split(".")[0].upper()
        if bare in _RESERVED_NAMES:
            raise UnsafePathError(f"Reserved device name in path: {part!r}")

    clean = "/".join(parts)
    max_len = settings.max_workspace_path_length
    if len(clean) > max_len:
        raise UnsafePathError(f"Path exceeds max length of {max_len} characters")

    return clean


def _resolve_within(root: Path, relative_path: str) -> Path:
    """Join a sanitized relative path onto root and verify it did not escape."""
    clean = sanitize_relative_path(relative_path)
    root_resolved = root.resolve()
    target = (root_resolved / PurePosixPath(clean)).resolve()
    try:
        target.relative_to(root_resolved)
    except ValueError:
        raise UnsafePathError(f"Resolved path escapes workspace root: {relative_path!r}")
    return target


def workspace_dir(user_id: str, workspace_id: str) -> Path:
    return _storage_root() / user_id / workspace_id


def originals_dir(user_id: str, workspace_id: str) -> Path:
    d = workspace_dir(user_id, workspace_id) / "originals"
    d.mkdir(parents=True, exist_ok=True)
    return d


def extracted_dir(user_id: str, workspace_id: str) -> Path:
    d = workspace_dir(user_id, workspace_id) / "extracted"
    d.mkdir(parents=True, exist_ok=True)
    return d


def generated_dir(user_id: str, workspace_id: str) -> Path:
    d = workspace_dir(user_id, workspace_id) / "generated"
    d.mkdir(parents=True, exist_ok=True)
    return d


def temp_dir(user_id: str, workspace_id: str) -> Path:
    d = workspace_dir(user_id, workspace_id) / "temp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def checksum(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def save_upload(user_id: str, workspace_id: str, relative_path: str, data: bytes) -> str:
    """Save an originally-uploaded file, preserving its relative folder path."""
    root = originals_dir(user_id, workspace_id)
    dest = _resolve_within(root, relative_path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return str(dest)


def save_extracted_text(user_id: str, workspace_id: str, file_id: str, text: str) -> str:
    root = extracted_dir(user_id, workspace_id)
    dest = root / f"{file_id}.txt"
    dest.write_text(text, encoding="utf-8", errors="replace")
    return str(dest)


def save_generated(user_id: str, workspace_id: str, filename: str, data: bytes) -> str:
    root = generated_dir(user_id, workspace_id)
    dest = _resolve_within(root, filename)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return str(dest)


def read_file(storage_path: str) -> bytes:
    return Path(storage_path).read_bytes()


def read_text_file(storage_path: str) -> str:
    return Path(storage_path).read_text(encoding="utf-8", errors="replace")


def delete_workspace_dir(user_id: str, workspace_id: str) -> None:
    d = workspace_dir(user_id, workspace_id)
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)


def purge_temp(user_id: str, workspace_id: str) -> None:
    """Clear the temp/ subdir after a task completes or fails."""
    d = workspace_dir(user_id, workspace_id) / "temp"
    if d.exists():
        shutil.rmtree(d, ignore_errors=True)
    d.mkdir(parents=True, exist_ok=True)
