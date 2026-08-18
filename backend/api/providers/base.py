"""
Abstract base class for Translation Providers.

Every provider must implement:
  translate_batch(texts, source_lang, target_lang) -> list[str]
  supports_language_pair(src, tgt) -> bool
  health_check() -> dict
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class TranslationProvider(ABC):
    """Interface all translation providers must implement."""

    provider_id: str         # e.g. "deepl", "azure", "google", "openai"
    display_name: str        # e.g. "DeepL"
    description: str
    best_for: str            # e.g. "Best quality"
    requires_api_key: bool = True

    def __init__(self, api_key: str | None = None, extra_config: dict | None = None):
        self.api_key = api_key or ""
        self.extra_config = extra_config or {}

    # ── Core interface ─────────────────────────────────────────────────────────

    @abstractmethod
    async def translate_batch(
        self,
        texts: list[str],
        source_lang: str,
        target_lang: str,
    ) -> list[str]:
        """
        Translate a list of source texts.
        Returns a list of translated strings in the same order.
        Raises RuntimeError on unrecoverable failure.
        """
        ...

    @abstractmethod
    def supports_language_pair(self, source_lang: str, target_lang: str) -> bool:
        """Return True if this provider can translate this language pair."""
        ...

    @abstractmethod
    async def health_check(self) -> dict:
        """
        Check provider health.
        Returns: {ok: bool, latency_ms: int | None, message: str}
        """
        ...

    # ── Properties ─────────────────────────────────────────────────────────────

    @property
    def is_configured(self) -> bool:
        """True when this provider has the necessary credentials to operate."""
        if not self.requires_api_key:
            return True
        return bool(self.api_key)

    def to_dict(self, include_key: bool = False) -> dict:
        return {
            "provider_id": self.provider_id,
            "display_name": self.display_name,
            "description": self.description,
            "best_for": self.best_for,
            "is_configured": self.is_configured,
            "requires_api_key": self.requires_api_key,
            **({"api_key_set": bool(self.api_key)} if not include_key else {}),
        }
