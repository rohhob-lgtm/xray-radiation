"""Local Ollama structured knowledge extraction — Phase 2B.0, layer 1 of 3.

Asks a locally-running Ollama model to extract entities/relationships from
crawled text as JSON. Mirrors research_agent.ingestion._local_ollama_embedding's
graceful-degrade contract exactly: any failure (Ollama not running, model not
pulled, timeout, malformed JSON) returns None rather than raising, so the
caller (graph_extraction.py) falls through to deterministic_extraction.py —
the knowledge graph must keep growing in Free Mode even when Ollama isn't
available.
"""
from __future__ import annotations

import json
import logging
import os
import re

import httpx

log = logging.getLogger(__name__)

# Local models are a weaker evidence source than a hosted GPT-class model,
# but a stronger one than pure pattern-matching — reflected transparently via
# KnowledgeNode.confidence rather than pretending it's as reliable as either
# neighbor.
LOCAL_OLLAMA_CONFIDENCE = 0.65

_VALID_NODE_TYPES = {
    "Equipment", "Manufacturer", "Standard", "Procedure", "Fault", "Solution",
    "Warning", "Specification", "System", "Subsystem", "Component", "Function",
    "Safety", "Failure", "Cause", "Repair",
    # Phase 2B.5 — Manufacturer Intelligence + Scientific Literature Learning.
    "Product", "Patent", "Training", "Paper", "Author", "Institution",
    # Multimodal Internet Image Retrieval — a discovered reference image
    # (photo/diagram/schematic), never LLM-extracted text; written directly
    # by api.services.research_agent.image_discovery, not this module's own
    # extraction prompt below.
    "Image",
}
_VALID_RELATIONSHIPS = {
    "uses", "connected_to", "produces", "requires", "references", "contains",
    "causes", "repairs", "triggers", "prevents",
    # Phase 2B.5
    "manufactures", "authored_by", "affiliated_with", "cites",
}

_EXTRACTION_PROMPT = """Extract structured technical knowledge from the X-ray/radiation/security-screening text below. Return ONLY valid JSON — no markdown, no explanation, no code fences — matching exactly this schema:

{{
  "nodes": [
    {{"label": "short entity name", "type": "Equipment|Manufacturer|Standard|Procedure|Fault|Solution|Warning|Specification|System|Component|Safety|Product|Patent|Training|Paper|Author|Institution", "description": "one factual sentence"}}
  ],
  "edges": [
    {{"from": "node label", "to": "node label", "relationship": "uses|connected_to|produces|requires|references|contains|causes|repairs|triggers|prevents|manufactures|authored_by|affiliated_with|cites"}}
  ]
}}

Cover entities, facts, relationships, equipment, manufacturers, standards, procedures, faults, solutions, warnings, specifications, products, patents, training programs, papers/theses, authors, and institutions wherever the text actually supports them. Do not invent information not present in the text.
{manufacturer_hint_block}
TEXT:
{text}
"""

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.MULTILINE)


class ExtractionResult:
    """Shared result shape for all three extraction layers (local_ollama,
    deterministic, paid_provider) — graph_extraction.py's versioning loop is
    identical regardless of which layer produced it."""

    __slots__ = ("nodes", "edges", "provider_used", "extractor_confidence")

    def __init__(self, nodes: list[dict], edges: list[dict], provider_used: str, extractor_confidence: float):
        self.nodes = nodes
        self.edges = edges
        self.provider_used = provider_used
        self.extractor_confidence = extractor_confidence


def _parse_json_response(raw: str) -> dict | None:
    cleaned = _FENCE_RE.sub("", raw.strip()).strip()
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict) or "nodes" not in data or not isinstance(data["nodes"], list):
        return None
    return data


def _sanitize_nodes(raw_nodes: list) -> list[dict]:
    out = []
    for raw in raw_nodes:
        if not isinstance(raw, dict):
            continue
        label = str(raw.get("label", "")).strip()[:500]
        if not label:
            continue
        node_type = str(raw.get("type", "Component")).strip()
        if node_type not in _VALID_NODE_TYPES:
            node_type = "Component"
        out.append({
            "label": label,
            "type": node_type,
            "description": str(raw.get("description", "")).strip()[:2000] or None,
        })
    return out


def _sanitize_edges(raw_edges: list) -> list[dict]:
    out = []
    for raw in raw_edges:
        if not isinstance(raw, dict):
            continue
        from_label = str(raw.get("from", "")).strip()[:500]
        to_label = str(raw.get("to", "")).strip()[:500]
        if not from_label or not to_label or from_label == to_label:
            continue
        relationship = str(raw.get("relationship", "contains")).strip()
        if relationship not in _VALID_RELATIONSHIPS:
            relationship = "contains"
        out.append({"from": from_label, "to": to_label, "relationship": relationship})
    return out


async def local_ollama_extract(text: str, manufacturer_hint: str | None = None) -> ExtractionResult | None:
    """Best-effort structured extraction via a local Ollama model.

    Returns None (never raises) on any failure — no Ollama running, wrong
    model, timeout, or a response that isn't valid JSON matching the schema.

    manufacturer_hint (Phase 2B.5): the mission's already-detected
    manufacturer name (possibly novel, not on any hardcoded list) — folded
    into the prompt as extra context, not a replacement for what the model
    finds on its own.
    """
    if not text or len(text.strip()) < 50:
        return None

    base_url = os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.environ.get("OLLAMA_EXTRACTION_MODEL", os.environ.get("OLLAMA_MODEL", "qwen2.5-7b-fast6:latest"))
    hint_block = f"\nKnown manufacturer context for this mission: {manufacturer_hint}\n" if manufacturer_hint else ""
    prompt = _EXTRACTION_PROMPT.format(text=text[:6000], manufacturer_hint_block=hint_block)

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{base_url}/api/generate",
                json={"model": model, "prompt": prompt, "stream": False, "format": "json"},
            )
            resp.raise_for_status()
            raw_response = resp.json().get("response", "")
    except Exception as exc:
        log.info("Local Ollama extraction unavailable (%s) — falling back to deterministic extraction", exc)
        return None

    data = _parse_json_response(raw_response)
    if data is None:
        log.info("Local Ollama extraction returned unparseable JSON — falling back to deterministic extraction")
        return None

    nodes = _sanitize_nodes(data.get("nodes", []))
    if not nodes:
        return None
    edges = _sanitize_edges(data.get("edges", []))

    return ExtractionResult(nodes=nodes, edges=edges, provider_used="local_ollama", extractor_confidence=LOCAL_OLLAMA_CONFIDENCE)
