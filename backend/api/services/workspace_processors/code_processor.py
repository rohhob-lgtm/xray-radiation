"""Source/config code processor (PY/JS/TS/HTML/CSS/SQL/JSON/XML/YAML/...).

Files are only ever read as text for analysis — never executed, imported, or
passed to a shell. Secret-like values are redacted before the content is
assembled into any AI prompt (config/env-shaped files often carry secrets).
"""
from __future__ import annotations

from api.utils.secret_redaction import redact_secrets

from .base import make_result

_LANGUAGE_BY_EXT = {
    "py": "python", "js": "javascript", "jsx": "javascript",
    "ts": "typescript", "tsx": "typescript",
    "html": "html", "css": "css", "sql": "sql",
    "json": "json", "xml": "xml", "yaml": "yaml", "yml": "yaml",
    "ini": "ini", "toml": "toml", "log": "log",
}


def process_code(file_path: str, data: bytes, *, extension: str = "", filename: str = "") -> dict:
    warnings: list[str] = []
    errors: list[str] = []

    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as exc:
        errors.append(f"Failed to decode code/config file: {exc}")
        text = ""

    redacted_text, was_redacted = redact_secrets(text, filename=filename or file_path)
    if was_redacted:
        warnings.append(
            "One or more secret-like values in this file were redacted with [REDACTED] "
            "before being shown to the AI model."
        )

    lang = _LANGUAGE_BY_EXT.get(extension.lower().lstrip("."), "text")
    return make_result(
        file_path, "code",
        text=redacted_text,
        metadata={"language": lang, "char_count": len(text)},
        warnings=warnings, errors=errors,
    )
