"""Ollama provider — local models with streaming support."""
from __future__ import annotations
import json
from typing import List, Tuple, Optional, Dict, Any, AsyncIterator

import httpx

from .base import BaseAIProvider
from ..xray_knowledge import XRAY_SYSTEM_PROMPT, LINKEDIN_SYSTEM_PROMPT, XRAY_IMAGE_SYSTEM_PROMPT


class OllamaProvider(BaseAIProvider):
    provider_id = "ollama"
    provider_name = "Ollama (Local)"
    provider_type = "ollama"
    description = "Run open-source models locally via Ollama. Supports Llama, Mistral, Phi, and more. Requires Ollama running on the same network."

    @property
    def is_configured(self) -> bool:
        return bool(self.base_url)

    def _url(self) -> str:
        return (self.base_url or "http://127.0.0.1:11434").rstrip("/")

    def _model(self) -> str:
        return self.model or "qwen2.5-7b-fast6:latest"

    async def chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> str:
        system = system_prompt or XRAY_SYSTEM_PROMPT
        ollama_messages = [{"role": "system", "content": system}] + messages
        options = {"num_predict": max_tokens} if max_tokens else {}
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{self._url()}/api/chat",
                json={"model": self._model(), "messages": ollama_messages, "stream": False, "options": options},
            )
            response.raise_for_status()
            return response.json().get("message", {}).get("content", "")

    async def stream_chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> AsyncIterator[str]:
        system = system_prompt or XRAY_SYSTEM_PROMPT
        ollama_messages = [{"role": "system", "content": system}] + messages
        options = {"num_predict": max_tokens} if max_tokens else {}
        # Keep streaming bounded so stalled local inference fails fast.
        stream_timeout = httpx.Timeout(connect=20.0, read=45.0, write=120.0, pool=120.0)
        async with httpx.AsyncClient(timeout=stream_timeout) as client:
            async with client.stream(
                "POST",
                f"{self._url()}/api/chat",
                json={"model": self._model(), "messages": ollama_messages, "stream": True, "options": options},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        content = data.get("message", {}).get("content", "")
                        if content:
                            yield content
                        if data.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

    async def generate_linkedin_post(self, topic: str, tone: str, length: str, keywords: Optional[List[str]]) -> Tuple[str, List[str]]:
        length_map = {"short": "150-200 words", "medium": "250-350 words", "long": "450-600 words"}
        kw_line = f"\nKeywords: {', '.join(keywords)}" if keywords else ""
        prompt = f"Write a {tone} LinkedIn post about: {topic}\nLength: {length_map.get(length, '250-350 words')}{kw_line}\nAudience: X-ray security professionals.\nEnd with: HASHTAGS: #tag1 #tag2"
        msgs = [{"role": "system", "content": LINKEDIN_SYSTEM_PROMPT}, {"role": "user", "content": prompt}]
        raw = await self.chat(msgs)
        if "HASHTAGS:" in raw:
            parts = raw.split("HASHTAGS:", 1)
            content = parts[0].strip()
            hashtags = [h.strip() for h in parts[1].strip().split() if h.startswith("#")]
        else:
            content = raw
            hashtags = ["#XRayAcademy", "#SecurityScreening"]
        return content, hashtags

    async def analyze_xray_image(self, image_base64: str, scanner_type: str, context: Optional[str]) -> Tuple[str, str, List[str]]:
        from .openai_provider import _parse_analysis_response
        prompt = f"Analyze this X-ray security image from a {scanner_type} scanner.\nProvide FINDINGS, THREAT_LEVEL (clear/low/medium/high/critical), and RECOMMENDATIONS."
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{self._url()}/api/generate",
                json={"model": "llava", "prompt": prompt, "images": [image_base64], "stream": False, "system": XRAY_IMAGE_SYSTEM_PROMPT},
            )
            response.raise_for_status()
            raw = response.json().get("response", "")
        return _parse_analysis_response(raw)
