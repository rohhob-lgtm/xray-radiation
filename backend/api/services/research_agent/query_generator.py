"""Mission statement -> normalized topic + ranked search-query list.

Reuses Research Studio's topic normalization / keyword-expansion
(api.services.research_pipeline) rather than re-deriving query-generation
logic, then layers in the platform's fixed domain-seed queries so a mission
also pulls in the standard research tracks called out in the product spec,
even when the user's own wording doesn't mention them explicitly.
"""
from __future__ import annotations

from api.services.research_pipeline import normalize_topic, generate_search_keywords

# Fixed domain-seed queries — the platform's standard research tracks.
DOMAIN_SEED_QUERIES: list[str] = [
    "X-ray source engineering",
    "radiation detection systems",
    "cargo and baggage X-ray inspection",
    "linear accelerator X-ray systems",
    "radiation safety manuals",
    "radiation measurement standards",
    "X-ray tube technical manuals",
    "high-voltage X-ray generators",
    "dual-energy X-ray imaging",
    "computed tomography security screening",
    "backscatter X-ray systems",
    "gamma and neutron detection",
    "radiation portal monitors",
    "medical and industrial X-ray systems",
    "preventive maintenance and troubleshooting X-ray systems",
    "AI applications in X-ray systems",
]

_QUERIES_BY_MODE = {"quick_scan": 6, "deep_research": 12, "continuous_learning": 16}


def generate_mission_queries(mission_text: str, mode: str = "quick_scan") -> tuple[str, list[str]]:
    """Mission statement -> (normalized_topic, ranked query list).

    Mission-derived queries come first (most specific to what the user
    actually asked); domain-seed tracks fill the remaining budget, ranked by
    token overlap with the mission so the most relevant seed tracks are
    included first. If nothing overlaps at all (a mission unrelated to any
    seed track), the top few seeds are still included so a short/generic
    mission still yields a usable query set.
    """
    normalized = normalize_topic(mission_text)
    normalized_topic = normalized["normalized_topic"] or mission_text.strip()[:200]

    keyword_stage = generate_search_keywords(normalized_topic, mode="technical_report", context=None)
    mission_queries = keyword_stage["search_queries"]

    topic_tokens = set(normalized["focus_terms"])
    scored_seeds = sorted(
        DOMAIN_SEED_QUERIES,
        key=lambda seed: len(topic_tokens & {t.lower() for t in seed.split()}),
        reverse=True,
    )

    limit = _QUERIES_BY_MODE.get(mode, 6)
    seen: set[str] = set()
    queries: list[str] = []

    for q in mission_queries:
        key = q.strip().lower()
        if key and key not in seen:
            seen.add(key)
            queries.append(q.strip())

    for seed in scored_seeds:
        if len(queries) >= limit:
            break
        key = seed.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        queries.append(seed)

    return normalized_topic, queries[:limit]
