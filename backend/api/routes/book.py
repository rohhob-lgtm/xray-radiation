"""
Book Authoring Studio — API routes.

Original-book creation from a topic: outline -> chapters -> compile -> export.
Not a translation module (single `language` per project, no editions).
Existing modules (Research Studio, Training, Education, Knowledge Base) are
only ever read from as optional chapter source material — never modified.

Endpoints:
  POST   /api/book/projects
  GET    /api/book/projects
  GET    /api/book/projects/{id}
  PATCH  /api/book/projects/{id}
  DELETE /api/book/projects/{id}

  POST   /api/book/projects/{id}/outline
  PATCH  /api/book/projects/{id}/outline
  POST   /api/book/projects/{id}/outline/approve

  GET    /api/book/projects/{id}/chapters
  POST   /api/book/projects/{id}/chapters/{n}/generate
  PATCH  /api/book/projects/{id}/chapters/{n}
  POST   /api/book/projects/{id}/chapters/{n}/regenerate
  POST   /api/book/projects/{id}/chapters/{n}/approve
  GET    /api/book/projects/{id}/chapters/{n}/versions
  POST   /api/book/projects/{id}/chapters/{n}/versions/{version_num}/restore

  POST/GET/DELETE  /api/book/projects/{id}/references[/{ref_id}]
  POST/GET/DELETE  /api/book/projects/{id}/figures[/{fig_id}]
  POST/GET/DELETE  /api/book/projects/{id}/tables[/{table_id}]

  POST   /api/book/projects/{id}/compile
  GET    /api/book/projects/{id}/export/{fmt}
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.db.models import BookChapter
from api.middleware.auth import require_auth
from api.services import book_service
from api.services.book_service import BookServiceError
from api.utils.filename_helper import content_disposition

router = APIRouter(prefix="/book", tags=["book"])


def _uid(user: dict) -> Optional[str]:
    return user["id"] if user else None


def _project_dict(p) -> dict:
    return {
        "id": p.id,
        "title": p.title,
        "topic": p.topic,
        "language": p.language,
        "status": p.status,
        "last_error": p.last_error,
        "outline": p.outline or [],
        "source_config": p.source_config or [],
        "has_compiled_docx": bool(p.compiled_docx),
        "has_compiled_pdf": bool(p.compiled_pdf),
        "has_compiled_html": bool(p.compiled_html),
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


def _chapter_dict(c: BookChapter) -> dict:
    return {
        "id": c.id,
        "chapter_number": c.chapter_number,
        "title": c.title,
        "summary": c.summary,
        "status": c.status,
        "content": c.content,
        "word_count": c.word_count,
        "source_refs": c.source_refs or [],
        "created_at": c.created_at.isoformat() if c.created_at else None,
        "updated_at": c.updated_at.isoformat() if c.updated_at else None,
    }


def _get_chapter_or_404(db: Session, project, chapter_number: int) -> BookChapter:
    chapter = (
        db.query(BookChapter)
        .filter(BookChapter.book_project_id == project.id, BookChapter.chapter_number == chapter_number)
        .first()
    )
    if chapter is None:
        raise HTTPException(404, f"Chapter {chapter_number} not found — generate it first.")
    return chapter


def _handle(exc: BookServiceError) -> HTTPException:
    return HTTPException(400, str(exc))


# ── Project lifecycle ────────────────────────────────────────────────────

class CreateProjectBody(BaseModel):
    title: str
    topic: str = ""
    language: str = "en"


@router.post("/projects")
def create_project(body: CreateProjectBody, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    project = book_service.create_project(db, _uid(user), body.title, body.topic, body.language)
    return _project_dict(project)


@router.get("/projects")
def list_projects(db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    return [_project_dict(p) for p in book_service.list_projects(db, _uid(user))]


@router.get("/projects/{project_id}")
def get_project(project_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    d = _project_dict(project)
    d["chapters"] = [_chapter_dict(c) for c in book_service.list_chapters(db, project)]
    d["references"] = [
        {"id": r.id, "chapter_id": r.chapter_id, "citation_text": r.citation_text,
         "source_url": r.source_url, "source_type": r.source_type, "order_index": r.order_index}
        for r in book_service.list_references(db, project)
    ]
    d["figures"] = [
        {"id": f.id, "chapter_id": f.chapter_id, "caption": f.caption,
         "storage_path": f.storage_path, "order_index": f.order_index}
        for f in book_service.list_figures(db, project)
    ]
    d["tables"] = [
        {"id": t.id, "chapter_id": t.chapter_id, "caption": t.caption,
         "table_data": t.table_data, "order_index": t.order_index}
        for t in book_service.list_tables(db, project)
    ]
    return d


class PatchProjectBody(BaseModel):
    title: Optional[str] = None
    topic: Optional[str] = None
    language: Optional[str] = None


@router.patch("/projects/{project_id}")
def patch_project(project_id: str, body: PatchProjectBody, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        project = book_service.update_project_metadata(db, project, **body.model_dump())
    except BookServiceError as exc:
        raise _handle(exc)
    return _project_dict(project)


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    book_service.delete_project(db, project)
    return {"deleted": project_id}


# ── Outline ───────────────────────────────────────────────────────────────

class GenerateOutlineBody(BaseModel):
    chapter_count_hint: int = 8


@router.post("/projects/{project_id}/outline")
async def generate_outline(project_id: str, body: GenerateOutlineBody, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        project = await book_service.generate_outline(db, project, body.chapter_count_hint)
    except BookServiceError as exc:
        raise _handle(exc)
    return _project_dict(project)


class OutlineChapterBody(BaseModel):
    chapter_number: int
    title: str
    summary: str = ""


class UpdateOutlineBody(BaseModel):
    outline: list[OutlineChapterBody]


@router.patch("/projects/{project_id}/outline")
def update_outline(project_id: str, body: UpdateOutlineBody, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        project = book_service.update_outline(db, project, [c.model_dump() for c in body.outline])
    except BookServiceError as exc:
        raise _handle(exc)
    return _project_dict(project)


@router.post("/projects/{project_id}/outline/approve")
def approve_outline(project_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        project = book_service.approve_outline(db, project)
    except BookServiceError as exc:
        raise _handle(exc)
    return _project_dict(project)


# ── Chapters ─────────────────────────────────────────────────────────────

@router.get("/projects/{project_id}/chapters")
def list_chapters(project_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    return [_chapter_dict(c) for c in book_service.list_chapters(db, project)]


class GenerateChapterBody(BaseModel):
    source_refs: list[dict] = []


@router.post("/projects/{project_id}/chapters/{chapter_number}/generate")
async def generate_chapter(
    project_id: str, chapter_number: int, body: GenerateChapterBody,
    db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        chapter = await book_service.generate_chapter(db, project, chapter_number, body.source_refs)
    except BookServiceError as exc:
        raise _handle(exc)
    return _chapter_dict(chapter)


class UpdateChapterBody(BaseModel):
    content: str
    note: str = ""


@router.patch("/projects/{project_id}/chapters/{chapter_number}")
def update_chapter(
    project_id: str, chapter_number: int, body: UpdateChapterBody,
    db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    chapter = _get_chapter_or_404(db, project, chapter_number)
    chapter = book_service.update_chapter_content(db, chapter, body.content, body.note)
    return _chapter_dict(chapter)


@router.post("/projects/{project_id}/chapters/{chapter_number}/approve")
def approve_chapter(project_id: str, chapter_number: int, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    chapter = _get_chapter_or_404(db, project, chapter_number)
    chapter = book_service.approve_chapter(db, chapter)
    return _chapter_dict(chapter)


@router.post("/projects/{project_id}/chapters/{chapter_number}/regenerate")
async def regenerate_chapter(project_id: str, chapter_number: int, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        chapter = await book_service.regenerate_chapter(db, project, chapter_number)
    except BookServiceError as exc:
        raise _handle(exc)
    return _chapter_dict(chapter)


@router.get("/projects/{project_id}/chapters/{chapter_number}/versions")
def list_chapter_versions(project_id: str, chapter_number: int, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    chapter = _get_chapter_or_404(db, project, chapter_number)
    versions = book_service.list_chapter_versions(db, chapter)
    return [
        {"version_num": v.version_num, "created_by": v.created_by, "note": v.note,
         "created_at": v.created_at.isoformat() if v.created_at else None,
         "content_preview": (v.content or "")[:300]}
        for v in versions
    ]


@router.post("/projects/{project_id}/chapters/{chapter_number}/versions/{version_num}/restore")
def restore_chapter_version(
    project_id: str, chapter_number: int, version_num: int,
    db: Session = Depends(get_db), user: dict = Depends(require_auth),
):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        chapter = _get_chapter_or_404(db, project, chapter_number)
        chapter = book_service.restore_chapter_version(db, chapter, version_num)
    except BookServiceError as exc:
        raise _handle(exc)
    return _chapter_dict(chapter)


# ── References ───────────────────────────────────────────────────────────

class ReferenceBody(BaseModel):
    citation_text: str
    source_url: Optional[str] = None
    source_type: str = "manual"
    chapter_id: Optional[str] = None
    order_index: int = 0


@router.post("/projects/{project_id}/references")
def add_reference(project_id: str, body: ReferenceBody, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    ref = book_service.add_reference(db, project, **body.model_dump())
    return {"id": ref.id, "citation_text": ref.citation_text, "source_url": ref.source_url}


@router.get("/projects/{project_id}/references")
def get_references(project_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    return [
        {"id": r.id, "chapter_id": r.chapter_id, "citation_text": r.citation_text,
         "source_url": r.source_url, "source_type": r.source_type, "order_index": r.order_index}
        for r in book_service.list_references(db, project)
    ]


@router.delete("/projects/{project_id}/references/{reference_id}")
def delete_reference(project_id: str, reference_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        book_service.delete_reference(db, project, reference_id)
    except BookServiceError as exc:
        raise _handle(exc)
    return {"deleted": reference_id}


# ── Figures ──────────────────────────────────────────────────────────────

class FigureBody(BaseModel):
    caption: str
    storage_path: str
    chapter_id: Optional[str] = None
    order_index: int = 0
    placement_note: Optional[str] = None


@router.post("/projects/{project_id}/figures")
def add_figure(project_id: str, body: FigureBody, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    fig = book_service.add_figure(db, project, **body.model_dump())
    return {"id": fig.id, "caption": fig.caption, "storage_path": fig.storage_path}


@router.get("/projects/{project_id}/figures")
def get_figures(project_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    return [
        {"id": f.id, "chapter_id": f.chapter_id, "caption": f.caption,
         "storage_path": f.storage_path, "order_index": f.order_index}
        for f in book_service.list_figures(db, project)
    ]


@router.delete("/projects/{project_id}/figures/{figure_id}")
def delete_figure(project_id: str, figure_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        book_service.delete_figure(db, project, figure_id)
    except BookServiceError as exc:
        raise _handle(exc)
    return {"deleted": figure_id}


# ── Tables ───────────────────────────────────────────────────────────────

class TableBody(BaseModel):
    caption: str
    table_data: dict
    chapter_id: Optional[str] = None
    order_index: int = 0


@router.post("/projects/{project_id}/tables")
def add_table(project_id: str, body: TableBody, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    tbl = book_service.add_table(db, project, **body.model_dump())
    return {"id": tbl.id, "caption": tbl.caption}


@router.get("/projects/{project_id}/tables")
def get_tables(project_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")
    return [
        {"id": t.id, "chapter_id": t.chapter_id, "caption": t.caption,
         "table_data": t.table_data, "order_index": t.order_index}
        for t in book_service.list_tables(db, project)
    ]


@router.delete("/projects/{project_id}/tables/{table_id}")
def delete_table(project_id: str, table_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        book_service.delete_table(db, project, table_id)
    except BookServiceError as exc:
        raise _handle(exc)
    return {"deleted": table_id}


# ── Compile & export ─────────────────────────────────────────────────────

@router.post("/projects/{project_id}/compile")
def compile_project(project_id: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
        project = book_service.compile_project(db, project)
    except BookServiceError as exc:
        raise _handle(exc)
    return _project_dict(project)


_EXPORT_MIME = {
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pdf": "application/pdf",
    "html": "text/html; charset=utf-8",
}


@router.get("/projects/{project_id}/export/{fmt}")
def export_project(project_id: str, fmt: str, db: Session = Depends(get_db), user: dict = Depends(require_auth)):
    fmt = fmt.lower()
    if fmt not in _EXPORT_MIME:
        raise HTTPException(400, f"Unsupported export format: {fmt}")
    try:
        project = book_service.get_owned_project(db, project_id, _uid(user))
    except BookServiceError:
        raise HTTPException(404, "Book project not found")

    content = {"docx": project.compiled_docx, "pdf": project.compiled_pdf, "html": project.compiled_html}[fmt]
    if not content:
        raise HTTPException(400, "Book has not been compiled yet — call /compile first.")

    safe_title = (project.title or "book").replace(" ", "_").replace("/", "_")[:80]
    filename = f"{safe_title}.{fmt}"
    return Response(
        content=content,
        media_type=_EXPORT_MIME[fmt],
        headers={
            "Content-Disposition": content_disposition(filename),
            "Content-Length": str(len(content)),
            "Cache-Control": "private, no-store",
        },
    )
