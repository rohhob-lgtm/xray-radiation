"""
OpenAI Translation Provider.

Uses GPT-4o with a structured technical translation prompt.
This is the fallback provider — always available when OPENAI_API_KEY is set.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re

from .base import TranslationProvider

log = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a senior professional technical translator specialising in:
- X-ray security screening systems
- Radiation physics and dosimetry
- Electro-mechanical engineering and maintenance
- Aviation and border security equipment

Translate from {source_lang} to {target_lang}.
Style: Technical — precise, consistent engineering register.

Rules:
- Preserve all numbers, units, model numbers, part numbers, error codes exactly.
- Use accepted engineering and technical terminology from relevant standards (IEC, ISO, IEEE).
- Product names and trade names: preserve in original language or transliterate per convention.
- Return ONLY a valid JSON object: {{"translations": {{"0": "...", "1": "..."}}}}
- Do NOT add commentary or any text outside the JSON."""


class OpenAITranslatorProvider(TranslationProvider):
    provider_id = "openai"
    display_name = "OpenAI GPT-4o"
    description = "AI-powered translation with domain-specific engineering prompts. Best for AI-assisted editing and post-editing workflows."
    best_for = "AI editing & domain review"

    # Retry config
    _MAX_RETRIES = 4
    _RETRY_BASE_SECS = 8

    def __init__(self, api_key: str | None = None, extra_config: dict | None = None):
        super().__init__(api_key=api_key or os.environ.get("OPENAI_API_KEY"), extra_config=extra_config)
        self._model = (extra_config or {}).get("model", "gpt-4o")

    def supports_language_pair(self, source_lang: str, target_lang: str) -> bool:
        # GPT-4o supports virtually all language pairs
        return True

    async def translate_batch(self, texts: list[str], source_lang: str, target_lang: str) -> list[str]:
        from openai import AsyncOpenAI, RateLimitError
        client = AsyncOpenAI(api_key=self.api_key)

        lang_names = {
            "en": "English", "ar": "Arabic", "fr": "French",
            "de": "German", "es": "Spanish", "zh": "Chinese",
            "ja": "Japanese", "ru": "Russian", "tr": "Turkish",
        }
        src_name = lang_names.get(source_lang, source_lang)
        tgt_name = lang_names.get(target_lang, target_lang)

        system_prompt = _SYSTEM_PROMPT.format(source_lang=src_name, target_lang=tgt_name)
        input_map = {str(i): t for i, t in enumerate(texts)}
        user_msg = (
            "Translate every value in the JSON object below.\n"
            "Return ONLY valid JSON: {\"translations\": {\"0\": \"...\"}}\n"
            "Preserve \\n line breaks exactly.\n\n"
            "Input:\n" + json.dumps(input_map, ensure_ascii=False)
        )

        last_exc: Exception | None = None
        for attempt in range(self._MAX_RETRIES):
            try:
                resp = await client.chat.completions.create(
                    model=self._model,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_msg},
                    ],
                    max_completion_tokens=16000,
                    temperature=0.1,
                    response_format={"type": "json_object"},
                )
                raw = resp.choices[0].message.content or "{}"
                data = json.loads(raw)
                translations = data.get("translations", data)
                result = [translations.get(str(i), texts[i]) for i in range(len(texts))]
                return result

            except RateLimitError as e:
                last_exc = e
                wait = self._RETRY_BASE_SECS * (2 ** attempt)
                log.warning("OpenAI rate limit (attempt %d/%d) — waiting %ds", attempt + 1, self._MAX_RETRIES, wait)
                if attempt < self._MAX_RETRIES - 1:
                    await asyncio.sleep(wait)
                    continue
                raise RuntimeError(f"Rate limit after {self._MAX_RETRIES} attempts: {e}") from e

            except json.JSONDecodeError:
                # Try partial recovery
                try:
                    m = re.search(r'\{.*\}', raw, re.DOTALL)
                    if m:
                        data = json.loads(m.group())
                        translations = data.get("translations", data)
                        return [translations.get(str(i), texts[i]) for i in range(len(texts))]
                except Exception:
                    pass
                return list(texts)  # fallback: return source unchanged

            except Exception as e:
                err_name = type(e).__name__
                retriable = any(k in err_name for k in ("ServiceUnavailable", "Timeout", "Connection"))
                if retriable and attempt < self._MAX_RETRIES - 1:
                    wait = self._RETRY_BASE_SECS * (2 ** attempt)
                    log.warning("OpenAI retriable error %s attempt %d — waiting %ds", err_name, attempt + 1, wait)
                    await asyncio.sleep(wait)
                    continue
                raise

        raise RuntimeError(f"OpenAI translation failed after {self._MAX_RETRIES} attempts: {last_exc}")

    async def health_check(self) -> dict:
        import time
        try:
            from openai import AsyncOpenAI
            client = AsyncOpenAI(api_key=self.api_key)
            t0 = time.monotonic()
            resp = await client.chat.completions.create(
                model=self._model,
                messages=[{"role": "user", "content": 'Reply with JSON: {"ok": true}'}],
                max_completion_tokens=10,
                response_format={"type": "json_object"},
            )
            latency_ms = int((time.monotonic() - t0) * 1000)
            return {"ok": True, "latency_ms": latency_ms, "message": f"Model: {self._model}"}
        except Exception as e:
            return {"ok": False, "latency_ms": None, "message": str(e)}
