"""
In-memory provider registry.

Holds one instance per provider type. At startup the active provider
is set to MockProvider so the app works without any configuration.
Switching providers via the API updates the active_provider here.
"""
from __future__ import annotations
import logging
from typing import Dict, Optional

import httpx

from api.config import settings

log = logging.getLogger(__name__)

# Default automatic-routing rules (seeded once, on first run, into AppSetting —
# never overwrite an explicit user change on restart). Matches the documented
# split: Claude for code/long-document/structured-writing work, Gemini for
# web-search/Drive/image/multimodal/quick work.
_DEFAULT_TASK_ROUTES: Dict[str, str] = {
    "code": "claude",
    "code_review": "claude",
    "debugging": "claude",
    "long_document": "claude",
    "ppt": "claude",
    "pdf": "claude",
    "docx": "claude",
    "curriculum": "claude",
    "structured_writing": "claude",
    "translation_refinement": "claude",
    "web_search": "gemini",
    "google_drive": "gemini",
    "image": "gemini",
    "multimodal": "gemini",
    "quick": "gemini",
}


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers: Dict[str, object] = {}
        self._active_id: str = "mock"
        self._provider_warnings: Dict[str, str] = {}
        self._provider_online: Dict[str, bool] = {}
        # Phase 2 AI Orchestrator: optional per-task-hint provider override
        # (e.g. "vision" -> "openai"). Empty by default — get_for_task()
        # always falls back to get_active(), so this changes nothing until
        # someone explicitly configures a route.
        self._task_routes: Dict[str, str] = {}

    def register(self, provider) -> None:
        self._providers[provider.provider_id] = provider

    def get(self, provider_id: str):
        return self._providers.get(provider_id)

    def get_active(self):
        return self._providers.get(self._active_id)

    def get_for_task(self, task_hint: Optional[str]):
        """
        Multi-model routing — purely additive. Returns the configured
        override provider for `task_hint` if one is set and available,
        otherwise the globally active provider (today's behavior,
        unchanged). No route is configured by default.
        """
        if task_hint:
            override_id = self._task_routes.get(task_hint)
            if override_id:
                provider = self._providers.get(override_id)
                if provider and getattr(provider, "is_configured", False):
                    return provider
        return self.get_active()

    def set_task_route(self, task_hint: str, provider_id: str) -> bool:
        if provider_id not in self._providers:
            return False
        self._task_routes[task_hint] = provider_id
        return True

    def clear_task_route(self, task_hint: str) -> None:
        self._task_routes.pop(task_hint, None)

    def list_task_routes(self) -> Dict[str, str]:
        return dict(self._task_routes)

    def _set_task_route_setting(self, db, task_hint: str, provider_id: str) -> None:
        from api.db.models import AppSetting
        key = f"ai.task_route.{task_hint}"
        row = db.query(AppSetting).filter(AppSetting.key == key).first()
        if row:
            row.value = provider_id
        else:
            db.add(AppSetting(key=key, value=provider_id))

    def persist_task_route(self, db, task_hint: str, provider_id: str) -> bool:
        """Set a per-task provider override and persist it so it survives a restart."""
        if not self.set_task_route(task_hint, provider_id):
            return False
        self._set_task_route_setting(db, task_hint, provider_id)
        db.commit()
        return True

    def persist_clear_task_route(self, db, task_hint: str) -> None:
        self.clear_task_route(task_hint)
        from api.db.models import AppSetting
        row = db.query(AppSetting).filter(AppSetting.key == f"ai.task_route.{task_hint}").first()
        if row:
            db.delete(row)
            db.commit()

    def restore_and_seed_task_routes(self, db) -> None:
        """
        Restore persisted per-task provider overrides from AppSetting. On a
        genuinely first run (no `ai.task_route.*` rows exist at all) seed the
        documented default routing rules — never overwrites a user's explicit
        change on a later restart, since any existing row (default or custom)
        counts as "already configured".
        """
        from api.db.models import AppSetting
        rows = db.query(AppSetting).filter(AppSetting.key.like("ai.task_route.%")).all()
        persisted = {row.key[len("ai.task_route."):]: row.value for row in rows}
        for hint, provider_id in persisted.items():
            self.set_task_route(hint, provider_id)
        if not persisted:
            for hint, provider_id in _DEFAULT_TASK_ROUTES.items():
                self.set_task_route(hint, provider_id)
                self._set_task_route_setting(db, hint, provider_id)
            db.commit()

    def set_active(self, provider_id: str) -> bool:
        if provider_id in self._providers:
            self._active_id = provider_id
            return True
        return False

    @property
    def active_id(self) -> str:
        return self._active_id

    def get_warning(self, provider_id: str) -> Optional[str]:
        return self._provider_warnings.get(provider_id)

    def is_online(self, provider_id: str) -> Optional[bool]:
        return self._provider_online.get(provider_id)

    def all_providers(self):
        return list(self._providers.values())

    def refresh_startup_provider_status(self) -> None:
        """
        Check provider reachability signals at startup.

        This should never change the active provider selection. It only records
        warnings for the UI and logs so persisted selections survive restarts.
        """
        self._provider_warnings.pop("ollama", None)
        self._provider_online.pop("ollama", None)

        # Explicit startup requirement: probe local Ollama endpoint.
        probe_url = "http://127.0.0.1:11434/api/tags"
        try:
            response = httpx.get(probe_url, timeout=2.0)
            is_ok = response.status_code < 500
            self._provider_online["ollama"] = is_ok
            if not is_ok:
                self._provider_warnings["ollama"] = "Ollama is offline"
        except Exception:
            self._provider_online["ollama"] = False
            self._provider_warnings["ollama"] = "Ollama is offline"

    def restore_from_db(self, db) -> None:
        """
        Restore provider runtime settings and active selection from AppSetting.

        This is invoked at startup after tables are created so provider state
        survives server restarts.
        """
        try:
            from api.db.models import AppSetting
        except Exception:
            return

        try:
            self.restore_and_seed_task_routes(db)
        except Exception:
            log.warning("Task-routing restore/seed skipped", exc_info=True)

        settings_map = {
            row.key: row.value
            for row in db.query(AppSetting).filter(
                AppSetting.key.in_(
                    [
                        "ai.active_provider",
                        "ai.active_model",
                        "ai.provider_enabled",
                        "ai.provider_configured",
                        "ai.last_successful_provider",
                        "ai.fallback_provider",
                        "ai.gemini.model",
                        "ai.claude.model",
                        "ai.openai.model",
                        "ai.ollama.base_url",
                        "ai.ollama.model",
                        "ai.copilot.base_url",
                        "ai.copilot.model",
                    ]
                )
            )
        }

        def _set_app_setting(key: str, value: str) -> None:
            row = db.query(AppSetting).filter(AppSetting.key == key).first()
            if row:
                row.value = value
            else:
                db.add(AppSetting(key=key, value=value))

        def _configured_real_provider_ids() -> list[str]:
            ids: list[str] = []
            for pid in ("gemini", "claude", "ollama", "openai", "copilot"):
                p = self.get(pid)
                if p and p.is_configured:
                    ids.append(pid)
            return ids

        def _choose_fallback(*provider_ids: str) -> Optional[str]:
            for pid in provider_ids:
                if not pid:
                    continue
                p = self.get(pid)
                if p and p.is_configured and pid != "mock":
                    return pid
            return None

        # Apply non-secret runtime overrides first.
        gemini = self.get("gemini")
        if gemini and settings_map.get("ai.gemini.model"):
            gemini.model = settings_map["ai.gemini.model"]

        claude = self.get("claude")
        if claude and settings_map.get("ai.claude.model"):
            claude.model = settings_map["ai.claude.model"]

        openai = self.get("openai")
        if openai and settings_map.get("ai.openai.model"):
            openai.model = settings_map["ai.openai.model"]

        ollama = self.get("ollama")
        if ollama and settings_map.get("ai.ollama.base_url"):
            ollama.base_url = settings_map["ai.ollama.base_url"]
        if ollama and settings_map.get("ai.ollama.model"):
            ollama.model = settings_map["ai.ollama.model"]

        copilot = self.get("copilot")
        if copilot and settings_map.get("ai.copilot.base_url"):
            copilot.base_url = settings_map["ai.copilot.base_url"]
        if copilot and settings_map.get("ai.copilot.model"):
            copilot.model = settings_map["ai.copilot.model"]

        persisted_active = (settings_map.get("ai.active_provider") or "").strip().lower()
        persisted_last_success = (settings_map.get("ai.last_successful_provider") or "").strip().lower()
        persisted_fallback = (settings_map.get("ai.fallback_provider") or "").strip().lower()

        # Priority 1: backend database persistent setting
        if persisted_active:
            active_candidate = self.get(persisted_active)
            if active_candidate and persisted_active != "mock" and active_candidate.is_configured:
                self.set_active(persisted_active)
                _set_app_setting("ai.provider_configured", "true")
                _set_app_setting("ai.provider_enabled", "true")
                _set_app_setting("ai.active_model", (getattr(active_candidate, "model", "") or "").strip())
                _set_app_setting("ai.last_successful_provider", persisted_active)
                db.commit()
                return

            # Saved provider unavailable -> fallback to configured real provider and keep warning
            fb = _choose_fallback(
                persisted_fallback,
                persisted_last_success,
                settings.active_provider,
                "gemini",
                "claude",
                "ollama",
                "openai",
                "copilot",
            )
            if fb:
                self._provider_warnings[persisted_active or "mock"] = "Previously selected provider is unavailable"
                self.set_active(fb)
                fb_provider = self.get(fb)
                _set_app_setting("ai.active_provider", fb)
                _set_app_setting("ai.fallback_provider", fb)
                _set_app_setting("ai.provider_enabled", "true")
                _set_app_setting("ai.provider_configured", "true")
                _set_app_setting("ai.active_model", (getattr(fb_provider, "model", "") or "").strip())
                _set_app_setting("ai.last_successful_provider", fb)
                db.commit()
                return

        # Priority 2: environment configuration (via settings object)
        env_choice = (settings.active_provider or "").strip().lower()
        env_fallback = _choose_fallback(env_choice, "gemini", "claude", "ollama", "openai", "copilot")
        if env_fallback:
            env_provider = self.get(env_fallback)
            self.set_active(env_fallback)
            _set_app_setting("ai.active_provider", env_fallback)
            _set_app_setting("ai.fallback_provider", env_fallback)
            _set_app_setting("ai.provider_enabled", "true")
            _set_app_setting("ai.provider_configured", "true")
            _set_app_setting("ai.active_model", (getattr(env_provider, "model", "") or "").strip())
            _set_app_setting("ai.last_successful_provider", env_fallback)
            db.commit()
            return

        # Priority 3: config-file default already mapped via settings.active_provider
        # Priority 4: placeholder only when no real provider is configured
        configured_real = _configured_real_provider_ids()
        if configured_real:
            pick = _choose_fallback("gemini", "claude", "ollama", "openai", "copilot") or configured_real[0]
            pick_provider = self.get(pick)
            self.set_active(pick)
            _set_app_setting("ai.active_provider", pick)
            _set_app_setting("ai.fallback_provider", pick)
            _set_app_setting("ai.provider_enabled", "true")
            _set_app_setting("ai.provider_configured", "true")
            _set_app_setting("ai.active_model", (getattr(pick_provider, "model", "") or "").strip())
            _set_app_setting("ai.last_successful_provider", pick)
            db.commit()
            return

        self.set_active("mock")
        _set_app_setting("ai.active_provider", "mock")
        _set_app_setting("ai.fallback_provider", "mock")
        _set_app_setting("ai.provider_enabled", "false")
        _set_app_setting("ai.provider_configured", "false")
        _set_app_setting("ai.active_model", "")
        db.commit()


