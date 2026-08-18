"""3-layer knowledge extraction — Phase 2B.0.

Free Mode ON (the platform default): tries a local Ollama model first
(local_extraction.local_ollama_extract), falling back to always-available
deterministic pattern-matching (deterministic_extraction.deterministic_extract)
when Ollama isn't reachable. The knowledge graph keeps growing either way —
extraction is never skipped in Free Mode, unlike the earlier Sub-Phase 2A
behavior this replaces.

Free Mode OFF (explicit opt-in): uses the existing GPT-4o/Gemini pipeline in
api.services.study_service.py, completely unmodified — only adapted here to
the same ExtractionResult shape the other two layers return, so the
downstream versioning call (knowledge_versioning.upsert_node_with_evidence)
is identical regardless of which of the three providers ran.
"""
from __future__ import annotations

import logging

from api.db import crud
from api.services.research_brain import knowledge_versioning
from api.services.research_brain.local_extraction import local_ollama_extract, ExtractionResult
from api.services.research_brain.deterministic_extraction import deterministic_extract

log = logging.getLogger(__name__)

# study_service.py's GPT-4o/Gemini extraction has no per-node confidence
# today — a fixed baseline reflecting hosted-model-class reliability, higher
# than either Free Mode layer, consistent with it being the opt-in paid tier.
PAID_PROVIDER_CONFIDENCE = 0.75


async def paid_provider_extract(db, rag_document_id: str, filename: str, text: str) -> ExtractionResult | None:
    """Thin adapter over the EXISTING, unmodified study_service.run_study_pipeline() —
    reshapes its output into the shared ExtractionResult so the caller doesn't
    need to know which provider ran."""
    from api.services.study_service import run_study_pipeline
    job = await run_study_pipeline(db, rag_document_id, filename, text)
    if job.status != "approved":
        # awaiting_approval / rejected — do not version unapproved facts into
        # the shared graph; the existing study.py admin-review flow still
        # applies to what this pipeline produced.
        return None

    nodes = [
        {
            "label": str(n.get("label", "")).strip()[:500],
            "type": str(n.get("type", "Component")).strip(),
            "description": n.get("description"),
        }
        for n in (job.graph_nodes or []) if str(n.get("label", "")).strip()
    ]
    if not nodes:
        return None
    edges = [
        {
            "from": str(e.get("from", "")).strip()[:500],
            "to": str(e.get("to", "")).strip()[:500],
            "relationship": str(e.get("relationship", "contains")).strip(),
        }
        for e in (job.graph_edges or [])
        if str(e.get("from", "")).strip() and str(e.get("to", "")).strip()
    ]
    return ExtractionResult(nodes=nodes, edges=edges, provider_used="paid_provider", extractor_confidence=PAID_PROVIDER_CONFIDENCE)


async def extract_and_version(db, mission, research_file, rag_document_id: str, topic_id: str | None = None) -> dict:
    """Best-effort: any failure here must never break Phase 1's ingestion
    guarantee — callers wrap this in try/except.

    Returns {"facts_count": int, "edges_count": int} — additive return value
    (Phase 2B.4) so callers can feed TopicResearchMemory's activity counters;
    existing callers that ignore the return value are unaffected."""
    from api.db.models import RagDocument
    doc = db.query(RagDocument).filter(RagDocument.id == rag_document_id).first()
    if not doc or not doc.content:
        return {"facts_count": 0, "edges_count": 0}

    # Phase 2B.5 — the mission's already-detected manufacturer (planner.py's
    # generalized detection, not just a hardcoded list) is folded into both
    # Free Mode extraction layers as extra context; the paid path is
    # unmodified (sole-gateway/paid-path-untouched rule from every prior phase).
    manufacturer_hint = getattr(mission, "detected_manufacturer", None)

    if not mission.free_mode:
        result = await paid_provider_extract(db, rag_document_id, research_file.filename, doc.content)
    else:
        result = await local_ollama_extract(doc.content, manufacturer_hint=manufacturer_hint)
        if result is None:
            # Ollama unreachable / invalid response — the graph must still
            # grow in Free Mode, so this always succeeds.
            result = deterministic_extract(doc.content, manufacturer_hint=manufacturer_hint)

    if not result or not result.nodes:
        crud.add_research_activity(db, mission.id, "info", f"Graph extraction found nothing to add from {research_file.filename}")
        return {"facts_count": 0, "edges_count": 0}

    source_quality = research_file.quality_score or 50.0

    label_to_node_id: dict[str, str] = {}
    for raw_node in result.nodes:
        node = knowledge_versioning.upsert_node_with_evidence(
            db,
            label=raw_node["label"], node_type=raw_node["type"], description=raw_node.get("description"),
            research_source_id=research_file.source_id, provider_used=result.provider_used,
            extractor_confidence=result.extractor_confidence, supports=True,
            source_quality_score=source_quality, topic_id=topic_id,
        )
        label_to_node_id[raw_node["label"].lower()] = node.id

    edges_created = 0
    for raw_edge in result.edges:
        from_id = label_to_node_id.get(raw_edge["from"].lower())
        to_id = label_to_node_id.get(raw_edge["to"].lower())
        if not from_id or not to_id:
            continue
        knowledge_versioning.upsert_edge_with_evidence(
            db, from_node_id=from_id, to_node_id=to_id, relationship=raw_edge["relationship"],
            research_source_id=research_file.source_id, provider_used=result.provider_used,
            extractor_confidence=result.extractor_confidence, supports=True, source_quality_score=source_quality,
        )
        edges_created += 1

    crud.add_research_activity(
        db, mission.id, "info",
        f"Graph updated via {result.provider_used}: {len(result.nodes)} fact(s), {edges_created} relationship(s) from {research_file.filename}",
    )
    return {"facts_count": len(result.nodes), "edges_count": edges_created}


