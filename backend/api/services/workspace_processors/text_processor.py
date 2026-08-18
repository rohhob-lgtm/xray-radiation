"""Plain-text processor (TXT/MD/RTF/LOG/INI/TOML/env-example) with secret redaction."""
from __future__ import annotations

from api.utils.secret_redaction import redact_secrets

from .base import make_result


def process_text(file_path: str, data: bytes, *, filename: str = "") -> dict:
    warnings: list[str] = []
    errors: list[str] = []

    try:
        text = data.decode("utf-8", errors="replace")
    except Exception as exc:
        errors.append(f"Failed to decode text file: {exc}")
        text = ""

    redacted_text, was_redacted = redact_secrets(text, filename=filename or file_path)
    if was_redacted:
        warnings.append(
            "One or more secret-like values in this file were redacted with [REDACTED] "
            "before being shown to the AI model."
        )

    return make_result(
        file_path, "text",
        text=redacted_text,
        metadata={"char_count": len(text)},
        warnings=warnings, errors=errors,
    )
