"""
X-Ray Academy AI Assistant — FastAPI entry point (production-ready).

Features:
  - Replit OIDC authentication (session-based via cookie)
  - PostgreSQL persistence for all data
  - Streaming chat with SSE
  - RAG knowledge base
  - Multi-provider AI (OpenAI, Ollama, Copilot, Mock)
"""
import os
import logging
from pathlib import Path

# Standalone Translation Studio: load backend/.env before anything reads settings,
# regardless of the current working directory. (The main platform relied on the
# host/launcher to inject env vars; this clone is self-contained.)
from dotenv import load_dotenv
load_dotenv(Path(__file__).with_name(".env"))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from api.config import settings
from api.routes import router
from api.security import install_security

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Fail fast on insecure production configuration
# ──────────────────────────────────────────────────────────
_config_problems = settings.validate_production_secrets()
if _config_problems:
    if settings.is_production:
        raise RuntimeError(
            "Refusing to start in production with insecure configuration:\n  - "
            + "\n  - ".join(_config_problems)
        )
    for _p in _config_problems:
        logger.warning("Security config (non-production): %s", _p)

app = FastAPI(
    title="X-Ray Academy AI Assistant",
    description="Production-ready AI assistant for X-ray security screening professionals.",
    version="2.0.0",
    # Interactive docs and the OpenAPI schema are exposed only outside production.
    docs_url="/api/docs" if settings.docs_enabled else None,
    redoc_url="/api/redoc" if settings.docs_enabled else None,
    openapi_url="/api/openapi.json" if settings.docs_enabled else None,
    # Never surface Starlette's interactive-traceback debug page to clients.
    debug=settings.debug_enabled,
)

# ──────────────────────────────────────────────────────────
# Middleware (order matters — last added runs first / outermost)
# ──────────────────────────────────────────────────────────

app.add_middleware(
    SessionMiddleware,
    secret_key=settings.session_secret,
    session_cookie="xray_session",
    max_age=86400 * settings.session_max_age_days,
    # HttpOnly is set by Starlette automatically. Secure + SameSite are forced
    # to the hardened values in production (see config cookie_* properties).
    https_only=settings.cookie_secure,
    same_site=settings.cookie_samesite,
)

# Explicit CORS allow-list. Credentialed requests are incompatible with the "*"
# wildcard, so origins come from config (safe localhost defaults in dev).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Requested-With"],
)

# Host-header validation (enforced in production when an allow-list is set).
if settings.is_production and settings.trusted_hosts:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)

# Security headers, inbound rate limiting, and stack-trace-hiding exception
# handlers. Added last so its response headers wrap every other layer.
install_security(app)

# ──────────────────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────────────────

app.include_router(router, prefix="/api")


# ──────────────────────────────────────────────────────────
# Static SPA (single-origin "publish rehearsal")
# ──────────────────────────────────────────────────────────
# When the frontend has been built (artifacts/xray-academy/dist/public), serve it
# from this same FastAPI process so the whole app is one origin — exactly how it
# will run in production on Linux (no separate dev server, no CORS). If the build
# is absent, this is skipped and the API still runs on its own (use `vite dev`).
_SPA_DIST = Path(__file__).resolve().parent.parent / "artifacts" / "xray-academy" / "dist" / "public"
if _SPA_DIST.is_dir():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    _assets_dir = _SPA_DIST / "assets"
    if _assets_dir.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets_dir)), name="assets")

    @app.get("/{full_path:path}")
    async def _spa_fallback(full_path: str):
        # /api/* is handled above (registered first); never serve the SPA for it.
        if full_path.startswith("api/"):
            from fastapi import HTTPException as _HTTPException
            raise _HTTPException(status_code=404, detail="Not Found")
        candidate = _SPA_DIST / full_path
        if full_path and candidate.is_file():
            # Serve .apk with the correct MIME + as an attachment so browsers
            # download it instead of rendering the binary as text.
            if full_path.lower().endswith(".apk"):
                return FileResponse(
                    str(candidate),
                    media_type="application/vnd.android.package-archive",
                    filename=candidate.name,
                )
            return FileResponse(str(candidate))
        # Client-side routes (e.g. /translation) → serve the SPA entry point.
        return FileResponse(str(_SPA_DIST / "index.html"))

    logger.info("Serving built SPA from %s", _SPA_DIST)
