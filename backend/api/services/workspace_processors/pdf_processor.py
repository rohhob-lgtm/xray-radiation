"""PDF processor — PyMuPDF text extraction, per-page, non-fatal on scanned pages."""
from __future__ import annotations

from .base import make_result


def process_pdf(file_path: str, data: bytes) -> dict:
    warnings: list[str] = []
    errors: list[str] = []
    text_parts: list[str] = []
    page_count = 0

    try:
        import fitz  # PyMuPDF

        doc = fitz.open(stream=data, filetype="pdf")
        page_count = len(doc)
        empty_pages: list[int] = []
        for i in range(page_count):
            page_text = (doc[i].get_text("text") or "").strip()
            if page_text:
                text_parts.append(f"[Page {i + 1}]\n{page_text}")
            else:
                empty_pages.append(i + 1)
        doc.close()

        if empty_pages:
            shown = empty_pages[:20]
            more = "..." if len(empty_pages) > 20 else ""
            warnings.append(
                f"{len(empty_pages)} page(s) had no extractable text layer (likely scanned "
                f"images): pages {shown}{more}. OCR is not enabled in this deployment, so "
                "these pages were skipped rather than failing the whole file."
            )
    except Exception as exc:
        errors.append(f"Failed to read PDF: {exc}")

    return make_result(
        file_path, "pdf",
        text="\n\n".join(text_parts),
        metadata={"page_count": page_count},
        warnings=warnings, errors=errors,
    )
