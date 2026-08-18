"""Disk storage helpers for uploaded source files.

Translation projects used to store the entire source file as a PostgreSQL
bytea (``source_file_data``).  For large files this causes DB connections to
be dropped or timed out.  New uploads are persisted on disk instead; the
project record stores the absolute path in ``source_file_path``.  Legacy rows
that still have ``source_file_data`` bytes continue to work.
"""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Optional

from api.db.models import TranslationProject
from api.config import settings


def _upload_dir() -> Path:
    """Return the directory where uploaded source files are stored."""
    path = Path(settings.upload_storage_dir or "/tmp/translation_uploads")
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_source_file(project_id: str, data: bytes, filename: str) -> str:
    """Persist source bytes on disk and return the absolute path."""
    dest = _upload_dir() / f"{project_id}"
    dest.mkdir(parents=True, exist_ok=True)
    ext = Path(filename).suffix or ".bin"
    file_path = dest / f"source{ext}"
    file_path.write_bytes(data)
    return str(file_path)


def copy_source_file(src_project: TranslationProject, dst_project_id: str) -> Optional[str]:
    """Copy a source file from one project to another. Returns the new path or None."""
    src_path = src_project.source_file_path
    if src_path and os.path.exists(src_path):
        dest = _upload_dir() / f"{dst_project_id}"
        dest.mkdir(parents=True, exist_ok=True)
        ext = Path(src_project.source_filename).suffix or ".bin"
        dst_path = dest / f"source{ext}"
        shutil.copy2(src_path, dst_path)
        return str(dst_path)
    return None


def get_source_bytes(project: TranslationProject) -> Optional[bytes]:
    """Return the source file bytes, reading from disk when available."""
    if project.source_file_path:
        try:
            return Path(project.source_file_path).read_bytes()
        except FileNotFoundError:
            # Fall back to legacy in-DB bytes if the disk file is missing
            return project.source_file_data
    return project.source_file_data


def has_source_file(project: TranslationProject) -> bool:
    """Return True if the project has a source file (disk or legacy bytea)."""
    if project.source_file_path:
        return Path(project.source_file_path).exists()
    return bool(project.source_file_data)


def delete_source_file(project: TranslationProject) -> None:
    """Remove the on-disk source file, if any."""
    if project.source_file_path:
        try:
            os.unlink(project.source_file_path)
        except FileNotFoundError:
            pass
        try:
            # Remove the project directory if it is empty
            project_dir = Path(project.source_file_path).parent
            if project_dir.exists() and not any(project_dir.iterdir()):
                project_dir.rmdir()
        except OSError:
            pass
