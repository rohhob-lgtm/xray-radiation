"""
GoogleDriveConnector — real Google Drive API v3 over OAuth2PkceAuthStrategy.

Phase 2: `_READ_SCOPES` (kept its Phase 1 name for git-blame continuity) now
requests userinfo + drive.readonly + drive.file, so write actions
(upload_file/create_folder/save_generated_file — used by the AI Tool
Router's "Save to Google Drive" chat action) work for newly-connected users.
Users who connected during Phase 1 still get an honest INSUFFICIENT_SCOPE
from ConnectorService's own scope check until they disconnect/reconnect
once — there is no scope-upgrade flow in this framework.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from ...base import PlatformConnector, ConnectorActionResult, HealthStatus
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy
from ...credential_store import save_credentials, load_credentials
from .._shared.google_oauth import google_oauth_config
from . import client as drive_client

_PROFILE_SCOPES = "openid email profile"
_DRIVE_READ_SCOPE = "https://www.googleapis.com/auth/drive.readonly"
_DRIVE_WRITE_SCOPE = "https://www.googleapis.com/auth/drive.file"
# Phase 2: the AI Tool Router's "Save to Google Drive" chat action needs
# upload_file/save_generated_file to actually work, so write scope is now
# requested up front. Users who connected during Phase 1 (read-only) keep
# getting an honest INSUFFICIENT_SCOPE from ConnectorService's own scope
# check until they disconnect/reconnect once — there is no scope-upgrade
# flow, same as every other scope-widening change in this framework.
_READ_SCOPES = f"{_PROFILE_SCOPES} {_DRIVE_READ_SCOPE} {_DRIVE_WRITE_SCOPE}"

_NATIVE_FIELD = {"type": "string", "required": True,
                  "description": "One of: google_doc, google_slide, google_sheet"}

GOOGLE_DRIVE_MANIFEST = ConnectorManifest(
    provider="google_drive", display_name="Google Drive", icon="🗂️",
    category=ConnectorCategory.FILE_STORAGE, auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    supports_sync=False, supports_health_check=True,
    capabilities=(
        CapabilityDefinition("google_drive.get_profile", "Get the connected Google account's name/email",
                              required_scopes=(_PROFILE_SCOPES,)),
        CapabilityDefinition(
            "google_drive.list_files", "List the user's Drive files (most recently modified first)",
            required_scopes=(_DRIVE_READ_SCOPE,),
            parameters_schema={"limit": {"type": "integer", "required": False,
                                          "description": "Max files to return, default 25"}},
        ),
        CapabilityDefinition(
            "google_drive.search_files", "Search Drive files by name",
            required_scopes=(_DRIVE_READ_SCOPE,),
            parameters_schema={"query": {"type": "string", "required": True},
                                "limit": {"type": "integer", "required": False}},
        ),
        CapabilityDefinition(
            "google_drive.get_file_metadata", "Get one file's metadata (name, type, size, modified, link)",
            required_scopes=(_DRIVE_READ_SCOPE,),
            parameters_schema={"file_id": {"type": "string", "required": True}},
        ),
        CapabilityDefinition(
            "google_drive.list_folder", "List the files directly inside one Drive folder",
            required_scopes=(_DRIVE_READ_SCOPE,),
            parameters_schema={"folder_id": {"type": "string", "required": True},
                                "limit": {"type": "integer", "required": False}},
        ),
        CapabilityDefinition(
            "google_drive.open_file", "Return a file's real Google Drive web view link",
            required_scopes=(_DRIVE_READ_SCOPE,),
            parameters_schema={"file_id": {"type": "string", "required": True}},
        ),
        CapabilityDefinition(
            "google_drive.download_file", "Download a regular (non-Google-native) file's raw content",
            required_scopes=(_DRIVE_READ_SCOPE,),
            parameters_schema={"file_id": {"type": "string", "required": True}},
        ),
        CapabilityDefinition(
            "google_drive.export_google_doc", "Export a Google Doc to .docx",
            required_scopes=(_DRIVE_READ_SCOPE,),
            parameters_schema={"file_id": {"type": "string", "required": True}},
        ),
        CapabilityDefinition(
            "google_drive.export_google_slide", "Export a Google Slides presentation to .pptx",
            required_scopes=(_DRIVE_READ_SCOPE,),
            parameters_schema={"file_id": {"type": "string", "required": True}},
        ),
        CapabilityDefinition(
            "google_drive.export_google_sheet", "Export a Google Sheet to .xlsx",
            required_scopes=(_DRIVE_READ_SCOPE,),
            parameters_schema={"file_id": {"type": "string", "required": True}},
        ),
        # Write actions — real code, gated by a scope not requested during
        # Phase 1 OAuth, so these honestly report INSUFFICIENT_SCOPE (never a
        # fabricated success) until the user reconnects with write access.
        CapabilityDefinition(
            "google_drive.upload_file", "Upload a file to the user's Drive",
            required_scopes=(_DRIVE_WRITE_SCOPE,), is_destructive=True,
            parameters_schema={"filename": {"type": "string", "required": True},
                                "folder_id": {"type": "string", "required": False}},
        ),
        CapabilityDefinition(
            "google_drive.create_folder", "Create a folder in the user's Drive",
            required_scopes=(_DRIVE_WRITE_SCOPE,), is_destructive=True,
            parameters_schema={"name": {"type": "string", "required": True},
                                "parent_id": {"type": "string", "required": False}},
        ),
        CapabilityDefinition(
            "google_drive.save_generated_file", "Save a platform-generated file to the user's Drive",
            required_scopes=(_DRIVE_WRITE_SCOPE,), is_destructive=True,
            parameters_schema={"filename": {"type": "string", "required": True},
                                "folder_id": {"type": "string", "required": False}},
        ),
    ),
)


class GoogleDriveConnector(PlatformConnector):
    manifest = GOOGLE_DRIVE_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(lambda: google_oauth_config("google_drive", _READ_SCOPES))

    async def on_connected(self, db: Session, user_id: str) -> None:
        connector_row = self._connector_row(db)
        stored = load_credentials(db, user_id, connector_row.id)
        access_token = (stored or {}).get("access_token")
        if not access_token:
            return
        try:
            profile = await drive_client.get_profile(access_token)
            email = profile.get("email")
            if email:
                from api.db import crud
                crud.upsert_user_connector_account(
                    db, user_id=user_id, connector_id=connector_row.id, external_account_email=email,
                )
        except drive_client.GoogleApiError:
            pass  # non-fatal — account label just stays unset

    async def execute_action(self, db: Session, user_id: str, action: str, parameters: dict[str, Any]) -> ConnectorActionResult:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")

        try:
            if action == "google_drive.get_profile":
                data = await drive_client.get_profile(access_token)

            elif action == "google_drive.list_files":
                data = await drive_client.list_files(
                    access_token, page_size=parameters.get("limit", 25), order_by="modifiedTime desc",
                )

            elif action == "google_drive.search_files":
                query = parameters.get("query")
                if not query:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="query is required")
                data = await drive_client.list_files(access_token, query=query, page_size=parameters.get("limit", 25))

            elif action == "google_drive.get_file_metadata":
                file_id = parameters.get("file_id")
                if not file_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await drive_client.get_file_metadata(access_token, file_id)

            elif action == "google_drive.list_folder":
                folder_id = parameters.get("folder_id")
                if not folder_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="folder_id is required")
                data = await drive_client.list_files(access_token, folder_id=folder_id, page_size=parameters.get("limit", 25))

            elif action == "google_drive.open_file":
                file_id = parameters.get("file_id")
                if not file_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                data = await drive_client.get_file_metadata(access_token, file_id)

            elif action == "google_drive.download_file":
                file_id = parameters.get("file_id")
                if not file_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                content = await drive_client.download_file(access_token, file_id)
                data = {"file_id": file_id, "size_bytes": len(content)}

            elif action in ("google_drive.export_google_doc", "google_drive.export_google_slide", "google_drive.export_google_sheet"):
                file_id = parameters.get("file_id")
                if not file_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER")
                native_type = action.rsplit("_", 1)[-1]  # doc | slide | sheet
                mime_type = drive_client.EXPORT_MIME_TYPES[f"google_{native_type}"]
                content = await drive_client.export_file(access_token, file_id, mime_type)
                data = {"file_id": file_id, "mime_type": mime_type, "size_bytes": len(content)}

            elif action in ("google_drive.upload_file", "google_drive.save_generated_file"):
                filename = parameters.get("filename")
                if not filename:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="filename is required")
                # Content bytes must be supplied by the caller (e.g. a Training
                # Generator export) via parameters["content_bytes_hex"] — the
                # chat tool router never has raw file bytes to hand.
                content_hex = parameters.get("content_bytes_hex")
                if not content_hex:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="content_bytes_hex is required")
                content = bytes.fromhex(content_hex)
                data = await drive_client.upload_file(
                    access_token, filename, content,
                    mime_type=parameters.get("mime_type", "application/octet-stream"),
                    parent_id=parameters.get("folder_id"),
                )

            elif action == "google_drive.create_folder":
                name = parameters.get("name")
                if not name:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="name is required")
                data = await drive_client.create_folder(access_token, name, parent_id=parameters.get("parent_id"))

            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except drive_client.GoogleApiError as exc:
            return ConnectorActionResult(success=False, action=action,
                                          error_code=f"GOOGLE_API_ERROR_{exc.status_code}", error_message=str(exc))

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str) -> HealthStatus:
        access_token = await self._get_bearer_token(db, user_id)
        if not access_token:
            return HealthStatus(healthy=False, detail="Not connected")
        try:
            await drive_client.about_user(access_token)
            return HealthStatus(healthy=True)
        except drive_client.GoogleApiError as exc:
            return HealthStatus(healthy=False, detail=str(exc))


google_drive_connector = GoogleDriveConnector()
