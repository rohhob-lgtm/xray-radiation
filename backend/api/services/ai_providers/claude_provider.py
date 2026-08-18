"""Anthropic Claude provider — second first-class AI provider alongside Gemini."""
from __future__ import annotations
import json
import os
import time
from typing import List, Tuple, Optional, Dict, Any, AsyncIterator

from .base import BaseAIProvider
from ..xray_knowledge import XRAY_SYSTEM_PROMPT, LINKEDIN_SYSTEM_PROMPT, XRAY_IMAGE_SYSTEM_PROMPT

_DEFAULT_MODEL = "claude-sonnet-5"


class _SimpleFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class _SimpleToolCall:
    def __init__(self, call_id: str, name: str, arguments: str):
        self.id = call_id
        self.type = "function"
        self.function = _SimpleFunction(name, arguments)


class _SimpleMessage:
    """Duck-types the OpenAI SDK's `choices[0].message` shape so callers built
    against GeminiProvider.chat_with_tools() (the AI Chat tool loop, the
    connector tool router) work unchanged against Claude's native tool_use
    blocks — no caller-side branching per provider."""

    def __init__(self, content: str, tool_calls: List[_SimpleToolCall]):
        self.content = content
        self.tool_calls = tool_calls


def _parse_data_url(url: str) -> Tuple[str, str]:
    """'data:image/jpeg;base64,<b64>' -> ('image/jpeg', '<b64>')."""
    if not url.startswith("data:") or ";base64," not in url:
        return "image/jpeg", ""
    header, b64data = url.split(",", 1)
    media_type = header[len("data:"):].split(";", 1)[0] or "image/jpeg"
    return media_type, b64data


def _record_usage(feature: str, response: Any, *, sub_feature: Optional[str] = None,
                   duration_ms: int = 0, meta: Optional[dict] = None) -> None:
    try:
        from api.utils.usage_recorder import record_usage
        usage = getattr(response, "usage", None)
        if not usage:
            return
        record_usage(
            feature=feature,
            model=getattr(response, "model", None),
            prompt_tokens=getattr(usage, "input_tokens", 0) or 0,
            completion_tokens=getattr(usage, "output_tokens", 0) or 0,
            cached_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
            duration_ms=duration_ms,
            sub_feature=sub_feature,
            meta=meta,
        )
    except Exception:
        pass


