"""AI Chat Workspace routes — upload, inspect, index, and download for the
per-user file/folder workspace that backs the workspace agent in AI Chat.

Every route requires a logged-in user (require_auth) and every query is
scoped to that user's own workspaces — this is the whole of the "no user can
access another user's files by changing a URL parameter" guarantee, enforced
in api.db.crud (get_workspace/get_workspace_file/get_generated_file all take
and filter by user_id/workspace_id).
"""
from __future__ import annotations

import logging
import mimetypes
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.db import crud
from api.middleware.auth import require_auth
from api.utils import workspace_storage
from api.utils.filename_helper import content_disposition, mime_for_ext
from api.services.workspace_processors.service import process_workspace
from api.services import workspace_index

log = logging.getLogger(__name__)
router = APIRouter(prefix="/workspaces", tags=["workspaces"])

# Extensions rejected outright regardless of size/count limits — never stored,
# never executed. Matches "no executable uploads / no automatic execution".
_BLOCKED_EXTENSIONS = {
    "exe", "dll", "so", "dylib", "sh", "bash", "bat", "cmd", "ps1", "psm1",
    "msi", "com", "scr", "vbs", "vbe", "js.exe", "jar", "app", "deb", "rpm",
    "bin", "apk", "run", "action", "workflow", "gadget",
}


def _owned_workspace(db: Session, workspace_id: str, user_id: str):
    ws = crud.get_workspace(db, workspace_id, user_id)
    if not ws:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


class CreateWorkspaceInput(BaseModel):
    name: Optional[str] = None
    conversation_id: Optional[str] = None


