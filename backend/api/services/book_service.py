"""
Book Authoring Studio — business logic.

Creates original books from a topic (not a translation module — see
routes/book.py and models.BookProject for the constraints this follows).
Every function takes an already-open `db: Session` and does not manage
transactions beyond its own commits, matching the pattern in routes/translation.py.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.db.models import (
    BookProject, BookChapter, BookChapterVersion, BookReference, BookFigure, BookTable,
)

log = logging.getLogger(__name__)


class BookServiceError(RuntimeError):
    pass


def _get_provider():
    from api.services.ai_providers.registry import provider_registry
    provider = provider_registry.get_active()
    if provider is None or not hasattr(provider, "chat"):
        raise BookServiceError("No active AI provider is configured to generate book content.")
    return provider


def _extract_json(text: str) -> Any:
    """Best-effort JSON extraction from an LLM reply — strips markdown code
    fences and grabs the first top-level JSON array/object if the model
    added any surrounding prose."""
    t = (text or "").strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    try:
        return json.loads(t)
    except Exception:
        pass
    m = re.search(r"(\[.*\]|\{.*\})", t, re.DOTALL)
    if m:
        return json.loads(m.group(1))
    raise BookServiceError("Could not parse a JSON outline from the AI response.")


# ── Project lifecycle ────────────────────────────────────────────────────

def create_project(db: Session, user_id: Optional[str], title: str, topic: str = "", language: str = "en") -> BookProject:
    project = BookProject(
        user_id=user_id,
        title=title.strip() or "Untitled Book",
        topic=(topic or title).strip(),
        language=language or "en",
        status="draft",
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    return project


def get_owned_project(db: Session, project_id: str, user_id: Optional[str]) -> BookProject:
    project = (
        db.query(BookProject)
        .filter(BookProject.id == project_id, BookProject.user_id == user_id)
        .first()
    )
    if project is None:
        raise BookServiceError("Book project not found.")
    return project


def list_projects(db: Session, user_id: Optional[str]) -> list[BookProject]:
    return (
        db.query(BookProject)
        .filter(BookProject.user_id == user_id)
        .order_by(BookProject.updated_at.desc())
        .all()
    )


def delete_project(db: Session, project: BookProject) -> None:
    db.delete(project)
    db.commit()


def update_project_metadata(db: Session, project: BookProject, **fields) -> BookProject:
    for key in ("title", "topic", "language"):
        if key in fields and fields[key] is not None:
            setattr(project, key, fields[key])
    db.commit()
    return project


# ── Outline ───────────────────────────────────────────────────────────────

_OUTLINE_SYSTEM_PROMPT = (
    "You are a professional non-fiction book editor. Given a book title and topic, "
    "produce a chapter outline. Respond with ONLY a JSON array (no prose, no markdown "
    "fences) of objects shaped like: "
    '[{"chapter_number": 1, "title": "...", "summary": "1-3 sentence summary"}, ...]. '
    "Produce a coherent, logically ordered set of chapters covering the topic thoroughly."
)


async def generate_outline(db: Session, project: BookProject, chapter_count_hint: int = 8) -> BookProject:
    provider = _get_provider()
    project.status = "outline_generating"
    db.commit()

    user_msg = (
        f"Book title: {project.title}\n"
        f"Topic: {project.topic}\n"
        f"Target chapter count: approximately {chapter_count_hint}\n"
        "Generate the outline now."
    )
    try:
        reply = await provider.chat([{"role": "user", "content": user_msg}], system_prompt=_OUTLINE_SYSTEM_PROMPT)
        outline_raw = _extract_json(reply)
    except Exception as exc:
        project.status = "error"
        project.last_error = f"Outline generation failed: {exc}"
        db.commit()
        raise BookServiceError(str(exc)) from exc

    if not isinstance(outline_raw, list) or not outline_raw:
        project.status = "error"
        project.last_error = "Outline generation returned no chapters."
        db.commit()
        raise BookServiceError("Outline generation returned no chapters.")

    outline = []
    for i, item in enumerate(outline_raw, start=1):
        if not isinstance(item, dict):
            continue
        outline.append({
            "chapter_number": int(item.get("chapter_number") or i),
            "title": str(item.get("title") or f"Chapter {i}").strip(),
            "summary": str(item.get("summary") or "").strip(),
        })

    project.outline = outline
    project.status = "outline_ready"
    project.last_error = None
    db.commit()
    db.refresh(project)
    return project


def update_outline(db: Session, project: BookProject, outline: list[dict]) -> BookProject:
    normalized = []
    for i, item in enumerate(outline, start=1):
        normalized.append({
            "chapter_number": int(item.get("chapter_number") or i),
            "title": str(item.get("title") or f"Chapter {i}").strip(),
            "summary": str(item.get("summary") or "").strip(),
        })
    project.outline = normalized
    if project.status not in ("outline_approved", "chapters_in_progress", "chapters_ready", "compiled", "exported"):
        project.status = "outline_ready"
    db.commit()
    db.refresh(project)
    return project


def approve_outline(db: Session, project: BookProject) -> BookProject:
    if not project.outline:
        raise BookServiceError("Cannot approve an empty outline — generate or add one first.")
    project.status = "outline_approved"
    db.commit()
    db.refresh(project)
    return project


# ── Chapters ─────────────────────────────────────────────────────────────

_CHAPTER_SYSTEM_PROMPT = (
    "You are a professional non-fiction book author writing one chapter of a book. "
    "Write complete, well-structured prose in Markdown (headings, paragraphs, lists "
    "where useful). Do not write a chapter title heading yourself — it is added "
    "separately. Do not include any meta-commentary about the writing process."
)


def _outline_entry(project: BookProject, chapter_number: int) -> dict:
    for entry in project.outline or []:
        if int(entry.get("chapter_number", -1)) == chapter_number:
            return entry
    raise BookServiceError(f"Chapter {chapter_number} is not in the approved outline.")


def _get_or_create_chapter(db: Session, project: BookProject, chapter_number: int) -> BookChapter:
    chapter = (
        db.query(BookChapter)
        .filter(BookChapter.book_project_id == project.id, BookChapter.chapter_number == chapter_number)
        .first()
    )
    if chapter is None:
        entry = _outline_entry(project, chapter_number)
        chapter = BookChapter(
            book_project_id=project.id,
            chapter_number=chapter_number,
            title=entry.get("title", f"Chapter {chapter_number}"),
            summary=entry.get("summary", ""),
            status="pending",
        )
        db.add(chapter)
        db.commit()
        db.refresh(chapter)
    return chapter


def _snapshot_version(db: Session, chapter: BookChapter, created_by: str, note: str = "") -> BookChapterVersion:
    last = (
        db.query(BookChapterVersion)
        .filter(BookChapterVersion.chapter_id == chapter.id)
        .order_by(BookChapterVersion.version_num.desc())
        .first()
    )
    next_num = (last.version_num + 1) if last else 1
    version = BookChapterVersion(
        chapter_id=chapter.id, version_num=next_num,
        content=chapter.content, created_by=created_by, note=note,
    )
    db.add(version)
    db.commit()
    return version


async def _fetch_source_context(db: Session, source_refs: list[dict]) -> str:
    """Read-only lookup of optional existing-module content used as chapter
    source material. Never modifies the source module's data."""
    if not source_refs:
        return ""
    chunks: list[str] = []
    for ref in source_refs:
        module = ref.get("module")
        ref_id = ref.get("ref_id")
        if not module or not ref_id:
            continue
        try:
            if module == "research_studio":
                from api.db.models import ResearchOutput
                row = db.query(ResearchOutput).filter(ResearchOutput.id == ref_id).first()
                if row:
                    chunks.append(f"[Research Studio: {row.topic}]\n{row.content[:6000]}")
            elif module == "knowledge_base":
                from api.services import xray_knowledge
                if hasattr(xray_knowledge, "get_document_text"):
                    text = xray_knowledge.get_document_text(db, ref_id)
                    if text:
                        chunks.append(f"[Knowledge Base excerpt]\n{text[:6000]}")
        except Exception as exc:
            log.warning("Book chapter source lookup failed for %s/%s: %s", module, ref_id, exc)
    return "\n\n".join(chunks)