class ClaudeProvider(BaseAIProvider):
    provider_id = "claude"
    provider_name = "Anthropic Claude"
    provider_type = "claude"
    description = (
        "Anthropic Claude via API key from ANTHROPIC_API_KEY. "
        "Strong on code, long documents, structured writing, and translation refinement."
    )

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key or os.environ.get("ANTHROPIC_API_KEY"))

    def _effective_key(self) -> str:
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise ValueError("ANTHROPIC_API_KEY is missing. Set ANTHROPIC_API_KEY in .env.")
        return key

    def _client(self):
        from anthropic import AsyncAnthropic

        return AsyncAnthropic(api_key=self._effective_key())

    def _model(self) -> str:
        return self.model or _DEFAULT_MODEL

    def _to_claude_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Convert the OpenAI-shaped message list used throughout this codebase
        (plain chat, tool_calls, tool results, vision content blocks) into
        Claude's Messages API shape."""
        claude_messages: List[Dict[str, Any]] = []
        for m in messages:
            role = m.get("role")
            if role == "system":
                continue  # carried separately as the `system` param
            if role == "tool":
                claude_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": m.get("tool_call_id"),
                        "content": str(m.get("content", "")),
                    }],
                })
                continue
            if role == "assistant" and m.get("tool_calls"):
                content: List[Dict[str, Any]] = []
                if m.get("content"):
                    content.append({"type": "text", "text": m["content"]})
                for tc in m["tool_calls"]:
                    fn = tc.get("function", {})
                    try:
                        tool_input = json.loads(fn.get("arguments") or "{}")
                    except json.JSONDecodeError:
                        tool_input = {}
                    content.append({
                        "type": "tool_use", "id": tc.get("id"),
                        "name": fn.get("name"), "input": tool_input,
                    })
                claude_messages.append({"role": "assistant", "content": content})
                continue

            content = m.get("content")
            if isinstance(content, list):
                claude_content: List[Dict[str, Any]] = []
                for block in content:
                    if block.get("type") == "text":
                        claude_content.append({"type": "text", "text": block.get("text", "")})
                    elif block.get("type") == "image_url":
                        url = (block.get("image_url") or {}).get("url", "")
                        media_type, b64data = _parse_data_url(url)
                        if b64data:
                            claude_content.append({
                                "type": "image",
                                "source": {"type": "base64", "media_type": media_type, "data": b64data},
                            })
                claude_messages.append({"role": role, "content": claude_content})
            else:
                claude_messages.append({"role": role, "content": content or ""})
        return claude_messages

    # ── Text chat ──────────────────────────────────────────

    async def chat(self, messages: List[Dict[str, Any]], system_prompt: str = "") -> str:
        client = self._client()
        t0 = time.monotonic()
        response = await client.messages.create(
            model=self._model(),
            max_tokens=2048,
            system=system_prompt or XRAY_SYSTEM_PROMPT,
            messages=self._to_claude_messages(messages),
        )
        _record_usage("AI Chat (non-stream)", response,
                       duration_ms=int((time.monotonic() - t0) * 1000), sub_feature="chat")
        return "".join(b.text for b in response.content if b.type == "text")

    async def stream_chat(
        self, messages: List[Dict[str, Any]], system_prompt: str = ""
    ) -> AsyncIterator[str]:
        client = self._client()
        async with client.messages.stream(
            model=self._model(),
            max_tokens=4096,
            system=system_prompt or XRAY_SYSTEM_PROMPT,
            messages=self._to_claude_messages(messages),
        ) as stream:
            async for text in stream.text_stream:
                yield text
            final = await stream.get_final_message()
            _record_usage("AI Chat", final, sub_feature="stream_chat")

    async def chat_with_tools(
        self,
        messages: List[Dict[str, Any]],
        tools: List[Dict[str, Any]],
        system_prompt: str = "",
    ) -> Any:
        """OpenAI-style tool schemas in, a duck-typed OpenAI-style message out —
        so the connector tool router and AI Chat Workspace agent (built against
        Gemini's chat_with_tools) work against Claude with no caller changes."""
        client = self._client()
        claude_tools = [
            {
                "name": t["function"]["name"],
                "description": t["function"].get("description", ""),
                "input_schema": t["function"].get("parameters") or {"type": "object", "properties": {}},
            }
            for t in tools
        ]
        response = await client.messages.create(
            model=self._model(),
            max_tokens=4096,
            system=system_prompt or XRAY_SYSTEM_PROMPT,
            tools=claude_tools,
            messages=self._to_claude_messages(messages),
        )
        _record_usage("AI Chat (tools)", response, sub_feature="chat_with_tools")
        text = "".join(b.text for b in response.content if b.type == "text")
        tool_calls = [
            _SimpleToolCall(b.id, b.name, json.dumps(b.input))
            for b in response.content if b.type == "tool_use"
        ]
        return _SimpleMessage(text, tool_calls)

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
            "Audience: X-ray security screening professionals.\n"
            "End with: HASHTAGS: #tag1 #tag2 ..."
        )
        response = await client.messages.create(
            model=self._model(),
            max_tokens=1024,
            system=LINKEDIN_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        _record_usage("LinkedIn Generator", response, sub_feature="post_generation")
        raw = "".join(b.text for b in response.content if b.type == "text")
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
        response = await client.messages.create(
            model=self._model(),
            max_tokens=1024,
            system=XRAY_IMAGE_SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": image_base64}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )
        _record_usage("X-Ray Image Analysis", response, sub_feature="xray_vision", meta={"scanner_type": scanner_type})
        raw = "".join(b.text for b in response.content if b.type == "text")
        return _parse_analysis_response(raw)
