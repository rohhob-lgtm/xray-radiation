"""Image processor — Pillow metadata only. No OCR is run automatically (opt-in,
best-effort; see agent tool layer for on-demand Gemini vision analysis)."""
from __future__ import annotations

import io

from .base import make_result


def process_image(file_path: str, data: bytes) -> dict:
    warnings: list[str] = []
    errors: list[str] = []
    metadata: dict = {}

    try:
        from PIL import Image

        img = Image.open(io.BytesIO(data))
        metadata = {"width": img.width, "height": img.height, "format": img.format}
    except Exception as exc:
        errors.append(f"Failed to read image: {exc}")

    warnings.append(
        "No OCR or automatic vision analysis was run on this image — ask the assistant "
        "to describe/analyze it if you need that."
    )
    return make_result(
        file_path, "image",
        metadata=metadata,
        images=[{"path": file_path}],
        warnings=warnings, errors=errors,
    )
