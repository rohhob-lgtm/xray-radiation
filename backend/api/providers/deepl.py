"""
DeepL Translation Provider.

Uses DeepL REST API v2.
Best quality for European language pairs.
"""
from __future__ import annotations

import logging
import time

from .base import TranslationProvider

log = logging.getLogger(__name__)

_DEEPL_LANG_MAP = {
    "en": "EN", "ar": "AR", "fr": "FR", "de": "DE", "es": "ES",
    "zh": "ZH", "ja": "JA", "ru": "RU", "tr": "TR", "it": "IT",
    "pt": "PT", "nl": "NL", "pl": "PL", "ko": "KO",
}

_DEEPL_SUPPORTED_PAIRS = {
    # DeepL supports Arabic as target (EN→AR) since 2023
    ("en", "ar"), ("en", "fr"), ("en", "de"), ("en", "es"), ("en", "zh"),
    ("en", "ja"), ("en", "ru"), ("en", "it"), ("en", "pt"), ("en", "nl"),
    ("en", "pl"), ("en", "ko"), ("en", "tr"),
    ("fr", "en"), ("de", "en"), ("es", "en"), ("zh", "en"),
    ("ja", "en"), ("ru", "en"), ("it", "en"), ("pt", "en"),
    ("nl", "en"), ("pl", "en"), ("ko", "en"),
    ("fr", "de"), ("de", "fr"), ("fr", "es"), ("es", "fr"),
}


class DeepLProvider(TranslationProvider):
    provider_id = "deepl"
    display_name = "DeepL"
    description = "Industry-leading neural machine translation. Highest quality for European and Arabic documents, especially legal, technical, and scientific content."
    best_for = "Best quality"

    def __init__(self, api_key: str | None = None, extra_config: dict | None = None):
        super().__init__(api_key=api_key, extra_config=extra_config)
        # DeepL has two API tiers: Free (.../v2 at api-free.deepl.com) and Pro (api.deepl.com)
        self._base_url = (extra_config or {}).get("endpoint", "https://api-free.deepl.com/v2")

    def supports_language_pair(self, source_lang: str, target_lang: str) -> bool:
        return (source_lang.lower(), target_lang.lower()) in _DEEPL_SUPPORTED_PAIRS

    async def translate_batch(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        import httpx

        if not self.api_key:
            raise RuntimeError("DeepL API key not configured")

        src_code = _DEEPL_LANG_MAP.get(source_lang.lower(), source_lang.upper())
        tgt_code = _DEEPL_LANG_MAP.get(target_lang.lower(), target_lang.upper())

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._base_url}/translate",
                headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                json={
                    "text": texts,
                    "source_lang": src_code,
                    "target_lang": tgt_code,
                    "preserve_formatting": True,
                    "tag_handling": "xml",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["text"] for item in data.get("translations", [])]

    async def health_check(self) -> dict:
        import httpx
        if not self.api_key:
            return {"ok": False, "latency_ms": None, "message": "API key not configured"}
        try:
            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base_url}/usage",
                    headers={"Authorization": f"DeepL-Auth-Key {self.api_key}"},
                )
                resp.raise_for_status()
                latency_ms = int((time.monotonic() - t0) * 1000)
                data = resp.json()
                char_count = data.get("character_count", 0)
                char_limit = data.get("character_limit", 0)
                return {
                    "ok": True,
                    "latency_ms": latency_ms,
                    "message": f"Usage: {char_count:,} / {char_limit:,} characters",
                }
        except Exception as e:
            return {"ok": False, "latency_ms": None, "message": str(e)}
