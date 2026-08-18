"""In-place PDF translation — preserve the original page (images, colours,
vector graphics, layout) and swap only the text for its translation.

The reflow path (``doc_rebuilder.build_translated_pdf`` /
``build_translated_docx``) throws away the visual document and emits a bare
bilingual text table. For image-heavy technical PDFs that is unacceptable, so
this module edits the *original* PDF instead:

  1. Match each on-page text block to a translated segment by its **source
     text** (robust to any block-index drift — the source strings are stored on
     the segments by ``doc_extractor._extract_pdf_text``).
  2. Redact the original text inside each block's bbox, keeping images and
     vector graphics untouched (``PDF_REDACT_IMAGE_NONE`` / ``..._GRAPHICS_NONE``).
  3. Re-insert the translation into the same bbox with ``insert_htmlbox`` —
     ``dir=rtl`` + right-alignment for Arabic, an embedded Arabic-capable font,
     and auto-shrink so longer/shorter translations still fit the box.

Only works for PDFs with a real text layer (``loc.format == "pdf"``). Scanned /
OCR PDFs (``loc.format == "pdf_ocr"``) have no reliable per-block geometry, so
the caller falls back to the reflow path for those.
"""
from __future__ import annotations

import glob
import html as _html
import logging
import os

from api.languages import is_rtl_lang

log = logging.getLogger(__name__)


class InPlacePdfError(RuntimeError):
    """Raised when in-place translation isn't possible for this document."""


def _find_font(target_lang: str) -> str | None:
    """Locate a TTF that can shape the target language's script."""
    rtl = is_rtl_lang(target_lang)
    patterns: list[str] = []
    if rtl:
        patterns = [
            "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
            "/usr/share/fonts/**/NotoSansArabic*.ttf",
            "/usr/share/fonts/**/NotoNaskhArabic*.ttf",
            "/usr/share/fonts/**/Amiri*.ttf",
            r"C:\Windows\Fonts\arial.ttf",
            r"C:\Windows\Fonts\tahoma.ttf",
            r"C:\Windows\Fonts\trado.ttf",
        ]
    else:
        patterns = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/**/NotoSans-Regular.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
            r"C:\Windows\Fonts\arial.ttf",
        ]
    for pat in patterns:
        if "*" in pat:
            for m in sorted(glob.glob(pat, recursive=True)):
                if os.path.isfile(m):
                    return m
        elif os.path.isfile(pat):
            return pat
    return None


def _int_color_to_hex(color: int | None) -> str:
    """Convert PyMuPDF's packed sRGB int span colour to '#rrggbb'."""
    if not isinstance(color, int):
        return "#000000"
    r = (color >> 16) & 0xFF
    g = (color >> 8) & 0xFF
    b = color & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}"


def _block_style_lookup(page) -> dict:
    """Map a text block's rounded bbox -> (hex_colour, max_font_size).

    Sampled from ``get_text('dict')`` so re-inserted text roughly matches the
    original colour and size (important for white-on-colour titles).
    """
    lookup: dict[tuple, tuple[str, float]] = {}
    try:
        data = page.get_text("dict")
    except Exception:
        return lookup
    for blk in data.get("blocks", []):
        if blk.get("type", 0) != 0:  # 0 = text block
            continue
        best_size = 0.0
        color_hex = "#000000"
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                sz = float(span.get("size", 0) or 0)
                if sz > best_size:
                    best_size = sz
                    color_hex = _int_color_to_hex(span.get("color"))
        bbox = blk.get("bbox")
        if bbox:
            key = tuple(round(v) for v in bbox)
            lookup[key] = (color_hex, best_size or 11.0)
    return lookup


def _style_in_rect(page, rect) -> tuple[str, float]:
    """Sample the dominant colour + largest font size of text inside *rect*."""
    try:
        data = page.get_text("dict", clip=rect)
    except Exception:
        return ("#000000", 11.0)
    best = 0.0
    color = "#000000"
    for blk in data.get("blocks", []):
        for line in blk.get("lines", []):
            for span in line.get("spans", []):
                sz = float(span.get("size", 0) or 0)
                if sz > best:
                    best = sz
                    color = _int_color_to_hex(span.get("color"))
    return (color, best or 11.0)


