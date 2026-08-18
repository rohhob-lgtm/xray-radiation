"""AI Research Brain — plans a mission into a ranked topic tree BEFORE any
discovery/crawl happens.

Deterministic by design (no LLM call required): a manufacturer-name match
triggers the manufacturer topic template from the product spec; otherwise a
generic X-ray-domain template is built from the platform's existing 16
standard research tracks (research_agent.query_generator.DOMAIN_SEED_QUERIES),
ranked by token overlap with the mission. This keeps the planner fully
functional even in Free Mode, where no paid LLM call is ever made — planning
should never depend on a paid API.

Workflow implemented here (the rest — Collect/Evaluate/Extract/Cross-Validate/
Update/Detect Gaps/Schedule — is Phase 1's crawler_orchestrator.py +
Sub-Phase 2A's graph_extraction.py/gap_detector.py, called per topic by
research_agent.job_runner.run_mission):

    Understand Mission -> Break into Topics -> Rank Topics
        -> Generate Plan -> Generate Questions -> Generate Search Strategy
"""
from __future__ import annotations

import re

from api.db import crud
from api.db.models import ResearchPlan
from api.services.research_pipeline import normalize_topic
from api.services.research_agent.query_generator import DOMAIN_SEED_QUERIES, generate_mission_queries
from api.services.research_brain.research_memory import (
    classify_content_category, get_or_create_topic_memory, normalize_topic_key,
)

# Manufacturer topic template — exactly the breakdown given in the product
# spec's own "Learn everything about Rapiscan X-ray systems" example.
_MANUFACTURER_TOPIC_TEMPLATE: list[str] = [
    "Company History",
    "Security Products",
    "Baggage Systems",
    "Cargo Systems",
    "Backscatter",
    "Dual Energy",
    "Generator",
    "Detector",
    "Image Processing",
    "Maintenance",
    "Calibration",
    "Operator Training",
    "Engineer Training",
    "Service Manuals",
    "Patents",
    "Research Papers",
    "Standards",
    "Troubleshooting",
    "Fault Codes",
]

# Manufacturer names the planner recognizes — broader than
# research_agent.discovery.TRUSTED_DOMAINS (which only lists domains it has
# a *crawl* allowlist entry for) since a mission can name a manufacturer the
# platform doesn't yet have a curated domain for.
KNOWN_MANUFACTURERS: list[str] = [
    "Rapiscan", "Smiths Detection", "Astrophysics", "Nuctech",
    "Leidos", "Gilardoni", "VMI", "CEIA",
]

_QUESTION_TEMPLATES = [
    "What is the current state of {topic}?",
    "What are the key technical parameters of {topic}?",
    "What standards or regulations govern {topic}?",
]

_TOPICS_BY_MODE = {"quick_scan": 6, "deep_research": 12, "continuous_learning": len(DOMAIN_SEED_QUERIES)}

# Phase 2B.5 — generalized manufacturer detection. KNOWN_MANUFACTURERS above
# stays the fast path (existing behavior/tests unchanged); these deterministic
# (no-LLM) fallbacks recognize a manufacturer name NOT already on that list,
# so "Manufacturer Intelligence" isn't limited to 8 pre-known companies.
_MANUFACTURER_TRIGGER_RE = re.compile(
    r"(?:manufacturer|company|maker|vendor)\s+(?:called\s+|named\s+)?"
    r"([A-Z][\w&.\-]{1,40}(?:\s+[A-Z][\w&.\-]{1,40}){0,2})"
)
_MANUFACTURER_TRIGGER_AR_RE = re.compile(r"شركة\s+([؀-ۿ]+(?:\s+[؀-ۿ]+){0,3})")
_MANUFACTURER_CONTEXT_RE = re.compile(
    # NOTE: no re.IGNORECASE on this pattern as a whole — [A-Z] below must
    # stay genuinely case-sensitive (it's the "looks like a proper noun"
    # signal); only the trailing technical-keyword alternation is
    # case-insensitive, via the scoped (?i:...) group.
    r"\babout\s+([A-Z][\w&.\-]*(?:\s+[A-Z][\w&.\-]*){0,2})\b"
    r"(?:'s)?.{0,40}\b(?i:x-?rays?|scanners?|securitys?|detections?|inspections?|screenings?|systems?|equipments?|products?)\b"
)


