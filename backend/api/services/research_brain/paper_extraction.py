"""Structured academic-paper/thesis section extraction — Phase 2B.5.

Deterministic (no LLM), heading-based: given the full text of an
open-access paper/thesis (plus its already-known ExternalSource metadata —
title/authors/abstract/etc., see discovery._external_source_to_metadata),
regex-scans for standard section headers and slices the text between
consecutive recognized headers into research_problem/methodology/
equipment_components/results/limitations/future_work/citations.

Degrades gracefully: if zero recognizable section headers are found (a
common case — not every crawled document is a clean academic PDF-to-text
extraction), returns an abstract-only record rather than failing. Never
raises — same "best-effort, caller wraps in try/except" convention as
graph_extraction.extract_and_version().
"""
from __future__ import annotations

import re

# (canonical output field, header-text pattern) — checked in this order only
# for readability; actual section boundaries are determined by sorting ALL
# matches by position in the text, not by this list's order.
_SECTION_PATTERNS: list[tuple[str, str]] = [
    ("abstract", r"abstract"),
    ("research_problem", r"introduction|problem\s+statement|research\s+problem"),
    ("methodology", r"methodology|methods|materials\s+and\s+methods"),
    ("equipment_components", r"experimental\s+setup|system\s+description|apparatus|instrumentation"),
    ("results", r"results|findings"),
    ("conclusion", r"conclusion"),
    ("limitations", r"limitations"),
    ("future_work", r"future\s+work|future\s+research|recommendations"),
    ("citations", r"references|bibliography"),
]

# Line-start-anchored, optional leading number ("1.", "II)"), optional
# trailing colon — a common heading shape in both PDF-extracted text and
# ordinary HTML article bodies.
_HEADER_RES = [
    (field, re.compile(rf"^\s*(?:[\dIVXLCivxlc]+[.\)]\s*)?(?:{pattern})\s*:?\s*$", re.IGNORECASE | re.MULTILINE))
    for field, pattern in _SECTION_PATTERNS
]

_CITATION_RE = re.compile(r"\b(?:10\.\d{4,9}/[^\s,;\]]+|arXiv:\d{4}\.\d{4,5})\b", re.IGNORECASE)

_MAX_SECTION_CHARS = 3000
_MAX_CITATIONS = 30


def extract_paper_sections(text: str, metadata: dict | None = None) -> dict:
    """Returns a dict with keys: abstract, research_problem, methodology,
    equipment_components, results, limitations, future_work, citations
    (list of DOI/arXiv-ID strings). Never raises."""
    metadata = metadata or {}
    text = text or ""
    result = {
        "abstract": (metadata.get("abstract") or "").strip(),
        "research_problem": "", "methodology": "", "equipment_components": "",
        "results": "", "limitations": "", "future_work": "", "citations": [],
    }

    matches: list[tuple[int, int, str]] = []
    for field, regex in _HEADER_RES:
        for m in regex.finditer(text):
            matches.append((m.start(), m.end(), field))
    matches.sort(key=lambda t: t[0])

    if not matches:
        # Graceful degradation — no recognizable structure in this
        # particular document; the metadata's own abstract is still real,
        # useful, structured knowledge, just not a full breakdown.
        return result

    for i, (_start, end, field) in enumerate(matches):
        section_end = matches[i + 1][0] if i + 1 < len(matches) else len(text)
        section_text = text[end:section_end].strip()[:_MAX_SECTION_CHARS]
        if not section_text:
            continue
        if field == "citations":
            result["citations"] = _CITATION_RE.findall(section_text)[:_MAX_CITATIONS]
        elif field == "abstract":
            result["abstract"] = result["abstract"] or section_text
        elif field == "conclusion":
            # Not one of the caller's requested fields — folds into
            # "results" only when results wasn't already found from its own
            # section, so an explicit "Results" section always wins.
            if not result["results"]:
                result["results"] = section_text
        elif field in result:
            result[field] = section_text

    return result
