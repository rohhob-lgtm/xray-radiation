"""Minimal AI Tutor chat endpoint for the Radiation Sources learning site.

The learning-center "AI Tutor" tab posts to /api/chat/stream and reads an SSE
stream of `data: {"type":"chunk"|"done"|"error", ...}` lines. This is a lean
replacement for the platform's full chat route (no connectors/tools/DB) — it
just streams the active provider's reply, which is all the tutor needs.
"""
from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from api.services.ai_providers.registry import provider_registry

log = logging.getLogger(__name__)
router = APIRouter(tags=["chat"])

_TUTOR_SYSTEM = (
    "You are the AI tutor for a Radiation Sources & Accelerator Engineering "
    "learning platform (X-ray tubes, LINACs, radioisotopes, security/industrial "
    "imaging, radiation protection). Answer clearly and concisely for a learner. "
    "Reply in the same language as the question."
)


def _sse(obj: dict) -> str:
    return "data: " + json.dumps(obj, ensure_ascii=False) + "\n"


@router.post("/chat/stream")
async def chat_stream(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = str((body or {}).get("message", "")).strip()

    async def gen():
        if not message:
            yield _sse({"type": "error", "error": "Empty message."})
            return
        try:
            provider = provider_registry.get_active() or provider_registry.get_for_task(None)
            if provider is None:
                yield _sse({"type": "error", "error": "No AI provider configured."})
                return
            history = [{"role": "user", "content": message}]
            got = False
            async for chunk in provider.stream_chat(history, system_prompt=_TUTOR_SYSTEM, max_tokens=1200):
                if chunk:
                    got = True
                    yield _sse({"type": "chunk", "chunk": chunk})
            if not got:
                yield _sse({"type": "error", "error": "The AI tutor returned no reply."})
            else:
                yield _sse({"type": "done"})
        except Exception as exc:  # pragma: no cover
            log.warning("AI tutor stream failed: %s", exc, exc_info=True)
            yield _sse({"type": "error", "error": "The AI tutor is unavailable right now."})

    return StreamingResponse(gen(), media_type="text/event-stream")
