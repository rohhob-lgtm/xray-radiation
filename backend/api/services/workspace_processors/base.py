"""Shared result-shape builder for all workspace file processors."""
from __future__ import annotations

from typing import Any, Optional


def make_result(
    file_path: str,
    file_type: str,
    *,
    text: str = "",
    metadata: Optional[dict] = None,
    tables: Optional[list] = None,
    images: Optional[list] = None,
    slides: Optional[list] = None,
    sheets: Optional[list] = None,
    warnings: Optional[list] = None,
    errors: Optional[list] = None,
) -> dict[str, Any]:
    return {
        "filePath": file_path,
        "fileType": file_type,
        "text": text,
        "metadata": metadata or {},
        "tables": tables or [],
        "images": images or [],
        "slides": slides or [],
        "sheets": sheets or [],
        "warnings": warnings or [],
        "errors": errors or [],
    }