else:
    logger.info("No SPA build at %s — API-only (run `vite dev` for the UI)", _SPA_DIST)


# ──────────────────────────────────────────────────────────
# Startup
# ──────────────────────────────────────────────────────────

@app.on_event("startup")
def on_startup():
    """Create database tables and log provider status."""
    try:
        from api.db.base import create_all_tables
        create_all_tables()
        logger.info("Database tables created/verified")
    except Exception as exc:
        logger.error("Database startup error: %s", exc)

    # ── Clean up orphaned translation slots from previous session ──────────────
    try:
        from api.utils.cost_guard import startup_cleanup
        startup_cleanup()
    except Exception as exc:
        logger.error("Slot cleanup error (non-fatal): %s", exc)

    from api.services.ai_providers.registry import provider_registry
    try:
        from api.db.base import SessionLocal
        _db = SessionLocal()
        try:
            provider_registry.restore_from_db(_db)
        finally:
            _db.close()
    except Exception as exc:
        logger.warning("Provider restore skipped: %s", exc)

    try:
        provider_registry.refresh_startup_provider_status()
    except Exception as exc:
        logger.warning("Provider status probe skipped: %s", exc)

    active = provider_registry.get_active()
    logger.info(
        "Active provider loaded from persistent storage: %s",
        active.provider_name if active else "None",
    )
    logger.info("Active AI provider: %s", active.provider_name if active else "None")
    ollama_warning = provider_registry.get_warning("ollama")
    if ollama_warning:
        logger.warning(ollama_warning)

    # ── Recover stuck documents from previous server crash/reload ─────────────
    # Background asyncio tasks are killed on uvicorn reload. Any doc still in
    # "processing" state with extracted text (word_count > 0) was orphaned.
    # Reset them to "ready" so the frontend can show them and the user can
    # re-trigger the study pipeline if needed.
    try:
        from api.db.base import SessionLocal
        from api.db.models import RagDocument
        from datetime import datetime, timezone, timedelta
        _db = SessionLocal()
        try:
            cutoff = datetime.now(timezone.utc) - timedelta(minutes=5)
            stuck = (
                _db.query(RagDocument)
                .filter(
                    RagDocument.status == "processing",
                    RagDocument.word_count > 0,
                    RagDocument.created_at < cutoff,
                )
                .all()
            )
            if stuck:
                for doc in stuck:
                    doc.status = "ready"
                _db.commit()
                logger.info(
                    "Startup recovery: reset %d orphaned 'processing' docs to 'ready'",
                    len(stuck),
                )
        finally:
            _db.close()
    except Exception as exc:
        logger.warning("Startup recovery skipped: %s", exc)


@app.on_event("startup")
def _migrate_layout_columns():
    """Add layout_config / reference_template_data columns to existing tables."""
    try:
        from api.db.base import engine
        from sqlalchemy import text as _text
        with engine.connect() as _conn:
            _conn.execute(_text(
                "ALTER TABLE translation_projects "
                "ADD COLUMN IF NOT EXISTS layout_config JSON"
            ))
            _conn.execute(_text(
                "ALTER TABLE translation_projects "
                "ADD COLUMN IF NOT EXISTS reference_template_data BYTEA"
            ))
            _conn.commit()
        logger.info("layout_config / reference_template_data columns verified")
    except Exception as _exc:
        logger.debug("Layout column migration: %s", _exc)


