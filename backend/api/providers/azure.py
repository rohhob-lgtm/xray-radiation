"""
Azure AI Translator Provider.

Uses Azure Cognitive Services Translator REST API v3.
Preferred in enterprise/government environments.
"""
from __future__ import annotations

import logging
import time
import uuid

from .base import TranslationProvider

log = logging.getLogger(__name__)

_AZURE_DEFAULT_ENDPOINT = "https://api.cognitive.microsofttranslator.com"

_AZURE_LANG_MAP = {
    "en": "en", "ar": "ar", "fr": "fr", "de": "de", "es": "es",
    "zh": "zh-Hans", "ja": "ja", "ru": "ru", "tr": "tr", "it": "it",
    "pt": "pt", "nl": "nl", "pl": "pl", "ko": "ko",
}


class AzureTranslatorProvider(TranslationProvider):
    provider_id = "azure"
    display_name = "Azure AI Translator"
    description = "Microsoft's enterprise-grade translation service. Preferred for corporate and government environments requiring data sovereignty and compliance."
    best_for = "Corporate & enterprise"

    def __init__(self, api_key: str | None = None, extra_config: dict | None = None):
        super().__init__(api_key=api_key, extra_config=extra_config)
        cfg = extra_config or {}
        self._endpoint = cfg.get("endpoint", _AZURE_DEFAULT_ENDPOINT)
        self._region = cfg.get("region", "eastus")

    def supports_language_pair(self, source_lang: str, target_lang: str) -> bool:
        # Azure supports 100+ languages including Arabic
        return source_lang.lower() in _AZURE_LANG_MAP and target_lang.lower() in _AZURE_LANG_MAP

    async def translate_batch(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        import httpx

        if not self.api_key:
            raise RuntimeError("Azure Translator API key not configured")

        src_code = _AZURE_LANG_MAP.get(source_lang.lower(), source_lang)
        tgt_code = _AZURE_LANG_MAP.get(target_lang.lower(), target_lang)

        body = [{"text": t} for t in texts]
        headers = {
            "Ocp-Apim-Subscription-Key": self.api_key,
            "Ocp-Apim-Subscription-Region": self._region,
            "Content-Type": "application/json; charset=UTF-8",
            "X-ClientTraceId": str(uuid.uuid4()),
        }
        params = {
            "api-version": "3.0",
            "from": src_code,
            "to": tgt_code,
            "textType": "plain",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{self._endpoint}/translate",
                headers=headers,
                params=params,
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()
            return [item["translations"][0]["text"] for item in data]

    async def health_check(self) -> dict:
        import httpx
        if not self.api_key:
            return {"ok": False, "latency_ms": None, "message": "API key not configured"}
        try:
            t0 = time.monotonic()
            headers = {
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Ocp-Apim-Subscription-Region": self._region,
            }
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._endpoint}/languages",
                    params={"api-version": "3.0"},
                    headers=headers,
                )
                resp.raise_for_status()
                latency_ms = int((time.monotonic() - t0) * 1000)
                lang_count = len(resp.json().get("translation", {}))
                return {"ok": True, "latency_ms": latency_ms, "message": f"Region: {self._region} · {lang_count} languages"}
        except Exception as e:
            return {"ok": False, "latency_ms": None, "message": str(e)}
