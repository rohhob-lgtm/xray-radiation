"""
Knowledge Library — persistent local folder sources for the AI Training Center.

Lets an admin register a folder once (e.g. D:\\Training Manuals\\) and re-scan it
on demand instead of re-picking files through the browser every time. Reuses the
existing per-file dedup (DocumentHash/is_duplicate) and study pipeline
(ProcessingJob + run_processing_job) — a scan just walks the filesystem and
enqueues exactly the same jobs a browser upload would create.

Endpoints:
  GET    /library/folders           — list registered folders
  POST   /library/folders           — register a new folder path
  DELETE /library/folders/{id}      — unregister (does not delete already-learned knowledge)
  POST   /library/folders/{id}/scan — recursively scan + ingest new files (background)
"""
from __future__ import annotations
import asyncio
import hashlib
import logging
import os
import pathlib
import shutil
import tempfile
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException
from sqlalchemy.orm import Session

from api.config import settings
from api.db import get_db
from api.db.base import SessionLocal
from api.db.models import KnowledgeLibraryFolder, ProcessingJob
from api.db.crud import create_rag_document
from api.middleware.auth import require_auth
from api.routes.study import _require_admin
from api.services.study_service import is_duplicate
from api.services.job_runner import run_processing_job

log = logging.getLogger(__name__)
router = APIRouter(tags=["knowledge-library"])

# Same allowlist the folder-upload UI filters to on the client. Kept in sync
# manually since there's no shared frontend/backend config for it today.
SUPPORTED_EXTENSIONS = {"pdf", "docx", "pptx", "xlsx", "txt", "csv", "md", "html", "xml"}
_HIDDEN_NAMES = {"thumbs.db", "desktop.ini", ".ds_store"}

# The study pipeline writes intermediate files (extracted_text.txt, checkpoints)
# next to ProcessingJob.file_path. Registered library folders are the user's own
# files, not disposable upload scratch space, so every file is copied here
# before a job is created — the original is only ever opened read-only.
_SCAN_TEMP_ROOT = pathlib.Path(tempfile.gettempdir()) / "library_scans"
_SCAN_TEMP_ROOT.mkdir(parents=True, exist_ok=True)


def _is_hidden(name: str) -> bool:
    return name.startswith(".") or name.lower() in _HIDDEN_NAMES


def _folder_to_dict(folder: KnowledgeLibraryFolder) -> dict:
    return {
        "id": folder.id,
        "path": folder.path,
        "label": folder.label,
        "enabled": folder.enabled,
        "scan_status": folder.scan_status,
        "last_scanned_at": folder.last_scanned_at.isoformat() if folder.last_scanned_at else None,
        "last_scan_summary": folder.last_scan_summary,
        "created_at": folder.created_at.isoformat() if folder.created_at else None,
    }