@app.on_event("startup")
async def on_startup_async():
    """Resume any queued translation jobs interrupted by a restart.

    TRANSLATION STUDIO CLONE — the main platform's heavy background services
    are intentionally NOT started here:
      • research-agent bootstrap + mission scheduler
      • ColPali visual-search model pre-warm
      • connector sync engine + health monitor
      • workspace index sweep
      • source-trust recalculation worker
    This clone runs the translation pipeline only, so those schedulers would
    consume memory/CPU with no feature depending on them. Re-enable a specific
    one here only if a translation feature is later found to need it.
    """
    try:
        from api.services.job_runner import resume_queued_jobs
        await resume_queued_jobs()
    except Exception as exc:
        logger.warning("Job startup recovery skipped: %s", exc)

    # ── Project retention sweep ────────────────────────────────────────────
    # Auto-delete translation projects (and their stored source/output files)
    # older than PROJECT_RETENTION_HOURS (default 24h) so a public deployment
    # never accumulates uploaded documents — storage hygiene + privacy. Runs
    # once now, then hourly. Set PROJECT_RETENTION_HOURS=0 to disable.
    import asyncio as _asyncio_ret
    from datetime import datetime as _dt_ret, timezone as _tz_ret, timedelta as _td_ret

    _retention_hours = float(os.environ.get("PROJECT_RETENTION_HOURS", "24") or 0)
    # Hard cap on how many projects (uploads) are ever kept — the key defence
    # against an upload flood on a free/open site, since every upload stores a
    # source file even if its translation is later refused by the cost ceiling.
    # Oldest beyond this are deleted every sweep, so peak storage ≈
    # MAX_RETAINED_PROJECTS × (source + output) regardless of daily volume.
    _max_projects = int(os.environ.get("MAX_RETAINED_PROJECTS", "300") or 0)

    def _delete_project(db, p) -> None:
        from api.db.models import TranslationImage
        from api.utils.file_storage import delete_source_file
        try:
            delete_source_file(p)
        except Exception:
            pass
        try:
            db.query(TranslationImage).filter(
                TranslationImage.project_id == p.id
            ).delete(synchronize_session=False)
        except Exception:
            pass
        db.delete(p)

    def _purge_expired_projects() -> int:
        from api.db.base import SessionLocal
        from api.db.models import TranslationProject
        deleted = 0
        db = SessionLocal()
        try:
            # 1) Time-based: anything older than the retention window.
            if _retention_hours > 0:
                cutoff = _dt_ret.now(_tz_ret.utc) - _td_ret(hours=_retention_hours)
                for p in db.query(TranslationProject).filter(
                    TranslationProject.created_at < cutoff
                ).all():
                    _delete_project(db, p)
                    deleted += 1
            # 2) Count cap: keep only the newest N projects, delete the rest.
            if _max_projects > 0:
                overflow = (
                    db.query(TranslationProject)
                    .order_by(TranslationProject.created_at.desc())
                    .offset(_max_projects)
                    .all()
                )
                for p in overflow:
                    _delete_project(db, p)
                    deleted += 1
            if deleted:
                db.commit()
        finally:
            db.close()
        return deleted

    _sweep_secs = int(os.environ.get("RETENTION_SWEEP_SECONDS", "600") or 600)

    async def _retention_loop():
        while True:
            try:
                n = await _asyncio_ret.to_thread(_purge_expired_projects)
                if n:
                    logger.info(
                        "Retention sweep: deleted %d project(s) (>%sh old or beyond %d newest)",
                        n, _retention_hours, _max_projects,
                    )
            except Exception as exc:
                logger.warning("Retention sweep failed (non-fatal): %s", exc)
            await _asyncio_ret.sleep(_sweep_secs)

    if _retention_hours > 0 or _max_projects > 0:
        _asyncio_ret.create_task(_retention_loop())
        logger.info(
            "Project retention enabled: %sh window, max %d projects, sweep every %ds",
            _retention_hours, _max_projects, _sweep_secs,
        )
    else:
        logger.info("Project retention disabled")


@app.on_event("shutdown")
async def on_shutdown():
    """No background schedulers run in the Translation Studio clone."""
    return


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        # Auto-reload is a development convenience only — never in production.
        reload=not settings.is_production,
        log_level="info",
        # Allow large multipart uploads (200 MB file + headers + form fields).
        # h11_max_incomplete_event_size covers incomplete HTTP events in the h11
        # parser; raising it prevents 400 errors on large header blocks that
        # accompany big multipart requests.
        h11_max_incomplete_event_size=8 * 1024 * 1024,  # 8 MB header budget
    )
