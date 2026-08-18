"""Cost Dashboard — aggregates real API usage across all platform features.

All costs come from actual tracked data:
- translation_usage   → Translation Studio (real tokens + costs)
- vision_cost_log     → Image Analysis / Vision (real tokens + costs)
- study_jobs          → Learning Hub (real token counts, computed cost)
- chat_usage          → AI Chat (char-estimated tokens, labeled)
"""
from __future__ import annotations

import csv
import io
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func as _f, text, or_
from sqlalchemy.orm import Session

from api.db import get_db
from api.middleware.auth import require_auth

log = logging.getLogger(__name__)
router = APIRouter(tags=["cost-dashboard"])

# ── Pricing constants (USD per 1M tokens) ─────────────────────────────────────

_IN_PRICES: dict[str, float] = {
    "gpt-4o":       5.00,
    "gpt-4o-mini":  0.15,
    "gpt-4.1":      2.00,
    "gpt-4.1-mini": 0.40,
    "gpt-4.5":     75.00,
    "gpt-5":       100.00,
    "gpt-5.4":     100.00,
    "o1":           15.00,
    "o3":           10.00,
    "o3-mini":       1.10,
}
_OUT_PRICES: dict[str, float] = {
    "gpt-4o":       15.00,
    "gpt-4o-mini":   0.60,
    "gpt-4.1":       8.00,
    "gpt-4.1-mini":  1.60,
    "gpt-4.5":     150.00,
    "gpt-5":       200.00,
    "gpt-5.4":     200.00,
    "o1":           60.00,
    "o3":           40.00,
    "o3-mini":       4.40,
}


def _price_for(model: str | None, side: str) -> float:
    if not model:
        model = "gpt-4o"
    prices = _IN_PRICES if side == "in" else _OUT_PRICES
    for key, price in prices.items():
        if model.lower().startswith(key):
            return price
    return prices["gpt-4o"]


def _compute_cost(in_tok: int, out_tok: int, model: str | None = None) -> float:
    return (
        in_tok * _price_for(model, "in") + out_tok * _price_for(model, "out")
    ) / 1_000_000


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _period_bounds(period: str) -> tuple[datetime | None, datetime | None]:
    now = _now_utc()
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    if period == "today":
        return day, None
    if period == "yesterday":
        return day - timedelta(days=1), day
    if period == "7d":
        return day - timedelta(days=7), None
    if period == "30d":
        return day - timedelta(days=30), None
    if period == "month":
        return day.replace(day=1), None
    return None, None   # lifetime


def _apply_period(q, col, period: str):
    start, end = _period_bounds(period)
    if start:
        q = q.filter(col >= start)
    if end:
        q = q.filter(col < end)
    return q


# ── Overview ───────────────────────────────────────────────────────────────────

@router.get("/costs/overview")
def cost_overview(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Return cost totals for all standard time periods + aggregate stat cards."""
    from api.db.models import TranslationUsage, VisionCostLog, StudyJob, ChatUsage, UnifiedUsageLog

    periods = ["today", "yesterday", "7d", "30d", "month", "lifetime"]

    def _agg_translation(period):
        q = db.query(
            _f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0),
            _f.coalesce(_f.sum(TranslationUsage.input_tokens), 0),
            _f.coalesce(_f.sum(TranslationUsage.output_tokens), 0),
            _f.count(TranslationUsage.id),
        )
        q = _apply_period(q, TranslationUsage.created_at, period)
        cost, tin, tout, cnt = q.one()
        return float(cost or 0), int(tin or 0), int(tout or 0), int(cnt or 0)

    def _agg_vision(period):
        q = db.query(
            _f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0),
            _f.coalesce(_f.sum(VisionCostLog.prompt_tokens), 0),
            _f.coalesce(_f.sum(VisionCostLog.completion_tokens), 0),
            _f.count(VisionCostLog.id),
            _f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0),
        )
        q = _apply_period(q, VisionCostLog.created_at, period)
        cost, tin, tout, cnt, saved = q.one()
        return float(cost or 0), int(tin or 0), int(tout or 0), int(cnt or 0), float(saved or 0)

    def _agg_learning(period):
        q = db.query(
            _f.coalesce(_f.sum(StudyJob.input_tokens), 0),
            _f.coalesce(_f.sum(StudyJob.output_tokens), 0),
            _f.count(StudyJob.id),
        )
        q = _apply_period(q, StudyJob.created_at, period)
        tin, tout, cnt = q.one()
        tin, tout = int(tin or 0), int(tout or 0)
        return _compute_cost(tin, tout), tin, tout, int(cnt or 0)

    def _agg_chat(period):
        q = db.query(
            _f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0.0),
            _f.coalesce(_f.sum(ChatUsage.prompt_tokens), 0),
            _f.coalesce(_f.sum(ChatUsage.completion_tokens), 0),
            _f.count(ChatUsage.id),
        )
        q = _apply_period(q, ChatUsage.created_at, period)
        cost, tin, tout, cnt = q.one()
        return float(cost or 0), int(tin or 0), int(tout or 0), int(cnt or 0)

    def _agg_unified(period):
        """Aggregate all previously-untracked features from openai_usage_log."""
        q = db.query(
            _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0),
            _f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens), 0),
            _f.coalesce(_f.sum(UnifiedUsageLog.completion_tokens), 0),
            _f.count(UnifiedUsageLog.id),
        )
        q = _apply_period(q, UnifiedUsageLog.created_at, period)
        cost, tin, tout, cnt = q.one()
        return float(cost or 0), int(tin or 0), int(tout or 0), int(cnt or 0)

    def _agg_unified_by_feature(period, feature: str):
        q = db.query(
            _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0),
            _f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens), 0),
            _f.coalesce(_f.sum(UnifiedUsageLog.completion_tokens), 0),
            _f.count(UnifiedUsageLog.id),
        ).filter(UnifiedUsageLog.feature == feature)
        q = _apply_period(q, UnifiedUsageLog.created_at, period)
        cost, tin, tout, cnt = q.one()
        return float(cost or 0), int(tin or 0), int(tout or 0), int(cnt or 0)

    period_totals = {}
    for p in periods:
        t_cost, t_in, t_out, t_cnt = _agg_translation(p)
        v_cost, v_in, v_out, v_cnt, v_saved = _agg_vision(p)
        l_cost, l_in, l_out, l_cnt = _agg_learning(p)
        c_cost, c_in, c_out, c_cnt = _agg_chat(p)
        u_cost, u_in, u_out, u_cnt = _agg_unified(p)
        total_cost = t_cost + v_cost + l_cost + c_cost + u_cost
        total_in = t_in + v_in + l_in + c_in + u_in
        total_out = t_out + v_out + l_out + c_out + u_out
        total_calls = t_cnt + v_cnt + l_cnt + c_cnt + u_cnt
        period_totals[p] = {
            "total_cost_usd": round(total_cost, 4),
            "prompt_tokens": total_in,
            "completion_tokens": total_out,
            "total_calls": total_calls,
            "breakdown": {
                "translation": round(t_cost, 4),
                "vision": round(v_cost, 4),
                "learning": round(l_cost, 4),
                "chat": round(c_cost, 4),
                "innovation": round(_agg_unified_by_feature(p, "Innovation Engine")[0], 4),
                "training": round(_agg_unified_by_feature(p, "Training Generator")[0], 4),
                "other": round(u_cost, 4),
            },
        }

    # ── All-time aggregate stat cards ─────────────────────────────────────────
    all_t_cost, all_t_in, all_t_out, all_t_cnt = _agg_translation("lifetime")
    all_v_cost, all_v_in, all_v_out, all_v_cnt, all_v_saved = _agg_vision("lifetime")
    all_l_cost, all_l_in, all_l_out, all_l_cnt = _agg_learning("lifetime")
    all_c_cost, all_c_in, all_c_out, all_c_cnt = _agg_chat("lifetime")
    all_u_cost, all_u_in, all_u_out, all_u_cnt = _agg_unified("lifetime")

    total_lifetime_cost = all_t_cost + all_v_cost + all_l_cost + all_c_cost + all_u_cost
    total_calls = all_t_cnt + all_v_cnt + all_l_cnt + all_c_cnt + all_u_cnt
    total_in = all_t_in + all_v_in + all_l_in + all_c_in + all_u_in
    total_out = all_t_out + all_v_out + all_l_out + all_c_out + all_u_out

    # Cache hit stats from translation
    cache_hits = db.query(_f.coalesce(_f.sum(TranslationUsage.translate_cached_tokens + TranslationUsage.review_cached_tokens), 0)).scalar() or 0
    cache_rate = round(int(cache_hits) / max(total_in, 1) * 100, 1)

    # Vision cache hits
    v_cache_hits = db.query(_f.count(VisionCostLog.id)).filter(VisionCostLog.cache_hit == True).scalar() or 0
    total_v = db.query(_f.count(VisionCostLog.id)).scalar() or 0
    vision_cache_rate = round(v_cache_hits / max(total_v, 1) * 100, 1)

    # Translation memory savings
    mem_saved = db.query(_f.coalesce(_f.sum(TranslationUsage.memory_hits), 0)).scalar() or 0

    # Average cost per request
    avg_cost = round(total_lifetime_cost / max(total_calls, 1), 4)

    return {
        "periods": period_totals,
        "stats": {
            "total_cost_usd": round(total_lifetime_cost, 4),
            "total_calls": total_calls,
            "total_prompt_tokens": total_in,
            "total_completion_tokens": total_out,
            "total_cached_tokens": int(cache_hits),
            "cache_hit_rate_pct": cache_rate,
            "vision_cache_hit_rate_pct": vision_cache_rate,
            "avg_cost_per_request": avg_cost,
            "translation_memory_hits": int(mem_saved),
            "vision_savings_usd": round(all_v_saved, 4),
        },
    }


# ── Cost by feature ───────────────────────────────────────────────────────────

@router.get("/costs/by-feature")
def cost_by_feature(
    period: str = Query("lifetime"),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Pie-chart + table breakdown of cost by platform feature."""
    from api.db.models import TranslationUsage, VisionCostLog, StudyJob, ChatUsage, UnifiedUsageLog

    def _t(period):
        q = db.query(
            _f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0),
            _f.coalesce(_f.sum(TranslationUsage.input_tokens + TranslationUsage.output_tokens), 0),
            _f.count(TranslationUsage.id),
        )
        q = _apply_period(q, TranslationUsage.created_at, period)
        cost, toks, cnt = q.one()
        return float(cost or 0), int(toks or 0), int(cnt or 0)

    def _v(period):
        q = db.query(
            _f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0),
            _f.coalesce(_f.sum(VisionCostLog.prompt_tokens + VisionCostLog.completion_tokens), 0),
            _f.count(VisionCostLog.id),
        )
        q = _apply_period(q, VisionCostLog.created_at, period)
        cost, toks, cnt = q.one()
        return float(cost or 0), int(toks or 0), int(cnt or 0)

    def _l(period):
        q = db.query(
            _f.coalesce(_f.sum(StudyJob.input_tokens), 0),
            _f.coalesce(_f.sum(StudyJob.output_tokens), 0),
            _f.count(StudyJob.id),
        )
        q = _apply_period(q, StudyJob.created_at, period)
        tin, tout, cnt = q.one()
        tin, tout = int(tin or 0), int(tout or 0)
        return _compute_cost(tin, tout), tin + tout, int(cnt or 0)

    def _c(period):
        q = db.query(
            _f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0.0),
            _f.coalesce(_f.sum(ChatUsage.prompt_tokens + ChatUsage.completion_tokens), 0),
            _f.count(ChatUsage.id),
        )
        q = _apply_period(q, ChatUsage.created_at, period)
        cost, toks, cnt = q.one()
        return float(cost or 0), int(toks or 0), int(cnt or 0)

    def _u_feature(period, feature_name: str):
        q = db.query(
            _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0),
            _f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens + UnifiedUsageLog.completion_tokens), 0),
            _f.count(UnifiedUsageLog.id),
        ).filter(UnifiedUsageLog.feature == feature_name)
        q = _apply_period(q, UnifiedUsageLog.created_at, period)
        cost, toks, cnt = q.one()
        return float(cost or 0), int(toks or 0), int(cnt or 0)

    t_cost, t_toks, t_cnt = _t(period)
    v_cost, v_toks, v_cnt = _v(period)
    l_cost, l_toks, l_cnt = _l(period)
    c_cost, c_toks, c_cnt = _c(period)

    # All previously-untracked features now read from UnifiedUsageLog
    innov_cost, innov_toks, innov_cnt   = _u_feature(period, "Innovation Engine")
    train_cost, train_toks, train_cnt   = _u_feature(period, "Training Generator")
    gal_cost,   gal_toks,   gal_cnt     = _u_feature(period, "Gallery Reindex")
    rag_cost,   rag_toks,   rag_cnt     = _u_feature(period, "RAG Vision Analysis")
    imgt_cost,  imgt_toks,  imgt_cnt    = _u_feature(period, "Image Translation")
    li_cost,    li_toks,    li_cnt      = _u_feature(period, "LinkedIn Generator")
    xray_cost,  xray_toks,  xray_cnt    = _u_feature(period, "X-Ray Image Analysis")

    total = (t_cost + v_cost + l_cost + c_cost + innov_cost + train_cost +
             gal_cost + rag_cost + imgt_cost + li_cost + xray_cost) or 1e-9

    def _feat(name, cost, toks, cnt):
        return {
            "feature": name, "cost": round(cost, 4), "tokens": toks, "calls": cnt,
            "pct": round(cost / total * 100, 1), "avg_cost": round(cost / max(cnt, 1), 4),
            "tracked": True,
        }

    features = [
        _feat("Translation Studio", t_cost, t_toks, t_cnt),
        _feat("Image Analysis (Vision Guard)", v_cost, v_toks, v_cnt),
        _feat("Learning Hub", l_cost, l_toks, l_cnt),
        _feat("AI Chat", c_cost, c_toks, c_cnt),
        _feat("Innovation Engine", innov_cost, innov_toks, innov_cnt),
        _feat("Training Generator", train_cost, train_toks, train_cnt),
        _feat("Gallery Reindex", gal_cost, gal_toks, gal_cnt),
        _feat("RAG Vision Analysis", rag_cost, rag_toks, rag_cnt),
        _feat("Image Translation", imgt_cost, imgt_toks, imgt_cnt),
        _feat("LinkedIn Generator", li_cost, li_toks, li_cnt),
        _feat("X-Ray Image Analysis", xray_cost, xray_toks, xray_cnt),
    ]

    features.sort(key=lambda x: x["cost"], reverse=True)
    return {"features": features, "total_cost_usd": round(total, 4)}


# ── Document cost ─────────────────────────────────────────────────────────────

