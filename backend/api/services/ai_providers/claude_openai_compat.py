"""
Minimal OpenAI-SDK-shaped wrapper around Anthropic's Messages API.

Several existing pipelines (Translation Studio's translate_segments /
run_engineering_review) are written directly against an `AsyncOpenAI`-style
client — `client.chat.completions.create(model=, messages=, ...)` returning
`.choices[0].message.content` and `.usage.prompt_tokens/.completion_tokens`.
That shape is also what Gemini's OpenAI-compatibility endpoint speaks, which
is how Gemini already plugs into those same call sites.

Anthropic has no OpenAI-compatible endpoint, so the same trick doesn't work
by pointing an AsyncOpenAI client's base_url at Anthropic. This class instead
implements the same minimal surface natively against the real Anthropic SDK,
so translate_segments/run_engineering_review can call Claude with zero
changes to their own code.

Two deliberate incompatibilities, both handled here rather than left to
surprise the caller:
  - `temperature` is dropped. Claude Sonnet 5 (and Opus 5/4.7/Fable 5) reject
    any non-default sampling parameter with a 400 — silently forwarding the
    caller's `temperature=0.1` would break every request.
  - `response_format={"type": "json_object"}` is dropped (Claude has no
    equivalent flag). The existing prompts already say "Return ONLY a valid
    JSON object..." explicitly, which Claude follows reliably via plain
    prompting; callers still get a JSON string to parse.
"""
from __future__ import annotations

from typing import Any, List, Dict, Optional


class _Message:
    def __init__(self, content: str):
        self.content = content


class _Choice:
    def __init__(self, content: str):
        self.message = _Message(content)


class _UsageDetails:
    def __init__(self, cached_tokens: int):
        self.cached_tokens = cached_tokens


class _Usage:
    def __init__(self, prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.prompt_tokens_details = _UsageDetails(cached_tokens)


class _CompletionResponse:
    def __init__(self, content: str, usage: _Usage, model: Optional[str] = None):
        self.choices = [_Choice(content)]
        self.usage = usage
        self.model = model


class _Completions:
    def __init__(self, anthropic_client: Any):
        self._client = anthropic_client

    async def create(
        self,
        *,
        model: str,
        messages: List[Dict[str, Any]],
        max_completion_tokens: int = 2048,
        **_ignored: Any,  # temperature, response_format, etc. — see module docstring
    ) -> _CompletionResponse:
        system_parts = [m["content"] for m in messages if m.get("role") == "system"]
        system = "\n\n".join(system_parts)
        claude_messages = [
            {"role": m["role"], "content": m["content"]}
            for m in messages if m.get("role") != "system"
        ]
        response = await self._client.messages.create(
            model=model,
            max_tokens=max_completion_tokens,
            system=system,
            messages=claude_messages,
        )
        text = "".join(b.text for b in response.content if b.type == "text")
        usage = response.usage
        return _CompletionResponse(
            text,
            _Usage(
                prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
                completion_tokens=getattr(usage, "output_tokens", 0) or 0,
                cached_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            ),
            model=model,
        )


class _ChatNamespace:
    def __init__(self, anthropic_client: Any):
        self.completions = _Completions(anthropic_client)


class ClaudeOpenAICompatClient:
    """Drop-in replacement for `openai.AsyncOpenAI` backed by Claude — only
    implements `.chat.completions.create(...)`, the one surface the existing
    translation pipeline actually calls."""

    def __init__(self, api_key: str):
        import anthropic

        self._anthropic = anthropic.AsyncAnthropic(api_key=api_key)
        self.chat = _ChatNamespace(self._anthropic)
