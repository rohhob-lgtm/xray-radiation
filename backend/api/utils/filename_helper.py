"""
Centralized translated-file naming helpers.

Every download route must call ``build_translated_filename`` and
``content_disposition`` instead of constructing filenames ad-hoc.

Rule:  {OriginalBaseName} ({TargetLanguageName}){OriginalExtension}

Examples
--------
    build_translated_filename("G60 ZBx OP Introduction.pptx", "Arabic")
    → "G60 ZBx OP Introduction (Arabic).pptx"

    build_translated_filename("Manual (Arabic).pdf", "Arabic")
    → "Manual (Arabic).pdf"          # no duplicate suffix

    build_translated_filename("training.manual.v2.pdf", "French")
    → "training.manual.v2 (French).pdf"   # only last dot is the extension

    build_translated_filename("دليل تشغيل الجهاز.pdf", "English")
    → "دليل تشغيل الجهاز (English).pdf"
"""

from __future__ import annotations

import unicodedata
from urllib.parse import quote

# ── Language code → display name ──────────────────────────────────────────────
# Extend whenever a new target language is added to the translation UI.
LANG_NAMES: dict[str, str] = {
    "en": "English",
    "ar": "Arabic",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "zh": "Chinese",
    "ja": "Japanese",
    "ru": "Russian",
    "tr": "Turkish",
    "pt": "Portuguese",
    "it": "Italian",
    "nl": "Dutch",
    "ko": "Korean",
    "pl": "Polish",
    "sv": "Swedish",
    "da": "Danish",
    "fi": "Finnish",
    "nb": "Norwegian",
    "cs": "Czech",
    "hu": "Hungarian",
    "ro": "Romanian",
    "uk": "Ukrainian",
    "vi": "Vietnamese",
    "th": "Thai",
    "id": "Indonesian",
    "ms": "Malay",
    "he": "Hebrew",
    "fa": "Persian",
    "ur": "Urdu",
}

# ── MIME types ────────────────────────────────────────────────────────────────
_MIME: dict[str, str] = {
    "pptx":  "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "ppt":   "application/vnd.ms-powerpoint",
    "docx":  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "doc":   "application/msword",
    "xlsx":  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "xls":   "application/vnd.ms-excel",
    "pdf":   "application/pdf",
    "txt":   "text/plain; charset=utf-8",
    "csv":   "text/csv; charset=utf-8",
    "rtf":   "application/rtf",
    "html":  "text/html; charset=utf-8",
    "htm":   "text/html; charset=utf-8",
    "png":   "image/png",
    "jpg":   "image/jpeg",
    "jpeg":  "image/jpeg",
    "tiff":  "image/tiff",
    "tif":   "image/tiff",
    "gif":   "image/gif",
    "webp":  "image/webp",
    "zip":   "application/zip",
    "json":  "application/json",
    "xml":   "application/xml",
}


def lang_display_name(lang_code: str) -> str:
    """Return the display name for a BCP-47 language code.

    Falls back to the uppercased code if unknown so nothing ever crashes.
    """
    return LANG_NAMES.get(lang_code.lower().split("-")[0], lang_code.upper())


def build_translated_filename(
    original_filename: str,
    target_language_name: str,
) -> str:
    """Return the translated download filename.

    Parameters
    ----------
    original_filename:
        The *exact* filename as uploaded by the user, including extension.
        May be empty or None — a safe fallback is used.
    target_language_name:
        Display name of the target language, e.g. ``"Arabic"``.

    Returns
    -------
    str
        e.g. ``"G60 ZBx OP Introduction (Arabic).pptx"``
    """
    fallback = "file"
    safe_original = (original_filename or "").strip() or fallback

    # Split at the *last* dot so multi-dot names work correctly.
    last_dot = safe_original.rfind(".")
    has_ext = 0 < last_dot < len(safe_original) - 1

    base = safe_original[:last_dot] if has_ext else safe_original
    ext  = safe_original[last_dot:] if has_ext else ""   # includes the dot

    # Avoid duplicate language suffix if it already exists.
    suffix = f" ({target_language_name})"
    if base.lower().endswith(suffix.lower()):
        translated_base = base
    else:
        translated_base = f"{base}{suffix}"

    return f"{translated_base}{ext}"


def build_translated_filename_from_code(
    original_filename: str,
    target_lang_code: str,
) -> str:
    """Convenience wrapper that accepts a BCP-47 language code."""
    return build_translated_filename(
        original_filename,
        lang_display_name(target_lang_code),
    )


def _ascii_fallback(filename: str) -> str:
    """Return an ASCII-safe version of *filename* for the plain ``filename=`` field.

    Non-ASCII characters are replaced with ``_``.  This is only used inside
    the quoted ``filename="..."`` token; the real name is in ``filename*=``.
    """
    normalized = unicodedata.normalize("NFKD", filename)
    ascii_chars = []
    for ch in normalized:
        if ord(ch) < 128:
            ascii_chars.append(ch)
        else:
            # Replace non-ASCII with underscore but avoid consecutive underscores
            if ascii_chars and ascii_chars[-1] != "_":
                ascii_chars.append("_")
    result = "".join(ascii_chars).strip("_") or "file"
    # Double-quotes inside filename= would break the header — strip them.
    return result.replace('"', "_").replace("\n", "_").replace("\r", "_")


def content_disposition(filename: str) -> str:
    """Build a ``Content-Disposition`` header value with RFC 5987 UTF-8 support.

    The returned string is used directly as the header value, e.g.::

        headers={"Content-Disposition": content_disposition(translated_name)}

    It produces both ``filename="..."`` (for legacy clients) and
    ``filename*=UTF-8''...`` (RFC 5987, preferred by modern browsers and used
    for non-ASCII filenames).
    """
    ascii_name = _ascii_fallback(filename)
    utf8_encoded = quote(filename, safe=" -_.~()[]")  # preserve common safe chars
    return f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{utf8_encoded}'


def mime_for_ext(ext: str) -> str:
    """Return the MIME type for a file extension.

    The leading dot is optional.  Falls back to ``application/octet-stream``.
    """
    key = ext.lstrip(".").lower()
    return _MIME.get(key, "application/octet-stream")
