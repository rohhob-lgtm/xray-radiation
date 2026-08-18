"""Agent tool layer for the AI Chat Workspace.

Every tool only ever touches paths under the active workspace's own storage
directory (via ``api.utils.workspace_storage``) — this is the "no
unrestricted OS access" boundary the model operates inside. Tool schemas use
the OpenAI ``tools=`` JSON-schema shape, which Gemini's OpenAI-compatibility
endpoint also accepts (see ``GeminiProvider.chat_with_tools``).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.config import settings
from api.db import crud
from api.db.models import Workspace, WorkspaceFile
from api.languages import is_rtl_lang
from api.utils import filename_helper, workspace_storage
from api.utils.rate_limiter import acquire_slot
from api.utils.secret_redaction import redact_secrets
from api.utils.translator import LANG_NAMES

from ..workspace_processors.registry import process_file
from . import doc_builder, pptx_builder
from .xlsx_builder import build_workbook, build_csv_bytes, WorkbookValidationError

log = logging.getLogger(__name__)

_MAX_TEXT_RETURN_CHARS = 12000
_MAX_SEARCH_SNIPPET_CHARS = 400


@dataclass
class WorkspaceToolContext:
    db: Session
    workspace: Workspace
    provider: Any = None  # active AI provider (for translate_text)
    model_name: str = ""


class ToolError(RuntimeError):
    pass


# ──────────────────────────────────────────────────────────
# Tool schemas (OpenAI-style function definitions)
# ──────────────────────────────────────────────────────────

TOOL_SCHEMAS: list[dict] = [
    {"type": "function", "function": {
        "name": "list_workspace_files",
        "description": "List every file in the active workspace with its id, relative path, size, and processing status.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_workspace_tree",
        "description": "Get the workspace's folder/file structure as a nested tree.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read the extracted text of one workspace file by id (truncated if very large — use read_file_range for more).",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"},
        }, "required": ["file_id"]},
    }},
    {"type": "function", "function": {
        "name": "read_file_range",
        "description": "Read a character range of one workspace file's extracted text.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"},
            "start_char": {"type": "integer"},
            "end_char": {"type": "integer"},
        }, "required": ["file_id", "start_char", "end_char"]},
    }},
    {"type": "function", "function": {
        "name": "search_workspace",
        "description": "Hybrid keyword+semantic search across all indexed workspace files. Use this instead of reading every file when looking for something specific.",
        "parameters": {"type": "object", "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer", "description": "Default 10, max 50"},
        }, "required": ["query"]},
    }},
    {"type": "function", "function": {
        "name": "refresh_workspace_index",
        "description": "Force an immediate refresh of the workspace's semantic search index (e.g. if search_workspace seems to be returning stale results). Only re-embeds files that actually changed.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
    {"type": "function", "function": {
        "name": "get_file_metadata",
        "description": "Get metadata (size, mime type, parse status, warnings/errors) for one workspace file.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"},
        }, "required": ["file_id"]},
    }},
    {"type": "function", "function": {
        "name": "extract_document_text",
        "description": "Extract the full plain text of a document file (PDF/DOCX/PPTX/TXT/code). Same as read_file but explicit about intent.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"},
        }, "required": ["file_id"]},
    }},
    {"type": "function", "function": {
        "name": "extract_tables",
        "description": "Extract structured tables from a DOCX, XLSX, or CSV file.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"},
        }, "required": ["file_id"]},
    }},
    {"type": "function", "function": {
        "name": "inspect_excel_workbook",
        "description": "Inspect an Excel file's sheet names, dimensions, and a preview of each sheet's rows.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"},
        }, "required": ["file_id"]},
    }},
    {"type": "function", "function": {
        "name": "inspect_powerpoint",
        "description": "Inspect a PowerPoint file's slide count, per-slide text, and speaker notes.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"},
        }, "required": ["file_id"]},
    }},
    {"type": "function", "function": {
        "name": "inspect_word_document",
        "description": "Inspect a Word document's paragraphs, headings, and tables.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"},
        }, "required": ["file_id"]},
    }},
    {"type": "function", "function": {
        "name": "translate_text",
        "description": "Translate a short piece of text. For translating a whole file, use translate_document instead.",
        "parameters": {"type": "object", "properties": {
            "text": {"type": "string"},
            "target_lang": {"type": "string", "description": "BCP-47 code, e.g. 'ar', 'fr', 'de', 'es', 'en'"},
            "source_lang": {"type": "string", "description": "Optional; defaults to auto-detect"},
        }, "required": ["text", "target_lang"]},
    }},
    {"type": "function", "function": {
        "name": "translate_document",
        "description": "Translate an entire DOCX/PPTX/XLSX/PDF/TXT workspace file into another language, preserving formatting where possible, and register the result as a downloadable generated file.",
        "parameters": {"type": "object", "properties": {
            "file_id": {"type": "string"},
            "target_lang": {"type": "string", "description": "BCP-47 code, e.g. 'ar', 'fr', 'de', 'es'"},
            "source_lang": {"type": "string", "description": "Default 'en'"},
        }, "required": ["file_id", "target_lang"]},
    }},
    {"type": "function", "function": {
        "name": "create_excel_workbook",
        "description": "Create a downloadable multi-sheet Excel workbook (.xlsx) with headers, autofilter, frozen header row, and a summary sheet.",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string"},
            "sheets": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "name": {"type": "string"},
                    "headers": {"type": "array", "items": {"type": "string"}},
                    "rows": {"type": "array", "items": {"type": "array"}},
                }, "required": ["name", "headers", "rows"]},
            },
        }, "required": ["filename", "sheets"]},
    }},
    {"type": "function", "function": {
        "name": "create_csv",
        "description": "Create a downloadable CSV file.",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string"},
            "headers": {"type": "array", "items": {"type": "string"}},
            "rows": {"type": "array", "items": {"type": "array"}},
        }, "required": ["filename", "headers", "rows"]},
    }},
    {"type": "function", "function": {
        "name": "create_word_document",
        "description": "Create a downloadable Word document (.docx) from a title and markdown body.",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string"},
            "title": {"type": "string"},
            "markdown_body": {"type": "string"},
            "lang": {"type": "string", "description": "'en' or 'ar', default 'en'"},
        }, "required": ["filename", "title", "markdown_body"]},
    }},
    {"type": "function", "function": {
        "name": "create_powerpoint",
        "description": "Create a downloadable PowerPoint training deck (.pptx) from a course title and slide outline.",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string"},
            "course_title": {"type": "string"},
            "slides_outline": {
                "type": "array",
                "items": {"type": "object", "properties": {
                    "title": {"type": "string"},
                    "bullets": {"type": "array", "items": {"type": "string"}},
                    "notes": {"type": "string"},
                }, "required": ["title", "bullets"]},
            },
        }, "required": ["filename", "course_title", "slides_outline"]},
    }},
    {"type": "function", "function": {
        "name": "create_pdf_report",
        "description": "Create a downloadable PDF report (.pdf) from a title and markdown body.",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string"},
            "title": {"type": "string"},
            "markdown_body": {"type": "string"},
            "lang": {"type": "string", "description": "'en' or 'ar', default 'en'"},
        }, "required": ["filename", "title", "markdown_body"]},
    }},
    {"type": "function", "function": {
        "name": "create_markdown_report",
        "description": "Create a downloadable Markdown (.md) report.",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string"},
            "title": {"type": "string"},
            "markdown_body": {"type": "string"},
        }, "required": ["filename", "markdown_body"]},
    }},
    {"type": "function", "function": {
        "name": "write_generated_file",
        "description": "Write a downloadable plain-text, JSON, TXT, or MD file with exact content you provide (use for formats not covered by the other create_* tools).",
        "parameters": {"type": "object", "properties": {
            "filename": {"type": "string"},
            "content": {"type": "string"},
            "format": {"type": "string", "description": "e.g. 'txt', 'json', 'md'"},
        }, "required": ["filename", "content", "format"]},
    }},
    {"type": "function", "function": {
        "name": "validate_generated_file",
        "description": "Re-check that a previously generated file is well-formed and non-empty.",
        "parameters": {"type": "object", "properties": {
            "generated_file_id": {"type": "string"},
        }, "required": ["generated_file_id"]},
    }},
    {"type": "function", "function": {
        "name": "list_generated_files",
        "description": "List every file generated so far in this workspace.",
        "parameters": {"type": "object", "properties": {}, "required": []},
    }},
]


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _get_file(ctx: WorkspaceToolContext, file_id: str) -> WorkspaceFile:
    wf = crud.get_workspace_file(ctx.db, file_id, ctx.workspace.id)
    if not wf:
        raise ToolError(f"No file with id '{file_id}' in this workspace.")
    return wf


def _truncate(text: str, limit: int = _MAX_TEXT_RETURN_CHARS) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit], True


def _read_bytes(wf: WorkspaceFile) -> bytes:
    return workspace_storage.read_file(wf.storage_path)


def _extracted_text(wf: WorkspaceFile) -> str:
    if wf.extracted_text_path:
        try:
            return workspace_storage.read_text_file(wf.extracted_text_path)
        except FileNotFoundError:
            pass
    return ""


def _register_generated(
    ctx: WorkspaceToolContext, filename: str, fmt: str, data: bytes, *, source_file_ids: Optional[list[str]] = None,
) -> dict:
    storage_path = workspace_storage.save_generated(ctx.workspace.user_id, ctx.workspace.id, filename, data)
    gf = crud.add_generated_file(
        ctx.db, ctx.workspace.id,
        filename=filename, format=fmt, storage_path=storage_path,
        size_bytes=len(data), source_file_ids=source_file_ids or [],
    )
    return crud.generated_file_to_dict(gf)


# ──────────────────────────────────────────────────────────
# Tool implementations
# ──────────────────────────────────────────────────────────

def _tool_list_workspace_files(ctx: WorkspaceToolContext, args: dict) -> dict:
    files = crud.list_workspace_files(ctx.db, ctx.workspace.id)
    return {"files": [
        {
            "id": f.id, "relative_path": f.relative_path, "extension": f.extension,
            "size_bytes": f.size_bytes, "parse_status": f.parse_status,
        }
        for f in files
    ]}


def _tool_get_workspace_tree(ctx: WorkspaceToolContext, args: dict) -> dict:
    files = crud.list_workspace_files(ctx.db, ctx.workspace.id)
    tree: dict = {}
    for f in files:
        parts = f.relative_path.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = {"id": f.id, "size_bytes": f.size_bytes, "parse_status": f.parse_status}
    return {"tree": tree}


def _tool_read_file(ctx: WorkspaceToolContext, args: dict) -> dict:
    wf = _get_file(ctx, args["file_id"])
    text = _extracted_text(wf)
    if not text:
        return {"file_id": wf.id, "text": "", "note": "No extracted text available for this file (unsupported type, processing error, or empty document)."}
    truncated_text, was_truncated = _truncate(text)
    return {"file_id": wf.id, "text": truncated_text, "truncated": was_truncated, "total_chars": len(text)}


def _tool_read_file_range(ctx: WorkspaceToolContext, args: dict) -> dict:
    wf = _get_file(ctx, args["file_id"])
    text = _extracted_text(wf)
    start = max(0, int(args.get("start_char", 0)))
    end = min(len(text), int(args.get("end_char", start + _MAX_TEXT_RETURN_CHARS)))
    return {"file_id": wf.id, "text": text[start:end], "start_char": start, "end_char": end, "total_chars": len(text)}


async def _tool_search_workspace(ctx: WorkspaceToolContext, args: dict) -> dict:
    """
    Hybrid Workspace Awareness search — uses the semantic+keyword index
    (api.services.workspace_index) instead of a raw substring scan, so
    results rank by relevance and cover content the literal query text
    doesn't appear in verbatim.
    """
    query = (args.get("query") or "").strip()
    if not query:
        raise ToolError("query is required")
    max_results = min(int(args.get("max_results", 10) or 10), 50)

    from api.services.workspace_index import ensure_fresh, search_workspace
    await ensure_fresh(ctx.db, ctx.workspace.id)
    hits = await search_workspace(ctx.db, ctx.workspace.id, query, top_k=max_results)

    results = []
    for hit in hits:
        resource_id = hit.meta.get("resource_id", "")
        wf = crud.get_workspace_file(ctx.db, resource_id, ctx.workspace.id) if resource_id else None
        results.append({
            "file_id": resource_id,
            "relative_path": wf.relative_path if wf else hit.title,
            "snippet": hit.content[:_MAX_SEARCH_SNIPPET_CHARS],
            "score": round(hit.score, 3),
        })
    return {"query": args.get("query"), "results": results, "result_count": len(results)}


async def _tool_refresh_workspace_index(ctx: WorkspaceToolContext, args: dict) -> dict:
    """Hybrid Workspace Awareness trigger #13 — explicit AI-requested refresh."""
    from api.services.workspace_index import reindex_dirty
    counts = await reindex_dirty(ctx.db, workspace_id=ctx.workspace.id, limit=200)
    return {"workspace_id": ctx.workspace.id, **counts}


