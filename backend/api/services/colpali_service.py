"""
ColPali-style multimodal RAG — visual embeddings for page-level retrieval.

Backends (auto-detected in order):
  1. colqwen2   — ColQwen2-v1 via colpali-engine + torch  (needs ≥6 GB RAM / GPU)
  2. openclip   — OpenCLIP ViT-L/14  (~1.2 GB RAM, CPU-friendly, single-vector)
  3. disabled   — both unavailable; image search falls back to caption+text embeddings

Storage format
  ColQwen2  →  colpali_vecs = List[List[float]]  (N_patches × 128)   multi-vector
  OpenCLIP  →  colpali_vecs = List[List[float]]  ([[vec]])             single-vector-wrapped

Scoring
  Both use the same MaxSim formula:
    score(Q, D) = Σ_q  max_d  dot(q, d)
  For single-vector this reduces to plain cosine similarity.
"""
from __future__ import annotations
import asyncio
import io
import logging
import math
import os
from concurrent.futures import ThreadPoolExecutor
from typing import Any, List, Optional, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from api.db.models import RagPage

log = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────

COLQWEN2_MODEL  = "vidore/colqwen2-v1.0"
OPENCLIP_MODEL  = "ViT-L-14"
OPENCLIP_PRETRAINED = "openai"
PAGE_RENDER_PX  = 1024          # longest edge for page renders fed to the model
MAXSIM_THRESHOLD = 0.0          # minimum MaxSim score to include a page in results

# Thread pool for CPU-bound inference (keeps FastAPI event loop responsive)
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="colpali")

# ──────────────────────────────────────────────────────────────
# Backend state (lazy-initialised)
# ──────────────────────────────────────────────────────────────

_backend: str = "uninitialised"   # "colqwen2" | "openclip" | "disabled"
_backend_state: str = "not_loaded"  # not_loaded | loading | ready | failed
_colqwen2_model: Any = None
_colqwen2_processor: Any = None
_openclip_model: Any = None
_openclip_preprocess: Any = None
_openclip_tokenizer: Any = None
_init_lock = asyncio.Lock()


def get_backend_state() -> str:
    """
    Return the current vision model readiness state.
    Values: "not_loaded" | "loading" | "ready" | "failed"
    Call this before triggering ColPali work to avoid blocking.
    """
    return _backend_state


def is_vision_ready() -> bool:
    """True only when the visual embedding backend is loaded and operational."""
    return _backend_state == "ready"


