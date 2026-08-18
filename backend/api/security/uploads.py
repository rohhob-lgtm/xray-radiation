"""File-upload allow-listing: extension + MIME type + size + magic bytes.

Central chokepoint for every multipart upload. A file is accepted only if all
of the following hold:

  1. its extension is on the allow-list for the requested category,
  2. its declared Content-Type (if any) is on the allow-list,
  3. its size is within the configured ceiling,
  4. its leading magic bytes are consistent with the extension (so a
     ``.pdf`` that is really an executable, or a polyglot, is rejected).

Rejections raise ``fastapi.HTTPException`` (415/413/400) and are logged as
security events. Text-like formats (txt/csv/md/json/…) have no reliable magic
signature; for those we require the bytes to decode as UTF-8/Latin-1 text and
reject anything containing NUL bytes (a strong binary indicator).
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional

from fastapi import HTTPException
from starlette.requests import Request

from api.config import settings
from .events import log_security_event

# ── Allow-lists ─────────────────────────────────────────────────────────────
# extension -> set of acceptable declared MIME types (empty set == skip MIME
# check for that extension, used for formats browsers label inconsistently).
_ALLOWED: dict[str, set[str]] = {
    # Documents
    ".pdf": {"application/pdf"},
    ".doc": {"application/msword"},
    ".docx": {
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/zip",
    },
    ".ppt": {"application/vnd.ms-powerpoint"},
    ".pptx": {
        "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "application/zip",
    },
    ".xls": {"application/vnd.ms-excel"},
    ".xlsx": {
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "application/zip",
    },
    # Text / data
    ".txt": {"text/plain"},
    ".md": {"text/plain", "text/markdown"},
    ".csv": {"text/csv", "application/csv", "text/plain"},
    ".json": {"application/json", "text/plain"},
    ".yaml": {"text/plain", "application/x-yaml", "application/yaml"},
    ".yml": {"text/plain", "application/x-yaml", "application/yaml"},
    ".html": {"text/html", "text/plain"},
    ".htm": {"text/html", "text/plain"},
    ".xml": {"application/xml", "text/xml", "text/plain"},
    ".srt": {"text/plain"},
    ".vtt": {"text/plain", "text/vtt"},
    # Images
    ".png": {"image/png"},
    ".jpg": {"image/jpeg"},
    ".jpeg": {"image/jpeg"},
    ".gif": {"image/gif"},
    ".webp": {"image/webp"},
    ".bmp": {"image/bmp"},
    ".tif": {"image/tiff"},
    ".tiff": {"image/tiff"},
    # Archives
    ".zip": {"application/zip", "application/x-zip-compressed"},
}

# Named categories: which extensions each upload endpoint should accept.
CATEGORIES: dict[str, set[str]] = {
    "document": {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx",
                 ".txt", ".md", ".csv", ".rtf"},
    "image": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tif", ".tiff"},
    "data": {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".xml"},
    "spreadsheet": {".xls", ".xlsx", ".csv"},
    "archive": {".zip"},
    # "any" == the whole allow-list (still excludes executables/scripts).
    "any": set(_ALLOWED.keys()),
}

# Magic-byte signatures keyed by extension. A tuple of acceptable prefixes.
_MAGIC: dict[str, tuple[bytes, ...]] = {
    ".pdf": (b"%PDF-",),
    ".png": (b"\x89PNG\r\n\x1a\n",),
    ".jpg": (b"\xff\xd8\xff",),
    ".jpeg": (b"\xff\xd8\xff",),
    ".gif": (b"GIF87a", b"GIF89a"),
    ".bmp": (b"BM",),
    ".tif": (b"II*\x00", b"MM\x00*"),
    ".tiff": (b"II*\x00", b"MM\x00*"),
    # OOXML + zip share the ZIP local-file-header magic.
    ".docx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".pptx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".xlsx": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ".zip": (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
}

# Extensions whose content is text — validated by decodability, not magic.
_TEXT_EXTS = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".html",
              ".htm", ".xml", ".srt", ".vtt", ".doc", ".ppt", ".xls", ".rtf",
              ".webp"}


def _max_bytes(explicit: Optional[int]) -> int:
    if explicit is not None:
        return explicit
    return int(settings.max_upload_size_mb) * 1024 * 1024


def _looks_like_text(data: bytes) -> bool:
    if b"\x00" in data[:8192]:
        return False
    try:
        data[:8192].decode("utf-8")
        return True
    except UnicodeDecodeError:
        try:
            data[:8192].decode("latin-1")
            return True
        except UnicodeDecodeError:
            return False


def validate_upload(
    filename: Optional[str],
    data: bytes,
    *,
    declared_content_type: Optional[str] = None,
    category: str = "any",
    max_size: Optional[int] = None,
    allowed_extensions: Optional[Iterable[str]] = None,
    request: Optional[Request] = None,
) -> str:
    """Validate an uploaded file. Returns the normalized (lower-cased) extension.

    Raises ``HTTPException`` (400 empty/missing, 413 too large, 415 disallowed
    type / content mismatch) on any failure.
    """
    name = (filename or "").strip()
    if not name:
        _reject(request, "missing_filename", 400, "A filename is required.", filename)

    ext = Path(name).suffix.lower()
    allowed = (
        {e.lower() for e in allowed_extensions}
        if allowed_extensions is not None
        else CATEGORIES.get(category, CATEGORIES["any"])
    )

    if ext not in allowed or ext not in _ALLOWED:
        _reject(
            request, "upload_rejected", 415,
            f"File type '{ext or '(none)'}' is not allowed.",
            name, ext=ext, category=category,
        )

    if not data:
        _reject(request, "upload_empty", 400, "Uploaded file is empty.", name)

    ceiling = _max_bytes(max_size)
    if len(data) > ceiling:
        _reject(
            request, "upload_too_large", 413,
            f"File too large (max {ceiling // (1024 * 1024)} MB).",
            name, size=len(data),
        )

    # Declared MIME type (from the multipart part) — checked when both a value
    # is present and we have an allow-list for the extension.
    allowed_mimes = _ALLOWED.get(ext, set())
    if declared_content_type and allowed_mimes:
        mime = declared_content_type.split(";")[0].strip().lower()
        if mime and mime not in allowed_mimes and mime != "application/octet-stream":
            _reject(
                request, "upload_mime_mismatch", 415,
                f"Declared content type '{mime}' does not match '{ext}'.",
                name, ext=ext, mime=mime,
            )

    # Content sniffing.
    signatures = _MAGIC.get(ext)
    if signatures:
        if not any(data.startswith(sig) for sig in signatures):
            _reject(
                request, "upload_content_mismatch", 415,
                f"File content does not match its '{ext}' extension.",
                name, ext=ext,
            )
    elif ext in _TEXT_EXTS:
        if not _looks_like_text(data):
            _reject(
                request, "upload_content_mismatch", 415,
                f"File does not appear to be valid '{ext}' text.",
                name, ext=ext,
            )

    return ext


def _reject(request, event, status, detail, filename, **details):
    log_security_event(event, request, filename=filename, **details)
    raise HTTPException(status_code=status, detail=detail)