# Singleton registry — instantiated once at module import
provider_registry = ProviderRegistry()


def _bootstrap_registry() -> None:
    """Register all providers and set the active one from settings."""
    from .mock_provider import MockProvider
    from .gemini_provider import GeminiProvider
    from .claude_provider import ClaudeProvider
    from .openai_provider import OpenAIProvider
    from .ollama_provider import OllamaProvider
    from .copilot_provider import CopilotProvider

    provider_registry.register(MockProvider())
    provider_registry.register(
        GeminiProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    )
    provider_registry.register(
        ClaudeProvider(api_key=settings.anthropic_api_key, model=settings.anthropic_model)
    )
    provider_registry.register(
        OpenAIProvider(api_key=settings.openai_api_key, model=settings.openai_model)
    )
    provider_registry.register(
        OllamaProvider(base_url=settings.ollama_base_url, model=settings.ollama_model)
    )
    provider_registry.register(
        CopilotProvider(
            api_key=settings.copilot_api_key,
            base_url=settings.copilot_endpoint,
            model=settings.copilot_deployment,
        )
    )

    # Bootstrap chooses a safe real-provider default before DB restore runs.
    # Gemini stays first — adding Claude must never silently take over as the
    # default active provider.
    for pid in ("gemini", "claude", "ollama", "openai", "copilot"):
        provider = provider_registry.get(pid)
        if provider and provider.is_configured:
            provider_registry.set_active(pid)
            break
    else:
        provider_registry.set_active("mock")


_bootstrap_registry()
