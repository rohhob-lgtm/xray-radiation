"""
Training Course Report Generator — X-Ray Academy

Produces official training-completion reports from structured form input by
populating the canonical "Training Course Report v3 - Blank Copy.docx"
template stored under backend/templates/training_reports/ — never rebuilt
from scratch, so header/footer/branding/fonts/pagination are preserved.

Narrative sections are drafted from the entered facts only (see
api.services.training_report_ai) with a deterministic fallback so the
feature works even without a configured LLM. Each generated report is
persisted (backend/uploads/training_course_reports/) with a DB row
(TrainingCourseReport) so it can be reopened, edited, duplicated or
re-downloaded later.
"""
from __future__ import annotations
import asyncio
import csv
import io
import logging
import os
import re
import uuid
from datetime import date, datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.db import get_db
from api.middleware.auth import optional_auth
from api.utils.filename_helper import content_disposition, mime_for_ext

log = logging.getLogger(__name__)
router = APIRouter(tags=["training-reports"])

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STORAGE_ROOT = os.path.join(_BACKEND_ROOT, "uploads", "training_course_reports")
_IMAGES_DIR = os.path.join(_STORAGE_ROOT, "_images")
os.makedirs(_IMAGES_DIR, exist_ok=True)

_NARRATIVE_SECTIONS = [
    "reference_documents", "background", "instructor", "delivery_language",
    "training_location", "students", "schedule", "completion_certification",
    "additional_notes", "follow_up_plan",
]

_TEMPLATES = [
    {
        "id": "standard_completion",
        "label": "Standard Training Completion Report",
        "description": "Course info table + narrative sections + attendee/certificate list, "
                        "populated from the official Training Course Report v3 template.",
    },
]


@router.get("/training-reports/templates")
def list_templates(user: Optional[dict] = Depends(optional_auth)):
    return _TEMPLATES


# ── Request/response schemas ──────────────────────────────────────────────────

class DocRefIn(BaseModel):
    reference_number: str = ""
    title: str = ""


class AttendeeIn(BaseModel):
    name: str = ""
    exam_percentage: Optional[float] = None
    certificate_awarded: bool = False
    certificate_serial: str = ""
    comments: str = ""


class TrainingReportFormData(BaseModel):
    # A. Basic report information
    report_title: str = ""
    training_level: str = ""
    course_name: str = ""
    start_date: str = ""
    end_date: str = ""
    instructor: str = ""
    project_code: str = ""
    system_type: str = ""
    system_serial_no: str = ""
    site_of_operation: str = ""
    customer: str = ""
    contract_reference: str = ""
    delivery_language: str = ""
    documentation_language: str = ""
    classroom_location: str = ""
    practical_location: str = ""
    total_training_days: Optional[float] = None
    classroom_days: Optional[float] = None
    practical_days: Optional[float] = None
    instructor_travel_days: Optional[float] = None
    output_language: str = "en"  # en | ar

    # B. Course attendance
    attendees_total: Optional[int] = None
    attendees_pass: Optional[int] = None
    attendees_fail: Optional[int] = None
    attendees_certified: Optional[int] = None
    previous_experience: str = ""
    computer_skills: str = ""
    language_ability: str = ""
    trainee_background: str = ""
    attendees: list[AttendeeIn] = Field(default_factory=list)

    # C. Reference documents
    doc_refs: list[DocRefIn] = Field(default_factory=list)

    # D. Training details
    training_purpose: str = ""
    course_objectives: str = ""
    training_scope: str = ""
    schedule_summary: str = ""
    subjects_covered: str = ""
    practical_activities: str = ""
    assessment_method: str = ""
    written_exam_completed: bool = False
    practical_exam_completed: bool = False
    pass_percentage: Optional[float] = None
    certification_requirements: str = ""
    instructor_evaluation: str = ""
    instructor_bio: str = ""
    additional_notes: str = ""
    qa_issues: str = ""
    technical_issues: str = ""
    action_taken: str = ""
    responsible_party: str = ""
    follow_up_plan: str = ""

    # E. Media
    site_image_id: Optional[str] = None


