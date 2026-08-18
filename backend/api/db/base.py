"""SQLAlchemy engine, session factory, and dependency."""
from __future__ import annotations
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, Session, DeclarativeBase

from api.config import settings


class Base(DeclarativeBase):
    pass


def _make_engine():
    url = settings.db_url
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    
    # SQLite doesn't support connect_timeout, only PostgreSQL does
    connect_args = {}
    if not url.startswith("sqlite://"):
        connect_args = {"connect_timeout": 10}
    
    return create_engine(
        url,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
        connect_args=connect_args,
    )


engine = _make_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency — yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_all_tables() -> None:
    """Create all tables if they don't exist, then apply column migrations."""
    from . import models  # noqa: F401 — ensure models are imported before create_all
    _drop_superseded_connector_tables()
    Base.metadata.create_all(bind=engine)
    _apply_migrations()
    _seed_connectors()


def _drop_superseded_connector_tables() -> None:
    """
    One-time cleanup: the Phase-1 connector tables (fixed access/refresh-token
    columns, no category/auth-strategy/sync metadata) are superseded by the
    Enterprise Connector Framework schema. No real user ever completed a
    connector OAuth flow against the old schema, so there is no data to
    migrate — old tables are dropped so create_all() lays down the new shape
    cleanly.

    This must NOT drop tables that already have the new shape (that would
    wipe real connector data on every restart) — it only fires once, gated
    on the presence of the old `encrypted_access_token` column, which never
    exists in the new schema.
    """
    import logging
    from sqlalchemy import inspect as sa_inspect
    log = logging.getLogger(__name__)

    inspector = sa_inspect(engine)
    existing_tables = set(inspector.get_table_names())

    if "user_connector_accounts" in existing_tables:
        columns = {c["name"] for c in inspector.get_columns("user_connector_accounts")}
        if "encrypted_access_token" in columns:
            # Old shape confirmed — safe to drop all 3 Phase-1 connector tables together.
            with engine.begin() as conn:
                for table in ("connector_action_logs", "user_connector_accounts", "connectors"):
                    conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
                    log.info("Dropped superseded Phase-1 connector table: %s", table)


def _seed_connectors() -> None:
    """
    Idempotent upsert of every registered connector's manifest into the
    `connectors` table. The manifest list (real connectors + declared-but-
    not-yet-implemented placeholders) is the single source of truth — see
    api.services.connectors.bootstrap.get_all_manifests().
    """
    import logging
    from . import models
    from api.services.connectors.bootstrap import get_all_manifests, IMPLEMENTED_PROVIDERS
    log = logging.getLogger(__name__)

    with SessionLocal() as db:
        try:
            existing = {c.provider: c for c in db.query(models.Connector).all()}
            for manifest in get_all_manifests():
                data = manifest.as_dict()
                enabled = manifest.provider in IMPLEMENTED_PROVIDERS
                row = existing.get(manifest.provider)
                if row is None:
                    db.add(models.Connector(
                        provider=manifest.provider,
                        display_name=manifest.display_name,
                        category=data["category"],
                        auth_strategy_type=data["auth_strategy_type"],
                        icon=manifest.icon,
                        enabled=enabled,
                        supports_sync=manifest.supports_sync,
                        supports_health_check=manifest.supports_health_check,
                        capabilities=data["capabilities"],
                        configuration={},
                    ))
                else:
                    # Keep the manifest snapshot current on every startup —
                    # capability lists evolve as connectors get implemented.
                    row.display_name = manifest.display_name
                    row.category = data["category"]
                    row.auth_strategy_type = data["auth_strategy_type"]
                    row.icon = manifest.icon
                    row.enabled = enabled
                    row.supports_sync = manifest.supports_sync
                    row.supports_health_check = manifest.supports_health_check
                    row.capabilities = data["capabilities"]
            db.commit()
        except Exception as exc:
            db.rollback()
            log.warning("Connector seed skipped: %s", exc)


