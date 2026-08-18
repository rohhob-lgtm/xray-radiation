"""
In-memory TTL cache for hot RAG queries and research metadata.
Thread-safe for asyncio (single-threaded event loop); uses monotonic clock.
"""
from __future__ import annotations
import time
from typing import Any, Optional


class TTLCache:
    """
    Lightweight dict-backed cache with TTL eviction.
    On overflow, evicts the oldest 25% of entries.
    """

    def __init__(self, ttl: int = 300, max_size: int = 500):
        self._store: dict[str, tuple[Any, float]] = {}
        self.ttl = ttl
        self.max_size = max_size
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    # ── public API ──────────────────────────────────────────────────────────

    def get(self, key: str) -> Optional[Any]:
        entry = self._store.get(key)
        if entry is None:
            self.misses += 1
            return None
        value, ts = entry
        if time.monotonic() - ts > self.ttl:
            del self._store[key]
            self.misses += 1
            return None
        self.hits += 1
        return value

    def set(self, key: str, value: Any) -> None:
        if len(self._store) >= self.max_size:
            self._evict()
        self._store[key] = (value, time.monotonic())

    def invalidate(self, prefix: str = "") -> int:
        """Remove all entries whose keys start with *prefix* (or all if empty)."""
        if not prefix:
            n = len(self._store)
            self._store.clear()
            self.evictions += n
            return n
        keys = [k for k in list(self._store) if k.startswith(prefix)]
        for k in keys:
            del self._store[k]
        self.evictions += len(keys)
        return len(keys)

    def stats(self) -> dict:
        now = time.monotonic()
        valid = sum(1 for _, ts in self._store.values() if now - ts <= self.ttl)
        total_calls = self.hits + self.misses
        return {
            "entries_total": len(self._store),
            "entries_valid": valid,
            "entries_expired": len(self._store) - valid,
            "ttl_seconds": self.ttl,
            "max_size": self.max_size,
            "hits": self.hits,
            "misses": self.misses,
            "evictions": self.evictions,
            "hit_rate_pct": round(self.hits / total_calls * 100, 1) if total_calls else 0.0,
        }

    # ── private ─────────────────────────────────────────────────────────────

    def _evict(self) -> None:
        """Remove oldest 25% of entries to make room."""
        n = max(1, self.max_size // 4)
        oldest = sorted(self._store.items(), key=lambda kv: kv[1][1])[:n]
        for k, _ in oldest:
            del self._store[k]
        self.evictions += n


# ── Global singletons ────────────────────────────────────────────────────────

# RAG chunk retrieval — 5 min TTL, large pool (expensive DB scan)
rag_cache = TTLCache(ttl=300, max_size=500)

# Research metadata (modes list, etc.) — 2 min TTL
research_meta_cache = TTLCache(ttl=120, max_size=50)

# Gallery search results — 5 min TTL
# Key: "gallery:{normalized_query}:{top_k}"
# Avoids repeated DB scans + OpenAI embedding calls for the same query.
gallery_cache = TTLCache(ttl=300, max_size=200)

# Query embedding cache — 10 min TTL
# Key: "embed:{text[:200]}"
# Deduplicates OpenAI embedding calls across gallery search, RAG, and similarity.
embed_cache = TTLCache(ttl=600, max_size=1000)
