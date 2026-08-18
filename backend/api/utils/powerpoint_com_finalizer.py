"""
Microsoft PowerPoint desktop COM automation — native-fidelity PPTX
translation backend, mirroring ``word_com_finalizer.py``'s structure for
Word.

Every translated PPTX produced by this module is written directly into the
real, installed Microsoft PowerPoint desktop application's own live shape/
paragraph/table objects — never a python-pptx reconstruction — so themes,
masters, animations, transitions, images, and layout are preserved exactly
as PowerPoint itself keeps them.

This module is Windows-only and has no fallback renderer: if PowerPoint COM
is unavailable or a step fails, ``PowerPointAutomationError`` is raised and
the caller must fall back to the existing python-pptx-based
``doc_rebuilder.rebuild_pptx`` path rather than silently claiming native
fidelity.

Known limitation: PowerPoint's COM object model has no equivalent of Word's
``Table.TableDirection`` — RTL is applied per-paragraph (alignment + base
text direction via TextFrame2) but table column order is not mirrored for
RTL languages the way the python-pptx fallback path's raw-XML ``tblPr
rtl="1"`` manipulation does.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import tempfile
import time
import uuid

from .office_com_availability import check_powerpoint_available, run_with_timeout

log = logging.getLogger(__name__)

_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿ]")
_RTL_LANGS = {"ar", "he", "fa", "ur"}

# MsoShapeType
MSO_GROUP = 6

# PpParagraphAlignment
PP_ALIGN_LEFT = 1
PP_ALIGN_CENTER = 2
PP_ALIGN_RIGHT = 3

# MsoTextDirection (TextFrame2)
MSO_TEXT_DIRECTION_LTR = 1
MSO_TEXT_DIRECTION_RTL = 2

# PpSaveAsFileType
PP_SAVE_AS_PDF = 32

# Whole-attempt wall-clock ceiling — see word_com_finalizer._run_attempt_with_timeout
# for why this wraps the entire attempt rather than individual COM calls
# (COM objects are single-apartment-threaded).
_ATTEMPT_TIMEOUT_S = 180.0


class PowerPointAutomationError(RuntimeError):
    """Raised when Microsoft PowerPoint desktop COM automation is unavailable or fails."""


def powerpoint_com_available() -> bool:
    """Cheap, cached check for whether real Microsoft PowerPoint desktop COM
    automation can be used right now (Windows + pywin32 + PowerPoint installed)."""
    return check_powerpoint_available()


def _kill_new_pids(pids_before: set[int]) -> None:
    for pid in (_powerpnt_pids() - pids_before):
        _kill_pid(pid)


def _run_attempt_with_timeout(fn, timeout_s: float, label: str):
    """Run one whole COM attempt (fn takes no args, self-contained
    CoInitialize/.../CoUninitialize) in a worker thread bounded by
    timeout_s. See word_com_finalizer._run_attempt_with_timeout — the same
    single-apartment-threading constraint applies here."""
    pids_before = _powerpnt_pids()
    try:
        return run_with_timeout(fn, timeout_s, on_timeout_kill=lambda: _kill_new_pids(pids_before))
    except concurrent.futures.TimeoutError as exc:
        raise PowerPointAutomationError(f"{label} exceeded {timeout_s:.0f}s and was treated as hung") from exc


def _is_rtl_lang(target_lang: str) -> bool:
    return (target_lang or "").strip().lower() in _RTL_LANGS


def _powerpnt_pids() -> set[int]:
    """Snapshot the PIDs of running POWERPNT.EXE processes (best-effort)."""
    try:
        import psutil

        return {
            p.pid for p in psutil.process_iter(["name"])
            if (p.info.get("name") or "").lower() == "powerpnt.exe"
        }
    except Exception:
        return set()


def _kill_pid(pid: int | None) -> None:
    """Best-effort force-kill of an orphaned POWERPNT.EXE process by pid."""
    if not pid:
        return
    try:
        import psutil

        proc = psutil.Process(pid)
        if proc.name().lower() == "powerpnt.exe":
            proc.kill()
            log.info("PowerPoint COM: force-killed orphaned POWERPNT.EXE (pid=%s)", pid)
    except Exception:
        pass


def _apply_rtl_to_paragraph(paragraph_text_range, is_rtl: bool) -> None:
    """Best-effort RTL application for one paragraph — alignment via the
    classic TextRange API, base text direction via TextFrame2 when the host
    shape supports it (tables/some placeholders may not)."""
    if not is_rtl:
        return
    try:
        text = paragraph_text_range.Text or ""
    except Exception:
        text = ""
    if not text.strip() or not _ARABIC_RE.search(text):
        return
    try:
        paragraph_text_range.ParagraphFormat.Alignment = PP_ALIGN_RIGHT
    except Exception:
        log.debug("PPT finalize: paragraph alignment skipped", exc_info=True)


def _apply_rtl_base_direction(shape, is_rtl: bool) -> None:
    """Set BaseTextDirection on every paragraph via the newer TextFrame2
    model — not all shapes expose it, so this is fully best-effort."""
    if not is_rtl:
        return
    try:
        tf2 = shape.TextFrame2
        for para in tf2.TextRange.Paragraphs:
            try:
                text = para.Text or ""
            except Exception:
                text = ""
            if text.strip() and _ARABIC_RE.search(text):
                try:
                    para.ParagraphFormat.BaseTextDirection = MSO_TEXT_DIRECTION_RTL
                except Exception:
                    pass
    except Exception:
        log.debug("PPT finalize: TextFrame2 base text direction skipped", exc_info=True)


# ── Native translate-in-place (extraction + rebuild via real PowerPoint) ────

def _build_pptx_lookup_maps(segments: list[dict]) -> tuple[dict, dict, dict]:
    """Mirror doc_rebuilder.rebuild_pptx's lookup-building — mapping
    (slide_idx, shape_idx, para_idx) / (slide_idx, shape_idx, row_idx,
    col_idx) / slide_idx to translated text, ignoring style-profile/layout
    concerns (PowerPoint itself owns layout in this backend)."""
    text_map: dict[tuple, str] = {}
    table_map: dict[tuple, str] = {}
    notes_map: dict[int, str] = {}

    for seg in segments:
        target = (seg.get("target") or "").strip()
        if not target:
            continue
        loc = seg.get("loc", {})
        if loc.get("format") != "pptx":
            continue
        if seg.get("seg_type") == "image_text":
            continue
        # Be tolerant of segments whose loc lacks the positional keys this native
        # backend needs (e.g. non-standard extractor output). Skip them rather
        # than KeyError-crashing the whole job — the caller falls back to the
        # python-pptx rebuild, which uses its own placement logic.
        slide_idx = loc.get("slide_idx")
        if slide_idx is None:
            continue
        if loc.get("notes"):
            notes_map[slide_idx] = target
        elif loc.get("table_cell"):
            if all(k in loc for k in ("shape_idx", "row_idx", "col_idx")):
                table_map[(slide_idx, loc["shape_idx"], loc["row_idx"], loc["col_idx"])] = target
        elif "shape_idx" in loc and "para_idx" in loc:
            text_map[(slide_idx, loc["shape_idx"], loc["para_idx"])] = target

    return text_map, table_map, notes_map


def _walk_com_shapes(shapes_col, slide_idx: int, base_shape_idx, text_map, table_map, is_rtl: bool, counters: dict) -> None:
    """
    Recursively walk a PowerPoint Shapes/GroupItems collection, writing
    translated text into whatever shape_idx/table_cell keys the segment
    lookup maps have — mirroring doc_extractor.extract_pptx's shape_idx
    scheme exactly (top-level shapes numbered by enumerate() position; group
    children numbered ``outer_shape_idx * 10000 + child_idx``), so no
    separate off-slide/type-classification pass is needed here: a shape
    simply gets no write if no segment ever referenced its key.
    """
    for idx0 in range(shapes_col.Count):
        shape = shapes_col.Item(idx0 + 1)
        shape_idx = idx0 if base_shape_idx is None else base_shape_idx * 10000 + idx0

        try:
            is_group = int(shape.Type) == MSO_GROUP
        except Exception:
            is_group = False
        if is_group:
            try:
                _walk_com_shapes(shape.GroupItems, slide_idx, shape_idx, text_map, table_map, is_rtl, counters)
            except Exception:
                log.debug("PPT translate: slide %d group %d unreadable", slide_idx + 1, shape_idx, exc_info=True)
            continue

        has_table = False
        try:
            has_table = bool(shape.HasTable)
        except Exception:
            pass
        if has_table:
            try:
                table = shape.Table
                for row_idx in range(table.Rows.Count):
                    for col_idx in range(table.Columns.Count):
                        key = (slide_idx, shape_idx, row_idx, col_idx)
                        target = table_map.get(key)
                        if not target:
                            continue
                        cell = table.Cell(row_idx + 1, col_idx + 1)
                        tr = cell.Shape.TextFrame.TextRange
                        tr.Text = target
                        _apply_rtl_to_paragraph(tr, is_rtl)
                        _apply_rtl_base_direction(cell.Shape, is_rtl)
                        counters["written"] += 1
            except Exception:
                log.debug("PPT translate: slide %d shape %d table unreadable", slide_idx + 1, shape_idx, exc_info=True)
            continue

        has_tf = False
        try:
            has_tf = bool(shape.HasTextFrame)
        except Exception:
            pass
        if not has_tf:
            continue

        try:
            tf = shape.TextFrame
            paragraphs = tf.TextRange.Paragraphs()
            n_paras = paragraphs.Count
        except Exception:
            continue

        wrote_any = False
        for para_idx in range(n_paras):
            key = (slide_idx, shape_idx, para_idx)
            target = text_map.get(key)
            if not target:
                continue
            try:
                pr = tf.TextRange.Paragraphs(para_idx + 1, 1)
                pr.Text = target
                _apply_rtl_to_paragraph(pr, is_rtl)
                counters["written"] += 1
                wrote_any = True
            except Exception:
                log.debug("PPT translate: slide %d shape %d para %d write failed", slide_idx + 1, shape_idx, para_idx, exc_info=True)
        if wrote_any:
            _apply_rtl_base_direction(shape, is_rtl)


def translate_pptx_with_powerpoint(
    original_bytes: bytes, segments: list[dict], target_lang: str, max_attempts: int = 3,
) -> bytes:
    """
    High-fidelity PPTX translation: opens the *original* file in real
    Microsoft PowerPoint via COM, writes translated text directly into
    PowerPoint's own live shape/paragraph/table objects (never a
    python-pptx reconstruction), applies best-effort RTL, saves, and
    returns the bytes.

    Callers should fall back to ``doc_rebuilder.rebuild_pptx`` when this
    raises PowerPointAutomationError (e.g. PowerPoint/COM unavailable).
    """
    last_exc: PowerPointAutomationError | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return _run_attempt_with_timeout(
                lambda: _translate_pptx_with_powerpoint_once(original_bytes, segments, target_lang, attempt),
                _ATTEMPT_TIMEOUT_S, "PowerPoint COM translate-in-place",
            )
        except PowerPointAutomationError as exc:
            last_exc = exc
            log.warning("PowerPoint COM translate-in-place: attempt %d/%d failed: %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(1.5)
    raise last_exc  # type: ignore[misc]


def _translate_pptx_with_powerpoint_once(
    original_bytes: bytes, segments: list[dict], target_lang: str, attempt: int,
) -> bytes:
    if os.name != "nt":
        raise PowerPointAutomationError(
            "Microsoft PowerPoint desktop COM automation requires Windows; "
            "this server process is not running on Windows."
        )
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise PowerPointAutomationError(
            "pywin32 is not installed — Microsoft PowerPoint COM automation is unavailable."
        ) from exc

    is_rtl = _is_rtl_lang(target_lang)
    text_map, table_map, notes_map = _build_pptx_lookup_maps(segments)

    tmp_dir = tempfile.mkdtemp(prefix="ppt_translate_")
    tmp_path = os.path.join(tmp_dir, f"translate_{uuid.uuid4().hex}.pptx")
    with open(tmp_path, "wb") as fh:
        fh.write(original_bytes)

    pythoncom.CoInitialize()
    ppt = None
    prs = None
    ppt_pid = None
    t0 = time.time()
    counters = {"written": 0}
    try:
        _pids_before = _powerpnt_pids()
        try:
            ppt = win32com.client.DispatchEx("PowerPoint.Application")
        except Exception as exc:
            raise PowerPointAutomationError(f"Could not launch Microsoft PowerPoint desktop via COM: {exc}") from exc

        # PowerPoint's COM automation does not support a fully headless
        # Application.Visible = False the way Word does — Presentations
        # opened with WithWindow=False keep the app itself out of the
        # foreground, which is the practical equivalent used here.
        try:
            ppt.DisplayAlerts = 0  # ppAlertsNone
        except Exception:
            pass

        _new_pids = _powerpnt_pids() - _pids_before
        ppt_pid = next(iter(_new_pids)) if _new_pids else None

        log.info(
            "PowerPoint COM: launched POWERPNT.EXE (pid=%s, attempt=%d) to translate-in-place %s (target_lang=%s, rtl=%s)",
            ppt_pid, attempt, tmp_path, target_lang, is_rtl,
        )

        try:
            prs = ppt.Presentations.Open(tmp_path, WithWindow=False)
        except Exception as exc:
            raise PowerPointAutomationError(f"Microsoft PowerPoint failed to open the original PPTX: {exc}") from exc

        try:
            for slide_idx in range(prs.Slides.Count):
                slide = prs.Slides.Item(slide_idx + 1)
                _walk_com_shapes(slide.Shapes, slide_idx, None, text_map, table_map, is_rtl, counters)

                notes_text = notes_map.get(slide_idx)
                if notes_text:
                    try:
                        notes_page = slide.NotesPage
                        for shp_idx in range(notes_page.Shapes.Count):
                            shp = notes_page.Shapes.Item(shp_idx + 1)
                            is_body = False
                            try:
                                is_body = shp.PlaceholderFormat.Type == 2  # ppPlaceholderBody
                            except Exception:
                                pass
                            if is_body and bool(shp.HasTextFrame):
                                shp.TextFrame.TextRange.Text = notes_text
                                counters["written"] += 1
                                break
                    except Exception:
                        log.debug("PPT translate: slide %d notes write failed", slide_idx + 1, exc_info=True)

            prs.Save()
        except Exception as exc:
            raise PowerPointAutomationError(f"Microsoft PowerPoint translate-in-place failed: {exc}") from exc

        with open(tmp_path, "rb") as fh:
            result_bytes = fh.read()

        log.info(
            "PowerPoint COM: translated-in-place %s (pid=%s, %d paragraph/cell(s) written, %d bytes, elapsed=%.2fs)",
            tmp_path, ppt_pid, counters["written"], len(result_bytes), time.time() - t0,
        )
        return result_bytes

    finally:
        _quit_ok = False
        try:
            if prs is not None:
                prs.Close()
        except Exception:
            log.warning("PowerPoint COM translate-in-place: failed to close presentation cleanly", exc_info=True)
        try:
            if ppt is not None:
                ppt.Quit()
                _quit_ok = True
        except Exception:
            log.warning("PowerPoint COM translate-in-place: failed to quit PowerPoint application cleanly", exc_info=True)
        if not _quit_ok:
            _kill_pid(ppt_pid)
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except Exception:
            pass


def convert_pptx_to_pdf_with_powerpoint(pptx_bytes: bytes, max_attempts: int = 3) -> bytes:
    """
    Convert a PPTX to PDF using the installed Microsoft PowerPoint desktop
    application via COM automation, so the PDF is laid out by the same
    rendering engine that will open the PPTX for the user.

    Windows-only; raises PowerPointAutomationError if PowerPoint COM is
    unavailable or a step fails.
    """
    last_exc: PowerPointAutomationError | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return _run_attempt_with_timeout(
                lambda: _convert_pptx_to_pdf_once(pptx_bytes, attempt),
                _ATTEMPT_TIMEOUT_S, "PowerPoint COM PDF export",
            )
        except PowerPointAutomationError as exc:
            last_exc = exc
            log.warning("PowerPoint COM PDF export: attempt %d/%d failed: %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(1.5)
    raise last_exc  # type: ignore[misc]


def _convert_pptx_to_pdf_once(pptx_bytes: bytes, attempt: int) -> bytes:
    if os.name != "nt":
        raise PowerPointAutomationError(
            "Microsoft PowerPoint desktop COM automation requires Windows; "
            "this server process is not running on Windows."
        )
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise PowerPointAutomationError(
            "pywin32 is not installed — Microsoft PowerPoint COM automation is unavailable."
        ) from exc

    tmp_dir = tempfile.mkdtemp(prefix="ppt_pdf_export_")
    pptx_path = os.path.join(tmp_dir, f"source_{uuid.uuid4().hex}.pptx")
    pdf_path = os.path.join(tmp_dir, f"output_{uuid.uuid4().hex}.pdf")
    with open(pptx_path, "wb") as fh:
        fh.write(pptx_bytes)

    pythoncom.CoInitialize()
    ppt = None
    prs = None
    ppt_pid = None
    t0 = time.time()
    try:
        _pids_before = _powerpnt_pids()
        try:
            ppt = win32com.client.DispatchEx("PowerPoint.Application")
        except Exception as exc:
            raise PowerPointAutomationError(f"Could not launch Microsoft PowerPoint desktop via COM: {exc}") from exc
        try:
            ppt.DisplayAlerts = 0
        except Exception:
            pass

        _new_pids = _powerpnt_pids() - _pids_before
        ppt_pid = next(iter(_new_pids)) if _new_pids else None

        log.info("PowerPoint COM: launched POWERPNT.EXE (pid=%s, attempt=%d) to export PDF for %s", ppt_pid, attempt, pptx_path)

        try:
            prs = ppt.Presentations.Open(pptx_path, WithWindow=False)
        except Exception as exc:
            raise PowerPointAutomationError(f"Microsoft PowerPoint failed to open the PPTX for PDF export: {exc}") from exc

        try:
            prs.SaveAs(pdf_path, PP_SAVE_AS_PDF)
        except Exception as exc:
            raise PowerPointAutomationError(f"Microsoft PowerPoint PDF export failed: {exc}") from exc

        if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
            raise PowerPointAutomationError("Microsoft PowerPoint produced an empty or missing PDF file.")

        with open(pdf_path, "rb") as fh:
            result_bytes = fh.read()

        log.info("PowerPoint COM: exported PDF %s (pid=%s, %d bytes, elapsed=%.2fs)", pdf_path, ppt_pid, len(result_bytes), time.time() - t0)
        return result_bytes

    finally:
        _quit_ok = False
        try:
            if prs is not None:
                prs.Close()
        except Exception:
            log.warning("PowerPoint COM PDF export: failed to close presentation cleanly", exc_info=True)
        try:
            if ppt is not None:
                ppt.Quit()
                _quit_ok = True
        except Exception:
            log.warning("PowerPoint COM PDF export: failed to quit PowerPoint application cleanly", exc_info=True)
        if not _quit_ok:
            _kill_pid(ppt_pid)
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        try:
            os.remove(pptx_path)
        except Exception:
            pass
        try:
            os.remove(pdf_path)
        except Exception:
            pass
        try:
            os.rmdir(tmp_dir)
        except Exception:
            pass
