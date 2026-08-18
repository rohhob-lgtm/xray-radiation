"""
Hybrid Workspace Awareness.

Every place workspace content can change calls mark_dirty() (upload, edit,
delete, folder import, KB scan, connector sync, explicit refresh, workspace
switch — see routes/workspaces.py, workspace_agent/tools.py,
routes/knowledge_library.py, connectors/sync_engine.py). A 15-30 min
background sweep (IndexSweepScheduler) catches anything a trigger missed.

Re-indexing is always incremental: reindex_dirty() only touches resources
flagged dirty, compares content_hash before re-embedding (a cache hit just
flips status back to clean), and never rebuilds a whole workspace unless
force=True is passed explicitly.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from api.config import settings
from api.db import crud
from api.db.base import SessionLocal
from api.services.embedding_service import get_embedding
from api.services.retrieval_utils import MemoryResult, tokenize, keyword_score, cosine_similarity

log = logging.getLogger(__name__)

_MIN_KEYWORD_SCORE = 0.10
_MIN_SEMANTIC_BOOST = 0.70
_CONTENT_PREVIEW_CHARS = 4000


def mark_dirty(
    db: Session,
    resource_type: str,
    resource_id: str,
    workspace_id: Optional[str] = None,
    reason: str = "",
) -> None:
    """Single integration point every trigger calls. Cheap, synchronous."""
    crud.upsert_indexed_resource_dirty(db, resource_type, resource_id, workspace_id, reason)


# ──────────────────────────────────────────────────────────
# Incremental re-indexing
# ──────────────────────────────────────────────────────────

async def _reindex_workspace_file(db: Session, row: "crud.IndexedResource") -> str:
    from api.db.models import WorkspaceFile
    from api.utils import workspace_storage

    wf = db.query(WorkspaceFile).filter(WorkspaceFile.id == row.resource_id).first()
    if not wf or row.dirty_reason == "deleted":
        crud.delete_indexed_resource(db, row.resource_type, row.resource_id)
        return "deleted"

    new_hash = wf.checksum  # already sha256 of the original file bytes, computed at upload
    if (
        row.content_hash == new_hash
        and row.embedding_model_version == settings.embedding_model_version
    ):
        crud.mark_indexed_resource_clean(
            db, row, content_hash=new_hash, embedding_model_version=settings.embedding_model_version,
        )
        return "cache_hit"

    if not wf.extracted_text_path or wf.parse_status not in ("ready", "unsupported"):
        # Text extraction hasn't finished yet — leave dirty, next sweep retries.
        return "pending_extraction"

    text = workspace_storage.read_text_file(wf.extracted_text_path)
    preview = text[:_CONTENT_PREVIEW_CHARS]
    embedding = await get_embedding(preview)
    crud.mark_indexed_resource_clean(
        db, row, content_hash=new_hash, embedding_model_version=settings.embedding_model_version,
        title=wf.original_filename, content_preview=preview, embedding=embedding,
    )
    return "reindexed"


async def _reindex_rag_document(db: Session, row: "crud.IndexedResource") -> str:
    """
    RAG documents already own their own content + embedding (rag_service.py /
    embed_and_store). Re-indexing here just re-triggers that existing
    pipeline and mirrors its content_hash so the freshness state stays
    consistent — no duplicate content storage.
    """
    from api.db.models import RagDocument
    from api.services import rag_service
    import hashlib

    doc = db.query(RagDocument).filter(RagDocument.id == row.resource_id).first()
    if not doc:
        crud.delete_indexed_resource(db, row.resource_type, row.resource_id)
        return "deleted"

    new_hash = hashlib.sha256(doc.content.encode("utf-8", "ignore")).hexdigest()
    if (
        row.content_hash == new_hash
        and row.embedding_model_version == settings.embedding_model_version
        and doc.embedding
    ):
        crud.mark_indexed_resource_clean(
            db, row, content_hash=new_hash, embedding_model_version=settings.embedding_model_version,
            title=doc.filename,
        )
        return "cache_hit"

    await rag_service.embed_and_store(db, doc)
    crud.mark_indexed_resource_clean(
        db, row, content_hash=new_hash, embedding_model_version=settings.embedding_model_version,
        title=doc.filename,
    )
    return "reindexed"


async def _reindex_connector_item(db: Session, row: "crud.IndexedResource") -> str:
    """
    No defined text-extraction pipeline exists yet for arbitrary
    connector-synced content (Phase 1 scope) — the trigger is wired so
    future connector work can populate content_preview/embedding without
    redesigning this dispatch, but for now this just clears the dirty flag.
    """
    crud.mark_indexed_resource_clean(
        db, row, content_hash=row.content_hash, embedding_model_version=settings.embedding_model_version,
    )
    return "no_pipeline"


_HANDLERS = {
    "workspace_file": _reindex_workspace_file,
    "rag_document": _reindex_rag_document,
    "kb_folder_entry": _reindex_rag_document,  # KB scans create RagDocument rows
    "connector_item": _reindex_connector_item,
}


async def reindex_dirty(
    db: Session,
    workspace_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    limit: int = 50,
    force: bool = False,
) -> dict:
    """Process the dirty queue incrementally. force=True additionally marks
    every clean resource in the workspace dirty first — the only path to a
    full rebuild, and only ever taken on an explicit user/admin action."""
    if force and workspace_id:
        for row in crud.list_indexed_resources_for_workspace(db, workspace_id):
            crud.upsert_indexed_resource_dirty(db, row.resource_type, row.resource_id, workspace_id, reason="force_rebuild")

    dirty_rows = crud.list_dirty_resources(db, workspace_id=workspace_id, resource_type=resource_type, limit=limit)
    counts: dict = {"processed": 0, "deleted": 0, "cache_hit": 0, "errors": 0, "pending": 0}
    for row in dirty_rows:
        handler = _HANDLERS.get(row.resource_type)
        if not handler:
            continue
        try:
            outcome = await handler(db, row)
        except Exception:
            log.exception("reindex_dirty failed for %s/%s", row.resource_type, row.resource_id)
            crud.mark_indexed_resource_error(db, row, reason="reindex_exception")
            counts["errors"] += 1
            continue
        if outcome == "deleted":
            counts["deleted"] += 1
        elif outcome == "cache_hit":
            counts["cache_hit"] += 1
        elif outcome == "pending_extraction":
            counts["pending"] += 1
        else:
            counts["processed"] += 1
    return counts


async def ensure_fresh(db: Session, workspace_id: str, budget_ms: Optional[int] = None) -> None:
    """
    Called at the top of every chat turn that has an active workspace.
    Small dirty counts are reindexed inline within the time budget; large
    counts kick off a background sweep and the turn proceeds with the
    current best-effort index rather than blocking the user.
    """
    budget_ms = budget_ms or settings.workspace_index_refresh_budget_ms
    dirty_count = crud.count_dirty_resources(db, workspace_id)
    if dirty_count == 0:
        return

    if dirty_count <= 5:
        try:
            await asyncio.wait_for(reindex_dirty(db, workspace_id=workspace_id, limit=10), timeout=budget_ms / 1000)
        except asyncio.TimeoutError:
            log.info("ensure_fresh: inline reindex exceeded budget for workspace_id=%s, backgrounding", workspace_id)
            asyncio.create_task(_background_reindex(workspace_id))
    else:
        asyncio.create_task(_background_reindex(workspace_id))


async def _background_reindex(workspace_id: str) -> None:
    """Runs outside the request lifecycle — must own its own DB session."""
    bg_db = SessionLocal()
    try:
        await reindex_dirty(bg_db, workspace_id=workspace_id, limit=200)
    except Exception:
        log.exception("Background workspace reindex failed for workspace_id=%s", workspace_id)
    finally:
        bg_db.close()


# ──────────────────────────────────────────────────────────
# Search
# ──────────────────────────────────────────────────────────

async def search_workspace(db: Session, workspace_id: str, query: str, top_k: int = 5) -> List[MemoryResult]:
    """Hybrid keyword+embedding search over everything tracked for this workspace."""
    query_tokens = tokenize(query)
    if not query_tokens:
        return []
    query_embedding = await get_embedding(query)

    resources = [
        r for r in crud.list_indexed_resources_for_workspace(db, workspace_id)
        if r.status == "clean" and r.content_preview
    ]
    results: List[MemoryResult] = []
    for r in resources:
        kw = keyword_score(query_tokens, r.content_preview)
        boost = 0.0
        if query_embedding and r.embedding:
            boost = max(0.0, cosine_similarity(query_embedding, r.embedding))
        combined = kw + boost * 0.2
        if kw < _MIN_KEYWORD_SCORE and not (boost >= _MIN_SEMANTIC_BOOST and combined > 0.05):
            continue
        results.append(MemoryResult(
            source_kind="workspace", title=r.title or r.resource_id, content=r.content_preview,
            score=combined, meta={"resource_type": r.resource_type, "resource_id": r.resource_id},
        ))

    results.sort(key=lambda x: x.score, reverse=True)
    return results[:top_k]


# ──────────────────────────────────────────────────────────
# Background safety-net sweep (15-30 min)
# ──────────────────────────────────────────────────────────

class IndexSweepScheduler:
    """
    Structurally identical to connectors/sync_engine.SyncScheduler — an
    asyncio periodic loop, started/stopped from main.py's existing
    startup/shutdown hooks. Runs the incremental reindex plus a cheap
    stored-hash-vs-actual-file-hash verification pass so anything a trigger
    missed still gets caught within the sweep interval.
    """

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        log.info("IndexSweepScheduler started (every %ds)", settings.workspace_index_sweep_interval_s)

    async def stop(self) -> None:
        if self._task is None:
            return
        assert self._stop_event is not None
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        log.info("IndexSweepScheduler stopped")

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("IndexSweepScheduler tick failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=settings.workspace_index_sweep_interval_s)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> dict:
        """Public so tests can call it directly. Processes the dirty queue
        across all workspaces, plus a verification pass for missed changes."""
        db = SessionLocal()
        try:
            counts = await reindex_dirty(db, limit=200)
            verified = await self._verify_missed_changes(db)
            counts["verified_dirty"] = verified
            return counts
        finally:
            db.close()

    async def _verify_missed_changes(self, db: Session) -> int:
        """Cheap safety net: compare stored content_hash against the current
        WorkspaceFile.checksum for recently-touched clean resources, in case
        a trigger point was missed. Marks mismatches dirty for the next tick."""
        from api.db.models import WorkspaceFile, IndexedResource

        cutoff = datetime.now(timezone.utc) - timedelta(seconds=settings.workspace_index_sweep_interval_s * 2)
        rows = (
            db.query(IndexedResource)
            .filter(
                IndexedResource.resource_type == "workspace_file",
                IndexedResource.status == "clean",
                IndexedResource.updated_at >= cutoff,
            )
            .limit(500)
            .all()
        )
        marked = 0
        for row in rows:
            wf = db.query(WorkspaceFile).filter(WorkspaceFile.id == row.resource_id).first()
            if not wf:
                crud.upsert_indexed_resource_dirty(db, row.resource_type, row.resource_id, row.workspace_id, reason="missing_source")
                marked += 1
            elif wf.checksum != row.content_hash:
                crud.upsert_indexed_resource_dirty(db, row.resource_type, row.resource_id, row.workspace_id, reason="hash_mismatch_sweep")
                marked += 1
        return marked


index_sweep_scheduler = IndexSweepScheduler()