class NarrativeGenerateRequest(BaseModel):
    form_data: TrainingReportFormData
    sections: Optional[list[str]] = None  # None = all sections


class TrainingReportSaveRequest(BaseModel):
    template: str = "standard_completion"
    status: str = "draft"  # draft | final
    form_data: TrainingReportFormData
    narrative: dict[str, str] = Field(default_factory=dict)


# ── Validation (spec section 5) ───────────────────────────────────────────────

def _valid_attendees(fd: TrainingReportFormData) -> list[AttendeeIn]:
    return [a for a in fd.attendees if a.name.strip()]


def validate_for_final(fd: TrainingReportFormData) -> list[str]:
    errors: list[str] = []

    def require(value: str, message: str) -> None:
        if not (value or "").strip():
            errors.append(message)

    require(fd.report_title, "Report title is required.")
    if not (fd.training_level.strip() or fd.course_name.strip()):
        errors.append("Course name / training level is required.")
    require(fd.start_date, "Start date is required.")
    require(fd.end_date, "End date is required.")
    require(fd.instructor, "Instructor is required.")
    require(fd.system_type, "System type is required.")
    require(fd.site_of_operation, "Site of operation is required.")
    require(fd.customer, "Customer is required.")

    valid_attendees = _valid_attendees(fd)
    if not (fd.attendees_total or valid_attendees):
        errors.append("Total attendees or at least one attendee row is required.")

    try:
        sd = date.fromisoformat(fd.start_date.strip())
        ed = date.fromisoformat(fd.end_date.strip())
        if ed < sd:
            errors.append("End date cannot be earlier than start date.")
    except ValueError:
        pass  # free-text dates are tolerated; ordering just can't be checked

    for a in fd.attendees:
        if a.exam_percentage is not None and not (0 <= a.exam_percentage <= 100):
            errors.append(f"Exam percentage for '{a.name or 'an attendee'}' must be between 0 and 100.")

    if fd.pass_percentage is not None and not (0 <= fd.pass_percentage <= 100):
        errors.append("Pass percentage must be between 0 and 100.")

    if fd.attendees_certified is not None and fd.attendees_total is not None and fd.attendees_certified > fd.attendees_total:
        errors.append("Total certified cannot exceed total attendees.")

    if fd.attendees_pass is not None and fd.attendees_fail is not None and fd.attendees_total is not None:
        if fd.attendees_pass + fd.attendees_fail > fd.attendees_total:
            errors.append("Passed + failed cannot exceed total attendees.")

    return errors


# ── Form data -> facts / docx-fill mapping ────────────────────────────────────

def _format_date_range(start: str, end: str) -> str:
    def fmt(d: str) -> str:
        try:
            return date.fromisoformat(d.strip()).strftime("%d %b %Y")
        except ValueError:
            return d.strip()

    s, e = (start or "").strip(), (end or "").strip()
    if s and e:
        return f"{fmt(s)} - {fmt(e)}" if s != e else fmt(s)
    return fmt(s) or fmt(e)


def _facts_from_form(fd: TrainingReportFormData) -> dict[str, Any]:
    valid_attendees = _valid_attendees(fd)
    return {
        "training_level": fd.training_level or fd.course_name,
        "system_type": fd.system_type,
        "site_of_operation": fd.site_of_operation,
        "total_training_days": fd.total_training_days,
        "training_purpose": fd.training_purpose,
        "instructor": fd.instructor,
        "instructor_bio": fd.instructor_bio,
        "delivery_language": fd.delivery_language,
        "documentation_language": fd.documentation_language,
        "classroom_location": fd.classroom_location,
        "practical_location": fd.practical_location,
        "attendees_total": fd.attendees_total or len(valid_attendees),
        "previous_experience": fd.previous_experience,
        "computer_skills": fd.computer_skills,
        "language_ability": fd.language_ability,
        "trainee_background": fd.trainee_background,
        "start_date": _format_date_range(fd.start_date, fd.start_date),
        "end_date": _format_date_range(fd.end_date, fd.end_date),
        "schedule_summary": fd.schedule_summary,
        "subjects_covered": fd.subjects_covered,
        "practical_activities": fd.practical_activities,
        "written_exam_completed": fd.written_exam_completed,
        "practical_exam_completed": fd.practical_exam_completed,
        "pass_percentage": fd.pass_percentage,
        "attendees_certified": fd.attendees_certified,
        "certification_requirements": fd.certification_requirements,
        "instructor_evaluation": fd.instructor_evaluation,
        "additional_notes": fd.additional_notes,
        "qa_issues": fd.qa_issues,
        "technical_issues": fd.technical_issues,
        "action_taken": fd.action_taken,
        "responsible_party": fd.responsible_party,
        "follow_up_plan": fd.follow_up_plan,
        "doc_refs": [r.model_dump() for r in fd.doc_refs],
    }


