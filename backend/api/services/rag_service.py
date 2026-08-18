"""
RAG QA Service.

Pipeline:
  upload  → chunk + embed in background
  query   → retrieve top-k chunks → build focused QA system prompt → LLM answers concisely
  image Q → keyword-search extracted images → return image URL or "not found" message

Design rules:
  - Never dump raw document text as an answer.
  - Every answer must cite source filename and estimated page.
  - No caching: every call starts fresh from the DB.
"""
from __future__ import annotations
import asyncio
import re
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

from sqlalchemy.orm import Session

from api.services.ai_providers.registry import provider_registry
from api.services.embedding_service import get_embedding as _shared_get_embedding
from api.services.retrieval_utils import tokenize, keyword_score, cosine_similarity

if TYPE_CHECKING:
    from api.db.models import RagDocument, RagImage
    from api.services.retrieval_utils import MemoryResult

WORDS_PER_PAGE = 400   # rough words-per-page estimate for page number calculation
CHUNK_SIZE     = 500   # words per chunk
CHUNK_OVERLAP  = 50    # word overlap between consecutive chunks

_IMAGE_RE = re.compile(
    r"\b(show|display|image|photo|photograph|picture|diagram|figure|"
    r"visual|illustration|chart|graph|screenshot|drawing|render|capture|"
    r"view|exhibit|depict|look)\b",
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────
# Data class
# ──────────────────────────────────────────────────────────

@dataclass
class RagChunk:
    doc_id: str
    filename: str
    document_type: str
    page_num: int
    chunk_index: int
    content: str
    score: float = 0.0


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def is_image_request(query: str) -> bool:
    """Return True if the query is asking for a visual / image."""
    return bool(_IMAGE_RE.search(query))


def _chunk_document(doc: "RagDocument") -> List[RagChunk]:
    """Split a document into overlapping word-window chunks."""
    words = doc.content.split()
    if not words:
        return []
    step = max(1, CHUNK_SIZE - CHUNK_OVERLAP)
    chunks: List[RagChunk] = []
    for i, start in enumerate(range(0, len(words), step)):
        window = words[start: start + CHUNK_SIZE]
        mid = start + len(window) // 2
        page_num = max(1, mid // WORDS_PER_PAGE + 1)
        chunks.append(RagChunk(
            doc_id=doc.id,
            filename=doc.filename,
            document_type=doc.document_type,
            page_num=page_num,
            chunk_index=i,
            content=" ".join(window),
        ))
    return chunks


# ──────────────────────────────────────────────────────────
# Embedding
# ──────────────────────────────────────────────────────────

_get_embedding = _shared_get_embedding  # backward-compatible alias


# ──────────────────────────────────────────────────────────
# Retrieval
# ──────────────────────────────────────────────────────────

def _sync_score_chunks(
    docs: list,
    query_tokens: List[str],
    query_embedding: Optional[List[float]],
    top_k: int,
) -> List[RagChunk]:
    """
    CPU-intensive scoring: chunk every document and rank by keyword + semantic score.

    This is a pure sync function — call it via run_in_executor so it runs in a
    thread-pool worker and never blocks the asyncio event loop.
    """
    scored: List[RagChunk] = []

    for doc in docs:
        # Semantic boost: cosine similarity between query embedding and doc embedding
        boost = 0.0
        if query_embedding and doc.embedding:
            boost = max(0.0, cosine_similarity(query_embedding, doc.embedding))

        for chunk in _chunk_document(doc):
            kw = keyword_score(query_tokens, chunk.content)
            # Combined score: keyword is primary, semantic boost is secondary
            combined = kw + boost * 0.2
            # Minimum threshold: at least 10% keyword overlap OR strong semantic match
            if kw >= 0.10 or (boost >= 0.70 and combined > 0.05):
                chunk.score = combined
                scored.append(chunk)

    scored.sort(key=lambda c: c.score, reverse=True)
    return scored[:top_k]


async def retrieve_chunks(query: str, db: Session, top_k: int = 5) -> List[RagChunk]:
    """
    Return the top_k most relevant chunks for the query.

    Strategy — keyword-first, embedding-boosted:
      • Every chunk in every document is scored by keyword overlap with the query.
      • If embeddings are available, add a cosine similarity boost for semantic ranking.
      • Chunks must exceed a meaningful relevance threshold to be included —
        low-score junk is excluded so the LLM doesn't produce false "no info" replies.
      • Results are cached (TTL=5 min) to avoid repeated full-corpus scans.

    The CPU-intensive scoring step runs in a thread-pool executor so it never
    blocks the asyncio event loop (49+ large documents would cause a 2-minute
    hang and 502 Bad Gateway without this).
    """
    from api.services.cache_service import rag_cache

    cache_key = f"chunks:{query.lower().strip()}:{top_k}"
    cached = rag_cache.get(cache_key)
    if cached is not None:
        return cached

    from api.db.crud import get_all_rag_documents
    docs = get_all_rag_documents(db)
    if not docs:
        return []

    query_tokens = tokenize(query)
    if not query_tokens:
        # No meaningful tokens — return nothing so general knowledge is used
        rag_cache.set(cache_key, [])
        return []

    # Async: get query embedding (network call, non-blocking)
    query_embedding = await _get_embedding(query)

    # CPU-bound: run chunk scoring in thread pool so the event loop stays free.
    # With 49 docs and the largest at 829 KB (~138K words → ~307 chunks per doc),
    # running this synchronously in an async handler blocked uvicorn completely.
    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(
        None, _sync_score_chunks, docs, query_tokens, query_embedding, top_k
    )

    rag_cache.set(cache_key, result)
    return result


# ──────────────────────────────────────────────────────────
# QA prompt builder
# ──────────────────────────────────────────────────────────

def build_qa_system_prompt(chunks: List[RagChunk], graph_facts: Optional[List[dict]] = None) -> str:
    """
    Build a citation-aware QA system prompt.

    The model is an X-ray expert FIRST — it should always provide a helpful answer.
    Document context supplements its expertise; it never blocks a response.

    `graph_facts` (Knowledge Evolution Engine, Sub-Phase 2A — optional,
    additive) are versioned facts from api.services.research_brain.graph_query,
    each carrying a confidence score and status (current/deprecated/
    experimental/historical). Omitting it (the default) reproduces the exact
    prompt this function has always built.
    """
    ctx_parts: List[str] = []
    for chunk in chunks:
        ctx_parts.append(
            "[Source: " + chunk.filename
            + " | Page ~" + str(chunk.page_num) + "]\n"
            + chunk.content
        )
    context = "\n\n---\n\n".join(ctx_parts)

    graph_section = ""
    graph_rule = ""
    if graph_facts:
        fact_lines = []
        for fact in graph_facts:
            confidence_pct = round(float(fact.get("confidence", 0.5)) * 100)
            fact_lines.append(
                f"- [{fact.get('node_type', 'Fact')}] {fact.get('label', '')}"
                + (f": {fact['description']}" if fact.get("description") else "")
                + f" (confidence {confidence_pct}%, {fact.get('evidence_count', 0)} evidence source(s), status: {fact.get('status', 'current')})"
            )
        graph_section = "\n\nVERSIONED KNOWLEDGE GRAPH FACTS:\n" + "\n".join(fact_lines)
        graph_rule = (
            "7. **Versioned graph facts** — facts listed under VERSIONED KNOWLEDGE GRAPH FACTS carry "
            "a confidence score and status from the platform's Knowledge Evolution Engine. Cite their "
            "confidence when relevant (e.g. \"established, 85% confidence, 4 sources\"), and never "
            "present an \"experimental\" or \"deprecated\" fact as settled without saying so.\n\n"
        )

    return (
        "You are an advanced AI platform specialized in X-ray technology, security screening, "
        "radiation science, engineering, research, training, and technical innovation — operating "
        "at the level of a senior international X-ray expert with decades of field, engineering, "
        "and research experience.\n\n"
        "The user has uploaded technical documents to the knowledge base. Relevant passages are "
        "provided below as CONTEXT. Apply these rules:\n\n"
        "1. **Uploaded documents are primary project knowledge** — when the documents address "
        "the question, cite them inline: (Source: <filename>, p. ~<N>). Treat them as the "
        "authoritative reference for this project.\n"
        "2. **Supplement with expert knowledge** — if the documents do not fully cover the topic, "
        "draw on your comprehensive X-ray, physics, and engineering expertise to give a complete "
        "answer. You are never restricted to the context alone.\n"
        "3. **Source transparency** — distinguish clearly between: established scientific facts "
        "(cite standard/publication), manufacturer-specific information (note the source), "
        "expert professional recommendation (frame as such), and information from the uploaded "
        "documents (cite by filename and page).\n"
        "4. **Proactive guidance** — go beyond the literal question where it adds genuine value: "
        "relevant best practices, applicable standards (IAEA, IEC, ISO, ANSI, NCRP, ICRP), "
        "safety considerations, and common pitfalls.\n"
        "5. **Structured, professional output** — use headings, bullets, or numbered steps where "
        "helpful. Match the depth to the question: concise for simple queries, detailed for "
        "engineering or diagnostic questions.\n"
        "6. **Never refuse** — always provide a complete, actionable answer. Only decline if the "
        "question is entirely outside X-ray, radiation, or security-screening technology.\n\n"
        + graph_rule
        + "CONTEXT FROM UPLOADED DOCUMENTS:\n" + context
        + graph_section
    )


_SECTION_LABELS = {
    "doc": "CONTEXT FROM UPLOADED DOCUMENTS",
    "memory": "YOUR PAST DECISIONS, PREFERENCES, AND PINNED NOTES WITH THIS USER",
    "summary": "SUMMARY OF EARLIER CONVERSATIONS WITH THIS USER",
    "workspace": "CONTEXT FROM THE ACTIVE WORKSPACE'S FILES",
    "solution": "PROVEN SOLUTIONS FROM PAST PROBLEMS — REUSE THESE BEFORE INVENTING A NEW APPROACH",
    "graph": "RELATED ENTITIES FROM THE KNOWLEDGE GRAPH (projects, files, tasks, decisions)",
    "timeline": "RECENT PROJECT TIMELINE EVENTS",
}


def build_qa_system_prompt_from_results(results: List["MemoryResult"]) -> str:
    """
    Global-AI-Brain variant of build_qa_system_prompt() — same expert
    persona and citation rules, but the context section is built from a
    merged, source_kind-tagged result list (documents + durable memory +
    conversation summaries + workspace files) instead of RAG chunks alone.
    """
    if not results:
        return build_qa_system_prompt([])

    sections: dict[str, list[str]] = {}
    for r in results:
        sections.setdefault(r.source_kind, []).append(f"[{r.title}]\n{r.content}")

    context_blocks = []
    for kind, label in _SECTION_LABELS.items():
        if kind in sections:
            context_blocks.append(f"{label}:\n" + "\n\n---\n\n".join(sections[kind]))
    context = "\n\n===\n\n".join(context_blocks)

    return (
        "You are an advanced AI platform specialized in X-ray technology, security screening, "
        "radiation science, engineering, research, training, and technical innovation — operating "
        "at the level of a senior international X-ray expert with decades of field, engineering, "
        "and research experience. You are a persistent member of this project's team: you "
        "remember prior decisions, preferences, and conversations with this user, and the active "
        "workspace's files, as shown below. Apply these rules:\n\n"
        "1. **Continue prior work — never start from zero.** If past decisions, preferences, or "
        "conversation summaries below are relevant, use them and reference them naturally rather "
        "than asking the user to repeat themselves.\n"
        "2. **Uploaded documents and workspace files are primary project knowledge** — when they "
        "address the question, cite them inline (Source: <filename>, p. ~<N> for documents; "
        "<filename> for workspace files). Treat them as the authoritative reference for this "
        "project.\n"
        "3. **Supplement with expert knowledge** — if the context does not fully cover the topic, "
        "draw on your comprehensive X-ray, physics, and engineering expertise. You are never "
        "restricted to the context alone.\n"
        "4. **Source transparency** — distinguish established scientific facts, manufacturer-"
        "specific information, expert recommendation, and information drawn from the context "
        "below.\n"
        "5. **Structured, professional output** — use headings, bullets, or numbered steps where "
        "helpful. Match depth to the question.\n"
        "6. **Never refuse** — always provide a complete, actionable answer. Only decline if the "
        "question is entirely outside X-ray, radiation, or security-screening technology.\n\n"
        + context
    )


# ──────────────────────────────────────────────────────────
# Image search
# ──────────────────────────────────────────────────────────

async def search_rag_images(query: str, db: Session) -> List["RagImage"]:
    """
    Semantic + keyword image search.
    Delegates to image_service.search_images_semantic which:
      1. Uses cosine similarity over GPT-vision-generated caption embeddings when available.
      2. Falls back to keyword search over captions + filenames.
    """
    from api.services.image_service import search_images_semantic
    return await search_images_semantic(query, db, top_k=5)


# ──────────────────────────────────────────────────────────
# Embed and store (background, called after upload)
# ──────────────────────────────────────────────────────────

async def embed_and_store(db: Session, doc: "RagDocument") -> None:
    """Generate and persist an embedding for a document (fire-and-forget)."""
    embedding = await _get_embedding(doc.content)
    if embedding:
        doc.embedding = embedding
        db.commit()
