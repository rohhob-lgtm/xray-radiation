"""
Google Cloud Translation Provider.

Uses Google Cloud Translation API v2 (Basic) — fastest throughput.
"""
from __future__ import annotations

import logging
import time

from .base import TranslationProvider

log = logging.getLogger(__name__)

_GOOGLE_ENDPOINT = "https://translation.googleapis.com/language/translate/v2"

_GOOGLE_LANG_MAP = {
    "en": "en", "ar": "ar", "fr": "fr", "de": "de", "es": "es",
    "zh": "zh-CN", "ja": "ja", "ru": "ru", "tr": "tr", "it": "it",
    "pt": "pt", "nl": "nl", "pl": "pl", "ko": "ko",
}


class GoogleTranslateProvider(TranslationProvider):
    provider_id = "google"
    display_name = "Google Cloud Translation"
    description = "Google's Neural Machine Translation with the fastest throughput. Ideal for high-volume documents where speed is prioritised over editorial quality."
    best_for = "Fastest throughput"

    def __init__(self, api_key: str | None = None, extra_config: dict | None = None):
        super().__init__(api_key=api_key, extra_config=extra_config)

    def supports_language_pair(self, source_lang: str, target_lang: str) -> bool:
        return source_lang.lower() in _GOOGLE_LANG_MAP and target_lang.lower() in _GOOGLE_LANG_MAP

    async def translate_batch(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        import httpx

        if not self.api_key:
            raise RuntimeError("Google Cloud Translation API key not configured")

        src_code = _GOOGLE_LANG_MAP.get(source_lang.lower(), source_lang)
        tgt_code = _GOOGLE_LANG_MAP.get(target_lang.lower(), target_lang)

        # Google Basic API handles batches of up to 128 strings
        # Each call sends all texts in one request
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                _GOOGLE_ENDPOINT,
                params={"key": self.api_key},
                json={
                    "q": texts,
                    "source": src_code,
                    "target": tgt_code,
                    "format": "text",
                },
            )
            resp.raise_for_status()
            data = resp.json()
            translations = data.get("data", {}).get("translations", [])
            return [t.get("translatedText", texts[i]) for i, t in enumerate(translations)]

    async def health_check(self) -> dict:
        import httpx
        if not self.api_key:
            return {"ok": False, "latency_ms": None, "message": "API key not configured"}
        try:
            t0 = time.monotonic()
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    "https://translation.googleapis.com/language/translate/v2/languages",
                    params={"key": self.api_key, "target": "en"},
                )
                resp.raise_for_status()
                latency_ms = int((time.monotonic() - t0) * 1000)
                lang_count = len(resp.json().get("data", {}).get("languages", []))
                return {"ok": True, "latency_ms": latency_ms, "message": f"{lang_count} languages supported"}
        except Exception as e:
            return {"ok": False, "latency_ms": None, "message": str(e)}
