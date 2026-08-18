"""Google Gemini provider via the OpenAI-compatible Gemini endpoint."""
from __future__ import annotations
import os
from typing import List, Tuple, Optional, Dict, Any, AsyncIterator

from .base import BaseAIProvider
from ..xray_knowledge import XRAY_SYSTEM_PROMPT, LINKEDIN_SYSTEM_PROMPT, XRAY_IMAGE_SYSTEM_PROMPT

_DEFAULT_MODEL = "gemini-3.1-flash-lite"
_GEMINI_OPENAI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/openai"


class GeminiProvider(BaseAIProvider):
    provider_id = "gemini"
    provider_name = "Google Gemini"
    provider_type = "gemini"
    description = (
        "Google Gemini via API key from GEMINI_API_KEY. "
        "Uses the OpenAI-compatible Gemini endpoint."
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key or os.environ.get("GEMINI_API_KEY"))

    def _effective_key(self) -> str:
        key = self.api_key or os.environ.get("GEMINI_API_KEY", "")
        if not key:
            raise ValueError("GEMINI_API_KEY is missing. Set GEMINI_API_KEY in .env.")
        return key

    def _client(self):
        from openai import AsyncOpenAI

        # The SDK's default timeout is ~600s per request with no override
        # here. A single stalled connection (observed: sockets sitting in
        # CloseWait against Google's endpoint — the remote side dropped the
        # connection without completing the response) then blocks an entire
        # sequential retry loop for up to 4x that before giving up — a real
        # 69-slide/568-segment translation was observed hung 50+ minutes
        # with zero checkpoint progress from exactly this. A much shorter
        # timeout lets the existing batch/segment retry-with-backoff logic
        # in batch_translator.py actually do its job instead of the first
        # stuck request silently eating the whole request budget.
        return AsyncOpenAI(
            api_key=self._effective_key(),
            base_url=_GEMINI_OPENAI_BASE_URL,
            timeout=60.0,
        )

    def _model(self) -> str:
        return self.model or _DEFAULT_MODEL

    def _build_messages(self, messages: List[Dict[str, Any]], system_prompt: str) -> List[Dict[str, Any]]:
        system = system_prompt or XRAY_SYSTEM_PROMPT
        return [{"role": "system", "content": system}] + messages

    async def chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> str:
        client = self._client()
        response = await client.chat.completions.create(
            model=self._model(),
            messages=self._build_messages(messages, system_prompt),
            max_completion_tokens=max_tokens or 2048,
        )
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
        )
        async for chunk in stream:
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Any:
        """Non-streaming completion with OpenAI-style function/tool calling.

        Gemini's OpenAI-compatibility endpoint accepts the same ``tools=``
        JSON-schema array as OpenAI. Returns the raw ``choices[0].message``
        object — callers should check ``message.tool_calls``.

        Used by the AI Chat Workspace agent loop only; plain chat/stream_chat
        are untouched by this addition.
        """
        client = self._client()
        response = await client.chat.completions.create(
            model=self._model(),
            messages=self._build_messages(messages, system_prompt),
            tools=tools,
            tool_choice="auto",
            max_completion_tokens=4096,
        )
        return response.choices[0].message

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
            "Audience: X-ray security screening professionals.\n"
            "End with: HASHTAGS: #tag1 #tag2 ..."
        )
        response = await client.chat.completions.create(
            model=self._model(),
            messages=[
                {"role": "system", "content": LINKEDIN_SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            max_completion_tokens=1024,
        )
        raw = response.choices[0].message.content or ""
        if "HASHTAGS:" in raw:
            parts = raw.split("HASHTAGS:", 1)
            content = parts[0].strip()
            hashtags = [h.strip() for h in parts[1].strip().split() if h.startswith("#")]
        else:
            content = raw
            hashtags = ["#XRayAcademy", "#SecurityScreening"]
        return content, hashtags

    async def analyze_xray_image(
        self,
        image_base64: str,
        scanner_type: str,
        context: Optional[str],
    ) -> Tuple[str, str, List[str]]:
        from .openai_provider import _parse_analysis_response

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
        raw = response.choices[0].message.content or ""
        return _parse_analysis_response(raw)
