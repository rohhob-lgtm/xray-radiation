"""
Automated tests for api.utils.filename_helper.

Run with:
    cd backend && .venv/bin/python -m pytest tests/test_filename_helper.py -v
"""
import pytest
from api.utils.filename_helper import (
    build_translated_filename,
    build_translated_filename_from_code,
    content_disposition,
    lang_display_name,
    mime_for_ext,
)


# ── build_translated_filename ─────────────────────────────────────────────────

class TestBuildTranslatedFilename:
    """Spec rule 11 — use the centralised helper for every format."""

    def test_pptx_basic(self):
        assert build_translated_filename(
            "G60 ZBx OP Introduction.pptx", "Arabic"
        ) == "Arabic-G60 ZBx OP Introduction.pptx"

    def test_pdf_basic(self):
        assert build_translated_filename(
            "Safety Manual.pdf", "Arabic"
        ) == "Arabic-Safety Manual.pdf"

    def test_docx_basic(self):
        assert build_translated_filename(
            "Operator Guide.docx", "Arabic"
        ) == "Arabic-Operator Guide.docx"

    def test_xlsx_basic(self):
        assert build_translated_filename(
            "Training Data.xlsx", "Arabic"
        ) == "Arabic-Training Data.xlsx"

    def test_txt_basic(self):
        assert build_translated_filename(
            "Instructions.txt", "Arabic"
        ) == "Arabic-Instructions.txt"

    def test_png_basic(self):
        assert build_translated_filename(
            "System Diagram.png", "Arabic"
        ) == "Arabic-System Diagram.png"

    # Spec rule 12 — multi-dot filenames
    def test_multi_dot(self):
        assert build_translated_filename(
            "training.manual.v2.pdf", "Arabic"
        ) == "Arabic-training.manual.v2.pdf"

    # Spec rule 13 — no extension
    def test_no_extension(self):
        assert build_translated_filename(
            "Safety Manual", "Arabic"
        ) == "Arabic-Safety Manual"

    # Spec rule 10 — no duplicate prefix
    def test_no_double_prefix_exact(self):
        assert build_translated_filename(
            "Arabic-Existing File.pdf", "Arabic"
        ) == "Arabic-Existing File.pdf"

    def test_no_double_prefix_case_insensitive(self):
        assert build_translated_filename(
            "arabic-Manual.pdf", "Arabic"
        ) == "arabic-Manual.pdf"

    # Spec rule 15 — Unicode / Arabic filenames
    def test_arabic_filename_english_output(self):
        assert build_translated_filename(
            "دليل تشغيل الجهاز.pdf", "English"
        ) == "English-دليل تشغيل الجهاز.pdf"

    def test_arabic_filename_french_output(self):
        assert build_translated_filename(
            "تدريب الأشعة.pptx", "French"
        ) == "French-تدريب الأشعة.pptx"

    # Various languages
    def test_french_prefix(self):
        assert build_translated_filename(
            "Operator Guide.docx", "French"
        ) == "French-Operator Guide.docx"

    def test_german_prefix(self):
        assert build_translated_filename(
            "Training Data.xlsx", "German"
        ) == "German-Training Data.xlsx"

    def test_spanish_prefix(self):
        assert build_translated_filename(
            "Manual de usuario.pdf", "Spanish"
        ) == "Spanish-Manual de usuario.pdf"

    # Spec rule 14 — preserve spaces (do not replace with underscores)
    def test_spaces_preserved(self):
        result = build_translated_filename("My File Name.docx", "Arabic")
        assert " " in result
        assert result == "Arabic-My File Name.docx"

    # Edge cases
    def test_empty_original_uses_fallback(self):
        result = build_translated_filename("", "Arabic")
        assert result.startswith("Arabic-")

    def test_none_original_uses_fallback(self):
        result = build_translated_filename(None, "Arabic")  # type: ignore[arg-type]
        assert result.startswith("Arabic-")

    def test_hyphen_underscore_preserved(self):
        assert build_translated_filename(
            "my-file_v2.pdf", "Arabic"
        ) == "Arabic-my-file_v2.pdf"

    def test_parentheses_preserved(self):
        assert build_translated_filename(
            "Manual (Rev 3).pdf", "Arabic"
        ) == "Arabic-Manual (Rev 3).pdf"


