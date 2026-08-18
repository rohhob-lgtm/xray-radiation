"""
Symmetric encryption for connector tokens at rest.

Key resolution goes through api.config.settings (pydantic-settings), NOT
raw os.environ. This project never calls python-dotenv's load_dotenv(), so
.env file contents are only ever parsed by pydantic-settings into
`settings.*` — a plain os.environ.get() here would only ever see a
variable that was actually exported in the shell, silently ignoring
anything set only in backend/.env or the repo-root .env. Reading through
`settings` is what makes "edit .env, restart the backend" actually work.
"""
from __future__ import annotations

import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from api.config import settings

log = logging.getLogger(__name__)


def _get_fernet() -> Fernet:
    """
    Derive a Fernet instance from, in order of preference:
    CANVA_TOKEN_ENCRYPTION_KEY, GOOGLE_TOKEN_ENCRYPTION_KEY,
    CONNECTOR_TOKEN_ENCRYPTION_KEY, SESSION_SECRET.

    One key encrypts every connector's tokens (Canva, Google Drive, and
    everything else) — the provider-named variables are accepted as aliases
    since that's what's documented per-integration, but there is only ever
    one key in effect. CANVA_TOKEN_ENCRYPTION_KEY is checked first
    deliberately: it's the one already set and actively encrypting a real
    connected account's tokens, so a later-added GOOGLE_TOKEN_ENCRYPTION_KEY
    must never silently take priority and break existing decryption — as
    long as the Canva key stays set, adding the Google one has no effect,
    which is the safe behavior (rotate by removing the old one on purpose).
    A dedicated key is preferred over SESSION_SECRET so rotating it doesn't
    also invalidate login sessions. Raises RuntimeError if nothing usable is
    configured — never falls back to a hardcoded key.
    """
    secret = (
        settings.canva_token_encryption_key
        or settings.google_token_encryption_key
        or settings.connector_token_encryption_key
        or settings.session_secret
    )
    if len(secret) < 16:
        raise RuntimeError(
            "No connector token encryption key is configured (checked "
            "CANVA_TOKEN_ENCRYPTION_KEY, GOOGLE_TOKEN_ENCRYPTION_KEY, "
            "CONNECTOR_TOKEN_ENCRYPTION_KEY, SESSION_SECRET) — cannot encrypt connector "
            "tokens safely. Set one to a random string of at least 16 characters in "
            "backend/.env and restart the backend."
        )
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode()).digest())
    return Fernet(key)


def encrypt_secret(plaintext: str) -> str:
    """Encrypt a token for DB storage. Raises on failure — fails closed."""
    try:
        return _get_fernet().encrypt(plaintext.encode()).decode()
    except Exception as exc:
        raise RuntimeError(
            f"Connector token encryption failed — refusing to store unencrypted: {exc}"
        ) from exc


def decrypt_secret(ciphertext: str) -> str | None:
    """Decrypt a token from DB storage. Returns None if decryption fails."""
    try:
        return _get_fernet().decrypt(ciphertext.encode()).decode()
    except (InvalidToken, Exception):
        log.warning("Connector token decryption failed")
        return None
