"""User-input validation and sanitization helpers.

Small, dependency-free utilities used by routes that accept free-form strings,
filenames, or identifiers. These complement (not replace) Pydantic model
validation: they neutralize the specific injection classes that type-checking
alone does not catch — path traversal in filenames, control characters in text,
and over-long inputs used for resource exhaustion.
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import PurePosixPath, PureWindowsPath

from fastapi import HTTPException

# Control characters except tab/newline/carriage-return.
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Characters unsafe in a filesystem name.
_UNSAFE_NAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,128}$")


def sanitize_text(
    value: str,
    *,
    max_length: int = 100_000,
    strip: bool = True,
    field: str = "input",
) -> str:
    """Remove control characters and enforce a length ceiling.

    Raises ``HTTPException(422)`` if the value exceeds ``max_length`` so an
    attacker cannot force megabytes of text through a field that expects a
    sentence.
    """
    if value is None:
        return ""
    text = unicodedata.normalize("NFC", str(value))
    text = _CONTROL_RE.sub("", text)
    if strip:
        text = text.strip()
    if len(text) > max_length:
        raise HTTPException(
            status_code=422,
            detail=f"'{field}' exceeds the maximum length of {max_length} characters.",
        )
    return text


def sanitize_filename(filename: str, *, default: str = "upload", max_length: int = 255) -> str:
    """Return a safe basename with no path components.

    Strips any directory portion (defends against ``../`` traversal and
    absolute paths on both POSIX and Windows), removes filesystem-unsafe
    characters, and caps the length. Never returns an empty string.
    """
    if not filename:
        return default
    # Take the basename under both path flavours so a Windows-style path sent to
    # a POSIX host (or vice-versa) can't smuggle a directory component.
    base = PurePosixPath(PureWindowsPath(filename).name).name
    base = _UNSAFE_NAME_RE.sub("_", base).strip(". ")
    if not base or base in {".", ".."}:
        return default
    if len(base) > max_length:
        stem, _, ext = base.rpartition(".")
        if ext and len(ext) < 20:
            base = stem[: max_length - len(ext) - 1] + "." + ext
        else:
            base = base[:max_length]
    return base or default


def validate_identifier(value: str, *, field: str = "id") -> str:
    """Validate an opaque identifier (UUID, slug, provider name, …).

    Allows only ``[A-Za-z0-9_.-]`` up to 128 chars — enough for UUIDs and slugs,
    tight enough to block SQL/NoSQL/path payloads. Raises ``HTTPException(422)``.
    """
    if not value or not _ID_RE.match(value):
        raise HTTPException(status_code=422, detail=f"Invalid '{field}'.")
    return value
