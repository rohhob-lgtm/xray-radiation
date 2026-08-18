"""Workspace indexing orchestrator — ties file processors, storage, archive
extraction, and the DB manifest together.

Used both right after upload and by the explicit ``POST /:id/index`` re-index
endpoint. A single bad file only marks that file ``error`` — it never aborts
processing of the rest of the workspace.
"""
from __future__ import annotations

import logging
import mimetypes

from sqlalchemy.orm import Session

from api.config import settings
from api.db import crud
from api.db.models import Workspace, WorkspaceFile
from api.utils import workspace_storage
from api.utils.archive_processor import extract_zip_safely

from .registry import is_supported, process_file

log = logging.getLogger(__name__)


def _mime_guess(extension: str) -> str:
    mime, _ = mimetypes.guess_type(f"file.{extension}")
    return mime or "application/octet-stream"


def register_extracted_zip_entries(db: Session, workspace: Workspace, zip_file: WorkspaceFile) -> list[WorkspaceFile]:
    """Extract a ZIP WorkspaceFile's contents and register each entry as its own
    WorkspaceFile (parse_status='pending'), so the normal processing loop picks
    them up next — including nested ZIPs, which recurse naturally."""
    data = workspace_storage.read_file(zip_file.storage_path)
    result = extract_zip_safely(workspace.user_id, workspace.id, data)

    new_files: list[WorkspaceFile] = []
    existing_count = len(crud.list_workspace_files(db, workspace.id))
    skipped = list(result.skipped)

    for entry in result.entries:
        if existing_count + len(new_files) >= settings.max_workspace_files:
            skipped.append({"path": entry.relative_path, "reason": "Workspace file-count limit reached"})
            continue
        extension = entry.relative_path.rsplit(".", 1)[-1] if "." in entry.relative_path else ""
        entry_bytes = workspace_storage.read_file(entry.storage_path)
        wf = crud.add_workspace_file(
            db, workspace.id,
            relative_path=f"{zip_file.relative_path}/{entry.relative_path}",
            original_filename=entry.relative_path.rsplit("/", 1)[-1],
            mime_type=_mime_guess(extension),
            extension=extension,
            size_bytes=entry.size_bytes,
            checksum=workspace_storage.checksum(entry_bytes),
            storage_path=entry.storage_path,
        )
        new_files.append(wf)

    warnings = [f"{s['path']}: {s['reason']}" for s in skipped]
    crud.update_workspace_file_status(db, zip_file.id, parse_status="ready", warnings=warnings)
    crud.recompute_workspace_totals(db, workspace.id)
    return new_files


def process_workspace_file(db: Session, workspace: Workspace, wf: WorkspaceFile) -> None:
    crud.update_workspace_file_status(db, wf.id, parse_status="processing")
    try:
        if (wf.extension or "").lower() == "zip":
            register_extracted_zip_entries(db, workspace, wf)
            return

        data = workspace_storage.read_file(wf.storage_path)
        result = process_file(wf.relative_path, data, wf.extension, filename=wf.original_filename)

        if result["errors"]:
            crud.update_workspace_file_status(
                db, wf.id, parse_status="error",
                errors=result["errors"], warnings=result["warnings"],
            )
            return

        text_path = None
        if result["text"]:
            text_path = workspace_storage.save_extracted_text(workspace.user_id, workspace.id, wf.id, result["text"])

        status = "ready" if is_supported(wf.extension) else "unsupported"
        crud.update_workspace_file_status(
            db, wf.id, parse_status=status,
            extracted_text_path=text_path, warnings=result["warnings"], errors=[],
        )
    except Exception as exc:
        log.exception("Failed to process workspace file %s", wf.id)
        crud.update_workspace_file_status(db, wf.id, parse_status="error", errors=[f"Unexpected processing error: {exc}"])


def process_workspace(db: Session, workspace: Workspace) -> dict:
    """Process every pending file (including files newly discovered inside ZIPs
    extracted during this same run). Returns {processed, failed, total}."""
    processed = 0
    failed = 0
    guard = 0

    pending = [f for f in crud.list_workspace_files(db, workspace.id) if f.parse_status == "pending"]
    while pending and guard < 20:
        guard += 1
        for wf in pending:
            process_workspace_file(db, workspace, wf)
            db.refresh(wf)
            if wf.parse_status == "error":
                failed += 1
            else:
                processed += 1
        pending = [f for f in crud.list_workspace_files(db, workspace.id) if f.parse_status == "pending"]

    crud.recompute_workspace_totals(db, workspace.id)
    return {"processed": processed, "failed": failed, "total": processed + failed}
