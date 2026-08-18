"""OpenAI provider — gpt-5.4 with full streaming, vision, and RAG support."""
from __future__ import annotations
import os
from typing import List, Tuple, Optional, Dict, Any, AsyncIterator

from .base import BaseAIProvider
from ..xray_knowledge import XRAY_SYSTEM_PROMPT, LINKEDIN_SYSTEM_PROMPT, XRAY_IMAGE_SYSTEM_PROMPT

# Default model: gpt-5.4 is vision-capable and handles RAG QA, image analysis,
# research generation, and report writing.
_DEFAULT_MODEL = "gpt-5.4"


class OpenAIProvider(BaseAIProvider):
    provider_id = "openai"
    provider_name = "OpenAI gpt-5.4"
    provider_type = "openai"
    description = (
        "OpenAI gpt-5.4 — vision-capable model for RAG answers, X-ray image analysis, "
        "research generation, and technical report writing. API key auto-loaded from environment."
    )

    @property
    def is_configured(self) -> bool:
        # Accept key from the instance or directly from the environment
        return bool(self.api_key or os.environ.get("OPENAI_API_KEY"))

    def _effective_key(self) -> str:
        return self.api_key or os.environ.get("OPENAI_API_KEY", "")

    def _client(self):
        from openai import AsyncOpenAI
        return AsyncOpenAI(api_key=self._effective_key())

    def _model(self) -> str:
        return self.model or _DEFAULT_MODEL

    def _build_messages(self, messages: List[Dict[str, Any]], system_prompt: str) -> List[Dict]:
        system = system_prompt or XRAY_SYSTEM_PROMPT
        return [{"role": "system", "content": system}] + messages

    # ── Text chat ──────────────────────────────────────────

    async def chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> str:
        import time as _time
        client = self._client()
        _t0 = _time.monotonic()
        response = await client.chat.completions.create(
            model=self._model(),
            messages=self._build_messages(messages, system_prompt),
            max_completion_tokens=max_tokens or 2048,
        )
        try:
            from api.utils.usage_recorder import record_usage_from_response
            record_usage_from_response(
                "AI Chat (non-stream)", response,
                duration_ms=int((_time.monotonic() - _t0) * 1000),
                sub_feature="chat",
            )
        except Exception:
            pass
        return response.choices[0].message.content or ""

    async def stream_chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> AsyncIterator[str]:
        client = self._client()
        stream = await client.chat.completions.create(
            model=self._model(),
            messages=self._build_messages(messages, system_prompt),
            max_completion_tokens=max_tokens or 2048,
            stream=True,
            stream_options={"include_usage": True},
        )
        async for chunk in stream:
            if not chunk.choices:
                # Final usage chunk from stream_options
                try:
                    from api.utils.usage_recorder import record_usage_from_response
                    record_usage_from_response("AI Chat", chunk, sub_feature="stream_chat")
                except Exception:
                    pass
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    # ── LinkedIn post generation ───────────────────────────

    async def generate_linkedin_post(
        self,
        topic: str,
        tone: str,
        length: str,
        keywords: Optional[List[str]],
    ) -> Tuple[str, List[str]]:
        client = self._client()
        length_map = {
            "short": "150-200 words",
            "medium": "250-350 words",
            "long": "450-600 words",
        }
        word_count = length_map.get(length, "250-350 words")
        kw_line = f"\nKeywords to include: {', '.join(keywords)}" if keywords else ""

        prompt = (
            f"Write a {tone} LinkedIn post about: {topic}\n"
            f"Length: {word_count}{kw_line}\n"
            f"Audience: X-ray security screening professionals.\n"
            f"End with: HASHTAGS: #tag1 #tag2 ..."
        )
        response = await client.chat.completions.create(
            model=self._model(),
            messages=[
                {"role": "system", "content": LINKEDIN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=1024,
        )
        try:
            from api.utils.usage_recorder import record_usage_from_response
            record_usage_from_response("LinkedIn Generator", response, sub_feature="post_generation")
        except Exception:
            pass
        raw = response.choices[0].message.content or ""
        if "HASHTAGS:" in raw:
            parts = raw.split("HASHTAGS:", 1)
            content = parts[0].strip()
            hashtags = [h.strip() for h in parts[1].strip().split() if h.startswith("#")]
        else:
            content = raw
            hashtags = ["#XRayAcademy", "#SecurityScreening"]
        return content, hashtags

    # ── X-ray image analysis (vision) ─────────────────────

    async def analyze_xray_image(
        self,
        image_base64: str,
        scanner_type: str,
        context: Optional[str],
    ) -> Tuple[str, str, List[str]]:
        client = self._client()
        ctx_note = f"\nOperator context: {context}" if context else ""
        prompt = (
            f"Analyse this X-ray security image from a {scanner_type} scanner.{ctx_note}\n"
            "Provide:\n"
            "FINDINGS: Detailed description of materials, densities, shapes, and areas of concern.\n"
            "THREAT_LEVEL: one of clear | low | medium | high | critical\n"
            "RECOMMENDATIONS: 3-5 specific, actionable bullet points for the operator."
        )
        response = await client.chat.completions.create(
            model=self._model(),
            messages=[
                {"role": "system", "content": XRAY_IMAGE_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"},
                        },
                    ],
                },
            ],
            max_completion_tokens=1024,
        )
        try:
            from api.utils.usage_recorder import record_usage_from_response
            record_usage_from_response(
                "X-Ray Image Analysis", response,
                sub_feature="xray_vision",
                meta={"scanner_type": scanner_type},
            )
        except Exception:
            pass
        raw = response.choices[0].message.content or ""
        return _parse_analysis_response(raw)


def _parse_analysis_response(raw: str) -> Tuple[str, str, List[str]]:
    findings = raw
    threat_level = "low"
    recommendations: List[str] = []

    if "THREAT_LEVEL:" in raw:
        parts = raw.split("THREAT_LEVEL:")
        findings = parts[0].replace("FINDINGS:", "").strip()
        rest = parts[1]
        lines = rest.strip().split("\n")
        threat_level = lines[0].strip().lower().split()[0] if lines else "low"
        if "RECOMMENDATIONS:" in rest:
            recs_raw = rest.split("RECOMMENDATIONS:", 1)[1]
            recommendations = [
                line.lstrip("- •123456789.").strip()
                for line in recs_raw.strip().split("\n")
                if line.strip()
            ]

    valid = {"clear", "low", "medium", "high", "critical"}
    if threat_level not in valid:
        threat_level = "low"
    return findings, threat_level, recommendations