def _apply_migrations() -> None:
    """
    Idempotent column-level migrations.

    create_all() only creates missing *tables* — it never alters existing ones.
    Any new columns added to existing ORM models need explicit ALTER TABLE
    statements so they are applied to existing deployed databases.

    All statements use IF NOT EXISTS / safe variants so they are safe to run
    on every startup without failing on a fresh or already-migrated DB.
    """
    import logging
    log = logging.getLogger(__name__)

    migrations: list[tuple[str, str]] = [
        # ── translation_projects new provider-platform columns (Task #22) ──────
        (
            "translation_projects.provider_name",
            "ALTER TABLE translation_projects "
            "ADD COLUMN IF NOT EXISTS provider_name VARCHAR(32) DEFAULT 'auto'",
        ),
        (
            "translation_projects.quality_breakdown",
            "ALTER TABLE translation_projects "
            "ADD COLUMN IF NOT EXISTS quality_breakdown JSON",
        ),
        (
            "translation_projects.engineering_review_changes",
            "ALTER TABLE translation_projects "
            "ADD COLUMN IF NOT EXISTS engineering_review_changes JSON",
        ),
        (
            "translation_projects.dnt_tokens",
            "ALTER TABLE translation_projects "
            "ADD COLUMN IF NOT EXISTS dnt_tokens JSON",
        ),
        # ── rag_documents background-processing status column ────────────────
        (
            "rag_documents.status",
            "ALTER TABLE rag_documents "
            "ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'ready'",
        ),
        # ── translation_usage DeepL character billing column ─────────────────
        (
            "translation_usage.chars_translated",
            "ALTER TABLE translation_usage "
            "ADD COLUMN IF NOT EXISTS chars_translated INTEGER NOT NULL DEFAULT 0",
        ),
        # ── self-learning: rag_documents content hash ────────────────────────
        (
            "rag_documents.content_hash",
            "ALTER TABLE rag_documents "
            "ADD COLUMN IF NOT EXISTS content_hash VARCHAR(64)",
        ),
        # ── self-learning: training_slides approval ──────────────────────────
        (
            "training_slides.approval_status",
            "ALTER TABLE training_slides "
            "ADD COLUMN IF NOT EXISTS approval_status VARCHAR(32) NOT NULL DEFAULT 'pending'",
        ),
        (
            "training_slides.approved_at",
            "ALTER TABLE training_slides "
            "ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITH TIME ZONE",
        ),
        # ── self-learning: education_outputs approval timestamp ───────────────
        (
            "education_outputs.approved_at",
            "ALTER TABLE education_outputs "
            "ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP WITH TIME ZONE",
        ),
        # ── study_jobs: archived flag for owner undo/archive workflow ─────────
        (
            "study_jobs.archived",
            "ALTER TABLE study_jobs "
            "ADD COLUMN IF NOT EXISTS archived BOOLEAN NOT NULL DEFAULT FALSE",
        ),
        # ── Vision Cost Protection: rag_documents pre-flight estimate ─────────
        (
            "rag_documents.vision_estimate",
            "ALTER TABLE rag_documents "
            "ADD COLUMN IF NOT EXISTS vision_estimate JSON",
        ),
        # ── Vision Cost Protection: rag_images new guard columns ─────────────
        (
            "rag_images.image_sha256",
            "ALTER TABLE rag_images "
            "ADD COLUMN IF NOT EXISTS image_sha256 VARCHAR(64)",
        ),
        (
            "rag_images.vision_skipped",
            "ALTER TABLE rag_images "
            "ADD COLUMN IF NOT EXISTS vision_skipped BOOLEAN NOT NULL DEFAULT FALSE",
        ),
        (
            "rag_images.skip_reason",
            "ALTER TABLE rag_images "
            "ADD COLUMN IF NOT EXISTS skip_reason VARCHAR(64)",
        ),
        (
            "rag_images.vision_cost_usd",
            "ALTER TABLE rag_images "
            "ADD COLUMN IF NOT EXISTS vision_cost_usd FLOAT NOT NULL DEFAULT 0",
        ),
        # ── Cost Dashboard: chat_usage table is created by create_all; add
        #    columns defensively for existing deployments ─────────────────────
        (
            "chat_usage.request_id",
            "ALTER TABLE chat_usage "
            "ADD COLUMN IF NOT EXISTS request_id VARCHAR(64)",
        ),
        (
            "chat_usage.conversation_id",
            "ALTER TABLE chat_usage "
            "ADD COLUMN IF NOT EXISTS conversation_id VARCHAR(36)",
        ),
        (
            "chat_usage.user_id",
            "ALTER TABLE chat_usage "
            "ADD COLUMN IF NOT EXISTS user_id VARCHAR(128)",
        ),
        # ── Large file upload tables ──────────────────────────────────────────
        # UploadSession and ProcessingJob are new tables created by create_all
        # on fresh deployments. The column below is added after initial release
        # to fix the idempotent /complete path (session→job linkage).
        (
            "upload_sessions.job_id",
            "ALTER TABLE upload_sessions "
            "ADD COLUMN IF NOT EXISTS job_id VARCHAR(36)",
        ),
        (
            "upload_sessions.result_doc_id",
            "ALTER TABLE upload_sessions "
            "ADD COLUMN IF NOT EXISTS result_doc_id VARCHAR(36)",
        ),
        # ── Large source-file disk storage ───────────────────────────────────────
        (
            "translation_projects.source_file_path",
            "ALTER TABLE translation_projects "
            "ADD COLUMN IF NOT EXISTS source_file_path VARCHAR(1024)",
        ),
        # ── Publication-readiness gate: structured reference metadata ────────
        (
            "research_outputs.readiness_meta",
            "ALTER TABLE research_outputs "
            "ADD COLUMN IF NOT EXISTS readiness_meta JSON",
        ),
        # ── AI Chat Workspace agent: link a conversation to its active workspace ──
        # workspaces/workspace_files/workspace_tasks/task_events/generated_files
        # are new tables created by create_all() on fresh deployments; this column
        # is added to the pre-existing conversations table for upgraded deployments.
        (
            "conversations.workspace_id",
            "ALTER TABLE conversations "
            "ADD COLUMN IF NOT EXISTS workspace_id VARCHAR(36)",
        ),
        # ── Persistent AI Memory: anonymous session isolation ─────────────────
        # Anonymous conversations are scoped by anon_session_id instead of the
        # shared user_id=NULL bucket. memory_items/conversation_summaries/
        # indexed_resources are new tables created by create_all().
        (
            "conversations.anon_session_id",
            "ALTER TABLE conversations "
            "ADD COLUMN IF NOT EXISTS anon_session_id VARCHAR(64)",
        ),
        # ── Microsoft Office Desktop Automation translation backend ──────────
        (
            "translation_projects.formatting_fidelity",
            "ALTER TABLE translation_projects "
            "ADD COLUMN IF NOT EXISTS formatting_fidelity VARCHAR(32) DEFAULT 'reconstructed'",
        ),
        # ── Knowledge Evolution Engine (Phase 2A): versioning on knowledge_nodes ──
        # research_plans/research_topics/knowledge_evidence are new tables created
        # by create_all(); these columns are added to the pre-existing
        # knowledge_nodes/knowledge_edges tables for upgraded deployments.
        (
            "knowledge_nodes.version",
            "ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
        ),
        (
            "knowledge_nodes.confidence",
            "ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS confidence FLOAT NOT NULL DEFAULT 0.5",
        ),
        (
            "knowledge_nodes.evidence_count",
            "ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS evidence_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "knowledge_nodes.status",
            "ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'current'",
        ),
        (
            "knowledge_nodes.supersedes_id",
            "ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS supersedes_id VARCHAR(36)",
        ),
        (
            "knowledge_nodes.replaced_by_id",
            "ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS replaced_by_id VARCHAR(36)",
        ),
        (
            "knowledge_nodes.research_topic_id",
            "ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS research_topic_id VARCHAR(36)",
        ),
        # ── Knowledge Evolution Engine (Phase 2A): versioning on knowledge_edges ──
        (
            "knowledge_edges.version",
            "ALTER TABLE knowledge_edges ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1",
        ),
        (
            "knowledge_edges.confidence",
            "ALTER TABLE knowledge_edges ADD COLUMN IF NOT EXISTS confidence FLOAT NOT NULL DEFAULT 0.5",
        ),
        (
            "knowledge_edges.evidence_count",
            "ALTER TABLE knowledge_edges ADD COLUMN IF NOT EXISTS evidence_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "knowledge_edges.status",
            "ALTER TABLE knowledge_edges ADD COLUMN IF NOT EXISTS status VARCHAR(16) NOT NULL DEFAULT 'current'",
        ),
        (
            "research_queue_items.topic_id",
            "ALTER TABLE research_queue_items ADD COLUMN IF NOT EXISTS topic_id VARCHAR(36)",
        ),
        # ── Knowledge Evolution Engine (Phase 2B.0/2B.1) ──────────────────────
        # curiosity_questions is a new table created by create_all(); these
        # columns are added to the pre-existing knowledge_nodes/knowledge_edges/
        # research_missions tables for upgraded deployments.
        (
            "knowledge_nodes.provider_used",
            "ALTER TABLE knowledge_nodes ADD COLUMN IF NOT EXISTS provider_used VARCHAR(24)",
        ),
        (
            "knowledge_edges.provider_used",
            "ALTER TABLE knowledge_edges ADD COLUMN IF NOT EXISTS provider_used VARCHAR(24)",
        ),
        (
            "research_missions.curiosity_settings",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS curiosity_settings JSON",
        ),
        # ── Bounded resume queue / atomic claim / provider throttle (2B.2.1) ──
        (
            "research_missions.priority",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS priority INTEGER NOT NULL DEFAULT 100",
        ),
        (
            "research_missions.origin",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS origin VARCHAR(16) NOT NULL DEFAULT 'user'",
        ),
        (
            "research_missions.queued_at",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS queued_at TIMESTAMP WITH TIME ZONE",
        ),
        (
            "research_missions.claim_owner",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS claim_owner VARCHAR(128)",
        ),
        (
            "research_missions.claim_expires_at",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS claim_expires_at TIMESTAMP WITH TIME ZONE",
        ),
        (
            "research_missions.heartbeat_at",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS heartbeat_at TIMESTAMP WITH TIME ZONE",
        ),
        (
            "research_missions.resume_count",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS resume_count INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "research_missions.next_retry_at",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS next_retry_at TIMESTAMP WITH TIME ZONE",
        ),
        (
            "research_missions.last_attempt_error_type",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS last_attempt_error_type VARCHAR(32)",
        ),
        # ── Dynamic Source Trust (Phase 2B.3) ─────────────────────────────────
        (
            "research_sources.dynamic_trust_score",
            "ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS dynamic_trust_score FLOAT NOT NULL DEFAULT 50.0",
        ),
        (
            "research_sources.effective_trust_score",
            "ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS effective_trust_score FLOAT NOT NULL DEFAULT 50.0",
        ),
        (
            "research_sources.trust_status",
            "ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS trust_status VARCHAR(24) NOT NULL DEFAULT 'unproven'",
        ),
        (
            "research_sources.trust_algorithm_version",
            "ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS trust_algorithm_version INTEGER NOT NULL DEFAULT 1",
        ),
        (
            "research_sources.last_trust_calculated_at",
            "ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS last_trust_calculated_at TIMESTAMP WITH TIME ZONE",
        ),
        (
            "research_sources.trust_signal_summary",
            "ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS trust_signal_summary JSON",
        ),
        (
            "research_sources.source_family_id",
            "ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS source_family_id VARCHAR(80)",
        ),
        (
            "research_sources.source_doi",
            "ALTER TABLE research_sources ADD COLUMN IF NOT EXISTS source_doi VARCHAR(256)",
        ),
        # ── Research Memory & Knowledge Freshness (Phase 2B.4) ────────────────
        (
            "research_topics.topic_memory_id",
            "ALTER TABLE research_topics ADD COLUMN IF NOT EXISTS topic_memory_id VARCHAR(36)",
        ),
        # ── Autonomous Internet Learning + Manufacturer/Scientific Intelligence (Phase 2B.5) ──
        (
            "research_queue_items.academic_metadata",
            "ALTER TABLE research_queue_items ADD COLUMN IF NOT EXISTS academic_metadata JSON",
        ),
        (
            "research_missions.coverage_target",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS coverage_target FLOAT NOT NULL DEFAULT 70.0",
        ),
        (
            "research_missions.max_coverage_rounds",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS max_coverage_rounds INTEGER NOT NULL DEFAULT 3",
        ),
        (
            "research_missions.coverage_rounds_completed",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS coverage_rounds_completed INTEGER NOT NULL DEFAULT 0",
        ),
        (
            "research_missions.detected_manufacturer",
            "ALTER TABLE research_missions ADD COLUMN IF NOT EXISTS detected_manufacturer VARCHAR(128)",
        ),
    ]

    # SQLite's ALTER TABLE supports ADD COLUMN but not the "IF NOT EXISTS"
    # clause used above (Postgres-only), so on SQLite that clause makes every
    # statement fail — silently, since failures are swallowed below — and no
    # column ever gets added. Detect the column's presence via PRAGMA
    # table_info() instead and strip the unsupported clause before executing.
    is_sqlite = engine.dialect.name == "sqlite"

    with engine.begin() as conn:
        for label, sql in migrations:
            table, _, column = label.partition(".")
            if is_sqlite:
                existing_columns = {
                    row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))
                }
                if column in existing_columns:
                    log.debug("Migration OK (already present): %s", label)
                    continue
                sql = sql.replace("ADD COLUMN IF NOT EXISTS ", "ADD COLUMN ")
            try:
                conn.execute(text(sql))
                log.debug("Migration OK: %s", label)
            except Exception as exc:
                # Log but do not abort — if the column already exists with a
                # different type some DBs raise; treat all errors as non-fatal
                # so a fresh DB (where create_all handled everything) doesn't fail.
                log.warning("Migration skipped (%s): %s", label, exc)