@router.post("", status_code=201)
def create_workspace(
    body: CreateWorkspaceInput,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    ws = crud.create_workspace(db, user["id"], name=body.name or "Workspace", conversation_id=body.conversation_id)
    if body.conversation_id:
        conv = crud.get_conversation(db, body.conversation_id)
        if conv and conv.user_id == user["id"]:
            crud.link_conversation_workspace(db, body.conversation_id, ws.id)
    return crud.workspace_to_dict(ws)


@router.get("")
def list_workspaces(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    return [crud.workspace_to_dict(w) for w in crud.list_workspaces(db, user["id"])]


@router.get("/{workspace_id}")
def get_workspace(workspace_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    files = crud.list_workspace_files(db, ws.id)
    return {**crud.workspace_to_dict(ws), "files": [crud.workspace_file_to_dict(f) for f in files]}


@router.get("/{workspace_id}/tree")
def get_workspace_tree(workspace_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    files = crud.list_workspace_files(db, ws.id)
    tree: dict = {}
    for f in files:
        parts = f.relative_path.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {"__type__": "dir", "children": {}})["children"]
        node[parts[-1]] = {
            "__type__": "file", "id": f.id, "size_bytes": f.size_bytes,
            "parse_status": f.parse_status, "extension": f.extension,
        }
    return {"workspace_id": ws.id, "tree": tree}


@router.get("/{workspace_id}/files")
def list_files(workspace_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    return [crud.workspace_file_to_dict(f) for f in crud.list_workspace_files(db, ws.id)]


@router.get("/{workspace_id}/files/{file_id}")
def get_file(workspace_id: str, file_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    wf = crud.get_workspace_file(db, file_id, ws.id)
    if not wf:
        raise HTTPException(status_code=404, detail="File not found")
    return crud.workspace_file_to_dict(wf)


@router.delete("/{workspace_id}/files/{file_id}", status_code=204)
def delete_file(workspace_id: str, file_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    if not crud.delete_workspace_file(db, file_id, ws.id):
        raise HTTPException(status_code=404, detail="File not found")
    crud.recompute_workspace_totals(db, ws.id)
    # Hybrid Workspace Awareness trigger #3 (file deleted) — next reindex
    # pass removes the now-orphaned IndexedResource instead of re-embedding it.
    workspace_index.mark_dirty(db, "workspace_file", file_id, ws.id, reason="deleted")


def _validate_and_store_upload(
    db: Session, ws, filename: str, relative_path: str, data: bytes, existing_count: int, existing_total: int,
) -> tuple[Optional[dict], Optional[str]]:
    """Returns (file_dict_or_None, error_or_None). Never raises."""
    extension = relative_path.rsplit(".", 1)[-1].lower() if "." in relative_path else ""

    if extension in _BLOCKED_EXTENSIONS:
        return None, f"{relative_path}: executable/script files are not allowed"

    if len(data) > settings.max_workspace_file_size_mb * 1024 * 1024:
        return None, f"{relative_path}: exceeds the per-file size limit of {settings.max_workspace_file_size_mb}MB"

    if existing_count >= settings.max_workspace_files:
        return None, f"{relative_path}: workspace file-count limit of {settings.max_workspace_files} reached"

    if existing_total + len(data) > settings.max_workspace_total_size_mb * 1024 * 1024:
        return None, f"{relative_path}: would exceed the workspace total size limit of {settings.max_workspace_total_size_mb}MB"

    try:
        storage_path = workspace_storage.save_upload(ws.user_id, ws.id, relative_path, data)
    except workspace_storage.UnsafePathError as exc:
        return None, f"{relative_path}: {exc}"

    mime, _ = mimetypes.guess_type(filename)
    wf = crud.add_workspace_file(
        db, ws.id,
        relative_path=workspace_storage.sanitize_relative_path(relative_path),
        original_filename=filename,
        mime_type=mime or "application/octet-stream",
        extension=extension,
        size_bytes=len(data),
        checksum=workspace_storage.checksum(data),
        storage_path=storage_path,
    )
    return crud.workspace_file_to_dict(wf), None


@router.post("/{workspace_id}/upload")
@router.post("/{workspace_id}/upload-folder")
async def upload_files(
    workspace_id: str,
    files: list[UploadFile] = File(...),
    relative_paths: Optional[list[str]] = Form(None),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Accepts one or many files. ``relative_paths`` (parallel array, same
    order as ``files``) preserves folder structure for folder/multi-file
    uploads (browser sends ``file.webkitRelativePath`` here); when omitted,
    each file's own name is used (flat upload). A ``.zip`` among the files is
    stored as-is and auto-extracted (path-traversal/zip-bomb guarded) during
    indexing below — this is also how "upload a folder as a zip" is handled.
    """
    ws = _owned_workspace(db, workspace_id, user["id"])
    existing = crud.list_workspace_files(db, ws.id)
    existing_count = len(existing)
    existing_total = sum(f.size_bytes for f in existing)

    added: list[dict] = []
    errors: list[str] = []

    for i, upload in enumerate(files):
        data = await upload.read()
        rel_path = (relative_paths[i] if relative_paths and i < len(relative_paths) else None) or upload.filename or f"file_{i}"
        result, err = _validate_and_store_upload(db, ws, upload.filename or rel_path, rel_path, data, existing_count, existing_total)
        if err:
            errors.append(err)
            continue
        added.append(result)
        existing_count += 1
        existing_total += len(data)

    crud.recompute_workspace_totals(db, ws.id)

    summary = process_workspace(db, ws)

    return {
        "workspace": crud.workspace_to_dict(ws),
        "uploaded": added,
        "upload_errors": errors,
        "processing": summary,
    }


@router.post("/{workspace_id}/index")
def reindex_workspace(workspace_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    # Re-queue error/unsupported files for another pass (e.g. after a processor fix)
    # in addition to any still-pending files.
    for wf in crud.list_workspace_files(db, ws.id):
        if wf.parse_status == "error":
            crud.update_workspace_file_status(db, wf.id, parse_status="pending")
    summary = process_workspace(db, ws)
    return {"workspace": crud.workspace_to_dict(ws), "processing": summary}


@router.post("/{workspace_id}/refresh-index")
async def refresh_index(
    workspace_id: str,
    force: bool = False,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Hybrid Workspace Awareness trigger #13 (explicit AI/user refresh request).
    Incremental by default; force=True marks every resource dirty first —
    the only path to a full rebuild, and only ever taken explicitly.
    """
    ws = _owned_workspace(db, workspace_id, user["id"])
    counts = await workspace_index.reindex_dirty(db, workspace_id=ws.id, limit=200, force=force)
    return {"workspace_id": ws.id, **counts}


@router.get("/{workspace_id}/index-status")
def index_status(workspace_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    """
    Hybrid Workspace Awareness trigger #14 (user opening a different
    project) — the frontend calls this on workspace switch to decide whether
    a refresh is needed before the next chat turn.
    """
    ws = _owned_workspace(db, workspace_id, user["id"])
    dirty = crud.count_dirty_resources(db, ws.id)
    return {"workspace_id": ws.id, "dirty_count": dirty, "fresh": dirty == 0}


@router.get("/{workspace_id}/tasks/{task_id}")
def get_task(workspace_id: str, task_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    task = crud.get_task(db, task_id, ws.id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return crud.task_to_dict(task, include_events=True)


@router.get("/{workspace_id}/generated")
def list_generated(workspace_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    return [crud.generated_file_to_dict(g) for g in crud.list_generated_files(db, ws.id)]


@router.get("/{workspace_id}/generated/{file_id}/download")
def download_generated(workspace_id: str, file_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    gf = crud.get_generated_file(db, file_id, ws.id)
    if not gf:
        raise HTTPException(status_code=404, detail="Generated file not found")
    try:
        data = workspace_storage.read_file(gf.storage_path)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="Generated file is missing from storage")
    return Response(
        content=data,
        media_type=mime_for_ext(gf.format),
        headers={"Content-Disposition": content_disposition(gf.filename), "Content-Length": str(len(data))},
    )


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    ws = _owned_workspace(db, workspace_id, user["id"])
    workspace_storage.delete_workspace_dir(ws.user_id, ws.id)
    crud.delete_workspace(db, workspace_id, user["id"])
