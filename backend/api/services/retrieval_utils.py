"""
Shared pure-function scoring helpers for hybrid keyword+embedding search.

Used identically by rag_service (document chunks), memory_service (memory
items, conversation summaries), and workspace_index (workspace files) so all
retrieval paths rank results the same way instead of each re-implementing
the same math.
"""
from __future__ import annotations
import math
import re
from dataclasses import dataclass, field
from typing import List


@dataclass
class MemoryResult:
    """A single Global-AI-Brain search hit, tagged by originating source."""
    source_kind: str  # doc | memory | summary | workspace
    title: str
    content: str
    score: float
    meta: dict = field(default_factory=dict)


_STOP_WORDS = {
    "the", "and", "for", "are", "but", "not", "you", "all", "can", "had",
    "was", "one", "our", "out", "day", "get", "has", "him", "his",
    "how", "its", "may", "new", "now", "old", "see", "two", "who", "did",
    "what", "with", "this", "that", "from", "they", "will", "been", "have",
    "were", "said", "each", "she", "use", "about", "into", "than",
    "then", "some", "more", "also", "like", "time", "very", "when", "much",
    "other", "which", "their", "there", "these", "those", "would", "could",
    "should", "your", "just", "over", "such", "only", "because", "document",
    "file", "text", "content", "please", "tell", "explain", "describe",
    "information", "according", "based", "related", "regarding", "show",
    "find", "give", "want", "need", "know", "does", "say", "ask", "get",
    "photo", "image", "picture", "diagram", "figure", "visual",
}


def tokenize(text: str) -> List[str]:
    tokens = re.findall(r"\b[a-z][a-z0-9]{2,}\b", text.lower())
    return [t for t in tokens if t not in _STOP_WORDS]


def keyword_score(query_tokens: List[str], text: str) -> float:
    if not query_tokens:
        return 0.0
    lower = text.lower()
    hits = sum(1 for t in query_tokens if t in lower)
    return hits / len(query_tokens)


def cosine_similarity(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    return dot / (norm_a * norm_b) if norm_a and norm_b else 0.0