def _tool_get_file_metadata(ctx: WorkspaceToolContext, args: dict) -> dict:
    wf = _get_file(ctx, args["file_id"])
    return crud.workspace_file_to_dict(wf)


def _tool_extract_document_text(ctx: WorkspaceToolContext, args: dict) -> dict:
    return _tool_read_file(ctx, args)


def _process_fresh(wf: WorkspaceFile) -> dict:
    data = _read_bytes(wf)
    return process_file(wf.relative_path, data, wf.extension, filename=wf.original_filename)


def _tool_extract_tables(ctx: WorkspaceToolContext, args: dict) -> dict:
    wf = _get_file(ctx, args["file_id"])
    result = _process_fresh(wf)
    return {"file_id": wf.id, "tables": result["tables"], "errors": result["errors"]}


def _tool_inspect_excel_workbook(ctx: WorkspaceToolContext, args: dict) -> dict:
    wf = _get_file(ctx, args["file_id"])
    if wf.extension.lower() not in ("xlsx", "xls"):
        raise ToolError("File is not an Excel workbook.")
    result = _process_fresh(wf)
    return {"file_id": wf.id, "sheets": result["sheets"], "metadata": result["metadata"], "errors": result["errors"]}


def _tool_inspect_powerpoint(ctx: WorkspaceToolContext, args: dict) -> dict:
    wf = _get_file(ctx, args["file_id"])
    if wf.extension.lower() != "pptx":
        raise ToolError("File is not a PowerPoint presentation.")
    result = _process_fresh(wf)
    return {"file_id": wf.id, "slides": result["slides"], "metadata": result["metadata"], "errors": result["errors"]}


