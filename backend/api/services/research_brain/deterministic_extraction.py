"""Deterministic (no-LLM) knowledge extraction — Phase 2B.0, layer 2 of 3.

The "always works" fallback for when Ollama isn't reachable either. Reuses
the existing zero-network keyword dictionaries and regexes from
terminology_service.py (equipment/safety/radiation/component/procedure
vocab) and technical_classifier.py's fault/error-code pattern, and adds
standards-identifier and manufacturer-name matching. Always returns a
result — this is the layer that guarantees Free Mode's knowledge graph
keeps growing even when no model, local or paid, is available.
"""
from __future__ import annotations

import re

from api.services.terminology_service import (
    _EQUIPMENT, _SAFETY, _RADIATION, _XRAY_COMPONENTS, _PROCEDURES,
)
from api.utils.technical_classifier import _PATTERN_RE
from api.services.research_brain.local_extraction import ExtractionResult

# Pattern-matching is intentionally treated as weaker evidence than either
# model-backed layer — transparently lower, fixed baseline confidence rather
# than pretending it's as reliable as local_ollama_extract or the paid path.
DETERMINISTIC_CONFIDENCE = 0.35

# Crawled web text has no markdown structure (web_crawler.py extracts plain
# text), so heading detection here is a line-shape heuristic rather than a
# reuse of references.py's markdown-heading regex: a short, period-free line
# starting with a capital letter — good enough to catch genuine section
# titles as sparse-but-real signal, at the cost of some false positives,
# which the low DETERMINISTIC_CONFIDENCE already accounts for.
_HEADING_RE = re.compile(r"^(?=.{3,80}$)([A-Z][A-Za-z0-9 /\-]{2,79})$", re.MULTILINE)

_STANDARDS_RE = re.compile(
    # Number may carry an optional single-letter series prefix (ANSI's
    # N42.35, C63.4 style) before the digits, and an optional dotted
    # sub-number (42.35) in addition to the hyphenated (-1) and dated
    # (:2015) suffixes other bodies use.
    r"\b(IEC|ISO|IAEA|ICRP|ANSI|ASTM|NCRP)\s*[-:]?\s*([A-Z]?\d{1,6}(?:\.\d+)?(?:-\d+)?(?::\d{4})?)\b",
    re.IGNORECASE,
)

# The 8 manufacturers named in the product spec, plus common aliases.
MANUFACTURER_ALIASES: dict[str, list[str]] = {
    "Rapiscan": ["rapiscan systems", "rapiscan"],
    "Smiths Detection": ["smiths detection", "smiths heimann"],
    "Nuctech": ["nuctech"],
    "Leidos": ["leidos"],
    "Astrophysics": ["astrophysics inc", "astrophysics"],
    "Gilardoni": ["gilardoni"],
    "VMI": ["vmi"],
    "CEIA": ["ceia"],
}

# Phase 2B.5 — Scientific Literature Learning: patent numbers (same pattern
# shape as innovation_external_research._PATENT_NUMBER_RE, kept local to
# avoid a cross-module dependency from research_brain on the Innovation
# Engine-scoped module) and training-program phrases.
_PATENT_RE = re.compile(r"\b(?:US|EP|WO|GB|JP|CN|KR)\s?\d{4,12}(?:[A-Z]\d?|\s?[A-Z]\d?)?\b")
_TRAINING_TERMS = [
    "operator training", "engineer training", "training manual",
    "certification course", "training program", "training course",
]


def _find_manufacturers(text_lower: str, manufacturer_hint: str | None = None) -> list[str]:
    found = [
        canonical for canonical, aliases in MANUFACTURER_ALIASES.items()
        if any(alias in text_lower for alias in aliases)
    ]
    if manufacturer_hint:
        hint_lower = manufacturer_hint.strip().lower()
        if hint_lower and hint_lower in text_lower and manufacturer_hint not in found:
            found.append(manufacturer_hint)
    return found


def _find_products(text: str, manufacturers: list[str]) -> list[dict]:
    """A manufacturer name immediately followed by a model-looking token
    (e.g. "Rapiscan 620DV", "Meridian Scan Systems X9") — sparse but real,
    same heuristic family as _find_standards()/_find_faults() below."""
    out, seen = [], set()
    for manufacturer in manufacturers:
        pattern = re.compile(re.escape(manufacturer) + r"\s+([A-Z0-9][\w\-]{1,20})")
        for m in pattern.finditer(text):
            model = m.group(1).strip()
            if model.lower() == manufacturer.lower():
                continue
            label = f"{manufacturer} {model}"
            if label in seen:
                continue
            seen.add(label)
            out.append({"label": label, "type": "Product", "description": None})
    return out[:15]


