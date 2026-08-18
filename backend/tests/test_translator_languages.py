"""
Multilingual Translation Studio tests: the central language registry
(api/languages.py) and its consumers — translator.py's prompt templates and
LANG_NAMES, and doc_extractor.py's script-aware "is this translatable" gate.

Covers Arabic, Russian, French, and Spanish as an explicit regression check
that generalizing the (formerly Arabic-only) prompts and RTL checks did not
change Arabic's own behavior.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest

from api.languages import (
    SUPPORTED_LANGUAGES,
    TARGET_LANGUAGES,
    SOURCE_LANGUAGES,
    is_rtl_lang,
    lang_display_name,
    ocr_lang_code,
    get_language,
)
from api.utils.translator import LANG_NAMES, _SYSTEM_TECHNICAL, _SYSTEM_FORMAL, _SYSTEM_BILINGUAL
from api.utils.doc_extractor import _is_translatable


# ── Registry ──────────────────────────────────────────────────────────────

def test_target_languages_are_exactly_the_four_required():
    assert set(TARGET_LANGUAGES) == {"ar", "ru", "fr", "es"}


def test_source_languages_include_auto_and_all_targets():
    assert "auto" in SOURCE_LANGUAGES
    assert "en" in SOURCE_LANGUAGES
    for code in TARGET_LANGUAGES:
        assert code in SOURCE_LANGUAGES


@pytest.mark.parametrize("code,expected_rtl", [
    ("ar", True), ("ru", False), ("fr", False), ("es", False), ("en", False),
])
def test_is_rtl_lang(code, expected_rtl):
    assert is_rtl_lang(code) is expected_rtl


def test_is_rtl_lang_recognizes_legacy_rtl_codes_not_yet_selectable():
    # he/fa/ur aren't offered as targets but existing/legacy data using them
    # must still lay out RTL.
    assert is_rtl_lang("he") is True
    assert is_rtl_lang("fa") is True
    assert is_rtl_lang("ur") is True


def test_is_rtl_lang_handles_missing_or_region_suffixed_codes():
    assert is_rtl_lang(None) is False
    assert is_rtl_lang("") is False
    assert is_rtl_lang("ar-SA") is True
    assert is_rtl_lang("fr-FR") is False


@pytest.mark.parametrize("code,name", [
    ("ar", "Arabic"), ("ru", "Russian"), ("fr", "French"), ("es", "Spanish"), ("en", "English"),
])
def test_lang_display_name(code, name):
    assert lang_display_name(code) == name


def test_lang_display_name_falls_back_to_uppercased_code():
    assert lang_display_name("xx") == "XX"


@pytest.mark.parametrize("code,tess_code", [
    ("en", "eng"), ("ar", "ara"), ("ru", "rus"), ("fr", "fra"), ("es", "spa"),
])
def test_ocr_lang_code(code, tess_code):
    assert ocr_lang_code(code) == tess_code


def test_ocr_lang_code_defaults_to_english_for_unknown():
    assert ocr_lang_code("xx") == "eng"
    assert ocr_lang_code(None) == "eng"


def test_get_language_unknown_returns_none():
    assert get_language("xx") is None
    assert get_language(None) is None


# ── translator.py prompt generalization ──────────────────────────────────

def test_lang_names_sourced_from_registry():
    for code, lang in SUPPORTED_LANGUAGES.items():
        assert LANG_NAMES[code] == lang.name


@pytest.mark.parametrize("template", [_SYSTEM_TECHNICAL, _SYSTEM_FORMAL, _SYSTEM_BILINGUAL])
@pytest.mark.parametrize("target_code", ["ar", "ru", "fr", "es"])
def test_prompt_templates_render_for_every_target_language(template, target_code):
    target_name = lang_display_name(target_code)
    rendered = template.format(source_lang="English", target_lang=target_name, keep_english=False)
    # The target language's display name must actually appear in its own
    # rendered prompt (this is the crux of the Arabic->generic refactor).
    assert target_name in rendered
    # No leftover literal "Arabic" wording when translating into a
    # different language — the old hardcoded prompts would have failed this.
    if target_code != "ar":
        assert "Arabic" not in rendered
    assert "translations" in rendered  # JSON contract instruction preserved


def test_bilingual_prompt_uses_target_language_not_literal_arabic():
    rendered = _SYSTEM_BILINGUAL.format(source_lang="English", target_lang="Russian", keep_english=False)
    assert "[Russian translation] (English original)" in rendered


# ── doc_extractor.py script-aware translatable-text gate ─────────────────

@pytest.mark.parametrize("text", [
    "Привет, это тестовый текст",       # Russian (Cyrillic) — regression-critical
    "Bonjour, ceci est un texte",        # French
    "Hola, esto es un texto",            # Spanish
    "مرحبا هذا نص",                        # Arabic
    "Hello, this is text",               # English
])
def test_is_translatable_accepts_every_supported_script(text):
    assert _is_translatable(text) is True


@pytest.mark.parametrize("text", ["", "123", "12.5%", "   ", "http://example.com"])
def test_is_translatable_still_rejects_non_text(text):
    assert _is_translatable(text) is False