def _tool_inspect_word_document(ctx: WorkspaceToolContext, args: dict) -> dict:
    wf = _get_file(ctx, args["file_id"])
    if wf.extension.lower() != "docx":
        raise ToolError("File is not a Word document.")
    result = _process_fresh(wf)
    return {"file_id": wf.id, "tables": result["tables"], "text_preview": result["text"][:2000], "metadata": result["metadata"], "errors": result["errors"]}


async def _tool_translate_text(ctx: WorkspaceToolContext, args: dict) -> dict:
    text = args.get("text", "")
    target_lang = args.get("target_lang", "")
    source_lang = args.get("source_lang", "auto")
    if not text or not target_lang:
        raise ToolError("text and target_lang are required")
    if ctx.provider is None or not hasattr(ctx.provider, "chat"):
        raise ToolError("No AI provider is configured to perform translation.")

    target_name = LANG_NAMES.get(target_lang, target_lang)
    system_prompt = (
        f"You are a professional technical translator. Translate the user's text into {target_name}. "
        "Preserve technical terms, model numbers, codes, and formatting. "
        "Return ONLY the translated text, nothing else."
    )
    await acquire_slot(ctx.model_name)
    translated = await ctx.provider.chat([{"role": "user", "content": text}], system_prompt=system_prompt)
    return {"source_text": text, "translated_text": translated.strip(), "target_lang": target_lang, "source_lang": source_lang}