# ── Scientific Literature Learning (Phase 2B.5) ─────────────────────────────
# Additive to extract_and_version() above, not a replacement — a paper's body
# text is still run through the generic extractor too (it may mention
# Manufacturer/Component/Standard entities worth graphing on their own). This
# function ONLY runs for academic-typed, open-access, non-duplicate sources
# (gated by the caller, crawler_orchestrator.process_next_queue_item()) and
# writes the structured section breakdown + Paper/Author/Institution nodes
# through the SAME governance/versioning write path as every other extractor.

ACADEMIC_METADATA_CONFIDENCE = 0.6


async def version_academic_paper(
    db, mission, research_file, research_source, academic_metadata: dict, full_text: str,
    topic_id: str | None = None,
) -> dict:
    """Best-effort, never re-raised — same convention as extract_and_version().
    Returns {"paper_created": bool, "author_count": int, "cites_count": int}."""
    from api.services.research_brain.paper_extraction import extract_paper_sections

    sections = extract_paper_sections(full_text, academic_metadata)
    authors = [a.strip() for a in (academic_metadata.get("authors") or "").split(",") if a.strip()][:5]
    institution_name = (academic_metadata.get("publisher") or "").strip()

    crud.create_academic_paper_metadata(
        db,
        research_source_id=research_source.id,
        title=(academic_metadata.get("title") or research_source.title)[:1024],
        authors=authors,
        institution_or_journal=institution_name,
        degree_type=academic_metadata.get("degree_type") or "",
        publication_year=academic_metadata.get("year") or "",
        doi_or_repo_id=academic_metadata.get("doi") or "",
        abstract=sections["abstract"],
        research_problem=sections["research_problem"],
        methodology=sections["methodology"],
        equipment_components=sections["equipment_components"],
        results=sections["results"],
        limitations=sections["limitations"],
        future_work=sections["future_work"],
        citations=sections["citations"],
        is_open_access=bool(academic_metadata.get("is_open_access")),
        file_hash=research_source.content_hash,
    )

    source_quality = research_file.quality_score or 50.0
    paper_label = (academic_metadata.get("title") or research_source.title)[:500]
    paper_node = knowledge_versioning.upsert_node_with_evidence(
        db, label=paper_label, node_type="Paper", description=(sections["abstract"] or None) and sections["abstract"][:2000],
        research_source_id=research_source.id, provider_used="academic_metadata",
        extractor_confidence=ACADEMIC_METADATA_CONFIDENCE, supports=True,
        source_quality_score=source_quality, topic_id=topic_id,
    )

    author_node_ids: list[str] = []
    for author_name in authors:
        author_node = knowledge_versioning.upsert_node_with_evidence(
            db, label=author_name, node_type="Author", description=None,
            research_source_id=research_source.id, provider_used="academic_metadata",
            extractor_confidence=ACADEMIC_METADATA_CONFIDENCE, supports=True,
            source_quality_score=source_quality, topic_id=topic_id,
        )
        author_node_ids.append(author_node.id)
        knowledge_versioning.upsert_edge_with_evidence(
            db, from_node_id=paper_node.id, to_node_id=author_node.id, relationship="authored_by",
            research_source_id=research_source.id, provider_used="academic_metadata",
            extractor_confidence=ACADEMIC_METADATA_CONFIDENCE, supports=True, source_quality_score=source_quality,
        )

    if institution_name and author_node_ids:
        institution_node = knowledge_versioning.upsert_node_with_evidence(
            db, label=institution_name, node_type="Institution", description=None,
            research_source_id=research_source.id, provider_used="academic_metadata",
            extractor_confidence=ACADEMIC_METADATA_CONFIDENCE, supports=True,
            source_quality_score=source_quality, topic_id=topic_id,
        )
        for author_id in author_node_ids:
            knowledge_versioning.upsert_edge_with_evidence(
                db, from_node_id=author_id, to_node_id=institution_node.id, relationship="affiliated_with",
                research_source_id=research_source.id, provider_used="academic_metadata",
                extractor_confidence=ACADEMIC_METADATA_CONFIDENCE, supports=True, source_quality_score=source_quality,
            )

    # cites — only when a cited DOI matches ANOTHER source already
    # discovered within this SAME mission (no new fetches triggered by the
    # reference list itself — a disclosed, deliberate scope limit; see the
    # Phase 2B.5 plan's deferrals).
    cites_count = 0
    if sections["citations"]:
        mission_sources = crud.list_research_sources(db, mission.id)
        for cited_id in sections["citations"]:
            match = next(
                (s for s in mission_sources if s.source_doi and (s.source_doi in cited_id or cited_id in s.source_doi) and s.id != research_source.id),
                None,
            )
            if not match:
                continue
            cited_paper_node = crud.get_knowledge_node_by_label(db, match.title, "Paper")
            if cited_paper_node:
                knowledge_versioning.upsert_edge_with_evidence(
                    db, from_node_id=paper_node.id, to_node_id=cited_paper_node.id, relationship="cites",
                    research_source_id=research_source.id, provider_used="academic_metadata",
                    extractor_confidence=ACADEMIC_METADATA_CONFIDENCE, supports=True, source_quality_score=source_quality,
                )
                cites_count += 1

    crud.add_research_activity(
        db, mission.id, "info",
        f"Academic paper structured: {len(authors)} author(s), {cites_count} citation link(s) — {research_source.title}",
    )
    return {"paper_created": True, "author_count": len(authors), "cites_count": cites_count}