# ── build_translated_filename_from_code ──────────────────────────────────────

class TestBuildFromCode:
    """Convenience wrapper resolves language codes to names."""

    def test_ar_resolves_to_arabic(self):
        assert build_translated_filename_from_code(
            "Safety Manual.pdf", "ar"
        ) == "Arabic-Safety Manual.pdf"

    def test_en_resolves_to_english(self):
        assert build_translated_filename_from_code(
            "دليل تشغيل الجهاز.pdf", "en"
        ) == "English-دليل تشغيل الجهاز.pdf"

    def test_fr_resolves_to_french(self):
        assert build_translated_filename_from_code(
            "Operator Guide.docx", "fr"
        ) == "French-Operator Guide.docx"

    def test_de_resolves_to_german(self):
        assert build_translated_filename_from_code(
            "Training Data.xlsx", "de"
        ) == "German-Training Data.xlsx"

    def test_unknown_code_uses_upper(self):
        result = build_translated_filename_from_code("file.pdf", "xx")
        assert result.startswith("XX-")

    def test_bcp47_hyphen_stripped(self):
        # "zh-TW" should resolve the same as "zh"
        result = build_translated_filename_from_code("file.pdf", "zh-TW")
        assert result.startswith("Chinese-")


# ── lang_display_name ─────────────────────────────────────────────────────────

class TestLangDisplayName:
    def test_ar(self):
        assert lang_display_name("ar") == "Arabic"

    def test_en(self):
        assert lang_display_name("en") == "English"

    def test_fr(self):
        assert lang_display_name("fr") == "French"

    def test_unknown(self):
        assert lang_display_name("xx") == "XX"

    def test_case_insensitive(self):
        assert lang_display_name("AR") == "Arabic"


# ── content_disposition ───────────────────────────────────────────────────────

class TestContentDisposition:
    def test_ascii_filename(self):
        hdr = content_disposition("Arabic-Safety Manual.pdf")
        assert "attachment" in hdr
        assert "Arabic-Safety Manual.pdf" in hdr
        assert "filename*=UTF-8''" in hdr

    def test_unicode_filename(self):
        hdr = content_disposition("Arabic-دليل تشغيل الجهاز.pdf")
        assert "attachment" in hdr
        assert "filename*=UTF-8''" in hdr
        # ASCII fallback must not contain Arabic letters
        import re
        ascii_part = re.search(r'filename="([^"]+)"', hdr)
        assert ascii_part is not None
        ascii_name = ascii_part.group(1)
        for ch in ascii_name:
            assert ord(ch) < 128, f"Non-ASCII in ascii fallback: {ch!r}"

    def test_no_newlines(self):
        hdr = content_disposition("file\nwith\nnewlines.pdf")
        assert "\n" not in hdr

    def test_no_bare_quotes(self):
        hdr = content_disposition('file"with"quotes.pdf')
        # The ascii fallback must not break the header — no unescaped quotes
        # between filename=" and "
        import re
        m = re.search(r'filename="([^"]*)"', hdr)
        assert m is not None  # parseable


# ── mime_for_ext ──────────────────────────────────────────────────────────────

class TestMimeForExt:
    @pytest.mark.parametrize("ext,expected", [
        ("pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        (".pptx", "application/vnd.openxmlformats-officedocument.presentationml.presentation"),
        ("docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
        ("pdf",  "application/pdf"),
        ("txt",  "text/plain; charset=utf-8"),
        ("csv",  "text/csv; charset=utf-8"),
        ("png",  "image/png"),
        ("jpg",  "image/jpeg"),
        ("jpeg", "image/jpeg"),
        ("zip",  "application/zip"),
        ("html", "text/html; charset=utf-8"),
        ("htm",  "text/html; charset=utf-8"),
    ])
    def test_known_types(self, ext, expected):
        assert mime_for_ext(ext) == expected

    def test_unknown_falls_back(self):
        assert mime_for_ext("xyz") == "application/octet-stream"
