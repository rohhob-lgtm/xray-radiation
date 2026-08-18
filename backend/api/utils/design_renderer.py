"""
Pillow-based PNG renderer for AI-generated design specs.

This is the Mode 2b fallback (internal render only, no PPTX/PDF import
available) and the source image for Mode 1's image-type autofill fields —
see design_orchestrator.py for when each mode is chosen. Deliberately one
flexible template (background fill, title, subtitle, bullet list, accent
bar/border) driven by a small per-design_type dimension/style table rather
than N bespoke layouts: Canva's Connect API has no endpoint to place
arbitrary elements into a design, so this PNG is only ever a seed asset or
a last-resort deliverable, never a "final polished Canva design" in itself.

Arabic/RTL text uses this repo's existing arabic_reshaper + python-bidi
convention (see api/utils/image_translator.py's _prepare_rtl_text) rather
than reinventing text shaping.
"""
from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

from .design_specs import resolve_dimensions, resolve_palette

log = logging.getLogger(__name__)

_SEARCH_DIRS = [
    os.environ.get("ARABIC_FONTS_DIR", ""),
    "C:/Windows/Fonts",
    "/usr/share/fonts/truetype/dejavu",
    "/usr/share/fonts/truetype/msttcorefonts",
    "/usr/share/fonts/truetype/noto",
]
_ARABIC_CANDIDATES = ["tahoma.ttf", "Tahoma.ttf", "NotoNaskhArabic-Regular.ttf", "NotoSansArabic-Regular.ttf", "arial.ttf", "Arial.ttf"]
_LATIN_BOLD_CANDIDATES = ["arialbd.ttf", "Arial Bold.ttf", "DejaVuSans-Bold.ttf"]
_LATIN_REGULAR_CANDIDATES = ["arial.ttf", "Arial.ttf", "DejaVuSans.ttf"]


def _bundled_dejavu() -> Optional[str]:
    """matplotlib is a hard dependency of this backend and always ships
    DejaVuSans — the one font guaranteed present on every platform."""
    try:
        import matplotlib
        path = Path(matplotlib.get_data_path()) / "fonts" / "ttf" / "DejaVuSans.ttf"
        return str(path) if path.is_file() else None
    except Exception:
        return None


def _find_font_file(candidates: list[str]) -> Optional[str]:
    for d in _SEARCH_DIRS:
        if not d:
            continue
        for name in candidates:
            p = Path(d) / name
            if p.is_file():
                return str(p)
    return _bundled_dejavu()


def _load_font(size: int, *, bold: bool = False, arabic: bool = False) -> ImageFont.ImageFont:
    candidates = _ARABIC_CANDIDATES if arabic else (_LATIN_BOLD_CANDIDATES if bold else _LATIN_REGULAR_CANDIDATES)
    path = _find_font_file(candidates)
    if path:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            log.warning("design_renderer: failed to load font %s", path)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _prepare_text(text: str, is_rtl: bool) -> str:
    """Shape + reorder Arabic/RTL text for correct PIL rendering (same
    convention as image_translator.py's _prepare_rtl_text)."""
    if not is_rtl:
        return text
    try:
        import arabic_reshaper
        from bidi.algorithm import get_display
        return get_display(arabic_reshaper.reshape(text))
    except Exception as exc:
        log.debug("design_renderer: arabic_reshaper/bidi failed: %s", exc)
        return text


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if not current or draw.textlength(candidate, font=font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_design(spec: dict, design_type: str) -> bytes:
    """Renders a structured design spec to PNG bytes.

    spec: {title, subtitle?, bullets?: list[str], palette?: one of
    _PALETTES' keys, language?, direction?: "rtl"|"ltr"}. Never raises on a
    malformed/sparse spec — missing fields just render less content.
    """
    width, height, layout = resolve_dimensions(design_type)
    palette = resolve_palette(spec.get("palette"))
    is_rtl = (spec.get("direction") or "").lower() == "rtl"

    img = Image.new("RGB", (width, height), palette["bg"])
    draw = ImageDraw.Draw(img)

    bar_h = max(8, int(height * 0.012))
    draw.rectangle([0, 0, width, bar_h], fill=palette["primary"])
    draw.rectangle([0, height - bar_h, width, height], fill=palette["accent"])

    margin = int(width * 0.08)
    content_width = width - 2 * margin
    anchor_x = width - margin if is_rtl else margin
    text_anchor = "ra" if is_rtl else "la"

    title = _prepare_text((spec.get("title") or "Untitled Design").strip(), is_rtl)
    subtitle = _prepare_text((spec.get("subtitle") or "").strip(), is_rtl)
    bullets = [b.strip() for b in (spec.get("bullets") or []) if isinstance(b, str) and b.strip()][:6]

    title_size = max(48, int(width * 0.075))
    subtitle_size = max(28, int(width * 0.035))
    bullet_size = max(24, int(width * 0.028))
    title_font = _load_font(title_size, bold=True, arabic=is_rtl)
    subtitle_font = _load_font(subtitle_size, arabic=is_rtl)
    bullet_font = _load_font(bullet_size, arabic=is_rtl)

    y = int(height * (0.20 if layout == "certificate" else 0.14))
    for line in _wrap_text(draw, title, title_font, content_width):
        draw.text((anchor_x, y), line, font=title_font, fill=palette["text"], anchor=text_anchor)
        y += int(title_size * 1.25)

    if subtitle:
        y += int(height * 0.02)
        for line in _wrap_text(draw, subtitle, subtitle_font, content_width):
            draw.text((anchor_x, y), line, font=subtitle_font, fill=palette["accent"], anchor=text_anchor)
            y += int(subtitle_size * 1.3)

    if bullets:
        y += int(height * 0.04)
        marker = "• "
        for bullet in bullets:
            bullet_text = _prepare_text(bullet, is_rtl)
            line_text = f"{bullet_text} {marker}" if is_rtl else f"{marker}{bullet_text}"
            for line in _wrap_text(draw, line_text, bullet_font, content_width):
                draw.text((anchor_x, y), line, font=bullet_font, fill=palette["text"], anchor=text_anchor)
                y += int(bullet_size * 1.4)
            y += int(bullet_size * 0.4)

    if layout == "certificate":
        border = max(6, int(min(width, height) * 0.012))
        draw.rectangle([border, border, width - border, height - border], outline=palette["accent"], width=border)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