async def _tool_translate_document(ctx: WorkspaceToolContext, args: dict) -> dict:
    wf = _get_file(ctx, args["file_id"])
    target_lang = args.get("target_lang", "")
    source_lang = args.get("source_lang", "en")
    if not target_lang:
        raise ToolError("target_lang is required")
    if ctx.provider is None or not hasattr(ctx.provider, "chat"):
        raise ToolError("No AI provider is configured to perform translation.")

    ext = wf.extension.lower()
    if ext not in ("docx", "pptx", "xlsx", "pdf", "txt", "md"):
        raise ToolError(f"Translating .{ext} files is not supported — supported: docx, pptx, xlsx, pdf, txt, md.")

    from api.utils.doc_extractor import extract_document
    from api.utils.doc_rebuilder import rebuild_document

    original_bytes = _read_bytes(wf)
    warnings: list[str] = []
    try:
        segments = extract_document(original_bytes, ext)
    except Exception as exc:
        raise ToolError(f"Could not extract translatable segments from this file: {exc}")

    if not segments:
        raise ToolError("No translatable text segments were found in this file.")

    # Some uploaded files are already partially in the target language —
    # e.g. a deck someone informally pre-translated before it reached this
    # tool. Sending that text back through the model with a hardcoded
    # "translate from {source_lang} to {target_name}" instruction produces
    # a contradiction (the model is being told the Arabic text in front of
    # it is English), and its behavior on that contradiction is
    # inconsistent: some segments come back as cleaned-up Arabic, others
    # come back flipped into English — actively DESTROYING correct,
    # pre-existing content. Segments already in the target script are
    # excluded from translation entirely and left untouched; rebuild_document
    # skips any segment with no `target` set, so the original text survives
    # exactly as it was. `segments` itself keeps every entry (unchanged
    # ones included) since the rebuild step still needs it for those
    # shapes — only the sublist actually sent to the model is filtered.
    segments_to_translate = segments
    if is_rtl_lang(target_lang):
        from api.utils.doc_rebuilder import _text_is_rtl_script
        already_in_target = [s for s in segments if _text_is_rtl_script(s.get("source", "") or "")]
        if already_in_target:
            segments_to_translate = [s for s in segments if s not in already_in_target]
            warnings.append(
                f"{len(already_in_target)} segment(s) were already in {LANG_NAMES.get(target_lang, target_lang)} "
                "and were left unchanged rather than re-translated."
            )

    target_name = LANG_NAMES.get(target_lang, target_lang)
    system_prompt = (
        f"You are a professional technical translator specializing in security screening and X-ray systems. "
        f"Translate from {source_lang} to {target_name}. Preserve technical terms, model numbers, part codes, "
        "and units unless they have a standard translated form. Do not translate formulas. "
        "Return ONLY the translated text, nothing else."
    )

    # No segment-count cap — every segment is translated. Large documents are
    # handled by translate_segments_parallel: token-aware batching (~10-20
    # segments/request) run many-at-once under an adaptive rate limiter
    # (GEMINI_RPM_LIMIT), with a JSON checkpoint so a retry resumes instead
    # of re-translating (and re-billing) completed segments.
    from api.utils.batch_translator import translate_segments_parallel
    import hashlib

    checkpoint_key = hashlib.sha256(f"{wf.id}:{target_lang}".encode()).hexdigest()[:24]
    checkpoint_path = workspace_storage.temp_dir(ctx.workspace.user_id, ctx.workspace.id) / f"translate_checkpoint_{checkpoint_key}.json"

    still_missing = (
        await translate_segments_parallel(segments_to_translate, ctx.provider, system_prompt, checkpoint_path)
        if segments_to_translate else []
    )
    if still_missing:
        raise ToolError(
            f"Translation incomplete: {len(still_missing)} of {len(segments)} segment(s) could not be "
            "translated after retries. No file was produced — re-run the translation to resume from "
            "the checkpoint (already-translated segments will not be re-billed)."
        )

    try:
        # layout_warnings must be a real (mutable) list, not the default
        # None — rebuild_pptx's entire font-shrink/box-resize/overlap-repair
        # QA pass is gated on `if layout_warnings is not None`, so leaving
        # this at its default silently skips auto-repair altogether even
        # though auto_repair_enabled defaults to True.
        layout_warnings: list[str] = []
        docx_bytes, pptx_bytes, xlsx_bytes = rebuild_document(
            original_bytes, ext, segments, target_lang, source_lang,
            layout_warnings=layout_warnings,
        )
        warnings.extend(layout_warnings)
    except Exception as exc:
        raise ToolError(f"Failed to rebuild the translated document: {exc}")

    out_bytes = docx_bytes or pptx_bytes or xlsx_bytes
    if not out_bytes:
        raise ToolError("Document rebuild produced no output.")

    out_ext = "docx" if docx_bytes else ("pptx" if pptx_bytes else ("xlsx" if xlsx_bytes else ext))
    filename = filename_helper.build_translated_filename_from_code(wf.original_filename, target_lang)
    if not filename.lower().endswith(f".{out_ext}"):
        filename = f"{filename.rsplit('.', 1)[0]}.{out_ext}"

    gen = _register_generated(ctx, filename, out_ext, out_bytes, source_file_ids=[wf.id])
    gen["warnings"] = warnings
    return gen


