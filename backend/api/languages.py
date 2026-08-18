"""Central language registry for the Translation Studio.

Single source of truth for every language the translation pipeline knows
about — display names, writing direction, OCR language codes, and preferred
fonts. Adding a new language to the platform means adding one entry to
``SUPPORTED_LANGUAGES`` (and, if it should be selectable, to
``TARGET_LANGUAGES``/``SOURCE_LANGUAGES``) — no other module should hard-code
language metadata or per-language branching.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Direction = Literal["ltr", "rtl"]


@dataclass(frozen=True)
class LanguageConfig:
    code: str
    name: str
    native_name: str
    flag: str
    direction: Direction
    ocr_lang: str  # tesseract language code
    preferred_fonts: list[str] = field(default_factory=list)


SUPPORTED_LANGUAGES: dict[str, LanguageConfig] = {
    "en": LanguageConfig(
        code="en", name="English", native_name="English", flag="🇬🇧",
        direction="ltr", ocr_lang="eng",
        preferred_fonts=["Calibri", "Arial", "Segoe UI"],
    ),
    "ar": LanguageConfig(
        code="ar", name="Arabic", native_name="العربية", flag="🇸🇦",
        direction="rtl", ocr_lang="ara",
        preferred_fonts=["Traditional Arabic", "Arial", "Dubai"],
    ),
    "ru": LanguageConfig(
        code="ru", name="Russian", native_name="Русский", flag="🇷🇺",
        direction="ltr", ocr_lang="rus",
        preferred_fonts=["Arial", "Times New Roman", "PT Sans"],
    ),
    "fr": LanguageConfig(
        code="fr", name="French", native_name="Français", flag="🇫🇷",
        direction="ltr", ocr_lang="fra",
        preferred_fonts=["Arial", "Calibri", "Georgia"],
    ),
    "es": LanguageConfig(
        code="es", name="Spanish", native_name="Español", flag="🇪🇸",
        direction="ltr", ocr_lang="spa",
        preferred_fonts=["Arial", "Calibri", "Georgia"],
    ),
}

# Selectable as a translation target in the UI/API.
TARGET_LANGUAGES: list[str] = ["ar", "en", "ru", "fr", "es"]

# Selectable as a translation source in the UI/API ("auto" triggers
# language detection rather than naming a LanguageConfig entry).
SOURCE_LANGUAGES: list[str] = ["auto", "en", "ar", "ru", "fr", "es"]

# Additional RTL codes recognized for display purposes (e.g. legacy projects
# or documents) even though they aren't offered as selectable targets yet.
_EXTRA_RTL_CODES = {"he", "fa", "ur"}


def get_language(code: str | None) -> LanguageConfig | None:
    if not code:
        return None
    return SUPPORTED_LANGUAGES.get(code.lower().split("-")[0])


def lang_display_name(code: str | None) -> str:
    """Return the human-readable name for a language code.

    Falls back to the uppercased code if unknown so this never raises.
    """
    lang = get_language(code)
    if lang:
        return lang.name
    return (code or "").upper()


def is_rtl_lang(code: str | None) -> bool:
    """True if *code* should be laid out right-to-left."""
    if not code:
        return False
    normalized = code.lower().split("-")[0]
    lang = SUPPORTED_LANGUAGES.get(normalized)
    if lang:
        return lang.direction == "rtl"
    return normalized in _EXTRA_RTL_CODES


def ocr_lang_code(code: str | None) -> str:
    """Return the tesseract language code for *code*, defaulting to English."""
    lang = get_language(code)
    return lang.ocr_lang if lang else "eng"


def list_target_languages() -> list[LanguageConfig]:
    return [SUPPORTED_LANGUAGES[c] for c in TARGET_LANGUAGES]


def list_source_languages() -> list[LanguageConfig]:
    return [SUPPORTED_LANGUAGES[c] for c in SOURCE_LANGUAGES if c in SUPPORTED_LANGUAGES]