def _sync_detect_and_load() -> str:
    """
    Detect and load the best visual embedding backend.

    Runs ENTIRELY in a thread-pool worker — never touches the asyncio event loop.
    All imports, filesystem scans (scan_cache_dir), psutil calls, and model
    weight loading happen here so the event loop stays free during initialisation.

    Sets the global model variables directly (safe under the GIL).
    """
    global _colqwen2_model, _colqwen2_processor
    global _openclip_model, _openclip_preprocess, _openclip_tokenizer

    forced = os.environ.get("COLPALI_BACKEND", "").lower()

    # ── Try ColQwen2 ────────────────────────────────────────────────────────
    if forced not in ("openclip", "disabled"):
        try:
            import torch
            from colpali_engine.models import ColQwen2, ColQwen2Processor
            import psutil
            from huggingface_hub import scan_cache_dir

            free_gb = psutil.virtual_memory().available / 1e9
            if free_gb < 6.0 and not torch.cuda.is_available():
                raise RuntimeError(
                    f"only {free_gb:.1f} GB RAM free — ColQwen2 needs ≥6 GB. "
                    "Use GPU or set COLPALI_BACKEND=colqwen2 to override."
                )

            # scan_cache_dir does filesystem I/O — must stay in thread
            cache = scan_cache_dir()
            cached_repos = {r.repo_id for r in cache.repos}
            if COLQWEN2_MODEL not in cached_repos and not os.environ.get("HF_DOWNLOAD_COLQWEN2"):
                raise RuntimeError(
                    "ColQwen2 not in local HF cache. Set HF_DOWNLOAD_COLQWEN2=1 "
                    "to allow the ~8 GB download on first run."
                )

            hf_token = os.environ.get("HF_TOKEN") or None
            log.info("Loading ColQwen2 (%s) …", COLQWEN2_MODEL)
            proc = ColQwen2Processor.from_pretrained(COLQWEN2_MODEL, token=hf_token)
            mdl = ColQwen2.from_pretrained(
                COLQWEN2_MODEL,
                torch_dtype=torch.bfloat16,
                device_map="auto" if torch.cuda.is_available() else "cpu",
                low_cpu_mem_usage=True,
                attn_implementation="eager",
                token=hf_token,
            )
            mdl.eval()
            _colqwen2_model, _colqwen2_processor = mdl, proc
            log.info("ColQwen2 loaded — multi-vector late-interaction retrieval active")
            return "colqwen2"

        except Exception as exc:
            log.warning("ColQwen2 unavailable (%s) — trying OpenCLIP", exc)

    # ── Try OpenCLIP ────────────────────────────────────────────────────────
    if forced != "disabled":
        try:
            import open_clip   # import stays inside thread — not on event loop
            import torch
            import psutil

            # OpenCLIP ViT-L/14 weights are ~1.2 GB but the translation pipeline
            # also needs RAM for document processing (PyMuPDF, python-pptx, GPT
            # context buffers).  Require at least 3.5 GB free before loading so
            # the model doesn't starve the worker and trigger an OOM-kill.
            # Hosts with a GPU bypass this check (GPU VRAM is separate).
            free_gb = psutil.virtual_memory().available / 1e9
            if free_gb < 3.5 and not torch.cuda.is_available():
                raise RuntimeError(
                    f"only {free_gb:.1f} GB RAM free — OpenCLIP ViT-L/14 needs ≥3.5 GB "
                    "headroom to coexist with the translation pipeline. "
                    "Set COLPALI_BACKEND=openclip to override the guard."
                )

            log.info("Loading OpenCLIP %s (%.1f GB RAM free) …", OPENCLIP_MODEL, free_gb)
            mdl, _, prep = open_clip.create_model_and_transforms(
                OPENCLIP_MODEL, pretrained=OPENCLIP_PRETRAINED
            )
            tok = open_clip.get_tokenizer(OPENCLIP_MODEL)
            mdl.eval()
            _openclip_model, _openclip_preprocess, _openclip_tokenizer = mdl, prep, tok
            log.info("OpenCLIP ViT-L/14 loaded — using single-vector visual retrieval")
            return "openclip"

        except Exception as exc:
            log.warning("OpenCLIP unavailable (%s) — visual search disabled", exc)

    log.warning("No visual embedding backend available; image search uses caption text only")
    return "disabled"


async def _init_backend() -> str:
    """
    Detect and initialise the best available visual embedding backend.
    Called once; subsequent calls return immediately via the lock guard.

    ALL blocking work (imports, filesystem scan, model weight loading) runs in
    a thread-pool worker via _sync_detect_and_load so the event loop is never
    stalled — not even for the milliseconds spent on `import open_clip`.

    State transitions: not_loaded → loading → ready | failed
    Call get_backend_state() to check readiness without awaiting.
    """
    global _backend, _backend_state

    async with _init_lock:
        if _backend != "uninitialised":
            return _backend
        _backend_state = "loading"
        log.info("[vision] backend: loading in thread pool …")
        try:
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(_executor, _sync_detect_and_load)
            _backend = result
            _backend_state = "ready" if result != "disabled" else "failed"
            log.info("[vision] backend: %s → state=%s", _backend, _backend_state)
        except Exception as exc:
            _backend = "disabled"
            _backend_state = "failed"
            log.error("[vision] backend init failed: %s", exc)
        return _backend


