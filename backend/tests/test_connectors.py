"""
Enterprise Connector Framework tests: manifest/registry validation, all 6
auth strategies, the credential store, cross-user isolation, Canva +
Local Folder end-to-end (Canva's real Canva Connect HTTP calls are
monkeypatched at the client.py/oauth2_pkce.py boundary — Local Folder's
filesystem calls are real, against a pytest tmp_path), and the sync/health
background schedulers.
"""
import base64
import hashlib
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth
from api.db.base import SessionLocal
from api.db.models import User
from api.db import crud
from api.utils import crypto

from api.services.connectors.manifest import ConnectorCategory, AuthStrategyType, CapabilityDefinition, ConnectorManifest
from api.services.connectors.registry import ConnectorRegistry, ConnectorNotRegisteredError, InvalidManifestError
from api.services.connectors.base import PlatformConnector, ConnectorActionResult
from api.services.connectors import credential_store
from api.services.connectors.bootstrap import get_all_manifests, register_all_connectors
from api.services.connectors.service import connector_service
from api.services.connectors.sync_engine import SyncScheduler
from api.services.connectors.health_monitor import HealthMonitor

from api.services.connectors.auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy, OAuth2Config, OAuth2PkceError
from api.services.connectors.auth_strategies.api_key import ApiKeyAuthStrategy, ApiKeyConfig
from api.services.connectors.auth_strategies.basic_auth import BasicAuthStrategy
from api.services.connectors.auth_strategies.ssh_key import SshKeyAuthStrategy
from api.services.connectors.auth_strategies.no_auth import NoAuthStrategy
from api.services.connectors.auth_strategies.custom_header import CustomHeaderAuthStrategy

from api.services.connectors.providers.canva.connector import canva_connector, _canva_oauth_config
from api.services.connectors.providers.canva import client as canva_client
from api.services.connectors.providers.local_folder.connector import local_folder_connector

USER_A = {"id": "conn-test-user-a", "username": "a@example.com", "name": "User A"}
USER_B = {"id": "conn-test-user-b", "username": "b@example.com", "name": "User B"}


def _ensure_user(u: dict) -> None:
    s = SessionLocal()
    try:
        if not s.get(User, u["id"]):
            s.add(User(id=u["id"], username=u["username"], name=u["name"]))
            s.commit()
    finally:
        s.close()


@pytest.fixture
def client():
    _ensure_user(USER_A)
    _ensure_user(USER_B)
    app.dependency_overrides[require_auth] = lambda: USER_A
    yield TestClient(app)
    app.dependency_overrides.pop(require_auth, None)


@pytest.fixture
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _canva_row(db):
    return crud.get_connector_by_provider(db, "canva")


def _local_folder_row(db):
    return crud.get_connector_by_provider(db, "local_folder")


def _cleanup_account(db, user_id, connector_id):
    crud.delete_user_connector_account(db, user_id, connector_id)


# ──────────────────────────────────────────────────────────
# Manifests / bootstrap
# ──────────────────────────────────────────────────────────

def test_all_17_manifests_load_with_unique_providers():
    manifests = get_all_manifests()
    assert len(manifests) == 17
    providers = [m.provider for m in manifests]
    assert len(providers) == len(set(providers))


def test_every_manifest_has_unique_capability_actions():
    for manifest in get_all_manifests():
        actions = [c.action for c in manifest.capabilities]
        assert len(actions) == len(set(actions)), f"duplicate actions in {manifest.provider}"


# ──────────────────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────────────────

def test_registry_rejects_unregistered_provider():
    registry = ConnectorRegistry()
    with pytest.raises(ConnectorNotRegisteredError):
        registry.get("not_a_real_provider")


def test_registry_resolves_registered_provider():
    registry = ConnectorRegistry()
    register_all_connectors(registry)
    assert registry.get("canva") is canva_connector
    assert registry.get("local_folder") is local_folder_connector
    assert registry.is_registered("canva")


def test_registry_rejects_duplicate_capability_actions():
    class BadConnector(PlatformConnector):
        manifest = ConnectorManifest(
            provider="bad", display_name="Bad", category=ConnectorCategory.CUSTOM,
            auth_strategy_type=AuthStrategyType.NO_AUTH,
            capabilities=(
                CapabilityDefinition("bad.action", "one"),
                CapabilityDefinition("bad.action", "duplicate"),
            ),
        )

        def __init__(self):
            self.auth_strategy = NoAuthStrategy()

        async def execute_action(self, db, user_id, action, parameters):
            return ConnectorActionResult(success=False, action=action)

    registry = ConnectorRegistry()
    with pytest.raises(InvalidManifestError):
        registry.register(BadConnector())