def _find_patents(text: str) -> list[dict]:
    out, seen = [], set()
    for m in _PATENT_RE.finditer(text):
        code = m.group(0).strip()
        if code in seen:
            continue
        seen.add(code)
        out.append({"label": code, "type": "Patent", "description": None})
    return out[:15]


def _find_training_mentions(text_lower: str) -> list[dict]:
    out = []
    for phrase in _TRAINING_TERMS:
        if re.search(r"\b" + re.escape(phrase) + r"\b", text_lower):
            out.append({"label": phrase.title(), "type": "Training", "description": None})
    return out


def _find_headings(text: str) -> list[str]:
    return [h.strip() for h in _HEADING_RE.findall(text)][:20]


def _find_standards(text: str) -> list[dict]:
    out, seen = [], set()
    for m in _STANDARDS_RE.finditer(text):
        label = f"{m.group(1).upper()} {m.group(2)}"
        if label in seen:
            continue
        seen.add(label)
        out.append({"label": label, "type": "Standard", "description": None})
    return out[:15]


def _find_faults(text: str) -> list[dict]:
    out, seen = [], set()
    for m in _PATTERN_RE.finditer(text):
        code = m.group(0)
        if code in seen:
            continue
        seen.add(code)
        out.append({"label": code, "type": "Fault", "description": None})
    return out[:15]


def _find_keyword_nodes(text: str) -> list[dict]:
    out = []
    for term, node_type in (
        [(t, "Equipment") for t in _EQUIPMENT]
        + [(t, "Safety") for t in _SAFETY]
        + [(t, "Specification") for t in _RADIATION]
        + [(t, "Component") for t in _XRAY_COMPONENTS]
        + [(t, "Procedure") for t in _PROCEDURES]
    ):
        # Word-boundary match, not substring — a naive `in` check on short
        # terms like "mA" or "HCV" false-positives inside ordinary words
        # ("manual", "archive"); \b keeps false positives to real whole-word
        # coincidences instead of every substring occurrence.
        if re.search(r"\b" + re.escape(term) + r"\b", text, re.IGNORECASE):
            out.append({"label": term, "type": node_type, "description": None})
    return out


def deterministic_extract(text: str, manufacturer_hint: str | None = None) -> ExtractionResult:
    """Always returns a result — possibly sparse for thin/off-topic text,
    never None. This is what keeps Free Mode's knowledge graph growing when
    neither a local nor a paid model is available.

    manufacturer_hint (Phase 2B.5): the mission's already-detected
    manufacturer name (possibly novel, not in MANUFACTURER_ALIASES) — folded
    into the same manufacturer-finder, not a replacement for it.
    """
    text = text or ""
    text_lower = text.lower()
    nodes: list[dict] = []
    seen_labels: set[tuple[str, str]] = set()

    def _add(candidates: list[dict]) -> None:
        for c in candidates:
            key = (c["label"].lower(), c["type"])
            if key in seen_labels:
                continue
            seen_labels.add(key)
            nodes.append(c)

    _add(_find_keyword_nodes(text))
    _add(_find_standards(text))
    _add(_find_faults(text))
    manufacturers = _find_manufacturers(text_lower, manufacturer_hint)
    for manufacturer in manufacturers:
        _add([{"label": manufacturer, "type": "Manufacturer", "description": None}])
    for heading in _find_headings(text):
        _add([{"label": heading, "type": "System", "description": "Document section heading"}])
    products = _find_products(text, manufacturers)
    _add(products)
    _add(_find_patents(text))
    _add(_find_training_mentions(text_lower))

    edges: list[dict] = []
    equipment_labels = [n["label"] for n in nodes if n["type"] == "Equipment"]
    for manufacturer in manufacturers:
        for equipment in equipment_labels[:5]:
            if equipment.lower() == manufacturer.lower():
                continue  # e.g. "Rapiscan" appears in both the equipment brand list and the manufacturer list
            edges.append({"from": manufacturer, "to": equipment, "relationship": "produces"})
        for product in products:
            if product["label"].lower().startswith(manufacturer.lower()):
                edges.append({"from": manufacturer, "to": product["label"], "relationship": "manufactures"})

    return ExtractionResult(
        nodes=nodes[:60], edges=edges[:30],
        provider_used="deterministic", extractor_confidence=DETERMINISTIC_CONFIDENCE,
    )
