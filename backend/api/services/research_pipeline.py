"""Phase 1 research pipeline for Research Studio.

This module builds structured artifacts only. It stops before writing any
paper sections so the user can inspect the search, verification, evidence,
matrix, gap, and outline artifacts first.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from api.db.crud import create_research_pipeline_run, update_research_pipeline_run
from api.services.cache_service import research_meta_cache
from api.services.innovation_external_research import perform_hybrid_external_research
from api.services.rag_service import retrieve_chunks
from api.services.research_service import RESEARCH_MODE_LABELS

log = logging.getLogger(__name__)


_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "using", "used", "use",
    "study", "analysis", "based", "method", "methods", "approach", "system", "systems", "model",
    "models", "data", "results", "research", "paper", "review", "toward", "through", "across",
    "between", "within", "their", "than", "have", "has", "had", "were", "was", "are", "is",
    "its", "his", "her", "our", "your", "them", "they", "these", "those", "about", "impact",
    "effect", "effects", "role", "roles",
    # NOTE: "x", "ray", "xray", "security", "screening", "inspection" used to be
    # listed here as stopwords. They are this platform's core domain vocabulary —
    # stripping them before computing topic-overlap silently deflated the
    # relevance score of every genuinely on-topic X-ray/security source and
    # contributed to retrieval starving down to near-zero references.
}

_MODE_OUTLINE_SECTIONS: dict[str, list[tuple[str, list[str]]]] = {
    "paper_ieee": [
        ("Abstract", ["Problem, aim, method, core findings, and contribution summary."]),
        ("Introduction", ["Problem framing", "Gap statement", "Motivation", "Paper organization"]),
        ("Literature Review", ["Thematic synthesis", "What prior work solved", "What remains unresolved"]),
        ("Novel Contributions", ["Contribution #1", "Contribution #2", "Contribution #3"]),
        ("Methodology", ["System design", "Processing pipeline", "Reproducibility notes"]),
        ("Mathematical Models", ["Equations with variable definitions and assumptions"]),
        ("Experimental Setup", ["Data sources", "Acquisition geometry", "Evaluation protocol", "Metrics"]),
        ("Results", ["Comparative table", "Quantitative findings", "Uncertainty notes"]),
        ("Discussion", ["Interpretation versus state of the art", "Operational implications"]),
        ("Limitations", ["Failure modes", "Scope limits", "Validation constraints"]),
        ("Future Work", ["Next experiments", "Deployment roadmap"]),
        ("Conclusion", ["Concise technical takeaway"]),
        ("References", ["Verifiable source list only"]),
    ],
    "paper_elsevier": [
        ("Abstract", ["Structured abstract with scope, method, findings, and implications"]),
        ("Introduction", ["Background", "Gap", "Contribution overview"]),
        ("Related Work", ["Clustered synthesis of prior studies"]),
        ("Methodology", ["Experimental or algorithmic design", "Implementation details"]),
        ("Results", ["Figures/tables plan", "Performance comparison"]),
        ("Discussion", ["Interpretation and limitations"]),
        ("Conclusion", ["Key conclusions and future work"]),
        ("References", ["Verifiable source list only"]),
    ],
    "literature_review": [
        ("Scope and Questions", ["Review objective", "Research questions", "Inclusion criteria"]),
        ("Search Strategy", ["Databases", "Queries", "Filters"]),
        ("Thematic Synthesis", ["Themes", "Consensus", "Contradictions"]),
        ("Methodological Quality", ["Risk of bias", "Evidence hierarchy"]),
        ("Research Gaps", ["Missing evidence", "Open questions"]),
        ("Future Directions", ["Priority research avenues"]),
        ("References", ["Verifiable source list only"]),
    ],
    "research_gaps": [
        ("Current State", ["What is established", "What is still missing"]),
        ("Methodological Gaps", ["Experimental and dataset limitations"]),
        ("Theoretical Gaps", ["Incomplete models and assumptions"]),
        ("Operational Gaps", ["Translation to deployment"]),
        ("Priority Matrix", ["Impact", "Feasibility", "Urgency"]),
        ("Top Research Questions", ["Ranked follow-on questions"]),
    ],
    "experiment_plan": [
        ("Objectives", ["Hypotheses and success criteria"]),
        ("Background", ["Relevant equations and assumptions"]),
        ("Design", ["Factors", "Sample size", "Randomization"]),
        ("Protocol", ["Step-by-step procedure"]),
        ("Analysis", ["Statistics", "Uncertainty", "Acceptance criteria"]),
        ("Safety", ["Radiation safety and compliance"]),
    ],
    "patent_analysis": [
        ("Invention Summary", ["Technical concept and scope"]),
        ("Prior Art", ["Representative references and clusters"]),
        ("Novelty", ["Distinctive features and inventive step"]),
        ("FTO", ["Blocking risks and design-around options"]),
        ("Claim Strategy", ["Independent and dependent claim direction"]),
        ("Recommendations", ["File, refine, or abandon"]),
    ],
    "technical_report": [
        ("Executive Summary", ["Purpose", "Key findings", "Recommendations"]),
        ("Background", ["Scope and technical context"]),
        ("System Description", ["Architecture and design rationale"]),
        ("Analysis", ["Results and performance"]),
        ("Risk and Safety", ["Failure modes and mitigations"]),
        ("Conclusions", ["Actionable next steps"]),
    ],
    "security_algorithm": [
        ("Algorithm Overview", ["Targets", "Operating environment"]),
        ("Physical Principles", ["Attenuation and detection basis"]),
        ("Signal Processing Pipeline", ["Preprocess", "Detect", "Classify"]),
        ("Math and ML", ["Objective", "Loss", "Training strategy"]),
        ("Validation", ["Metrics", "Dataset needs"]),
        ("Limitations", ["Failure modes and deployment constraints"]),
    ],
}


# Short domain acronyms that matter a great deal for this platform's topics
# despite failing the generic "longer than 2 characters" token filter — "AI"
# in particular was silently dropped from every topic's keyword/query
# expansion, which meant an "AI ... X-ray screening" topic never actually
# triggered any AI-specific concept queries.
_SHORT_DOMAIN_TERMS = {"ai", "ml", "ct", "xai", "ir", "uv", "3d", "2d"}


def _slug_terms(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", (text or "").lower())
    return [t for t in tokens if (len(t) > 2 or t in _SHORT_DOMAIN_TERMS) and t not in _STOPWORDS]


def _title_case_phrase(text: str) -> str:
    parts = re.split(r"\s+", re.sub(r"[^A-Za-z0-9\s-]+", " ", text).strip())
    return " ".join(part.capitalize() for part in parts if part)


def normalize_topic(topic: str, context: str | None = None, keywords: list[str] | None = None) -> dict[str, Any]:
    clean_topic = re.sub(r"\s+", " ", (topic or "").strip())
    clean_context = re.sub(r"\s+", " ", (context or "").strip())
    key_terms = []
    key_terms.extend(_slug_terms(clean_topic))
    if context:
        key_terms.extend(_slug_terms(context))
    if keywords:
        key_terms.extend(_slug_terms(" ".join(keywords)))

    focus_terms = []
    for term in key_terms:
        if term not in focus_terms:
            focus_terms.append(term)

    normalized = _title_case_phrase(clean_topic)
    if clean_context:
        normalized = f"{normalized} ({_title_case_phrase(clean_context[:120])})"

    scope_notes = [
        "Focus on verifiable sources and practical X-ray/security relevance.",
        "Do not infer section content until source evidence and gap matrices exist.",
    ]
    if clean_context:
        scope_notes.append("Context was provided by the user and is treated as scope guidance.")

    return {
        "original_topic": topic,
        "normalized_topic": normalized,
        "context": context,
        "scope_notes": scope_notes,
        "focus_terms": focus_terms[:12],
    }


# Concept queries covering the AI-in-X-ray-security-screening literature the
# platform specializes in (per the domain mission: ATR, deep learning for
# baggage X-ray, dual-energy/CT, material discrimination, TIP, false-positive
# reduction, explainable AI, human-AI collaboration, deployment, datasets).
# Each is only added to a run's query set when its trigger tokens actually
# overlap the topic, so a run about an unrelated X-ray subject doesn't get
# flooded with AI-specific queries it has no use for.
_CONCEPT_QUERIES: dict[str, str] = {
    "ai_screening": "artificial intelligence X-ray security screening threat detection",
    "deep_learning": "deep learning baggage X-ray image classification",
    "atr": "automatic threat recognition X-ray screening algorithms",
    "object_detection": "object detection X-ray imagery security",
    "cnn_transformer": "convolutional neural network transformer X-ray threat detection",
    "dual_energy_ct": "dual-energy X-ray computed tomography screening material discrimination",
    "cargo_vehicle": "cargo vehicle X-ray inspection AI automated",
    "tip": "threat image projection X-ray security screening",
    "false_positive": "false-positive reduction X-ray baggage screening alarm",
    "explainable_ai": "explainable AI human-AI collaboration security screening",
    "datasets": "X-ray security screening baggage dataset benchmark",
    "deployment": "deployment validation AI X-ray screening airport customs",
    # X-ray source/generator/detector physics track — a genuinely distinct
    # sub-field from screening (tube/generator design, radiation physics,
    # detector/photon statistics). A topic like "AI and X-ray sources" is
    # ambiguous between this and screening, so both tracks are searched
    # whenever their own trigger words are present, rather than assuming
    # every AI+X-ray topic means screening.
    "source_physics": "artificial intelligence X-ray tube generator source design optimization",
    "detector_physics": "machine learning X-ray detector technology photon statistics radiation physics",
    "explosives_detection": "AI explosives detection X-ray material discrimination density",
    "nuclear_radiological": "AI radiological nuclear threat detection gamma spectroscopy neutron special nuclear material",
}

_CONCEPT_TRIGGER_TOKENS: dict[str, set[str]] = {
    "ai_screening": {"ai", "artificial", "intelligence", "screening", "threat"},
    "deep_learning": {"deep", "learning", "neural", "network", "cnn"},
    "atr": {"threat", "recognition", "automatic", "detection"},
    "object_detection": {"detection", "object", "recognition", "vision", "imagery"},
    "cnn_transformer": {"cnn", "convolutional", "transformer", "neural", "network", "model"},
    "dual_energy_ct": {"dual", "energy", "ct", "tomography", "material"},
    "cargo_vehicle": {"cargo", "container", "vehicle", "freight"},
    "tip": {"tip", "projection", "training"},
    "false_positive": {"false", "alarm", "positive"},
    "explainable_ai": {"explainable", "xai", "interpretable", "human", "operator"},
    "datasets": {"dataset", "datasets", "benchmark"},
    "deployment": {"deployment", "validation", "operational", "airport", "customs", "implementation", "implementations"},
    "source_physics": {"source", "sources", "generator", "generators", "tube", "tubes", "anode", "cathode", "voltage", "spectrum"},
    "detector_physics": {"detector", "detectors", "photon", "photons", "scintillator", "sensor", "sensors", "physics", "radiation", "dose"},
    "explosives_detection": {"explosive", "explosives", "bomb", "ied", "contraband"},
    "nuclear_radiological": {"nuclear", "radiological", "radioactive", "gamma", "neutron", "isotope", "isotopes", "snm", "dirty"},
}


def _expand_search_queries(normalized_topic: str, unique_terms: list[str], synonyms: dict[str, list[str]], mode: str, context: str | None) -> list[str]:
    queries: list[str] = [normalized_topic]

    # Synonym-substituted variants of the topic itself.
    for term, expansions in list(synonyms.items())[:2]:
        if expansions:
            variant = normalized_topic.replace(term, expansions[0])
            if variant != normalized_topic:
                queries.append(variant)

    # Curated concept queries, ranked by token overlap with the topic and only
    # included when relevant — this platform is X-ray-security-specific, so a
    # generic AI/detection topic legitimately overlaps most of them.
    topic_token_set = set(unique_terms)

    # A topic that is *already* clearly about AI/detection (even a short,
    # generic phrase like "AI ... X-ray scanning systems") is squarely this
    # platform's core subject — pull in the core AI-in-screening concept
    # queries even when the topic string is too short to literally contain
    # every trigger word (e.g. it says "AI" but never says "neural network").
    ai_signal_tokens = {"ai", "artificial", "intelligence", "deep", "learning", "neural", "machine", "algorithm", "automatic", "detection", "recognition"}
    core_ai_concepts = {"ai_screening", "deep_learning", "atr", "object_detection", "cnn_transformer"}
    is_ai_topic = bool(topic_token_set & ai_signal_tokens)

    scored = sorted(
        _CONCEPT_TRIGGER_TOKENS.items(),
        key=lambda kv: len(topic_token_set & kv[1]),
        reverse=True,
    )
    for concept_key, trigger_tokens in scored:
        relevant = len(topic_token_set & trigger_tokens) > 0
        relevant = relevant or (is_ai_topic and concept_key in core_ai_concepts)
        if not relevant:
            continue
        queries.append(_CONCEPT_QUERIES[concept_key])
        if len(queries) >= 10:
            break

    if context:
        queries.append(f"{normalized_topic} {context[:80]}")

    # Dedupe while preserving order.
    seen: set[str] = set()
    out: list[str] = []
    for q in queries:
        key = q.strip().lower()
        if key and key not in seen:
            seen.add(key)
            out.append(q.strip())
    return out[:10]


def generate_search_keywords(normalized_topic: str, mode: str, context: str | None = None, user_keywords: list[str] | None = None) -> dict[str, Any]:
    tokens = _slug_terms(normalized_topic)
    if context:
        tokens.extend(_slug_terms(context))
    if user_keywords:
        tokens.extend(_slug_terms(" ".join(user_keywords)))

    unique_terms: list[str] = []
    for term in tokens:
        if term not in unique_terms:
            unique_terms.append(term)

    synonym_map: dict[str, list[str]] = {
        "xray": ["x-ray", "x ray", "radiography"],
        "detector": ["sensor", "imager", "detection system"],
        "security": ["screening", "inspection", "checkpoint"],
        "dual": ["multi-energy", "spectral", "two-energy"],
        "photon": ["quantum", "counting"],
        "ct": ["computed tomography", "tomographic"],
        "cargo": ["container", "freight"],
        "baggage": ["luggage", "parcel"],
        "algorithm": ["method", "pipeline", "approach"],
    }

    synonyms: dict[str, list[str]] = {}
    for term in unique_terms:
        expanded = synonym_map.get(term, [])
        if expanded:
            synonyms[term] = expanded

    search_keywords = unique_terms[:10]
    search_queries = _expand_search_queries(normalized_topic, unique_terms, synonyms, mode, context)

    return {
        "search_keywords": search_keywords,
        "synonyms": synonyms,
        "search_queries": search_queries,
    }


def _source_to_json(source) -> dict[str, Any]:
    return {
        "title": getattr(source, "title", ""),
        "source_type": getattr(source, "source_type", "external"),
        "url": getattr(source, "url", ""),
        "year": getattr(source, "year", ""),
        "authors": getattr(source, "authors", ""),
        "publisher": getattr(source, "publisher", ""),
        "doi": getattr(source, "doi", ""),
        "patent_number": getattr(source, "patent_number", ""),
        "standard_number": getattr(source, "standard_number", ""),
        "verified_by": getattr(source, "verified_by", ""),
        "abstract": getattr(source, "abstract", ""),
        "relevance_score": round(float(getattr(source, "relevance_score", 0.0) or 0.0), 3),
        "provider": getattr(source, "provider", ""),
        "citation_count": getattr(source, "citation_count", None),
        "is_peer_reviewed": getattr(source, "is_peer_reviewed", None),
        "doi_verified": bool(getattr(source, "doi_verified", False)),
        "is_retracted": bool(getattr(source, "is_retracted", False)),
        "quality_score": round(float(getattr(source, "quality_score", 0.0) or 0.0), 3),
    }


def _priority_rank_for_source_type(source_type: str) -> int:
    return {
        "academic": 1,
        "standard": 2,
        "regulator": 2,
        "manufacturer": 3,
        "patent": 4,
        "knowledge_base": 5,
    }.get(source_type, 6)


def _source_priority_label(source_type: str) -> str:
    return {
        "academic": "Peer-reviewed or indexed academic source",
        "standard": "Official standard or government publication",
        "regulator": "Official standard or government publication",
        "manufacturer": "Official manufacturer documentation",
        "patent": "Patent or prior-art source",
        "knowledge_base": "Uploaded knowledge-base document",
    }.get(source_type, "General reference")


def _serialize_kb_chunk(chunk: Any) -> dict[str, Any]:
    content = (getattr(chunk, "content", "") or "").strip()
    return {
        "citation_key": None,
        "title": getattr(chunk, "filename", None) or "Unknown KB document",
        "filename": getattr(chunk, "filename", None) or "Unknown KB document",
        "page_num": getattr(chunk, "page_num", None),
        "source_type": "knowledge_base",
        "url": "",
        "year": "",
        "authors": "",
        "publisher": "Uploaded knowledge base",
        "doi": "",
        "patent_number": "",
        "standard_number": "",
        "verified_by": f"Uploaded knowledge base page ~{getattr(chunk, 'page_num', 1)}",
        "abstract": content[:900],
        "relevance_score": round(float(getattr(chunk, "score", 0.0) or 0.0), 3),
        "priority_rank": _priority_rank_for_source_type("knowledge_base"),
        "source_priority": _source_priority_label("knowledge_base"),
        "chunk_index": getattr(chunk, "chunk_index", None),
    }


def _kb_chunks_to_sources(chunks: list[Any]) -> list[dict[str, Any]]:
    kb_sources: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, 1):
        source = _serialize_kb_chunk(chunk)
        source["citation_key"] = f"KB-{index}"
        source["source_index"] = index
        kb_sources.append(source)
    return kb_sources


def _merge_source_bases(external_sources: list[dict[str, Any]], kb_sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()

    def key_for(source: dict[str, Any]) -> str:
        if source.get("doi"):
            return f"doi:{source['doi'].strip().lower()}"
        if source.get("url"):
            return f"url:{source['url'].strip().lower()}"
        title = source.get("title", "").strip().lower()
        filename = source.get("filename", "").strip().lower()
        page = str(source.get("page_num", "")).strip().lower()
        return f"title:{title}|file:{filename}|page:{page}"

    for source in external_sources + kb_sources:
        key = key_for(source)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)

    merged.sort(key=lambda item: (
        item.get("priority_rank", _priority_rank_for_source_type(item.get("source_type", ""))),
        -float(item.get("relevance_score", 0.0) or 0.0),
        item.get("citation_key", ""),
    ))
    return merged


def _build_source_transparency(artifacts: dict[str, Any]) -> dict[str, Any]:
    external = artifacts.get("sources_accepted", [])
    rejected = artifacts.get("sources_rejected", [])
    kb_chunks = artifacts.get("kb_chunks", [])
    kb_sources = artifacts.get("kb_sources", [])
    trans = artifacts.get("source_transparency", {})

    return {
        "academic_sources_searched": trans.get("academic_sources_searched", []),
        "official_sources_searched": trans.get("official_sources_searched", []),
        "manufacturer_sources_searched": trans.get("manufacturer_sources_searched", []),
        "knowledge_base_documents_used": [
            {
                "filename": src.get("filename", "Unknown KB document") if isinstance(src, dict) else getattr(src, "filename", "Unknown KB document"),
                "page": src.get("page_num") if isinstance(src, dict) else getattr(src, "page_num", None),
            }
            for src in kb_sources[:12]
        ] if kb_sources else [
            {
                "filename": getattr(chunk, "filename", "Unknown KB document"),
                "page": getattr(chunk, "page_num", None),
            }
            for chunk in kb_chunks[:12]
        ],
        "verified_references": [
            {
                "citation_key": src.get("citation_key", ""),
                "title": src.get("title", ""),
                "source_type": src.get("source_type", ""),
                "priority_rank": src.get("priority_rank", _priority_rank_for_source_type(src.get("source_type", ""))),
                "relevance_score": src.get("relevance_score", 0.0),
            }
            for src in (external + kb_sources)
        ],
        "rejected_references": rejected[:20],
        "knowledge_base_contribution": trans.get("knowledge_base_contribution", {}),
        "external_evidence_contribution": trans.get("external_evidence_contribution", {}),
    }


def _build_source_transparency_section(artifacts: dict[str, Any]) -> str:
    transparency = _build_source_transparency(artifacts)
    kb_docs = transparency.get("knowledge_base_documents_used", [])
    verified_refs = transparency.get("verified_references", [])
    rejected_refs = transparency.get("rejected_references", [])
    kb_contrib = transparency.get("knowledge_base_contribution", {})
    ext_contrib = transparency.get("external_evidence_contribution", {})

    lines = ["## Search Transparency", ""]
    lines.append("### Search Order")
    lines.append("1. Verified academic and technical sources from the Internet")
    lines.append("2. Official standards and government publications")
    lines.append("3. Official manufacturer documentation")
    lines.append("4. Uploaded knowledge-base documents")
    lines.append("5. General LLM knowledge only for explanation, never as evidence")
    lines.append("")

    def list_block(title: str, values: list[str]) -> None:
        lines.append(f"### {title}")
        if values:
            for value in values:
                lines.append(f"- {value}")
        else:
            lines.append("- None recorded")
        lines.append("")

    list_block("Academic Sources Searched", transparency.get("academic_sources_searched", []))
    list_block("Official Sources Searched", transparency.get("official_sources_searched", []))
    list_block("Manufacturer Sources Searched", transparency.get("manufacturer_sources_searched", []))

    lines.append("### Knowledge Base Documents Used")
    if kb_docs:
        for doc in kb_docs:
            filename = doc.get("filename", "Unknown document")
            page = doc.get("page")
            if page:
                lines.append(f"- {filename} (page ~{page})")
            else:
                lines.append(f"- {filename}")
    else:
        lines.append("- No uploaded knowledge-base documents were used.")
    lines.append("")

    lines.append("### Verified References")
    if verified_refs:
        summary_rows = []
        for ref in verified_refs[:20]:
            summary_rows.append([
                ref.get("citation_key", ""),
                ref.get("title", "")[:80],
                ref.get("source_type", ""),
                str(ref.get("priority_rank", "")),
            ])
        lines.append(_table_md(["Key", "Title", "Type", "Priority"], summary_rows))
    else:
        lines.append("- None")
    lines.append("")

    lines.append("### Rejected References")
    if rejected_refs:
        rejected_rows = []
        for ref in rejected_refs[:15]:
            rejected_rows.append([
                ref.get("title", "")[:70],
                ref.get("source_type", ""),
                ", ".join(ref.get("rejection_reasons", [])[:3]),
            ])
        lines.append(_table_md(["Title", "Type", "Rejected Because"], rejected_rows))
    else:
        lines.append("- None")
    lines.append("")

    lines.append("### Knowledge-Base Contribution")
    if kb_contrib:
        for key, value in kb_contrib.items():
            lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    else:
        lines.append("- Uploaded documents were used only as a supplement to verified external evidence.")
    lines.append("")

    lines.append("### External Evidence Contribution")
    if ext_contrib:
        for key, value in ext_contrib.items():
            lines.append(f"- {key.replace('_', ' ').title()}: {value}")
    else:
        lines.append("- External evidence formed the primary basis of the draft.")
    return "\n".join(lines).strip()


def _topic_tokens(normalized_topic: str, keywords: list[str]) -> set[str]:
    return set(_slug_terms(normalized_topic) + _slug_terms(" ".join(keywords)))


def _research_cache_key(mode: str, topic: str, context: str | None, keywords: list[str] | None, depth: str | None, word_count: int | None) -> str:
    key = {
        "mode": mode,
        "topic": (topic or "").strip().lower(),
        "context": (context or "").strip().lower(),
        "keywords": sorted([(k or "").strip().lower() for k in (keywords or []) if (k or "").strip()]),
        "depth": (depth or "").strip().lower(),
        "word_count": int(word_count or 0),
    }
    return "research:phase1:" + json.dumps(key, sort_keys=True, ensure_ascii=True)


def _clone_json(obj: Any) -> Any:
    return json.loads(json.dumps(obj, ensure_ascii=False))


def _extract_first_match(blob: str, candidates: list[str], fallback: str = "") -> str:
    low = blob.lower()
    for c in candidates:
        if c.lower() in low:
            return c
    return fallback


def _extract_equation_candidates(text: str) -> list[str]:
    equations: list[str] = []
    for pattern in [r"\$\$(.+?)\$\$", r"\\\((.+?)\\\)", r"\\\[(.+?)\\\]", r"\$([^$\n]{1,300})\$"]:
        for m in re.findall(pattern, text or "", flags=re.DOTALL):
            eq = re.sub(r"\s+", " ", m).strip()
            if eq and eq not in equations:
                equations.append(eq)
    return equations[:6]


def _evidence_database_row(source: dict[str, Any], normalized_topic: str) -> dict[str, Any]:
    title = source.get("title", "")
    abstract = source.get("abstract", "") or ""
    blob = f"{title} {abstract}"
    method = _extract_first_match(blob, [
        "deep learning", "machine learning", "convolutional network", "transformer", "bayesian", "monte carlo",
        "reconstruction", "segmentation", "classification", "detection", "signal processing",
    ], fallback="Not explicitly reported")
    equipment = _extract_first_match(blob, [
        "linac", "dual-energy", "photon counting", "x-ray detector", "scintillator", "computed tomography", "backscatter",
    ], fallback="Not explicitly reported")
    dataset = _extract_first_match(blob, [
        "dataset", "benchmark", "sample", "phantom", "cargo", "baggage", "container", "vehicle",
    ], fallback="Not explicitly reported")
    results = _extract_first_match(blob, [
        "accuracy", "sensitivity", "specificity", "precision", "recall", "auc", "f1", "throughput", "false alarm",
    ], fallback="Not explicitly reported")
    limitations = _extract_first_match(blob, [
        "limitation", "challenge", "constraint", "future work", "uncertainty", "bias",
    ], fallback="Not explicitly reported")
    novelty = _extract_first_match(blob, [
        "novel", "new", "first", "proposed", "improved", "enhanced",
    ], fallback="Not explicitly reported")

    return {
        "citation_key": source.get("citation_key", ""),
        "title": title,
        "authors": source.get("authors", ""),
        "year": source.get("year", ""),
        "publisher": source.get("publisher", ""),
        "doi": source.get("doi", ""),
        "url": source.get("url", ""),
        "research_question": f"How does this source contribute to {normalized_topic}?",
        "methodology": method,
        "equipment": equipment,
        "algorithms": method,
        "dataset": dataset,
        "equations": _extract_equation_candidates(blob),
        "results": results,
        "limitations": limitations,
        "novelty": novelty,
        "future_work": "Use as comparative baseline for future experiments.",
        "reliability_score": round(float(source.get("relevance_score", 0.0) or 0.0) + max(0, 6 - _priority_rank_for_source_type(source.get("source_type", ""))), 3),
        "source_type": source.get("source_type", ""),
        "priority_rank": source.get("priority_rank", _priority_rank_for_source_type(source.get("source_type", ""))),
    }


def build_scientific_analysis(accepted_sources: list[dict[str, Any]], literature_matrix: list[dict[str, Any]], gap_matrix: list[dict[str, Any]]) -> dict[str, Any]:
    timeline = []
    by_year = {}
    for src in accepted_sources:
        year = (src.get("year") or "n.d.").strip() or "n.d."
        by_year.setdefault(year, 0)
        by_year[year] += 1
    for year, count in sorted(by_year.items(), key=lambda kv: kv[0]):
        timeline.append({"year": year, "evidence_count": count})

    def _compare_by(predicate: str, label: str) -> list[dict[str, Any]]:
        grouped: dict[str, int] = {}
        for row in literature_matrix:
            key = row.get(predicate, "unknown") or "unknown"
            grouped[key] = grouped.get(key, 0) + 1
        return [{label: k, "count": v} for k, v in grouped.items()]

    strengths = []
    weaknesses = []
    if any(row.get("source_type") == "academic" for row in literature_matrix):
        strengths.append("Academic evidence base is present and prioritized.")
    else:
        weaknesses.append("Academic evidence coverage is insufficient.")
    if any(row.get("source_type") in {"standard", "regulator"} for row in literature_matrix):
        strengths.append("Official standards and regulatory references are included.")
    else:
        weaknesses.append("Standards/regulatory coverage remains limited.")
    if sum(1 for row in literature_matrix if row.get("source_type") == "knowledge_base") > 0:
        strengths.append("Knowledge base contributes implementation-specific context without dominating evidence.")

    open_questions = [
        gap.get("gap", "") for gap in gap_matrix[:8] if gap.get("gap")
    ]

    return {
        "technology_evolution_timeline": timeline,
        "method_comparison": _compare_by("method_focus", "method_focus"),
        "dataset_comparison": _compare_by("evidence_type", "dataset_signal"),
        "algorithm_comparison": _compare_by("method_focus", "algorithm_family"),
        "standard_comparison": _compare_by("source_type", "source_type"),
        "patent_comparison": [row for row in literature_matrix if row.get("source_type") == "patent"],
        "strengths": strengths,
        "weaknesses": weaknesses,
        "open_research_questions": open_questions,
    }


# Cap accepted academic references to the strongest N — perform_hybrid_external_research
# already returns academic sources sorted by quality_score (best first), so
# capping here keeps exactly the strongest 20-40 rather than every candidate
# that happened to clear the relevance bar.
_MAX_ACCEPTED_ACADEMIC_SOURCES = 40
# Target ratio acceptance aims for while admitting sources — set a bit above
# the publication-readiness gate's actual 0.6 floor (research_quality.py) so
# the accepted set clears the gate with margin rather than landing exactly on
# the boundary.
_MIN_PEER_REVIEWED_RATIO_TARGET = 0.65


def verify_sources(sources: list[Any], normalized_topic: str, keywords: list[str]) -> dict[str, Any]:
    topic_tokens = _topic_tokens(normalized_topic, keywords)
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    accepted_academic_count = 0
    accepted_peer_reviewed = 0
    accepted_non_peer_reviewed = 0

    for idx, source in enumerate(sources, 1):
        record = _source_to_json(source)
        title_tokens = set(_slug_terms(record["title"]))
        abstract_tokens = set(_slug_terms(record["abstract"]))
        evidence_tokens = title_tokens | abstract_tokens | set(_slug_terms(record["publisher"]))
        overlap = len(evidence_tokens & topic_tokens)
        reasons: list[str] = []

        if not record["title"]:
            reasons.append("missing_title")
        if not record["url"]:
            reasons.append("missing_url")
        if not record["verified_by"]:
            reasons.append("missing_verification_trace")
        if record["source_type"] == "academic" and not (record["doi"] or record["abstract"] or record["authors"]):
            reasons.append("insufficient_academic_metadata")
        if overlap == 0:
            reasons.append("low_topic_overlap")
        if record["source_type"] == "academic" and len(title_tokens) < 3:
            reasons.append("weak_title_signal")
        if record["source_type"] == "academic" and accepted_academic_count >= _MAX_ACCEPTED_ACADEMIC_SOURCES:
            reasons.append("exceeds_max_accepted_academic_sources")
        # Preserve the required >=60% peer-reviewed ratio (research_quality.py's
        # publication-readiness gate) by capping how many non-peer-reviewed
        # academic sources (mainly arXiv preprints) can be admitted relative to
        # peer-reviewed ones, rather than hoping ranking alone gets there.
        # Sources arrive quality-sorted (peer-reviewed already scores higher),
        # so this mostly just formalizes what ranking already tends to do.
        # Simulates the ratio *after* provisionally accepting this source and
        # rejects if it would drop below the gate's floor — a one-source
        # bootstrap grace (the "+ 1" in the denominator only) lets the very
        # first candidate through even if it happens to be non-peer-reviewed,
        # so a strong single arXiv result doesn't deadlock acceptance.
        if record["source_type"] == "academic" and not reasons and not record.get("is_peer_reviewed"):
            prospective_nonpeer = accepted_non_peer_reviewed + 1
            prospective_ratio = accepted_peer_reviewed / (accepted_peer_reviewed + prospective_nonpeer)
            if prospective_nonpeer > 1 and prospective_ratio < (_MIN_PEER_REVIEWED_RATIO_TARGET):
                reasons.append("exceeds_non_peer_reviewed_ratio_cap")

        if reasons:
            rejected.append({
                **record,
                "source_index": idx,
                "priority_rank": _priority_rank_for_source_type(record.get("source_type", "")),
                "source_priority": _source_priority_label(record.get("source_type", "")),
                "rejection_reasons": reasons,
            })
            continue

        if record["source_type"] == "academic":
            accepted_academic_count += 1
            if record.get("is_peer_reviewed"):
                accepted_peer_reviewed += 1
            else:
                accepted_non_peer_reviewed += 1

        accepted.append({
            **record,
            "source_index": idx,
            "citation_key": f"SRC-{len(accepted) + 1}",
            "priority_rank": _priority_rank_for_source_type(record.get("source_type", "")),
            "source_priority": _source_priority_label(record.get("source_type", "")),
            "acceptance_notes": [
                "Verified authority trace present.",
                "Topic overlap is sufficient for downstream evidence extraction.",
            ],
        })

    return {
        "sources_found": [_source_to_json(source) for source in sources],
        "sources_accepted": accepted,
        "sources_rejected": rejected,
    }


def _pick_evidence_sentences(abstract: str, keywords: list[str], limit: int = 3) -> list[str]:
    if not abstract:
        return []
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", abstract) if s.strip()]
    if not sentences:
        return []

    keywords_set = set(_slug_terms(" ".join(keywords)))

    def score(sentence: str) -> tuple[int, int]:
        tokens = set(_slug_terms(sentence))
        keyword_hits = len(tokens & keywords_set)
        return keyword_hits, len(sentence)

    ranked = sorted(sentences, key=score, reverse=True)
    return ranked[:limit]


def extract_structured_evidence(accepted_sources: list[dict[str, Any]], normalized_topic: str, keywords: list[str]) -> list[dict[str, Any]]:
    evidence_rows: list[dict[str, Any]] = []
    topic_tokens = _topic_tokens(normalized_topic, keywords)

    for source in accepted_sources:
        abstract = source.get("abstract", "") or ""
        picked = _pick_evidence_sentences(abstract, keywords, limit=2)
        if not picked:
            picked = [source.get("title", "")]

        source_tokens = set(_slug_terms(source.get("title", ""))) | set(_slug_terms(abstract))
        support = len(source_tokens & topic_tokens)
        evidence_type = "background"
        blob = f"{source.get('title', '')} {abstract}".lower()
        if any(term in blob for term in ["method", "pipeline", "algorithm", "model"]):
            evidence_type = "method"
        elif any(term in blob for term in ["dataset", "sample", "experiment", "trial"]):
            evidence_type = "dataset"
        elif any(term in blob for term in ["result", "performance", "accuracy", "benchmark"]):
            evidence_type = "results"
        elif any(term in blob for term in ["limitation", "challenge", "gap", "future work"]):
            evidence_type = "limitation"

        evidence_rows.append({
            "citation_key": source["citation_key"],
            "source_index": source["source_index"],
            "title": source.get("title", ""),
            "authors": source.get("authors", ""),
            "year": source.get("year", ""),
            "source_type": source.get("source_type", "external"),
            "abstract": abstract,
            "key_findings": picked,
            "limitations": "Not explicitly reported" if "limitation" not in blob else "Limitations reported in source text",
            "doi": source.get("doi", ""),
            "url": source.get("url", ""),
            "evidence_type": evidence_type,
            "support_level": "high" if support >= 4 else "medium" if support >= 2 else "low",
            "supporting_sentences": picked,
            "evidence_summary": picked[0],
            "topic_alignment_score": support,
            # Carried through from _source_to_json so the publication-readiness
            # gate can score real reference quality (peer-review ratio, DOI
            # verification) instead of re-guessing it from rendered text.
            "provider": source.get("provider", ""),
            "citation_count": source.get("citation_count"),
            "is_peer_reviewed": source.get("is_peer_reviewed"),
            "doi_verified": bool(source.get("doi_verified", False)),
            "quality_score": source.get("quality_score", 0.0),
        })

    return evidence_rows


def build_literature_matrix(accepted_sources: list[dict[str, Any]], evidence_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    evidence_by_key = {row["citation_key"]: row for row in evidence_rows}
    matrix: list[dict[str, Any]] = []

    for source in accepted_sources:
        evidence = evidence_by_key.get(source["citation_key"], {})
        blob = f"{source.get('title', '')} {source.get('abstract', '')}".lower()
        method_focus = "study or system overview"
        if any(term in blob for term in ["detector", "sensor", "hardware", "instrument"]):
            method_focus = "hardware or detector design"
        elif any(term in blob for term in ["algorithm", "learning", "network", "model"]):
            method_focus = "algorithmic or learning-based method"
        elif any(term in blob for term in ["review", "survey", "systematic"]):
            method_focus = "review or synthesis"
        elif any(term in blob for term in ["experiment", "benchmark", "validation"]):
            method_focus = "experimental validation"
        elif source.get("source_type") == "knowledge_base":
            method_focus = "uploaded implementation or project note"

        matrix.append({
            "citation_key": source["citation_key"],
            "title": source.get("title", ""),
            "year": source.get("year", ""),
            "source_type": source.get("source_type", "external"),
            "priority_rank": source.get("priority_rank", _priority_rank_for_source_type(source.get("source_type", ""))),
            "method_focus": method_focus,
            "core_contribution": evidence.get("evidence_summary") or source.get("abstract") or source.get("title", ""),
            "evidence_type": evidence.get("evidence_type", "background"),
            "support_level": evidence.get("support_level", "low"),
            "notes": source.get("acceptance_notes", []),
        })

    return matrix


def build_research_gap_matrix(normalized_topic: str, keywords: list[str], literature_matrix: list[dict[str, Any]]) -> list[dict[str, Any]]:
    title_blob = " ".join(row.get("title", "") for row in literature_matrix).lower()
    evidence_types = Counter(row.get("evidence_type", "background") for row in literature_matrix)
    source_types = Counter(row.get("source_type", "external") for row in literature_matrix)
    kb_count = source_types.get("knowledge_base", 0)

    gaps = [
        {
            "gap": f"Limited operational validation of {normalized_topic} in real screening workflows.",
            "why_it_matters": "Lab results often do not transfer directly to checkpoint or field-service conditions.",
            "evidence_support": "Most available sources emphasize theory, concepts, or isolated experiments.",
            "priority": "high",
            "recommended_next_step": "Define a field-validation protocol and deployment benchmark.",
        },
        {
            "gap": "Weak cross-source synthesis between hardware evidence and algorithmic evidence.",
            "why_it_matters": "The paper can over-index on one layer and understate the system interaction.",
            "evidence_support": f"Evidence mix currently favors {evidence_types.most_common(1)[0][0] if evidence_types else 'background'} content.",
            "priority": "high",
            "recommended_next_step": "Separate physical, data, and decision-making evidence into a shared matrix.",
        },
        {
            "gap": "Insufficient standards, compliance, or reproducibility framing.",
            "why_it_matters": "Publication-grade work needs explicit evaluation and verification criteria.",
            "evidence_support": f"Source mix currently includes {source_types.get('standard', 0)} standards/regulatory sources and {kb_count} supplementary KB sources.",
            "priority": "medium",
            "recommended_next_step": "Add a validation and traceability subsection in the outline.",
        },
        {
            "gap": "Unclear evidence for the strongest novelty claim.",
            "why_it_matters": "The outline should prioritize the most defensible contribution first.",
            "evidence_support": f"Current evidence tokens: {len(title_blob.split())} title/abstract terms across accepted literature.",
            "priority": "medium",
            "recommended_next_step": "Tie the primary contribution to the most frequent method-focus theme.",
        },
    ]

    if source_types.get("academic", 0) == 0:
        gaps.append({
            "gap": "No verified academic sources were retained after verification.",
            "why_it_matters": "The paper outline should not overstate evidence strength.",
            "evidence_support": "The pipeline kept only authoritative non-academic references.",
            "priority": "high",
            "recommended_next_step": "Relax topic specificity or expand the search keyword set.",
        })

    return gaps


def build_phase1_outline(mode: str, normalized_topic: str, keywords: list[str], literature_matrix: list[dict[str, Any]], gap_matrix: list[dict[str, Any]]) -> dict[str, Any]:
    sections = []
    for heading, bullets in _MODE_OUTLINE_SECTIONS.get(mode, _MODE_OUTLINE_SECTIONS["paper_ieee"]):
        sections.append({
            "heading": heading,
            "purpose": bullets[0] if bullets else "",
            "bullet_points": bullets,
        })

    primary_sources = [row["citation_key"] for row in literature_matrix[:6]]
    figures = [
        {
            "figure": "Figure 1",
            "caption": f"Conceptual pipeline for {normalized_topic}.",
            "purpose": "Show the technical flow before section drafting begins.",
        },
        {
            "figure": "Figure 2",
            "caption": "Evidence and gap linkage across accepted sources.",
            "purpose": "Connect literature matrix entries to the research gap matrix.",
        },
    ]
    tables = [
        {
            "table": "Table 1",
            "caption": "Literature matrix assembled from verified sources.",
            "purpose": "Support source traceability.",
        },
        {
            "table": "Table 2",
            "caption": "Research gap matrix and priority ranking.",
            "purpose": "Define the focus for later prose generation.",
        },
    ]

    return {
        "title": f"{normalized_topic}",
        "mode": mode,
        "mode_label": RESEARCH_MODE_LABELS.get(mode, mode.replace("_", " ").title()),
        "search_focus": keywords[:8],
        "primary_sources": primary_sources,
        "section_plan": sections,
        "figure_plan": figures,
        "table_plan": tables,
        "drafting_notes": [
            "Do not write any section prose yet.",
            "Use the evidence and gap matrices as the only source of truth for Phase 2.",
            "Keep citations grounded in the accepted source list.",
        ],
        "gap_priorities": [gap["gap"] for gap in gap_matrix[:4]],
    }


_MAX_RETRIEVAL_ALIGNMENT_RETRIES = 2
_TARGET_EVIDENCE_ALIGNMENT = 0.9


async def _retrieve_with_alignment_retry(topic: str, domain_label: str, queries: list[str], mode: str = ""):
    """Search, then keep broadening the query set and re-searching until the
    retrieved evidence's own vocabulary plausibly matches the topic *and*
    there's enough of it — instead of writing a full paper on whatever the
    first, possibly-too-narrow query happened to return and only discovering
    the mismatch or the thin reference count afterward.

    Good alignment with too few references is still a retry trigger — a
    tight domain-relevance gate (see _is_relevant's _STRONG_XRAY_DOMAIN_TERMS
    check) can legitimately shrink a raw hit count down to a clean but small
    pool on the very first, narrow query; broadening the query set finds
    more of the *same* on-topic literature rather than diluting it.

    This never blocks indefinitely: it tries the given queries, then up to
    `_MAX_RETRIEVAL_ALIGNMENT_RETRIES` broadened attempts, and always returns
    the best attempt seen (even if none crossed the target) so the caller can
    proceed with the strongest evidence found rather than nothing at all.
    Every attempt and its score is logged server-side only — this is
    intentionally invisible to the end user, who should just see either a
    good paper or a single simple failure message, never intermediate scores.
    """
    from api.utils.research_quality import (
        title_alignment_score, _LITERATURE_HEAVY_MODES,
        _MIN_REFERENCES_LITERATURE_HEAVY, _MIN_REFERENCES_DEFAULT,
    )

    min_refs = _MIN_REFERENCES_LITERATURE_HEAVY if mode in _LITERATURE_HEAVY_MODES else _MIN_REFERENCES_DEFAULT

    attempt_queries = list(queries)
    best_retrieval = None
    best_score = -1.0
    best_academic_count = -1
    best_retrieval_error: str | None = None

    for attempt in range(_MAX_RETRIEVAL_ALIGNMENT_RETRIES + 1):
        try:
            retrieval = await asyncio.wait_for(
                perform_hybrid_external_research(attempt_queries, domain_label),
                timeout=120,
            )
            retrieval_error = None
        except Exception as exc:
            retrieval = None
            retrieval_error = str(exc)

        academic = [s for s in (retrieval.sources if retrieval else []) if s.source_type == "academic"]
        corpus = "\n".join(f"{s.title} {s.abstract}" for s in academic)
        score = title_alignment_score(topic, corpus) if academic else 0.0

        log.info(
            "Research retrieval attempt %d/%d: queries=%d academic_sources=%d evidence_alignment=%.2f (need >=%d refs)",
            attempt + 1, _MAX_RETRIEVAL_ALIGNMENT_RETRIES + 1, len(attempt_queries), len(academic), score, min_refs,
        )

        # Prefer whichever attempt has better alignment; among equally-aligned
        # attempts prefer more evidence (a broadened retry that keeps the
        # same clean alignment but finds more references is strictly better).
        if score > best_score or (score == best_score and len(academic) > best_academic_count):
            best_score = score
            best_academic_count = len(academic)
            best_retrieval = retrieval
            best_retrieval_error = retrieval_error

        # verify_sources() rejects some raw candidates afterward (weak title
        # signal, insufficient metadata, the peer-review-ratio cap, etc.), so
        # raw retrieval count must clear min_refs with real margin, not just
        # touch it, or the final accepted count lands short even though this
        # check said "sufficient".
        sufficient = score >= _TARGET_EVIDENCE_ALIGNMENT and len(academic) >= max(min_refs + 8, round(min_refs * 1.5))
        if sufficient or attempt == _MAX_RETRIEVAL_ALIGNMENT_RETRIES:
            break

        # Broaden: pull in every domain concept-track query not already tried
        # (covers screening, source/detector physics, explosives, nuclear/
        # radiological) so a retry searches meaningfully differently, not
        # just the same narrow net again.
        extra = [q for q in _CONCEPT_QUERIES.values() if q not in attempt_queries]
        attempt_queries = (attempt_queries + extra)[:16]

    return best_retrieval, best_score, best_retrieval_error


async def run_phase1_research_pipeline(
    db: Session,
    *,
    user_id: str | None,
    mode: str,
    topic: str,
    context: str | None = None,
    keywords: list[str] | None = None,
    depth: str | None = None,
    word_count: int | None = None,
) -> dict[str, Any]:
    run_id = str(uuid.uuid4())
    cache_key = _research_cache_key(mode, topic, context, keywords, depth, word_count)
    cached_artifacts = research_meta_cache.get(cache_key)

    if cached_artifacts is not None:
        artifacts = _clone_json(cached_artifacts)
        artifacts.setdefault("stages", {})
        artifacts["stages"]["cache_reuse"] = {
            "cache_hit": True,
            "message": "Evidence retrieval reused from cached topic fingerprint to minimize repeated searches.",
        }
        completed = create_research_pipeline_run(
            db,
            run_id=run_id,
            user_id=user_id,
            mode=mode,
            topic=topic,
            normalized_topic=artifacts.get("normalized_topic", topic),
            artifacts=artifacts,
            status="complete",
            current_stage="export",
        )
        return {"run": completed, "artifacts": artifacts}

    artifacts: dict[str, Any] = {
        "phase": "phase1",
        "mode": mode,
        "topic": topic,
        "generation_depth": depth,
        "target_word_count": word_count,
        "stages": {},
    }

    normalized = normalize_topic(topic, context=context, keywords=keywords)
    artifacts["stages"]["topic_understanding"] = normalized
    artifacts["stages"]["topic_normalization"] = normalized
    artifacts["normalized_topic"] = normalized["normalized_topic"]
    create_research_pipeline_run(
        db,
        run_id=run_id,
        user_id=user_id,
        mode=mode,
        topic=topic,
        normalized_topic=normalized["normalized_topic"],
        artifacts=artifacts,
        status="running",
        current_stage="topic_understanding",
    )

    keyword_stage = generate_search_keywords(normalized["normalized_topic"], mode, context=context, user_keywords=keywords)
    artifacts["stages"]["scientific_query_expansion"] = keyword_stage
    artifacts["stages"]["search_keywords"] = keyword_stage
    artifacts["search_keywords"] = keyword_stage["search_keywords"]
    artifacts["search_synonyms"] = keyword_stage["synonyms"]
    update_research_pipeline_run(
        db,
        run_id,
        artifacts=artifacts,
        status="running",
        current_stage="scientific_query_expansion",
        normalized_topic=normalized["normalized_topic"],
    )

    # Search, and if the retrieved evidence doesn't plausibly match the topic,
    # automatically broaden and retry before ever committing to writing a
    # paper on it — see _retrieve_with_alignment_retry. Attempt count and
    # alignment scores are logged server-side only, never surfaced to the user.
    retrieval, evidence_alignment_score, retrieval_error = await _retrieve_with_alignment_retry(
        normalized["normalized_topic"],
        RESEARCH_MODE_LABELS.get(mode, mode),
        keyword_stage["search_queries"],
        mode=mode,
    )

    sources = retrieval.sources if retrieval else []
    sources_payload = {
        "searched_at_utc": retrieval.searched_at_utc if retrieval else datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "searched_sources": retrieval.searched_sources if retrieval else [],
        "warnings": (retrieval.warnings if retrieval else []) + ([f"External retrieval failed: {retrieval_error}"] if retrieval_error else []),
        "sources_found": [_source_to_json(source) for source in sources],
    }
    artifacts["stages"]["internet_academic_search"] = {
        "searched_sources": sources_payload["searched_sources"],
        "warnings": sources_payload["warnings"],
        "academic_sources": [s for s in sources_payload["sources_found"] if s.get("source_type") == "academic"],
    }
    artifacts["stages"]["standards_search"] = {
        "standards_sources": [s for s in sources_payload["sources_found"] if s.get("source_type") in {"standard", "regulator"}],
    }
    artifacts["stages"]["patent_search"] = {
        "patent_sources": [s for s in sources_payload["sources_found"] if s.get("source_type") == "patent"],
    }
    artifacts["stages"]["manufacturer_documentation_search"] = {
        "manufacturer_sources": [s for s in sources_payload["sources_found"] if s.get("source_type") == "manufacturer"],
    }
    artifacts["stages"]["source_retrieval"] = sources_payload
    artifacts["sources_found"] = sources_payload["sources_found"]
    # Internal diagnostic only — never rendered to the user as a score or
    # warning; used by the caller to decide whether to report a simple
    # "not enough evidence" failure after Phase 2 if things still don't add up.
    artifacts["_evidence_alignment_score"] = evidence_alignment_score
    update_research_pipeline_run(
        db,
        run_id,
        artifacts=artifacts,
        status="running",
        current_stage="internet_academic_search",
        normalized_topic=normalized["normalized_topic"],
    )

    verification = verify_sources(sources, normalized["normalized_topic"], keyword_stage["search_keywords"])
    artifacts["stages"]["source_verification"] = verification
    artifacts["sources_accepted"] = verification["sources_accepted"]
    artifacts["sources_rejected"] = verification["sources_rejected"]

    kb_chunks: list[Any] = []
    kb_queries: list[str] = []
    try:
        base_queries = [
            normalized["normalized_topic"],
            " ".join(keyword_stage["search_keywords"][:6]),
            f"{normalized['normalized_topic']} cargo inspection x-ray screening detector",
        ]
        if mode in {"paper_ieee", "paper_elsevier", "technical_report", "literature_review"}:
            base_queries.append(f"{normalized['normalized_topic']} standards implementation safety")
        for query in base_queries:
            cleaned = re.sub(r"\s+", " ", query).strip()
            if cleaned and cleaned not in kb_queries:
                kb_queries.append(cleaned)
        top_k = 6 if mode in {"literature_review", "research_gaps"} else 4
        for query in kb_queries:
            chunks = await retrieve_chunks(query, db, top_k=top_k)
            if chunks:
                kb_chunks.extend(chunks)
        deduped: list[Any] = []
        seen_kb: set[tuple[str, int, int]] = set()
        for chunk in kb_chunks:
            key = (getattr(chunk, "filename", ""), getattr(chunk, "page_num", 0), getattr(chunk, "chunk_index", 0))
            if key in seen_kb:
                continue
            seen_kb.add(key)
            deduped.append(chunk)
        kb_chunks = deduped[:8]
    except Exception as exc:
        kb_queries.append(f"KB retrieval failed: {exc}")

    kb_sources = _kb_chunks_to_sources(kb_chunks)
    unified_sources = _merge_source_bases(verification["sources_accepted"], kb_sources)
    artifacts["stages"]["knowledge_base_search"] = {
        "queries": kb_queries,
        "kb_chunks": [_serialize_kb_chunk(chunk) for chunk in kb_chunks],
    }
    artifacts["stages"]["evidence_fusion"] = {
        "merged_source_count": len(unified_sources),
        "deduplicated": True,
        "priority_order": [
            "peer-reviewed journals",
            "conference papers",
            "technical books",
            "official standards",
            "government publications",
            "university repositories",
            "patents",
            "manufacturer documentation",
            "uploaded knowledge base",
            "general model knowledge",
        ],
    }
    artifacts["kb_chunks"] = [_serialize_kb_chunk(chunk) for chunk in kb_chunks]
    artifacts["kb_sources"] = kb_sources
    artifacts["unified_sources"] = unified_sources
    artifacts["source_transparency"] = {
        "academic_sources_searched": ["Crossref", "PubMed", "arXiv"],
        "official_sources_searched": ["NIST", "IAEA", "IEC", "ISO", "ASTM", "ICRP", "ICRU", "ICAO", "ECAC", "TSA", "DHS"],
        "manufacturer_sources_searched": ["Rapiscan Systems", "Smiths Detection", "Nuctech", "Leidos", "Astrophysics Inc."],
        "knowledge_base_queries": kb_queries,
        "knowledge_base_contribution": {
            "documents_retrieved": len({getattr(chunk, 'filename', '') for chunk in kb_chunks}),
            "chunks_retrieved": len(kb_chunks),
            "supplementary_role": "Uploaded documents were used to enrich implementation details and local context only.",
        },
        "external_evidence_contribution": {
            "external_sources_found": len(verification["sources_found"]),
            "external_sources_accepted": len(verification["sources_accepted"]),
            "external_sources_rejected": len(verification["sources_rejected"]),
            "supplementary_kb_chunks": len(kb_chunks),
        },
    }
    update_research_pipeline_run(
        db,
        run_id,
        artifacts=artifacts,
        status="running",
        current_stage="source_verification",
        normalized_topic=normalized["normalized_topic"],
    )

    evidence_rows = extract_structured_evidence(unified_sources, normalized["normalized_topic"], keyword_stage["search_keywords"])
    evidence_database = [_evidence_database_row(src, normalized["normalized_topic"]) for src in unified_sources]
    artifacts["stages"]["evidence_extraction"] = {"evidence_extracted": evidence_rows}
    artifacts["stages"]["evidence_database"] = {"evidence_database": evidence_database}
    artifacts["evidence_extracted"] = evidence_rows
    artifacts["evidence_database"] = evidence_database
    update_research_pipeline_run(
        db,
        run_id,
        artifacts=artifacts,
        status="running",
        current_stage="evidence_fusion",
        normalized_topic=normalized["normalized_topic"],
    )

    literature_matrix = build_literature_matrix(unified_sources, evidence_rows)
    comparison_matrix = [
        {
            "citation_key": row.get("citation_key", ""),
            "source_type": row.get("source_type", ""),
            "year": row.get("year", ""),
            "method_focus": row.get("method_focus", ""),
            "core_contribution": row.get("core_contribution", ""),
            "support_level": row.get("support_level", ""),
        }
        for row in literature_matrix
    ]
    scientific_analysis = build_scientific_analysis(unified_sources, literature_matrix, [])
    artifacts["stages"]["literature_matrix"] = {"literature_matrix": literature_matrix}
    artifacts["stages"]["comparison_matrix"] = {"comparison_matrix": comparison_matrix}
    artifacts["stages"]["literature_analysis"] = {
        "literature_matrix": literature_matrix,
        "technology_evolution_timeline": scientific_analysis["technology_evolution_timeline"],
        "method_comparison": scientific_analysis["method_comparison"],
        "dataset_comparison": scientific_analysis["dataset_comparison"],
        "algorithm_comparison": scientific_analysis["algorithm_comparison"],
        "standard_comparison": scientific_analysis["standard_comparison"],
        "patent_comparison": scientific_analysis["patent_comparison"],
    }
    artifacts["literature_matrix"] = literature_matrix
    artifacts["comparison_matrix"] = comparison_matrix
    update_research_pipeline_run(
        db,
        run_id,
        artifacts=artifacts,
        status="running",
        current_stage="literature_analysis",
        normalized_topic=normalized["normalized_topic"],
    )

    gap_matrix = build_research_gap_matrix(normalized["normalized_topic"], keyword_stage["search_keywords"], literature_matrix)
    scientific_analysis = build_scientific_analysis(unified_sources, literature_matrix, gap_matrix)
    artifacts["stages"]["research_gap_matrix"] = {"research_gap_matrix": gap_matrix}
    artifacts["stages"]["research_gap_analysis"] = {
        "research_gap_matrix": gap_matrix,
        "strengths": scientific_analysis["strengths"],
        "weaknesses": scientific_analysis["weaknesses"],
        "open_research_questions": scientific_analysis["open_research_questions"],
    }
    artifacts["research_gap_matrix"] = gap_matrix
    artifacts["scientific_analysis"] = scientific_analysis
    update_research_pipeline_run(
        db,
        run_id,
        artifacts=artifacts,
        status="running",
        current_stage="research_gap_analysis",
        normalized_topic=normalized["normalized_topic"],
    )

    outline = build_phase1_outline(mode, normalized["normalized_topic"], keyword_stage["search_keywords"], literature_matrix, gap_matrix)
    artifacts["stages"]["paper_planning"] = {"final_outline": outline}
    artifacts["stages"]["outline"] = {"final_outline": outline}
    artifacts["final_outline"] = outline

    completed = update_research_pipeline_run(
        db,
        run_id,
        artifacts=artifacts,
        status="complete",
        current_stage="paper_planning",
        normalized_topic=normalized["normalized_topic"],
    )

    research_meta_cache.set(cache_key, _clone_json(artifacts))

    return {
        "run": completed,
        "artifacts": artifacts,
    }


def research_pipeline_run_to_dict(run) -> dict[str, Any]:
    return {
        "id": run.id,
        "user_id": run.user_id,
        "mode": run.mode,
        "mode_label": RESEARCH_MODE_LABELS.get(run.mode, run.mode),
        "topic": run.topic,
        "normalized_topic": run.normalized_topic,
        "status": run.status,
        "current_stage": run.current_stage,
        "artifacts": run.artifacts or {},
        "last_error": run.last_error,
        "created_at": run.created_at.isoformat(),
        "updated_at": run.updated_at.isoformat(),
    }


_DEPTH_PROFILES: dict[str, dict[str, int]] = {
    "research_brief": {"total": 2600, "abstract": 180, "problem": 220, "background": 260, "rq": 180, "scope": 140, "contrib": 220, "literature": 420, "gap": 320, "foundation": 180, "technical": 240, "method": 320, "dataset": 180, "experiment": 180, "model": 200, "workflow": 180, "validation": 140, "expected": 160, "discussion": 220, "comparison": 140, "implementation": 180, "hardware": 120, "operational": 120, "safety": 120, "limitations": 180, "reproducibility": 120, "future": 120, "conclusion": 120},
    "technical_paper": {"total": 4800, "abstract": 220, "problem": 320, "background": 380, "rq": 220, "scope": 180, "contrib": 320, "literature": 780, "gap": 420, "foundation": 280, "technical": 420, "method": 720, "dataset": 300, "experiment": 340, "model": 360, "workflow": 300, "validation": 280, "expected": 240, "discussion": 420, "comparison": 300, "implementation": 360, "hardware": 220, "operational": 220, "safety": 220, "limitations": 280, "reproducibility": 220, "future": 220, "conclusion": 160},
    "full_journal_paper": {"total": 8600, "abstract": 260, "problem": 420, "background": 520, "rq": 260, "scope": 220, "contrib": 420, "literature": 1200, "gap": 680, "foundation": 420, "technical": 560, "method": 980, "dataset": 480, "experiment": 560, "model": 560, "workflow": 420, "validation": 420, "expected": 320, "discussion": 620, "comparison": 420, "implementation": 520, "hardware": 300, "operational": 300, "safety": 300, "limitations": 380, "reproducibility": 300, "future": 280, "conclusion": 220},
    "systematic_review": {"total": 9800, "abstract": 280, "problem": 300, "background": 420, "rq": 260, "scope": 220, "contrib": 220, "literature": 1800, "gap": 800, "foundation": 300, "technical": 340, "method": 900, "dataset": 260, "experiment": 260, "model": 260, "workflow": 240, "validation": 360, "expected": 200, "discussion": 760, "comparison": 500, "implementation": 260, "hardware": 160, "operational": 180, "safety": 160, "limitations": 380, "reproducibility": 280, "future": 260, "conclusion": 200},
    "technical_dossier": {"total": 14000, "abstract": 320, "problem": 520, "background": 700, "rq": 320, "scope": 260, "contrib": 520, "literature": 2000, "gap": 1000, "foundation": 500, "technical": 900, "method": 1200, "dataset": 700, "experiment": 800, "model": 800, "workflow": 560, "validation": 520, "expected": 380, "discussion": 980, "comparison": 700, "implementation": 760, "hardware": 420, "operational": 420, "safety": 420, "limitations": 520, "reproducibility": 420, "future": 360, "conclusion": 280},
}


_SECTION_ORDER = [
    ("abstract", "Abstract"),
    ("keywords", "Keywords"),
    ("problem", "Research Problem"),
    ("background", "Background"),
    ("rq", "Research Questions and Objectives"),
    ("scope", "Scope"),
    ("contrib", "Novel Contributions"),
    ("literature", "Detailed Literature Review"),
    ("gap", "Research-Gap Analysis"),
    ("foundation", "Theoretical Foundation"),
    ("technical", "Technical Explanation"),
    ("method", "Methodology"),
    ("dataset", "Dataset or Data-Collection Plan"),
    ("experiment", "Experimental Setup or Experimental Plan"),
    ("model", "Mathematical Model"),
    ("workflow", "Algorithm or Workflow"),
    ("validation", "Validation Protocol"),
    ("expected", "Results or Expected Outcomes"),
    ("discussion", "Discussion"),
    ("comparison", "Comparison with Previous Work"),
    ("implementation", "Practical Implementation"),
    ("hardware", "Required Hardware and Software"),
    ("operational", "Operational Considerations"),
    ("safety", "Safety and Regulatory Considerations"),
    ("limitations", "Limitations and Threats to Validity"),
    ("reproducibility", "Reproducibility Plan"),
    ("future", "Future Work"),
    ("conclusion", "Conclusion"),
]


def _target_depth_profile(depth: str | None, mode: str, override_word_count: int | None) -> dict[str, int]:
    key = (depth or "technical_paper").strip().lower()
    if key not in _DEPTH_PROFILES:
        key = "technical_paper"
    profile = dict(_DEPTH_PROFILES[key])
    if mode == "paper_ieee" and profile["total"] < 4000:
        profile = dict(_DEPTH_PROFILES["technical_paper"])
    if override_word_count and override_word_count > 0:
        profile["total"] = override_word_count
    return profile


def _section_word_target(profile: dict[str, int], key: str) -> int:
    return max(80, int(profile.get(key, max(100, profile["total"] // 20))))


def _classify_document_type(mode: str, accepted_sources: list[dict[str, Any]], has_real_results: bool) -> str:
    if mode == "literature_review":
        return "Systematic Review"
    if mode == "experiment_plan":
        return "Experimental Plan"
    if mode == "technical_report":
        return "Technical Review"
    if mode == "patent_analysis":
        return "Concept Paper"
    if has_real_results:
        return "Original Research Paper"
    if mode == "research_gaps":
        return "Research Proposal"
    if len(accepted_sources) >= 6:
        return "Technical Review"
    return "Concept Paper"


def _table_md(headers: list[str], rows: list[list[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    sep = "|" + "|".join(["---"] * len(headers)) + "|"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, sep, *body])


def _render_reference_entries(accepted_sources: list[dict[str, Any]], kb_chunks: list[Any]) -> str:
    lines = ["## References"]
    if not accepted_sources:
        lines.append("_No verified references were retained from the search stage._")
        return "\n\n".join(lines)

    for idx, source in enumerate(accepted_sources, 1):
        parts = [source.get("authors", "").strip(), source.get("title", "").strip(), source.get("publisher", "").strip(), source.get("year", "").strip()]
        citation = ". ".join([p for p in parts if p])
        doi = source.get("doi", "").strip()
        url = source.get("url", "").strip()
        lines.append(f"[{idx}] {citation}.")
        if doi:
            lines.append(f"DOI: {doi}")
        if url:
            lines.append(f"URL: {url}")
        lines.append("")

    if kb_chunks:
        seen: set[str] = set()
        lines.append("## Knowledge Base Sources")
        for chunk in kb_chunks:
            if isinstance(chunk, dict):
                fname = chunk.get("filename") or chunk.get("title") or "Unknown"
                page = chunk.get("page_num")
            else:
                fname = getattr(chunk, "filename", None) or "Unknown"
                page = getattr(chunk, "page_num", None)
            if fname in seen:
                continue
            seen.add(fname)
            meta = f"Page {page}" if page else "Internal knowledge base"
            lines.append(f"- {fname} ({meta})")

    return "\n".join(lines).strip()


def _build_literature_matrix_section(literature_matrix: list[dict[str, Any]]) -> str:
    rows = []
    for row in literature_matrix:
        rows.append([
            row.get("citation_key", ""),
            row.get("title", "")[:120],
            row.get("year", ""),
            row.get("source_type", ""),
            row.get("method_focus", ""),
            row.get("evidence_type", ""),
            row.get("support_level", ""),
        ])
    return _table_md([
        "Key", "Title", "Year", "Type", "Method Focus", "Evidence Type", "Support",
    ], rows)


def _build_gap_matrix_section(gap_matrix: list[dict[str, Any]]) -> str:
    rows = []
    for row in gap_matrix:
        rows.append([
            row.get("gap", "")[:90],
            row.get("priority", ""),
            row.get("why_it_matters", "")[:100],
            row.get("recommended_next_step", "")[:100],
        ])
    return _table_md(["Gap", "Priority", "Why It Matters", "Next Step"], rows)


def _build_dataset_plan_section(normalized_topic: str, depth: str, has_real_results: bool) -> str:
    if has_real_results:
        return (
            "- Measured or experimentally collected dataset: describe only if available.\n"
            "- Retain the exact acquisition conditions, sample counts, splits, and calibration steps.\n"
            "- Include all preprocessing, annotation, and quality-control procedures."
        )
    return (
        f"- Proposed dataset focus: {normalized_topic}.\n"
        "- Use a mixed corpus of verified academic sources, standards, and engineering documentation to define the research boundary.\n"
        "- For any future study, specify source documents, scan geometry, detector type, data format, and annotation protocol before acquisition.\n"
        f"- Output depth profile: {depth}."
    )


def _build_equipment_plan_section() -> str:
    return _table_md(
        ["Category", "Specification / Planning Item", "Status"],
        [
            ["X-ray source", "High-energy cargo or vehicle inspection system; specify kVp / MeV only when known", "planned"],
            ["Detector array", "Dual-energy / multi-energy detector chain, scintillator or photon-counting detector", "planned"],
            ["Compute", "Workstation or edge device for reconstruction, analysis, and report generation", "planned"],
            ["Software", "Acquisition, reconstruction, analysis, and document generation stack", "planned"],
        ],
    )


def _build_validation_criteria_section(has_real_results: bool) -> str:
    rows = [
        ["Source verification", "All references are retrievable and cited with title, authors, year, venue, DOI, URL", "mandatory"],
        ["Evidence traceability", "Every major claim maps to a verified source key or a clearly labeled hypothesis", "mandatory"],
        ["Methodology completeness", "Hardware, software, workflow, data plan, and evaluation criteria are explicit", "mandatory"],
        ["Unsupported claims", "No fabricated datasets, experiments, metrics, or results", "mandatory"],
    ]
    if has_real_results:
        rows.append(["Measured results", "Include measured values with uncertainty and conditions", "only when available"])
    else:
        rows.append(["Expected outcomes", "Use target / hypothetical values only, labeled clearly", "required"])
    return _table_md(["Criterion", "Requirement", "Status"], rows)


def _build_limitations_section(has_real_results: bool) -> str:
    rows = [
        ["No fabricated results", "If no experiment exists, report expected outcomes only"],
        ["No fake datasets", "Do not name a dataset unless it is actually available"],
        ["No unverifiable references", "Exclude URLs, DOI numbers, and citations that were not verified"],
        ["No original-research claim", "Do not classify as original research without real data or experiments"],
    ]
    if has_real_results:
        rows.append(["Real-data limitations", "Report instrument drift, calibration limits, and sample-size limitations honestly"])
    return _table_md(["Limitation", "Rule"], rows)


def _build_implementation_stages_section() -> str:
    return _table_md(
        ["Stage", "What Happens", "Output"],
        [
            ["1", "Normalize topic and build verified search strategy", "search keywords + synonyms"],
            ["2", "Retrieve and verify sources", "accepted/rejected source lists"],
            ["3", "Extract structured evidence", "evidence matrix"],
            ["4", "Build gap analysis", "research-gap matrix"],
            ["5", "Draft sections separately", "paper sections"],
            ["6", "Assemble and export", "DOCX/PDF"],
        ],
    )


def _build_source_summary_rows(accepted_sources: list[dict[str, Any]]) -> list[list[str]]:
    rows: list[list[str]] = []
    for src in accepted_sources:
        rows.append([
            src.get("citation_key", ""),
            src.get("title", "")[:110],
            src.get("year", ""),
            src.get("source_type", ""),
            (src.get("abstract", "") or src.get("verified_by", ""))[:120],
        ])
    return rows


def _build_architecture_diagram_section(topic: str, run_id: str = "") -> str:
    from api.utils.figure_renderer import render_flow_diagram
    path = render_flow_diagram(
        "Implementation Architecture",
        [
            "External Academic + Standards Sources",
            "Source Verification Engine",
            "Unified Evidence Base",
            "Literature + Gap Matrices",
            "Section-by-Section Drafting",
            "Publication Export (DOCX/PDF)",
        ],
        run_id, "architecture_diagram",
    )
    return (
        "## Implementation Architecture Diagram\n\n"
        f"![Implementation architecture diagram]({path})\n\n"
        f"This architecture ensures that the primary evidence chain for {topic} starts from verified external literature and standards, while uploaded documents are used only as supplementary implementation context."
    )


def _build_workflow_diagram_section(run_id: str = "") -> str:
    from api.utils.figure_renderer import render_flow_diagram
    path = render_flow_diagram(
        "Research Workflow",
        [
            "Topic Normalization + Query Expansion",
            "Multi-Provider External Retrieval",
            "Deduplication + Quality Ranking",
            "Evidence Extraction",
            "Section-by-Section Drafting",
            "Publication-Readiness Gate",
        ],
        run_id, "workflow_diagram",
    )
    return (
        "## Research Workflow Diagram\n\n"
        f"![Research workflow diagram]({path})\n\n"
        "The workflow enforces deep multi-provider retrieval and evidence fusion before writing."
    )


def _build_critical_synthesis_section(literature_matrix: list[dict[str, Any]]) -> str:
    if not literature_matrix:
        return "## Critical Comparative Synthesis\n\nNo verified literature matrix entries were available for comparative synthesis."

    by_type = Counter(row.get("source_type", "unknown") for row in literature_matrix)
    by_focus = Counter(row.get("method_focus", "unknown") for row in literature_matrix)
    strongest_type = by_type.most_common(1)[0][0]
    strongest_focus = by_focus.most_common(1)[0][0]

    rows = [[k, str(v)] for k, v in by_type.items()]
    focus_rows = [[k, str(v)] for k, v in by_focus.items()]

    return (
        "## Critical Comparative Synthesis\n\n"
        "The evidence base was compared across source type, methodological focus, and support strength. "
        "The objective is synthesis and critical comparison rather than paper-by-paper summary.\n\n"
        f"Dominant source type: **{strongest_type}**. Dominant methodological focus: **{strongest_focus}**.\n\n"
        "### Source-Type Distribution\n\n"
        + _table_md(["Source Type", "Count"], rows)
        + "\n\n### Method-Focus Distribution\n\n"
        + _table_md(["Method Focus", "Count"], focus_rows)
        + "\n\n"
        "Interpretation: claims are weighted toward high-priority evidence classes first, and lower-priority sources are used only for implementation context or supplementary clarification."
    )


_LATEX_CAPTURE_RE = re.compile(r"\$\$(.+?)\$\$|\\\((.+?)\\\)|\\\[(.+?)\\\]|\$([^$\n]{1,300})\$", re.DOTALL)


def _extract_equations(content: str) -> list[str]:
    equations: list[str] = []
    for match in _LATEX_CAPTURE_RE.finditer(content or ""):
        expr = next((g for g in match.groups() if g), "").strip()
        expr = re.sub(r"\s+", " ", expr)
        if expr and expr not in equations:
            equations.append(expr)
    return equations[:12]


def _explain_expression(expr: str) -> tuple[str, str]:
    cleaned = re.sub(r"\\[a-zA-Z]+", " ", expr)
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9_]*", cleaned)
    vars_unique: list[str] = []
    for token in tokens:
        if token.lower() in {"sin", "cos", "tan", "exp", "log", "min", "max", "arg", "det", "sum", "prod"}:
            continue
        if token not in vars_unique:
            vars_unique.append(token)
    variables = ", ".join(vars_unique[:8]) if vars_unique else "Variables should be defined in context"
    explanation = (
        "Engineering implication: this equation should be interpreted together with detector operating range, acquisition geometry, and uncertainty assumptions before deployment decisions are made."
    )
    return variables, explanation


def _build_equation_explanation_section(content: str) -> str:
    equations = _extract_equations(content)
    if not equations:
        return (
            "## Equation and Variable Explanations\n\n"
            "No explicit LaTeX equations were detected in this draft. Any mathematical relation introduced in a later revision must include variable definitions, physical meaning, and practical implications."
        )

    rows: list[list[str]] = []
    for index, expr in enumerate(equations, 1):
        variables, implication = _explain_expression(expr)
        rows.append([
            f"Eq.{index}: {expr[:80]}",
            variables,
            implication,
        ])
    return "## Equation and Variable Explanations\n\n" + _table_md(["Equation", "Variables", "Engineering and Practical Implication"], rows)


def _enforce_expected_outcomes_only(content: str, has_real_results: bool) -> str:
    if has_real_results:
        return content
    updated = re.sub(r"(?im)^#{2,3}\s+results\b", "### Expected Outcomes (Proposed)", content)
    notice = (
        "## Experimental Integrity Notice\n\n"
        "This document does not claim completed experimental measurements. "
        "Sections are written as proposed methodology, experimental plan, expected outcomes, and validation strategy."
    )
    if "## Experimental Integrity Notice" not in updated:
        updated = updated + "\n\n" + notice
    return updated


def _ensure_claim_citations(content: str, accepted_sources: list[dict[str, Any]]) -> str:
    citation_key = ""
    for source in accepted_sources:
        if source.get("source_type") != "knowledge_base" and source.get("citation_key"):
            citation_key = source["citation_key"]
            break
    if not citation_key:
        return content

    output_lines: list[str] = []
    for line in content.splitlines():
        stripped = line.strip()
        if not stripped:
            output_lines.append(line)
            continue
        if stripped.startswith("#") or stripped.startswith("|") or stripped.startswith("```"):
            output_lines.append(line)
            continue
        if stripped.startswith("-") or stripped.startswith("*") or re.match(r"^\d+\.\s", stripped):
            output_lines.append(line)
            continue
        if "[" in stripped and "]" in stripped:
            output_lines.append(line)
            continue
        if len(stripped) >= 100:
            output_lines.append(f"{line} [{citation_key}]")
        else:
            output_lines.append(line)
    return "\n".join(output_lines)


async def _draft_section_with_provider(
    provider,
    *,
    section_title: str,
    target_words: int,
    document_type: str,
    paper_title: str,
    normalized_topic: str,
    mode: str,
    depth: str,
    artifacts: dict[str, Any],
    section_key: str,
) -> str:
    raise RuntimeError("Template fallback generator is disabled. Use evidence-only section assembly.")


def _is_official_url(url: str) -> bool:
    if not url:
        return False
    parsed = url.strip().lower()
    if not (parsed.startswith("http://") or parsed.startswith("https://")):
        return False
    blocked = ("example.com", "localhost", "127.0.0.1")
    return not any(host in parsed for host in blocked)


def _is_verified_reference_source(source: dict[str, Any]) -> bool:
    doi = str(source.get("doi") or "").strip()
    url = str(source.get("url") or "").strip()
    return bool(_DOI_RE.match(doi)) or _is_official_url(url)


_DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9]+$", re.IGNORECASE)
_CITATION_RE = re.compile(r"\[([A-Z]+-\d+)\]")


def _has_verified_doi(source: dict[str, Any]) -> bool:
    doi = str(source.get("doi") or "").strip()
    if not doi or not _DOI_RE.match(doi):
        return False
    verifier = str(source.get("verified_by") or "").lower()
    url = str(source.get("url") or "").lower()
    return ("doi" in verifier) or ("doi.org" in url)


def _build_evidence_objects(artifacts: dict[str, Any]) -> list[dict[str, Any]]:
    base = artifacts.get("unified_sources", artifacts.get("sources_accepted", [])) or []
    evidence: list[dict[str, Any]] = []
    for src in base:
        key = str(src.get("citation_key") or "").strip()
        if not key:
            continue
        abstract = str(src.get("abstract") or "").strip()
        title = str(src.get("title") or "").strip()
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", abstract) if s.strip()]
        key_findings = sentences[:2] if sentences else ([title] if title else [])
        limitations = [s for s in sentences if re.search(r"limitation|constraint|challenge|uncertainty", s, flags=re.IGNORECASE)]
        if not _is_verified_reference_source(src):
            continue
        evidence.append({
            "citation_key": key,
            "title": title,
            "authors": str(src.get("authors") or "").strip(),
            "year": str(src.get("year") or "").strip(),
            "abstract": abstract,
            "key_findings": key_findings,
            "limitations": limitations or ["No explicit limitation reported in abstract."],
            "doi": str(src.get("doi") or "").strip(),
            "url": str(src.get("url") or "").strip(),
            "source_type": str(src.get("source_type") or "").strip(),
            "verified_doi": _has_verified_doi(src),
            # Carried through from _source_to_json / verify_sources so the
            # publication-readiness gate can score real reference quality
            # (peer-review ratio, live DOI verification) rather than
            # re-guessing it from rendered text.
            "provider": str(src.get("provider") or "").strip(),
            "citation_count": src.get("citation_count"),
            "is_peer_reviewed": src.get("is_peer_reviewed"),
            "doi_verified": bool(src.get("doi_verified", False)),
            "quality_score": src.get("quality_score", 0.0),
        })
    return evidence


def _cluster_evidence_by_topic(evidence: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    clusters: dict[str, list[dict[str, Any]]] = {
        "detector physics": [],
        "algorithmic methods": [],
        "operational deployment": [],
        "standards and regulation": [],
        "industrial implementation": [],
    }
    for ev in evidence:
        blob = f"{ev['title']} {ev['abstract']}".lower()
        matched = False
        if re.search(r"attenuation|detector|photon|spectral|scintillator|counting", blob):
            clusters["detector physics"].append(ev)
            matched = True
        if re.search(r"algorithm|model|learning|classification|segmentation|inference", blob):
            clusters["algorithmic methods"].append(ev)
            matched = True
        if re.search(r"cargo|checkpoint|throughput|screening|deployment|operator", blob):
            clusters["operational deployment"].append(ev)
            matched = True
        if ev.get("source_type") in {"standard", "regulator"} or re.search(r"iso|iec|nist|iaea|astm|standard", blob):
            clusters["standards and regulation"].append(ev)
            matched = True
        if ev.get("source_type") == "manufacturer" or re.search(r"manufacturer|system|platform|commercial", blob):
            clusters["industrial implementation"].append(ev)
            matched = True
        if not matched:
            clusters["operational deployment"].append(ev)
    return {k: v for k, v in clusters.items() if v}


def _cite_keys(items: list[dict[str, Any]], limit: int = 3) -> str:
    keys = [it.get("citation_key", "") for it in items[:limit] if it.get("citation_key")]
    return " ".join(f"[{k}]" for k in keys)


async def _llm_write_section(
    provider,
    *,
    title: str,
    section_role: str,
    topic: str,
    evidence: list[dict[str, Any]],
) -> "str | None":
    """Ask the active AI provider to write genuine academic prose for one
    section, strictly grounded in the given evidence.

    Returns None — never raises — if the provider is unavailable, the call
    fails, or the output would violate the same citation-integrity rules
    _validate_scientific_manuscript enforces (only cite provided keys, every
    substantive paragraph cited). Callers must fall back to
    _section_from_evidence() in that case. This is what actually replaces the
    deterministic evidence-sentence templater with real synthesis — the
    template path remains as the safety net, not the default.
    """
    if provider is None or not evidence:
        return None

    allowed_keys = {ev.get("citation_key", "") for ev in evidence if ev.get("citation_key")}
    if not allowed_keys:
        return None

    evidence_brief = []
    for ev in evidence[:6]:
        findings = ev.get("key_findings") or []
        finding = findings[0] if findings else ev.get("title", "")
        limitations = ev.get("limitations") or []
        limitation = limitations[0] if limitations else ""
        entry = f"[{ev['citation_key']}] {ev.get('title', '')} ({ev.get('year') or 'n.d.'}): {finding}"
        if limitation:
            entry += f" Limitation noted: {limitation}"
        evidence_brief.append(entry)

    system_prompt = (
        "You are an academic technical writer producing one section of an IEEE-style "
        "research paper about X-ray screening and detection technology. Write formal, "
        "precise scientific prose — genuine analysis and synthesis across sources, "
        "never a bare restatement of one source's finding.\n\n"
        "STRICT RULES:\n"
        f"1. You may ONLY cite these exact keys, in square brackets: {', '.join(sorted(allowed_keys))}. "
        "Never invent a citation key or reference not in this list.\n"
        "2. Every sentence that states a claim, finding, or comparison must end with at least one "
        "citation from the allowed list, e.g. \"X improves Y [SRC-1].\" When citing more than one "
        "source for the same sentence, use a separate bracket per key — \"[SRC-1] [SRC-2]\" — "
        "never combine keys inside one bracket like \"[SRC-1, SRC-2]\".\n"
        "3. Do not copy a source's finding sentence verbatim — compare, interpret, and connect "
        "sources instead of listing them one after another.\n"
        "4. Output 2-4 sentences as one or two short paragraphs. No headings, no bullet points, "
        "no markdown, no preamble such as \"Sure, here is...\" — output ONLY the prose itself."
    )
    user_prompt = (
        f"Paper topic: {topic}\n"
        f"Section: {title} — {section_role}\n\n"
        "Verified evidence available for this section (cite only these keys):\n"
        + "\n".join(evidence_brief)
    )

    try:
        raw = await provider.chat(
            [{"role": "user", "content": user_prompt}],
            system_prompt=system_prompt,
            max_tokens=16384,
        )
    except Exception:
        return None

    text = (raw or "").strip()
    if not text:
        return None
    # Strip accidental markdown headers/code fences some models add anyway.
    text = re.sub(r"^#{1,4}\s*.*(\n|$)", "", text).strip()
    text = re.sub(r"^```\w*\n|\n?```$", "", text).strip()
    # Normalize combined-bracket citations ("[SRC-1, SRC-3]") into the paper's
    # single-key-per-bracket style ("[SRC-1] [SRC-3]") — the prompt asks for
    # the latter but models don't always comply, and _CITATION_RE (and
    # _validate_scientific_manuscript downstream) only recognizes one key per
    # bracket, so leaving this unnormalized just silently drops the citation.
    text = re.sub(
        r"\[([A-Z]+-\d+(?:\s*,\s*[A-Z]+-\d+)+)\]",
        lambda m: " ".join(f"[{k.strip()}]" for k in m.group(1).split(",")),
        text,
    )

    cited = set(_CITATION_RE.findall(text))
    if not cited or not cited.issubset(allowed_keys):
        return None
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    if not paragraphs or any(not _CITATION_RE.search(p) for p in paragraphs):
        return None

    return f"## {title}\n\n" + "\n\n".join(paragraphs)


def _section_from_evidence(title: str, evidence: list[dict[str, Any]], objective: str) -> str:
    if not evidence:
        return ""
    lines = [f"## {title}"]
    top = evidence[:3]
    for ev in top:
        finding = ev.get("key_findings", [ev.get("title", "")])[0]
        limitation = ev.get("limitations", [""])[0]
        cite = _cite_keys([ev], 1)
        lines.append(
            f"{objective}: {finding} {cite}. Reported limitation: {limitation} {cite}."
        )
    if len(evidence) > 1:
        synth_cite = _cite_keys(evidence, 3)
        lines.append(
            f"Cross-source synthesis indicates converging evidence across {len(evidence)} records with remaining methodological heterogeneity {synth_cite}."
        )
    return "\n\n".join(lines)


def _build_comparison_matrix(evidence: list[dict[str, Any]]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for ev in evidence:
        rows.append({
            "citation_key": ev.get("citation_key", ""),
            "source_type": ev.get("source_type", ""),
            "year": ev.get("year", ""),
            "key_finding": (ev.get("key_findings", [""])[0] or "")[:180],
            "limitation": (ev.get("limitations", [""])[0] or "")[:140],
        })
    return rows


def _build_tables_section(literature_matrix: list[dict[str, Any]], comparison_matrix: list[dict[str, str]], gap_matrix: list[dict[str, Any]]) -> str:
    if not literature_matrix and not comparison_matrix and not gap_matrix:
        return ""
    lines = ["## Tables"]
    if literature_matrix:
        lines.append("### Literature Matrix")
        lit_rows = [[r.get("citation_key", ""), r.get("source_type", ""), r.get("year", ""), r.get("method_focus", ""), r.get("support_level", "")] for r in literature_matrix[:20]]
        lines.append(_table_md(["Key", "Type", "Year", "Method Focus", "Support"], lit_rows))
    if comparison_matrix:
        lines.append("### Comparison Matrix")
        cmp_rows = [[r.get("citation_key", ""), r.get("source_type", ""), r.get("year", ""), r.get("key_finding", ""), r.get("limitation", "")] for r in comparison_matrix[:20]]
        lines.append(_table_md(["Key", "Type", "Year", "Key Finding", "Limitation"], cmp_rows))
    if gap_matrix:
        lines.append("### Gap Matrix")
        gap_rows = [[g.get("gap", "")[:100], g.get("priority", ""), g.get("recommended_next_step", "")[:110]] for g in gap_matrix[:12]]
        lines.append(_table_md(["Gap", "Priority", "Recommended Next Step"], gap_rows))
    return "\n\n".join(lines)


def _build_figures_section(evidence: list[dict[str, Any]], topic: str = "", run_id: str = "") -> str:
    if not evidence:
        return ""
    from api.utils.figure_renderer import render_source_type_pie, render_year_bar, render_flow_diagram

    by_type = Counter(ev.get("source_type", "unknown") for ev in evidence)
    by_year = Counter((ev.get("year") or "n.d.") for ev in evidence if (ev.get("year") or "").strip().isdigit())
    cites = _cite_keys(evidence, 4)

    # Each figure is a single markdown image line only — the image-embedding
    # code (docgen.py's _add_body_docx / _md_to_flowables, export.py's
    # _md_to_html) already renders the alt text as the figure's caption
    # underneath it, so a separate leading caption line would duplicate it.
    pie_path = render_source_type_pie(dict(by_type), run_id)
    parts = [
        "## Figures\n",
        f"![Figure 1. Source-type distribution derived from verified evidence.]({pie_path})",
    ]
    if by_year:
        bar_path = render_year_bar(dict(by_year), run_id)
        parts.append(f"![Figure 2. Publication-year distribution derived from verified evidence.]({bar_path})")

    pipeline_path = render_flow_diagram(
        "AI-Enabled X-Ray Screening Pipeline",
        ["Image Acquisition", "Preprocessing", "AI-Based Detection", "Decision Support", "Operator Review"],
        run_id, "pipeline_figure", horizontal=True,
    )
    fig_n = 3 if by_year else 2
    parts.append(
        f"![Figure {fig_n}. Data flow from X-ray detector acquisition to operator decision support.]({pipeline_path})"
    )
    parts.append(f"All figures above are rendered directly from retrieved evidence metadata {cites}.")
    return "\n\n".join(parts)


def _build_equations_section(evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return ""
    corpus = " ".join(f"{e.get('title', '')} {e.get('abstract', '')}" for e in evidence).lower()
    equations: list[tuple[str, str, str]] = []
    if "attenuation" in corpus or "beer" in corpus:
        equations.append(("E1", "I = I_0 e^{-\\mu x}", "Attenuation model for transmitted intensity"))
    if "snr" in corpus or "noise" in corpus:
        equations.append(("E2", "SNR = \\mu_s / \\sigma_n", "Signal-to-noise characterization"))
    if "dqe" in corpus or "mtf" in corpus:
        equations.append(("E3", "DQE(f) = SNR_{out}(f)^2 / SNR_{in}(f)^2", "Frequency-dependent detector efficiency"))
    if not equations:
        return ""
    cites = _cite_keys(evidence, 3)
    rows = [[num, expr, meaning + f" {cites}"] for num, expr, meaning in equations]
    return "## Equations\n\n" + _table_md(["Equation", "Expression", "Evidence-Supported Meaning"], rows)


def _render_dual_style_references(cited: list[dict[str, Any]]) -> str:
    lines = ["## References"]
    for idx, ev in enumerate(cited, 1):
        author_text = ev.get("authors") or "Unknown author"
        year_text = ev.get("year") or "n.d."
        doi_text = ev.get("doi") or ""
        url_text = ev.get("url") or ""
        line = f"[{idx}] {author_text}, \"{ev.get('title', 'Untitled source')}\", {year_text}."
        if doi_text:
            line += f" DOI: {doi_text}."
        if url_text:
            line += f" URL: {url_text}"
        lines.append(line.strip())
    return "\n".join(lines)


_BARE_CITATION_KEY_RE = re.compile(r"\b([A-Z]+-\d+)\b")


def _renumber_citations(content: str, referencable: list[dict[str, Any]]) -> str:
    """Rewrite every internal ``SRC-N``/``KB-N`` citation key to the final
    numeric form matching `_render_dual_style_references`'s positional
    numbering — in-text ``[SRC-1]`` becomes ``[1]``, and a bare ``SRC-1``
    inside a Literature/Comparison Matrix "Key" table cell becomes plain
    ``1`` (no brackets, since it isn't an in-text citation there).

    Without this, body prose cites "[SRC-1]" while the reference list shows
    "[1]" for the same source, and matrix tables display the raw internal
    key — both are exactly the placeholder leakage the acceptance tests ban.
    """
    key_to_index = {
        ev.get("citation_key", ""): idx
        for idx, ev in enumerate(referencable, 1)
        if ev.get("citation_key")
    }

    def _replace_bracketed(match: re.Match) -> str:
        idx = key_to_index.get(match.group(1))
        return f"[{idx}]" if idx else match.group(0)

    content = _CITATION_RE.sub(_replace_bracketed, content)

    def _replace_bare(match: re.Match) -> str:
        idx = key_to_index.get(match.group(1))
        return str(idx) if idx else match.group(0)

    return _BARE_CITATION_KEY_RE.sub(_replace_bare, content)


def _validate_scientific_manuscript(*, content: str, external_sources_count: int, reference_keys: set[str]) -> None:
    if external_sources_count == 0 or not reference_keys:
        raise ValueError("No verified evidence found")

    banned = [
        "paper should",
        "literature should",
        "methodology should",
        "discussion should",
        "expected outcomes guidance should",
        "theoretical foundation should",
    ]
    for line in content.splitlines():
        stripped = line.strip().lower()
        if any(stripped.startswith(x) for x in banned):
            raise ValueError("Research generation rejected: template paragraph detected")

    cited_keys = set(_CITATION_RE.findall(content))
    if not cited_keys.issubset(reference_keys):
        missing = sorted(cited_keys - reference_keys)
        raise ValueError(f"Research generation rejected: citations missing from references: {missing}")

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    for p in paragraphs:
        if p.startswith("#") or p.startswith("|") or p.startswith("```"):
            continue
        if p.startswith("Figure") or p.startswith("###"):
            continue
        # Rendered figure image lines (see api/utils/figure_renderer.py) — a
        # standalone "![Figure N. Caption](path)" line is a rendered asset,
        # not an uncited prose claim.
        if p.startswith("!["):
            continue
        if not _CITATION_RE.search(p):
            raise ValueError("Research generation rejected: uncited claim paragraph detected")


async def build_phase2_research_document(
    *,
    artifacts: dict[str, Any],
    mode: str,
    topic: str,
    context: str | None,
    keywords: list[str] | None,
    depth: str | None,
    word_count: int | None,
    provider,
    run_id: str = "",
) -> dict[str, Any]:
    accepted_sources = artifacts.get("unified_sources", artifacts.get("sources_accepted", []))
    literature_matrix = artifacts.get("literature_matrix", [])
    gap_matrix = artifacts.get("research_gap_matrix", [])
    normalized_topic = artifacts.get("normalized_topic", topic)
    target_profile = _target_depth_profile(depth, mode, word_count)
    has_real_results = False
    document_type = _classify_document_type(mode, accepted_sources, has_real_results)
    paper_title = topic.strip() or normalized_topic
    evidence = _build_evidence_objects(artifacts)
    if not evidence:
        raise ValueError("No verified evidence found")
    clusters = _cluster_evidence_by_topic(evidence)
    comparison_matrix = _build_comparison_matrix(evidence)

    def _dedupe_evidence(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
        # _cluster_evidence_by_topic deliberately lets one evidence item match
        # more than one cluster (e.g. both "industrial implementation" and
        # "operational deployment"), so concatenating two clusters can include
        # the same item twice — which showed up as the same finding printed
        # twice in a row within a single section (observed in Discussion).
        seen: set[str] = set()
        out: list[dict[str, Any]] = []
        for it in items:
            key = it.get("citation_key", "")
            if key and key in seen:
                continue
            seen.add(key)
            out.append(it)
        return out

    intro_evidence = _dedupe_evidence(clusters.get("operational deployment", []) + clusters.get("detector physics", []))
    lit_evidence = _dedupe_evidence(clusters.get("detector physics", []) + clusters.get("algorithmic methods", []))
    method_evidence = _dedupe_evidence(clusters.get("algorithmic methods", []) + clusters.get("standards and regulation", []))
    discussion_evidence = _dedupe_evidence(clusters.get("industrial implementation", []) + clusters.get("operational deployment", []))

    # Write each prose section with the active AI provider first — genuine
    # synthesis grounded in the same verified evidence, not a restatement of
    # one source's abstract sentence. _llm_write_section never raises and
    # returns None if the provider is unavailable/errors/would violate the
    # citation-integrity rules, so every section falls back to the
    # deterministic templater (_section_from_evidence) it always used before.
    # Sections run in parallel since each is an independent LLM call.
    llm_sections = await asyncio.gather(
        _llm_write_section(
            provider, title="Abstract",
            section_role="a concise high-level summary of the objective and key findings",
            topic=paper_title, evidence=evidence[:4],
        ),
        _llm_write_section(
            provider, title="Introduction",
            section_role="motivating problem framing and context for the reader",
            topic=paper_title, evidence=intro_evidence[:6],
        ),
        _llm_write_section(
            provider, title="Literature Review",
            section_role="comparative synthesis of prior work, not a list of summaries",
            topic=paper_title, evidence=lit_evidence[:8],
        ),
        _llm_write_section(
            provider, title="Methodology",
            section_role="the methodological basis this review draws from the cited evidence",
            topic=paper_title, evidence=method_evidence[:6],
        ),
        _llm_write_section(
            provider, title="Discussion",
            section_role="operational interpretation and practical implications of the evidence",
            topic=paper_title, evidence=discussion_evidence[:6],
        ),
        _llm_write_section(
            provider, title="Conclusion",
            section_role="a concluding synthesis of the overall contribution — do not restate the Abstract",
            topic=paper_title, evidence=evidence[:4],
        ),
        _llm_write_section(
            provider, title="Research Gap",
            section_role="what remains unresolved across the cited literature — the specific gap this evidence base exposes, not a restatement of the Literature Review",
            topic=paper_title, evidence=lit_evidence[:6],
        ),
        _llm_write_section(
            provider, title="Novel Contributions",
            section_role="the specific original contribution or proposed direction this work adds, explicitly distinguished from summarizing prior work — label any proposed (not yet validated) contribution as proposed",
            topic=paper_title, evidence=discussion_evidence[:6],
        ),
        _llm_write_section(
            provider, title="Limitations",
            section_role="concrete limitations of the evidence base and any proposed approach — scope, generalizability, and validation gaps",
            topic=paper_title, evidence=evidence[:4],
        ),
        _llm_write_section(
            provider, title="Future Work",
            section_role="concrete, evidence-grounded directions for future research building on the identified gap",
            topic=paper_title, evidence=evidence[:4],
        ),
    )
    (
        llm_abstract, llm_intro, llm_literature,
        llm_methodology, llm_discussion, llm_conclusion,
        llm_research_gap, llm_novel_contributions, llm_limitations, llm_future_work,
    ) = llm_sections

    abstract_text = llm_abstract or _section_from_evidence("Abstract", evidence[:4], "Evidence-grounded objective")
    intro_text = llm_intro or _section_from_evidence("Introduction", intro_evidence[:6], "Problem framing")
    literature_text = llm_literature or _section_from_evidence("Literature Review", lit_evidence[:8], "Comparative synthesis")
    methodology_text = llm_methodology or _section_from_evidence("Methodology", method_evidence[:6], "Method evidence")
    discussion_text = llm_discussion or _section_from_evidence("Discussion", discussion_evidence[:6], "Operational interpretation")
    conclusion_text = llm_conclusion or _section_from_evidence("Conclusion", evidence[:4], "Evidence-backed conclusion")
    research_gap_text = llm_research_gap or _section_from_evidence("Research Gap", lit_evidence[:6], "Unresolved gap across cited evidence")
    novel_contributions_text = llm_novel_contributions or _section_from_evidence("Novel Contributions", discussion_evidence[:6], "Proposed original contribution")
    limitations_text = llm_limitations or _section_from_evidence("Limitations", evidence[:4], "Scope and validation limitations")
    future_work_text = llm_future_work or _section_from_evidence("Future Work", evidence[:4], "Evidence-grounded future directions")

    keywords_list = artifacts.get("search_keywords") or []
    keywords_text = f"## Keywords\n{', '.join(keywords_list[:8])}" if keywords_list else ""

    tables_text = _build_tables_section(literature_matrix, comparison_matrix, gap_matrix)
    figures_text = _build_figures_section(evidence, topic=paper_title, run_id=run_id)
    equations_text = _build_equations_section(evidence)

    referencable = [ev for ev in evidence if _is_verified_reference_source(ev)]
    if not referencable:
        raise ValueError("No verified evidence found")

    section_blocks = [
        f"# {paper_title}",
        f"## Document Type\n{document_type}",
        abstract_text,
        keywords_text,
        intro_text,
        literature_text,
        research_gap_text,
        novel_contributions_text,
        methodology_text,
        tables_text,
        figures_text,
        equations_text,
        discussion_text,
        limitations_text,
        future_work_text,
        conclusion_text,
    ]
    section_blocks = [block for block in section_blocks if block and block.strip()]
    section_blocks.append(_render_dual_style_references(referencable))
    content = "\n\n".join(section_blocks)
    content = re.sub(r"\n{3,}", "\n\n", content).strip()

    reference_keys = {ev.get("citation_key", "") for ev in referencable if ev.get("citation_key")}
    _validate_scientific_manuscript(
        content=content,
        external_sources_count=len(artifacts.get("sources_found", [])),
        reference_keys=reference_keys,
    )

    # Body prose cites internal keys like "[SRC-1]" (validated above against
    # `reference_keys`), but `_render_dual_style_references` renders the
    # reference list by position as "[1] Author...". Left unrenumbered, the
    # manuscript literally shows "[SRC-1]" next to a reference list showing
    # "[1]" for the same source — rewrite every in-text key to match.
    content = _renumber_citations(content, referencable)
    if re.search(r"\[(?:SRC|KB)-\d+\]", content):
        raise ValueError("Research generation rejected: unresolved citation placeholder survived renumbering")

    reference_meta = [
        {
            "source_type": ev.get("source_type", ""),
            "provider": ev.get("provider", ""),
            "citation_count": ev.get("citation_count"),
            "is_peer_reviewed": ev.get("is_peer_reviewed"),
            "doi_verified": bool(ev.get("doi_verified", False)),
            "quality_score": ev.get("quality_score", 0.0),
        }
        for ev in referencable
    ]

    return {
        "paper_title": paper_title,
        "document_type": document_type,
        "content": content,
        "total_target_words": target_profile["total"],
        "has_real_results": has_real_results,
        "comparison_matrix": comparison_matrix,
        "evidence_objects": evidence,
        "reference_meta": reference_meta,
    }