def _tool_create_excel_workbook(ctx: WorkspaceToolContext, args: dict) -> dict:
    filename = args.get("filename") or "workbook.xlsx"
    if not filename.lower().endswith(".xlsx"):
        filename += ".xlsx"
    sheets = args.get("sheets") or []
    if not sheets:
        raise ToolError("At least one sheet is required.")
    try:
        data = build_workbook(sheets)
    except WorkbookValidationError as exc:
        raise ToolError(str(exc))
    return _register_generated(ctx, filename, "xlsx", data)


def _tool_create_csv(ctx: WorkspaceToolContext, args: dict) -> dict:
    filename = args.get("filename") or "data.csv"
    if not filename.lower().endswith(".csv"):
        filename += ".csv"
    data = build_csv_bytes(args.get("headers") or [], args.get("rows") or [])
    return _register_generated(ctx, filename, "csv", data)


def _tool_create_word_document(ctx: WorkspaceToolContext, args: dict) -> dict:
    filename = args.get("filename") or "document.docx"
    if not filename.lower().endswith(".docx"):
        filename += ".docx"
    data = doc_builder.build_word_document(args.get("title", ""), args.get("markdown_body", ""), lang=args.get("lang", "en"))
    return _register_generated(ctx, filename, "docx", data)


def _tool_create_powerpoint(ctx: WorkspaceToolContext, args: dict) -> dict:
    filename = args.get("filename") or "presentation.pptx"
    if not filename.lower().endswith(".pptx"):
        filename += ".pptx"
    data = pptx_builder.build_training_pptx(args.get("course_title", ""), args.get("slides_outline") or [])
    return _register_generated(ctx, filename, "pptx", data)


