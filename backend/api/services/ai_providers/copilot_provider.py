"""Microsoft Copilot / Azure OpenAI provider with streaming."""
from __future__ import annotations
from typing import List, Tuple, Optional, Dict, Any, AsyncIterator

from .base import BaseAIProvider
from ..xray_knowledge import XRAY_SYSTEM_PROMPT, LINKEDIN_SYSTEM_PROMPT, XRAY_IMAGE_SYSTEM_PROMPT


class CopilotProvider(BaseAIProvider):
    provider_id = "copilot"
    provider_name = "Microsoft Copilot (Azure OpenAI)"
    provider_type = "copilot"
    description = "Microsoft Copilot via Azure OpenAI Service. Requires an Azure OpenAI resource endpoint, API key, and deployment name."

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key and self.base_url)

    def _client(self):
        from openai import AsyncAzureOpenAI
        return AsyncAzureOpenAI(api_key=self.api_key, azure_endpoint=self.base_url, api_version="2024-02-01")

    def _model(self) -> str:
        return self.model or "gpt-4"

    async def chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> str:
        client = self._client()
        system = system_prompt or XRAY_SYSTEM_PROMPT
        response = await client.chat.completions.create(
            model=self._model(),
            messages=[{"role": "system", "content": system}] + messages,
            temperature=0.7, max_tokens=max_tokens or 1500,
        )
        return response.choices[0].message.content or ""

    async def stream_chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> AsyncIterator[str]:
        client = self._client()
        system = system_prompt or XRAY_SYSTEM_PROMPT
        stream = await client.chat.completions.create(
            model=self._model(),
            messages=[{"role": "system", "content": system}] + messages,
            temperature=0.7, max_tokens=max_tokens or 1500, stream=True,
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content

    async def generate_linkedin_post(self, topic: str, tone: str, length: str, keywords: Optional[List[str]]) -> Tuple[str, List[str]]:
        client = self._client()
        length_map = {"short": "150-200 words", "medium": "250-350 words", "long": "450-600 words"}
        kw_line = f"\nKeywords: {', '.join(keywords)}" if keywords else ""
        prompt = f"Write a {tone} LinkedIn post about: {topic}\nLength: {length_map.get(length, '250-350 words')}{kw_line}\nEnd with HASHTAGS: #tag1 #tag2"
        response = await client.chat.completions.create(
            model=self._model(),
            messages=[{"role": "system", "content": LINKEDIN_SYSTEM_PROMPT}, {"role": "user", "content": prompt}],
            temperature=0.8, max_tokens=800,
        )
        raw = response.choices[0].message.content or ""
        if "HASHTAGS:" in raw:
            parts = raw.split("HASHTAGS:", 1)
            return parts[0].strip(), [h.strip() for h in parts[1].strip().split() if h.startswith("#")]
        return raw, ["#XRayAcademy", "#SecurityScreening"]

    async def analyze_xray_image(self, image_base64: str, scanner_type: str, context: Optional[str]) -> Tuple[str, str, List[str]]:
        from .openai_provider import _parse_analysis_response
        client = self._client()
        ctx_note = f"\nContext: {context}" if context else ""
        prompt = f"Analyze this X-ray security image from a {scanner_type} scanner.{ctx_note}\nProvide FINDINGS, THREAT_LEVEL, and RECOMMENDATIONS."
        response = await client.chat.completions.create(
            model=self._model(),
            messages=[
                {"role": "system", "content": XRAY_IMAGE_SYSTEM_PROMPT},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}},
                ]},
            ],
            max_tokens=1000,
        )
        return _parse_analysis_response(response.choices[0].message.content or "")
