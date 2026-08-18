"""
Shared text-embedding helper.

Single place that owns the OpenAI embedding client so every caller (RAG
documents, memory items, conversation summaries, workspace resources) embeds
with the same model and the same timeout/error-handling behavior.
"""
from __future__ import annotations
import os
from typing import List, Optional

EMBEDDING_MODEL = "text-embedding-3-small"


async def get_embedding(text: str) -> Optional[List[float]]:
    """Generate a text-embedding-3-small vector, using the env key directly.

    Returns None (never raises) when no API key is configured or the call
    fails — callers treat a missing embedding as "keyword-search only".
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None
    try:
        from openai import AsyncOpenAI
        # Explicit 10-second timeout so a slow API never blocks the event loop forever
        client = AsyncOpenAI(api_key=api_key, timeout=10.0)
        resp = await client.embeddings.create(
            input=text[:8000],
            model=EMBEDDING_MODEL,
        )
        return resp.data[0].embedding
    except Exception:
        return None