def _tool_create_pdf_report(ctx: WorkspaceToolContext, args: dict) -> dict:
    filename = args.get("filename") or "report.pdf"
    if not filename.lower().endswith(".pdf"):
        filename += ".pdf"
    data = doc_builder.build_pdf_document(args.get("title", ""), args.get("markdown_body", ""), lang=args.get("lang", "en"))
    return _register_generated(ctx, filename, "pdf", data)


def _tool_create_markdown_report(ctx: WorkspaceToolContext, args: dict) -> dict:
    filename = args.get("filename") or "report.md"
    if not filename.lower().endswith(".md"):
        filename += ".md"
    data = doc_builder.build_markdown_report(args.get("title", ""), args.get("markdown_body", ""))
    return _register_generated(ctx, filename, "md", data)


def _tool_write_generated_file(ctx: WorkspaceToolContext, args: dict) -> dict:
    filename = args.get("filename") or "output.txt"
    fmt = (args.get("format") or filename.rsplit(".", 1)[-1] or "txt").lower()
    content = args.get("content", "")
    data = content.encode("utf-8")
    return _register_generated(ctx, filename, fmt, data)


def _tool_validate_generated_file(ctx: WorkspaceToolContext, args: dict) -> dict:
    gf = crud.get_generated_file(ctx.db, args["generated_file_id"], ctx.workspace.id)
    if not gf:
        raise ToolError("No such generated file.")
    try:
        data = workspace_storage.read_file(gf.storage_path)
    except FileNotFoundError:
        return {"valid": False, "reason": "File is missing from storage."}
    if not data:
        return {"valid": False, "reason": "File is empty."}
    if gf.format == "xlsx":
        try:
            import io as _io
            from openpyxl import load_workbook
            wb = load_workbook(_io.BytesIO(data))
            wb.close()
        except Exception as exc:
            return {"valid": False, "reason": f"Workbook failed to reopen: {exc}"}
    return {"valid": True, "size_bytes": len(data)}


