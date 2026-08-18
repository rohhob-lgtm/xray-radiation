"""
Shared dimension/palette tables for AI-generated design specs — used by both
design_renderer.py (Pillow PNG, Mode 2b) and design_pptx_builder.py (PPTX,
Mode 2a) so the two rendering paths for the same design_type always agree
on canvas size and color scheme.
"""
from __future__ import annotations

# (width_px, height_px, layout) per design_type. "hero" = big centered title
# block (poster/flyer/social), "hero_wide" = landscape hero (banner/
# presentation cover), "sectioned" = denser text-heavy layout (infographic/
# brochure), "certificate" = bordered/centered formal layout. Any
# design_type not listed here (new routing keywords added later) still
# renders via DEFAULT_DIMENSIONS instead of raising.
DIMENSIONS: dict[str, tuple[int, int, str]] = {
    "poster": (1080, 1920, "hero"),
    "flyer": (1080, 1920, "hero"),
    "social_media": (1080, 1080, "hero"),
    "banner": (1600, 900, "hero_wide"),
    "course_cover": (1600, 900, "hero_wide"),
    "presentation_cover": (1920, 1080, "hero_wide"),
    "presentation": (1920, 1080, "hero_wide"),
    "infographic": (1080, 1350, "sectioned"),
    "brochure": (1080, 1350, "sectioned"),
    "training_visual": (1080, 1350, "sectioned"),
    "certificate": (1600, 1200, "certificate"),
}
DEFAULT_DIMENSIONS: tuple[int, int, str] = (1080, 1350, "sectioned")

PALETTES: dict[str, dict[str, tuple[int, int, int]]] = {
    "blue":   {"bg": (15, 23, 42),  "primary": (37, 99, 235),  "accent": (96, 165, 250),  "text": (248, 250, 252)},
    "red":    {"bg": (32, 10, 10),  "primary": (220, 38, 38),  "accent": (248, 113, 113), "text": (255, 241, 242)},
    "amber":  {"bg": (32, 22, 8),   "primary": (217, 119, 6),  "accent": (251, 191, 36),  "text": (255, 251, 235)},
    "green":  {"bg": (6, 30, 18),   "primary": (5, 150, 105),  "accent": (52, 211, 153),  "text": (236, 253, 245)},
    "purple": {"bg": (24, 12, 40),  "primary": (124, 58, 237), "accent": (167, 139, 250), "text": (245, 243, 255)},
    "teal":   {"bg": (6, 27, 30),   "primary": (13, 148, 136), "accent": (45, 212, 191),  "text": (240, 253, 250)},
}
DEFAULT_PALETTE = "blue"


def resolve_dimensions(design_type: str) -> tuple[int, int, str]:
    return DIMENSIONS.get(design_type, DEFAULT_DIMENSIONS)


def resolve_palette(palette_name: str | None) -> dict[str, tuple[int, int, int]]:
    return PALETTES.get((palette_name or "").lower(), PALETTES[DEFAULT_PALETTE])