@router.get("/library/folders")
def list_folders(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _require_admin(user)
    folders = db.query(KnowledgeLibraryFolder).order_by(KnowledgeLibraryFolder.created_at.desc()).all()
    return [_folder_to_dict(f) for f in folders]


@router.post("/library/folders", status_code=201)
def register_folder(
    body: dict = Body(...),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    _require_admin(user)
    raw_path = (body.get("path") or "").strip()
    label = (body.get("label") or "").strip()
    if not raw_path:
        raise HTTPException(status_code=400, detail="path is required")

    path = pathlib.Path(raw_path)
    if not path.is_absolute():
        raise HTTPException(status_code=400, detail="path must be an absolute filesystem path")
    if not path.exists() or not path.is_dir():
        raise HTTPException(status_code=400, detail=f"Folder not found or not a directory: {raw_path}")

    normalized = str(path.resolve())
    existing = db.query(KnowledgeLibraryFolder).filter(KnowledgeLibraryFolder.path == normalized).first()
    if existing:
        raise HTTPException(status_code=409, detail="This folder is already registered")

    folder = KnowledgeLibraryFolder(path=normalized, label=label or path.name)
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return _folder_to_dict(folder)


@router.delete("/library/folders/{folder_id}")
def unregister_folder(folder_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    _require_admin(user)
    folder = db.query(KnowledgeLibraryFolder).filter(KnowledgeLibraryFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    # Unregistering only stops future re-scans — knowledge already learned from
    # files in this folder is kept, per the "never relearn, never silently
    # forget" requirement.
    db.delete(folder)
    db.commit()
    return {"ok": True}


@router.post("/library/folders/{folder_id}/scan", status_code=202)
def scan_folder(
    folder_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    _require_admin(user)
    folder = db.query(KnowledgeLibraryFolder).filter(KnowledgeLibraryFolder.id == folder_id).first()
    if not folder:
        raise HTTPException(status_code=404, detail="Folder not found")
    if folder.scan_status == "scanning":
        raise HTTPException(status_code=409, detail="A scan is already running for this folder")

    folder.scan_status = "scanning"
    db.commit()

    background_tasks.add_task(_run_scan, folder_id, user.get("id"))
    return {"ok": True, "status": "scanning"}


def _stream_sha256(path: pathlib.Path) -> str:
    sha = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            block = f.read(1024 * 1024)
            if not block:
                break
            sha.update(block)
    return sha.hexdigest()


async def _run_scan(folder_id: str, user_id: str | None) -> None:
    """Background task: recursively walk the folder, dedup, and enqueue study jobs."""
    db = SessionLocal()
    summary = {"discovered": 0, "queued": 0, "skipped_duplicate": 0, "skipped_unsupported": 0, "errors": []}
    semaphore = asyncio.Semaphore(max(1, settings.max_concurrent_study_jobs))
    # DocumentHash rows are only written once a study job *finishes*, so two
    # identical files discovered in the same scan would both pass is_duplicate()
    # if we only checked the DB. Track hashes seen this scan too.
    seen_this_scan: set[str] = set()

    async def _launch(job_id: str) -> None:
        async with semaphore:
            await run_processing_job(job_id)

    try:
        folder = db.query(KnowledgeLibraryFolder).filter(KnowledgeLibraryFolder.id == folder_id).first()
        if not folder:
            return
        root = pathlib.Path(folder.path)

        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if not _is_hidden(d)]
            for name in filenames:
                if _is_hidden(name):
                    continue
                file_path = pathlib.Path(dirpath) / name
                ext = file_path.suffix.lower().lstrip(".")
                if ext not in SUPPORTED_EXTENSIONS:
                    summary["skipped_unsupported"] += 1
                    continue
                summary["discovered"] += 1

                try:
                    relative_path = str(file_path.relative_to(root))
                except ValueError:
                    relative_path = name

                try:
                    sha = _stream_sha256(file_path)
                except Exception as exc:
                    summary["errors"].append(f"{relative_path}: {exc}")
                    continue

                if sha in seen_this_scan or is_duplicate(db, sha):
                    summary["skipped_duplicate"] += 1
                    continue
                seen_this_scan.add(sha)

                # Copy into scratch space — the study pipeline writes intermediate
                # files next to file_path, and this must never touch the user's
                # own folder.
                scratch_dir = _SCAN_TEMP_ROOT / uuid.uuid4().hex
                scratch_dir.mkdir(parents=True, exist_ok=True)
                scratch_path = scratch_dir / file_path.name
                try:
                    shutil.copy2(file_path, scratch_path)
                except Exception as exc:
                    summary["errors"].append(f"{relative_path}: copy failed: {exc}")
                    continue

                doc = create_rag_document(
                    db,
                    user_id=user_id,
                    filename=relative_path,
                    document_type="other",
                    content="__processing__",
                    status="processing",
                )
                job = ProcessingJob(
                    doc_id=doc.id,
                    filename=relative_path,
                    file_path=str(scratch_path),
                    status="queued",
                    current_stage="Queued for processing",
                    total_batches=0,
                )
                db.add(job)
                db.commit()
                db.refresh(job)

                summary["queued"] += 1
                asyncio.create_task(_launch(job.id))

        folder.scan_status = "completed"
        folder.last_scanned_at = datetime.now(timezone.utc)
        folder.last_scan_summary = summary
        db.commit()
    except Exception as exc:
        log.exception("Knowledge Library scan failed for folder %s", folder_id)
        summary["errors"].append(str(exc))
        try:
            folder = db.query(KnowledgeLibraryFolder).filter(KnowledgeLibraryFolder.id == folder_id).first()
            if folder:
                folder.scan_status = "error"
                folder.last_scan_summary = summary
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
