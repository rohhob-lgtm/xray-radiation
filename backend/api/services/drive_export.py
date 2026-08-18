"""Shared "export a design, then upload it to Google Drive" logic.

Extracted from POST /connectors/canva/{design_id}/save-to-drive (the manual
Save-to-Drive button's route) so the exact same, already-audited call chain
(canva.export_design -> download -> google_drive.save_generated_file) is
used both by that route and by the Agent Orchestrator runner, which needs to
do the same thing automatically for a design+drive-save chat request —
including the local_render_only case (no Canva object at all), which the
manual route never has to handle since it always starts from a design_id.
"""
from __future__ import annotations

import base64
import re
from dataclasses import dataclass
from typing import Any, Optional

import httpx
from sqlalchemy.orm import Session

from api.services.connectors.base import ConnectorActionResult
from api.services.connectors.service import connector_service

_SANITIZE_RE = re.compile(r"[^\w\-. ]+")


def sanitize_filename(name: str) -> str:
    cleaned = _SANITIZE_RE.sub("", name or "").strip()
    return cleaned[:100] or "design"


@dataclass
class ExportOutcome:
    success: bool
    format: str  # png | pdf
    content_bytes: Optional[bytes] = None
    mime_type: Optional[str] = None
    error_code: Optional[str] = None
    error_message: Optional[str] = None


async def export_canva_design(
    db: Session, user_id: str, canva_design_id: str, export_format: str,
) -> ExportOutcome:
    """Exports a real Canva design and downloads the resulting bytes."""
    export_result = await connector_service.execute_action(
        db, user_id, "canva", "canva.export_design",
        {"design_id": canva_design_id, "format": export_format},
    )
    if not export_result.success:
        return ExportOutcome(success=False, format=export_format,
                              error_code=export_result.error_code, error_message=export_result.error_message)

    urls = (export_result.data or {}).get("urls") or []
    if not urls:
        return ExportOutcome(success=False, format=export_format, error_code="EXPORT_NOT_READY",
                              error_message="Export did not finish in time — try again shortly")

    async with httpx.AsyncClient(timeout=30.0) as client:
        download = await client.get(urls[0])
    if download.status_code != 200:
        return ExportOutcome(success=False, format=export_format, error_code="EXPORT_DOWNLOAD_FAILED",
                              error_message=f"Could not download the exported file ({download.status_code})")

    mime_type = "image/png" if export_format == "png" else "application/pdf"
    return ExportOutcome(success=True, format=export_format, content_bytes=download.content, mime_type=mime_type)


async def upload_bytes_to_drive(
    db: Session, user_id: str, filename: str, content_bytes: bytes, mime_type: str,
    folder_id: Optional[str] = None,
) -> ConnectorActionResult:
    return await connector_service.execute_action(
        db, user_id, "google_drive", "google_drive.save_generated_file",
        {"filename": filename, "content_bytes_hex": content_bytes.hex(), "mime_type": mime_type,
         "folder_id": folder_id},
    )


async def get_export_bytes(db: Session, user_id: str, design_result: Any, export_format: str) -> ExportOutcome:
    """design_result is a design_orchestrator.DesignResult. Branches on
    whether it's Canva-backed (has a canva_design_id) or local_render_only
    (a base64 PNG data: URL and nothing else) — the latter can only produce
    a PNG, never a PDF, since no real design object exists to export."""
    if design_result.canva_design_id:
        return await export_canva_design(db, user_id, design_result.canva_design_id, export_format)

    if export_format != "png":
        return ExportOutcome(success=False, format=export_format, error_code="NOT_AVAILABLE",
                              error_message="PDF export isn't available for a locally rendered design (Canva not connected)")
    thumbnail_url = design_result.thumbnail_url or ""
    if not thumbnail_url.startswith("data:image/png;base64,"):
        return ExportOutcome(success=False, format=export_format, error_code="NO_LOCAL_IMAGE",
                              error_message="No local image available to upload")
    content_bytes = base64.b64decode(thumbnail_url.split(",", 1)[1])
    return ExportOutcome(success=True, format=export_format, content_bytes=content_bytes, mime_type="image/png")
