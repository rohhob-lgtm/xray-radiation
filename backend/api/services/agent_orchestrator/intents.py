"""Intent taxonomy + the one new deterministic detector this session adds.

Detection here is deliberately keyword/regex-based, matching every existing
intent detector in this codebase (canva_chat_intent.detect_canva_intent,
design_content.detect_design_intent, gallery_service.detect_intent) — no new
per-message classifier LLM call is introduced.
"""
from __future__ import annotations

import re


class IntentType:
    GENERAL_CHAT = "general_chat"
    RESEARCH = "research"
    TRANSLATION = "translation"
    COURSE_GENERATION = "course_generation"
    TECHNICAL_REPORT = "technical_report"
    VISUAL_DESIGN = "visual_design"
    IMAGE_GENERATION = "image_generation"
    DOCUMENT_GENERATION = "document_generation"
    FILE_SEARCH = "file_search"
    FILE_IMPORT = "file_import"
    FILE_EXPORT = "file_export"
    SAVE_TO_DRIVE = "save_to_drive"
    CANVA_EDITING = "canva_editing"
    XRAY_ANALYSIS = "xray_analysis"

    ALL = (
        GENERAL_CHAT, RESEARCH, TRANSLATION, COURSE_GENERATION, TECHNICAL_REPORT,
        VISUAL_DESIGN, IMAGE_GENERATION, DOCUMENT_GENERATION, FILE_SEARCH,
        FILE_IMPORT, FILE_EXPORT, SAVE_TO_DRIVE, CANVA_EDITING, XRAY_ANALYSIS,
    )


_DRIVE_SAVE_RE = re.compile(
    r"\b(save|upload|export|send)\b.{0,40}\b(to|on|into)\b.{0,20}\b(my\s+)?(google\s+)?drive\b"
    r"|drive\b.{0,20}\b(save|upload)"
    r"|احفظ.{0,20}درايف|درايف.{0,20}احفظ",
    re.IGNORECASE,
)


def wants_drive_save(message: str) -> bool:
    """True if the message explicitly asks to save/upload the result to
    Google Drive — used to combine a design request with an automatic Drive
    upload in the same turn, instead of requiring a separate manual click."""
    if not message:
        return False
    return bool(_DRIVE_SAVE_RE.search(message))
