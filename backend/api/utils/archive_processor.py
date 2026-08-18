"""Secure ZIP extraction for the AI Chat Workspace.

Guards against the classic archive attacks: path traversal (entries that
resolve outside the destination), zip bombs (huge uncompressed size hidden
behind a tiny compressed file), entry-count flooding, and symlink entries —
all bounded by configurable limits (api.config.settings), never hardcoded.

A bad entry is recorded in ``ExtractionResult.skipped`` and extraction
continues with the remaining entries — one malicious/corrupt entry must not
abort the whole archive, matching the "a failure in one file must not
terminate the complete job" requirement.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from typing import Optional

from api.config import settings
from api.utils.workspace_storage import sanitize_relative_path, UnsafePathError, save_upload

_SYMLINK_UNIX_MODE = 0o120000
_UNIX_MODE_MASK = 0o170000


@dataclass
class ExtractedEntry:
    relative_path: str
    size_bytes: int
    storage_path: str = ""


@dataclass
class ExtractionResult:
    entries: list[ExtractedEntry] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)  # [{"path": str, "reason": str}]
    total_uncompressed_bytes: int = 0


def extract_zip_safely(user_id: str, workspace_id: str, zip_bytes: bytes) -> ExtractionResult:
    result = ExtractionResult()
    max_entries = settings.max_zip_file_count
    max_uncompressed = settings.max_zip_uncompressed_size_mb * 1024 * 1024

    try:
        zf = zipfile.ZipFile(io.BytesIO(zip_bytes))
    except zipfile.BadZipFile as exc:
        result.skipped.append({"path": "<archive>", "reason": f"Corrupted or invalid ZIP file: {exc}"})
        return result

    infolist = zf.infolist()
    if len(infolist) > max_entries:
        result.skipped.append({
            "path": "<archive>",
            "reason": f"Archive has {len(infolist)} entries, exceeding the limit of {max_entries}",
        })
        return result

    running_total = 0
    for info in infolist:
        if info.is_dir():
            continue

        # Symlinks: upper 16 bits of external_attr hold the unix file mode when
        # the archive was created on a POSIX system (create_system == 3).
        unix_mode = (info.external_attr >> 16) & 0xFFFF
        if unix_mode and (unix_mode & _UNIX_MODE_MASK) == _SYMLINK_UNIX_MODE:
            result.skipped.append({"path": info.filename, "reason": "Symlink entries are not extracted"})
            continue

        # Zip-bomb guard: abort BEFORE decompressing this entry if the
        # declared uncompressed size alone would exceed the cap.
        running_total += info.file_size
        if running_total > max_uncompressed:
            result.skipped.append({
                "path": info.filename,
                "reason": f"Extraction stopped: cumulative uncompressed size would exceed {settings.max_zip_uncompressed_size_mb}MB",
            })
            break

        try:
            safe_rel = sanitize_relative_path(info.filename)
        except UnsafePathError as exc:
            result.skipped.append({"path": info.filename, "reason": str(exc)})
            continue

        try:
            data = zf.read(info)
        except Exception as exc:
            result.skipped.append({"path": info.filename, "reason": f"Failed to read entry: {exc}"})
            continue

        # Defense in depth: a crafted central-directory record can under-report
        # file_size relative to the real decompressed bytes.
        actual_extra = max(0, len(data) - info.file_size)
        if actual_extra:
            running_total += actual_extra
            if running_total > max_uncompressed:
                result.skipped.append({
                    "path": info.filename,
                    "reason": "Extraction stopped: actual decompressed size exceeded the declared size and the cumulative cap",
                })
                break

        try:
            storage_path = save_upload(user_id, workspace_id, safe_rel, data)
        except UnsafePathError as exc:
            result.skipped.append({"path": info.filename, "reason": str(exc)})
            continue

        result.entries.append(ExtractedEntry(relative_path=safe_rel, size_bytes=len(data), storage_path=storage_path))

    result.total_uncompressed_bytes = running_total
    return result