def _info_values_from_form(fd: TrainingReportFormData) -> dict[str, Any]:
    valid_attendees = _valid_attendees(fd)
    return {
        "training_level": fd.training_level or fd.course_name,
        "dates_of_training": _format_date_range(fd.start_date, fd.end_date),
        "instructor": fd.instructor,
        "project_code": fd.project_code,
        "system_type": fd.system_type,
        "system_serial_no": fd.system_serial_no,
        "site_of_operation": fd.site_of_operation,
        "customer": fd.customer,
        "contract_reference": fd.contract_reference,
        "attendees_total": fd.attendees_total or len(valid_attendees),
        "attendees_pass": fd.attendees_pass if fd.attendees_pass is not None else 0,
        "attendees_fail": fd.attendees_fail if fd.attendees_fail is not None else 0,
        "attendees_certified": fd.attendees_certified if fd.attendees_certified is not None else 0,
    }


# ── Narrative generation ──────────────────────────────────────────────────────

@router.post("/training-reports/narrative/generate")
async def generate_narrative(body: NarrativeGenerateRequest, user: Optional[dict] = Depends(optional_auth)):
    from api.services.ai_providers.registry import provider_registry
    from api.services.training_report_ai import generate_section

    provider = provider_registry.get_active()
    facts = _facts_from_form(body.form_data)
    section_keys = body.sections or _NARRATIVE_SECTIONS
    unknown = [k for k in section_keys if k not in _NARRATIVE_SECTIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"Unknown section(s): {unknown}")

    results = await asyncio.gather(*[
        generate_section(key, facts, body.form_data.output_language, provider=provider)
        for key in section_keys
    ])
    return {"sections": dict(zip(section_keys, results))}


# ── Image upload ──────────────────────────────────────────────────────────────

@router.post("/training-reports/upload-image")
async def upload_report_image(
    file: UploadFile = File(...),
    user: Optional[dict] = Depends(optional_auth),
):
    from PIL import Image

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    _MAX_IMAGE_BYTES = 25 * 1024 * 1024
    if len(data) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=413, detail="Image too large (max 25 MB).")
    try:
        img = Image.open(io.BytesIO(data))
        img.verify()
        fmt = (img.format or "PNG").lower()
    except Exception:
        raise HTTPException(status_code=400, detail="Uploaded file is not a valid image.")

    ext = {"jpeg": "jpg"}.get(fmt, fmt)
    if ext not in ("jpg", "png", "gif", "webp", "bmp", "tiff"):
        ext = "png"
    image_id = f"{uuid.uuid4().hex}.{ext}"
    with open(os.path.join(_IMAGES_DIR, image_id), "wb") as fh:
        fh.write(data)
    return {"image_id": image_id}


def _load_image_bytes(image_id: Optional[str]) -> Optional[bytes]:
    if not image_id or "/" in image_id or "\\" in image_id or ".." in image_id:
        return None
    path = os.path.join(_IMAGES_DIR, image_id)
    if not os.path.exists(path):
        return None
    with open(path, "rb") as fh:
        return fh.read()


# ── Attendee CSV/XLSX import ──────────────────────────────────────────────────

_HEADER_ALIASES = {
    "name": {"name", "attendee name", "attendee", "trainee", "trainee name"},
    "exam_percentage": {"exam %", "exam percentage", "exam%", "score", "score %"},
    "certificate_awarded": {"certificate awarded", "certified", "pass", "passed"},
    "certificate_serial": {"certificate serial", "certificate serial number", "cert serial", "serial", "serial number"},
    "comments": {"comments", "comment", "notes", "remarks"},
}