async def generate_chapter(
    db: Session, project: BookProject, chapter_number: int, source_refs: Optional[list[dict]] = None,
) -> BookChapter:
    provider = _get_provider()
    if project.status not in ("outline_approved", "chapters_in_progress", "chapters_ready"):
        raise BookServiceError("Approve the outline before generating chapters.")

    entry = _outline_entry(project, chapter_number)
    chapter = _get_or_create_chapter(db, project, chapter_number)
    chapter.source_refs = source_refs or chapter.source_refs or []
    chapter.status = "generating"
    project.status = "chapters_in_progress"
    db.commit()

    source_context = await _fetch_source_context(db, chapter.source_refs)
    user_msg = (
        f"Book: {project.title}\n"
        f"Chapter {chapter_number}: {entry.get('title')}\n"
        f"Chapter summary/brief: {entry.get('summary')}\n"
        + (f"\nOptional reference material (use only what's relevant, don't copy verbatim):\n{source_context}\n" if source_context else "")
        + "\nWrite the full chapter now."
    )
    try:
        content = await provider.chat([{"role": "user", "content": user_msg}], system_prompt=_CHAPTER_SYSTEM_PROMPT)
    except Exception as exc:
        chapter.status = "error"
        db.commit()
        raise BookServiceError(f"Chapter generation failed: {exc}") from exc

    chapter.content = content.strip()
    chapter.word_count = len(chapter.content.split())
    chapter.status = "generated"
    db.commit()
    _snapshot_version(db, chapter, created_by="ai_generate")
    db.refresh(chapter)
    return chapter


def update_chapter_content(db: Session, chapter: BookChapter, content: str, note: str = "") -> BookChapter:
    chapter.content = content
    chapter.word_count = len(content.split())
    chapter.status = "edited"
    db.commit()
    _snapshot_version(db, chapter, created_by="manual_edit", note=note)
    db.refresh(chapter)
    return chapter