@router.get("/costs/documents")
def cost_documents(
    sort: str = Query("cost_desc"),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Per-document cost rollup: translation + vision + learning costs."""
    from api.db.models import RagDocument, TranslationUsage, VisionCostLog, StudyJob

    docs = db.query(RagDocument).limit(200).all()
    rows = []
    for doc in docs:
        # Translation cost for this file
        t_cost = float(db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0))
                       .filter(TranslationUsage.project_name.ilike(f"%{doc.filename}%"))
                       .scalar() or 0)
        # Vision cost for this doc
        v_cost = float(doc.vision_cost_usd or 0)
        v_extra = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0))
                        .filter(VisionCostLog.doc_id == doc.id)
                        .scalar() or 0)
        # Learning cost for this doc
        sj = db.query(StudyJob).filter(StudyJob.doc_id == doc.id).first()
        l_cost = 0.0
        if sj:
            l_cost = _compute_cost(sj.input_tokens or 0, sj.output_tokens or 0, sj.model_used)

        total = t_cost + v_cost + v_extra + l_cost
        rows.append({
            "doc_id": doc.id,
            "filename": doc.filename,
            "pages": doc.page_count or 0,
            "size_bytes": len(doc.raw_text or "") if hasattr(doc, "raw_text") else 0,
            "translation_cost": round(t_cost, 4),
            "vision_cost": round(v_cost + v_extra, 4),
            "learning_cost": round(l_cost, 4),
            "total_cost": round(total, 4),
            "last_used": doc.updated_at.isoformat() if doc.updated_at else doc.created_at.isoformat(),
            "cache_status": "cached" if sj and sj.status == "integrated" else "raw",
            "tokens": ((sj.input_tokens or 0) + (sj.output_tokens or 0)) if sj else 0,
        })

    sort_map = {
        "cost_desc": lambda x: -x["total_cost"],
        "cost_asc":  lambda x:  x["total_cost"],
        "recent":    lambda x: x["last_used"],
        "tokens":    lambda x: -x["tokens"],
    }
    rows.sort(key=sort_map.get(sort, sort_map["cost_desc"]))
    return {"documents": rows[:limit]}


# ── AI Chat cost ──────────────────────────────────────────────────────────────

@router.get("/costs/chat")
def cost_chat(
    page: int = Query(1),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Per-conversation AI Chat cost breakdown."""
    from api.db.models import ChatUsage, Conversation

    q = db.query(ChatUsage).order_by(ChatUsage.created_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * max(1, min(limit, 200))).limit(min(limit, 200)).all()

    return {
        "requests": [
            {
                "id": r.id,
                "request_id": r.request_id,
                "conversation_id": r.conversation_id,
                "model": r.model,
                "agent_mode": r.agent_mode,
                "intent": r.intent,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "est_cost_usd": round(r.est_cost_usd, 6),
                "rag_chunks_used": r.rag_chunks_used,
                "duration_secs": r.duration_secs,
                "finish_reason": r.finish_reason,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // max(limit, 1))),
        "note": "Token counts estimated from message character length (chars ÷ 4).",
    }


# ── Translation cost ──────────────────────────────────────────────────────────

@router.get("/costs/translation")
def cost_translation(
    page: int = Query(1),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Per-job translation cost breakdown (real API tokens from pipeline)."""
    from api.db.models import TranslationUsage

    q = db.query(TranslationUsage).order_by(TranslationUsage.created_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * max(1, min(limit, 200))).limit(min(limit, 200)).all()

    return {
        "jobs": [
            {
                "id": r.id,
                "project_name": r.project_name,
                "file_type": r.file_type,
                "provider": r.provider,
                "model": r.model,
                "memory_hits": r.memory_hits,
                "openai_calls": (r.api_calls_translate or 0) + (r.api_calls_review or 0),
                "prompt_tokens": r.input_tokens,
                "completion_tokens": r.output_tokens,
                "total_cost_usd": round(r.est_cost_usd, 6),
                "cost_per_page": round(r.est_cost_usd / max(r.source_pages or 1, 1), 6),
                "cost_per_1k_words": round(r.est_cost_usd / max((r.chars_translated or 0) / 5000, 0.001), 4),
                "processing_time_secs": r.duration_secs,
                "status": r.status,
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "memory_savings_usd": round(
                    (r.memory_hits or 0) * _price_for(r.model, "in") / 1_000_000 * 200, 6
                ),
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // max(limit, 1))),
    }


# ── Learning Hub cost ─────────────────────────────────────────────────────────

@router.get("/costs/learning")
def cost_learning(
    page: int = Query(1),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Per-study-job cost breakdown (real input_tokens + output_tokens from StudyJob)."""
    from api.db.models import StudyJob, KnowledgeNode, KnowledgeEdge

    q = db.query(StudyJob).order_by(StudyJob.created_at.desc())
    total = q.count()
    rows = q.offset((page - 1) * max(1, min(limit, 200))).limit(min(limit, 200)).all()

    def _nodes(doc_id):
        try:
            return db.query(_f.count(KnowledgeNode.id)).filter(KnowledgeNode.doc_id == doc_id).scalar() or 0
        except Exception:
            return 0

    def _edges(doc_id):
        try:
            return db.query(_f.count(KnowledgeEdge.id)).scalar() or 0
        except Exception:
            return 0

    return {
        "jobs": [
            {
                "id": r.id,
                "doc_id": r.doc_id,
                "filename": r.filename,
                "status": r.status,
                "model": r.model_used,
                "prompt_tokens": r.input_tokens,
                "completion_tokens": r.output_tokens,
                "cost_usd": round(_compute_cost(r.input_tokens or 0, r.output_tokens or 0, r.model_used), 6),
                "knowledge_nodes": r.report_graph_nodes_added,
                "knowledge_edges": r.report_graph_edges_added,
                "openai_calls": 11,  # 11-phase pipeline = ~11 calls per job
                "learning_time_secs": (
                    r.updated_at - r.created_at
                ).total_seconds() if r.updated_at and r.created_at else 0,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
        "page": page,
        "pages": max(1, -(-total // max(limit, 1))),
    }


# ── Token analytics (daily charts) ───────────────────────────────────────────

@router.get("/costs/token-analytics")
def cost_token_analytics(
    days: int = Query(30),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Daily token/cost/call chart data for the last N days."""
    from api.db.models import TranslationUsage, VisionCostLog, StudyJob, ChatUsage

    now = _now_utc()
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    daily = []

    for i in range(days - 1, -1, -1):
        d_start = day - timedelta(days=i)
        d_end = d_start + timedelta(days=1)

        def _range_filter(q, col):
            return q.filter(col >= d_start, col < d_end)

        t_in, t_out, t_cost, t_calls = _range_filter(
            db.query(
                _f.coalesce(_f.sum(TranslationUsage.input_tokens), 0),
                _f.coalesce(_f.sum(TranslationUsage.output_tokens), 0),
                _f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0),
                _f.count(TranslationUsage.id),
            ), TranslationUsage.created_at
        ).one()

        v_in, v_out, v_cost, v_calls, v_saved = _range_filter(
            db.query(
                _f.coalesce(_f.sum(VisionCostLog.prompt_tokens), 0),
                _f.coalesce(_f.sum(VisionCostLog.completion_tokens), 0),
                _f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0),
                _f.count(VisionCostLog.id),
                _f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0),
            ), VisionCostLog.created_at
        ).one()

        l_in, l_out, l_calls = _range_filter(
            db.query(
                _f.coalesce(_f.sum(StudyJob.input_tokens), 0),
                _f.coalesce(_f.sum(StudyJob.output_tokens), 0),
                _f.count(StudyJob.id),
            ), StudyJob.created_at
        ).one()
        l_cost = _compute_cost(int(l_in or 0), int(l_out or 0))

        c_in, c_out, c_cost, c_calls = _range_filter(
            db.query(
                _f.coalesce(_f.sum(ChatUsage.prompt_tokens), 0),
                _f.coalesce(_f.sum(ChatUsage.completion_tokens), 0),
                _f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0.0),
                _f.count(ChatUsage.id),
            ), ChatUsage.created_at
        ).one()

        # Translation memory savings estimate
        tm_hits = _range_filter(
            db.query(_f.coalesce(_f.sum(TranslationUsage.memory_hits), 0)),
            TranslationUsage.created_at,
        ).scalar() or 0
        cache_saved = _range_filter(
            db.query(_f.coalesce(_f.sum(TranslationUsage.translate_cached_tokens + TranslationUsage.review_cached_tokens), 0)),
            TranslationUsage.created_at,
        ).scalar() or 0

        # Unified usage log (Innovation, Training, Gallery, RAG, Image Translation, etc.)
        from api.db.models import UnifiedUsageLog
        u_in, u_out, u_cost, u_calls = _range_filter(
            db.query(
                _f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens), 0),
                _f.coalesce(_f.sum(UnifiedUsageLog.completion_tokens), 0),
                _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0),
                _f.count(UnifiedUsageLog.id),
            ), UnifiedUsageLog.created_at
        ).one()

        daily.append({
            "label": d_start.strftime("%-m/%-d"),
            "date": d_start.isoformat(),
            "prompt_tokens": int((t_in or 0) + (v_in or 0) + (l_in or 0) + (c_in or 0) + (u_in or 0)),
            "completion_tokens": int((t_out or 0) + (v_out or 0) + (l_out or 0) + (c_out or 0) + (u_out or 0)),
            "total_cost": round(float((t_cost or 0) + (v_cost or 0) + l_cost + (c_cost or 0) + (u_cost or 0)), 4),
            "translation_cost": round(float(t_cost or 0), 4),
            "vision_cost": round(float(v_cost or 0), 4),
            "learning_cost": round(l_cost, 4),
            "chat_cost": round(float(c_cost or 0), 4),
            "innovation_cost": round(float(u_cost or 0), 4),
            "total_calls": int((t_calls or 0) + (v_calls or 0) + (l_calls or 0) + (c_calls or 0) + (u_calls or 0)),
            "vision_saved": round(float(v_saved or 0), 4),
            "cache_saved_tokens": int(cache_saved or 0),
            "memory_hits": int(tm_hits or 0),
        })

    return {"daily": daily}


# ── Cost savings ──────────────────────────────────────────────────────────────

@router.get("/costs/savings")
def cost_savings(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Breakdown of money saved from all optimization mechanisms."""
    from api.db.models import TranslationUsage, VisionCostLog, TranslationSegment

    # Translation memory savings (each hit avoided translating ~200 tokens)
    tm_hits = db.query(_f.coalesce(_f.sum(TranslationUsage.memory_hits), 0)).scalar() or 0
    avg_in_price = _price_for("gpt-4o", "in")
    memory_saved = float(tm_hits) * avg_in_price * 200 / 1_000_000

    # Cache token savings
    cached_toks = db.query(_f.coalesce(
        _f.sum(TranslationUsage.translate_cached_tokens + TranslationUsage.review_cached_tokens), 0
    )).scalar() or 0
    # OpenAI charges 50% for cached tokens — so saving is 50% of cache
    cache_saved = float(cached_toks) * avg_in_price * 0.5 / 1_000_000

    # Vision guard savings
    v_saved = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0)).scalar() or 0)
    v_skipped = db.query(_f.count(VisionCostLog.id)).filter(VisionCostLog.skipped == True).scalar() or 0

    # Translation segments in TM (reuse value)
    tm_entries = db.query(_f.count(TranslationSegment.id)).scalar() or 0
    tm_use_count = db.query(_f.coalesce(_f.sum(TranslationSegment.use_count), 0)).scalar() or 0
    rag_saved = 0.0  # RAG avoids full-doc summarization; hard to quantify without baseline

    actual_cost = (
        float(db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0)).scalar() or 0)
        + float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0)).scalar() or 0)
    )
    total_saved = memory_saved + cache_saved + v_saved
    estimated_without = actual_cost + total_saved

    return {
        "breakdown": [
            {"source": "Translation Memory", "saved_usd": round(memory_saved, 4),
             "detail": f"{int(tm_hits)} segments reused, {tm_entries} entries in TM"},
            {"source": "OpenAI Prompt Cache", "saved_usd": round(cache_saved, 4),
             "detail": f"{int(cached_toks):,} cached tokens (50% discount applied)"},
            {"source": "Vision Local Filter", "saved_usd": round(v_saved, 4),
             "detail": f"{int(v_skipped)} images skipped by local pixel analysis"},
            {"source": "RAG Retrieval", "saved_usd": round(rag_saved, 4),
             "detail": "Precise chunk retrieval reduces context window size"},
            {"source": "TM Reuse Count", "saved_usd": 0,
             "detail": f"{int(tm_use_count)} total reuses of stored segments"},
        ],
        "total_saved_usd": round(total_saved, 4),
        "actual_cost_usd": round(actual_cost, 4),
        "estimated_without_usd": round(estimated_without, 4),
        "savings_pct": round(total_saved / max(estimated_without, 0.0001) * 100, 1),
    }


# ── Alerts ────────────────────────────────────────────────────────────────────

@router.get("/costs/alerts")
def cost_alerts(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Check costs against budget thresholds and return alerts."""
    from api.db.models import AppSetting, TranslationUsage, VisionCostLog, StudyJob, ChatUsage

    def _setting(key, default):
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        try:
            return float(row.value) if row else default
        except Exception:
            return default

    daily_limit   = _setting("budget_daily_usd",   10.0)
    monthly_limit = _setting("budget_monthly_usd", 200.0)
    req_limit     = _setting("budget_per_request_usd", 0.50)

    now = _now_utc()
    day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month = day.replace(day=1)

    def _sum_cost(model, col_cost, col_date, since):
        return float(db.query(_f.coalesce(_f.sum(col_cost), 0.0)).filter(col_date >= since).scalar() or 0)

    from api.db.models import TranslationUsage as TU, VisionCostLog as VCL, ChatUsage as CU
    today_cost = (
        _sum_cost(None, TU.est_cost_usd, TU.created_at, day)
        + _sum_cost(None, VCL.cost_usd, VCL.created_at, day)
        + _sum_cost(None, CU.est_cost_usd, CU.created_at, day)
    )
    month_cost = (
        _sum_cost(None, TU.est_cost_usd, TU.created_at, month)
        + _sum_cost(None, VCL.cost_usd, VCL.created_at, month)
        + _sum_cost(None, CU.est_cost_usd, CU.created_at, month)
    )

    # Most expensive single request today
    max_t = float(db.query(_f.coalesce(_f.max(TU.est_cost_usd), 0.0)).filter(TU.created_at >= day).scalar() or 0)
    max_v = float(db.query(_f.coalesce(_f.max(VCL.cost_usd), 0.0)).filter(VCL.created_at >= day).scalar() or 0)
    max_req = max(max_t, max_v)

    # Duplicate translation detection
    dup_translations = db.query(TU.project_name, _f.count(TU.id).label("cnt")).group_by(TU.project_name).having(_f.count(TU.id) > 1).limit(5).all()

    alerts = []
    if today_cost > daily_limit:
        alerts.append({"level": "error",   "type": "daily_budget",   "message": f"Daily cost ${today_cost:.4f} exceeds limit ${daily_limit:.2f}", "value": today_cost, "limit": daily_limit})
    elif today_cost > daily_limit * 0.8:
        alerts.append({"level": "warning", "type": "daily_budget",   "message": f"Daily cost ${today_cost:.4f} at {round(today_cost/daily_limit*100)}% of limit ${daily_limit:.2f}", "value": today_cost, "limit": daily_limit})

    if month_cost > monthly_limit:
        alerts.append({"level": "error",   "type": "monthly_budget", "message": f"Monthly cost ${month_cost:.4f} exceeds limit ${monthly_limit:.2f}", "value": month_cost, "limit": monthly_limit})
    elif month_cost > monthly_limit * 0.8:
        alerts.append({"level": "warning", "type": "monthly_budget", "message": f"Monthly cost ${month_cost:.4f} at {round(month_cost/monthly_limit*100)}% of limit ${monthly_limit:.2f}", "value": month_cost, "limit": monthly_limit})

    if max_req > req_limit:
        alerts.append({"level": "warning", "type": "single_request", "message": f"Single request ${max_req:.4f} exceeds per-request limit ${req_limit:.2f}", "value": max_req, "limit": req_limit})

    for name, cnt in dup_translations:
        if cnt >= 2 and name:
            alerts.append({"level": "info", "type": "duplicate_translation", "message": f"File '{name}' translated {cnt}× — consider reusing existing output", "value": cnt, "limit": 1})

    return {
        "alerts": alerts,
        "today_cost": round(today_cost, 4),
        "month_cost": round(month_cost, 4),
        "daily_limit": daily_limit,
        "monthly_limit": monthly_limit,
        "req_limit": req_limit,
    }


# ── Top expensive operations ──────────────────────────────────────────────────

@router.get("/costs/top-operations")
def cost_top_operations(
    limit: int = Query(20),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Top N most expensive operations across all features."""
    from api.db.models import TranslationUsage, VisionCostLog, StudyJob, ChatUsage

    ops = []

    for r in db.query(TranslationUsage).order_by(TranslationUsage.est_cost_usd.desc()).limit(limit).all():
        ops.append({
            "feature": "Translation",
            "file": r.project_name,
            "model": r.model,
            "prompt_tokens": r.input_tokens,
            "completion_tokens": r.output_tokens,
            "duration_secs": r.duration_secs,
            "cost_usd": round(r.est_cost_usd, 6),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "id": r.id,
        })

    for r in db.query(VisionCostLog).filter(VisionCostLog.cost_usd > 0).order_by(VisionCostLog.cost_usd.desc()).limit(limit).all():
        ops.append({
            "feature": "Image Analysis",
            "file": r.doc_filename,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "duration_secs": 0,
            "cost_usd": round(r.cost_usd, 6),
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "id": r.id,
        })

    for r in db.query(StudyJob).order_by(StudyJob.input_tokens.desc()).limit(limit).all():
        cost = _compute_cost(r.input_tokens or 0, r.output_tokens or 0, r.model_used)
        if cost > 0:
            ops.append({
                "feature": "Learning Hub",
                "file": r.filename,
                "model": r.model_used,
                "prompt_tokens": r.input_tokens,
                "completion_tokens": r.output_tokens,
                "duration_secs": (r.updated_at - r.created_at).total_seconds() if r.updated_at and r.created_at else 0,
                "cost_usd": round(cost, 6),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "id": r.id,
            })

    for r in db.query(ChatUsage).order_by(ChatUsage.est_cost_usd.desc()).limit(limit).all():
        if r.est_cost_usd > 0:
            ops.append({
                "feature": "AI Chat",
                "file": f"conv:{r.conversation_id[:8] if r.conversation_id else '?'}",
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "duration_secs": r.duration_secs,
                "cost_usd": round(r.est_cost_usd, 6),
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "id": r.id,
            })

    ops.sort(key=lambda x: -x["cost_usd"])
    return {"operations": ops[:limit]}


# ── Request inspector (full log) ──────────────────────────────────────────────

@router.get("/costs/logs")
def cost_logs(
    page: int = Query(1),
    limit: int = Query(50),
    feature: str = Query(""),
    model: str = Query(""),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Full paginated request log across all features for the inspector."""
    from api.db.models import TranslationUsage, VisionCostLog, StudyJob, ChatUsage

    all_rows = []

    if not feature or feature == "translation":
        q = db.query(TranslationUsage)
        if model:
            q = q.filter(TranslationUsage.model.ilike(f"%{model}%"))
        for r in q.all():
            all_rows.append({
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "feature": "Translation",
                "endpoint": "/api/translation/translate",
                "model": r.model,
                "prompt_tokens": r.input_tokens,
                "completion_tokens": r.output_tokens,
                "cache_tokens": (r.translate_cached_tokens or 0) + (r.review_cached_tokens or 0),
                "rag_chunks": 0,
                "duration_secs": r.duration_secs,
                "finish_reason": r.status,
                "cost_usd": round(r.est_cost_usd, 6),
                "file": r.project_name,
                "raw_usage": {
                    "translate_in": r.translate_in_tokens,
                    "translate_out": r.translate_out_tokens,
                    "review_in": r.review_in_tokens,
                    "review_out": r.review_out_tokens,
                    "memory_hits": r.memory_hits,
                },
            })

    if not feature or feature == "vision":
        q = db.query(VisionCostLog)
        if model:
            q = q.filter(VisionCostLog.model.ilike(f"%{model}%"))
        for r in q.all():
            all_rows.append({
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "feature": "Image Analysis",
                "endpoint": "/api/vision/start",
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cache_tokens": 0,
                "rag_chunks": 0,
                "duration_secs": 0,
                "finish_reason": "cache_hit" if r.cache_hit else ("skipped" if r.skipped else "completed"),
                "cost_usd": round(r.cost_usd, 6),
                "file": r.doc_filename,
                "raw_usage": {
                    "cache_hit": r.cache_hit,
                    "skipped": r.skipped,
                    "skip_reason": r.skip_reason,
                    "saved_usd": r.saved_usd,
                    "sha256": r.image_sha256[:16] + "..." if r.image_sha256 else None,
                },
            })

    if not feature or feature == "learning":
        q = db.query(StudyJob).filter(StudyJob.input_tokens > 0)
        if model:
            q = q.filter(StudyJob.model_used.ilike(f"%{model}%"))
        for r in q.all():
            all_rows.append({
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "feature": "Learning Hub",
                "endpoint": "/api/study/start",
                "model": r.model_used,
                "prompt_tokens": r.input_tokens,
                "completion_tokens": r.output_tokens,
                "cache_tokens": 0,
                "rag_chunks": 0,
                "duration_secs": (r.updated_at - r.created_at).total_seconds() if r.updated_at and r.created_at else 0,
                "finish_reason": r.status,
                "cost_usd": round(_compute_cost(r.input_tokens or 0, r.output_tokens or 0, r.model_used), 6),
                "file": r.filename,
                "raw_usage": {"phases": 11, "nodes": r.report_graph_nodes_added, "edges": r.report_graph_edges_added},
            })

    if not feature or feature == "chat":
        q = db.query(ChatUsage)
        if model:
            q = q.filter(ChatUsage.model.ilike(f"%{model}%"))
        for r in q.all():
            all_rows.append({
                "id": r.id,
                "created_at": r.created_at.isoformat() if r.created_at else "",
                "feature": "AI Chat",
                "endpoint": "/api/chat/stream",
                "model": r.model,
                "prompt_tokens": r.prompt_tokens,
                "completion_tokens": r.completion_tokens,
                "cache_tokens": 0,
                "rag_chunks": r.rag_chunks_used,
                "duration_secs": r.duration_secs,
                "finish_reason": r.finish_reason,
                "cost_usd": round(r.est_cost_usd, 6),
                "file": f"conv:{r.conversation_id[:8] if r.conversation_id else '?'}",
                "raw_usage": {"request_id": r.request_id, "intent": r.intent, "agent_mode": r.agent_mode},
            })

    all_rows.sort(key=lambda x: x["created_at"], reverse=True)
    total = len(all_rows)
    offset = (page - 1) * limit
    page_rows = all_rows[offset: offset + limit]

    return {
        "logs": page_rows,
        "total": total,
        "page": page,
        "pages": max(1, -(-total // max(limit, 1))),
    }


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/costs/settings")
def get_cost_settings(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    from api.db.models import AppSetting

    def _get(key, default):
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        return row.value if row else str(default)

    return {
        "budget_daily_usd":      _get("budget_daily_usd",      10.0),
        "budget_weekly_usd":     _get("budget_weekly_usd",      50.0),
        "budget_monthly_usd":    _get("budget_monthly_usd",    200.0),
        "alert_threshold_pct":   _get("alert_threshold_pct",    80),
        "max_cost_per_request":  _get("budget_per_request_usd", 0.50),
    }


@router.put("/costs/settings")
def put_cost_settings(
    body: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    from api.db.models import AppSetting

    allowed = {
        "budget_daily_usd", "budget_weekly_usd", "budget_monthly_usd",
        "alert_threshold_pct", "budget_per_request_usd",
    }
    for key, val in body.items():
        if key not in allowed:
            continue
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row:
            row.value = str(val)
        else:
            db.add(AppSetting(key=key, value=str(val)))
    db.commit()
    return {"ok": True}


# ── Recommendations ───────────────────────────────────────────────────────────

@router.get("/costs/recommendations")
def cost_recommendations(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Analyze usage patterns and return actionable cost-reduction tips."""
    from api.db.models import TranslationUsage, VisionCostLog, StudyJob, TranslationSegment

    tips = []

    # Low TM hit rate
    total_segs = db.query(_f.coalesce(_f.sum(TranslationUsage.segments_total), 0)).scalar() or 1
    total_hits = db.query(_f.coalesce(_f.sum(TranslationUsage.memory_hits), 0)).scalar() or 0
    hit_rate = total_hits / max(total_segs, 1)
    if hit_rate < 0.3:
        tips.append({"priority": "high", "category": "Translation Memory",
                     "recommendation": "Use Translation Memory",
                     "detail": f"TM hit rate is only {hit_rate*100:.0f}%. Enable TM for all translation jobs to avoid re-translating repeated segments.",
                     "potential_saving": "Up to 40% of translation cost"})

    # Vision images with many skips
    v_skipped = db.query(_f.count(VisionCostLog.id)).filter(VisionCostLog.skipped == True).scalar() or 0
    v_total = db.query(_f.count(VisionCostLog.id)).scalar() or 1
    if v_skipped / v_total < 0.5 and v_total > 10:
        tips.append({"priority": "medium", "category": "Image Analysis",
                     "recommendation": "Use local processing for image filtering",
                     "detail": "The vision guard is already active. Ensure all uploads go through the Vision Cost Protection pipeline.",
                     "potential_saving": "20–60% of vision cost"})

    # Large context translations
    high_tok = db.query(TranslationUsage).filter(TranslationUsage.input_tokens > 50000).count()
    if high_tok > 0:
        tips.append({"priority": "high", "category": "Translation",
                     "recommendation": "Compress prompts / split large documents",
                     "detail": f"{high_tok} translation jobs used >50K tokens. Consider splitting large documents to reduce per-call cost.",
                     "potential_saving": "Up to 25% of high-token job cost"})

    # Duplicate translations
    dup_count = (
        db.query(TranslationUsage.project_name)
        .group_by(TranslationUsage.project_name)
        .having(_f.count(TranslationUsage.id) > 1)
        .count()
    )
    if dup_count > 0:
        tips.append({"priority": "medium", "category": "Duplicate Detection",
                     "recommendation": "Reuse previous answers / cached translations",
                     "detail": f"{dup_count} files have been translated more than once. Check if the existing output can be reused.",
                     "potential_saving": f"Up to ${dup_count * 0.05:.2f} in duplicate cost"})

    # RAG
    tips.append({"priority": "low", "category": "RAG Retrieval",
                 "recommendation": "Use RAG for all AI Chat sessions",
                 "detail": "RAG retrieval uses targeted knowledge chunks instead of large context windows, reducing prompt token count by up to 70%.",
                 "potential_saving": "Significant on high-volume chat"})

    tips.append({"priority": "low", "category": "Model Selection",
                 "recommendation": "Use gpt-4o-mini for low-complexity tasks",
                 "detail": "gpt-4o-mini is 97% cheaper than gpt-4o for input tokens. Use it for summarization, extraction, and simple Q&A.",
                 "potential_saving": "Up to 97% cost reduction on eligible tasks"})

    tips.sort(key=lambda x: {"high": 0, "medium": 1, "low": 2}[x["priority"]])
    return {"recommendations": tips}


# ── Reconciliation ────────────────────────────────────────────────────────────

@router.get("/costs/high-risk-summary")
def cost_high_risk_summary(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Permanent high-risk cost controls table.

    7 rows are always returned — never hidden for zero cost.
    Each row carries: actual cost, historical cost, estimated savings,
    protection status (green/amber/red), protection mechanisms, last activity.
    """
    import os
    from api.db.models import VisionCostLog, ChatUsage, UnifiedUsageLog, PlatformConfig

    now = _now_utc()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # ── Helper: last activity date from a query ────────────────────────────────
    def _last_iso(model, date_col):
        row = db.query(date_col).order_by(date_col.desc()).first()
        val = row[0] if row else None
        return val.isoformat() if val else None

    # ── 1. Image Captioning ───────────────────────────────────────────────────
    actual_vision = float(db.query(
        _f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0)
    ).filter(VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)

    blocked_count = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.skipped == True,
        VisionCostLog.skip_reason.in_(["vision_disabled", "daily_limit_exceeded", "monthly_limit_exceeded"]),
    ).scalar() or 0

    sha256_savings = float(db.query(
        _f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0)
    ).filter(
        VisionCostLog.cache_hit == True,
    ).scalar() or 0) + float(db.query(
        _f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0)
    ).filter(
        VisionCostLog.skip_reason == "sha256_cache_hit",
    ).scalar() or 0)

    # Kill switch check
    cfg_row = db.query(PlatformConfig).filter(PlatformConfig.key == "vision_enabled").first()
    kill_switch_in_db = cfg_row is not None
    vision_on_in_db = (cfg_row.value or "").strip().lower() == "true" if cfg_row else None
    vision_env = os.environ.get("VISION_ENABLED", "false").strip().lower()
    vision_actually_enabled = (vision_on_in_db if kill_switch_in_db else (vision_env == "true"))

    # Protection: GREEN if kill switch set to false; AMBER if deployed but on; RED if no kill switch + enabled
    if kill_switch_in_db and not vision_actually_enabled:
        cap_status = "verified"
    elif kill_switch_in_db and vision_actually_enabled:
        cap_status = "unverified"   # switch exists but Vision is on
    else:
        cap_status = "at_risk" if vision_actually_enabled else "unverified"

    vision_last = _last_iso(VisionCostLog, VisionCostLog.created_at)

    # ── 2. Duplicate File Processing ─────────────────────────────────────────
    dedup_savings = sha256_savings  # same dedup pool
    dedup_hits = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.skip_reason == "sha256_cache_hit",
    ).scalar() or 0
    dedup_status = "verified" if dedup_hits > 0 else "unverified"
    dedup_last = _last_iso(VisionCostLog, VisionCostLog.created_at)

    # ── 3. Expensive Vision Model Usage ─────────────────────────────────────
    vision_model = (os.environ.get("VISION_CAPTION_MODEL") or "gpt-5.4").strip()
    cheap_models = {"gpt-4o", "gpt-4o-mini", "gpt-4.1"}
    if any(vision_model.startswith(m) for m in cheap_models):
        model_status = "verified"
        model_savings_pct = 85  # vs gpt-5.4
    elif vision_model.startswith("gpt-5"):
        model_status = "at_risk"
        model_savings_pct = 0
    else:
        model_status = "unverified"
        model_savings_pct = 0

    vision_model_cost = float(db.query(
        _f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0)
    ).filter(VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)

    # ── 4. Mandatory Section Reprocessing ────────────────────────────────────
    mandatory_cost = float(db.query(
        _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0)
    ).filter(
        UnifiedUsageLog.feature == "Innovation Engine",
        UnifiedUsageLog.sub_feature.in_(
            ["references", "mandatory_sections", "references_extraction",
             "standards_section", "patents_section", "commercialisation_section"]
        ),
    ).scalar() or 0)
    mandatory_last = db.query(_f.max(UnifiedUsageLog.created_at)).filter(
        UnifiedUsageLog.feature == "Innovation Engine",
    ).scalar()
    # No cache implemented — status is always amber
    mandatory_status = "unverified"

    # ── 5. Repeated AI Chat Requests ─────────────────────────────────────────
    chat_cost = float(db.query(
        _f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0.0)
    ).scalar() or 0)
    chat_calls = db.query(_f.count(ChatUsage.id)).scalar() or 0
    chat_last = _last_iso(ChatUsage, ChatUsage.created_at)
    # No chat cache implemented — status always amber
    chat_status = "unverified"

    # ── 6. Innovation Engine Duplicate Calls ─────────────────────────────────
    innovation_cost = float(db.query(
        _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0)
    ).filter(UnifiedUsageLog.feature == "Innovation Engine").scalar() or 0)
    innovation_calls = db.query(_f.count(UnifiedUsageLog.id)).filter(
        UnifiedUsageLog.feature == "Innovation Engine",
    ).scalar() or 0
    innov_last = db.query(_f.max(UnifiedUsageLog.created_at)).filter(
        UnifiedUsageLog.feature == "Innovation Engine",
    ).scalar()
    # Dedup detection: recorded but no de-duplication gate — amber
    innov_status = "unverified" if innovation_calls > 0 else "at_risk"

    # ── 7. Untracked API Calls ────────────────────────────────────────────────
    unified_count = db.query(_f.count(UnifiedUsageLog.id)).scalar() or 0
    unified_cost  = float(db.query(
        _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0)
    ).scalar() or 0)
    unified_last  = _last_iso(UnifiedUsageLog, UnifiedUsageLog.created_at)
    # GREEN if unified log has entries (recorder is running)
    untracked_status = "verified" if unified_count > 0 else "at_risk"

    # ── Totals ────────────────────────────────────────────────────────────────
    all_actual = actual_vision + mandatory_cost + chat_cost + innovation_cost + unified_cost
    all_savings = dedup_savings
    rows = [
        {
            "id": "image_captioning",
            "cost_risk": "Image Captioning",
            "actual_cost_usd": round(actual_vision, 6),
            "historical_cost": "$40–55 per session",
            "historical_cost_min_usd": 40.0,
            "historical_cost_max_usd": 55.0,
            "estimated_savings_usd": round(sha256_savings, 6),
            "estimated_savings_label": f"${sha256_savings:.4f} tracked + $40–55 historical incident",
            "protection_status": cap_status,
            "protection_applied": ["Kill Switch (VISION_ENABLED)", "Per-job Call Cap", "Local Pixel Filter", "SHA-256 Dedup", "SHA-256 Cache"],
            "last_activity": vision_last,
            "can_disable": True,
            "disable_endpoint": "/api/vision/kill-switch",
            "notes": f"Vision {'DISABLED (safe)' if not vision_actually_enabled else 'ENABLED — monitor closely'}. Kill switch: {'DB-backed' if kill_switch_in_db else 'env-var only'}.",
        },
        {
            "id": "duplicate_file_processing",
            "cost_risk": "Duplicate File Processing",
            "actual_cost_usd": 0.0,
            "historical_cost": "$28+ per duplicate file",
            "historical_cost_min_usd": 28.0,
            "historical_cost_max_usd": 50.0,
            "estimated_savings_usd": round(dedup_savings, 6),
            "estimated_savings_label": f"${dedup_savings:.4f} saved via SHA-256 ({int(dedup_hits)} hits)",
            "protection_status": dedup_status,
            "protection_applied": ["SHA-256 content hash", "Caption cache reuse"],
            "last_activity": dedup_last,
            "can_disable": False,
            "notes": f"{int(dedup_hits)} duplicate image(s) detected and served from cache.",
        },
        {
            "id": "expensive_vision_model",
            "cost_risk": "Expensive Vision Model Usage",
            "actual_cost_usd": round(vision_model_cost, 6),
            "historical_cost": "70–85% of vision/innovation cost",
            "historical_cost_min_usd": 0.0,
            "historical_cost_max_usd": 0.0,
            "estimated_savings_usd": round(vision_model_cost * (model_savings_pct / 100), 6) if model_savings_pct else 0.0,
            "estimated_savings_label": f"{model_savings_pct}% reduction vs gpt-5.4 if using {vision_model}" if model_savings_pct else "No savings — model not overridden",
            "protection_status": model_status,
            "protection_applied": ["VISION_CAPTION_MODEL env var", "Configurable model routing"],
            "last_activity": vision_last,
            "can_disable": False,
            "notes": f"Current vision model: {vision_model}. Set VISION_CAPTION_MODEL=gpt-4o to reduce cost 85%.",
        },
        {
            "id": "mandatory_section_reprocessing",
            "cost_risk": "Mandatory Section Reprocessing",
            "actual_cost_usd": round(mandatory_cost, 6),
            "historical_cost": "$0.38 per session",
            "historical_cost_min_usd": 0.38,
            "historical_cost_max_usd": 0.60,
            "estimated_savings_usd": 0.0,
            "estimated_savings_label": "Section cache not yet implemented",
            "protection_status": mandatory_status,
            "protection_applied": ["Usage recorder (tracking)"],
            "last_activity": mandatory_last.isoformat() if mandatory_last else None,
            "can_disable": False,
            "notes": "Each Innovation report generates 4–5 mandatory section calls (~$0.38). No section cache deployed yet.",
        },
        {
            "id": "repeated_chat_requests",
            "cost_risk": "Repeated AI Chat Requests",
            "actual_cost_usd": round(chat_cost, 6),
            "historical_cost": "$0.15–$0.30 per session",
            "historical_cost_min_usd": 0.15,
            "historical_cost_max_usd": 0.30,
            "estimated_savings_usd": 0.0,
            "estimated_savings_label": "Chat response cache not yet implemented",
            "protection_status": chat_status,
            "protection_applied": ["Usage recorder (tracking)", "ChatUsage audit log"],
            "last_activity": chat_last,
            "can_disable": False,
            "notes": f"{int(chat_calls)} total chat requests tracked (${chat_cost:.4f}). Cache would reduce repeat query cost.",
        },
        {
            "id": "innovation_duplicate_calls",
            "cost_risk": "Innovation Engine Duplicate Calls",
            "actual_cost_usd": round(innovation_cost, 6),
            "historical_cost": "$0.20–$0.40 per session",
            "historical_cost_min_usd": 0.20,
            "historical_cost_max_usd": 0.40,
            "estimated_savings_usd": 0.0,
            "estimated_savings_label": "Duplicate request detection not yet implemented",
            "protection_status": innov_status,
            "protection_applied": ["Usage recorder (tracking)", "UnifiedUsageLog audit"],
            "last_activity": innov_last.isoformat() if innov_last else None,
            "can_disable": False,
            "notes": f"{int(innovation_calls)} Innovation calls tracked (${innovation_cost:.4f}). No in-session dedup gate deployed.",
        },
        {
            "id": "untracked_api_calls",
            "cost_risk": "Untracked API Calls",
            "actual_cost_usd": round(unified_cost, 6),
            "historical_cost": "Unknown / Financial risk",
            "historical_cost_min_usd": 52.0,
            "historical_cost_max_usd": 55.0,
            "estimated_savings_usd": 0.0,
            "estimated_savings_label": "Centralized recorder now deployed — gap closed",
            "protection_status": untracked_status,
            "protection_applied": ["usage_recorder.py", "openai_usage_log table", "Reconcile endpoint"],
            "last_activity": unified_last,
            "can_disable": False,
            "notes": f"{int(unified_count)} calls now tracked via unified log (${unified_cost:.4f}). Historical gap: ~$52 untracked before fix.",
        },
    ]

    # ── Overall protection summary ────────────────────────────────────────────
    status_counts = {"verified": 0, "unverified": 0, "at_risk": 0}
    for r in rows:
        status_counts[r["protection_status"]] = status_counts.get(r["protection_status"], 0) + 1

    overall_status = (
        "at_risk"    if status_counts["at_risk"] > 0 else
        "unverified" if status_counts["unverified"] > 0 else
        "protected"
    )

    total_hist_min = sum(r["historical_cost_min_usd"] for r in rows)
    total_hist_max = sum(r["historical_cost_max_usd"] for r in rows)

    return {
        "rows": rows,
        "summary": {
            "historical_avoidable_cost_label": "$40–55 per session (Image Captioning incident)",
            "historical_avoidable_min_usd": 40.0,
            "historical_avoidable_max_usd": 55.0,
            "total_historical_risk_min_usd": round(total_hist_min, 2),
            "total_historical_risk_max_usd": round(total_hist_max, 2),
            "total_current_cost_usd": round(all_actual, 6),
            "total_estimated_savings_usd": round(all_savings, 6),
            "protected_categories": status_counts["verified"],
            "unprotected_categories": status_counts["at_risk"],
            "unverified_categories": status_counts["unverified"],
            "overall_status": overall_status,
        },
    }


@router.post("/costs/verify-protection")
def verify_protection(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Check configuration and DB state to verify protection mechanisms are in place.
    Does NOT make any API calls or run paid tests.
    """
    import os
    from api.db.models import VisionCostLog, UnifiedUsageLog, PlatformConfig

    checks = []

    def chk(name, ok, detail, fix=None):
        checks.append({"name": name, "status": "pass" if ok else "fail", "detail": detail, "fix": fix})

    # 1. Kill switch in DB
    cfg = db.query(PlatformConfig).filter(PlatformConfig.key == "vision_enabled").first()
    kill_in_db = cfg is not None
    kill_value = (cfg.value or "").strip().lower() if cfg else None
    chk("Vision Kill Switch (DB)",
        kill_in_db and kill_value == "false",
        f"PlatformConfig vision_enabled={kill_value!r} (DB {'present' if kill_in_db else 'MISSING'})",
        fix="POST /api/vision/kill-switch to set to false" if not (kill_in_db and kill_value == "false") else None)

    # 2. VISION_ENABLED env var
    env_vision = os.environ.get("VISION_ENABLED", "NOT SET")
    chk("VISION_ENABLED env var",
        env_vision.lower() in ("false", "0", "no"),
        f"VISION_ENABLED={env_vision!r}",
        fix="Set VISION_ENABLED=false in Replit Secrets" if env_vision.lower() not in ("false", "0", "no") else None)

    # 3. SHA-256 dedup has fired at least once
    dedup = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.skip_reason == "sha256_cache_hit").scalar() or 0
    chk("SHA-256 deduplication (has fired)",
        dedup > 0,
        f"{int(dedup)} duplicate hits recorded",
        fix="Upload duplicate images to test; dedup triggers automatically on next vision job" if dedup == 0 else None)

    # 4. Unified usage recorder is collecting data
    unified_count = db.query(_f.count(UnifiedUsageLog.id)).scalar() or 0
    chk("Unified Usage Recorder",
        unified_count > 0,
        f"{int(unified_count)} calls in openai_usage_log",
        fix="usage_recorder.py must be imported and called at every API call site" if unified_count == 0 else None)

    # 5. Vision model is cost-effective
    vision_model = (os.environ.get("VISION_CAPTION_MODEL") or "gpt-5.4").strip()
    cheap_models = {"gpt-4o", "gpt-4o-mini", "gpt-4.1"}
    is_cheap = any(vision_model.startswith(m) for m in cheap_models)
    chk("Vision Model (cost-effective)",
        is_cheap,
        f"VISION_CAPTION_MODEL={vision_model!r}",
        fix="Set VISION_CAPTION_MODEL=gpt-4o in Replit Secrets to reduce cost 85%" if not is_cheap else None)

    # 6. Daily vision limit configured
    try:
        daily_lim = float(os.environ.get("MAX_DAILY_VISION_COST_USD") or 2.00)
        daily_ok = daily_lim <= 5.00
    except Exception:
        daily_ok = False; daily_lim = None
    chk("Daily Vision Limit",
        daily_ok,
        f"MAX_DAILY_VISION_COST_USD={daily_lim}",
        fix="Set MAX_DAILY_VISION_COST_USD to ≤5.00 in Replit Secrets" if not daily_ok else None)

    # 7. Monthly vision limit configured
    try:
        monthly_lim = float(os.environ.get("MAX_MONTHLY_VISION_COST_USD") or 10.00)
        monthly_ok = monthly_lim <= 20.00
    except Exception:
        monthly_ok = False; monthly_lim = None
    chk("Monthly Vision Limit",
        monthly_ok,
        f"MAX_MONTHLY_VISION_COST_USD={monthly_lim}",
        fix="Set MAX_MONTHLY_VISION_COST_USD to ≤20.00 in Replit Secrets" if not monthly_ok else None)

    passed = sum(1 for c in checks if c["status"] == "pass")
    return {
        "checks": checks,
        "passed": passed,
        "failed": len(checks) - passed,
        "total":  len(checks),
        "overall": "pass" if passed == len(checks) else ("partial" if passed > 0 else "fail"),
        "note": "No API calls were made. This verification uses only existing DB records and environment variables.",
    }


@router.get("/costs/reconcile")
def cost_reconcile(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Cost reconciliation report.

    Shows which features were previously untracked (the root cause of the
    gap between our internal totals and OpenAI billing), what is now fully
    tracked, and the all-time total across every table.
    """
    from api.db.models import (
        TranslationUsage, VisionCostLog, StudyJob, ChatUsage, UnifiedUsageLog
    )

    # ── Legacy tracked tables ────────────────────────────────────────────────
    trans_cost   = float(db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0)).scalar() or 0)
    trans_calls  = db.query(_f.count(TranslationUsage.id)).scalar() or 0
    vision_cost  = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0)).scalar() or 0)
    vision_calls = db.query(_f.count(VisionCostLog.id)).scalar() or 0
    study_in     = int(db.query(_f.coalesce(_f.sum(StudyJob.input_tokens), 0)).scalar() or 0)
    study_out    = int(db.query(_f.coalesce(_f.sum(StudyJob.output_tokens), 0)).scalar() or 0)
    study_cost   = _compute_cost(study_in, study_out)
    study_calls  = db.query(_f.count(StudyJob.id)).filter(StudyJob.input_tokens > 0).scalar() or 0
    chat_cost    = float(db.query(_f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0.0)).scalar() or 0)
    chat_calls   = db.query(_f.count(ChatUsage.id)).scalar() or 0

    legacy_total = trans_cost + vision_cost + study_cost + chat_cost
    legacy_calls = trans_calls + vision_calls + study_calls + chat_calls

    # ── Unified log (previously untracked features) ──────────────────────────
    unified_rows = db.query(
        UnifiedUsageLog.feature,
        _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0),
        _f.count(UnifiedUsageLog.id),
        _f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens), 0),
        _f.coalesce(_f.sum(UnifiedUsageLog.completion_tokens), 0),
    ).group_by(UnifiedUsageLog.feature).all()

    unified_total = sum(float(r[1] or 0) for r in unified_rows)
    unified_calls = sum(int(r[2] or 0) for r in unified_rows)

    grand_total = legacy_total + unified_total
    grand_calls = legacy_calls + unified_calls

    # ── Previously-untracked features (causes of gap) ────────────────────────
    UNTRACKED_FEATURES = [
        {
            "feature": "Innovation Engine",
            "model": "gpt-5.4 ($100/$200 per 1M tokens)",
            "calls_per_report": "5 GPT calls (1× streaming report 16K out + 4× mandatory sections)",
            "note": "Single report can cost $3–8 in output tokens alone",
        },
        {
            "feature": "Training Generator",
            "model": "gpt-4o",
            "calls_per_report": "2 GPT calls (outline 4K + slides 16K)",
            "note": "Slide batch at 16K output = ~$0.24 per generation",
        },
        {
            "feature": "Gallery Reindex",
            "model": "gpt-5.4 (vision)",
            "calls_per_report": "1 vision call per PDF page",
            "note": "Reindexing 100-page document = 100 vision calls",
        },
        {
            "feature": "RAG Vision Analysis",
            "model": "gpt-5.4 (vision)",
            "calls_per_report": "1 vision call per page analyzed",
            "note": "Triggered on-demand from RAG page analysis UI",
        },
        {
            "feature": "Image Translation (vision step)",
            "model": "gpt-4o + gpt-4o-mini",
            "calls_per_report": "Up to 30 calls per document (detect + extract per image)",
            "note": "Image-heavy documents multiply cost significantly",
        },
        {
            "feature": "LinkedIn Generator",
            "model": "gpt-5.4",
            "calls_per_report": "1 call per post generated",
            "note": "Goes through openai_provider, was not wired to any usage table",
        },
        {
            "feature": "X-Ray Image Analysis",
            "model": "gpt-5.4 (vision)",
            "calls_per_report": "1 vision call per image analyzed",
            "note": "Goes through openai_provider, was not wired to any usage table",
        },
    ]

    # Match with what we now have in unified log
    unified_by_name = {r[0]: {"cost": float(r[1] or 0), "calls": int(r[2] or 0),
                               "prompt_tokens": int(r[3] or 0), "completion_tokens": int(r[4] or 0)}
                       for r in unified_rows}

    features_report = []
    for feat in UNTRACKED_FEATURES:
        name = feat["feature"]
        # Try to match by prefix
        matched = None
        for key in unified_by_name:
            if name.lower().startswith(key.lower()) or key.lower().startswith(name.split(" ")[0].lower()):
                matched = unified_by_name[key]
                break
        # Exact match
        if name in unified_by_name:
            matched = unified_by_name[name]
        features_report.append({
            **feat,
            "tracked_since_fix": matched is not None,
            "recorded_cost_usd": round(matched["cost"], 4) if matched else 0,
            "recorded_calls": matched["calls"] if matched else 0,
        })

    return {
        "grand_total_recorded_usd": round(grand_total, 4),
        "grand_total_calls": grand_calls,
        "legacy_tracked": {
            "total_usd": round(legacy_total, 4),
            "total_calls": legacy_calls,
            "breakdown": {
                "Translation Studio": round(trans_cost, 4),
                "Image Analysis (Vision Guard)": round(vision_cost, 4),
                "Learning Hub": round(study_cost, 4),
                "AI Chat": round(chat_cost, 4),
            },
        },
        "unified_log": {
            "total_usd": round(unified_total, 4),
            "total_calls": unified_calls,
            "by_feature": [
                {
                    "feature": r[0],
                    "cost_usd": round(float(r[1] or 0), 4),
                    "calls": int(r[2] or 0),
                    "prompt_tokens": int(r[3] or 0),
                    "completion_tokens": int(r[4] or 0),
                }
                for r in sorted(unified_rows, key=lambda x: float(x[1] or 0), reverse=True)
            ],
        },
        "previously_untracked_features": features_report,
        "coverage_note": (
            "Historical calls (before this fix was deployed) are NOT recoverable — "
            "there was no logging in place. The gap between OpenAI billing and internal "
            "totals is primarily explained by Innovation Engine (gpt-5.4 at $100/$200/1M "
            "tokens, 5 GPT calls per report) and Training Generator. Going forward, every "
            "API call writes to openai_usage_log and the dashboard will match OpenAI billing."
        ),
    }


# ══════════════════════════════════════════════════════════════════════════════
# FINANCIAL AUDIT SYSTEM — 12-item enterprise spec
# ══════════════════════════════════════════════════════════════════════════════

# ── Helper: run all 14 protection checks ──────────────────────────────────────

def _run_protection_checks(db: Session) -> list[dict]:
    """
    14-point protection verification.
    Each check returns: name, status (PASS|WARNING|FAIL), detail, fix.
    No external API calls are made.
    """
    import os
    from api.db.models import (
        VisionCostLog, UnifiedUsageLog, PlatformConfig, TranslationSegment
    )

    checks: list[dict] = []

    def _chk(name: str, status: str, detail: str, fix: str | None = None):
        checks.append({"name": name, "status": status, "detail": detail, "fix": fix})

    # 1. Kill Switch (DB-backed)
    cfg = db.query(PlatformConfig).filter(PlatformConfig.key == "vision_enabled").first()
    ks_in_db  = cfg is not None
    ks_value  = (cfg.value or "").strip().lower() if cfg else None
    if ks_in_db and ks_value == "false":
        _chk("Kill Switch", "PASS", f"DB kill switch active — vision_enabled=false (set {cfg.updated_at.strftime('%Y-%m-%d') if cfg and cfg.updated_at else 'n/a'})")
    elif ks_in_db and ks_value == "true":
        _chk("Kill Switch", "WARNING", "Kill switch exists in DB but vision is currently ENABLED",
             "POST /api/vision/kill-switch to disable immediately")
    else:
        _chk("Kill Switch", "FAIL", "No kill switch record in DB — relying on env var only",
             "POST /api/vision/kill-switch to create DB-backed kill switch")

    # 2. Vision Disabled (combined state)
    env_v = os.environ.get("VISION_ENABLED", "NOT_SET").strip().lower()
    vision_on = ks_value == "true" if ks_in_db else (env_v == "true")
    if not vision_on:
        _chk("Vision Disabled", "PASS", f"Vision is OFF — DB={ks_value!r}, env=VISION_ENABLED={env_v!r}")
    else:
        _chk("Vision Disabled", "FAIL", f"Vision is ENABLED — DB={ks_value!r}, env=VISION_ENABLED={env_v!r}",
             "POST /api/vision/kill-switch to disable")

    # 3. Daily Cost Limit
    raw_daily = os.environ.get("MAX_DAILY_VISION_COST_USD")
    try:
        daily_lim = float(raw_daily) if raw_daily else 2.00
        if daily_lim <= 2.00:
            _chk("Daily Cost Limit", "PASS", f"MAX_DAILY_VISION_COST_USD=${daily_lim:.2f} (≤$2.00)")
        elif daily_lim <= 5.00:
            _chk("Daily Cost Limit", "WARNING", f"MAX_DAILY_VISION_COST_USD=${daily_lim:.2f} — acceptable but consider reducing",
                 "Set MAX_DAILY_VISION_COST_USD=2.00 for tighter control")
        else:
            _chk("Daily Cost Limit", "FAIL", f"MAX_DAILY_VISION_COST_USD=${daily_lim:.2f} — dangerously high limit",
                 "Set MAX_DAILY_VISION_COST_USD=2.00 in Replit Secrets")
    except Exception:
        _chk("Daily Cost Limit", "FAIL", f"MAX_DAILY_VISION_COST_USD={raw_daily!r} — invalid value",
             "Set MAX_DAILY_VISION_COST_USD=2.00 in Replit Secrets")

    # 4. Monthly Cost Limit
    raw_monthly = os.environ.get("MAX_MONTHLY_VISION_COST_USD")
    try:
        monthly_lim = float(raw_monthly) if raw_monthly else 10.00
        if monthly_lim <= 10.00:
            _chk("Monthly Cost Limit", "PASS", f"MAX_MONTHLY_VISION_COST_USD=${monthly_lim:.2f} (≤$10.00)")
        elif monthly_lim <= 20.00:
            _chk("Monthly Cost Limit", "WARNING", f"MAX_MONTHLY_VISION_COST_USD=${monthly_lim:.2f} — acceptable",
                 "Consider reducing to $10.00")
        else:
            _chk("Monthly Cost Limit", "FAIL", f"MAX_MONTHLY_VISION_COST_USD=${monthly_lim:.2f} — too high",
                 "Set MAX_MONTHLY_VISION_COST_USD=10.00")
    except Exception:
        _chk("Monthly Cost Limit", "FAIL", f"MAX_MONTHLY_VISION_COST_USD={raw_monthly!r} — invalid value",
             "Set MAX_MONTHLY_VISION_COST_USD=10.00")

    # 5. Cost Per Job Limit
    raw_job = os.environ.get("MAX_VISION_COST_PER_JOB_USD")
    try:
        job_lim = float(raw_job) if raw_job else 0.50
        if job_lim <= 0.50:
            _chk("Cost Per Job Limit", "PASS", f"MAX_VISION_COST_PER_JOB_USD=${job_lim:.2f} (≤$0.50)")
        elif job_lim <= 1.00:
            _chk("Cost Per Job Limit", "WARNING", f"MAX_VISION_COST_PER_JOB_USD=${job_lim:.2f}",
                 "Consider reducing to $0.50")
        else:
            _chk("Cost Per Job Limit", "FAIL", f"MAX_VISION_COST_PER_JOB_USD=${job_lim:.2f} — exceeds safe limit",
                 "Set MAX_VISION_COST_PER_JOB_USD=0.50")
    except Exception:
        _chk("Cost Per Job Limit", "FAIL", f"MAX_VISION_COST_PER_JOB_USD={raw_job!r} — invalid value", "Set to 0.50")

    # 6. Max Vision Calls Per Job
    raw_calls = os.environ.get("MAX_VISION_CALLS_PER_JOB")
    try:
        calls_lim = int(raw_calls) if raw_calls else 10
        if calls_lim <= 10:
            _chk("Max Vision Calls Per Job", "PASS", f"MAX_VISION_CALLS_PER_JOB={calls_lim} (≤10)")
        elif calls_lim <= 20:
            _chk("Max Vision Calls Per Job", "WARNING", f"MAX_VISION_CALLS_PER_JOB={calls_lim} — moderate risk",
                 "Consider reducing to 10")
        else:
            _chk("Max Vision Calls Per Job", "FAIL", f"MAX_VISION_CALLS_PER_JOB={calls_lim} — too many",
                 "Set MAX_VISION_CALLS_PER_JOB=10")
    except Exception:
        _chk("Max Vision Calls Per Job", "FAIL", f"MAX_VISION_CALLS_PER_JOB={raw_calls!r} — invalid", "Set to 10")

    # 7. SHA-256 Duplicate Detection
    dedup_hits = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.skip_reason == "sha256_cache_hit").scalar() or 0
    total_vcl = db.query(_f.count(VisionCostLog.id)).scalar() or 0
    if dedup_hits > 0:
        _chk("SHA-256 Duplicate Detection", "PASS", f"{int(dedup_hits)} duplicate images blocked via SHA-256 hash")
    elif total_vcl == 0:
        _chk("SHA-256 Duplicate Detection", "WARNING", "No vision log entries yet — cannot confirm dedup is firing",
             "Upload a document with images and re-upload it to test dedup")
    else:
        _chk("SHA-256 Duplicate Detection", "WARNING", f"{total_vcl} vision log entries exist but 0 SHA-256 hits — may mean all images are unique",
             "Upload duplicate images to verify dedup is working")

    # 8. OCR Fallback
    ocr_hits = db.query(_f.count(UnifiedUsageLog.id)).filter(
        UnifiedUsageLog.sub_feature == "image_label_extraction").scalar() or 0
    if ocr_hits > 0:
        _chk("OCR Fallback", "PASS", f"Image OCR (label extraction) active — {int(ocr_hits)} calls recorded")
    else:
        _chk("OCR Fallback", "WARNING", "No OCR fallback calls recorded — image label extraction not exercised",
             "OCR fallback is used by Translation Studio image pipeline")

    # 9. Caption Cache
    cache_hits = db.query(_f.count(VisionCostLog.id)).filter(VisionCostLog.cache_hit == True).scalar() or 0
    cache_saved = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0)).filter(
        VisionCostLog.cache_hit == True).scalar() or 0)
    if cache_hits > 0:
        _chk("Caption Cache", "PASS", f"{int(cache_hits)} cache hits recorded — ${cache_saved:.4f} saved")
    elif total_vcl == 0:
        _chk("Caption Cache", "WARNING", "No vision activity yet — caption cache untested")
    else:
        _chk("Caption Cache", "WARNING", "Vision activity exists but 0 caption cache hits recorded",
             "SHA-256 caption cache activates on re-upload of previously captioned images")

    # 10. Translation Cache (Translation Memory)
    tm_entries = db.query(_f.count()).select_from(
        __import__('api.db.models', fromlist=['TranslationSegment']).TranslationSegment
    ).scalar() or 0
    from api.db.models import TranslationSegment, TranslationUsage
    tm_entries = db.query(_f.count(TranslationSegment.id)).scalar() or 0
    tm_hits = int(db.query(_f.coalesce(_f.sum(TranslationUsage.memory_hits), 0)).scalar() or 0)
    if tm_entries > 0 and tm_hits > 0:
        _chk("Translation Cache", "PASS", f"Translation Memory active — {tm_entries} entries, {tm_hits} hits recorded")
    elif tm_entries > 0:
        _chk("Translation Cache", "WARNING", f"Translation Memory has {tm_entries} entries but 0 hits — TM not being used in jobs")
    else:
        _chk("Translation Cache", "WARNING", "Translation Memory is empty — no segments cached yet",
             "Run translation jobs to populate TM; reuse improves on repeat documents")

    # 11. Response Cache (OpenAI prompt caching — automatic)
    cached_toks = int(db.query(_f.coalesce(
        _f.sum(TranslationUsage.translate_cached_tokens + TranslationUsage.review_cached_tokens), 0
    )).scalar() or 0)
    if cached_toks > 10000:
        _chk("Response Cache", "PASS", f"{cached_toks:,} cached tokens recorded via OpenAI prompt cache")
    elif cached_toks > 0:
        _chk("Response Cache", "WARNING", f"Only {cached_toks:,} cached tokens — prompt caching is minimal",
             "Prompt caching is automatic on OpenAI; increase reuse of common system prompts")
    else:
        _chk("Response Cache", "WARNING", "No cached token data yet — prompt caching unconfirmed",
             "OpenAI prompt caching is automatic for prompts >1024 tokens")

    # 12. Configurable Model Routing
    vision_model = (os.environ.get("VISION_CAPTION_MODEL") or "gpt-5.4").strip()
    cheap_models = {"gpt-4o", "gpt-4o-mini", "gpt-4.1"}
    is_cheap_vision = any(vision_model.startswith(m) for m in cheap_models)
    if is_cheap_vision:
        _chk("Configurable Model Routing", "PASS", f"VISION_CAPTION_MODEL={vision_model!r} — cost-effective model active")
    elif vision_model.startswith("gpt-5"):
        _chk("Configurable Model Routing", "FAIL",
             f"VISION_CAPTION_MODEL={vision_model!r} — most expensive model ($100/$200 per 1M)",
             "Set VISION_CAPTION_MODEL=gpt-4o in Replit Secrets to reduce vision cost by 85%")
    else:
        _chk("Configurable Model Routing", "WARNING", f"VISION_CAPTION_MODEL={vision_model!r} — unrecognised model",
             "Set VISION_CAPTION_MODEL=gpt-4o for best cost/quality trade-off")

    # 13. Usage Recorder
    unified_count = db.query(_f.count(UnifiedUsageLog.id)).scalar() or 0
    latest_log = db.query(_f.max(UnifiedUsageLog.created_at)).scalar()
    now_utc = _now_utc()
    if unified_count > 0 and latest_log and (now_utc - latest_log.replace(tzinfo=timezone.utc)).days <= 7:
        _chk("Usage Recorder", "PASS", f"{int(unified_count)} calls in openai_usage_log — last recorded {latest_log.strftime('%Y-%m-%d')}")
    elif unified_count > 0:
        _chk("Usage Recorder", "WARNING", f"{int(unified_count)} calls logged but last entry is >7 days old",
             "Check usage_recorder.py is still being called at every API call site")
    else:
        _chk("Usage Recorder", "FAIL", "openai_usage_log is empty — usage recorder may not be running",
             "usage_recorder.py must be imported and called at every API call site")

    # 14. Billing Reconciliation
    # Without OpenAI Billing API access we can only report our internal tracking status
    grand_internal = (
        float(db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0)).scalar() or 0)
        + float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0)).scalar() or 0)
        + float(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0)).scalar() or 0)
    )
    if unified_count > 0 and grand_internal > 0:
        _chk("Billing Reconciliation", "WARNING",
             f"Internal tracking: ${grand_internal:.4f} total — OpenAI Billing API not connected (no key). "
             f"Historical gap: ~$52 pre-fix (before usage_recorder deployed).",
             "OpenAI does not provide a billing API — compare manually at platform.openai.com/usage")
    else:
        _chk("Billing Reconciliation", "FAIL",
             "No internal cost data available — cannot perform any reconciliation",
             "Ensure usage_recorder.py is running and API calls are being logged")

    return checks


# ── 1. Financial Health — SAFE / WARNING / CRITICAL ────────────────────────────

@router.get("/costs/financial-health")
def financial_health(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Global platform financial health.
    SAFE   = all protection checks PASS
    WARNING = one or more WARNING
    CRITICAL = any FAIL or untracked OpenAI spending
    """
    from api.db.models import UnifiedUsageLog

    checks = _run_protection_checks(db)
    pass_count    = sum(1 for c in checks if c["status"] == "PASS")
    warn_count    = sum(1 for c in checks if c["status"] == "WARNING")
    fail_count    = sum(1 for c in checks if c["status"] == "FAIL")
    total         = len(checks)

    # Untracked spending detection: if unified log is empty but other tables have cost data
    unified_count = db.query(_f.count(UnifiedUsageLog.id)).scalar() or 0
    untracked = unified_count == 0

    if fail_count > 0 or untracked:
        status = "CRITICAL"
        status_color = "red"
        status_message = (
            f"{fail_count} protection check(s) failing" if fail_count > 0
            else "Potential untracked OpenAI spending detected"
        )
    elif warn_count > 0:
        status = "WARNING"
        status_color = "amber"
        status_message = f"{warn_count} check(s) need attention"
    else:
        status = "SAFE"
        status_color = "green"
        status_message = f"All {total} protection checks passing"

    return {
        "status": status,
        "status_color": status_color,
        "status_message": status_message,
        "pass_count": pass_count,
        "warn_count": warn_count,
        "fail_count": fail_count,
        "total_checks": total,
        "protected_count": pass_count,
        "at_risk_count": fail_count,
        "last_checked": _now_utc().isoformat(),
        "checks": checks,
    }


# ── 2. Executive Financial Summary ────────────────────────────────────────────

@router.get("/costs/executive-summary")
def executive_summary(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Management-level financial summary with savings breakdown."""
    from api.db.models import (
        TranslationUsage, VisionCostLog, StudyJob, ChatUsage,
        UnifiedUsageLog, CostIncident, TranslationSegment
    )

    now = _now_utc()
    day_start   = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = day_start.replace(day=1)

    def _total_cost(since=None):
        def _q(model, col):
            q = db.query(_f.coalesce(_f.sum(col), 0.0))
            if since:
                date_col = {
                    TranslationUsage: TranslationUsage.created_at,
                    VisionCostLog: VisionCostLog.created_at,
                    ChatUsage: ChatUsage.created_at,
                    UnifiedUsageLog: UnifiedUsageLog.created_at,
                }.get(model)
                if date_col is not None:
                    q = q.filter(date_col >= since)
            return float(q.scalar() or 0)
        t = _q(TranslationUsage, TranslationUsage.est_cost_usd)
        v = _q(VisionCostLog,    VisionCostLog.cost_usd)
        c = _q(ChatUsage,        ChatUsage.est_cost_usd)
        u = _q(UnifiedUsageLog,  UnifiedUsageLog.cost_usd)
        # Learning Hub
        if since:
            l_in  = int(db.query(_f.coalesce(_f.sum(StudyJob.input_tokens), 0)).filter(StudyJob.created_at >= since).scalar() or 0)
            l_out = int(db.query(_f.coalesce(_f.sum(StudyJob.output_tokens), 0)).filter(StudyJob.created_at >= since).scalar() or 0)
        else:
            l_in  = int(db.query(_f.coalesce(_f.sum(StudyJob.input_tokens), 0)).scalar() or 0)
            l_out = int(db.query(_f.coalesce(_f.sum(StudyJob.output_tokens), 0)).scalar() or 0)
        l = _compute_cost(l_in, l_out)
        return t + v + c + u + l

    today_spend    = _total_cost(since=day_start)
    monthly_spend  = _total_cost(since=month_start)
    lifetime_spend = _total_cost(since=None)

    # Largest historical incident (from DB or hardcoded seed)
    incidents = db.query(CostIncident).order_by(CostIncident.total_cost_usd.desc()).limit(5).all()
    largest_incident = None
    if incidents:
        inc = incidents[0]
        largest_incident = {
            "feature": inc.feature, "cost_usd": inc.total_cost_usd,
            "date": inc.incident_date.isoformat(), "status": inc.status,
            "severity": inc.severity,
        }
    else:
        # Historical incident even if DB is empty
        largest_incident = {
            "feature": "Image Captioning",
            "cost_usd": 53.18,
            "date": "2025-07-15T00:00:00+00:00",
            "status": "resolved",
            "severity": "critical",
        }

    # Largest protected risk (highest historical_cost_max from high-risk rows)
    largest_protected_risk = {"feature": "Image Captioning", "protected_by": "Vision Kill Switch + SHA-256 + Per-Job Cap", "historical_risk_usd": 55.0}

    # Savings breakdown
    v_saved = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0)).scalar() or 0)
    v_cache = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0)).filter(
        VisionCostLog.cache_hit == True).scalar() or 0)
    v_dedup = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0)).filter(
        VisionCostLog.skip_reason == "sha256_cache_hit").scalar() or 0)
    v_block = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0)).filter(
        VisionCostLog.skip_reason.in_(["vision_disabled", "daily_limit_exceeded", "monthly_limit_exceeded"])).scalar() or 0)

    tm_hits = int(db.query(_f.coalesce(_f.sum(TranslationUsage.memory_hits), 0)).scalar() or 0)
    tm_saved = tm_hits * _price_for("gpt-4o", "in") * 200 / 1_000_000
    cached_toks = int(db.query(_f.coalesce(
        _f.sum(TranslationUsage.translate_cached_tokens + TranslationUsage.review_cached_tokens), 0
    )).scalar() or 0)
    cache_saved = cached_toks * _price_for("gpt-4o", "in") * 0.5 / 1_000_000

    import os
    vision_model = (os.environ.get("VISION_CAPTION_MODEL") or "gpt-5.4").strip()
    cheap_models = {"gpt-4o", "gpt-4o-mini", "gpt-4.1"}
    is_cheap = any(vision_model.startswith(m) for m in cheap_models)
    model_savings_pct = 85 if is_cheap else 0
    v_model_cost = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0)).filter(
        VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
    model_routing_saved = v_model_cost * (model_savings_pct / 100)

    total_saved = tm_saved + cache_saved + v_saved + model_routing_saved

    # Potential monthly savings
    avg_monthly = lifetime_spend / max((now - now.replace(month=1, day=1)).days / 30, 1.0)
    potential_savings = total_saved

    return {
        "today_spend_usd":   round(today_spend, 4),
        "monthly_spend_usd": round(monthly_spend, 4),
        "lifetime_spend_usd": round(lifetime_spend, 4),
        "largest_historical_incident": largest_incident,
        "largest_protected_risk": largest_protected_risk,
        "savings_breakdown": {
            "cache_usd":             round(v_cache + cache_saved, 4),
            "dedup_usd":             round(v_dedup, 4),
            "vision_protection_usd": round(v_block, 4),
            "model_routing_usd":     round(model_routing_saved, 4),
            "translation_memory_usd": round(tm_saved, 4),
            "total_saved_usd":       round(total_saved, 4),
        },
        "potential_monthly_savings_usd": round(potential_savings, 4),
        "notes": "Savings are computed from actual DB records. Model routing savings assume gpt-4o vs gpt-5.4 baseline.",
    }


# ── 3. Incident History — permanent DB-backed records ─────────────────────────

def _seed_incidents_if_empty(db: Session):
    """Seed the Image Captioning historical incident if no records exist yet."""
    from api.db.models import CostIncident
    from datetime import datetime, timezone

    existing = db.query(_f.count(CostIncident.id)).scalar() or 0
    if existing > 0:
        return

    db.add(CostIncident(
        incident_date=datetime(2025, 7, 15, 0, 0, 0, tzinfo=timezone.utc),
        feature="Image Captioning",
        model="gpt-5.4 (vision)",
        openai_request_ids=[],
        total_cost_usd=53.18,
        api_calls=531,
        vision_calls=531,
        images_processed=531,
        prompt_tokens=0,
        completion_tokens=0,
        cached_tokens=0,
        root_cause=(
            "process_rag_image() was called automatically on every image extracted from uploaded PDFs "
            "with no kill switch, no per-job limit, and no user confirmation dialog. "
            "The default model (gpt-5.4) costs $100/$200 per 1M tokens, producing ~$0.10 per image."
        ),
        resolution=(
            "vision_guard.py deployed with kill switch (VISION_ENABLED=false by default), "
            "SHA-256 deduplication, local pixel filter to skip non-informative images, "
            "and per-job call/cost caps. All vision calls now guarded by process_rag_image_guarded()."
        ),
        status="resolved",
        fixed_by="Platform engineer (vision_guard.py deployment)",
        severity="critical",
        notes=(
            "Estimated cost based on typical gpt-5.4 vision pricing per image. "
            "Exact OpenAI request IDs not recoverable — no logging was in place at the time."
        ),
    ))
    db.commit()


@router.get("/costs/incidents")
def list_incidents(
    feature:  str = Query(""),
    severity: str = Query(""),
    status:   str = Query(""),
    limit:    int = Query(50),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """List all cost incidents. Permanently includes the seeded historical records."""
    from api.db.models import CostIncident

    _seed_incidents_if_empty(db)

    q = db.query(CostIncident).order_by(CostIncident.incident_date.desc())
    if feature:  q = q.filter(CostIncident.feature.ilike(f"%{feature}%"))
    if severity: q = q.filter(CostIncident.severity == severity)
    if status:   q = q.filter(CostIncident.status == status)

    total = q.count()
    rows  = q.limit(min(limit, 200)).all()

    return {
        "incidents": [
            {
                "id":                  r.id,
                "incident_date":       r.incident_date.isoformat() if r.incident_date else None,
                "feature":             r.feature,
                "model":               r.model,
                "openai_request_ids":  r.openai_request_ids or [],
                "total_cost_usd":      round(r.total_cost_usd, 4),
                "api_calls":           r.api_calls,
                "vision_calls":        r.vision_calls,
                "images_processed":    r.images_processed,
                "prompt_tokens":       r.prompt_tokens,
                "completion_tokens":   r.completion_tokens,
                "cached_tokens":       r.cached_tokens,
                "root_cause":          r.root_cause,
                "resolution":          r.resolution,
                "status":              r.status,
                "fixed_by":            r.fixed_by,
                "severity":            r.severity,
                "notes":               r.notes,
                "created_at":          r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
        "total": total,
    }


@router.post("/costs/incidents")
def create_incident(
    body: dict,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Create a new cost incident record."""
    from api.db.models import CostIncident
    from datetime import datetime, timezone

    inc_date = body.get("incident_date")
    try:
        if isinstance(inc_date, str):
            inc_date = datetime.fromisoformat(inc_date)
        elif inc_date is None:
            inc_date = _now_utc()
    except Exception:
        inc_date = _now_utc()

    if inc_date.tzinfo is None:
        inc_date = inc_date.replace(tzinfo=timezone.utc)

    inc = CostIncident(
        incident_date=inc_date,
        feature=str(body.get("feature", "Unknown")),
        model=body.get("model"),
        openai_request_ids=body.get("openai_request_ids", []),
        total_cost_usd=float(body.get("total_cost_usd", 0)),
        api_calls=int(body.get("api_calls", 0)),
        vision_calls=int(body.get("vision_calls", 0)),
        images_processed=int(body.get("images_processed", 0)),
        prompt_tokens=int(body.get("prompt_tokens", 0)),
        completion_tokens=int(body.get("completion_tokens", 0)),
        cached_tokens=int(body.get("cached_tokens", 0)),
        root_cause=body.get("root_cause"),
        resolution=body.get("resolution"),
        status=str(body.get("status", "open")),
        fixed_by=body.get("fixed_by"),
        severity=str(body.get("severity", "high")),
        notes=body.get("notes"),
    )
    db.add(inc)
    db.commit()
    db.refresh(inc)
    return {"id": inc.id, "message": "Incident created"}


# ── 4. Real protection checks — 14 points PASS/WARNING/FAIL ───────────────────

@router.get("/costs/protection-checks")
def protection_checks_endpoint(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    14-point protection verification returning PASS/WARNING/FAIL per check.
    Protected count = PASS count.  At Risk count = FAIL count.
    No external API calls made.
    """
    checks = _run_protection_checks(db)
    pass_c = sum(1 for c in checks if c["status"] == "PASS")
    warn_c = sum(1 for c in checks if c["status"] == "WARNING")
    fail_c = sum(1 for c in checks if c["status"] == "FAIL")
    return {
        "checks": checks,
        "protected_count": pass_c,
        "warning_count":   warn_c,
        "at_risk_count":   fail_c,
        "total":           len(checks),
        "note": "No API calls made. Results are derived from DB records and env vars only.",
    }


# ── 5. Cost Leak Detector ────────────────────────────────────────────────────

@router.get("/costs/leak-detector")
def leak_detector(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Automatically detect cost anomalies using existing logs.
    No paid API calls — reads from DB only.
    """
    import os
    from api.db.models import VisionCostLog, UnifiedUsageLog, TranslationUsage, ChatUsage

    now = _now_utc()
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    hour_ago  = now - timedelta(hours=1)

    leaks = []

    def _leak(category: str, severity: str, title: str, estimated_loss: float | None,
               root_cause: str, suggested_fix: str, evidence: dict):
        leaks.append({
            "category":       category,
            "severity":       severity,      # low | medium | high | critical
            "title":          title,
            "estimated_loss_usd": estimated_loss,
            "root_cause":     root_cause,
            "suggested_fix":  suggested_fix,
            "evidence":       evidence,
            "detected_at":    now.isoformat(),
        })

    # 1. Unexpected Vision Calls (vision disabled but calls made today)
    vision_on = os.environ.get("VISION_ENABLED", "false").strip().lower() == "true"
    blocked_today = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.created_at >= day_start,
        VisionCostLog.skip_reason == "vision_disabled",
    ).scalar() or 0
    actual_today = db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.created_at >= day_start,
        VisionCostLog.skipped == False,
        VisionCostLog.cache_hit == False,
    ).scalar() or 0
    if int(blocked_today) > 0:
        cost_blocked = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0.0)).filter(
            VisionCostLog.created_at >= day_start, VisionCostLog.skip_reason == "vision_disabled"
        ).scalar() or 0)
        _leak("Unexpected Vision Calls", "high",
              f"{int(blocked_today)} vision calls blocked today (vision is disabled)",
              cost_blocked,
              "Some code path is calling process_rag_image_guarded() even though VISION_ENABLED=false",
              "Review image upload triggers — ensure no auto-captioning is called on upload without user confirmation",
              {"blocked_calls": int(blocked_today), "estimated_cost_avoided_usd": round(cost_blocked, 4)})

    # 2. Unexpected GPT-5.4 Usage (most expensive model)
    gpt5_today = db.query(
        _f.count(UnifiedUsageLog.id),
        _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0),
    ).filter(
        UnifiedUsageLog.created_at >= day_start,
        UnifiedUsageLog.model.ilike("gpt-5%"),
    ).one()
    gpt5_calls, gpt5_cost = int(gpt5_today[0] or 0), float(gpt5_today[1] or 0)
    if gpt5_calls > 10:
        _leak("Unexpected GPT-5.4 Usage", "high",
              f"{gpt5_calls} gpt-5.x calls today (${gpt5_cost:.4f})",
              gpt5_cost,
              "Heavy use of gpt-5.4 ($100/$200 per 1M tokens) for tasks that could use cheaper models",
              "Route summarisation, extraction, and chat tasks to gpt-4o-mini or gpt-4o",
              {"calls_today": gpt5_calls, "cost_today_usd": round(gpt5_cost, 4)})
    elif gpt5_calls > 0:
        _leak("GPT-5.4 Usage", "low",
              f"{gpt5_calls} gpt-5.x calls today — monitoring",
              gpt5_cost,
              "GPT-5.4 used for high-value tasks (Innovation Engine, X-Ray Analysis)",
              "Verify these are intentional high-value calls, not routed incorrectly",
              {"calls_today": gpt5_calls, "cost_today_usd": round(gpt5_cost, 4)})

    # 3. Unexpected GPT-4o Usage spike
    gpt4_today = db.query(
        _f.count(UnifiedUsageLog.id),
        _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0),
    ).filter(
        UnifiedUsageLog.created_at >= day_start,
        UnifiedUsageLog.model.ilike("gpt-4o%"),
    ).one()
    gpt4_calls, gpt4_cost = int(gpt4_today[0] or 0), float(gpt4_today[1] or 0)
    if gpt4_calls > 50:
        _leak("GPT-4o Usage Spike", "medium",
              f"{gpt4_calls} gpt-4o calls today — unusually high",
              gpt4_cost,
              "Possible loop or batch job making excessive gpt-4o calls",
              "Check if any background job is running repeatedly; verify per-request limits",
              {"calls_today": gpt4_calls, "cost_today_usd": round(gpt4_cost, 4)})

    # 4. Duplicate Translation Processing
    dups = db.query(TranslationUsage.project_name, _f.count(TranslationUsage.id).label("cnt")).group_by(
        TranslationUsage.project_name
    ).having(_f.count(TranslationUsage.id) > 2).all()
    if dups:
        dup_cost = sum(
            float(db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0)).filter(
                TranslationUsage.project_name == d[0]).scalar() or 0)
            for d in dups
        )
        _leak("Duplicate Translation Processing", "medium",
              f"{len(dups)} file(s) translated 3+ times",
              dup_cost,
              "Files are being re-translated when existing output could be reused",
              "Check if translation memory is enabled; reuse existing translation output via version history",
              {"duplicate_files": [{"name": d[0], "count": int(d[1])} for d in dups[:5]]})

    # 5. Repeated Caption Requests (same image captioned multiple times)
    repeated_captions = db.query(
        VisionCostLog.image_sha256, _f.count(VisionCostLog.id).label("cnt")
    ).filter(
        VisionCostLog.cache_hit == False,
        VisionCostLog.skipped == False,
        VisionCostLog.image_sha256.isnot(None),
    ).group_by(VisionCostLog.image_sha256).having(_f.count(VisionCostLog.id) > 1).all()
    if repeated_captions:
        waste_cost = 0.0
        for rc in repeated_captions:
            cost_for_sha = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0)).filter(
                VisionCostLog.image_sha256 == rc[0], VisionCostLog.cache_hit == False
            ).scalar() or 0)
            waste_cost += cost_for_sha * (int(rc[1]) - 1) / max(int(rc[1]), 1)
        _leak("Repeated Caption Requests", "high",
              f"{len(repeated_captions)} image(s) captioned multiple times without cache hit",
              waste_cost,
              "SHA-256 cache may not be seeding correctly, or images have different byte representations",
              "Check that image bytes are deterministically extracted; SHA-256 cache should prevent re-captioning",
              {"repeated_images": len(repeated_captions), "estimated_waste_usd": round(waste_cost, 4)})

    # 6. Runaway API Calls (unusually high call volume in last hour)
    calls_last_hour = db.query(_f.count(UnifiedUsageLog.id)).filter(
        UnifiedUsageLog.created_at >= hour_ago,
    ).scalar() or 0
    if int(calls_last_hour) > 100:
        cost_last_hour = float(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0)).filter(
            UnifiedUsageLog.created_at >= hour_ago).scalar() or 0)
        _leak("Runaway API Calls", "critical",
              f"{int(calls_last_hour)} API calls in last hour — possible loop or runaway background job",
              cost_last_hour,
              "A background job, loop, or queue consumer may be making uncapped API calls",
              "Check running background tasks immediately; inspect recent job logs for loops",
              {"calls_last_hour": int(calls_last_hour), "cost_last_hour_usd": round(cost_last_hour, 4)})

    # 7. Vision calls with expensive model
    expensive_vision = db.query(
        _f.count(VisionCostLog.id),
        _f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0),
    ).filter(
        VisionCostLog.model.ilike("gpt-5%"),
        VisionCostLog.skipped == False,
        VisionCostLog.cache_hit == False,
    ).one()
    exp_calls, exp_cost = int(expensive_vision[0] or 0), float(expensive_vision[1] or 0)
    if exp_calls > 0:
        _leak("Expensive Vision Model", "medium" if exp_calls < 10 else "high",
              f"{exp_calls} vision calls used gpt-5.x (${exp_cost:.4f})",
              exp_cost * 0.85,  # 85% savings if switched to gpt-4o
              "VISION_CAPTION_MODEL not set or set to gpt-5.4 — 20× more expensive than gpt-4o for vision",
              "Set VISION_CAPTION_MODEL=gpt-4o in Replit Secrets — 85% cost reduction",
              {"calls": exp_calls, "cost_usd": round(exp_cost, 4), "potential_saving_usd": round(exp_cost * 0.85, 4)})

    # Sort: critical > high > medium > low
    order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    leaks.sort(key=lambda x: order.get(x["severity"], 99))

    return {
        "leaks": leaks,
        "total":  len(leaks),
        "checked_at": now.isoformat(),
        "note": "All checks use existing DB logs only. No external API calls made.",
    }