def _match_header(header_row: list[str]) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for idx, raw in enumerate(header_row):
        key = re.sub(r"\s+", " ", (raw or "").strip().lower())
        for field, aliases in _HEADER_ALIASES.items():
            if key in aliases:
                mapping[idx] = field
                break
    return mapping


def _row_to_attendee(row: list[Any], mapping: dict[int, str]) -> dict[str, Any]:
    out: dict[str, Any] = {"name": "", "exam_percentage": None, "certificate_awarded": False, "certificate_serial": "", "comments": ""}
    for idx, field in mapping.items():
        if idx >= len(row):
            continue
        value = row[idx]
        if value is None:
            continue
        if field == "exam_percentage":
            try:
                out[field] = float(str(value).replace("%", "").strip())
            except ValueError:
                pass
        elif field == "certificate_awarded":
            out[field] = str(value).strip().lower() in ("yes", "true", "1", "pass", "passed", "y")
        else:
            out[field] = str(value).strip()
    return out


@router.post("/training-reports/import-attendees")
async def import_attendees(file: UploadFile = File(...), user: Optional[dict] = Depends(optional_auth)):
    filename = (file.filename or "").lower()
    data = await file.read()
    if len(data) > 25 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB).")
    rows: list[list[Any]] = []

    if filename.endswith(".xlsx"):
        import openpyxl
        wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb.active
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
    elif filename.endswith(".csv"):
        text = data.decode("utf-8-sig", errors="replace")
        rows = [row for row in csv.reader(io.StringIO(text))]
    else:
        raise HTTPException(status_code=400, detail="Only .csv or .xlsx files are supported.")

    if not rows:
        return {"attendees": []}

    mapping = _match_header([str(c) if c is not None else "" for c in rows[0]])
    if not mapping:
        raise HTTPException(
            status_code=422,
            detail="Could not recognize any columns. Expected headers like Name, Exam %, Certificate Awarded, Certificate Serial, Comments.",
        )
    attendees = [_row_to_attendee(row, mapping) for row in rows[1:] if any(c not in (None, "") for c in row)]
    return {"attendees": attendees}


# ── Filename / storage helpers ────────────────────────────────────────────────

def _slug(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^\w\s-]", "", text or "").strip()[:max_len].replace(" ", "_")
    return slug or "Report"


def _report_dir(report_id: str) -> str:
    path = os.path.join(_STORAGE_ROOT, report_id)
    os.makedirs(path, exist_ok=True)
    return path


def build_report_filename(customer: str, system_type: str, start_date: str, report_id: str) -> str:
    return f"Training_Report_{_slug(customer)}_{_slug(system_type)}_{_slug(start_date, 20)}_{report_id[:8].upper()}.docx"


def _generate_docx_pdf(fd: TrainingReportFormData, narrative: dict[str, str], report_id: str) -> tuple[str, Optional[str], str]:
    from api.utils.training_report_docx import build_training_course_report_docx
    from api.utils.word_com_finalizer import convert_docx_to_pdf_with_word, WordAutomationError

    info_values = _info_values_from_form(fd)
    is_rtl = fd.output_language == "ar"
    site_image_bytes = _load_image_bytes(fd.site_image_id)

    docx_bytes = build_training_course_report_docx(
        info_values,
        [r.model_dump() for r in fd.doc_refs],
        [a.model_dump() for a in fd.attendees],
        narrative,
        is_rtl=is_rtl,
        site_image_bytes=site_image_bytes,
    )
    if not docx_bytes:
        raise HTTPException(status_code=500, detail="DOCX generation produced no output.")

    filename = build_report_filename(fd.customer, fd.system_type, fd.start_date, report_id)
    out_dir = _report_dir(report_id)
    docx_path = os.path.join(out_dir, filename)
    with open(docx_path, "wb") as fh:
        fh.write(docx_bytes)
    if os.path.getsize(docx_path) == 0:
        raise HTTPException(status_code=500, detail="Generated DOCX file is empty.")

    pdf_path: Optional[str] = None
    try:
        pdf_bytes = convert_docx_to_pdf_with_word(docx_bytes)
        pdf_path = os.path.join(out_dir, filename[:-5] + ".pdf")
        with open(pdf_path, "wb") as fh:
            fh.write(pdf_bytes)
        if os.path.getsize(pdf_path) == 0:
            os.remove(pdf_path)
            pdf_path = None
    except WordAutomationError as exc:
        log.warning("PDF export unavailable for report %s: %s", report_id, exc)
        pdf_path = None

    return docx_path, pdf_path, filename


