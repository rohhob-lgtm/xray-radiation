"""Pulls pending queue items and processes them one at a time.

A thin wrapper around api.services.web_crawler.crawl() — the crawler's own
robots.txt honoring, anti-bot fallback, and technical-relevance scoring are
reused unmodified; this module only persists per-page results as
ResearchSource/ResearchFile rows and enforces per-mission limits, instead of
web_crawler.crawl() returning one combined blob for a single caller.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from api.db import crud
from api.db.models import ResearchMission
from api.services.web_crawler import crawl as web_crawl
from api.services.research_agent.quality_scorer import score_source, REVIEW_REQUIRED_LABELS
from api.services.research_agent.ingestion import get_embedding_for_mission, ingest_research_content
from api.services.research_brain.graph_extraction import extract_and_version, version_academic_paper
from api.services.research_brain import research_memory
from api.services.study_service import compute_sha256, is_duplicate
from api.services.source_trust.source_trust_service import extract_doi, initialize_trust

log = logging.getLogger(__name__)

_DEFAULT_LIMITS = {
    "max_pages": 30,
    "max_files": 30,
    "max_storage_mb": 200,
    "max_depth": 1,
    "min_relevance_score": 0.15,
    "min_quality_score": 45.0,
}


def _limit(mission: ResearchMission, key: str) -> float:
    return (mission.limits or {}).get(key, _DEFAULT_LIMITS[key])


def _limits_exceeded(mission: ResearchMission) -> str | None:
    if mission.pages_processed >= _limit(mission, "max_pages"):
        return "max_pages reached"
    if mission.files_ingested + mission.files_rejected >= _limit(mission, "max_files"):
        return "max_files reached"
    max_storage_bytes = _limit(mission, "max_storage_mb") * 1024 * 1024
    if mission.storage_used_bytes >= max_storage_bytes:
        return "max_storage_mb reached"
    return None


async def process_next_queue_item(db: Session, mission: ResearchMission) -> bool:
    """Process one pending queue item.

    Returns False when there is nothing left to do (queue empty or a mission
    limit was hit) — signals the caller (job_runner.run_mission) to stop.
    Returns True after processing one item (success, rejection, or error) so
    the caller keeps looping.
    """
    stop_reason = _limits_exceeded(mission)
    if stop_reason:
        crud.add_research_activity(db, mission.id, "info", f"Stopping: {stop_reason}")
        return False

    item = crud.get_next_pending_queue_item(db, mission.id)
    if not item:
        return False

    crud.update_research_queue_item(db, item.id, status="fetching", attempts=item.attempts + 1)

    # Phase 2B.4 — Incremental Research: if this URL was already visited for
    # the topic's cross-mission memory, send a conditional GET (ETag/
    # Last-Modified) so an unchanged page costs one cheap 304 instead of a
    # full re-fetch + re-embed + re-extract.
    topic_memory_id: str | None = None
    known_source: dict | None = None
    if item.topic_id:
        topic = crud.get_research_topic(db, item.topic_id)
        if topic and topic.topic_memory_id:
            topic_memory_id = topic.topic_memory_id
            memory = crud.get_topic_research_memory(db, topic_memory_id)
            if memory:
                known_source = research_memory.get_known_source(memory, item.url)

    # Phase 2B.5 — legal/copyright compliance: an academic item whose source
    # is NOT verified open access is never crawled/ingested at all — no
    # web_crawl() call, no embedding, no graph extraction. Only metadata,
    # abstract, and the link are stored (accepted_into_kb stays False),
    # matching "never bypass a paywall or login."
    academic_metadata = item.academic_metadata or None
    if academic_metadata and not academic_metadata.get("is_open_access"):
        mission.pages_processed += 1
        domain = urlparse(item.url).hostname or item.source_domain
        source = crud.create_research_source(
            db,
            mission_id=mission.id,
            url=item.url,
            domain=domain,
            title=(academic_metadata.get("title") or item.url)[:1024],
            publisher=academic_metadata.get("publisher") or domain,
            content_hash=None,
            quality_score=50.0,
            quality_label="useful",
            quality_reasons=["Metadata-only: not verified open access, full text not fetched"],
            accepted_into_kb=False,
            source_doi=academic_metadata.get("doi") or None,
        )
        initialize_trust(db, source)
        mission.files_discovered += 1
        crud.add_research_activity(
            db, mission.id, "info",
            f"Metadata-only (not open access, no paywall bypass): {source.title}",
        )
        if topic_memory_id:
            research_memory.record_research_activity(
                db, topic_memory_id=topic_memory_id, url=item.url,
                content_hash=source.content_hash or "", was_duplicate=False,
            )
        crud.update_research_queue_item(db, item.id, status="done")
        db.commit()
        return True

    try:
        report = await web_crawl(
            item.url, max_pages=1, max_depth=0, include_sitemap=False, min_relevance_score=0.0,
            if_none_match=(known_source or {}).get("etag"),
            if_modified_since=(known_source or {}).get("last_modified"),
        )
    except Exception as exc:
        log.warning("Crawl failed for %s: %s", item.url, exc)
        crud.update_research_queue_item(db, item.id, status="error", last_error=str(exc))
        crud.add_research_activity(db, mission.id, "error", f"Crawl error for {item.url}: {exc}")
        mission.pages_processed += 1
        db.commit()
        return True

    mission.pages_processed += 1
    page = report.page_results[0] if report.page_results else None

    # getattr(..., default) throughout below: page objects in this codebase's
    # existing tests are lightweight fakes predating these fields (Phase
    # 2B.4) — defaulting to "absent" keeps every prior test passing unchanged
    # while real PageResult instances (which always define these fields) work
    # exactly as intended.
    if page and getattr(page, "not_modified", False):
        crud.update_research_queue_item(db, item.id, status="done")
        mission.duplicates_skipped += 1
        crud.add_research_activity(db, mission.id, "info", f"Unchanged since last visit (304): {item.url}")
        if topic_memory_id and known_source:
            research_memory.record_research_activity(
                db, topic_memory_id=topic_memory_id, url=item.url,
                content_hash=known_source.get("content_hash", ""),
                etag=getattr(page, "etag", None) or known_source.get("etag"),
                last_modified=getattr(page, "last_modified", None) or known_source.get("last_modified"),
                was_duplicate=True,
            )
        db.commit()
        return True

    if not page or not page.accessible or not page.text:
        reason = page.error if page else "No response"
        crud.update_research_queue_item(db, item.id, status="rejected", last_error=reason)
        crud.add_research_activity(db, mission.id, "warning", f"Inaccessible: {item.url} — {reason}")
        db.commit()
        return True

    quality = score_source(item.url, page.text, page.http_status, page.blocking_mechanism)
    domain = urlparse(item.url).hostname or item.source_domain
    content_hash = compute_sha256(page.text.encode("utf-8", errors="ignore"))

    dup_source = crud.get_research_source_by_hash(db, mission.id, content_hash)
    if dup_source:
        crud.update_research_queue_item(db, item.id, status="done")
        mission.duplicates_skipped += 1
        crud.add_research_activity(db, mission.id, "info", f"Duplicate content skipped: {item.url}")
        db.commit()
        return True

    # Phase 2B.5 — an open-access academic item already carries a real
    # title/publisher/DOI from the discovery API; prefer it over re-deriving
    # a title from the first non-blank line of raw fetched text.
    default_title = next((line.strip() for line in page.text.splitlines() if line.strip()), item.url)[:200]
    title = (academic_metadata.get("title") if academic_metadata else None) or default_title
    publisher = (academic_metadata.get("publisher") if academic_metadata else None) or domain
    source_doi = (academic_metadata.get("doi") if academic_metadata else None) or extract_doi(item.url)
    source = crud.create_research_source(
        db,
        mission_id=mission.id,
        url=item.url,
        domain=domain,
        title=title,
        publisher=publisher,
        content_hash=content_hash,
        quality_score=quality["score"],
        quality_label=quality["label"],
        quality_reasons=quality["reasons"],
        accepted_into_kb=False,
        source_doi=source_doi,
    )
    # Dynamic Source Trust (Phase 2B.3) — cheap, synchronous initial
    # snapshot (zero evidence yet); real recalculation happens later via
    # the bounded trust worker once evidence/conflicts/reviews exist.
    initialize_trust(db, source)
    mission.files_discovered += 1

    url_path = urlparse(item.url).path.strip("/").replace("/", "_") or "index"
    filename = f"{domain}_{url_path}.txt"[:500]
    file_row = crud.create_research_file(
        db,
        mission_id=mission.id,
        source_id=source.id,
        filename=filename,
        file_type="html",
        size_bytes=len(page.text.encode("utf-8")),
        relevance_score=page.technical_relevance,
        quality_score=quality["score"],
        status="discovered",
        downloaded=True,
    )
    mission.storage_used_bytes += file_row.size_bytes

    min_quality = _limit(mission, "min_quality_score")
    needs_review = quality["label"] in REVIEW_REQUIRED_LABELS or quality["score"] < min_quality
    if needs_review:
        crud.update_research_file(db, file_row.id, status="rejected")
        mission.files_rejected += 1
        crud.add_research_activity(
            db, mission.id, "info",
            f"Held for review (quality={quality['score']}, label={quality['label']}): {item.url}",
        )
        crud.update_research_queue_item(db, item.id, status="done")
        db.commit()
        return True

    # Phase 2B.4 — Research Memory: check the GLOBAL content-hash registry
    # (the same DocumentHash table ingest_research_content() itself checks)
    # BEFORE computing an embedding, instead of after. Content already known
    # platform-wide costs one cheap lookup instead of a wasted embedding call.
    stripped_text = page.text.strip()
    too_short = len(stripped_text) < 50
    pre_known_doc_id = None if too_short else is_duplicate(db, compute_sha256(stripped_text.encode("utf-8", errors="ignore")))

    embedding = None
    extraction_result: dict | None = None
    if too_short:
        rag_doc_id, was_duplicate = None, False
    elif pre_known_doc_id:
        rag_doc_id, was_duplicate = pre_known_doc_id, True
    else:
        embedding = await get_embedding_for_mission(page.text, mission.free_mode)
        rag_doc_id, was_duplicate = ingest_research_content(db, filename=filename, text=page.text, embedding=embedding)

    if rag_doc_id:
        crud.update_research_file(db, file_row.id, status="ingested", rag_document_id=rag_doc_id)
        crud.update_research_source(db, source.id, accepted_into_kb=True)
        mission.files_ingested += 1
        if was_duplicate:
            crud.add_research_activity(db, mission.id, "info", f"Already in knowledge base (dedup): {item.url}")
        else:
            crud.add_research_activity(db, mission.id, "info", f"Ingested into knowledge base: {item.url}")

        # Knowledge Evolution Engine (Sub-Phase 2A): version the knowledge graph
        # from this content. Best-effort — a failure here (or Free Mode being
        # on, handled inside extract_and_version) must never break Phase 1's
        # ingestion guarantee, so it's wrapped and never re-raised.
        # Phase 2B.4: skipped entirely for already-known content — the graph
        # was already extracted the first time this content was ingested.
        if not was_duplicate:
            try:
                extraction_result = await extract_and_version(db, mission, file_row, rag_doc_id, topic_id=item.topic_id)
            except Exception as exc:
                log.warning("Graph extraction failed for %s: %s", item.url, exc)
                crud.add_research_activity(db, mission.id, "warning", f"Graph extraction failed for {item.url}: {exc}")

            # Phase 2B.5 — additive to the generic extraction above (not a
            # replacement): structured paper/thesis sections + Paper/Author/
            # Institution graph linking, only for open-access academic items.
            if academic_metadata and academic_metadata.get("is_open_access"):
                try:
                    await version_academic_paper(
                        db, mission, file_row, source, academic_metadata, page.text, topic_id=item.topic_id,
                    )
                except Exception as exc:
                    log.warning("Academic paper structuring failed for %s: %s", item.url, exc)
                    crud.add_research_activity(db, mission.id, "warning", f"Academic paper structuring failed for {item.url}: {exc}")
    else:
        crud.update_research_file(db, file_row.id, status="rejected")
        mission.files_rejected += 1
        crud.add_research_activity(db, mission.id, "warning", f"Content too short to ingest: {item.url}")

    if topic_memory_id:
        research_memory.record_research_activity(
            db, topic_memory_id=topic_memory_id, url=item.url, content_hash=content_hash,
            etag=getattr(page, "etag", None), last_modified=getattr(page, "last_modified", None),
            was_duplicate=was_duplicate,
            embedded=embedding is not None, graph_extracted=extraction_result is not None,
            new_facts=(extraction_result or {}).get("facts_count", 0),
            conflicts_found=0,
        )

    crud.update_research_queue_item(db, item.id, status="done")
    db.commit()
    return True