def _detect_manufacturer(mission_text: str) -> str | None:
    lowered = mission_text.lower()
    for name in KNOWN_MANUFACTURERS:
        if name.lower() in lowered:
            return name
    for pattern in (_MANUFACTURER_TRIGGER_RE, _MANUFACTURER_TRIGGER_AR_RE, _MANUFACTURER_CONTEXT_RE):
        m = pattern.search(mission_text)
        if m:
            candidate = m.group(1).strip()
            # str.rstrip("'s") would strip trailing 's'/'\'' characters one at
            # a time as a SET, corrupting any name that legitimately ends in
            # "s" (e.g. "Systems" -> "System") — only strip a literal
            # trailing possessive "'s" suffix.
            if candidate.endswith("'s"):
                candidate = candidate[:-2]
            candidate = candidate.strip()
            if 2 <= len(candidate) <= 60:
                return candidate
    return None


def _estimate_for_topic(rank: float) -> dict:
    """A higher-ranked (more mission-relevant) topic gets a larger research budget."""
    base = 5 + round(rank * 3)
    return {
        "expected_sources": base,
        "expected_pdfs": max(1, base // 3),
        "expected_manuals": max(0, base // 5),
        "expected_standards": max(0, base // 5),
        "expected_papers": max(1, base // 3),
        "expected_duration_minutes": 5 + base * 2,
        "expected_knowledge_gain": "high" if rank >= 0.6 else "medium" if rank >= 0.3 else "low",
    }


def build_research_plan(db, mission_id: str, mission_text: str, mode: str = "quick_scan") -> ResearchPlan:
    """Understand the mission, break it into a ranked topic tree, and persist
    a ResearchPlan + ResearchTopic rows. Returns the created ResearchPlan."""
    normalized = normalize_topic(mission_text)
    normalized_topic = normalized["normalized_topic"] or mission_text.strip()[:200]
    manufacturer = _detect_manufacturer(mission_text)

    if manufacturer:
        raw_topics = list(_MANUFACTURER_TOPIC_TEMPLATE)
        template = "manufacturer"
    else:
        raw_topics = list(DOMAIN_SEED_QUERIES)
        template = "generic"

    topic_tokens = set(normalized["focus_terms"])
    scored: list[tuple[str, float]] = []
    for label in raw_topics:
        label_tokens = {t.lower() for t in label.replace("-", " ").split()}
        overlap = len(topic_tokens & label_tokens)
        # Manufacturer-template topics are always relevant to the mission by
        # construction (the mission named that manufacturer), so they get a
        # rank floor rather than depending on literal token overlap with
        # words like "Dual Energy" that a mission may never spell out.
        rank = (overlap / max(1, len(label_tokens))) if template == "generic" else max(0.4, overlap / max(1, len(label_tokens)))
        scored.append((label, round(rank, 3)))

    scored.sort(key=lambda pair: pair[1], reverse=True)
    limit = _TOPICS_BY_MODE.get(mode, 6)
    top_topics = scored[:limit] or scored[:1]

    plan = crud.create_research_plan(
        db,
        mission_id=mission_id,
        normalized_understanding={
            "normalized_topic": normalized_topic,
            "template": template,
            "matched_manufacturer": manufacturer,
        },
    )

    for label, rank in top_topics:
        _, topic_queries = generate_mission_queries(f"{normalized_topic} {label}", mode)
        # Phase 2B.4 — link this mission-scoped topic to its cross-mission
        # TopicResearchMemory row (matched/created by normalized topic_key),
        # so a later mission researching "the same" topic accumulates into
        # the same memory instead of starting from scratch.
        topic_key = normalize_topic_key(f"{normalized_topic}::{label}")
        content_category = classify_content_category(label, template)
        topic_memory = get_or_create_topic_memory(db, topic_key=topic_key, content_category=content_category)
        crud.create_research_topic(
            db,
            plan_id=plan.id,
            mission_id=mission_id,
            label=label,
            rank=rank,
            dependencies=[],
            status="pending",
            estimates=_estimate_for_topic(rank),
            research_questions=[q.format(topic=label) for q in _QUESTION_TEMPLATES],
            search_strategy={"queries": topic_queries, "source_type_priority": ["standard", "academic", "manufacturer", "web"]},
            topic_memory_id=topic_memory.id,
        )

    return plan
