"""
Cross-platform document finalization dispatcher.

Chooses the layout-authority engine at runtime so the same call works on the
Windows workstation (Microsoft Office desktop COM) and on the Linux deployment
target (headless LibreOffice):

    engine order for every operation:
      1. Microsoft Office COM   — when on Windows with Word/PowerPoint available
      2. LibreOffice headless   — when Office COM is unavailable but LO is present
      3. neither → raise DocumentFinalizeError

Callers translate DocumentFinalizeError into their own surface: the export
routes into HTTP 503, the SSE pipeline into a "type: error" event. This keeps
the "no silent unfinalized bytes" guarantee while removing the hard Windows-only
dependency that blocked Linux deployment.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)


class DocumentFinalizeError(RuntimeError):
    """Raised when no finalization engine could produce a finalized document."""


# ── DOCX finalize ─────────────────────────────────────────────────────────────

def finalize_docx(content: bytes, target_lang: str) -> bytes:
    """Final layout pass for a translated DOCX (Word COM → LibreOffice → error)."""
    from api.utils.word_com_finalizer import (
        finalize_docx_with_word, word_com_available, WordAutomationError,
    )
    from api.utils.libreoffice_finalizer import (
        finalize_docx_with_libreoffice, libreoffice_available, LibreOfficeError,
    )

    if word_com_available():
        try:
            return finalize_docx_with_word(content, target_lang)
        except WordAutomationError as exc:
            if not libreoffice_available():
                raise DocumentFinalizeError(f"Microsoft Word desktop processing failed: {exc}") from exc
            log.warning("Word COM DOCX finalize failed; falling back to LibreOffice: %s", exc)

    if libreoffice_available():
        try:
            return finalize_docx_with_libreoffice(content, target_lang)
        except LibreOfficeError as exc:
            raise DocumentFinalizeError(f"LibreOffice document processing failed: {exc}") from exc

    raise DocumentFinalizeError(
        "No document finalization engine is available. Install Microsoft Word "
        "(Windows) or LibreOffice (set LIBREOFFICE_PATH), then retry."
    )


# ── PDF export ────────────────────────────────────────────────────────────────

def docx_to_pdf(content: bytes) -> bytes:
    """Export a DOCX to PDF (Word COM → LibreOffice → error)."""
    from api.utils.word_com_finalizer import (
        convert_docx_to_pdf_with_word, word_com_available, WordAutomationError,
    )
    from api.utils.libreoffice_finalizer import (
        convert_docx_to_pdf_with_libreoffice, libreoffice_available, LibreOfficeError,
    )

    if word_com_available():
        try:
            return convert_docx_to_pdf_with_word(content)
        except WordAutomationError as exc:
            if not libreoffice_available():
                raise DocumentFinalizeError(f"Microsoft Word PDF export failed: {exc}") from exc
            log.warning("Word COM DOCX->PDF failed; falling back to LibreOffice: %s", exc)

    if libreoffice_available():
        try:
            return convert_docx_to_pdf_with_libreoffice(content)
        except LibreOfficeError as exc:
            raise DocumentFinalizeError(f"LibreOffice PDF export failed: {exc}") from exc

    raise DocumentFinalizeError(
        "No PDF export engine is available. Install Microsoft Word (Windows) or "
        "LibreOffice (set LIBREOFFICE_PATH), then retry."
    )


def pptx_to_pdf(content: bytes) -> bytes:
    """Export a PPTX to PDF (PowerPoint COM → LibreOffice → error)."""
    from api.utils.powerpoint_com_finalizer import (
        convert_pptx_to_pdf_with_powerpoint, powerpoint_com_available, PowerPointAutomationError,
    )
    from api.utils.libreoffice_finalizer import (
        convert_pptx_to_pdf_with_libreoffice, libreoffice_available, LibreOfficeError,
    )

    if powerpoint_com_available():
        try:
            return convert_pptx_to_pdf_with_powerpoint(content)
        except PowerPointAutomationError as exc:
            if not libreoffice_available():
                raise DocumentFinalizeError(f"Microsoft PowerPoint PDF export failed: {exc}") from exc
            log.warning("PowerPoint COM PPTX->PDF failed; falling back to LibreOffice: %s", exc)

    if libreoffice_available():
        try:
            return convert_pptx_to_pdf_with_libreoffice(content)
        except LibreOfficeError as exc:
            raise DocumentFinalizeError(f"LibreOffice PDF export failed: {exc}") from exc

    raise DocumentFinalizeError(
        "No PDF export engine is available. Install Microsoft PowerPoint (Windows) "
        "or LibreOffice (set LIBREOFFICE_PATH), then retry."
    )