def test_registry_rejects_auth_strategy_type_mismatch():
    class MismatchedConnector(PlatformConnector):
        manifest = ConnectorManifest(
            provider="mismatched", display_name="Mismatched", category=ConnectorCategory.CUSTOM,
            auth_strategy_type=AuthStrategyType.API_KEY,  # manifest says API_KEY...
        )

        def __init__(self):
            self.auth_strategy = NoAuthStrategy()  # ...but this composes NoAuth

        async def execute_action(self, db, user_id, action, parameters):
            return ConnectorActionResult(success=False, action=action)

    registry = ConnectorRegistry()
    with pytest.raises(InvalidManifestError):
        registry.register(MismatchedConnector())


# ──────────────────────────────────────────────────────────
# Encryption / credential store
# ──────────────────────────────────────────────────────────

def test_token_encryption_round_trip():
    plaintext = "super-secret-access-token"
    ciphertext = crypto.encrypt_secret(plaintext)
    assert ciphertext != plaintext
    assert crypto.decrypt_secret(ciphertext) == plaintext


def test_credential_store_round_trip(db):
    row = _canva_row(db)
    credential_store.save_credentials(db, USER_A["id"], row.id, {"access_token": "abc", "refresh_token": "xyz"})
    loaded = credential_store.load_credentials(db, USER_A["id"], row.id)
    assert loaded == {"access_token": "abc", "refresh_token": "xyz"}
    _cleanup_account(db, USER_A["id"], row.id)


def test_credential_store_returns_none_when_disconnected(db):
    row = _canva_row(db)
    assert credential_store.load_credentials(db, USER_B["id"], row.id) is None


# ──────────────────────────────────────────────────────────
# Cross-user isolation
# ──────────────────────────────────────────────────────────

def test_user_cannot_read_another_users_credentials(db):
    row = _canva_row(db)
    credential_store.save_credentials(db, USER_A["id"], row.id, {"access_token": "token-for-a"})
    assert credential_store.load_credentials(db, USER_B["id"], row.id) is None
    assert credential_store.load_credentials(db, USER_A["id"], row.id) == {"access_token": "token-for-a"}
    _cleanup_account(db, USER_A["id"], row.id)


# ──────────────────────────────────────────────────────────
# OAuth2PkceAuthStrategy
# ──────────────────────────────────────────────────────────

def _fake_oauth2_config() -> OAuth2Config:
    return OAuth2Config(
        authorize_url="https://example.test/authorize",
        token_url="https://example.test/token",
        revoke_url="https://example.test/revoke",
        scopes="scope:one scope:two",
        redirect_uri="http://127.0.0.1:8000/api/connectors/fake/callback",
        client_id="fake-client-id",
        client_secret="fake-client-secret",
        code_challenge_method="S256",
    )


