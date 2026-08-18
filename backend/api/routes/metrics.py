"""Platform metrics and observability endpoint."""
from __future__ import annotations
import time
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from api.db import get_db
from api.services.cache_service import rag_cache, research_meta_cache

router = APIRouter(tags=["metrics"])

_start_time = time.time()


@router.get("/metrics")
def get_platform_metrics(db: Session = Depends(get_db)):
    """Return platform-wide health and usage statistics."""
    from api.db.models import (
        Conversation, Message, XrayAnalysis, RagDocument,
        ResearchOutput, LinkedInPost, RagPage, RagImage,
    )

    pages_total   = db.query(RagPage).count()
    pages_indexed = db.query(RagPage).filter(RagPage.colpali_vecs.isnot(None)).count()
    imgs_total    = db.query(RagImage).count()
    imgs_captioned = db.query(RagImage).filter(RagImage.caption.isnot(None)).count()

    uptime_s = int(time.time() - _start_time)
    uptime_h = uptime_s // 3600
    uptime_m = (uptime_s % 3600) // 60

    return {
        "platform": "X-Ray Academy AI Platform",
        "version":  "2.0.0",
        "uptime":   f"{uptime_h}h {uptime_m}m",
        "uptime_seconds": uptime_s,
        "database": {
            "conversations":    db.query(Conversation).count(),
            "messages":         db.query(Message).count(),
            "xray_analyses":    db.query(XrayAnalysis).count(),
            "rag_documents":    db.query(RagDocument).count(),
            "research_outputs": db.query(ResearchOutput).count(),
            "linkedin_posts":   db.query(LinkedInPost).count(),
            "pages_total":      pages_total,
            "pages_indexed":    pages_indexed,
            "images_total":     imgs_total,
            "images_captioned": imgs_captioned,
        },
        "cache": {
            "rag": rag_cache.stats(),
            "research_meta": research_meta_cache.stats(),
        },
        "modules": [
            {"name": "AI Chat",          "agents": 8, "status": "online"},
            {"name": "X-Ray Analysis",   "status": "online"},
            {"name": "Research Studio",  "modes": 11, "status": "online"},
            {"name": "Patent Analyzer",  "status": "online"},
            {"name": "Education Studio", "types": 7, "status": "online"},
            {"name": "Knowledge Graph",  "status": "online"},
            {"name": "Image Gallery",    "pages": pages_indexed, "status": "online"},
            {"name": "Knowledge Base",   "status": "online"},
            {"name": "LinkedIn Content", "status": "online"},
            {"name": "Technical Reports","status": "online"},
            {"name": "Export Engine",    "formats": ["HTML", "Print"], "status": "online"},
        ],
    }


@router.post("/metrics/cache/clear")
def clear_all_caches():
    """Clear all in-memory caches. Use after bulk document uploads."""
    n_rag = rag_cache.invalidate()
    n_res = research_meta_cache.invalidate()
    return {"cleared_rag": n_rag, "cleared_research_meta": n_res, "total": n_rag + n_res}


@router.get("/metrics/cache")
def get_cache_stats():
    return {"rag": rag_cache.stats(), "research_meta": research_meta_cache.stats()}
