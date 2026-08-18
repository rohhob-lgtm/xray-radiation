"""
Arabic PowerPoint Reference Profile
====================================

Extracted programmatically from the approved reference file:
  Arabic-CarView OP Training 25_June_2026-V2 (1).pptx

Analysis summary
----------------
  Total slides:     251
  Slides analyzed:  40 (all up to slide 40)
  Shapes analyzed:  225
  Paragraphs:       509  (non-empty: ~303)
  Runs:             326
  Tables:           6

Paragraph direction breakdown
  rtl=1:            303  (100 % of non-empty paragraphs)

Alignment breakdown
  RIGHT (3):        271  (89 %)
  CENTER (2):        23  (8 %)  — titles, labels, captions
  LEFT (1):           9  (3 %)  — English technical identifiers embedded in slides

Fonts identified
  Primary:          "Simplified Arabic"  (103 run occurrences)
  Secondary:        "Calibri"             (1 — used in one mixed cell)

Semantic font sizes
  Titles:           18 pt, 40 pt
  Body:             12, 14, 16, 18, 19, 20, 24 pt
  Tables:           10, 11, 16, 18 pt

Line spacing
  Dominant:         150 %   (93 / 109 paragraphs)
  Others:           160 %, 200 %, 250 %, 100 %

Text-frame margins (EMU)
  Left / Right:     91 440 EMU  ≈ 0.10 in
  Top / Bottom:     45 720 EMU  ≈ 0.05 in

Table behaviour
  tblPr rtl=1:      YES  (all 6 tables)
  Cell para rtl=1:  YES  (all table cell paragraphs)
  Column order:     preserved (not mirrored)

Usage
-----
Import ARABIC_PROFILE and pass it to rebuild_pptx when target_lang=="ar".
All formatting decisions made inside rebuild_pptx reference this dict so that
there is one central place to update the Arabic formatting standard.
"""

from __future__ import annotations

# ── Fonts that can render Arabic script correctly ─────────────────────────────
# Any font NOT in this set will be substituted with ARABIC_FONT_PRIMARY.

ARABIC_CAPABLE_FONTS: frozenset[str] = frozenset({
    # Dedicated Arabic fonts
    "simplified arabic",
    "traditional arabic",
    "noto sans arabic",
    "noto naskh arabic",
    "noto kufi arabic",
    "amiri",
    "cairo",
    "tajawal",
    "lateef",
    "scheherazade",
    "harmattan",
    "aref ruqaa",
    "reem kufi",
    "mada",
    "almarai",
    "zain",
    # Multi-script fonts with solid Arabic support
    "arial",
    "arial unicode ms",
    "tahoma",
    "times new roman",
    "calibri",
    "segoe ui",
    "segoe ui historic",
    "microsoft sans serif",
    "microsoft yahei",
    "verdana",
    "dejavu sans",
    "dejavu serif",
    "freesans",
    "freeserif",
    "liberation sans",
    "liberation serif",
    "courier new",
    "lucida sans unicode",
    "palatino linotype",
    "book antiqua",
    "georgia",  # limited
    "trebuchet ms",  # limited
    # Common system Arabic fonts on macOS / Windows
    "geeza pro",
    "baghdad",
    "nadeem",
    "decotype naskh",
})


def is_arabic_capable(font_name: str | None) -> bool:
    """Return True if *font_name* can render Arabic glyphs reliably.

    A ``None`` or empty name means the run inherits its font from the theme
    or master — which we treat as OK (the theme font is assumed to support
    the target language).
    """
    if not font_name:
        return True
    return font_name.lower().strip() in ARABIC_CAPABLE_FONTS