@pytest.mark.asyncio
async def test_oauth2_initiate_builds_correct_pkce_and_url(db):
    strategy = OAuth2PkceAuthStrategy(_fake_oauth2_config)
    result = await strategy.initiate(db, USER_A["id"], _canva_row(db))
    assert result.success
    assert result.mode == "redirect"
    assert result.authorize_url.startswith("https://example.test/authorize?")
    assert "client_id=fake-client-id" in result.authorize_url
    assert "code_challenge_method=S256" in result.authorize_url
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(result.pkce_verifier.encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert expected_challenge in result.authorize_url
    assert 43 <= len(result.pkce_verifier) <= 128


@pytest.mark.asyncio
async def test_oauth2_initiate_fails_when_not_configured(db):
    strategy = OAuth2PkceAuthStrategy(lambda: OAuth2Config(
        authorize_url="https://example.test/authorize", token_url="https://example.test/token",
        revoke_url=None, scopes="x", redirect_uri="http://x", client_id="", client_secret="",
    ))
    result = await strategy.initiate(db, USER_A["id"], _canva_row(db))
    assert not result.success
    assert result.error_code == "NOT_CONFIGURED"


@pytest.mark.asyncio
async def test_oauth2_complete_exchanges_code_and_stores_credentials(db, monkeypatch):
    async def fake_exchange(self, cfg, code_or_refresh, code_verifier, grant_type):
        assert grant_type == "authorization_code"
        return {"access_token": "new-access", "refresh_token": "new-refresh", "expires_in": 3600, "scope": "scope:one"}

    monkeypatch.setattr(OAuth2PkceAuthStrategy, "_exchange", fake_exchange)
    strategy = OAuth2PkceAuthStrategy(_fake_oauth2_config)
    row = _canva_row(db)
    result = await strategy.complete(db, USER_A["id"], row, {"code": "auth-code", "code_verifier": "verifier"})
    assert result.success
    assert result.granted_scopes == ["scope:one"]

    stored = credential_store.load_credentials(db, USER_A["id"], row.id)
    assert stored["access_token"] == "new-access"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_oauth2_refresh_updates_stored_tokens(db, monkeypatch):
    row = _canva_row(db)
    credential_store.save_credentials(db, USER_A["id"], row.id, {"access_token": "old", "refresh_token": "old-refresh"})

    async def fake_exchange(self, cfg, code_or_refresh, code_verifier, grant_type):
        assert grant_type == "refresh_token"
        assert code_or_refresh == "old-refresh"
        return {"access_token": "refreshed-access", "refresh_token": "refreshed-refresh", "expires_in": 3600}

    monkeypatch.setattr(OAuth2PkceAuthStrategy, "_exchange", fake_exchange)
    strategy = OAuth2PkceAuthStrategy(_fake_oauth2_config)
    result = await strategy.refresh(db, USER_A["id"], row)
    assert result.success
    stored = credential_store.load_credentials(db, USER_A["id"], row.id)
    assert stored["access_token"] == "refreshed-access"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_oauth2_refresh_fails_without_stored_refresh_token(db):
    row = _canva_row(db)
    strategy = OAuth2PkceAuthStrategy(_fake_oauth2_config)
    result = await strategy.refresh(db, USER_B["id"], row)
    assert not result.success
    assert result.error_code == "NOT_CONNECTED"


# ──────────────────────────────────────────────────────────
# ApiKeyAuthStrategy / BasicAuthStrategy / SshKeyAuthStrategy / CustomHeaderAuthStrategy
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_api_key_strategy_round_trip(db):
    row = _local_folder_row(db)  # any connector row works — strategy is generic
    strategy = ApiKeyAuthStrategy(ApiKeyConfig())
    initiation = await strategy.initiate(db, USER_A["id"], row)
    assert initiation.mode == "form"
    assert initiation.credential_fields[0]["name"] == "api_key"

    result = await strategy.complete(db, USER_A["id"], row, {"api_key": "sk-test-123"})
    assert result.success
    ctx = await strategy.build_auth_context(db, USER_A["id"], row)
    assert ctx.headers["Authorization"] == "Bearer sk-test-123"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_api_key_strategy_rejects_empty_key(db):
    row = _local_folder_row(db)
    strategy = ApiKeyAuthStrategy(ApiKeyConfig())
    result = await strategy.complete(db, USER_A["id"], row, {"api_key": "  "})
    assert not result.success
    assert result.error_code == "MISSING_API_KEY"


@pytest.mark.asyncio
async def test_basic_auth_strategy_round_trip(db):
    row = _local_folder_row(db)
    strategy = BasicAuthStrategy()
    result = await strategy.complete(db, USER_A["id"], row, {"username": "bob", "password": "hunter2", "host": "sftp.example.com"})
    assert result.success
    ctx = await strategy.build_auth_context(db, USER_A["id"], row)
    expected = base64.b64encode(b"bob:hunter2").decode("ascii")
    assert ctx.headers["Authorization"] == f"Basic {expected}"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_ssh_key_strategy_round_trip(db):
    row = _local_folder_row(db)
    strategy = SshKeyAuthStrategy()
    result = await strategy.complete(db, USER_A["id"], row, {
        "username": "svc", "host": "nas.local", "private_key": "-----BEGIN KEY-----\nabc\n-----END KEY-----",
    })
    assert result.success
    ctx = await strategy.build_auth_context(db, USER_A["id"], row)
    assert ctx.extra["host"] == "nas.local"
    assert "BEGIN KEY" in ctx.extra["private_key"]
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_custom_header_strategy_parses_headers(db):
    row = _local_folder_row(db)
    strategy = CustomHeaderAuthStrategy()
    result = await strategy.complete(db, USER_A["id"], row, {
        "base_url": "https://api.example.com", "headers": "X-Api-Key: secret123\nX-Org: acme",
    })
    assert result.success
    ctx = await strategy.build_auth_context(db, USER_A["id"], row)
    assert ctx.headers == {"X-Api-Key": "secret123", "X-Org": "acme"}
    assert ctx.extra["base_url"] == "https://api.example.com"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_custom_header_strategy_rejects_no_headers(db):
    row = _local_folder_row(db)
    strategy = CustomHeaderAuthStrategy()
    result = await strategy.complete(db, USER_A["id"], row, {"base_url": "https://api.example.com", "headers": ""})
    assert not result.success
    assert result.error_code == "MISSING_FIELDS"


# ──────────────────────────────────────────────────────────
# Canva connector — real endpoint shapes, mocked HTTP boundary
# ──────────────────────────────────────────────────────────

def test_canva_manifest_requests_only_scopes_it_implements():
    implemented_scopes = set()
    for cap in canva_connector.manifest.capabilities:
        if cap.is_implemented:
            implemented_scopes.update(cap.required_scopes)
    cfg = _canva_oauth_config()
    requested = set(cfg.scopes.split())
    assert implemented_scopes <= requested


@pytest.mark.asyncio
async def test_canva_execute_action_not_connected(db):
    result = await canva_connector.execute_action(db, USER_B["id"], "canva.list_designs", {})
    assert not result.success
    assert result.error_code == "NOT_CONNECTED"


@pytest.mark.asyncio
async def test_canva_execute_action_list_designs_success(db, monkeypatch):
    row = _canva_row(db)
    credential_store.save_credentials(
        db, USER_A["id"], row.id, {"access_token": "valid-token"},
        connection_status="connected", token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    async def fake_list_designs(access_token, query=None, limit=25, sort_by=None):
        assert access_token == "valid-token"
        return {"items": [{"id": "d1", "title": "Deck", "urls": {"edit_url": "https://canva.com/design/d1/edit"}}]}

    monkeypatch.setattr(canva_client, "list_designs", fake_list_designs)
    result = await canva_connector.execute_action(db, USER_A["id"], "canva.list_designs", {})
    assert result.success
    assert result.data["items"][0]["urls"]["edit_url"] == "https://canva.com/design/d1/edit"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_canva_unimplemented_action_gated_by_service_layer(db):
    row = _canva_row(db)
    credential_store.save_credentials(
        db, USER_A["id"], row.id, {"access_token": "valid-token"},
        connection_status="connected", granted_scopes=["profile:read", "design:meta:read"],
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    # canva.copy_design is still declared is_implemented=False — export_design/
    # create_design/import_design etc. moved to the implemented set below.
    result = await connector_service.execute_action(db, USER_A["id"], "canva", "canva.copy_design", {})
    assert not result.success
    assert result.error_code == "NOT_IMPLEMENTED"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_canva_export_design_insufficient_scope_for_old_grant(db):
    """A user who connected before design-content scopes were added gets an
    honest INSUFFICIENT_SCOPE, never a fabricated success — same pattern as
    google_drive's own documented write-scope gap."""
    row = _canva_row(db)
    credential_store.save_credentials(
        db, USER_A["id"], row.id, {"access_token": "valid-token"},
        connection_status="connected", granted_scopes=["profile:read", "design:meta:read"],
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    result = await connector_service.execute_action(
        db, USER_A["id"], "canva", "canva.export_design", {"design_id": "d1", "format": "png"},
    )
    assert not result.success
    assert result.error_code == "INSUFFICIENT_SCOPE"
    _cleanup_account(db, USER_A["id"], row.id)


_FULL_SCOPES = [
    "profile:read", "design:meta:read", "design:content:write", "asset:write",
    "design:content:read", "brandtemplate:meta:read", "brandtemplate:content:read",
]


@pytest.mark.asyncio
async def test_canva_create_design_uploads_asset_and_creates_design(db, monkeypatch):
    row = _canva_row(db)
    credential_store.save_credentials(
        db, USER_A["id"], row.id, {"access_token": "valid-token"},
        connection_status="connected", granted_scopes=_FULL_SCOPES,
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    async def fake_upload_asset(access_token, file_bytes, name):
        return {"id": "upload-job-1", "status": "in_progress"}

    async def fake_poll_asset_upload(access_token, job_id, timeout_s=20.0):
        assert job_id == "upload-job-1"
        return "asset-123"

    async def fake_create_design(access_token, *, width, height, asset_id, title=None):
        assert asset_id == "asset-123"
        return {"design": {"id": "design-1", "title": title, "thumbnail": {"url": "https://canva.example/thumb.png"},
                            "urls": {"edit_url": "https://canva.com/design/design-1/edit"}}}

    monkeypatch.setattr(canva_client, "upload_asset", fake_upload_asset)
    monkeypatch.setattr(canva_client, "poll_asset_upload", fake_poll_asset_upload)
    monkeypatch.setattr(canva_client, "create_design", fake_create_design)

    result = await connector_service.execute_action(
        db, USER_A["id"], "canva", "canva.create_design",
        {"width": 1080, "height": 1920, "content_bytes_hex": b"fake-png".hex(), "title": "My Poster"},
    )
    assert result.success
    assert result.data["design"]["id"] == "design-1"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_canva_export_design_polls_until_success(db, monkeypatch):
    row = _canva_row(db)
    credential_store.save_credentials(
        db, USER_A["id"], row.id, {"access_token": "valid-token"},
        connection_status="connected", granted_scopes=_FULL_SCOPES,
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    async def fake_create_export_job(access_token, design_id, export_format):
        assert design_id == "design-1" and export_format == "png"
        return {"id": "export-job-1", "status": "in_progress"}

    async def fake_poll_export_job(access_token, job_id, timeout_s=25.0):
        assert job_id == "export-job-1"
        return {"id": job_id, "status": "success", "urls": ["https://canva.example/export.png"]}

    monkeypatch.setattr(canva_client, "create_export_job", fake_create_export_job)
    monkeypatch.setattr(canva_client, "poll_export_job", fake_poll_export_job)

    result = await connector_service.execute_action(
        db, USER_A["id"], "canva", "canva.export_design", {"design_id": "design-1", "format": "png"},
    )
    assert result.success
    assert result.data["urls"] == ["https://canva.example/export.png"]
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_canva_get_user_capabilities(db, monkeypatch):
    row = _canva_row(db)
    credential_store.save_credentials(
        db, USER_A["id"], row.id, {"access_token": "valid-token"},
        connection_status="connected", granted_scopes=_FULL_SCOPES,
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    async def fake_get_user_capabilities(access_token):
        return {"capabilities": ["brand_template"]}

    monkeypatch.setattr(canva_client, "get_user_capabilities", fake_get_user_capabilities)
    result = await connector_service.execute_action(db, USER_A["id"], "canva", "canva.get_user_capabilities", {})
    assert result.success
    assert "autofill" not in result.data["capabilities"]
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_canva_disconnect_clears_account_even_if_revoke_fails(db, monkeypatch):
    row = _canva_row(db)
    credential_store.save_credentials(db, USER_A["id"], row.id, {"access_token": "a", "refresh_token": "r"})

    async def fake_revoke_method(self, db, user_id, connector_row):
        return False  # simulates a provider-side revoke failure

    monkeypatch.setattr(OAuth2PkceAuthStrategy, "revoke", fake_revoke_method)
    await canva_connector.disconnect(db, USER_A["id"])
    assert credential_store.load_credentials(db, USER_A["id"], row.id) is None


# ──────────────────────────────────────────────────────────
# Local Folder connector — real filesystem, no mocking
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_local_folder_connect_and_list_files(db, tmp_path):
    row = _local_folder_row(db)
    (tmp_path / "notes.txt").write_text("hello world", encoding="utf-8")
    (tmp_path / "subdir").mkdir()

    connect_result = await local_folder_connector.complete_connection(db, USER_A["id"], {"root_path": str(tmp_path)})
    assert connect_result.success

    result = await local_folder_connector.execute_action(db, USER_A["id"], "local_folder.list_files", {})
    assert result.success
    names = {e["name"] for e in result.data["entries"]}
    assert names == {"notes.txt", "subdir"}
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_local_folder_read_file(db, tmp_path):
    row = _local_folder_row(db)
    (tmp_path / "notes.txt").write_text("hello world", encoding="utf-8")
    await local_folder_connector.complete_connection(db, USER_A["id"], {"root_path": str(tmp_path)})

    result = await local_folder_connector.execute_action(db, USER_A["id"], "local_folder.read_file", {"relative_path": "notes.txt"})
    assert result.success
    assert result.data["content"] == "hello world"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_local_folder_rejects_path_traversal(db, tmp_path):
    row = _local_folder_row(db)
    (tmp_path / "notes.txt").write_text("hello", encoding="utf-8")
    await local_folder_connector.complete_connection(db, USER_A["id"], {"root_path": str(tmp_path)})

    result = await local_folder_connector.execute_action(
        db, USER_A["id"], "local_folder.read_file", {"relative_path": "../../etc/passwd"}
    )
    assert not result.success
    assert result.error_code == "UNSAFE_PATH"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_local_folder_health_check_detects_missing_root(db, tmp_path):
    row = _local_folder_row(db)
    missing_dir = tmp_path / "gone"
    await local_folder_connector.complete_connection(db, USER_A["id"], {"root_path": str(missing_dir)})

    status = await local_folder_connector.health_check(db, USER_A["id"])
    assert not status.healthy
    _cleanup_account(db, USER_A["id"], row.id)


# ──────────────────────────────────────────────────────────
# Connector Service — scope checks, rate limiting, event logging
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_service_rejects_insufficient_scope(db):
    row = _canva_row(db)
    credential_store.save_credentials(
        db, USER_A["id"], row.id, {"access_token": "a"},
        connection_status="connected", granted_scopes=[],  # no scopes granted at all
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    result = await connector_service.execute_action(db, USER_A["id"], "canva", "canva.list_designs", {})
    assert not result.success
    assert result.error_code == "INSUFFICIENT_SCOPE"
    _cleanup_account(db, USER_A["id"], row.id)


@pytest.mark.asyncio
async def test_service_logs_action_event(db, monkeypatch):
    row = _canva_row(db)
    credential_store.save_credentials(
        db, USER_A["id"], row.id, {"access_token": "a"},
        connection_status="connected", granted_scopes=["profile:read"],
        token_expiry=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    async def fake_get_profile(access_token):
        return {"profile": {"display_name": "Test User"}}

    monkeypatch.setattr(canva_client, "get_profile", fake_get_profile)
    before = len(crud.list_connector_events(db, user_id=USER_A["id"], connector_id=row.id))
    result = await connector_service.execute_action(db, USER_A["id"], "canva", "canva.get_profile", {})
    assert result.success
    after = crud.list_connector_events(db, user_id=USER_A["id"], connector_id=row.id)
    assert len(after) == before + 1
    assert after[0].status == "success"
    _cleanup_account(db, USER_A["id"], row.id)


# ──────────────────────────────────────────────────────────
# Sync / health schedulers
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sync_scheduler_tick_runs_cleanly_with_nothing_due():
    scheduler = SyncScheduler()
    processed = await scheduler.tick()
    assert processed == 0


@pytest.mark.asyncio
async def test_health_monitor_tick_flags_error_after_repeated_failures(db, monkeypatch):
    row = _local_folder_row(db)
    missing_dir = "/definitely/does/not/exist/xyz"
    await local_folder_connector.complete_connection(db, USER_A["id"], {"root_path": missing_dir})

    monitor = HealthMonitor()
    for _ in range(3):
        await monitor.tick()

    account = crud.get_user_connector_account(db, USER_A["id"], row.id)
    assert account.connection_status == "error"
    _cleanup_account(db, USER_A["id"], row.id)


# ──────────────────────────────────────────────────────────
# Restart persistence
# ──────────────────────────────────────────────────────────

def test_connection_persists_across_new_db_sessions():
    connector_row = crud.get_connector_by_provider(SessionLocal(), "canva")
    s1 = SessionLocal()
    try:
        credential_store.save_credentials(s1, USER_A["id"], connector_row.id, {"access_token": "persisted-token"})
    finally:
        s1.close()

    s2 = SessionLocal()
    try:
        loaded = credential_store.load_credentials(s2, USER_A["id"], connector_row.id)
        assert loaded == {"access_token": "persisted-token"}
        crud.delete_user_connector_account(s2, USER_A["id"], connector_row.id)
    finally:
        s2.close()
