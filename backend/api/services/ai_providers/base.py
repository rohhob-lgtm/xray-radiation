"""
Abstract base class for all AI providers.

Each provider must implement:
  - chat(messages, system_prompt) → str
  - stream_chat(messages, system_prompt) → AsyncIterator[str]
  - generate_linkedin_post(topic, tone, length, keywords) → (content, hashtags)
  - analyze_xray_image(image_b64, scanner_type, context) → (findings, threat_level, recommendations)
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import List, Tuple, Optional, Dict, Any, AsyncIterator


class BaseAIProvider(ABC):
    provider_id: str = ""
    provider_name: str = ""
    provider_type: str = ""
    description: str = ""

    def __init__(self, api_key: str = "", base_url: str = "", model: str = ""):
        self.api_key = api_key
        self.base_url = base_url
        self.model = model

    @property
    def is_configured(self) -> bool:
        return True

    @abstractmethod
    async def chat(self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None) -> str:
        """Send messages and return full assistant reply. max_tokens is an
        optional per-call override — None keeps each provider's own default;
        providers that don't support tuning it are free to ignore it."""

    @abstractmethod
    async def stream_chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = "", max_tokens: Optional[int] = None
    ) -> AsyncIterator[str]:
        """Stream the assistant reply token by token."""
        # Ensure this is typed as an async generator
        return
        yield  # Make it a generator

    @abstractmethod
    async def generate_linkedin_post(
        self,
        topic: str,
        tone: str,
        length: str,
        keywords: Optional[List[str]],
    ) -> Tuple[str, List[str]]:
        """Return (post_content, hashtags)."""

    @abstractmethod
    async def analyze_xray_image(
        self,
        image_base64: str,
        scanner_type: str,
        context: Optional[str],
    ) -> Tuple[str, str, List[str]]:
        """Return (findings_text, threat_level, recommendations)."""
