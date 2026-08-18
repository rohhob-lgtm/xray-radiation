"""Unified Brain read side — versioned graph facts relevant to a query.

Used by api.services.rag_service.build_qa_system_prompt() (additive
parameter) so chat — and every future section that shares the same
retrieve_chunks()/build_qa_system_prompt() choke point — can cite
confidence-scored facts alongside raw RAG chunks, without duplicating data
or introducing a second retrieval pipeline.

Reuses the same tokenize()/keyword_score() helpers rag_service.py already
uses for RAG chunks, so graph facts are ranked on a comparable basis.
"""
from __future__ import annotations

from api.db.models import KnowledgeNode
from api.services.retrieval_utils import tokenize, keyword_score


def get_relevant_facts(db, query: str, top_k: int = 5) -> list[dict]:
    """Keyword-overlap match against current (non-deprecated) KnowledgeNode facts."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return []

    nodes = db.query(KnowledgeNode).filter(KnowledgeNode.status == "current").all()
    scored: list[tuple[float, KnowledgeNode]] = []
    for node in nodes:
        text = f"{node.label} {node.description or ''}"
        score = keyword_score(query_tokens, text)
        if score > 0:
            scored.append((score, node))

    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [
        {
            "label": node.label,
            "description": node.description,
            "node_type": node.node_type,
            "confidence": node.confidence,
            "evidence_count": node.evidence_count,
            "status": node.status,
            "version": node.version,
            # Phase 2B.6 — additive: the raw retrieval score (how well this
            # fact matches the query) and the ResearchTopic it came from, so
            # api.services.knowledge_router can assess answer confidence and
            # look up the topic's freshness without a second query pipeline.
            "match_score": score,
            "research_topic_id": node.research_topic_id,
        }
        for score, node in scored[:top_k]
    ]