def _rightmost_color_x(pix, scale: float, fill, y_pdf: float, x_lo_pdf: float, x_hi_pdf: float):
    """Rightmost x (PDF pt) between x_lo..x_hi at row y where the pixel matches
    *fill* (0..1 rgb). Used to find where an angled banner's colour actually
    ends on a given row, so a title isn't pushed past it onto the white page."""
    try:
        tr, tg, tb = (int(round(c * 255)) for c in fill[:3])
        row = max(0, min(pix.height - 1, int(y_pdf * scale)))
        x_hi = min(pix.width - 1, int(x_hi_pdf * scale))
        x_lo = max(0, int(x_lo_pdf * scale))
        tol = 45
        for xp in range(x_hi, x_lo, -1):
            px = pix.pixel(xp, row)
            if abs(px[0] - tr) <= tol and abs(px[1] - tg) <= tol and abs(px[2] - tb) <= tol:
                return xp / scale
    except Exception:
        return None
    return None


def _cell_translation(cell_text: str, src2tgt: dict, cell_src2tgt: dict) -> str | None:
    """Find the translation for a table cell, or None if untranslated."""
    ct = (cell_text or "").strip()
    if not ct:
        return None
    if ct in src2tgt:
        return src2tgt[ct]
    if ct in cell_src2tgt:
        return cell_src2tgt[ct]
    lines = [l.strip() for l in ct.split("\n") if l.strip()]
    joined = "\n".join(lines)
    if joined in src2tgt:
        return src2tgt[joined]
    if len(lines) > 1:
        outs, any_found = [], False
        for l in lines:
            if l in src2tgt:
                outs.append(src2tgt[l]); any_found = True
            elif l in cell_src2tgt:
                outs.append(cell_src2tgt[l]); any_found = True
            else:
                outs.append(l)
        if any_found:
            return "\n".join(outs)
    return None


