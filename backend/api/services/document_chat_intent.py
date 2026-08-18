"""
Document-generation intent detection for AI Chat — mirrors canva_chat_intent's
keyword-pattern approach (no extra LLM call) so a plain-chat request like
"Create an empty Word document." is recognized as a request for a real
downloadable file, not answered by the bare LLM.

Deliberately narrow: only imperative "create/generate/make ... a Word/Excel/
PowerPoint/PDF/CSV document" phrasing matches. Questions ("How do I create a
Word document?", "What is a DOCX file?") and requests for pasteable text
("Write text that I can paste into Word.") must not match — see
detect_document_generation_intent's docstring.
"""
from __future__ import annotations

import re

_QUESTION_RE = re.compile(
    r"^\s*(how\s+(do|can|would)\b|what(\'s|\s+is)\b|why\b|explain\b|can\s+you\s+explain\b|"
    r"كيف\b|ما\s+هو\b|ما\s+هي\b)",
    re.IGNORECASE,
)

_DOC_NOUN_RE = re.compile(
    r"(\bword\s+docs?\b|\bword\s+documents?\b|\bword\s+files?\b|\.docx\b|\bdocx\s+files?\b|"
    r"\bexcel\s+(?:workbooks?|spreadsheets?|files?)\b|\.xlsx\b|"
    r"\b(?:power\s*point|ppt)\s+(?:presentations?|slides?|files?)\b|\.pptx\b|"
    r"\bpdf\s+reports?\b|\bcsv\s+files?\b|"
    r"مستند\s*وورد|ملف\s*وورد|ملف\s*ورد|مستند\s*ورد)",
    re.IGNORECASE,
)

_CREATE_VERB_RE = re.compile(
    r"\b(create|generate|make|produce|build|draft|prepare)\b|"
    r"ولّد|ولد|أنشئ|انشئ|اصنع|جهز",
    re.IGNORECASE,
)


def detect_document_generation_intent(message: str) -> bool:
    """True when `message` is an imperative request to generate a real,
    downloadable office document — the same request family the Workspace
    Agent's create_word_document / create_excel_workbook / create_powerpoint
    / create_pdf_report / create_csv tools already handle. False for
    questions and requests for text to paste manually."""
    if not message:
        return False
    if _QUESTION_RE.search(message):
        return False
    if not _DOC_NOUN_RE.search(message):
        return False
    return bool(_CREATE_VERB_RE.search(message))


# ── AI Chat responsiveness — lightweight Intent Router ──────────────────────
# A conversation that ever touched a workspace (e.g. one earlier "translate
# this file" request) keeps carrying that workspace_id on every later turn
# (see api.routes.chat.py's _stream_workspace_turn, which links it to the
# conversation the first time it runs). Without this check, an unrelated
# follow-up like "what can you do?" would still pay for the full Workspace
# Agent pipeline (list_workspace_files, a tool-calling LLM round-trip, the
# zero-call corrective retry) before answering. Same deliberately-keyword-only
# philosophy as detect_document_generation_intent/detect_design_intent/
# detect_canva_intent above — this router itself must add ~0ms, or it
# defeats its own purpose.
_FILE_REFERENCE_RE = re.compile(
    r"\b(files?|documents?|docs?|folder|workspace|spreadsheets?|attachments?|"
    r"attached|uploaded?|the\s+pdf|this\s+file|these\s+files|the\s+file|"
    r"the\s+document|this\s+document|my\s+files?|my\s+documents?|my\s+upload)\b|"
    r"\.docx\b|\.xlsx\b|\.pptx\b|\.pdf\b|\.csv\b|"
    r"ملفات?|مستندات?|مجلد|المرفق|الملف\s+المرفق|رفعت(?:ه|ها)?",
    re.IGNORECASE,
)

_FILE_ACTION_RE = re.compile(
    r"\b(read|open|inspect|analyz[e]?|analys[e]?|summariz[e]?|summaris[e]?|extract|"
    r"translate|convert|compare|review|list\s+files|search\s+the\s+workspace|"
    r"search\s+my\s+files|what.?s\s+in\s+(?:the|this|my))\b|"
    r"لخص|حلل|استخرج|ترجم|افتح|اقرأ|راجع|قارن",
    re.IGNORECASE,
)


def detect_workspace_task_intent(message: str) -> bool:
    """True when `message` plausibly needs the Workspace Agent's file
    inspection / tool-calling pipeline — False for ordinary conversation,
    even on a turn whose conversation happens to carry a workspace_id from
    an earlier, unrelated request. A false negative here just means an
    actual file request gets answered without file context (rare, since the
    keyword lists are intentionally broad); a false positive just means one
    extra pipeline is used for a message that didn't strictly need it —
    both fail safe, unlike silently answering with fabricated file content."""
    if not message:
        return False
    if detect_document_generation_intent(message):
        return True
    return bool(_FILE_REFERENCE_RE.search(message) or _FILE_ACTION_RE.search(message))
