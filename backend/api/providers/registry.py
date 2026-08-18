"""
Translation Provider Registry.

Maintains a list of available providers, loads their configuration from the
database, and selects the active provider for a translation project.

Priority order (lower number = higher priority):
  1 = DeepL          (best quality)
  2 = Azure          (corporate/enterprise)
  3 = Google         (fastest)
  4 = OpenAI         (AI editing / fallback)
"""
from __future__ import annotations

import logging
import os

from .base import TranslationProvider
from .deepl import DeepLProvider
from .azure import AzureTranslatorProvider
from .google import GoogleTranslateProvider
from .openai_provider import OpenAITranslatorProvider

log = logging.getLogger(__name__)

# Priority → provider_id mapping
_PRIORITY_ORDER = ["deepl", "azure", "google", "openai"]

# provider_id → class
_PROVIDER_CLASSES: dict[str, type[TranslationProvider]] = {
    "deepl":  DeepLProvider,
    "azure":  AzureTranslatorProvider,
    "google": GoogleTranslateProvider,
    "openai": OpenAITranslatorProvider,
}


class ProviderRegistry:
    """
    Manages translation provider instances.

    Providers are loaded from the database at request time (not at module load)
    so that DB changes take effect immediately without restarts.
    """

    def get_provider(
        self,
        provider_name: str,
        db=None,
        user_id: str | None = None,
    ) -> TranslationProvider:
        """
        Get a configured provider instance by name.

        If provider_name is "auto", selects the highest-priority configured
        provider. Falls back to OpenAI if nothing else is configured.

        Args:
            provider_name: "auto" | "deepl" | "azure" | "google" | "openai"
            db: SQLAlchemy session (optional — if None, uses env vars only)
            user_id: owner filter for DB config lookup
        """
        configs = self._load_configs(db, user_id) if db else {}

        if provider_name == "auto":
            return self._select_auto(configs)

        pid = provider_name.lower()
        if pid not in _PROVIDER_CLASSES:
            log.warning("Unknown provider '%s' — falling back to OpenAI", pid)
            return self._make_openai(configs.get("openai"))

        cfg = configs.get(pid, {})
        return self._instantiate(pid, cfg)

    def list_providers(
        self,
        db=None,
        user_id: str | None = None,
    ) -> list[dict]:
        """Return metadata for all 4 providers with DB config applied."""
        configs = self._load_configs(db, user_id) if db else {}
        result = []
        for pid in _PRIORITY_ORDER:
            cfg = configs.get(pid, {})
            instance = self._instantiate(pid, cfg)
            result.append({
                "provider_id": pid,
                "display_name": instance.display_name,
                "description": instance.description,
                "best_for": instance.best_for,
                "is_configured": instance.is_configured,
                "is_enabled": cfg.get("is_enabled", pid == "openai"),
                "is_fallback": cfg.get("is_fallback", pid == "openai"),
                "priority": cfg.get("priority", _PRIORITY_ORDER.index(pid) + 1),
                "max_file_size_mb": cfg.get("max_file_size_mb", 50),
                "max_pages": cfg.get("max_pages", 500),
                "supported_langs": cfg.get("supported_langs", []),
                "extra_config": {
                    k: v for k, v in cfg.items()
                    if k not in ("api_key", "is_enabled", "is_fallback", "priority",
                                 "max_file_size_mb", "max_pages", "supported_langs")
                },
            })
        return result

    # ── Internal ───────────────────────────────────────────────────────────────

    def _load_configs(self, db, user_id: str | None) -> dict[str, dict]:
        """Load provider configs from DB. Returns {provider_id: config_dict}."""
        try:
            from api.db.models import ProviderConfig
            rows = db.query(ProviderConfig).filter(
                (ProviderConfig.user_id == user_id) | (ProviderConfig.user_id.is_(None))
            ).all()
            result: dict[str, dict] = {}
            for row in rows:
                cfg = {**(row.extra_config or {})}
                cfg["is_enabled"] = row.is_enabled
                cfg["is_fallback"] = row.is_fallback
                cfg["priority"] = row.priority
                cfg["max_file_size_mb"] = row.max_file_size_mb
                cfg["max_pages"] = row.max_pages
                cfg["supported_langs"] = row.supported_langs or []
                # Decrypt API key
                if row.api_key_enc:
                    cfg["api_key"] = _decrypt_key(row.api_key_enc)
                # User config overrides shared config
                if row.provider_name not in result or row.user_id is not None:
                    result[row.provider_name] = cfg
            return result
        except Exception as e:
            log.warning("Could not load provider configs from DB: %s", e)
            return {}

    def _select_auto(self, configs: dict[str, dict]) -> TranslationProvider:
        """Pick highest-priority configured and enabled provider."""
        for pid in _PRIORITY_ORDER:
            cfg = configs.get(pid, {})
            # OpenAI is always available via env var
            if pid == "openai":
                return self._instantiate(pid, cfg)
            if cfg.get("is_enabled") and cfg.get("api_key"):
                provider = self._instantiate(pid, cfg)
                if provider.is_configured:
                    log.info("Auto-selected provider: %s", pid)
                    return provider
        # Fallback to OpenAI
        log.info("Auto-selected provider: openai (fallback)")
        return self._make_openai(configs.get("openai"))

    def _instantiate(self, provider_id: str, cfg: dict) -> TranslationProvider:
        cls = _PROVIDER_CLASSES[provider_id]
        api_key = cfg.get("api_key") or (os.environ.get("OPENAI_API_KEY") if provider_id == "openai" else None)
        extra = {k: v for k, v in cfg.items() if k not in ("api_key",)}
        return cls(api_key=api_key, extra_config=extra)

    def _make_openai(self, cfg: dict | None) -> OpenAITranslatorProvider:
        cfg = cfg or {}
        return OpenAITranslatorProvider(
            api_key=cfg.get("api_key") or os.environ.get("OPENAI_API_KEY"),
            extra_config={k: v for k, v in cfg.items() if k != "api_key"},
        )


# ── Encryption helpers ─────────────────────────────────────────────────────────

def _get_fernet():
    """
    Get a Fernet instance derived from SESSION_SECRET.

    Raises RuntimeError if SESSION_SECRET is absent or too short.
    Never falls back to a hardcoded default — doing so would encrypt
    provider API keys with a predictable key, defeating at-rest protection.
    """
    import base64
    import hashlib
    from cryptography.fernet import Fernet
    secret = os.environ.get("SESSION_SECRET", "")
    if len(secret) < 16:
        raise RuntimeError(
            "SESSION_SECRET is not set or too short — cannot encrypt provider API keys safely. "
            "Set SESSION_SECRET to a random string of at least 16 characters."
        )
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_key(plaintext: str) -> str:
    """
    Encrypt an API key for DB storage.

    Raises RuntimeError if encryption fails — never stores credentials
    as plaintext; fails closed to prevent credential-at-rest exposure.
    """
    try:
        return _get_fernet().encrypt(plaintext.encode()).decode()
    except Exception as exc:
        raise RuntimeError(
            f"API key encryption failed — refusing to store credentials unencrypted: {exc}"
        ) from exc


def decrypt_key(ciphertext: str) -> str:
    """Decrypt an API key from DB storage."""
    return _decrypt_key(ciphertext)


def _decrypt_key(ciphertext: str) -> str:
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except Exception:
        # Decryption failed — return empty string so the provider reports
        # "not configured" rather than passing garbage as an API key.
        log.warning("API key decryption failed — treating provider as unconfigured")
        return ""


# Singleton
provider_registry = ProviderRegistry()