def translate_pdf_in_place(pdf_bytes: bytes, segments: list[dict], target_lang: str) -> bytes:
    """Return a PDF identical to the original but with text translated in place.

    Raises ``InPlacePdfError`` if the document has no positioned text layer
    (e.g. a scanned/OCR PDF) so the caller can fall back to the reflow path.
    """
    import fitz  # PyMuPDF

    # Source-text -> translation map (positioned text-layer segments only).
    src2tgt: dict[str, str] = {}
    has_text_layer = False
    for seg in segments or []:
        loc = seg.get("loc") or {}
        if loc.get("format") != "pdf":
            continue
        has_text_layer = True
        s = (seg.get("source") or "").strip()
        t = (seg.get("target") or "").strip()
        if s and t and s != t:
            src2tgt[s] = t
    if not has_text_layer:
        raise InPlacePdfError("PDF has no positioned text layer (scanned/OCR) — cannot edit in place")
    if not src2tgt:
        raise InPlacePdfError("No translated text-layer segments to place")

    # Per-cell map for tables: block sources/targets often merge a row's cells on
    # separate lines ("E411\nPre warn input dropped"). Splitting both by line
    # gives a per-cell lookup so each table cell can be placed individually.
    cell_src2tgt: dict[str, str] = {}
    for _s, _t in src2tgt.items():
        _sl = [x.strip() for x in _s.split("\n") if x.strip()]
        _tl = [x.strip() for x in _t.split("\n") if x.strip()]
        if len(_sl) == len(_tl) and len(_sl) > 1:
            for _a, _b in zip(_sl, _tl):
                cell_src2tgt.setdefault(_a, _b)

    rtl = is_rtl_lang(target_lang)
    align = "right" if rtl else "left"
    direction = "rtl" if rtl else "ltr"

    # Font: embed via an Archive referenced from an @font-face rule.
    font_path = _find_font(target_lang)
    archive = None
    font_face_css = ""
    family = "sans-serif"
    if font_path:
        try:
            # Archive the single font file (never a whole fonts directory — that
            # would bloat the output by embedding unrelated fonts).
            with open(font_path, "rb") as _fh:
                _font_data = _fh.read()
            archive = fitz.Archive()
            archive.add(_font_data, "docfont.ttf")
            family = "docfont"
            font_face_css = "@font-face { font-family: docfont; src: url(docfont.ttf); }"
        except Exception as exc:  # pragma: no cover - fallback to builtin
            log.warning("in-place PDF: could not build font archive (%s); using builtin", exc)
            archive = None
            family = "sans-serif"

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    edited_blocks = 0
    try:
        for page in doc:
            blocks = page.get_text("blocks") or []
            style = _block_style_lookup(page)

            # Detect tables and handle each CELL individually — every cell is
            # right-aligned within its OWN bbox, so text stays on the grid and
            # reads RTL (mirroring the columns geometrically is impossible here:
            # a wide "description" column cannot fit into a narrow "code" column).
            tables = []
            try:
                tables = list(page.find_tables().tables)
            except Exception:
                tables = []
            table_rects = [fitz.Rect(t.bbox) for t in tables]

            # Image regions: RTL text that overlaps an image is a diagram label —
            # it must stay put (mirroring would tear it off its target). Other
            # text (titles, bullets, paragraphs) gets mirrored to the right.
            page_w = page.rect.width
            page_h = page.rect.height
            img_rects: list = []
            colored_panels: list = []
            if rtl:
                try:
                    for _info in page.get_image_info():
                        _bb = _info.get("bbox")
                        if _bb:
                            img_rects.append(fitz.Rect(_bb))
                except Exception:
                    img_rects = []
                # Large, non-white filled shapes = coloured banners/panels. Text
                # on one must stay ON it (right-aligned within it) — mirroring to
                # the white part of the page would make white-on-colour text vanish.
                try:
                    for _dr in page.get_drawings():
                        _fill = _dr.get("fill")
                        _r = _dr.get("rect")
                        if not _fill or not _r:
                            continue
                        if min(_fill) > 0.9:  # near-white — not a coloured panel
                            continue
                        if _r.width < page_w * 0.3 or (_r.width * _r.height) < (page_w * page_h * 0.03):
                            continue
                        colored_panels.append((fitz.Rect(_r), tuple(_fill[:3])))
                except Exception:
                    colored_panels = []

            _PIXSCALE = 2.0
            _page_pix = {"img": None}  # lazily rendered once, only if a banner needs it

            def _get_pix():
                if _page_pix["img"] is None:
                    try:
                        _page_pix["img"] = page.get_pixmap(matrix=fitz.Matrix(_PIXSCALE, _PIXSCALE), alpha=False)
                    except Exception:
                        _page_pix["img"] = False
                return _page_pix["img"] or None

            # Plan: (redact_rect, insert_rect, translated_text, color, size).
            plan: list[tuple] = []

            # ── Table cells ───────────────────────────────────────────────────
            for t in tables:
                try:
                    rows = list(t.rows)
                    grid = t.extract()
                except Exception:
                    continue
                for row_obj, row_text in zip(rows, grid):
                    cell_boxes = list(getattr(row_obj, "cells", []) or [])
                    for cbox, ctext in zip(cell_boxes, row_text):
                        if not cbox or not ctext or not str(ctext).strip():
                            continue
                        tgt = _cell_translation(str(ctext), src2tgt, cell_src2tgt)
                        if tgt is None:
                            continue
                        rect = fitz.Rect(cbox)
                        color_hex, size = _style_in_rect(page, rect)
                        ins = fitz.Rect(rect.x0 + 3, rect.y0, rect.x1 - 4, rect.y1)
                        plan.append((rect, ins, tgt, color_hex, size))

            # ── Non-table blocks ──────────────────────────────────────────────
            for block in blocks:
                if len(block) < 5:
                    continue
                x0, y0, x1, y1 = block[:4]
                center = fitz.Point((x0 + x1) / 2, (y0 + y1) / 2)
                if any(tr.contains(center) for tr in table_rects):
                    continue  # already handled cell-by-cell
                block_text = block[4] or ""
                if not block_text.strip():
                    continue
                out_paras: list[str] = []
                found = False
                for para in block_text.split("\n\n"):
                    ps = para.strip()
                    if not ps:
                        continue
                    if ps in src2tgt:
                        out_paras.append(src2tgt[ps])
                        found = True
                    else:
                        out_paras.append(ps)  # numbers/codes left as-is
                if not found:
                    continue
                rect = fitz.Rect(x0, y0, x1, y1)
                insert_rect = rect
                if rtl:
                    if any(rect.intersects(ir) for ir in img_rects):
                        pass  # diagram label — keep in place (right-aligned in bbox)
                    else:
                        panel = next(((p, f) for (p, f) in colored_panels if p.contains(center)), None)
                        if panel is not None:
                            prect, pfill = panel
                            # Angled banners: the colour ends before the bbox right
                            # edge on the title's row. Pixel-scan the real colour
                            # boundary so the (white-on-colour) title stays ON it.
                            pix = _get_pix()
                            right = prect.x1 - 22
                            if pix is not None:
                                yscan = y0 - 2 if y0 - 2 > prect.y0 else (y0 + y1) / 2
                                edge = _rightmost_color_x(pix, _PIXSCALE, pfill, yscan, x0, prect.x1)
                                if edge:
                                    # Keep a clear right margin so the first (rightmost)
                                    # glyph doesn't touch the banner's colour edge.
                                    right = edge - 20
                            if right > x0 + 8:
                                insert_rect = fitz.Rect(min(x0, prect.x0) + 6, y0, right, y1)
                        else:
                            # On the white page area: mirror horizontally so the
                            # text leans to the right the way Arabic reads — but
                            # only if the mirrored slot is clear. If it would land
                            # on an image (e.g. a logo on the right), keep the text
                            # in place so it never overlaps artwork.
                            mirrored = fitz.Rect(page_w - x1, y0, page_w - x0, y1)
                            if not any(mirrored.intersects(ir) for ir in img_rects):
                                insert_rect = mirrored
                key = (round(x0), round(y0), round(x1), round(y1))
                color_hex, size = style.get(key, ("#000000", 11.0))
                plan.append((rect, insert_rect, "\n".join(out_paras), color_hex, size))

            if not plan:
                continue

            # 1) Redact original text, preserving images + vector graphics.
            for redact_rect, _ir, _txt, _c, _s in plan:
                page.add_redact_annot(redact_rect, fill=None)
            page.apply_redactions(
                images=fitz.PDF_REDACT_IMAGE_NONE,
                graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                text=fitz.PDF_REDACT_TEXT_REMOVE,
            )

            # 2) Insert the translation into each (now cleared) box.
            for _rr, insert_rect, txt, color_hex, size in plan:
                safe = _html.escape(txt).replace("\n", "<br>")
                css = (
                    f"{font_face_css} "
                    f"* {{ font-family: {family}; color: {color_hex}; "
                    f"font-size: {max(6.0, float(size)):.1f}px; "
                    f"line-height: 1.15; margin: 0; padding: 0; }}"
                )
                # Alignment comes from `dir` alone: insert_htmlbox aligns to the
                # start edge (right for rtl, left for ltr). An explicit
                # text-align:right is (counter-intuitively) ignored and leaves the
                # text left-aligned, so we must NOT set it.
                htmlbox = f'<div dir="{direction}">{safe}</div>'
                try:
                    page.insert_htmlbox(
                        insert_rect, htmlbox, css=css, archive=archive, scale_low=0,
                    )
                    edited_blocks += 1
                except Exception as exc:
                    log.warning("in-place PDF: insert_htmlbox failed on a block (%s)", exc)

        if edited_blocks == 0:
            raise InPlacePdfError("No blocks could be edited in place")

        # insert_htmlbox embeds a fresh font copy per call; merge them into one
        # subset so the file doesn't balloon (144 copies -> ~1).
        try:
            doc.subset_fonts()
        except Exception as exc:  # pragma: no cover
            log.debug("in-place PDF: subset_fonts skipped (%s)", exc)

        out = doc.tobytes(deflate=True, deflate_fonts=True, garbage=4)
        log.info(
            "in-place PDF translation: edited %d text block(s), %d page(s), %d bytes",
            edited_blocks, doc.page_count, len(out),
        )
        return out
    finally:
        doc.close()
