"""
Font Metrics — Arabic title width estimation via real font advance widths.

When the requested font file is present on the server, this module uses
fonttools to compute the average advance width of Arabic Unicode characters
(U+0600–U+06FF) relative to the font's em square.  The result is a
dimensionless *width factor* that replaces the fixed 0.60 heuristic in
the Arabic layout engine.

Falls back to the heuristic value when:
  • fonttools is not importable (should not happen — it ships with python-pptx)
  • the font file cannot be located on the local filesystem
  • the font file cannot be parsed (corrupt / unsupported format)

Usage
-----
    from backend.api.utils.font_metrics import arabic_width_factor

    factor, source = arabic_width_factor("Simplified Arabic")
    est_emu = char_count * font_pt * 12700 * factor
    # source is "measured" or "heuristic"
"""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Iterator

log = logging.getLogger(__name__)

# ── Heuristic fallback ────────────────────────────────────────────────────────
# Arabic glyphs average roughly 60 % of their em square width.
# Used when the font file cannot be found or measured.
_HEURISTIC_FACTOR: float = 0.60

# ── Arabic Unicode sample range ───────────────────────────────────────────────
# U+0600–U+06FF covers the core Arabic block.  We sample every codepoint that
# has a glyph mapping in the font and average their advance widths.
_ARABIC_RANGE_START = 0x0600
_ARABIC_RANGE_END   = 0x06FF  # inclusive

# ── Font search directories (checked in order) ────────────────────────────────
_FONT_SEARCH_DIRS: list[str] = [
    # Linux system fonts
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    "/usr/share/fonts/truetype",
    "/usr/share/fonts/opentype",
    # User fonts
    str(Path.home() / ".fonts"),
    str(Path.home() / ".local" / "share" / "fonts"),
    # Optional override: point ARABIC_FONTS_DIR at a directory with Arabic TTFs
    os.environ.get("ARABIC_FONTS_DIR", ""),
]

# ── Name → filename candidates ────────────────────────────────────────────────
# Maps the lower-cased font name (as it appears in PPTX) to one or more
# candidate filenames to look for on disk.  Not exhaustive — unknown fonts
# fall through to a normalised-name search.
_NAME_TO_CANDIDATES: dict[str, list[str]] = {
    "simplified arabic":  ["simpearab.ttf", "SimplifiedArabic.ttf",
                           "simplified-arabic.ttf", "SimplifiedArabicRegular.ttf"],
    "traditional arabic": ["traditar.ttf", "TraditionalArabic.ttf",
                           "traditional-arabic.ttf"],
    "arial":              ["arial.ttf", "Arial.ttf", "arialbd.ttf"],
    "tahoma":             ["tahoma.ttf", "Tahoma.ttf", "tahomabd.ttf"],
    "calibri":            ["calibri.ttf", "Calibri.ttf", "calibrib.ttf"],
    "times new roman":    ["times.ttf", "Times.ttf", "timesbd.ttf"],
    "verdana":            ["verdana.ttf", "Verdana.ttf"],
    "noto sans arabic":   ["NotoSansArabic-Regular.ttf", "NotoSansArabic.ttf"],
    "noto naskh arabic":  ["NotoNaskhArabic-Regular.ttf", "NotoNaskhArabic.ttf"],
    "dejavu sans":        ["DejaVuSans.ttf"],
}


def _iter_font_files() -> Iterator[Path]:
    """Yield every *.ttf / *.otf / *.ttc file found under all search dirs."""
    for d in _FONT_SEARCH_DIRS:
        if not d:
            continue
        root = Path(d)
        if not root.is_dir():
            continue
        for ext in ("*.ttf", "*.otf", "*.ttc", "*.TTF", "*.OTF"):
            yield from root.rglob(ext)


@lru_cache(maxsize=None)
def _build_font_index() -> dict[str, Path]:
    """Return a dict mapping lowercase filename → absolute path.

    Built once, cached for the process lifetime.
    """
    index: dict[str, Path] = {}
    for p in _iter_font_files():
        index[p.name.lower()] = p
    return index


def _locate_font_file(font_name: str) -> Path | None:
    """Try to find a font file for *font_name* on the local filesystem.

    Returns the first match, or None when nothing is found.
    """
    key = font_name.lower().strip()
    candidates = _NAME_TO_CANDIDATES.get(key, [])

    # 1. Exact candidate filenames
    index = _build_font_index()
    for fname in candidates:
        hit = index.get(fname.lower())
        if hit:
            return hit

    # 2. Normalised name search (e.g. "Noto Sans Arabic" → "notosansarabic")
    normalised = key.replace(" ", "").replace("-", "").replace("_", "")
    for fname_lower, path in index.items():
        stem = Path(fname_lower).stem.replace("-", "").replace("_", "").replace(" ", "")
        if stem == normalised or stem.startswith(normalised):
            return path

    return None


def _measure_arabic_factor(font_path: Path) -> float:
    """Compute the average Arabic advance-width ratio for the font at *font_path*.

    Returns advance_avg / units_per_em, a dimensionless factor in (0, 1].
    """
    try:
        from fontTools.ttLib import TTFont  # type: ignore[import]
    except ImportError:
        raise RuntimeError("fonttools not available")

    tt = TTFont(str(font_path), lazy=True)
    try:
        upm: int = tt["head"].unitsPerEm  # type: ignore[index]
        cmap_table = tt.getBestCmap()     # dict[codepoint → glyph_name]
        hmtx = tt["hmtx"].metrics        # type: ignore[index]  # {glyph_name: (advance, lsb)}

        advances: list[int] = []
        for cp in range(_ARABIC_RANGE_START, _ARABIC_RANGE_END + 1):
            glyph = cmap_table.get(cp) if cmap_table else None
            if glyph and glyph in hmtx:
                adv = hmtx[glyph][0]
                if adv > 0:
                    advances.append(adv)

        if not advances:
            log.debug("font_metrics: no Arabic glyphs in %s; using heuristic", font_path.name)
            return _HEURISTIC_FACTOR

        factor = sum(advances) / (len(advances) * upm)
        log.debug(
            "font_metrics: %s → %.3f (n=%d glyphs, upm=%d)",
            font_path.name, factor, len(advances), upm,
        )
        return factor
    finally:
        tt.close()


@lru_cache(maxsize=64)
def arabic_width_factor(font_name: str) -> tuple[float, str]:
    """Return *(factor, source)* for *font_name*.

    factor
        Dimensionless ratio: average Arabic glyph advance ÷ em square.
        Multiply by ``char_count * font_pt * 12700`` to get an EMU estimate.
    source
        ``"measured"`` when derived from real font metrics,
        ``"heuristic"`` when the font file was not found or could not be parsed.

    Results are cached for the process lifetime.
    """
    if not font_name or not font_name.strip():
        return _HEURISTIC_FACTOR, "heuristic"

    path = _locate_font_file(font_name)
    if path is None:
        log.debug("font_metrics: font file not found for %r; using heuristic", font_name)
        return _HEURISTIC_FACTOR, "heuristic"

    try:
        factor = _measure_arabic_factor(path)
        return factor, "measured"
    except Exception as exc:
        log.debug("font_metrics: could not measure %r (%s); using heuristic", font_name, exc)
        return _HEURISTIC_FACTOR, "heuristic"
