"""
Microsoft Word desktop COM automation — mandatory final formatting pass.

Every translated DOCX produced by the Translation Studio must be opened in
the real, installed Microsoft Word desktop application (via COM automation)
so Word's own paragraph, table, list, and pagination engine performs the
final RTL/alignment/layout pass before the file is handed to the user.

This module is Windows-only and has no fallback renderer: if Word COM is
unavailable or a step fails, `WordAutomationError` is raised and the caller
must surface a clear backend error rather than silently returning
unfinalized (python-docx-only) bytes.

Do NOT use LibreOffice or python-docx as a substitute rendering authority
here — this module exists specifically to replace that gap with Word itself.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import re
import tempfile
import time
import uuid
from collections import defaultdict

from .office_com_availability import check_word_available, run_with_timeout

log = logging.getLogger(__name__)

_ARABIC_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿ]")
_RTL_LANGS = {"ar", "he", "fa", "ur"}

# WdParagraphAlignment
WD_ALIGN_LEFT = 0
WD_ALIGN_CENTER = 1
WD_ALIGN_RIGHT = 2
WD_ALIGN_JUSTIFY = 3

# WdReadingOrder
WD_READING_ORDER_LTR = 0
WD_READING_ORDER_RTL = 1

# WdTableDirection
WD_TABLE_DIRECTION_LTR = 0
WD_TABLE_DIRECTION_RTL = 1

# WdSaveOptions
WD_DO_NOT_SAVE_CHANGES = 0

# WdAlertLevel
WD_ALERTS_NONE = 0

# msoAutomationSecurity
MSO_AUTOMATION_SECURITY_FORCE_DISABLE = 3

# WdInformation
WD_WITH_IN_TABLE = 12

# Whole-attempt wall-clock ceiling (Dispatch + Open + edits + Save/Export, all
# on one worker thread — COM objects are single-apartment-threaded, so the
# timeout wraps the *entire* attempt rather than individual COM calls; see
# _run_attempt_with_timeout).
_ATTEMPT_TIMEOUT_S = 180.0


class WordAutomationError(RuntimeError):
    """Raised when Microsoft Word desktop COM automation is unavailable or fails."""


def word_com_available() -> bool:
    """Cheap, cached check for whether real Microsoft Word desktop COM
    automation can be used right now (Windows + pywin32 + Word installed)."""
    return check_word_available()


def _kill_new_pids(pids_before: set[int]) -> None:
    for pid in (_winword_pids() - pids_before):
        _kill_pid(pid)


def _run_attempt_with_timeout(fn, timeout_s: float, label: str):
    """
    Run one whole COM attempt (fn takes no args) in a worker thread bounded
    by timeout_s. All COM calls fn makes must stay on that single thread —
    COM interface pointers are not valid across threads without explicit
    marshaling, so this must never be used to split a single COM session's
    calls across multiple threads, only to bound one self-contained attempt
    (which itself does its own CoInitialize/.../CoUninitialize internally).

    On timeout, any WINWORD.EXE process that appeared during the attempt is
    force-killed — fn's own cleanup can't run if it's genuinely stuck inside
    a blocking COM call.
    """
    pids_before = _winword_pids()
    try:
        return run_with_timeout(fn, timeout_s, on_timeout_kill=lambda: _kill_new_pids(pids_before))
    except concurrent.futures.TimeoutError as exc:
        raise WordAutomationError(f"{label} exceeded {timeout_s:.0f}s and was treated as hung") from exc


def _is_rtl_lang(target_lang: str) -> bool:
    return (target_lang or "").strip().lower() in _RTL_LANGS


def _finalize_range_bulk(rng, is_rtl: bool) -> None:
    """
    Apply RTL reading order + right alignment to an entire Range in a single
    pair of COM calls, rather than looping paragraph-by-paragraph. Bulk
    Range-level formatting is both the idiomatic Word-automation approach and
    far more resilient — each additional per-paragraph COM round-trip is one
    more chance for Word's RPC channel to drop mid-automation.
    """
    if not is_rtl:
        return
    try:
        text = rng.Text or ""
    except Exception:
        text = ""
    if not text.strip() or not _ARABIC_RE.search(text):
        return
    pf = rng.ParagraphFormat
    pf.ReadingOrder = WD_READING_ORDER_RTL
    pf.Alignment = WD_ALIGN_RIGHT


def _center_headings(doc, is_rtl: bool) -> int:
    """Re-center heading/title-styled paragraphs after the bulk right-align pass."""
    if not is_rtl:
        return 0
    count = 0
    for paragraph in doc.Content.Paragraphs:
        try:
            style_name = str(paragraph.Range.Style.NameLocal or "").lower()
            if "heading" not in style_name and "title" not in style_name:
                continue
            text = paragraph.Range.Text or ""
            if not text.strip() or not _ARABIC_RE.search(text):
                continue
            paragraph.Range.ParagraphFormat.Alignment = WD_ALIGN_CENTER
            count += 1
        except Exception:
            log.debug("Word finalize: skipped one heading", exc_info=True)
    return count


def _finalize_headers_footers(doc, is_rtl: bool) -> None:
    for section in doc.Sections:
        for hf in section.Headers:
            try:
                if hf.Exists:
                    _finalize_range_bulk(hf.Range, is_rtl)
            except Exception:
                log.debug("Word finalize: header pass skipped", exc_info=True)
        for hf in section.Footers:
            try:
                if hf.Exists:
                    _finalize_range_bulk(hf.Range, is_rtl)
            except Exception:
                log.debug("Word finalize: footer pass skipped", exc_info=True)


def _winword_pids() -> set[int]:
    """Snapshot the PIDs of running WINWORD.EXE processes (best-effort)."""
    try:
        import psutil

        return {
            p.pid for p in psutil.process_iter(["name"])
            if (p.info.get("name") or "").lower() == "winword.exe"
        }
    except Exception:
        return set()


def _finalize_tables(doc, is_rtl: bool) -> None:
    """
    Mirror table direction for RTL. Table cell paragraphs are already covered
    by the bulk doc.Content pass (Content includes table-cell paragraphs), so
    there is no separate per-cell paragraph loop here — that redundant second
    pass over the same paragraphs was pure extra COM round-trip risk.
    """
    if not is_rtl:
        return
    try:
        tables = doc.Tables
    except Exception:
        return
    for table in tables:
        try:
            table.TableDirection = WD_TABLE_DIRECTION_RTL
        except Exception:
            log.debug("Word finalize: table direction skipped", exc_info=True)


def _kill_pid(pid: int | None) -> None:
    """Best-effort force-kill of an orphaned WINWORD.EXE process by pid."""
    if not pid:
        return
    try:
        import psutil

        proc = psutil.Process(pid)
        if proc.name().lower() == "winword.exe":
            proc.kill()
            log.info("Word COM: force-killed orphaned WINWORD.EXE (pid=%s)", pid)
    except Exception:
        pass


# ── Native translate-in-place (extraction + rebuild via real Word) ─────────

def _set_word_range_text(rng, new_text: str) -> None:
    """
    Replace a Range's visible text while preserving whatever terminating mark
    (paragraph mark / end-of-cell mark) sits at Range.End — assigning
    ``.Text`` on the *full* range including that mark deletes it and merges
    the paragraph/cell with whatever follows. Excluding the last character
    before assigning is the standard COM idiom for this.

    ``\\n`` in new_text (soft line breaks, matching doc_extractor's
    convention of joining <w:br/> as "\\n") is written as Chr(11) — Word's
    manual-line-break character within a paragraph.
    """
    rng.End = rng.End - 1
    rng.Text = new_text.replace("\n", "\x0b")


def _docx_body_para_lookup(segments: list[dict]) -> tuple[dict[int, dict[int, str]], dict[int, int]]:
    """
    Mirror doc_rebuilder.rebuild_docx's lookup-building for body paragraphs:
    para_lines[para_idx][line_idx] = text to write (target, or source for
    passthrough segments); para_total[para_idx] = soft-return line count.
    """
    para_lines: dict[int, dict[int, str]] = defaultdict(dict)
    para_total: dict[int, int] = {}
    for seg in segments:
        loc = seg.get("loc", {})
        if loc.get("format") != "docx" or seg.get("seg_type") != "paragraph":
            continue
        para_idx = loc.get("para_idx")
        if para_idx is None:
            continue
        line_idx = loc.get("line_idx", 0)
        total_ln = loc.get("total_lines", 1)
        target = (seg.get("target") or "").strip()
        if target or loc.get("passthrough"):
            para_lines[para_idx][line_idx] = target or seg.get("source", "")
        para_total[para_idx] = total_ln
    return para_lines, para_total


def translate_docx_with_word(
    original_bytes: bytes, segments: list[dict], target_lang: str, max_attempts: int = 3,
) -> bytes:
    """
    High-fidelity DOCX translation: opens the *original* file in real
    Microsoft Word via COM, writes translated text directly into Word's own
    live paragraph/table/header/footer objects (never a python-docx
    reconstruction), applies the existing RTL/alignment/table-direction
    finalization pass in the same session, saves, and returns the bytes.

    This is the native-fidelity backend for the Translation Studio's DOCX
    rebuild step — callers should fall back to
    ``doc_rebuilder.rebuild_docx`` + ``finalize_docx_with_word`` when this
    raises WordAutomationError (e.g. Word/COM unavailable).
    """
    last_exc: WordAutomationError | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return _run_attempt_with_timeout(
                lambda: _translate_docx_with_word_once(original_bytes, segments, target_lang, attempt),
                _ATTEMPT_TIMEOUT_S, "Word COM translate-in-place",
            )
        except WordAutomationError as exc:
            last_exc = exc
            log.warning("Word COM translate-in-place: attempt %d/%d failed: %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(1.5)
    raise last_exc  # type: ignore[misc]


def _translate_docx_with_word_once(
    original_bytes: bytes, segments: list[dict], target_lang: str, attempt: int,
) -> bytes:
    if os.name != "nt":
        raise WordAutomationError(
            "Microsoft Word desktop COM automation requires Windows; "
            "this server process is not running on Windows."
        )
    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise WordAutomationError(
            "pywin32 is not installed — Microsoft Word COM automation is unavailable."
        ) from exc

    is_rtl = _is_rtl_lang(target_lang)
    para_lines, para_total = _docx_body_para_lookup(segments)

    table_map: dict[tuple, str] = {}
    header_map: dict[tuple, str] = {}
    footer_map: dict[tuple, str] = {}
    for seg in segments:
        loc = seg.get("loc", {})
        if loc.get("format") != "docx":
            continue
        target = (seg.get("target") or "").strip()
        if not target:
            continue
        seg_type = seg.get("seg_type", "paragraph")
        if seg_type == "table_cell":
            table_map[(loc["tbl_idx"], loc["row_idx"], loc["col_idx"])] = target
        elif seg_type == "header":
            header_map[(loc["section"], loc["header_para"])] = target
        elif seg_type == "footer":
            footer_map[(loc["section"], loc["footer_para"])] = target

    tmp_dir = tempfile.mkdtemp(prefix="word_translate_")
    tmp_path = os.path.join(tmp_dir, f"translate_{uuid.uuid4().hex}.docx")
    with open(tmp_path, "wb") as fh:
        fh.write(original_bytes)

    pythoncom.CoInitialize()
    word = None
    doc = None
    word_pid = None
    t0 = time.time()
    try:
        _pids_before = _winword_pids()
        try:
            word = win32com.client.DispatchEx("Word.Application")
        except Exception as exc:
            raise WordAutomationError(f"Could not launch Microsoft Word desktop via COM: {exc}") from exc

        word.Visible = False
        word.DisplayAlerts = WD_ALERTS_NONE
        try:
            word.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
        except Exception:
            pass
        try:
            word.ScreenUpdating = False
        except Exception:
            pass

        _new_pids = _winword_pids() - _pids_before
        word_pid = next(iter(_new_pids)) if _new_pids else None

        log.info(
            "Word COM: launched WINWORD.EXE (pid=%s, attempt=%d) to translate-in-place %s (target_lang=%s, rtl=%s)",
            word_pid, attempt, tmp_path, target_lang, is_rtl,
        )

        try:
            doc = word.Documents.Open(
                tmp_path, ConfirmConversions=False, ReadOnly=False,
                AddToRecentFiles=False, Visible=False,
            )
        except Exception as exc:
            raise WordAutomationError(f"Microsoft Word failed to open the original DOCX: {exc}") from exc

        try:
            # ── Body paragraphs — walk Word's own Paragraphs collection,
            # skipping any paragraph that lives inside a table (Word's
            # collection interleaves table paragraphs by document position;
            # doc_extractor.extract_docx's para_idx only counts body
            # paragraphs, matching python-docx's doc.paragraphs). ──────────
            body_idx = 0
            n_written = 0
            for com_para in doc.Paragraphs:
                try:
                    in_table = bool(com_para.Range.Information(WD_WITH_IN_TABLE))
                except Exception:
                    in_table = False
                if in_table:
                    continue
                line_map = para_lines.get(body_idx)
                if line_map:
                    total_lines = para_total.get(body_idx, 1)
                    lines_out = [line_map.get(li, "") for li in range(total_lines)]
                    new_text = "\n".join(lines_out).strip("\n")
                    if new_text:
                        try:
                            _set_word_range_text(com_para.Range, new_text)
                            n_written += 1
                        except Exception:
                            log.debug("Word translate: skipped one body paragraph (idx=%d)", body_idx, exc_info=True)
                body_idx += 1

            # ── Table cells ──────────────────────────────────────────────
            for (tbl_idx, row_idx, col_idx), text in table_map.items():
                try:
                    cell = doc.Tables(tbl_idx + 1).Cell(row_idx + 1, col_idx + 1)
                    _set_word_range_text(cell.Range, text)
                except Exception:
                    log.debug(
                        "Word translate: skipped table cell tbl=%d row=%d col=%d",
                        tbl_idx, row_idx, col_idx, exc_info=True,
                    )

            # ── Headers / footers (primary only — matches doc_extractor,
            # which only reads section.header/section.footer). ─────────────
            WD_HEADER_FOOTER_PRIMARY = 1
            for (sec_idx, hdr_para_idx), text in header_map.items():
                try:
                    section = doc.Sections(sec_idx + 1)
                    header = section.Headers(WD_HEADER_FOOTER_PRIMARY)
                    para = header.Range.Paragraphs(hdr_para_idx + 1)
                    _set_word_range_text(para.Range, text)
                except Exception:
                    log.debug("Word translate: skipped header sec=%d para=%d", sec_idx, hdr_para_idx, exc_info=True)

            for (sec_idx, ftr_para_idx), text in footer_map.items():
                try:
                    section = doc.Sections(sec_idx + 1)
                    footer = section.Footers(WD_HEADER_FOOTER_PRIMARY)
                    para = footer.Range.Paragraphs(ftr_para_idx + 1)
                    _set_word_range_text(para.Range, text)
                except Exception:
                    log.debug("Word translate: skipped footer sec=%d para=%d", sec_idx, ftr_para_idx, exc_info=True)

            # ── Same finalization pass as finalize_docx_with_word — RTL,
            # heading centering, header/footer RTL, table direction. ───────
            _finalize_range_bulk(doc.Content, is_rtl)
            n_headings = _center_headings(doc, is_rtl)
            _finalize_headers_footers(doc, is_rtl)
            _finalize_tables(doc, is_rtl)
            doc.Repaginate()
            doc.Save()
        except Exception as exc:
            raise WordAutomationError(f"Microsoft Word translate-in-place failed: {exc}") from exc

        with open(tmp_path, "rb") as fh:
            result_bytes = fh.read()

        log.info(
            "Word COM: translated-in-place %s (pid=%s, %d body paragraph(s) written, %d heading(s) "
            "centered, %d bytes, elapsed=%.2fs)",
            tmp_path, word_pid, n_written, n_headings, len(result_bytes), time.time() - t0,
        )
        return result_bytes

    finally:
        _quit_ok = False
        try:
            if doc is not None:
                doc.Close(SaveChanges=WD_DO_NOT_SAVE_CHANGES)
        except Exception:
            log.warning("Word COM translate-in-place: failed to close document cleanly", exc_info=True)
        try:
            if word is not None:
                word.Quit()
                _quit_ok = True
        except Exception:
            log.warning("Word COM translate-in-place: failed to quit Word application cleanly", exc_info=True)
        if not _quit_ok:
            _kill_pid(word_pid)
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except Exception:
            pass


def convert_docx_to_pdf_with_word(docx_bytes: bytes, max_attempts: int = 3) -> bytes:
    """
    Convert a DOCX to PDF using the installed Microsoft Word desktop
    application via COM automation (``ExportAsFixedFormat``), so the PDF is
    laid out by the same rendering engine that will open the DOCX for the
    user — not a third-party re-implementation like LibreOffice/WeasyPrint.

    Windows-only; raises WordAutomationError if Word COM is unavailable or a
    step fails, mirroring finalize_docx_with_word's retry behaviour.
    """
    last_exc: WordAutomationError | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return _run_attempt_with_timeout(
                lambda: _convert_docx_to_pdf_once(docx_bytes, attempt),
                _ATTEMPT_TIMEOUT_S, "Word COM PDF export",
            )
        except WordAutomationError as exc:
            last_exc = exc
            log.warning("Word COM PDF export: attempt %d/%d failed: %s", attempt, max_attempts, exc)
            if attempt < max_attempts:
                time.sleep(1.5)
    raise last_exc  # type: ignore[misc]


def _convert_docx_to_pdf_once(docx_bytes: bytes, attempt: int) -> bytes:
    if os.name != "nt":
        raise WordAutomationError(
            "Microsoft Word desktop COM automation requires Windows; "
            "this server process is not running on Windows."
        )

    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise WordAutomationError(
            "pywin32 is not installed — Microsoft Word COM automation is unavailable."
        ) from exc

    WD_EXPORT_FORMAT_PDF = 17

    tmp_dir = tempfile.mkdtemp(prefix="word_pdf_export_")
    docx_path = os.path.join(tmp_dir, f"source_{uuid.uuid4().hex}.docx")
    pdf_path = os.path.join(tmp_dir, f"output_{uuid.uuid4().hex}.pdf")
    with open(docx_path, "wb") as fh:
        fh.write(docx_bytes)

    pythoncom.CoInitialize()
    word = None
    doc = None
    word_pid = None
    t0 = time.time()
    try:
        _pids_before = _winword_pids()
        try:
            word = win32com.client.DispatchEx("Word.Application")
        except Exception as exc:
            raise WordAutomationError(
                f"Could not launch Microsoft Word desktop via COM: {exc}"
            ) from exc

        word.Visible = False
        word.DisplayAlerts = WD_ALERTS_NONE
        try:
            word.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
        except Exception:
            pass

        _new_pids = _winword_pids() - _pids_before
        word_pid = next(iter(_new_pids)) if _new_pids else None

        log.info(
            "Word COM: launched WINWORD.EXE (pid=%s, attempt=%d) to export PDF for %s",
            word_pid, attempt, docx_path,
        )

        try:
            doc = word.Documents.Open(
                docx_path,
                ConfirmConversions=False,
                ReadOnly=False,
                AddToRecentFiles=False,
                Visible=False,
            )
        except Exception as exc:
            raise WordAutomationError(
                f"Microsoft Word failed to open the DOCX for PDF export: {exc}"
            ) from exc

        try:
            doc.ExportAsFixedFormat(OutputFileName=pdf_path, ExportFormat=WD_EXPORT_FORMAT_PDF)
        except Exception as exc:
            raise WordAutomationError(f"Microsoft Word PDF export failed: {exc}") from exc

        if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) == 0:
            raise WordAutomationError("Microsoft Word produced an empty or missing PDF file.")

        with open(pdf_path, "rb") as fh:
            result_bytes = fh.read()

        log.info(
            "Word COM: exported PDF %s (pid=%s, %d bytes, elapsed=%.2fs)",
            pdf_path, word_pid, len(result_bytes), time.time() - t0,
        )
        return result_bytes

    finally:
        _quit_ok = False
        try:
            if doc is not None:
                doc.Close(SaveChanges=WD_DO_NOT_SAVE_CHANGES)
        except Exception:
            log.warning("Word COM PDF export: failed to close document cleanly", exc_info=True)
        try:
            if word is not None:
                word.Quit()
                _quit_ok = True
        except Exception:
            log.warning("Word COM PDF export: failed to quit Word application cleanly", exc_info=True)
        if not _quit_ok:
            _kill_pid(word_pid)
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        try:
            os.remove(docx_path)
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


def finalize_docx_with_word(docx_bytes: bytes, target_lang: str, max_attempts: int = 3) -> bytes:
    """
    Mandatory final formatting pass for a translated DOCX.

    Launches the installed Microsoft Word desktop application invisibly via
    COM automation, opens the document, applies Word's own document engine
    to finalize RTL direction, paragraph/title alignment, table direction,
    and pagination, saves it from Word, and returns the Word-saved bytes.

    A single COM/RPC hiccup against a freshly launched Word instance is
    retried once with a brand-new Word process (still Word — never another
    renderer) since Office COM automation is known to occasionally drop the
    RPC channel on first contact. Raises WordAutomationError only after all
    attempts are exhausted — callers must NOT fall back to another renderer.
    """
    last_exc: WordAutomationError | None = None
    for attempt in range(1, max(1, max_attempts) + 1):
        try:
            return _run_attempt_with_timeout(
                lambda: _finalize_docx_with_word_once(docx_bytes, target_lang, attempt),
                _ATTEMPT_TIMEOUT_S, "Word COM finalize",
            )
        except WordAutomationError as exc:
            last_exc = exc
            log.warning(
                "Word COM: attempt %d/%d failed: %s", attempt, max_attempts, exc
            )
            if attempt < max_attempts:
                time.sleep(1.5)
    raise last_exc  # type: ignore[misc]


def _finalize_docx_with_word_once(docx_bytes: bytes, target_lang: str, attempt: int) -> bytes:
    if os.name != "nt":
        raise WordAutomationError(
            "Microsoft Word desktop COM automation requires Windows; "
            "this server process is not running on Windows."
        )

    try:
        import pythoncom
        import win32com.client
    except ImportError as exc:
        raise WordAutomationError(
            "pywin32 is not installed — Microsoft Word COM automation is unavailable."
        ) from exc

    is_rtl = _is_rtl_lang(target_lang)

    tmp_dir = tempfile.mkdtemp(prefix="word_finalize_")
    tmp_path = os.path.join(tmp_dir, f"finalize_{uuid.uuid4().hex}.docx")
    with open(tmp_path, "wb") as fh:
        fh.write(docx_bytes)

    pythoncom.CoInitialize()
    word = None
    doc = None
    word_pid = None
    t0 = time.time()
    try:
        _pids_before = _winword_pids()
        try:
            word = win32com.client.DispatchEx("Word.Application")
        except Exception as exc:
            raise WordAutomationError(
                f"Could not launch Microsoft Word desktop via COM: {exc}"
            ) from exc

        word.Visible = False
        word.DisplayAlerts = WD_ALERTS_NONE
        try:
            word.AutomationSecurity = MSO_AUTOMATION_SECURITY_FORCE_DISABLE
        except Exception:
            pass
        try:
            word.ScreenUpdating = False
        except Exception:
            pass

        _new_pids = _winword_pids() - _pids_before
        word_pid = next(iter(_new_pids)) if _new_pids else None

        log.info(
            "Word COM: launched WINWORD.EXE (pid=%s, attempt=%d) to finalize %s (target_lang=%s, rtl=%s)",
            word_pid, attempt, tmp_path, target_lang, is_rtl,
        )

        try:
            doc = word.Documents.Open(
                tmp_path,
                ConfirmConversions=False,
                ReadOnly=False,
                AddToRecentFiles=False,
                Visible=False,
            )
        except Exception as exc:
            raise WordAutomationError(
                f"Microsoft Word failed to open the translated DOCX: {exc}"
            ) from exc

        try:
            _finalize_range_bulk(doc.Content, is_rtl)
            n_headings = _center_headings(doc, is_rtl)
            _finalize_headers_footers(doc, is_rtl)
            _finalize_tables(doc, is_rtl)
            doc.Repaginate()
            doc.Save()
        except Exception as exc:
            raise WordAutomationError(
                f"Microsoft Word layout finalization failed: {exc}"
            ) from exc

        with open(tmp_path, "rb") as fh:
            result_bytes = fh.read()

        mtime = os.path.getmtime(tmp_path)
        log.info(
            "Word COM: finalized and saved %s (pid=%s, %d heading(s) centered, %d bytes, "
            "mtime=%s, elapsed=%.2fs)",
            tmp_path, word_pid, n_headings, len(result_bytes), time.ctime(mtime), time.time() - t0,
        )

        return result_bytes

    finally:
        _quit_ok = False
        try:
            if doc is not None:
                doc.Close(SaveChanges=WD_DO_NOT_SAVE_CHANGES)
        except Exception:
            log.warning("Word COM: failed to close document cleanly", exc_info=True)
        try:
            if word is not None:
                word.Quit()
                log.info("Word COM: WINWORD.EXE (pid=%s) quit", word_pid)
                _quit_ok = True
        except Exception:
            log.warning("Word COM: failed to quit Word application cleanly", exc_info=True)
        if not _quit_ok:
            # Graceful Quit() failed (typically because Word already crashed) —
            # force-kill the orphaned process so it cannot corrupt a retry.
            _kill_pid(word_pid)
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass
        try:
            os.remove(tmp_path)
            os.rmdir(tmp_dir)
        except Exception:
            pass
