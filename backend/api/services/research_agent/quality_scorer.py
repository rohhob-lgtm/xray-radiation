"""Deterministic 0-100 Source Quality Score.

Combines a domain-trust tier with the crawler's own technical-relevance
score (api.services.web_crawler._score_technical_relevance) rather than
inventing a third scoring function from scratch — reuses the same signal
Research Studio/Innovation Engine already rely on for reference quality.
"""
from __future__ import annotations

from urllib.parse import urlparse

from api.services.web_crawler import _score_technical_relevance
from api.services.research_agent.discovery import TRUSTED_DOMAINS, TRUSTED_DOMAIN_SUFFIXES

_QUALITY_LABELS: list[tuple[float, str]] = [
    (85.0, "authoritative"),
    (65.0, "high_quality"),
    (45.0, "useful"),
    (25.0, "low_confidence"),
    (0.0, "rejected"),
]

# Labels below this line must never be auto-merged into the shared knowledge
# base without a human reviewing them first.
REVIEW_REQUIRED_LABELS = {"low_confidence", "rejected"}


def _domain_trust_score(url: str) -> tuple[float, str]:
    host = (urlparse(url).hostname or "").lower()
    if host in TRUSTED_DOMAINS or host.endswith(TRUSTED_DOMAIN_SUFFIXES):
        return 40.0, "trusted domain (.gov/.edu/IAEA/standards/manufacturer)"
    if host:
        return 15.0, "general web domain"
    return 0.0, "no domain"


def score_source(url: str, text: str, http_status: int, blocking_mechanism: str | None) -> dict:
    """Score a fetched page 0-100 and map it to a quality label."""
    reasons: list[str] = []

    domain_score, domain_reason = _domain_trust_score(url)
    reasons.append(domain_reason)

    relevance = _score_technical_relevance(text) if text else 0.0
    relevance_score = relevance * 50.0
    reasons.append(f"technical relevance {relevance:.2f}")

    length_bonus = min(10.0, len(text or "") / 5000)
    reasons.append(f"content length bonus {length_bonus:.1f}")

    penalty = 0.0
    if http_status and http_status >= 400:
        penalty += 20.0
        reasons.append(f"HTTP {http_status}")
    if blocking_mechanism:
        penalty += 15.0
        reasons.append(f"blocking detected: {blocking_mechanism}")

    total = max(0.0, min(100.0, domain_score + relevance_score + length_bonus - penalty))
    label = next(label for threshold, label in _QUALITY_LABELS if total >= threshold)
    return {"score": round(total, 1), "label": label, "reasons": reasons}
