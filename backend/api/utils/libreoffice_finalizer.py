"""
LibreOffice (headless) finalizer — the cross-platform layout authority used
when Microsoft Office desktop COM automation is unavailable (i.e. on the Linux
deployment target).

Word/PowerPoint COM (``word_com_finalizer`` / ``powerpoint_com_finalizer``) is
Windows-only. On a Linux server that hardware isn't there, so this module drives
a headless LibreOffice process instead:

  • ``finalize_docx_with_libreoffice`` — round-trips a rebuilt DOCX through LO so
    its Writer engine recomputes layout/pagination and normalizes the file. The
    RTL/alignment for Arabic is already written into the DOCX XML by
    ``doc_rebuilder.rebuild_docx``; LO honors those settings, this pass finalizes
    the layout the way Word's finalize pass does on Windows.
  • ``convert_docx_to_pdf_with_libreoffice`` / ``convert_pptx_to_pdf_with_libreoffice``
    — fixed-layout PDF export via LO.

Design mirrors the COM finalizers so a dispatcher can pick an engine uniformly:
same "available()" probe + same "<verb>_with_<engine>" naming + a dedicated
``LibreOfficeError`` raised on any failure (no silent unfinalized bytes).

Concurrency: each invocation uses its own throwaway ``-env:UserInstallation``
profile directory, so multiple conversions can run at once without LO's global
single-profile lock serializing (or corrupting) them.
"""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path

log = logging.getLogger(__name__)

# Whole-conversion wall-clock ceiling (launch + load + convert + write).
_CONVERT_TIMEOUT_S = 180.0

# Cache the availability probe briefly so a burst of exports doesn't re-scan
# the filesystem / spawn a probe process on every call.
_CACHE_TTL_S = 60.0
_avail_cache: tuple[float, str | None] | None = None


class LibreOfficeError(RuntimeError):
    """Raised when headless LibreOffice is unavailable or a conversion fails."""


def _candidate_binaries() -> list[str]:
    """Ordered list of soffice/libreoffice paths to try."""
    cands: list[str] = []
    env = (os.environ.get("LIBREOFFICE_PATH") or os.environ.get("SOFFICE_PATH") or "").strip()
    if env:
        cands.append(env)
    # On PATH (Linux/macOS, and Windows if added)
    for name in ("soffice", "libreoffice"):
        found = shutil.which(name)
        if found:
            cands.append(found)
    # Common absolute locations
    cands += [
        "/usr/bin/soffice",
        "/usr/bin/libreoffice",
        "/opt/libreoffice/program/soffice",
        "/snap/bin/libreoffice",
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ]
    # De-duplicate while preserving order
    seen: set[str] = set()
    out: list[str] = []
    for c in cands:
        if c and c not in seen and os.path.isfile(c):
            seen.add(c)
            out.append(c)
    return out


def _resolve_soffice_uncached() -> str | None:
    for path in _candidate_binaries():
        return path  # first existing candidate wins
    return None


def soffice_path() -> str | None:
    """Return a usable soffice/libreoffice executable path, or None. Cached."""
    global _avail_cache
    now = time.time()
    if _avail_cache is not None and (now - _avail_cache[0]) < _CACHE_TTL_S:
        return _avail_cache[1]
    path = _resolve_soffice_uncached()
    _avail_cache = (now, path)
    return path


def libreoffice_available() -> bool:
    """Cheap, cached check for whether headless LibreOffice can be used."""
    return soffice_path() is not None


def clear_availability_cache() -> None:
    """Test/ops hook — force the next probe to re-scan for the binary."""
    global _avail_cache
    _avail_cache = None