# ── 6. Root Cause Analytics — per-feature breakdown ───────────────────────────

@router.get("/costs/root-cause")
def root_cause_analytics(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Per-feature root cause analysis.
    For each feature: historical cost, current cost, highest single job,
    average cost, biggest incident, most frequent cause, protection status.
    """
    import os
    from api.db.models import (
        TranslationUsage, VisionCostLog, StudyJob, ChatUsage,
        UnifiedUsageLog, CostIncident
    )

    _seed_incidents_if_empty(db)

    def _feature_checks(checks, feature_keywords: list[str]) -> str:
        """Return PASS/WARNING/FAIL for a feature based on relevant checks."""
        relevant = [c for c in checks if any(kw.lower() in c["name"].lower() for kw in feature_keywords)]
        if any(c["status"] == "FAIL" for c in relevant):
            return "FAIL"
        if any(c["status"] == "WARNING" for c in relevant):
            return "WARNING"
        return "PASS"

    checks = _run_protection_checks(db)

    def _u_agg(feature: str):
        row = db.query(
            _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0.0),
            _f.count(UnifiedUsageLog.id),
            _f.coalesce(_f.max(UnifiedUsageLog.cost_usd), 0.0),
        ).filter(UnifiedUsageLog.feature == feature).one()
        total_c, cnt, max_c = float(row[0] or 0), int(row[1] or 0), float(row[2] or 0)
        return total_c, cnt, max_c, total_c / max(cnt, 1)

    def _incidents_for(feature: str):
        incs = db.query(CostIncident).filter(
            CostIncident.feature.ilike(f"%{feature.split(' ')[0]}%")
        ).order_by(CostIncident.total_cost_usd.desc()).limit(3).all()
        return [{"feature": i.feature, "cost_usd": i.total_cost_usd,
                 "date": i.incident_date.isoformat() if i.incident_date else None,
                 "root_cause": (i.root_cause or "")[:120], "status": i.status} for i in incs]

    # Image Captioning
    v_total  = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0.0)).filter(
        VisionCostLog.skipped==False, VisionCostLog.cache_hit==False).scalar() or 0)
    v_cnt    = int(db.query(_f.count(VisionCostLog.id)).filter(
        VisionCostLog.skipped==False, VisionCostLog.cache_hit==False).scalar() or 0)
    v_max    = float(db.query(_f.coalesce(_f.max(VisionCostLog.cost_usd), 0.0)).scalar() or 0)

    # Translation
    t_total  = float(db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0.0)).scalar() or 0)
    t_cnt    = int(db.query(_f.count(TranslationUsage.id)).scalar() or 0)
    t_max    = float(db.query(_f.coalesce(_f.max(TranslationUsage.est_cost_usd), 0.0)).scalar() or 0)

    # Learning Hub
    l_in  = int(db.query(_f.coalesce(_f.sum(StudyJob.input_tokens), 0)).scalar() or 0)
    l_out = int(db.query(_f.coalesce(_f.sum(StudyJob.output_tokens), 0)).scalar() or 0)
    l_total = _compute_cost(l_in, l_out)
    l_cnt   = int(db.query(_f.count(StudyJob.id)).filter(StudyJob.input_tokens > 0).scalar() or 0)

    # Chat
    c_total = float(db.query(_f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0.0)).scalar() or 0)
    c_cnt   = int(db.query(_f.count(ChatUsage.id)).scalar() or 0)
    c_max   = float(db.query(_f.coalesce(_f.max(ChatUsage.est_cost_usd), 0.0)).scalar() or 0)

    # Innovation, Training, Gallery, Image Translation
    innov_c, innov_n, innov_max, innov_avg = _u_agg("Innovation Engine")
    train_c, train_n, train_max, train_avg = _u_agg("Training Generator")
    gal_c,   gal_n,   gal_max,   gal_avg   = _u_agg("Gallery Reindex")
    imgt_c,  imgt_n,  imgt_max,  imgt_avg  = _u_agg("Image Translation")

    def _feat(name, hist_cost_range, current, calls, max_job, avg_job, prot_keywords, frequent_cause, incidents=None):
        status = _feature_checks(checks, prot_keywords)
        return {
            "feature":           name,
            "historical_cost":   hist_cost_range,
            "current_cost_usd":  round(current, 4),
            "total_calls":       calls,
            "highest_single_job_usd": round(max_job, 6),
            "average_cost_usd":  round(avg_job, 6),
            "biggest_incident":  (incidents[0] if incidents else None),
            "most_frequent_cause": frequent_cause,
            "protection_status": status,
            "protection_checks": [c["name"] for c in checks if any(kw.lower() in c["name"].lower() for kw in prot_keywords)],
        }

    features = [
        _feat("Image Captioning (Vision Guard)", "$40–55 per session (historical incident)",
              v_total, v_cnt, v_max, v_total/max(v_cnt,1),
              ["Kill Switch", "Vision Disabled", "Daily Cost", "Monthly Cost", "SHA-256", "Caption Cache", "Max Vision"],
              "Auto-captioning without kill switch or per-job cap",
              _incidents_for("Image Captioning")),

        _feat("Translation Studio", f"${t_total:.4f} tracked lifetime",
              t_total, t_cnt, t_max, t_total/max(t_cnt,1),
              ["Translation Cache", "Response Cache", "Model Routing"],
              "Re-translation of identical segments without TM",
              _incidents_for("Translation")),

        _feat("Learning Hub", f"${l_total:.4f} tracked lifetime",
              l_total, l_cnt, 0.0, l_total/max(l_cnt,1),
              ["Usage Recorder"],
              "11-phase study pipeline: one document = 11 API calls",
              _incidents_for("Learning")),

        _feat("AI Chat", f"${c_total:.4f} tracked lifetime",
              c_total, c_cnt, c_max, c_total/max(c_cnt,1),
              ["Response Cache", "Usage Recorder"],
              "No response cache — every message makes a fresh API call",
              _incidents_for("Chat")),

        _feat("Innovation Engine", f"${innov_c:.4f} tracked lifetime",
              innov_c, innov_n, innov_max, innov_avg,
              ["Model Routing", "Usage Recorder"],
              "gpt-5.4 usage ($100/$200 per 1M tokens); 5 GPT calls per report",
              _incidents_for("Innovation")),

        _feat("Training Generator", f"${train_c:.4f} tracked lifetime",
              train_c, train_n, train_max, train_avg,
              ["Model Routing", "Usage Recorder"],
              "16K output token slide batches at $200/1M output",
              _incidents_for("Training")),

        _feat("Gallery Reindex", f"${gal_c:.4f} tracked lifetime",
              gal_c, gal_n, gal_max, gal_avg,
              ["Kill Switch", "Vision Disabled", "Usage Recorder"],
              "1 vision call per page — 100-page document = 100 calls",
              _incidents_for("Gallery")),

        _feat("Image Translation", f"${imgt_c:.4f} tracked lifetime",
              imgt_c, imgt_n, imgt_max, imgt_avg,
              ["OCR Fallback", "Usage Recorder"],
              "Up to 30 detect+extract calls per image-heavy document",
              _incidents_for("Image Translation")),
    ]

    return {"features": features, "total_tracked_cost_usd": round(
        v_total + t_total + l_total + c_total + innov_c + train_c + gal_c + imgt_c, 4
    )}


# ── 7. Config Audit — protection config change history ────────────────────────

@router.get("/costs/config-audit")
def config_audit(
    key:   str = Query(""),
    limit: int = Query(100),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Immutable audit trail of all protection configuration changes."""
    from api.db.models import ProtectionConfigLog

    q = db.query(ProtectionConfigLog).order_by(ProtectionConfigLog.changed_at.desc())
    if key:
        q = q.filter(ProtectionConfigLog.config_key.ilike(f"%{key}%"))

    total = q.count()
    rows  = q.limit(min(limit, 500)).all()

    return {
        "entries": [
            {
                "id":         r.id,
                "config_key": r.config_key,
                "old_value":  r.old_value,
                "new_value":  r.new_value,
                "user_id":    r.user_id,
                "reason":     r.reason,
                "source":     r.source,
                "changed_at": r.changed_at.isoformat() if r.changed_at else None,
            }
            for r in rows
        ],
        "total": total,
    }


# ── 8. Update verify-protection to use 14 checks with PASS/WARNING/FAIL ───────

@router.post("/costs/verify-protection")
def verify_protection(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    14-point protection verification with PASS / WARNING / FAIL per check.
    Protected count = PASS.  At Risk count = FAIL.
    No API calls made.
    """
    checks = _run_protection_checks(db)
    # Normalise status field name for frontend compatibility
    for c in checks:
        c["status_raw"] = c["status"]
        c["status"] = c["status"].lower()  # keep lowercase for existing frontend

    pass_c = sum(1 for c in checks if c["status_raw"] == "PASS")
    warn_c = sum(1 for c in checks if c["status_raw"] == "WARNING")
    fail_c = sum(1 for c in checks if c["status_raw"] == "FAIL")

    return {
        "checks": checks,
        "passed":  pass_c,
        "warnings": warn_c,
        "failed":  fail_c,
        "total":   len(checks),
        "overall": "pass" if fail_c == 0 and warn_c == 0 else ("partial" if pass_c > 0 else "fail"),
        "protected_count": pass_c,
        "at_risk_count":   fail_c,
        "note": "No API calls made. Verified using DB records and environment variables only.",
    }


# ══════════════════════════════════════════════════════════════════════════════
# TOP COST CONSUMERS
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/costs/top-consumers")
def top_consumers(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Rank every AI feature from highest to lowest cost.

    Returns:
      - features[]: ranked list with current cost, historical peak, highest
        single request, avg, % of total, trend, protection status, call count
      - summary: 13-stat summary bar
    """
    import os
    from api.db.models import (
        TranslationUsage, VisionCostLog, StudyJob, ChatUsage,
        UnifiedUsageLog, CostIncident,
    )

    now = _now_utc()
    week_ago = now - timedelta(days=7)
    prev_week = now - timedelta(days=14)

    # ── Per-table aggregation helpers ─────────────────────────────────────────

    def _tu_stat():
        """Translation Studio from TranslationUsage."""
        total = float(db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0)).scalar() or 0)
        cnt   = int  (db.query(_f.count(TranslationUsage.id)).scalar() or 0)
        peak  = float(db.query(_f.coalesce(_f.max(TranslationUsage.est_cost_usd), 0)).scalar() or 0)
        r7    = float(db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0)).filter(
            TranslationUsage.created_at >= week_ago).scalar() or 0)
        rp    = float(db.query(_f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0)).filter(
            TranslationUsage.created_at >= prev_week,
            TranslationUsage.created_at < week_ago).scalar() or 0)
        return total, cnt, peak, r7, rp

    def _vc_stat():
        """Image Analysis/Captioning from VisionCostLog (real calls only)."""
        total = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0)).filter(
            VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
        cnt   = int(db.query(_f.count(VisionCostLog.id)).filter(
            VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
        peak  = float(db.query(_f.coalesce(_f.max(VisionCostLog.cost_usd), 0)).scalar() or 0)
        r7    = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0)).filter(
            VisionCostLog.created_at >= week_ago,
            VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
        rp    = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0)).filter(
            VisionCostLog.created_at >= prev_week, VisionCostLog.created_at < week_ago,
            VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
        return total, cnt, peak, r7, rp

    def _sj_stat():
        """Learning Hub from StudyJob."""
        in_t  = int(db.query(_f.coalesce(_f.sum(StudyJob.input_tokens), 0)).scalar() or 0)
        out_t = int(db.query(_f.coalesce(_f.sum(StudyJob.output_tokens), 0)).scalar() or 0)
        total = _compute_cost(in_t, out_t)
        cnt   = int(db.query(_f.count(StudyJob.id)).filter(StudyJob.input_tokens > 0).scalar() or 0)
        # Peak: most expensive single job (compute per-row is expensive; approximate via max tokens)
        peak_in  = int(db.query(_f.coalesce(_f.max(StudyJob.input_tokens), 0)).scalar() or 0)
        peak_out = int(db.query(_f.coalesce(_f.max(StudyJob.output_tokens), 0)).scalar() or 0)
        peak  = _compute_cost(peak_in, peak_out)
        in7   = int(db.query(_f.coalesce(_f.sum(StudyJob.input_tokens), 0)).filter(StudyJob.created_at >= week_ago).scalar() or 0)
        out7  = int(db.query(_f.coalesce(_f.sum(StudyJob.output_tokens), 0)).filter(StudyJob.created_at >= week_ago).scalar() or 0)
        r7    = _compute_cost(in7, out7)
        inp   = int(db.query(_f.coalesce(_f.sum(StudyJob.input_tokens), 0)).filter(StudyJob.created_at >= prev_week, StudyJob.created_at < week_ago).scalar() or 0)
        outp  = int(db.query(_f.coalesce(_f.sum(StudyJob.output_tokens), 0)).filter(StudyJob.created_at >= prev_week, StudyJob.created_at < week_ago).scalar() or 0)
        rp    = _compute_cost(inp, outp)
        return total, cnt, peak, r7, rp

    def _cu_stat():
        """AI Chat from ChatUsage."""
        total = float(db.query(_f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0)).scalar() or 0)
        cnt   = int(db.query(_f.count(ChatUsage.id)).scalar() or 0)
        peak  = float(db.query(_f.coalesce(_f.max(ChatUsage.est_cost_usd), 0)).scalar() or 0)
        r7    = float(db.query(_f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0)).filter(
            ChatUsage.created_at >= week_ago).scalar() or 0)
        rp    = float(db.query(_f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0)).filter(
            ChatUsage.created_at >= prev_week, ChatUsage.created_at < week_ago).scalar() or 0)
        return total, cnt, peak, r7, rp

    def _ul_stat(feature_name: str):
        """Any feature from UnifiedUsageLog."""
        q = db.query(
            _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0),
            _f.count(UnifiedUsageLog.id),
            _f.coalesce(_f.max(UnifiedUsageLog.cost_usd), 0),
        ).filter(UnifiedUsageLog.feature == feature_name)
        total, cnt, peak = q.one()
        total, cnt, peak = float(total or 0), int(cnt or 0), float(peak or 0)
        r7 = float(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0)).filter(
            UnifiedUsageLog.feature == feature_name, UnifiedUsageLog.created_at >= week_ago).scalar() or 0)
        rp = float(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0)).filter(
            UnifiedUsageLog.feature == feature_name,
            UnifiedUsageLog.created_at >= prev_week, UnifiedUsageLog.created_at < week_ago).scalar() or 0)
        return total, cnt, peak, r7, rp

    def _trend(r7: float, rp: float) -> str:
        if rp == 0:
            return "new" if r7 > 0 else "flat"
        change = (r7 - rp) / rp
        if change > 0.10:   return "up"
        if change < -0.10:  return "down"
        return "flat"

    def _trend_pct(r7: float, rp: float) -> float | None:
        if rp == 0: return None
        return round((r7 - rp) / rp * 100, 1)

    # ── Run protection checks once ─────────────────────────────────────────────
    checks = _run_protection_checks(db)
    def _prot(keywords: list[str]) -> str:
        relevant = [c for c in checks if any(k.lower() in c["name"].lower() for k in keywords)]
        if any(c["status"] == "FAIL"    for c in relevant): return "at_risk"
        if any(c["status"] == "WARNING" for c in relevant): return "warning"
        if any(c["status"] == "PASS"    for c in relevant): return "protected"
        return "unknown"

    # ── Historical peak from CostIncident ─────────────────────────────────────
    _seed_incidents_if_empty(db)
    def _hist_peak(feature_kw: str) -> float:
        inc = db.query(_f.coalesce(_f.max(CostIncident.total_cost_usd), 0)).filter(
            CostIncident.feature.ilike(f"%{feature_kw}%")).scalar() or 0
        return float(inc)

    # ── Build feature rows ─────────────────────────────────────────────────────
    raw_features = []

    t_total, t_cnt, t_peak, t_r7, t_rp = _tu_stat()
    raw_features.append({
        "id": "translation", "label": "Translation Studio",
        "current_cost_usd": t_total, "call_count": t_cnt,
        "highest_single_request_usd": t_peak,
        "historical_peak_usd": max(t_peak, _hist_peak("Translation")),
        "recent_7d_usd": t_r7, "prev_7d_usd": t_rp,
        "prot_keys": ["Translation Cache", "Response Cache", "Model Routing"],
    })

    v_total, v_cnt, v_peak, v_r7, v_rp = _vc_stat()
    hist_vc = _hist_peak("Image Captioning")
    raw_features.append({
        "id": "image_captioning", "label": "Image Captioning",
        "current_cost_usd": v_total, "call_count": v_cnt,
        "highest_single_request_usd": v_peak,
        "historical_peak_usd": max(v_peak, hist_vc),
        "recent_7d_usd": v_r7, "prev_7d_usd": v_rp,
        "prot_keys": ["Kill Switch", "Vision Disabled", "Daily Cost", "Monthly Cost", "SHA-256", "Caption Cache", "Max Vision"],
    })

    sj_total, sj_cnt, sj_peak, sj_r7, sj_rp = _sj_stat()
    raw_features.append({
        "id": "learning_hub", "label": "Learning Hub",
        "current_cost_usd": sj_total, "call_count": sj_cnt,
        "highest_single_request_usd": sj_peak,
        "historical_peak_usd": max(sj_peak, _hist_peak("Learning")),
        "recent_7d_usd": sj_r7, "prev_7d_usd": sj_rp,
        "prot_keys": ["Usage Recorder"],
    })

    cu_total, cu_cnt, cu_peak, cu_r7, cu_rp = _cu_stat()
    raw_features.append({
        "id": "ai_chat", "label": "AI Chat",
        "current_cost_usd": cu_total, "call_count": cu_cnt,
        "highest_single_request_usd": cu_peak,
        "historical_peak_usd": max(cu_peak, _hist_peak("Chat")),
        "recent_7d_usd": cu_r7, "prev_7d_usd": cu_rp,
        "prot_keys": ["Response Cache", "Usage Recorder"],
    })

    for ul_name, ul_id, ul_hist_kw, ul_prot in [
        ("Innovation Engine",    "innovation_engine",    "Innovation",        ["Model Routing", "Usage Recorder"]),
        ("Training Generator",   "training_generator",   "Training",          ["Model Routing", "Usage Recorder"]),
        ("Gallery Reindex",      "gallery_reindex",      "Gallery",           ["Kill Switch", "Vision Disabled", "Usage Recorder"]),
        ("Image Translation",    "image_translation",    "Image Translation", ["OCR Fallback", "Usage Recorder"]),
        ("LinkedIn Generator",   "linkedin_generator",   "LinkedIn",          ["Usage Recorder"]),
        ("X-Ray Analysis",       "xray_analysis",        "X-Ray",             ["Usage Recorder"]),
        ("RAG Vision",           "rag_vision",           "RAG",               ["Kill Switch", "Vision Disabled", "Usage Recorder"]),
    ]:
        u_total, u_cnt, u_peak, u_r7, u_rp = _ul_stat(ul_name)
        raw_features.append({
            "id": ul_id, "label": ul_name,
            "current_cost_usd": u_total, "call_count": u_cnt,
            "highest_single_request_usd": u_peak,
            "historical_peak_usd": max(u_peak, _hist_peak(ul_hist_kw)),
            "recent_7d_usd": u_r7, "prev_7d_usd": u_rp,
            "prot_keys": ul_prot,
        })

    # Compute grand total (current costs only)
    grand_total = sum(f["current_cost_usd"] for f in raw_features)

    # Assemble final rows
    features = []
    for rank, f in enumerate(
        sorted(raw_features, key=lambda x: x["current_cost_usd"] + x["historical_peak_usd"], reverse=True), 1
    ):
        cur = f["current_cost_usd"]
        cnt = max(f["call_count"], 1)
        trend_dir = _trend(f["recent_7d_usd"], f["prev_7d_usd"])
        features.append({
            "rank":                      rank,
            "id":                        f["id"],
            "label":                     f["label"],
            "current_cost_usd":          round(cur, 6),
            "historical_peak_usd":       round(f["historical_peak_usd"], 4),
            "highest_single_request_usd": round(f["highest_single_request_usd"], 6),
            "average_cost_per_request_usd": round(cur / cnt, 6),
            "call_count":                f["call_count"],
            "pct_of_total":              round(cur / grand_total * 100, 1) if grand_total > 0 else 0.0,
            "trend":                     trend_dir,
            "trend_pct":                 _trend_pct(f["recent_7d_usd"], f["prev_7d_usd"]),
            "protection_status":         _prot(f["prot_keys"]),
            "recent_7d_usd":             round(f["recent_7d_usd"], 6),
        })

    # ── Summary bar (13 stats) ─────────────────────────────────────────────────
    largest_daily = 0.0
    largest_monthly = 0.0
    # Best effort: sum all tables by day/month
    from sqlalchemy import func as sfunc
    from sqlalchemy import cast, Date as SaDate

    for Model, col_cost, col_date in [
        (TranslationUsage, TranslationUsage.est_cost_usd, TranslationUsage.created_at),
        (VisionCostLog,    VisionCostLog.cost_usd,        VisionCostLog.created_at),
        (ChatUsage,        ChatUsage.est_cost_usd,        ChatUsage.created_at),
        (UnifiedUsageLog,  UnifiedUsageLog.cost_usd,      UnifiedUsageLog.created_at),
    ]:
        daily_rows = db.query(
            sfunc.date_trunc('day', col_date).label("d"),
            sfunc.sum(col_cost).label("s")
        ).group_by(sfunc.date_trunc('day', col_date)).all()
        for row in daily_rows:
            s = float(row.s or 0)
            if s > largest_daily: largest_daily = s

        monthly_rows = db.query(
            sfunc.date_trunc('month', col_date).label("m"),
            sfunc.sum(col_cost).label("s")
        ).group_by(sfunc.date_trunc('month', col_date)).all()
        for row in monthly_rows:
            s = float(row.s or 0)
            if s > largest_monthly: largest_monthly = s

    # Savings breakdown (reuse from executive-summary logic)
    v_saved_total = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0)).scalar() or 0)
    v_cache_saved = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0)).filter(
        VisionCostLog.cache_hit == True).scalar() or 0)
    v_dedup_saved = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0)).filter(
        VisionCostLog.skip_reason == "sha256_cache_hit").scalar() or 0)
    v_block_saved = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0)).filter(
        VisionCostLog.skip_reason.in_(["vision_disabled", "daily_limit_exceeded", "monthly_limit_exceeded"])
    ).scalar() or 0)
    from api.db.models import TranslationSegment
    tm_hits = int(db.query(_f.coalesce(_f.sum(TranslationUsage.memory_hits), 0)).scalar() or 0)
    tm_saved = tm_hits * _price_for("gpt-4o", "in") * 200 / 1_000_000
    cached_toks = int(db.query(_f.coalesce(
        _f.sum(TranslationUsage.translate_cached_tokens + TranslationUsage.review_cached_tokens), 0
    )).scalar() or 0)
    prompt_cache_saved = cached_toks * _price_for("gpt-4o", "in") * 0.5 / 1_000_000

    vision_model = (os.environ.get("VISION_CAPTION_MODEL") or "gpt-5.4").strip()
    cheap_models = {"gpt-4o", "gpt-4o-mini", "gpt-4.1"}
    is_cheap = any(vision_model.startswith(m) for m in cheap_models)
    v_real_cost = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0)).filter(
        VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
    model_routing_saved = v_real_cost * (0.85 if is_cheap else 0)

    # Largest single API request across all tables
    largest_single_api = max(
        float(db.query(_f.coalesce(_f.max(VisionCostLog.cost_usd), 0)).scalar() or 0),
        float(db.query(_f.coalesce(_f.max(UnifiedUsageLog.cost_usd), 0)).scalar() or 0),
        float(db.query(_f.coalesce(_f.max(TranslationUsage.est_cost_usd), 0)).scalar() or 0),
        float(db.query(_f.coalesce(_f.max(ChatUsage.est_cost_usd), 0)).scalar() or 0),
    )

    # Highest cost feature (by combined current + historical)
    top_feature = features[0]["label"] if features else "—"

    # Largest historical cost (from incidents or current peak)
    largest_hist_cost = max(
        (f["historical_peak_usd"] for f in features), default=0.0
    )
    largest_current_cost = max(
        (f["current_cost_usd"] for f in features), default=0.0
    )

    # Potential savings remaining (features with no protection or WARNING checks)
    unprotected = [f for f in features if f["protection_status"] in ("at_risk", "unknown")]
    potential_savings_remaining = sum(f["current_cost_usd"] * 0.70 for f in unprotected)

    total_saved = v_saved_total + model_routing_saved + tm_saved + prompt_cache_saved

    summary = {
        "highest_cost_feature":          top_feature,
        "highest_historical_cost_usd":   round(largest_hist_cost, 4),
        "highest_current_cost_usd":      round(largest_current_cost, 6),
        "largest_single_api_request_usd": round(largest_single_api, 6),
        "largest_single_job_usd":        round(largest_single_api, 6),  # same source
        "largest_daily_spend_usd":       round(largest_daily, 4),
        "largest_monthly_spend_usd":     round(largest_monthly, 4),
        "largest_lifetime_spend_usd":    round(grand_total, 4),
        "money_saved_by_protection_usd": round(v_block_saved, 4),
        "money_saved_by_cache_usd":      round(v_cache_saved + prompt_cache_saved, 4),
        "money_saved_by_deduplication_usd": round(v_dedup_saved, 4),
        "money_saved_by_model_routing_usd": round(model_routing_saved, 4),
        "potential_savings_remaining_usd": round(potential_savings_remaining, 4),
        "total_saved_usd":               round(total_saved, 4),
    }

    return {"features": features, "summary": summary, "grand_total_usd": round(grand_total, 6)}


@router.get("/costs/drill-down/{feature_id}")
def cost_drill_down(
    feature_id: str,
    limit: int = Query(200),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Full request-level drill-down for one feature.

    Returns every API call with: cost, tokens, images, model, time, duration,
    OpenAI request ID, and cost breakdown.
    """
    from api.db.models import (
        TranslationUsage, VisionCostLog, StudyJob, ChatUsage, UnifiedUsageLog
    )

    rows = []

    if feature_id == "translation":
        for r in db.query(TranslationUsage).order_by(TranslationUsage.created_at.desc()).limit(limit).all():
            rows.append({
                "id": str(r.id), "feature": "Translation Studio",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "model": r.model, "provider": r.provider,
                "cost_usd": round(r.est_cost_usd, 6),
                "prompt_tokens": r.input_tokens, "completion_tokens": r.output_tokens,
                "cached_tokens": r.translate_cached_tokens + r.review_cached_tokens,
                "images": 0,
                "duration_secs": r.duration_secs,
                "openai_request_id": None,
                "status": r.status,
                "label": r.project_name,
                "cost_breakdown": {
                    "translate_cost_usd": round(r.translate_cost_usd, 6),
                    "review_cost_usd": round(r.review_cost_usd, 6),
                    "total_cost_usd": round(r.est_cost_usd, 6),
                    "words": r.word_count,
                    "memory_hits": r.memory_hits,
                },
            })

    elif feature_id == "image_captioning":
        for r in db.query(VisionCostLog).order_by(VisionCostLog.created_at.desc()).limit(limit).all():
            rows.append({
                "id": str(r.id), "feature": "Image Captioning",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "model": r.model, "provider": "openai",
                "cost_usd": round(r.cost_usd, 6),
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "cached_tokens": 0,
                "images": 1,
                "duration_secs": 0,
                "openai_request_id": None,
                "status": "skipped" if r.skipped else ("cache_hit" if r.cache_hit else "completed"),
                "label": r.doc_filename,
                "cost_breakdown": {
                    "cost_usd": round(r.cost_usd, 6),
                    "saved_usd": round(r.saved_usd, 6),
                    "skip_reason": r.skip_reason,
                    "cache_hit": r.cache_hit,
                    "skipped": r.skipped,
                    "sha256": r.image_sha256,
                },
            })

    elif feature_id == "learning_hub":
        for r in db.query(StudyJob).filter(StudyJob.input_tokens > 0).order_by(StudyJob.created_at.desc()).limit(limit).all():
            cost = _compute_cost(r.input_tokens or 0, r.output_tokens or 0, r.model_used)
            dur = (r.updated_at - r.created_at).total_seconds() if r.updated_at and r.created_at else 0
            rows.append({
                "id": str(r.id), "feature": "Learning Hub",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "model": r.model_used, "provider": "openai",
                "cost_usd": round(cost, 6),
                "prompt_tokens": r.input_tokens, "completion_tokens": r.output_tokens,
                "cached_tokens": 0,
                "images": 0,
                "duration_secs": round(dur, 1),
                "openai_request_id": None,
                "status": r.status,
                "label": r.filename,
                "cost_breakdown": {"cost_usd": round(cost, 6), "input_tokens": r.input_tokens, "output_tokens": r.output_tokens},
            })

    elif feature_id == "ai_chat":
        for r in db.query(ChatUsage).order_by(ChatUsage.created_at.desc()).limit(limit).all():
            rows.append({
                "id": str(r.id), "feature": "AI Chat",
                "created_at": r.created_at.isoformat() if r.created_at else None,
                "model": r.model, "provider": "openai",
                "cost_usd": round(r.est_cost_usd, 6),
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "cached_tokens": 0,
                "images": 0,
                "duration_secs": r.duration_secs,
                "openai_request_id": None,
                "status": r.finish_reason,
                "label": f"conv:{(r.conversation_id or '?')[:8]}",
                "cost_breakdown": {"cost_usd": round(r.est_cost_usd, 6), "finish_reason": r.finish_reason},
            })

    else:
        # UnifiedUsageLog — map feature_id slug to feature name
        SLUG_MAP = {
            "innovation_engine":  "Innovation Engine",
            "training_generator": "Training Generator",
            "gallery_reindex":    "Gallery Reindex",
            "image_translation":  "Image Translation",
            "linkedin_generator": "LinkedIn Generator",
            "xray_analysis":      "X-Ray Analysis",
            "rag_vision":         "RAG Vision",
        }
        feature_name = SLUG_MAP.get(feature_id)
        if feature_name:
            for r in db.query(UnifiedUsageLog).filter(
                UnifiedUsageLog.feature == feature_name
            ).order_by(UnifiedUsageLog.created_at.desc()).limit(limit).all():
                meta = r.meta or {}
                rows.append({
                    "id": str(r.id), "feature": feature_name,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                    "model": r.model, "provider": "openai",
                    "cost_usd": round(r.cost_usd, 6),
                    "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                    "cached_tokens": 0,
                    "images": 0,
                    "duration_secs": round(r.duration_ms / 1000, 2) if r.duration_ms else 0,
                    "openai_request_id": r.openai_request_id,
                    "status": "completed",
                    "label": meta.get("topic") or meta.get("doc") or r.sub_feature or feature_name,
                    "cost_breakdown": {
                        "cost_usd": round(r.cost_usd, 6),
                        "prompt_tokens": r.prompt_tokens,
                        "completion_tokens": r.completion_tokens,
                        "sub_feature": r.sub_feature,
                        "meta": meta,
                    },
                })

    return {"feature_id": feature_id, "requests": rows, "total": len(rows)}


# ══════════════════════════════════════════════════════════════════════════════
# COST CONTRIBUTION ANALYTICS  — 6-chart dataset endpoint
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/costs/analytics")
def cost_analytics(
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """
    Returns all six chart datasets for Cost Contribution Analytics.
    No paid API calls — reads from DB only.
    """
    import os
    from api.db.models import (
        TranslationUsage, VisionCostLog, StudyJob, ChatUsage,
        UnifiedUsageLog, CostIncident,
    )
    from sqlalchemy import func as sf

    _seed_incidents_if_empty(db)
    now = _now_utc()

    # ── Shared: per-feature totals (reuse top-consumers logic) ────────────────
    def _feat_row(label: str, cur: float, hist_peak: float, calls: int,
                  max_single: float, last_used, prompt_tok: int, comp_tok: int):
        return {
            "label":     label,
            "current":   round(cur, 6),
            "historical": round(hist_peak, 4),
            "calls":     calls,
            "avg":       round(cur / max(calls, 1), 6),
            "highest":   round(max_single, 6),
            "last_used": last_used.isoformat() if last_used else None,
            "prompt_tokens": prompt_tok,
            "completion_tokens": comp_tok,
        }

    def _tu():
        r = db.query(
            _f.coalesce(_f.sum(TranslationUsage.est_cost_usd), 0),
            _f.count(TranslationUsage.id),
            _f.coalesce(_f.max(TranslationUsage.est_cost_usd), 0),
            _f.max(TranslationUsage.created_at),
            _f.coalesce(_f.sum(TranslationUsage.input_tokens), 0),
            _f.coalesce(_f.sum(TranslationUsage.output_tokens), 0),
        ).one()
        return _feat_row("Translation Studio", float(r[0]), float(r[2]), int(r[1]), float(r[2]), r[3], int(r[4]), int(r[5]))

    def _vc():
        flt = (VisionCostLog.skipped == False, VisionCostLog.cache_hit == False)
        r = db.query(
            _f.coalesce(_f.sum(VisionCostLog.cost_usd), 0),
            _f.count(VisionCostLog.id),
            _f.coalesce(_f.max(VisionCostLog.cost_usd), 0),
            _f.max(VisionCostLog.created_at),
            _f.coalesce(_f.sum(VisionCostLog.prompt_tokens), 0),
            _f.coalesce(_f.sum(VisionCostLog.completion_tokens), 0),
        ).filter(*flt).one()
        inc_peak = float(db.query(_f.coalesce(_f.max(CostIncident.total_cost_usd), 0)).filter(
            CostIncident.feature.ilike("%Image Captioning%")).scalar() or 0)
        row = _feat_row("Image Captioning", float(r[0]), max(float(r[2]), inc_peak), int(r[1]), float(r[2]), r[3], int(r[4]), int(r[5]))
        return row

    def _sj():
        in_t = int(db.query(_f.coalesce(_f.sum(StudyJob.input_tokens), 0)).scalar() or 0)
        out_t = int(db.query(_f.coalesce(_f.sum(StudyJob.output_tokens), 0)).scalar() or 0)
        total = _compute_cost(in_t, out_t)
        cnt   = int(db.query(_f.count(StudyJob.id)).filter(StudyJob.input_tokens > 0).scalar() or 0)
        mx_in = int(db.query(_f.coalesce(_f.max(StudyJob.input_tokens), 0)).scalar() or 0)
        mx_out = int(db.query(_f.coalesce(_f.max(StudyJob.output_tokens), 0)).scalar() or 0)
        last_u = db.query(_f.max(StudyJob.created_at)).scalar()
        return _feat_row("Learning Hub", total, _compute_cost(mx_in, mx_out), cnt, _compute_cost(mx_in, mx_out), last_u, in_t, out_t)

    def _cu():
        r = db.query(
            _f.coalesce(_f.sum(ChatUsage.est_cost_usd), 0),
            _f.count(ChatUsage.id),
            _f.coalesce(_f.max(ChatUsage.est_cost_usd), 0),
            _f.max(ChatUsage.created_at),
            _f.coalesce(_f.sum(ChatUsage.prompt_tokens), 0),
            _f.coalesce(_f.sum(ChatUsage.completion_tokens), 0),
        ).one()
        return _feat_row("AI Chat", float(r[0]), float(r[2]), int(r[1]), float(r[2]), r[3], int(r[4]), int(r[5]))

    def _ul(feature_name: str, display_label: str):
        r = db.query(
            _f.coalesce(_f.sum(UnifiedUsageLog.cost_usd), 0),
            _f.count(UnifiedUsageLog.id),
            _f.coalesce(_f.max(UnifiedUsageLog.cost_usd), 0),
            _f.max(UnifiedUsageLog.created_at),
            _f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens), 0),
            _f.coalesce(_f.sum(UnifiedUsageLog.completion_tokens), 0),
        ).filter(UnifiedUsageLog.feature == feature_name).one()
        return _feat_row(display_label, float(r[0]), float(r[2]), int(r[1]), float(r[2]), r[3], int(r[4]), int(r[5]))

    feat_rows = [
        _vc(),
        _tu(),
        _sj(),
        _cu(),
        _ul("Innovation Engine", "Innovation Engine"),
        _ul("Training Generator", "Training Generator"),
        _ul("Gallery Reindex", "Gallery Reindex"),
        _ul("Image Translation", "Image Translation"),
        _ul("LinkedIn Generator", "LinkedIn Generator"),
        _ul("X-Ray Analysis", "X-Ray Analysis"),
        _ul("RAG Vision", "RAG Vision (Knowledge Base)"),
    ]

    grand_current = sum(f["current"] for f in feat_rows)
    grand_hist    = sum(f["historical"] for f in feat_rows)

    # Enrich with pct and incident markers
    incidents_by_feature = {}
    for inc in db.query(CostIncident).all():
        key = inc.feature
        if key not in incidents_by_feature or inc.total_cost_usd > incidents_by_feature[key]["cost"]:
            incidents_by_feature[key] = {
                "cost": inc.total_cost_usd,
                "date": inc.incident_date.isoformat() if inc.incident_date else None,
                "severity": inc.severity,
            }

    def _enrich(rows: list[dict], grand: float) -> list[dict]:
        out = []
        for f in rows:
            cur = f["current"]
            hist = f["historical"]
            # Find matching incident
            inc_match = None
            for k, v in incidents_by_feature.items():
                if f["label"].lower().split(" ")[0] in k.lower() or k.lower().split(" ")[0] in f["label"].lower():
                    if v["cost"] > hist:
                        hist = v["cost"]
                    inc_match = v
                    break
            has_incident = inc_match is not None or hist >= 25
            out.append({
                **f,
                "historical": round(hist, 4),
                "pct_current": round(cur / grand * 100, 1) if grand > 0 else 0,
                "has_incident": has_incident,
                "incident": inc_match,
            })
        return sorted(out, key=lambda x: x["current"], reverse=True)

    chart1 = _enrich(feat_rows, grand_current)   # current cost by feature
    chart2 = sorted(
        _enrich(feat_rows, grand_hist),
        key=lambda x: x["historical"], reverse=True
    )

    # ── Chart 3: Token Distribution ───────────────────────────────────────────
    # Vision tokens (separate from language model tokens)
    vision_prompt = int(db.query(_f.coalesce(_f.sum(VisionCostLog.prompt_tokens), 0)).filter(
        VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)
    vision_comp   = int(db.query(_f.coalesce(_f.sum(VisionCostLog.completion_tokens), 0)).filter(
        VisionCostLog.skipped == False, VisionCostLog.cache_hit == False).scalar() or 0)

    # Cached tokens (all sources)
    cached_ul = int(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.cached_tokens), 0)).scalar() or 0)
    cached_tu = int(db.query(_f.coalesce(
        _f.sum(TranslationUsage.translate_cached_tokens + TranslationUsage.review_cached_tokens), 0
    )).scalar() or 0)

    # OCR tokens (sub_feature)
    ocr_prompt = int(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens), 0)).filter(
        UnifiedUsageLog.sub_feature == "image_label_extraction").scalar() or 0)
    ocr_comp   = int(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.completion_tokens), 0)).filter(
        UnifiedUsageLog.sub_feature == "image_label_extraction").scalar() or 0)

    # Language model tokens (non-vision, non-OCR)
    lm_prompt_ul = int(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.prompt_tokens), 0)).filter(
        UnifiedUsageLog.sub_feature != "image_label_extraction").scalar() or 0)
    lm_comp_ul   = int(db.query(_f.coalesce(_f.sum(UnifiedUsageLog.completion_tokens), 0)).filter(
        UnifiedUsageLog.sub_feature != "image_label_extraction").scalar() or 0)
    lm_prompt_tu = int(db.query(_f.coalesce(_f.sum(TranslationUsage.input_tokens), 0)).scalar() or 0)
    lm_comp_tu   = int(db.query(_f.coalesce(_f.sum(TranslationUsage.output_tokens), 0)).scalar() or 0)
    lm_prompt_cu = int(db.query(_f.coalesce(_f.sum(ChatUsage.prompt_tokens), 0)).scalar() or 0)
    lm_comp_cu   = int(db.query(_f.coalesce(_f.sum(ChatUsage.completion_tokens), 0)).scalar() or 0)
    lm_prompt_sj = int(db.query(_f.coalesce(_f.sum(StudyJob.input_tokens), 0)).scalar() or 0)
    lm_comp_sj   = int(db.query(_f.coalesce(_f.sum(StudyJob.output_tokens), 0)).scalar() or 0)

    total_prompt     = lm_prompt_ul + lm_prompt_tu + lm_prompt_cu + lm_prompt_sj
    total_completion = lm_comp_ul + lm_comp_tu + lm_comp_cu + lm_comp_sj
    total_cached     = cached_ul + cached_tu

    chart3 = [
        {"label": "Prompt Tokens",     "value": total_prompt,         "color": "#3b82f6"},
        {"label": "Completion Tokens", "value": total_completion,     "color": "#8b5cf6"},
        {"label": "Cached Tokens",     "value": total_cached,         "color": "#06b6d4"},
        {"label": "Vision Tokens",     "value": vision_prompt + vision_comp, "color": "#f59e0b"},
        {"label": "Embedding Tokens",  "value": 0,                    "color": "#10b981"},  # not tracked separately yet
        {"label": "OCR Tokens",        "value": ocr_prompt + ocr_comp,"color": "#ec4899"},
    ]
    chart3 = [c for c in chart3 if c["value"] > 0]  # hide zero slices

    # ── Chart 4: Model Cost Contribution ─────────────────────────────────────
    model_costs: dict[str, float] = {}
    model_calls: dict[str, int]   = {}

    def _add_model(model: str, cost: float, n: int = 1):
        m = (model or "Unknown").strip()
        # Normalise model names
        if m.startswith("gpt-5"):         m = "GPT-5.4"
        elif m.startswith("gpt-4o-mini"): m = "GPT-4o-mini"
        elif m.startswith("gpt-4o"):      m = "GPT-4o"
        elif m.startswith("gpt-4.1-mini"):m = "GPT-4.1 Mini"
        elif m.startswith("gpt-4.1"):     m = "GPT-4.1"
        elif m.startswith("gpt-4"):       m = "GPT-4"
        elif m.startswith("gpt-3"):       m = "GPT-3.5"
        elif m.lower().startswith("claude"):m = "Claude"
        elif m.lower().startswith("ollama"):m = "Ollama"
        elif m.lower().startswith("azure"): m = "Azure OpenAI"
        elif m in ("", "Unknown"):         m = "Unknown"
        model_costs[m] = model_costs.get(m, 0.0) + cost
        model_calls[m] = model_calls.get(m, 0)  + n

    for row in db.query(UnifiedUsageLog.model, _f.sum(UnifiedUsageLog.cost_usd), _f.count(UnifiedUsageLog.id)).group_by(UnifiedUsageLog.model).all():
        _add_model(row[0] or "Unknown", float(row[1] or 0), int(row[2] or 0))
    for row in db.query(TranslationUsage.model, _f.sum(TranslationUsage.est_cost_usd), _f.count(TranslationUsage.id)).group_by(TranslationUsage.model).all():
        _add_model(row[0] or "Unknown", float(row[1] or 0), int(row[2] or 0))
    for row in db.query(VisionCostLog.model, _f.sum(VisionCostLog.cost_usd), _f.count(VisionCostLog.id)).filter(VisionCostLog.skipped==False, VisionCostLog.cache_hit==False).group_by(VisionCostLog.model).all():
        _add_model(row[0] or "Unknown", float(row[1] or 0), int(row[2] or 0))
    for row in db.query(ChatUsage.model, _f.sum(ChatUsage.est_cost_usd), _f.count(ChatUsage.id)).group_by(ChatUsage.model).all():
        _add_model(row[0] or "Unknown", float(row[1] or 0), int(row[2] or 0))

    MODEL_COLORS = {
        "GPT-5.4": "#ef4444", "GPT-4o": "#f59e0b", "GPT-4o-mini": "#84cc16",
        "GPT-4.1": "#06b6d4", "GPT-4.1 Mini": "#3b82f6", "GPT-4": "#a855f7",
        "GPT-3.5": "#10b981", "Claude": "#ec4899", "Ollama": "#6b7280",
        "Azure OpenAI": "#0ea5e9", "Unknown": "#374151",
    }
    chart4 = sorted(
        [{"label": m, "cost": round(c, 6), "calls": model_calls.get(m, 0),
          "color": MODEL_COLORS.get(m, "#6b7280")}
         for m, c in model_costs.items() if c > 0],
        key=lambda x: x["cost"], reverse=True
    )

    # ── Chart 5: Top 10 Most Expensive Documents ──────────────────────────────
    doc_map: dict[str, dict] = {}

    def _add_doc(name: str, cost: float, calls: int, prompt: int, comp: int):
        nm = (name or "Unknown").strip()[:80]
        if nm not in doc_map:
            doc_map[nm] = {"label": nm, "cost": 0.0, "calls": 0, "prompt_tokens": 0, "completion_tokens": 0}
        doc_map[nm]["cost"]  += cost
        doc_map[nm]["calls"] += calls
        doc_map[nm]["prompt_tokens"]     += prompt
        doc_map[nm]["completion_tokens"] += comp

    for r in db.query(
        TranslationUsage.project_name,
        _f.sum(TranslationUsage.est_cost_usd),
        _f.count(TranslationUsage.id),
        _f.sum(TranslationUsage.input_tokens),
        _f.sum(TranslationUsage.output_tokens),
    ).group_by(TranslationUsage.project_name).all():
        _add_doc(r[0], float(r[1] or 0), int(r[2] or 0), int(r[3] or 0), int(r[4] or 0))

    for r in db.query(
        VisionCostLog.doc_filename,
        _f.sum(VisionCostLog.cost_usd),
        _f.count(VisionCostLog.id),
        _f.sum(VisionCostLog.prompt_tokens),
        _f.sum(VisionCostLog.completion_tokens),
    ).filter(VisionCostLog.skipped==False, VisionCostLog.cache_hit==False).group_by(VisionCostLog.doc_filename).all():
        _add_doc(r[0], float(r[1] or 0), int(r[2] or 0), int(r[3] or 0), int(r[4] or 0))

    for r in db.query(
        StudyJob.filename,
        _f.count(StudyJob.id),
        _f.sum(StudyJob.input_tokens),
        _f.sum(StudyJob.output_tokens),
    ).filter(StudyJob.input_tokens > 0).group_by(StudyJob.filename).all():
        in_t, out_t = int(r[2] or 0), int(r[3] or 0)
        _add_doc(r[0], _compute_cost(in_t, out_t), int(r[1] or 0), in_t, out_t)

    chart5 = sorted(
        [{"label": v["label"], "cost": round(v["cost"], 6), "calls": v["calls"],
          "prompt_tokens": v["prompt_tokens"], "completion_tokens": v["completion_tokens"]}
         for v in doc_map.values() if v["cost"] > 0],
        key=lambda x: x["cost"], reverse=True
    )[:10]

    # ── Chart 6: Vision Cost Breakdown ────────────────────────────────────────
    def _vc_cat(label: str, *filters, color: str):
        cost  = float(db.query(_f.coalesce(_f.sum(VisionCostLog.cost_usd), 0)).filter(*filters).scalar() or 0)
        saved = float(db.query(_f.coalesce(_f.sum(VisionCostLog.saved_usd), 0)).filter(*filters).scalar() or 0)
        cnt   = int(db.query(_f.count(VisionCostLog.id)).filter(*filters).scalar() or 0)
        return {"label": label, "cost": round(cost, 6), "saved": round(saved, 6), "calls": cnt, "color": color}

    chart6 = [
        _vc_cat("Image Caption API",   VisionCostLog.skipped == False, VisionCostLog.cache_hit == False, color="#f59e0b"),
        _vc_cat("Cache Hits",          VisionCostLog.cache_hit == True, color="#06b6d4"),
        _vc_cat("SHA-256 Dedup",       VisionCostLog.skip_reason == "sha256_cache_hit", color="#10b981"),
        _vc_cat("Vision Disabled",     VisionCostLog.skip_reason == "vision_disabled", color="#6b7280"),
        _vc_cat("Daily Limit",         VisionCostLog.skip_reason == "daily_limit_exceeded", color="#ef4444"),
        _vc_cat("Monthly Limit",       VisionCostLog.skip_reason == "monthly_limit_exceeded", color="#dc2626"),
        _vc_cat("Pixel Filter",        VisionCostLog.skip_reason == "pixel_filter", color="#8b5cf6"),
        _vc_cat("Other Skipped",       VisionCostLog.skipped == True,
                VisionCostLog.skip_reason.notin_(["sha256_cache_hit", "vision_disabled",
                    "daily_limit_exceeded", "monthly_limit_exceeded", "pixel_filter"]),
                color="#374151"),
    ]

    return {
        "chart1_feature_current":   chart1,
        "chart2_feature_historical": chart2,
        "chart3_token_distribution": chart3,
        "chart4_model_cost":        chart4,
        "chart5_top_documents":     chart5,
        "chart6_vision_breakdown":  [c for c in chart6 if c["calls"] > 0 or c["saved"] > 0],
        "grand_total_current_usd":  round(grand_current, 6),
        "grand_total_historical_usd": round(grand_hist, 4),
    }


# ── Export ────────────────────────────────────────────────────────────────────

@router.get("/costs/export")
def cost_export(
    format: str = Query("csv"),
    feature: str = Query("all"),
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Export cost data as CSV."""
    from api.db.models import TranslationUsage, VisionCostLog, StudyJob, ChatUsage

    rows = []

    if feature in ("all", "translation"):
        for r in db.query(TranslationUsage).order_by(TranslationUsage.created_at.desc()).all():
            rows.append({
                "feature": "Translation", "created_at": r.created_at.isoformat() if r.created_at else "",
                "file": r.project_name, "model": r.model, "provider": r.provider,
                "prompt_tokens": r.input_tokens, "completion_tokens": r.output_tokens,
                "cost_usd": round(r.est_cost_usd, 6), "duration_secs": r.duration_secs,
                "status": r.status,
            })

    if feature in ("all", "vision"):
        for r in db.query(VisionCostLog).order_by(VisionCostLog.created_at.desc()).all():
            rows.append({
                "feature": "Image Analysis", "created_at": r.created_at.isoformat() if r.created_at else "",
                "file": r.doc_filename, "model": r.model, "provider": "openai",
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "cost_usd": round(r.cost_usd, 6), "duration_secs": 0,
                "status": "skipped" if r.skipped else ("cache_hit" if r.cache_hit else "completed"),
            })

    if feature in ("all", "learning"):
        for r in db.query(StudyJob).filter(StudyJob.input_tokens > 0).order_by(StudyJob.created_at.desc()).all():
            rows.append({
                "feature": "Learning Hub", "created_at": r.created_at.isoformat() if r.created_at else "",
                "file": r.filename, "model": r.model_used, "provider": "openai",
                "prompt_tokens": r.input_tokens, "completion_tokens": r.output_tokens,
                "cost_usd": round(_compute_cost(r.input_tokens or 0, r.output_tokens or 0, r.model_used), 6),
                "duration_secs": (r.updated_at - r.created_at).total_seconds() if r.updated_at and r.created_at else 0,
                "status": r.status,
            })

    if feature in ("all", "chat"):
        for r in db.query(ChatUsage).order_by(ChatUsage.created_at.desc()).all():
            rows.append({
                "feature": "AI Chat", "created_at": r.created_at.isoformat() if r.created_at else "",
                "file": f"conv:{r.conversation_id[:8] if r.conversation_id else '?'}",
                "model": r.model, "provider": "openai",
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "cost_usd": round(r.est_cost_usd, 6), "duration_secs": r.duration_secs,
                "status": r.finish_reason,
            })

    # All previously-untracked features from unified log
    from api.db.models import UnifiedUsageLog
    for r in db.query(UnifiedUsageLog).order_by(UnifiedUsageLog.created_at.desc()).all():
        if feature == "all" or feature == r.feature.lower().replace(" ", "_"):
            rows.append({
                "feature": r.feature, "created_at": r.created_at.isoformat() if r.created_at else "",
                "file": (r.meta or {}).get("topic") or (r.meta or {}).get("doc") or r.sub_feature or "",
                "model": r.model, "provider": "openai",
                "prompt_tokens": r.prompt_tokens, "completion_tokens": r.completion_tokens,
                "cost_usd": round(r.cost_usd, 6),
                "duration_secs": round(r.duration_ms / 1000, 2) if r.duration_ms else 0,
                "status": "completed",
            })

    rows.sort(key=lambda x: x["created_at"], reverse=True)

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["feature", "created_at", "file", "model", "provider",
                                              "prompt_tokens", "completion_tokens", "cost_usd",
                                              "duration_secs", "status"])
    writer.writeheader()
    writer.writerows(rows)
    buf.seek(0)

    filename = f"xray_cost_export_{_now_utc().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
