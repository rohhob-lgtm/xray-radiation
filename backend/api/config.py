"""Application configuration loaded from environment variables."""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(Path(__file__).resolve().parents[1] / ".env"),
            str(Path(__file__).resolve().parents[2] / ".env"),
        ),
        extra="ignore",
    )

    # Server
    port: int = 8000

    # Database
    database_url: str = ""

    # Auth
    disable_auth: bool = False  # Set to True for local development (disables Replit OIDC)
    session_secret: str = "dev-secret-change-in-production"
    repl_id: str = ""
    replit_dev_domain: str = ""
    replit_domains: str = ""

    # ── Production hardening ────────────────────────────────────────────────────
    # environment: "development" | "production". Controls secure-cookie flags,
    # whether interactive API docs are exposed, HSTS emission, auto-reload, and
    # whether insecure defaults (e.g. the placeholder session secret) are allowed.
    environment: str = "development"
    # Explicit debug flag. Forced off whenever environment == "production".
    debug: bool = False
    # Intentional open (no-auth) public deployment. When true, DISABLE_AUTH is
    # treated as a deliberate choice rather than a production misconfiguration,
    # so the site can run in `environment=production` (docs off, secure cookies,
    # HSTS, trusted-host checks) while still serving anonymous users. The cost
    # guard and upload/rate limits remain the protection layer in this mode.
    allow_open_access: bool = False

    # ── Google sign-in + free-tier quotas ───────────────────────────────────────
    # When auth_enabled is true the app runs the tiered model: anonymous browsers
    # get `anon_free_translations` free jobs; signing in with Google raises the
    # allowance to `account_free_translations`; beyond that the user is prompted to
    # buy a plan (paid tiers are a later phase). While false the site stays fully
    # open (current launch behaviour) — so this can be built now and switched on
    # once the Google OAuth credentials below are set.
    auth_enabled: bool = False
    google_client_id: str = ""
    google_client_secret: str = ""
    # Public origin used to build the OAuth redirect URI, e.g.
    # https://translation-studio.onrender.com (no trailing slash). Empty = derive
    # from the incoming request.
    public_base_url: str = ""
    anon_free_translations: int = 1
    account_free_translations: int = 5

    # CORS: comma-separated allow-list of exact origins. Empty means "derive a
    # safe default" (localhost dev ports + the configured Replit domain). The
    # wildcard "*" is only honoured in development and never together with
    # credentialed requests.
    cors_allow_origins: str = ""

    # Trusted Host allow-list (comma-separated hostnames). Empty disables the
    # TrustedHostMiddleware host check. Enforced only in production.
    allowed_hosts: str = ""

    # Inbound API rate limiting (per client IP, in-process sliding window).
    enable_rate_limit: bool = True
    rate_limit_requests: int = 120         # general budget per window
    rate_limit_window_s: int = 60          # window length in seconds
    rate_limit_auth_requests: int = 15     # tighter budget for auth/login paths
    rate_limit_auth_window_s: int = 60
    rate_limit_ai_requests: int = 20       # tighter budget for the AI tutor (cost abuse)
    rate_limit_ai_window_s: int = 60

    # Security response headers.
    enable_security_headers: bool = True
    hsts_max_age: int = 31536000           # 1 year, seconds
    # Content-Security-Policy applied to non-docs responses. Overridable via env
    # for deployments that embed the API under a specific frontend origin.
    content_security_policy: str = (
        "default-src 'none'; frame-ancestors 'none'; base-uri 'none'; "
        "form-action 'none'"
    )

    # Session cookie hardening. In production these are forced to the secure
    # settings regardless of the values below (see cookie_* properties).
    session_cookie_secure: bool = False
    session_cookie_samesite: str = "lax"
    session_max_age_days: int = 30

    # OpenAI
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"

    # Google Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    # Anthropic Claude
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"

    # Ollama
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5-7b-fast6:latest"

    # Microsoft Copilot / Azure OpenAI
    copilot_api_key: str = ""
    copilot_endpoint: str = ""
    copilot_deployment: str = "gpt-4"

    # Active provider (gemini | openai | ollama | copilot | mock)
    active_provider: str = "gemini"

    # ── Literature-search providers (Research Studio external retrieval) ───────
    # Crossref, OpenAlex, PubMed, arXiv, and DOAJ work fully unauthenticated.
    # These two are optional — blank means "skip" (CORE) or "use the public,
    # lower rate-limit tier" (Semantic Scholar), never a fake/mocked call.
    semantic_scholar_api_key: str = ""
    core_api_key: str = ""

    # Translation guard behavior (dev-only overrides)
    development_mode: bool = False
    disable_translation_rate_limit: bool = False
    disable_hourly_quota: bool = False
    disable_daily_quota: bool = False
    disable_monthly_quota: bool = False

    # ── Large file upload limits ───────────────────────────────────────────────
    max_upload_size_mb: int = 2000          # overall file size ceiling
    max_pdf_pages: int = 5000
    max_pptx_slides: int = 2000
    max_docx_pages: int = 5000
    max_xlsx_sheets: int = 500
    max_zip_uncompressed_size_mb: int = 5000
    max_zip_file_count: int = 5000

    # ── Study / AI cost limits ────────────────────────────────────────────────
    max_study_cost_per_file_usd: float = 2.00
    max_ai_calls_per_file: int = 100
    max_tokens_per_batch: int = 30000
    max_concurrent_study_jobs: int = 3

    # ── Chunked upload settings ───────────────────────────────────────────────
    upload_chunk_size_mb: int = 10          # chunk size for large file uploads
    chunked_upload_threshold_mb: int = 10   # files >= this use chunked protocol

    # Directory where uploaded source files are stored on disk (instead of DB bytea)
    upload_storage_dir: str = "/tmp/translation_uploads"

    # ── AI Chat Workspace (file/folder agent workspace) ───────────────────────
    workspace_storage_dir: str = "backend/uploads/workspaces"
    max_workspace_files: int = 2000
    max_workspace_total_size_mb: int = 2000
    max_workspace_file_size_mb: int = 200
    max_workspace_path_depth: int = 32
    max_workspace_path_length: int = 500
    max_agent_tool_calls_per_turn: int = 25

    # ── Connectors: Canva Connect API (OAuth 2.0 Authorization Code + PKCE) ────
    canva_client_id: str = ""
    canva_client_secret: str = ""
    # Overrides the computed default below (used for non-local deployments).
    canva_redirect_uri: str = ""
    # Encryption key for connector tokens at rest. Read via pydantic (so .env
    # file values work without a manual shell export) rather than raw
    # os.environ — see api/utils/crypto.py. Falls back to session_secret if unset.
    canva_token_encryption_key: str = ""
    connector_token_encryption_key: str = ""

    # ── Persistent AI Memory: Global AI Brain / Hybrid Workspace Awareness ─────
    # How many new conversation turns accumulate before a rolling summary is
    # generated (one LLM call, not per-message classification).
    memory_summary_every_n_messages: int = 25
    # Background safety-net sweep interval — catches any workspace-awareness
    # trigger that was missed (15-30 min requested range; default 25 min).
    workspace_index_sweep_interval_s: int = 1500
    # Time budget for a pre-response inline reindex before falling back to a
    # background task instead of blocking the chat response.
    workspace_index_refresh_budget_ms: int = 2500
    # Bumping this lazily invalidates every cached embedding on next touch —
    # no mass rebuild job needed when the embedding model/pipeline changes.
    embedding_model_version: str = "text-embedding-3-small@1"

    # ── Connectors: other OAuth2 platforms ──────────────────────────────────────
    # One app per *platform*, not per connector — a single Google Cloud OAuth
    # client covers Drive/Gmail/Calendar; a single Microsoft Entra app
    # registration covers OneDrive/SharePoint/Teams via Microsoft Graph.
    google_client_id: str = ""
    google_client_secret: str = ""
    # Overrides the computed default (google_drive's callback path) — matches
    # the canva_redirect_uri override pattern; only needed for non-local deployments.
    google_redirect_uri: str = ""
    google_token_encryption_key: str = ""

    microsoft_client_id: str = ""
    microsoft_client_secret: str = ""

    dropbox_client_id: str = ""
    dropbox_client_secret: str = ""

    atlassian_client_id: str = ""
    atlassian_client_secret: str = ""

    slack_client_id: str = ""
    slack_client_secret: str = ""

    # ── Research mission scheduler / provider throttling (Phase 2B.2.1) ────────
    # Bounded resume queue — see api.services.research_agent.mission_queue.
    research_resume_batch_size: int = 10
    research_max_active_missions: int = 3
    research_max_pending_in_memory: int = 25
    research_scheduler_startup_delay_s: int = 5
    research_claim_lease_seconds: int = 600
    research_mission_max_attempts: int = 5

    # Central provider throttle — see api.services.research_agent.provider_throttle.
    # Conservative, internally-chosen defaults (not each provider's documented
    # official limit, which varies and isn't authoritative here) — every value
    # is overridable via env/`.env` following this same field-name pattern.
    research_provider_crossref_rpm: int = 30
    research_provider_crossref_concurrency: int = 4
    research_provider_openalex_rpm: int = 30
    research_provider_openalex_concurrency: int = 4
    research_provider_semantic_scholar_rpm: int = 20
    research_provider_semantic_scholar_concurrency: int = 2
    research_provider_pubmed_rpm: int = 20
    research_provider_pubmed_concurrency: int = 3
    research_provider_arxiv_rpm: int = 20
    research_provider_arxiv_concurrency: int = 3
    research_provider_core_rpm: int = 15
    research_provider_core_concurrency: int = 2
    research_provider_doaj_rpm: int = 20
    research_provider_doaj_concurrency: int = 3
    research_provider_patentsview_rpm: int = 15
    research_provider_patentsview_concurrency: int = 2
    research_provider_web_search_rpm: int = 15
    research_provider_web_search_concurrency: int = 2
    research_provider_direct_crawl_rpm: int = 30
    research_provider_direct_crawl_concurrency: int = 5
    research_provider_ollama_rpm: int = 60
    research_provider_ollama_concurrency: int = 4
    # doi.org content-negotiation lookups (_verify_doi) — a Crossref-adjacent
    # resolver, not one of the search/discovery APIs above; added when
    # reconciling with a concurrent session's DOI-verification addition.
    research_provider_doi_resolver_rpm: int = 30
    research_provider_doi_resolver_concurrency: int = 4
    # Circuit breaker: consecutive failures before opening, cooldown before a
    # half-open probe.
    research_provider_breaker_failure_threshold: int = 5
    research_provider_breaker_cooldown_s: int = 60

    # ── Dynamic Source Trust (Phase 2B.3) ───────────────────────────────────
    # Bounded recalculation worker — same claim/lease/bounded-concurrency
    # pattern as the mission scheduler (2B.2.1), a distinct small worker.
    trust_recalc_batch_size: int = 20
    trust_recalc_max_concurrent: int = 2
    trust_recalc_claim_lease_seconds: int = 300
    trust_recalc_max_attempts: int = 3
    # Periodic-audit staleness threshold — sources with no recalculation in
    # this many days are eligible for the worker's background sweep.
    trust_recalc_staleness_days: int = 14
    # Effective = trust_static_weight * static + trust_dynamic_weight * dynamic.
    trust_static_weight: float = 0.5
    trust_dynamic_weight: float = 0.5

    # ── Research Memory & Knowledge Freshness (Phase 2B.4) ──────────────────
    # Bounded batch per MissionScheduler.tick() — same "never fan out
    # unbounded" discipline as every other scheduler sweep in this codebase.
    knowledge_refresh_sweep_batch_size: int = 5
    # Freshness thresholds in days, per content_category: (fresh, acceptable, aging).
    # Beyond "aging" is Outdated, except Research Papers which never age into
    # Outdated (only Fresh/Acceptable/Aging/Unknown apply — see
    # research_memory.compute_freshness()).
    freshness_thresholds_days: dict = {
        "Safety Documents": (30, 90, 180),
        "Standards": (90, 365, 730),
        "Manufacturer Docs": (90, 180, 365),
        "Manuals": (180, 365, 730),
        "Research Papers": (180, 365, 365),
    }

    # ── Intelligent Knowledge Router (Phase 2B.6) ────────────────────────────
    # AI Chat's automatic fallback to a bounded live-research pass through
    # the existing Research Agent when its own RAG/graph confidence is low
    # for a research-worthy question — see api.services.knowledge_router and
    # api.services.research_agent.quick_research. knowledge_router_enabled is
    # an instant kill switch (no deploy needed) if this ever needs to be
    # disabled without touching chat.py.
    knowledge_router_enabled: bool = True
    knowledge_router_confidence_threshold: float = 0.35
    knowledge_router_timeout_seconds: float = 8.0
    knowledge_router_max_sources: int = 3
    knowledge_router_min_reresearch_minutes: int = 30

    # ── Expert Reasoning Engine (Phase 2B.7) ─────────────────────────────────
    # Read-only context-assembly layer over the existing Knowledge Graph —
    # see api.services.research_brain.reasoning_engine. Instant kill switch,
    # same convention as knowledge_router_enabled.
    reasoning_engine_enabled: bool = True

    # ── Proactive AI Scientist (Phase 2B.8) ──────────────────────────────────
    # A thin classification/alerting layer over the existing Scheduler/
    # Research Agent/Curiosity Engine/Trust/Research Memory — see
    # api.services.research_brain.ai_scientist. Instant kill switch, same
    # convention as knowledge_router_enabled/reasoning_engine_enabled.
    ai_scientist_enabled: bool = True
    ai_scientist_daily_mission_limit: int = 3
    ai_scientist_daily_alert_limit: int = 10
    ai_scientist_dedup_window_days: int = 7
    ai_scientist_low_coverage_threshold: float = 60.0
    ai_scientist_min_trust_for_established_fact: float = 60.0

    # ── Knowledge Health (Phase 2B.9) ────────────────────────────────────────
    # A cached scoring/aggregation layer over signals every prior phase
    # already produces — see api.services.research_brain.knowledge_health.
    # Instant kill switch, same convention as the other Phase 2B.6-2B.8 flags.
    knowledge_health_enabled: bool = True
    knowledge_health_audit_batch_size: int = 20
    knowledge_health_low_trust_threshold: float = 60.0

    # ── Multimodal Internet Image Retrieval ──────────────────────────────────
    # Bounded fallback used only when the Knowledge Base image search
    # (gallery_service.py) genuinely finds nothing — see
    # api.services.research_agent.image_discovery. Never downloads/caches
    # image bytes, only metadata + the original external URL.
    image_retrieval_enabled: bool = True
    image_retrieval_max_images: int = 6
    image_retrieval_timeout_seconds: float = 8.0
    image_retrieval_min_trust_score: float = 40.0

    # ── Production hardening helpers ────────────────────────────────────────────
    @property
    def is_production(self) -> bool:
        return self.environment.strip().lower() in {"production", "prod"}

    @property
    def debug_enabled(self) -> bool:
        """Debug is only ever on outside production, and only if explicitly set."""
        return bool(self.debug) and not self.is_production

    @property
    def docs_enabled(self) -> bool:
        """Interactive API docs are exposed only outside production."""
        return not self.is_production

    @property
    def cookie_secure(self) -> bool:
        """HTTPS-only cookies are mandatory in production."""
        return True if self.is_production else bool(self.session_cookie_secure)

    @property
    def cookie_samesite(self) -> str:
        """SameSite policy for the session cookie.

        Use "lax" (not "strict"): the Google OAuth callback is a top-level
        cross-site navigation back from accounts.google.com, and a Strict cookie
        is withheld on it — so the stored OAuth state is missing at the callback
        and sign-in fails. Lax sends the cookie on top-level GET navigations
        (exactly the callback) while still blocking CSRF POSTs, which is the
        standard, secure choice for OAuth. Overridable via env otherwise.
        """
        if self.is_production:
            return "lax"
        value = (self.session_cookie_samesite or "lax").strip().lower()
        return value if value in {"strict", "lax", "none"} else "lax"

    @property
    def cors_origins(self) -> list[str]:
        """Resolve the CORS allow-list to an explicit list of origins.

        Never returns the credential-incompatible wildcard in production. In
        development, an unset/blank value falls back to the common localhost
        dev-server ports plus the configured Replit domain.
        """
        raw = (self.cors_allow_origins or "").strip()
        if raw:
            origins = [o.strip() for o in raw.split(",") if o.strip()]
            if "*" in origins and self.is_production:
                # Wildcard is unsafe with credentials — drop it in production.
                origins = [o for o in origins if o != "*"]
            return origins

        origins = [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
        ]
        for domain in (self.replit_dev_domain, self.replit_domains):
            for host in (domain or "").split(","):
                host = host.strip()
                if host:
                    origins.append(f"https://{host}")
        return origins

    @property
    def trusted_hosts(self) -> list[str]:
        return [h.strip() for h in (self.allowed_hosts or "").split(",") if h.strip()]

    def validate_production_secrets(self) -> list[str]:
        """Return a list of misconfiguration errors for a production deploy.

        Called at startup. In production a non-empty result aborts boot so the
        app never runs with insecure defaults; outside production the same
        issues are logged as warnings only.
        """
        problems: list[str] = []
        insecure_secrets = {"", "dev-secret-change-in-production", "changeme", "secret"}
        if self.session_secret.strip().lower() in insecure_secrets:
            problems.append(
                "SESSION_SECRET is unset or using an insecure default — set a "
                "long random value from the environment."
            )
        if len(self.session_secret) < 32:
            problems.append("SESSION_SECRET must be at least 32 characters.")
        if self.disable_auth and not self.allow_open_access:
            problems.append(
                "DISABLE_AUTH must be false in production (or set "
                "ALLOW_OPEN_ACCESS=true to intentionally run an open, no-auth site)."
            )
        if self.debug:
            problems.append("DEBUG must be false in production.")
        if "*" in [o.strip() for o in (self.cors_allow_origins or "").split(",")]:
            problems.append("CORS_ALLOW_ORIGINS must not contain '*' in production.")
        return problems

    @property
    def db_url(self) -> str:
        """Return a psycopg2-compatible URL."""
        url = self.database_url or os.environ.get("DATABASE_URL", "")
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)
        if url.startswith("sqlite:///"):
            path_part = url[len("sqlite:///"):]
            # Keep absolute sqlite paths unchanged, but normalize relative
            # ones against the backend directory so cwd changes do not
            # silently create a different database file.
            is_windows_abs = (
                len(path_part) >= 3
                and path_part[0] == "/"
                and path_part[1].isalpha()
                and path_part[2] == ":"
            )
            if path_part and path_part != ":memory:" and not is_windows_abs and not os.path.isabs(path_part):
                backend_root = Path(__file__).resolve().parents[1]
                abs_path = (backend_root / path_part).resolve()
                url = f"sqlite:///{abs_path.as_posix()}"
        return url

    @property
    def callback_url(self) -> str:
        domain = self.replit_dev_domain or os.environ.get("REPLIT_DEV_DOMAIN", "localhost")
        # Use http:// for localhost (local dev), https:// for Replit
        scheme = "https" if domain != "localhost" else "http"
        return f"{scheme}://{domain}/api/callback"

    @property
    def base_url(self) -> str:
        domain = self.replit_dev_domain or os.environ.get("REPLIT_DEV_DOMAIN", "localhost")
        # Use http:// for localhost (local dev), https:// for Replit
        scheme = "https" if domain != "localhost" else "http"
        return f"{scheme}://{domain}"

    @property
    def canva_redirect_uri_resolved(self) -> str:
        """
        The exact redirect_uri to send to Canva — must match the Canva
        Developer Portal integration's configured redirect URI byte-for-byte.

        Local dev: the backend's own 127.0.0.1 port (NOT the Vite frontend
        port) since the callback is handled by this FastAPI server directly.
        """
        if self.canva_redirect_uri:
            return self.canva_redirect_uri
        return self.connector_redirect_uri("canva")

    def connector_redirect_uri(self, provider: str) -> str:
        """
        Default local-dev redirect_uri for an OAuth2 connector's generic
        callback route (`/api/connectors/{provider}/callback`).

        Each connector gets its own callback path even when several share one
        OAuth app (e.g. Google Drive/Gmail/Calendar all use one Google Cloud
        client, but each needs its own registered redirect URI — Google/
        Microsoft/etc. OAuth apps support registering multiple redirect URIs
        under a single client, so this is not a limitation).
        """
        return f"http://127.0.0.1:{self.port}/api/connectors/{provider}/callback"


settings = Settings(
    database_url=os.environ.get("DATABASE_URL", ""),
    repl_id=os.environ.get("REPL_ID", ""),
    replit_dev_domain=os.environ.get("REPLIT_DEV_DOMAIN", ""),
    replit_domains=os.environ.get("REPLIT_DOMAINS", ""),
    session_secret=os.environ.get("SESSION_SECRET", "dev-secret-change-in-production"),
    openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
)