def _tool_list_generated_files(ctx: WorkspaceToolContext, args: dict) -> dict:
    files = crud.list_generated_files(ctx.db, ctx.workspace.id)
    return {"files": [crud.generated_file_to_dict(f) for f in files]}


_SYNC_TOOLS = {
    "list_workspace_files": _tool_list_workspace_files,
    "get_workspace_tree": _tool_get_workspace_tree,
    "read_file": _tool_read_file,
    "read_file_range": _tool_read_file_range,
    "get_file_metadata": _tool_get_file_metadata,
    "extract_document_text": _tool_extract_document_text,
    "extract_tables": _tool_extract_tables,
    "inspect_excel_workbook": _tool_inspect_excel_workbook,
    "inspect_powerpoint": _tool_inspect_powerpoint,
    "inspect_word_document": _tool_inspect_word_document,
    "create_excel_workbook": _tool_create_excel_workbook,
    "create_csv": _tool_create_csv,
    "create_word_document": _tool_create_word_document,
    "create_powerpoint": _tool_create_powerpoint,
    "create_pdf_report": _tool_create_pdf_report,
    "create_markdown_report": _tool_create_markdown_report,
    "write_generated_file": _tool_write_generated_file,
    "validate_generated_file": _tool_validate_generated_file,
    "list_generated_files": _tool_list_generated_files,
}

_ASYNC_TOOLS = {
    "translate_text": _tool_translate_text,
    "translate_document": _tool_translate_document,
    "search_workspace": _tool_search_workspace,
    "refresh_workspace_index": _tool_refresh_workspace_index,
}

ALL_TOOL_NAMES = set(_SYNC_TOOLS) | set(_ASYNC_TOOLS)


async def execute_tool(ctx: WorkspaceToolContext, name: str, arguments: dict) -> dict:
    """Dispatch a single tool call. Never raises — errors come back as {"error": str}
    inside the result so the model can see and react to them, and one bad tool
    call cannot crash the whole agent turn."""
    try:
        if name in _ASYNC_TOOLS:
            return await _ASYNC_TOOLS[name](ctx, arguments)
        if name in _SYNC_TOOLS:
            return _SYNC_TOOLS[name](ctx, arguments)
        return {"error": f"Unknown tool '{name}'."}
    except ToolError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        log.exception("Tool '%s' raised an unexpected error", name)
        return {"error": f"Unexpected error running '{name}': {exc}"}
