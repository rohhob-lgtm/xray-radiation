"""
Gallery routes — image search API and reindex admin endpoint.

GET  /api/gallery/search?q={query}   → structured image results
POST /api/gallery/reindex            → rebuild GalleryIndex from all RagPages
GET  /api/gallery/stats              → indexing stats
GET  /api/gallery/recent             → recent images (no search)
"""
from __future__ import annotations
import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.db import get_db
from api.services.gallery_service import search_gallery

logger = logging.getLogger(__name__)
router = APIRouter(tags=["gallery"])


@router.get("/gallery/search")
async def gallery_search(
    q: str = Query(default="", description="Search query"),
    limit: int = Query(default=6, le=24),
    db: Session = Depends(get_db),
):
    """Search the gallery index and return matching images as structured JSON."""
    query = q.strip() or None
    images = await search_gallery(query, db, top_k=limit)
    return {
        "type": "image_results",
        "query": q,
        "count": len(images),
        "images": images,
    }


@router.get("/gallery/recent")
async def gallery_recent(
    limit: int = Query(default=12, le=48),
    db: Session = Depends(get_db),
):
    """Return most recently indexed gallery images."""
    images = await search_gallery(None, db, top_k=limit)
    return {
        "type": "image_results",
        "query": "",
        "count": len(images),
        "images": images,
    }


@router.get("/gallery/stats")
def gallery_stats(db: Session = Depends(get_db)):
    """Return indexing stats for the admin UI."""
    from api.db.models import RagPage, GalleryIndex
    total_pages = db.query(RagPage).count()
    indexed = db.query(GalleryIndex).count()
    return {
        "total_pages": total_pages,
        "indexed": indexed,
        "unindexed": max(0, total_pages - indexed),
    }


@router.post("/gallery/reindex")
async def gallery_reindex(db: Session = Depends(get_db)):
    """
    Reindex all RagPages into the GalleryIndex using GPT Vision.
    Returns streaming JSON-lines progress so the UI can show a live counter.
    """
    import json
    import asyncio
    from api.db.models import RagPage, GalleryIndex
    from api.services.ai_providers.registry import provider_registry
    from api.services.rag_service import _get_embedding
    from api.services.gallery_service import reindex_page

    provider = provider_registry.get_active()

    async def streamer():
        pages = db.query(RagPage).all()
        total = len(pages)
        done = 0
        failed = 0
        skipped = 0

        yield json.dumps({"event": "start", "total": total}) + "\n"

        for page in pages:
            try:
                # Skip if already indexed (use --force param to override)
                existing = db.query(GalleryIndex).filter(
                    GalleryIndex.rag_page_id == page.id
                ).first()
                if existing:
                    skipped += 1
                    done += 1
                    yield json.dumps({
                        "event": "skip",
                        "page_id": page.id,
                        "doc": page.doc_filename,
                        "page_num": page.page_num,
                        "done": done,
                        "total": total,
                    }) + "\n"
                    continue

                # Generate metadata via GPT Vision
                meta = await reindex_page(page, provider)

                image_url = f"/api/rag/pages/{page.id}"
                # Build searchable text for embedding
                embed_text = " ".join(filter(None, [
                    meta.get("title", ""),
                    meta.get("caption", ""),
                    " ".join(meta.get("tags", [])),
                    meta.get("ocr_text", "")[:400],
                    meta.get("scanner_model", ""),
                    page.doc_filename,
                ]))
                embedding = await _get_embedding(embed_text)

                gi = GalleryIndex(
                    rag_page_id=page.id,
                    doc_filename=page.doc_filename,
                    page_num=page.page_num,
                    title=meta.get("title", f"{page.doc_filename} p.{page.page_num}"),
                    description=meta.get("description", ""),
                    caption=meta.get("caption", ""),
                    tags=meta.get("tags", []),
                    scanner_model=meta.get("scanner_model", ""),
                    manufacturer=meta.get("manufacturer", ""),
                    category=meta.get("category", "other"),
                    ocr_text=meta.get("ocr_text", ""),
                    image_url=image_url,
                    thumbnail_url=image_url,
                    embedding=embedding,
                )
                db.add(gi)
                db.commit()
                done += 1

                yield json.dumps({
                    "event": "indexed",
                    "page_id": page.id,
                    "doc": page.doc_filename,
                    "page_num": page.page_num,
                    "title": gi.title,
                    "tags": gi.tags,
                    "done": done,
                    "total": total,
                }) + "\n"

                # Small delay to avoid rate limits
                await asyncio.sleep(0.3)

            except Exception as e:
                failed += 1
                done += 1
                logger.error("[reindex] Error on page %s: %s", page.id, e)
                yield json.dumps({
                    "event": "error",
                    "page_id": page.id,
                    "error": str(e),
                    "done": done,
                    "total": total,
                }) + "\n"

        final_indexed = db.query(GalleryIndex).count()
        yield json.dumps({
            "event": "complete",
            "total": total,
            "newly_indexed": done - skipped - failed,
            "skipped": skipped,
            "failed": failed,
            "total_indexed": final_indexed,
        }) + "\n"

    return StreamingResponse(
        streamer(),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.delete("/gallery/index/{rag_page_id}")
def delete_gallery_index(rag_page_id: str, db: Session = Depends(get_db)):
    """Remove a single entry from the gallery index (force re-index on next run)."""
    from api.db.models import GalleryIndex
    entry = db.query(GalleryIndex).filter(GalleryIndex.rag_page_id == rag_page_id).first()
    if entry:
        db.delete(entry)
        db.commit()
    return {"deleted": rag_page_id}