# ── CRUD ───────────────────────────────────────────────────────────────────────

def _record_summary(rec) -> dict:
    return {
        "id": rec.id,
        "template": rec.template,
        "title": rec.title,
        "customer": rec.customer,
        "system_type": rec.system_type,
        "instructor": rec.instructor,
        "start_date": rec.start_date,
        "end_date": rec.end_date,
        "status": rec.status,
        "output_language": rec.output_language,
        "has_docx": bool(rec.docx_path and os.path.exists(rec.docx_path)),
        "has_pdf": bool(rec.pdf_path and os.path.exists(rec.pdf_path)),
        "created_at": rec.created_at.isoformat() if rec.created_at else None,
        "updated_at": rec.updated_at.isoformat() if rec.updated_at else None,
    }


@router.post("/training-reports")
async def create_training_report(
    body: TrainingReportSaveRequest,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import TrainingCourseReport
    from api.services.ai_providers.registry import provider_registry
    from api.services.training_report_ai import generate_section

    if body.status not in ("draft", "final"):
        raise HTTPException(status_code=400, detail="status must be 'draft' or 'final'")

    fd = body.form_data
    if body.status == "final":
        errors = validate_for_final(fd)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})

    narrative = dict(body.narrative)
    if body.status == "final":
        provider = provider_registry.get_active()
        facts = _facts_from_form(fd)
        missing = [k for k in _NARRATIVE_SECTIONS if not narrative.get(k)]
        if missing:
            generated = await asyncio.gather(*[
                generate_section(k, facts, fd.output_language, provider=provider) for k in missing
            ])
            narrative.update(dict(zip(missing, generated)))

    rec = TrainingCourseReport(
        template=body.template,
        title=fd.report_title,
        customer=fd.customer,
        system_type=fd.system_type,
        instructor=fd.instructor,
        start_date=fd.start_date,
        end_date=fd.end_date,
        status=body.status,
        output_language=fd.output_language,
        form_data=fd.model_dump(),
        narrative=narrative,
    )
    db.add(rec)
    db.flush()

    if body.status == "final":
        docx_path, pdf_path, filename = _generate_docx_pdf(fd, narrative, rec.id)
        rec.docx_path = docx_path
        rec.pdf_path = pdf_path
        rec.docx_filename = filename

    db.commit()
    db.refresh(rec)
    return _record_summary(rec)


@router.get("/training-reports")
def list_training_reports(db: Session = Depends(get_db), user: Optional[dict] = Depends(optional_auth)):
    from api.db.models import TrainingCourseReport
    q = db.query(TrainingCourseReport).order_by(TrainingCourseReport.updated_at.desc())
    return [_record_summary(r) for r in q.all()]