async def get_backend() -> str:
    """Return the active backend name, initialising it first if needed."""
    if _backend == "uninitialised":
        await _init_backend()
    return _backend


# ──────────────────────────────────────────────────────────────
# Image → visual vectors
# ──────────────────────────────────────────────────────────────

async def embed_image(image_bytes: bytes) -> Optional[List[List[float]]]:
    """
    Return visual patch/token vectors for one page image.
      ColQwen2 → List[N_patches][128]  (multi-vector)
      OpenCLIP → [[1536-dim vector]]   (single-vector wrapped)
      disabled → None
    """
    backend = await get_backend()

    if backend == "colqwen2":
        return await asyncio.get_running_loop().run_in_executor(
            _executor, _embed_image_colqwen2, image_bytes
        )
    if backend == "openclip":
        return await asyncio.get_running_loop().run_in_executor(
            _executor, _embed_image_openclip, image_bytes
        )
    return None


def _embed_image_colqwen2(image_bytes: bytes) -> Optional[List[List[float]]]:
    try:
        import torch
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = _resize_for_model(img)

        batch = _colqwen2_processor.process_images([img])
        batch = {k: v.to(_colqwen2_model.device) for k, v in batch.items()}
        with torch.no_grad():
            vecs = _colqwen2_model(**batch)   # (1, N, dim)
        return vecs[0].cpu().float().tolist()
    except Exception as exc:
        log.error("ColQwen2 image embed error: %s", exc)
        return None


def _embed_image_openclip(image_bytes: bytes) -> Optional[List[List[float]]]:
    try:
        import torch
        from PIL import Image

        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        tensor = _openclip_preprocess(img).unsqueeze(0)
        with torch.no_grad():
            vec = _openclip_model.encode_image(tensor, normalize=True)
        return [vec[0].cpu().float().tolist()]   # wrap in list → [[…]]
    except Exception as exc:
        log.error("OpenCLIP image embed error: %s", exc)
        return None


# ──────────────────────────────────────────────────────────────
# Query → visual vectors
# ──────────────────────────────────────────────────────────────

async def embed_query(query: str) -> Optional[List[List[float]]]:
    """
    Return visual query vectors for a text string.
      ColQwen2 → List[N_tokens][128]
      OpenCLIP → [[1536-dim vector]]
      disabled → None
    """
    backend = await get_backend()

    if backend == "colqwen2":
        return await asyncio.get_running_loop().run_in_executor(
            _executor, _embed_query_colqwen2, query
        )
    if backend == "openclip":
        return await asyncio.get_running_loop().run_in_executor(
            _executor, _embed_query_openclip, query
        )
    return None


def _embed_query_colqwen2(query: str) -> Optional[List[List[float]]]:
    try:
        import torch

        batch = _colqwen2_processor.process_queries([query])
        batch = {k: v.to(_colqwen2_model.device) for k, v in batch.items()}
        with torch.no_grad():
            vecs = _colqwen2_model(**batch)   # (1, N, dim)
        return vecs[0].cpu().float().tolist()
    except Exception as exc:
        log.error("ColQwen2 query embed error: %s", exc)
        return None


def _embed_query_openclip(query: str) -> Optional[List[List[float]]]:
    try:
        import torch

        tokens = _openclip_tokenizer([query])
        with torch.no_grad():
            vec = _openclip_model.encode_text(tokens, normalize=True)
        return [vec[0].cpu().float().tolist()]
    except Exception as exc:
        log.error("OpenCLIP query embed error: %s", exc)
        return None


# ──────────────────────────────────────────────────────────────
# MaxSim scoring
# ──────────────────────────────────────────────────────────────

def maxsim(
    query_vecs: List[List[float]],
    doc_vecs: List[List[float]],
) -> float:
    """
    Late-interaction MaxSim (ColBERT-style):
      score = Σ_q  max_d  dot(q, d)

    Works for both ColQwen2 (multi-vector) and OpenCLIP (single-vector wrapped).
    Optimised for CPU using pure Python — fast enough for hundreds of pages.
    """
    total = 0.0
    for q in query_vecs:
        best = max(_dot(q, d) for d in doc_vecs)
        total += best
    return total / len(query_vecs)   # normalise by query length


