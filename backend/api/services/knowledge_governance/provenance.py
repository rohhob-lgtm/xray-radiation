"""Provenance recording — where a fact/edge came from.

Pulls original_url/document_hash from the existing ResearchSource row and
original_filename from ResearchFile when a source_id/file_row is given
(Phase 1 data, already collected during crawling). Fields no current
extractor produces (page/section/paragraph/sentence_offset) are left null
rather than invented — "إذا لم تتوفر معلومة لا يتم اختراعها".
"""
from __future__ import annotations

from api.db import crud
from api.db.models import ResearchSource


def record_provenance(
    db,
    *,
    node_id: str | None = None,
    edge_id: str | None = None,
    mission_id: str | None = None,
    source_id: str | None = None,
    provider_used: str | None = None,
    extractor_used: str | None = None,
    parser_version: str | None = None,
    knowledge_version: int = 1,
    created_by_service: str,
    confidence_at_write: float = 0.5,
    page_number: int | None = None,
    section: str | None = None,
    paragraph: int | None = None,
    sentence_offset: int | None = None,
    original_filename: str | None = None,
):
    """Write one KnowledgeProvenance row. Exactly one of node_id/edge_id
    should be set by the caller (governance_service enforces this)."""
    original_url = None
    document_hash = None
    if source_id:
        source = db.query(ResearchSource).filter(ResearchSource.id == source_id).first()
        if source:
            original_url = source.url
            document_hash = source.content_hash

    return crud.create_knowledge_provenance(
        db,
        node_id=node_id,
        edge_id=edge_id,
        mission_id=mission_id,
        source_id=source_id,
        provider_used=provider_used,
        extractor_used=extractor_used,
        parser_version=parser_version,
        knowledge_version=knowledge_version,
        original_filename=original_filename,
        original_url=original_url,
        document_hash=document_hash,
        page_number=page_number,
        section=section,
        paragraph=paragraph,
        sentence_offset=sentence_offset,
        created_by_service=created_by_service,
        confidence_at_write=confidence_at_write,
    )