def approve_chapter(db: Session, chapter: BookChapter) -> BookChapter:
    chapter.status = "approved"
    db.commit()
    db.refresh(chapter)
    return chapter


async def regenerate_chapter(db: Session, project: BookProject, chapter_number: int) -> BookChapter:
    chapter = await generate_chapter(db, project, chapter_number)
    return chapter


def list_chapter_versions(db: Session, chapter: BookChapter) -> list[BookChapterVersion]:
    return (
        db.query(BookChapterVersion)
        .filter(BookChapterVersion.chapter_id == chapter.id)
        .order_by(BookChapterVersion.version_num.desc())
        .all()
    )


def restore_chapter_version(db: Session, chapter: BookChapter, version_num: int) -> BookChapter:
    version = (
        db.query(BookChapterVersion)
        .filter(BookChapterVersion.chapter_id == chapter.id, BookChapterVersion.version_num == version_num)
        .first()
    )
    if version is None:
        raise BookServiceError(f"Version {version_num} not found for this chapter.")
    chapter.content = version.content
    chapter.word_count = len(version.content.split())
    chapter.status = "edited"
    db.commit()
    _snapshot_version(db, chapter, created_by="manual_edit", note=f"restored from v{version_num}")
    db.refresh(chapter)
    return chapter


def list_chapters(db: Session, project: BookProject) -> list[BookChapter]:
    return (
        db.query(BookChapter)
        .filter(BookChapter.book_project_id == project.id)
        .order_by(BookChapter.chapter_number.asc())
        .all()
    )


# ── References / Figures / Tables ───────────────────────────────────────

def add_reference(db: Session, project: BookProject, **fields) -> BookReference:
    ref = BookReference(book_project_id=project.id, **fields)
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return ref


def list_references(db: Session, project: BookProject) -> list[BookReference]:
    return (
        db.query(BookReference)
        .filter(BookReference.book_project_id == project.id)
        .order_by(BookReference.order_index.asc())
        .all()
    )


def delete_reference(db: Session, project: BookProject, reference_id: str) -> None:
    ref = (
        db.query(BookReference)
        .filter(BookReference.id == reference_id, BookReference.book_project_id == project.id)
        .first()
    )
    if ref is None:
        raise BookServiceError("Reference not found.")
    db.delete(ref)
    db.commit()


def add_figure(db: Session, project: BookProject, **fields) -> BookFigure:
    fig = BookFigure(book_project_id=project.id, **fields)
    db.add(fig)
    db.commit()
    db.refresh(fig)
    return fig


def list_figures(db: Session, project: BookProject) -> list[BookFigure]:
    return (
        db.query(BookFigure)
        .filter(BookFigure.book_project_id == project.id)
        .order_by(BookFigure.order_index.asc())
        .all()
    )


def delete_figure(db: Session, project: BookProject, figure_id: str) -> None:
    fig = (
        db.query(BookFigure)
        .filter(BookFigure.id == figure_id, BookFigure.book_project_id == project.id)
        .first()
    )
    if fig is None:
        raise BookServiceError("Figure not found.")
    db.delete(fig)
    db.commit()


def add_table(db: Session, project: BookProject, **fields) -> BookTable:
    tbl = BookTable(book_project_id=project.id, **fields)
    db.add(tbl)
    db.commit()
    db.refresh(tbl)
    return tbl


def list_tables(db: Session, project: BookProject) -> list[BookTable]:
    return (
        db.query(BookTable)
        .filter(BookTable.book_project_id == project.id)
        .order_by(BookTable.order_index.asc())
        .all()
    )


def delete_table(db: Session, project: BookProject, table_id: str) -> None:
    tbl = (
        db.query(BookTable)
        .filter(BookTable.id == table_id, BookTable.book_project_id == project.id)
        .first()
    )
    if tbl is None:
        raise BookServiceError("Table not found.")
    db.delete(tbl)
    db.commit()


# ── Compile ──────────────────────────────────────────────────────────────

def compile_project(db: Session, project: BookProject) -> BookProject:
    from api.utils import book_export

    chapters = list_chapters(db, project)
    if not chapters:
        raise BookServiceError("No chapters to compile — generate at least Chapter 1 first.")

    project.status = "compiling"
    db.commit()

    try:
        references = list_references(db, project)
        figures = list_figures(db, project)
        tables = list_tables(db, project)
        markdown = book_export.compile_book(project, chapters, references, figures, tables)

        project.compiled_docx = book_export.export_docx(project.title, markdown, project.language)
        project.compiled_pdf = book_export.export_pdf(project.title, markdown, project.language)
        project.compiled_html = book_export.export_html(project.title, markdown)
    except Exception as exc:
        project.status = "error"
        project.last_error = f"Compile failed: {exc}"
        db.commit()
        raise BookServiceError(str(exc)) from exc

    project.status = "compiled"
    project.last_error = None
    db.commit()
    db.refresh(project)
    return project