def _run_convert(input_bytes: bytes, in_ext: str, convert_to: str, out_ext: str, label: str) -> bytes:
    """
    Convert ``input_bytes`` (an ``in_ext`` document) to ``out_ext`` via a
    headless LibreOffice ``--convert-to`` run, and return the output bytes.

    ``convert_to`` is LO's --convert-to argument, e.g. ``docx:"MS Word 2007 XML"``
    or ``pdf``. Raises LibreOfficeError on any failure.
    """
    soffice = soffice_path()
    if not soffice:
        raise LibreOfficeError(
            "LibreOffice (soffice) is not installed or not found. Set LIBREOFFICE_PATH "
            "or install LibreOffice to enable document finalization on this server."
        )

    work = tempfile.mkdtemp(prefix="lo_convert_")
    profile = os.path.join(work, "profile")
    out_dir = os.path.join(work, "out")
    os.makedirs(out_dir, exist_ok=True)
    in_path = os.path.join(work, f"in_{uuid.uuid4().hex}.{in_ext}")
    with open(in_path, "wb") as fh:
        fh.write(input_bytes)

    # file:// URL for the throwaway profile so concurrent runs don't share state
    profile_url = Path(profile).as_uri()

    cmd = [
        soffice,
        "--headless",
        "--norestore",
        "--nolockcheck",
        "--nodefault",
        "--nologo",
        f"-env:UserInstallation={profile_url}",
        "--convert-to",
        convert_to,
        "--outdir",
        out_dir,
        in_path,
    ]

    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            timeout=_CONVERT_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise LibreOfficeError(f"{label} exceeded {_CONVERT_TIMEOUT_S:.0f}s and was treated as hung") from exc
    except Exception as exc:
        _cleanup(work)
        raise LibreOfficeError(f"{label} failed to launch LibreOffice: {exc}") from exc

    try:
        if proc.returncode != 0:
            stderr = (proc.stderr or b"").decode("utf-8", "replace")[:500]
            raise LibreOfficeError(
                f"{label}: LibreOffice exited with code {proc.returncode}. {stderr}"
            )

        produced = list(Path(out_dir).glob(f"*.{out_ext}"))
        if not produced:
            stderr = (proc.stderr or b"").decode("utf-8", "replace")[:500]
            raise LibreOfficeError(
                f"{label}: LibreOffice produced no .{out_ext} output. {stderr}"
            )

        out_path = produced[0]
        result = out_path.read_bytes()
        if not result:
            raise LibreOfficeError(f"{label}: LibreOffice produced an empty .{out_ext} file.")

        log.info(
            "LibreOffice %s: %s -> %s (%d bytes, elapsed=%.2fs)",
            label, in_ext, out_ext, len(result), time.time() - t0,
        )
        return result
    finally:
        _cleanup(work)


def _cleanup(path: str) -> None:
    try:
        shutil.rmtree(path, ignore_errors=True)
    except Exception:
        pass


# ── Public API (mirrors word_com_finalizer / powerpoint_com_finalizer) ────────

def finalize_docx_with_libreoffice(docx_bytes: bytes, target_lang: str) -> bytes:
    """
    Final layout pass for a translated DOCX using headless LibreOffice.

    Round-trips the DOCX through LO Writer (docx -> docx) so its layout engine
    recomputes pagination and normalizes the file, analogous to the mandatory
    Word finalize pass on Windows. RTL/alignment for Arabic is already present
    in the rebuilt DOCX XML; ``target_lang`` is accepted for signature parity
    with ``finalize_docx_with_word`` and for future language-specific handling.
    """
    # NB: no shell here — subprocess passes each list element verbatim, so the
    # filter name must NOT be wrapped in quotes (quotes are only a shell concern);
    # embedding literal '"' characters would corrupt the --convert-to argument.
    return _run_convert(
        docx_bytes, "docx", "docx:MS Word 2007 XML", "docx", "DOCX finalize",
    )


def finalize_pptx_with_libreoffice(pptx_bytes: bytes, target_lang: str) -> bytes:
    """Final layout pass for a translated PPTX via headless LibreOffice Impress."""
    return _run_convert(
        pptx_bytes, "pptx", "pptx:Impress MS PowerPoint 2007 XML", "pptx", "PPTX finalize",
    )


def convert_docx_to_pdf_with_libreoffice(docx_bytes: bytes) -> bytes:
    """Export a DOCX to PDF using headless LibreOffice Writer."""
    return _run_convert(docx_bytes, "docx", "pdf", "pdf", "DOCX->PDF export")


def convert_pptx_to_pdf_with_libreoffice(pptx_bytes: bytes) -> bytes:
    """Export a PPTX to PDF using headless LibreOffice Impress."""
    return _run_convert(pptx_bytes, "pptx", "pdf", "pdf", "PPTX->PDF export")
