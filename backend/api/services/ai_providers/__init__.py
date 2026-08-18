"""
AI provider abstraction layer.

Providers are registered here. The active provider is resolved at
request time from the in-memory provider registry so that callers
can switch providers without restarting the server.
"""
from .base import BaseAIProvider
from .mock_provider import MockProvider
from .gemini_provider import GeminiProvider
from .claude_provider import ClaudeProvider
from .openai_provider import OpenAIProvider
from .ollama_provider import OllamaProvider
from .copilot_provider import CopilotProvider
from .registry import provider_registry

__all__ = [
    "BaseAIProvider",
    "MockProvider",
    "GeminiProvider",
    "ClaudeProvider",
    "OpenAIProvider",
    "OllamaProvider",
    "CopilotProvider",
    "provider_registry",
]
