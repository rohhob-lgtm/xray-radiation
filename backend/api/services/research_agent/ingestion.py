"""Accepted research content -> shared knowledge base (RagDocument).

Ingested content becomes an ordinary RagDocument row — exactly what
api.routes.study.py's website-crawl endpoint already does today — so the
existing shared api.services.rag_service.retrieve_chunks() path (already
used by chat.py and every other platform section) picks it up automatically,
with zero changes to retrieval itself. Dedup reuses the same platform-wide
SHA-256 DocumentHash table every other ingestion path in this codebase uses.
"""
from __future__ import annotations

import logging
import os

import httpx
from sqlalchemy.orm import Session

from api.db.crud import create_rag_document
from api.services.study_service import compute_sha256, is_duplicate, register_hash

log = logging.getLogger(__name__)


async def get_embedding_for_mission(text: str, free_mode: bool) -> list[float] | None:
    """Embed ingested content.

    Paid OpenAI embeddings are only used when Free Mode is explicitly off.
    When Free Mode is on, an optional local Ollama embedding is attempted;
    if Ollama isn't reachable this returns None and the content is still
    fully usable — rag_service.retrieve_chunks() already has a fully
    supported keyword-only degrade path for documents with no embedding.
    """
    if not free_mode:
        from api.services.embedding_service import get_embedding
        return await get_embedding(text)
    return await _local_ollama_embedding(text)


async def _local_ollama_embedding(text: str) -> list[float] | None:
    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_EMBED_MODEL", "nomic-embed-text")
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.post(
                f"{base_url}/api/embeddings",
                json={"model": model, "prompt": text[:8000]},
            )
            resp.raise_for_status()
            embedding = resp.json().get("embedding")
            return embedding if embedding else None
    except Exception:
        # Ollama not running / model not pulled — Free Mode gracefully
        # degrades to keyword-only retrieval rather than failing the mission
        # or silently falling back to a paid API.
        return None


def ingest_research_content(
    db: Session, *, filename: str, text: str, embedding: list[float] | None,
) -> tuple[str | None, bool]:
    """Create a RagDocument from accepted research content.

    Returns (rag_document_id_or_None, was_duplicate). None is returned when
    the content is too short to be worth ingesting.
    """
    text = (text or "").strip()
    if len(text) < 50:
        return None, False

    sha256 = compute_sha256(text.encode("utf-8", errors="ignore"))
    existing_doc_id = is_duplicate(db, sha256)
    if existing_doc_id:
        return existing_doc_id, True

    doc = create_rag_document(
        db,
        user_id=None,
        filename=filename,
        document_type="research_agent",
        content=text,
        embedding=embedding,
        status="ready",
    )
    register_hash(db, sha256, doc.id, filename)
    return doc.id, False
