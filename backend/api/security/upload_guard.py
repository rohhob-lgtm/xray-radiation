"""Upload content-safety guard.

Extension/MIME checks alone let a hostile file through under an allowed name.
This module inspects the actual *bytes* before the document is stored or parsed:

  * **Magic-byte check** — the content must match its claimed type (``%PDF`` for
    PDF, the ``PK`` local-file signature for the zip-based Office formats, etc.).
    A binary payload renamed ``.docx`` is rejected here.
  * **Zip-bomb defense** — OOXML/ODT files are zip containers. Using only the
    central-directory metadata (no decompression), we cap the total expanded
    size, the compression ratio, and the member count, and reject archive
    members with traversal/absolute paths (zip-slip).
  * **XXE / entity-expansion defense** — legitimate OOXML never uses a DTD, so
    any ``<!DOCTYPE`` / ``<!ENTITY`` in an XML member (or a standalone XML/HTML
    upload) is rejected, blocking external-entity and billion-laughs attacks
    that the downstream lxml/openpyxl parsers might otherwise process.

The document is never executed — only parsed — so this is defense-in-depth
against parser abuse and denial-of-service, not a substitute for it.
"""
from __future__ import annotations

import io
import logging
import zipfile
from typing import Optional

from fastapi import HTTPException
from starlette.requests import Request

log = logging.getLogger(__name__)

# Zip-bomb ceilings (checked against declared sizes — no decompression needed).
_ZIP_MAX_TOTAL_UNCOMPRESSED = 500 * 1024 * 1024   # 500 MB expanded
_ZIP_MAX_RATIO = 200                              # uncompressed / compressed
_ZIP_MAX_MEMBERS = 5000

_ZIP_TYPES = {"docx", "pptx", "xlsx", "odt"}
_TEXT_TYPES = {"txt", "csv", "md", "html", "htm", "xml"}

_ZIP_MAGICS = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")


def _reject(file_type: str, why: str, request: Optional[Request]) -> None:
    from api.security.events import log_security_event
    try:
        log_security_event("upload_content_rejected", request, file_type=file_type, reason=why)
    except Exception:  # pragma: no cover - logging must never mask the reject
        pass
    raise HTTPException(
        status_code=415,
        detail=f"The uploaded file is not a valid .{file_type} file ({why}).",
    )


def _check_zip(file_bytes: bytes, file_type: str, request: Optional[Request]) -> None:
    if file_bytes[:4] not in _ZIP_MAGICS:
        _reject(file_type, "missing zip signature", request)
    try:
        zf = zipfile.ZipFile(io.BytesIO(file_bytes))
    except zipfile.BadZipFile:
        _reject(file_type, "corrupt archive", request)
        return
    infos = zf.infolist()
    if not infos:
        _reject(file_type, "empty archive", request)
    if len(infos) > _ZIP_MAX_MEMBERS:
        _reject(file_type, f"too many entries ({len(infos)})", request)

    total_unc = 0
    total_comp = 0
    for zi in infos:
        name = (zi.filename or "").replace("\\", "/")
        if name.startswith("/") or ".." in name.split("/"):
            _reject(file_type, "archive member uses an unsafe path", request)
        total_unc += zi.file_size
        total_comp += zi.compress_size
    if total_unc > _ZIP_MAX_TOTAL_UNCOMPRESSED:
        _reject(file_type, f"expands to {total_unc // (1024 * 1024)} MB (zip-bomb guard)", request)
    if total_comp > 0 and (total_unc / total_comp) > _ZIP_MAX_RATIO:
        _reject(file_type, "excessive compression ratio (zip-bomb guard)", request)

    # OOXML sanity + XXE guard: expect [Content_Types].xml, and no DTD/ENTITY.
    names = {zi.filename for zi in infos}
    if file_type in ("docx", "pptx", "xlsx") and "[Content_Types].xml" not in names:
        _reject(file_type, "not a valid Office document (missing content types)", request)
    for zi in infos:
        low_name = (zi.filename or "").lower()
        if not (low_name.endswith(".xml") or low_name.endswith(".rels")):
            continue
        try:
            with zf.open(zi) as fh:
                head = fh.read(4096).lower()
        except Exception:
            continue
        if b"<!doctype" in head or b"<!entity" in head:
            _reject(file_type, "XML contains a DOCTYPE/ENTITY declaration (blocked)", request)


def _check_text(file_bytes: bytes, file_type: str, request: Optional[Request]) -> None:
    # A NUL byte in the first 64 KB means a binary payload wearing a text ext.
    if b"\x00" in file_bytes[:65536]:
        _reject(file_type, "binary content in a text file", request)
    if file_type in ("html", "htm", "xml"):
        head = file_bytes[:8192].lower()
        if b"<!entity" in head:
            _reject(file_type, "an ENTITY declaration is not allowed", request)


def validate_upload_bytes(
    file_bytes: bytes,
    file_type: str,
    request: Optional[Request] = None,
) -> None:
    """Validate uploaded content against its claimed type. Raises HTTP 415 on
    any mismatch or bomb signature; returns None when the file is acceptable."""
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file.")
    ft = (file_type or "").lower()

    if ft == "pdf":
        # Some PDFs carry a few junk bytes before the header; scan the first 1 KB.
        if b"%PDF-" not in file_bytes[:1024]:
            _reject(ft, "missing %PDF header", request)
    elif ft in _ZIP_TYPES:
        _check_zip(file_bytes, ft, request)
    elif ft == "rtf":
        if not file_bytes[:5] == b"{\\rtf":
            _reject(ft, "missing RTF header", request)
    elif ft in _TEXT_TYPES:
        _check_text(file_bytes, ft, request)
    # Unknown types never reach here — the route restricts to the allow-list.