def get_arabic_font(original_font: str | None, semantic_role: str = "body") -> tuple[str | None, bool]:
    """Return ``(font_to_use, was_substituted)``.

    If *original_font* supports Arabic → return it unchanged.
    Otherwise → return the profile's primary Arabic font.

    Parameters
    ----------
    original_font:
        Run font name from the source presentation (may be None/inherited).
    semantic_role:
        ``"title"`` | ``"body"`` | ``"table"`` — selects the most appropriate
        substitution from the profile when substitution is needed.
    """
    if is_arabic_capable(original_font):
        return original_font, False

    substitution = ARABIC_PROFILE["fonts"]["substitution_by_role"].get(
        semantic_role, ARABIC_PROFILE["fonts"]["primary"]
    )
    return substitution, True


# ── Master profile dict ────────────────────────────────────────────────────────

ARABIC_PROFILE: dict = {
    # ── Provenance ────────────────────────────────────────────────────────────
    "source_file": "Arabic-CarView OP Training 25_June_2026-V2 (1).pptx",
    "slide_dimensions_emu": {"width": 12_192_000, "height": 6_858_000},
    "slide_dimensions_in":  {"width": 13.3333,    "height": 7.5},

    # ── Fonts ─────────────────────────────────────────────────────────────────
    "fonts": {
        "primary":           "Simplified Arabic",
        "title_font":        "Simplified Arabic",
        "body_font":         "Simplified Arabic",
        "table_font":        "Simplified Arabic",
        # Substitution order per spec §9:
        #   1. Arial  2. Tahoma  3. Noto Sans Arabic  4. Noto Naskh Arabic
        # Arial is preferred over Simplified Arabic for substitution because it
        # has tighter glyph metrics → less overflow in fixed-size title boxes.
        "fallback_chain":    ["Arial", "Tahoma", "Noto Sans Arabic", "Noto Naskh Arabic", "Simplified Arabic"],
        # Per-semantic-role substitution when original font cannot render Arabic
        "substitution_by_role": {
            "title":   "Arial",
            "body":    "Arial",
            "table":   "Arial",
            "footer":  "Arial",
            "default": "Arial",
        },
    },

    # ── RTL paragraph rules ───────────────────────────────────────────────────
    "rtl_rules": {
        # Set <a:pPr rtl="1"/> on EVERY paragraph in the translated document
        "set_rtl_on_all_paragraphs":         True,
        # Alignment for body / regular paragraphs
        "default_body_alignment":            "right",   # PP_ALIGN.RIGHT = 3
        # Titles that were centered in the source → keep them centered
        "preserve_centered_titles":          True,
        # Titles that were right-aligned or left-aligned → convert to right
        "convert_title_ltr_to_rtl":          True,
        # Mirror left↔right paragraph indentation for RTL bullets
        "mirror_indentation":                True,
        # Table properties
        "table_tblPr_rtl":                   True,   # <a:tblPr rtl="1"/>
        "table_cell_paragraph_rtl":          True,
        "table_cell_alignment":              "right",
        # Do NOT automatically reverse column order
        "mirror_table_columns_by_default":   False,
    },

    # ── Semantic styles (extracted from reference) ─────────────────────────────
    "semantic_styles": {
        "title": {
            "font":           "Simplified Arabic",
            "size_range_pt":  [18, 40],
            "bold":           None,   # preserve original
            "alignment":      "preserve_center_else_right",
            "rtl":            True,
        },
        "body": {
            "font":           "Simplified Arabic",
            "size_range_pt":  [12, 24],
            "bold":           None,
            "alignment":      "right",
            "rtl":            True,
        },
        "table_header": {
            "font":           "Simplified Arabic",
            "size_range_pt":  [14, 18],
            "bold":           None,
            "alignment":      "right",
            "rtl":            True,
        },
        "table_body": {
            "font":           "Simplified Arabic",
            "size_range_pt":  [10, 16],
            "bold":           None,
            "alignment":      "right",
            "rtl":            True,
        },
        "footer": {
            "font":           "Simplified Arabic",
            "size_range_pt":  [10, 12],
            "bold":           None,
            "alignment":      "right",
            "rtl":            True,
        },
    },

    # ── Line spacing (dominant pattern) ───────────────────────────────────────
    "line_spacing": {
        "dominant_pct":  150,    # 150 % = 1.5× line height
        "safe_range":    [100, 200],
    },

    # ── Text-frame internal margins ───────────────────────────────────────────
    "text_frame_margins_emu": {
        "left":   91_440,   # ≈ 0.10 in
        "right":  91_440,
        "top":    45_720,   # ≈ 0.05 in
        "bottom": 45_720,
    },

    # ── Overflow correction order ──────────────────────────────────────────────
    "overflow_strategy": [
        "preserve_font_size",
        "enable_rtl_wrapping",
        "remove_trailing_spaces",
        "adjust_internal_margins",
        "adjust_line_spacing_within_safe_range",
        "expand_textbox_into_empty_space",
        "reduce_font_size_max_10pct",
        "flag_for_manual_review",
    ],

    # ── Formatting-score weights (spec §18) ───────────────────────────────────
    "score_weights": {
        "objects_preserved":              0.20,
        "colors_and_styles_preserved":    0.20,
        "arabic_rtl_and_alignment":       0.20,
        "layout_coordinates_preserved":   0.15,
        "fonts_and_arabic_shaping":       0.10,
        "bullets_and_tables":             0.05,
        "hyperlinks_and_relationships":   0.05,
        "animations_and_transitions":     0.05,
    },

    # ── Mixed Arabic-English rules ─────────────────────────────────────────────
    "mixed_text_rules": {
        "preserve_latin_technical_terms": True,
        "preserve_numbers":               True,
        "preserve_units":                 True,
        "preserve_urls":                  True,
        "preserve_model_numbers":         True,
        # Known model / product names to never reverse
        "protected_terms": [
            "CarView", "G60", "ZBx", "TDTX", "BX", "LINAC",
            "kV", "MeV", "µSv", "mSv", "mGy", "mR",
            "ANSI", "ISO", "IEC", "IAEA", "NCRP", "IEEE",
            "HTTP", "HTTPS", "API", "URL", "XML", "JSON",
        ],
    },

    # ── Arabic layout zones (learned from the reference deck) ─────────────────
    # Median placeholder geometry as fractions of slide width/height,
    # measured across 248 title / 126 body / 8 subtitle placeholders in the
    # approved Arabic reference presentation.
    #
    # title.logo_safe_right_frac — fraction of slide width where the Rapiscan
    #   logo begins.  The title text box right edge must not cross this line.
    #   Derived from the original title zone: x + w = 0.037 + 0.734 = 0.771.
    # title.left_margin_frac — small left gutter inside the blue banner so the
    #   box does not flush against the very left edge of the slide.
    "layout_zones": {
        "title": {
            "x":                    0.037,
            "y":                    0.017,
            "w":                    0.734,
            "h":                    0.113,
            "logo_safe_right_frac": 0.771,   # title box must end before this
            "left_margin_frac":     0.020,   # left gap inside the blue banner
        },
        "body":     {"x": 0.037, "y": 0.175, "w": 0.530, "h": 0.689},
        "subtitle": {"x": 0.009, "y": 0.278, "w": 0.265, "h": 0.121},
    },

    # ── Reference typography hierarchy ─────────────────────────────────────────
    "typography": {
        "title_pt":          40,
        "title_font_min_pt": 24,   # smallest font before word-wrap takes over
        "subtitle_pt":       20,
        "body_pt":           18,
        "line_spacing":      1.5,   # 150% dominant in the reference deck
    },

    # ── Mirroring rules for the layout transformation engine ──────────────────
    # Mirror = margin swap (x' = SW − x − w): identity for symmetric shapes,
    # flip for asymmetric ones. Applied to ALL non-title shapes so composed
    # elements (gutter + text, column pairs) stay coherent.
    "mirror_rules": {
        "min_move_emu": 5000,   # skip writes when the mirror moves less than this
    },
}