def _dot(a: List[float], b: List[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


# ──────────────────────────────────────────────────────────────
# Page-level visual search
# ──────────────────────────────────────────────────────────────

def _sync_score_pages(
    pages_with_vecs: list,
    q_vecs: List[List[float]],
    top_k: int,
) -> list:
    """
    CPU-bound MaxSim scoring over all indexed pages.

    Runs in thread-pool via run_in_executor — never on the event loop.
    With 408+ pages × 768-dim vectors this loop would stall uvicorn for
    seconds if run inline in an async handler.
    """
    scored: List[Tuple[Any, float]] = []
    for page in pages_with_vecs:
        try:
            score = maxsim(q_vecs, page.colpali_vecs)
            scored.append((page, score))
        except Exception:
            continue

    if not scored:
        return pages_with_vecs[:top_k]

    scored.sort(key=lambda x: x[1], reverse=True)
    return [p for p, _ in scored[:top_k]]


async def search_pages_colpali(
    query: str,
    db,
    top_k: int = 5,
) -> List["RagPage"]:
    """
    Retrieve the most visually relevant document pages for a query.

    1. Embeds the query with the active visual backend (thread-pool).
    2. Scores every indexed page by MaxSim against its stored visual vectors
       (thread-pool — 408+ pages would block the event loop if run inline).
    3. Returns top_k pages sorted by score.
    4. Falls back to empty list if no backend is active or no pages are indexed.
    """
    from api.db.crud import get_all_rag_pages

    backend = await get_backend()

    pages = get_all_rag_pages(db)
    pages_with_vecs = [p for p in pages if p.colpali_vecs]

    if not pages_with_vecs:
        return []

    if backend == "disabled":
        # No visual backend — cannot score; return most recent pages as a hint
        return pages_with_vecs[:top_k]

    # Embed query (runs in thread-pool executor inside embed_query)
    q_vecs = await embed_query(query)
    if not q_vecs:
        return pages_with_vecs[:top_k]

    # Score every indexed page in thread-pool — keeps event loop free
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, _sync_score_pages, pages_with_vecs, q_vecs, top_k
    )


# ──────────────────────────────────────────────────────────────
# Background indexing — called after a page is stored
# ──────────────────────────────────────────────────────────────

async def process_rag_page(db, page_id: str) -> None:
    """
    Generate ColPali visual embeddings for a stored RagPage and persist them.
    Designed to run as a fire-and-forget asyncio background task.
    """
    from api.db.crud import get_rag_page, update_rag_page_vecs

    page = get_rag_page(db, page_id)
    if not page or not page.image_data:
        return

    try:
        vecs = await embed_image(bytes(page.image_data))
        if vecs:
            update_rag_page_vecs(db, page_id, vecs)
            log.info(
                "Indexed page %d of %s (%s vecs × %d dim)",
                page.page_num, page.doc_filename, len(vecs), len(vecs[0])
            )
    except Exception as exc:
        log.error("process_rag_page %s failed: %s", page_id, exc)


# ──────────────────────────────────────────────────────────────
# Utility
# ──────────────────────────────────────────────────────────────

def _resize_for_model(img) -> Any:
    """Resize image so the longest edge ≤ PAGE_RENDER_PX (keeps aspect ratio)."""
    from PIL import Image
    w, h = img.size
    if max(w, h) <= PAGE_RENDER_PX:
        return img
    if w >= h:
        new_w, new_h = PAGE_RENDER_PX, int(h * PAGE_RENDER_PX / w)
    else:
        new_w, new_h = int(w * PAGE_RENDER_PX / h), PAGE_RENDER_PX
    return img.resize((new_w, new_h), Image.LANCZOS)