@router.get("/training-reports/{report_id}")
def get_training_report(report_id: str, db: Session = Depends(get_db), user: Optional[dict] = Depends(optional_auth)):
    from api.db.models import TrainingCourseReport
    rec = db.query(TrainingCourseReport).filter_by(id=report_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")
    return {
        **_record_summary(rec),
        "form_data": rec.form_data,
        "narrative": rec.narrative,
    }


@router.put("/training-reports/{report_id}")
async def update_training_report(
    report_id: str,
    body: TrainingReportSaveRequest,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import TrainingCourseReport
    from api.services.ai_providers.registry import provider_registry
    from api.services.training_report_ai import generate_section

    rec = db.query(TrainingCourseReport).filter_by(id=report_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")

    fd = body.form_data
    if body.status == "final":
        errors = validate_for_final(fd)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})

    narrative = dict(body.narrative)
    if body.status == "final":
        provider = provider_registry.get_active()
        facts = _facts_from_form(fd)
        missing = [k for k in _NARRATIVE_SECTIONS if not narrative.get(k)]
        if missing:
            generated = await asyncio.gather(*[
                generate_section(k, facts, fd.output_language, provider=provider) for k in missing
            ])
            narrative.update(dict(zip(missing, generated)))

    rec.template = body.template
    rec.title = fd.report_title
    rec.customer = fd.customer
    rec.system_type = fd.system_type
    rec.instructor = fd.instructor
    rec.start_date = fd.start_date
    rec.end_date = fd.end_date
    rec.status = body.status
    rec.output_language = fd.output_language
    rec.form_data = fd.model_dump()
    rec.narrative = narrative

    if body.status == "final":
        docx_path, pdf_path, filename = _generate_docx_pdf(fd, narrative, rec.id)
        rec.docx_path = docx_path
        rec.pdf_path = pdf_path
        rec.docx_filename = filename

    db.commit()
    db.refresh(rec)
    return _record_summary(rec)


@router.post("/training-reports/{report_id}/duplicate")
def duplicate_training_report(report_id: str, db: Session = Depends(get_db), user: Optional[dict] = Depends(optional_auth)):
    from api.db.models import TrainingCourseReport
    src = db.query(TrainingCourseReport).filter_by(id=report_id).first()
    if not src:
        raise HTTPException(status_code=404, detail="Report not found")

    clone = TrainingCourseReport(
        template=src.template,
        title=f"{src.title} (Copy)",
        customer=src.customer,
        system_type=src.system_type,
        instructor=src.instructor,
        start_date=src.start_date,
        end_date=src.end_date,
        status="draft",
        output_language=src.output_language,
        form_data={**src.form_data, "report_title": f"{src.title} (Copy)"},
        narrative=dict(src.narrative),
    )
    db.add(clone)
    db.commit()
    db.refresh(clone)
    return _record_summary(clone)


@router.delete("/training-reports/{report_id}")
def delete_training_report(report_id: str, db: Session = Depends(get_db), user: Optional[dict] = Depends(optional_auth)):
    from api.db.models import TrainingCourseReport
    rec = db.query(TrainingCourseReport).filter_by(id=report_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")
    report_dir = os.path.join(_STORAGE_ROOT, rec.id)
    db.delete(rec)
    db.commit()
    if os.path.isdir(report_dir):
        import shutil
        shutil.rmtree(report_dir, ignore_errors=True)
    return {"deleted": True}


def _download(path: Optional[str], filename: str) -> Response:
    if not path or not os.path.exists(path) or os.path.getsize(path) == 0:
        raise HTTPException(status_code=404, detail="File is not available. Generate the final report first.")
    with open(path, "rb") as fh:
        data = fh.read()
    ext = os.path.splitext(filename)[1]
    return Response(
        content=data,
        media_type=mime_for_ext(ext),
        headers={
            "Content-Disposition": content_disposition(filename),
            "Content-Length": str(len(data)),
        },
    )


@router.get("/training-reports/{report_id}/download/docx")
def download_docx(report_id: str, db: Session = Depends(get_db), user: Optional[dict] = Depends(optional_auth)):
    from api.db.models import TrainingCourseReport
    rec = db.query(TrainingCourseReport).filter_by(id=report_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")
    return _download(rec.docx_path, rec.docx_filename or f"Training_Report_{report_id[:8]}.docx")


@router.get("/training-reports/{report_id}/download/pdf")
def download_pdf(report_id: str, db: Session = Depends(get_db), user: Optional[dict] = Depends(optional_auth)):
    from api.db.models import TrainingCourseReport
    rec = db.query(TrainingCourseReport).filter_by(id=report_id).first()
    if not rec:
        raise HTTPException(status_code=404, detail="Report not found")
    pdf_name = (rec.docx_filename or f"Training_Report_{report_id[:8]}.docx")[:-5] + ".pdf"
    return _download(rec.pdf_path, pdf_name)
