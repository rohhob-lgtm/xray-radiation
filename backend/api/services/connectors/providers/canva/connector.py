"""
CanvaConnector — the first real implementation on top of the Enterprise
Connector Framework. All OAuth mechanics come from OAuth2PkceAuthStrategy;
this class only declares Canva's manifest and implements execute_action.
"""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from api.config import settings
from api.db import crud

from ...base import PlatformConnector, ConnectorActionResult
from ...manifest import ConnectorManifest, ConnectorCategory, AuthStrategyType, CapabilityDefinition
from ...auth_strategies.oauth2_pkce import OAuth2PkceAuthStrategy, OAuth2Config
from ...credential_store import load_credentials, save_credentials
from . import client as canva_client

log = logging.getLogger(__name__)


CANVA_MANIFEST = ConnectorManifest(
    provider="canva",
    display_name="Canva",
    category=ConnectorCategory.DESIGN,
    auth_strategy_type=AuthStrategyType.OAUTH2_PKCE,
    icon="🎨",
    supports_sync=False,
    supports_health_check=True,
    capabilities=(
        CapabilityDefinition("canva.get_profile", "Get the connected Canva account's display name",
                              required_scopes=("profile:read",)),
        CapabilityDefinition(
            "canva.list_designs",
            "List/search the user's Canva designs. Use 'query' to search by keyword "
            "(e.g. 'infographic'). Use sort_by='modified_descending' with limit=1 to "
            "find the single most recently modified design (e.g. for 'my latest design').",
            required_scopes=("design:meta:read",),
            parameters_schema={
                "query": {"type": "string", "required": False,
                          "description": "Keyword to search design titles for"},
                "sort_by": {"type": "string", "required": False,
                            "description": "One of: relevance, modified_descending, modified_ascending, "
                                            "title_descending, title_ascending. Default relevance.",
                            "enum": ["relevance", "modified_descending", "modified_ascending",
                                     "title_descending", "title_ascending"]},
                "limit": {"type": "integer", "required": False,
                          "description": "Max designs to return, 1-100. Default 25."},
            },
        ),
        CapabilityDefinition("canva.get_design", "Get one design's metadata and edit/view URLs",
                              required_scopes=("design:meta:read",),
                              parameters_schema={"design_id": {"type": "string", "required": True}}),
        CapabilityDefinition("canva.open_design", "Return a design's real Canva edit URL",
                              required_scopes=("design:meta:read",),
                              parameters_schema={"design_id": {"type": "string", "required": True}}),
        CapabilityDefinition("canva.get_user_capabilities",
                              "Get the connected Canva account's plan-gated capabilities "
                              "(e.g. whether 'autofill' or 'brand_template' is available — "
                              "both require a paid Canva plan). Check this before attempting autofill.",
                              required_scopes=("profile:read",)),
        CapabilityDefinition("canva.list_brand_templates",
                              "List the user's Canva brand templates. Pass dataset='non_empty' to "
                              "find only templates that actually have autofillable fields.",
                              required_scopes=("brandtemplate:meta:read",),
                              parameters_schema={
                                  "query": {"type": "string", "required": False},
                                  "dataset": {"type": "string", "required": False, "enum": ["any", "non_empty"]},
                                  "limit": {"type": "integer", "required": False},
                              }),
        CapabilityDefinition("canva.get_brand_template_dataset",
                              "Get a brand template's autofillable field names and types (text/image/chart)",
                              required_scopes=("brandtemplate:content:read",),
                              parameters_schema={"brand_template_id": {"type": "string", "required": True}}),
        CapabilityDefinition("canva.get_design_dataset",
                              "Get an existing design's autofillable field names and types, if any",
                              required_scopes=("design:content:read",),
                              parameters_schema={"design_id": {"type": "string", "required": True}}),
        CapabilityDefinition("canva.create_design_autofill_job",
                              "Create a new design by autofilling a brand template's (or design's) "
                              "text/image/chart fields with real data. Field names/types must come from "
                              "get_brand_template_dataset/get_design_dataset — never guessed.",
                              required_scopes=("brandtemplate:content:read", "design:content:write"),
                              is_destructive=True,
                              parameters_schema={
                                  "brand_template_id": {"type": "string", "required": False},
                                  "design_id": {"type": "string", "required": False},
                                  "title": {"type": "string", "required": False},
                                  "data": {"type": "object", "required": True,
                                           "description": "field_name -> {type, text|asset_id|chart_data}"},
                              }),
        CapabilityDefinition("canva.get_autofill_job_status", "Poll an autofill job's status",
                              required_scopes=("brandtemplate:content:read", "design:content:write"),
                              parameters_schema={"job_id": {"type": "string", "required": True}}),
        CapabilityDefinition("canva.create_design",
                              "Create a new custom-size Canva design, optionally seeded with an "
                              "uploaded image asset as its initial content",
                              required_scopes=("design:content:write",), is_destructive=True,
                              parameters_schema={
                                  "width": {"type": "integer", "required": True},
                                  "height": {"type": "integer", "required": True},
                                  "asset_id": {"type": "string", "required": False},
                                  "content_bytes_hex": {"type": "string", "required": False,
                                                         "description": "Hex-encoded image bytes to upload and use as asset_id"},
                                  "title": {"type": "string", "required": False},
                              }),
        CapabilityDefinition("canva.import_design",
                              "Import a design file (PDF/PPTX/DOCX/PNG/JPG) into Canva as a new design. "
                              "PPTX/PDF preserve real editable structure; PNG becomes a flat background.",
                              required_scopes=("design:content:write",), is_destructive=True,
                              parameters_schema={
                                  "content_bytes_hex": {"type": "string", "required": True},
                                  "title": {"type": "string", "required": True},
                                  "mime_type": {"type": "string", "required": False},
                              }),
        CapabilityDefinition("canva.get_import_job_status", "Poll a design-import job's status",
                              required_scopes=("design:content:write",),
                              parameters_schema={"job_id": {"type": "string", "required": True}}),
        CapabilityDefinition("canva.export_design", "Export a design to PNG or PDF",
                              required_scopes=("design:content:read",), is_destructive=True,
                              parameters_schema={
                                  "design_id": {"type": "string", "required": True},
                                  "format": {"type": "string", "required": True, "enum": ["png", "pdf"]},
                              }),
        CapabilityDefinition("canva.get_export_status", "Poll an export job's status",
                              required_scopes=("design:content:read",),
                              parameters_schema={"job_id": {"type": "string", "required": True}}),
        # Declared for the framework's full intended surface — not yet
        # implemented, so is_implemented=False keeps the Connector Service
        # from ever claiming these work.
        CapabilityDefinition("canva.copy_design", "Duplicate an existing design",
                              required_scopes=("design:content:write",), is_implemented=False),
        CapabilityDefinition("canva.list_folders", "List the user's Canva folders",
                              required_scopes=("folder:read",), is_implemented=False),
        CapabilityDefinition("canva.list_folder_items", "List items within a folder",
                              required_scopes=("folder:read",), is_implemented=False),
    ),
)

# Scopes actually requested during OAuth. Widened beyond plain read access so the
# Design Orchestrator's two real modes (Autofill / Internal-Render-and-Import) work:
# design:content:write + asset:write + design:content:read for create/import/export,
# brandtemplate:meta:read + brandtemplate:content:read for Mode 1 template discovery.
# Already-connected users must disconnect/reconnect once to pick these up — there is
# no scope-upgrade flow, only ConnectorService's honest INSUFFICIENT_SCOPE in the
# meantime (same known gap google_drive/connector.py documents for its own write scope).
_REQUESTED_SCOPES = (
    "profile:read design:meta:read design:content:write asset:write design:content:read "
    "brandtemplate:meta:read brandtemplate:content:read"
)


def _canva_oauth_config() -> OAuth2Config:
    return OAuth2Config(
        authorize_url="https://www.canva.com/api/oauth/authorize",
        token_url="https://api.canva.com/rest/v1/oauth/token",
        revoke_url="https://api.canva.com/rest/v1/oauth/revoke",
        scopes=_REQUESTED_SCOPES,
        redirect_uri=settings.canva_redirect_uri_resolved,
        client_id=settings.canva_client_id,
        client_secret=settings.canva_client_secret,
        code_challenge_method="s256",  # Canva specifically requires lowercase, unlike most OAuth2 providers
    )


def _autofill_job_payload(job: dict) -> dict:
    """Normalizes a polled /autofills/{id} job into {status, job_id, design}.
    Canva nests the result design differently across doc revisions
    (job.result.design vs job.design) — handled defensively rather than
    assuming one and crashing on the other."""
    result = job.get("result") or {}
    design = result.get("design") or job.get("design") or {}
    return {"status": job.get("status"), "job_id": job.get("id"), "design": design}


def _import_job_payload(job: dict) -> dict:
    """Normalizes a polled /imports/{id} job into {status, job_id, design}
    (the import API always returns exactly one design per job)."""
    result = job.get("result") or {}
    designs = result.get("designs") or job.get("designs") or []
    design = designs[0] if designs else {}
    return {"status": job.get("status"), "job_id": job.get("id"), "design": design}


def _export_job_payload(job: dict) -> dict:
    return {"status": job.get("status"), "job_id": job.get("id"), "urls": job.get("urls") or []}


class CanvaConnector(PlatformConnector):
    manifest = CANVA_MANIFEST

    def __init__(self):
        self.auth_strategy = OAuth2PkceAuthStrategy(_canva_oauth_config)

    async def on_connected(self, db: Session, user_id: str) -> None:
        """Best-effort profile fetch for a human-readable account label —
        Canva's profile endpoint has no email field, only display_name."""
        connector_row = self._connector_row(db)
        stored = load_credentials(db, user_id, connector_row.id)
        access_token = (stored or {}).get("access_token")
        if not access_token:
            return
        try:
            profile = await canva_client.get_profile(access_token)
            display_name = (profile.get("profile") or {}).get("display_name")
            if display_name:
                crud.upsert_user_connector_account(
                    db, user_id=user_id, connector_id=connector_row.id,
                    external_account_email=display_name,
                )
        except canva_client.CanvaApiError as exc:
            log.warning("Canva get_profile failed post-connect for user=%s: %s", user_id, exc)

    async def execute_action(
        self, db: Session, user_id: str, action: str, parameters: dict[str, Any]
    ) -> ConnectorActionResult:
        connector_row = self._connector_row(db)
        auth_context = await self.auth_strategy.build_auth_context(db, user_id, connector_row)
        if not auth_context or "Authorization" not in auth_context.headers:
            return ConnectorActionResult(success=False, action=action, error_code="NOT_CONNECTED")
        access_token = auth_context.headers["Authorization"].removeprefix("Bearer ")

        try:
            if action == "canva.get_profile":
                data = await canva_client.get_profile(access_token)
            elif action == "canva.list_designs":
                data = await canva_client.list_designs(
                    access_token, query=parameters.get("query"), limit=parameters.get("limit", 25),
                    sort_by=parameters.get("sort_by"),
                )
            elif action in ("canva.get_design", "canva.open_design"):
                design_id = parameters.get("design_id")
                if not design_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="design_id is required")
                data = await canva_client.get_design(access_token, design_id)

            elif action == "canva.get_user_capabilities":
                data = await canva_client.get_user_capabilities(access_token)

            elif action == "canva.list_brand_templates":
                data = await canva_client.list_brand_templates(
                    access_token, query=parameters.get("query"), limit=parameters.get("limit", 25),
                    dataset=parameters.get("dataset"),
                )

            elif action == "canva.get_brand_template_dataset":
                brand_template_id = parameters.get("brand_template_id")
                if not brand_template_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="brand_template_id is required")
                data = await canva_client.get_brand_template_dataset(access_token, brand_template_id)

            elif action == "canva.get_design_dataset":
                design_id = parameters.get("design_id")
                if not design_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="design_id is required")
                data = await canva_client.get_design_dataset(access_token, design_id)

            elif action == "canva.create_design_autofill_job":
                autofill_data = parameters.get("data")
                brand_template_id = parameters.get("brand_template_id")
                design_id = parameters.get("design_id")
                if not autofill_data or not (brand_template_id or design_id):
                    return ConnectorActionResult(
                        success=False, action=action, error_code="MISSING_PARAMETER",
                        error_message="data and one of brand_template_id/design_id are required",
                    )
                job = await canva_client.create_autofill_job(
                    access_token, autofill_data, brand_template_id=brand_template_id,
                    design_id=design_id, title=parameters.get("title"),
                )
                job = await canva_client.poll_autofill_job(access_token, job["id"], timeout_s=25.0)
                data = _autofill_job_payload(job)

            elif action == "canva.get_autofill_job_status":
                job_id = parameters.get("job_id")
                if not job_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="job_id is required")
                job = await canva_client.poll_autofill_job(access_token, job_id, timeout_s=0.0)
                data = _autofill_job_payload(job)

            elif action == "canva.create_design":
                width, height = parameters.get("width"), parameters.get("height")
                if not width or not height:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="width and height are required")
                asset_id = parameters.get("asset_id")
                content_hex = parameters.get("content_bytes_hex")
                if not asset_id and content_hex:
                    upload_job = await canva_client.upload_asset(
                        access_token, bytes.fromhex(content_hex), parameters.get("title") or "design-asset",
                    )
                    asset_id = await canva_client.poll_asset_upload(access_token, upload_job["id"], timeout_s=20.0)
                    if not asset_id:
                        return ConnectorActionResult(success=False, action=action, error_code="ASSET_UPLOAD_TIMEOUT",
                                                      error_message="Asset upload did not complete in time")
                data = await canva_client.create_design(
                    access_token, width=int(width), height=int(height), asset_id=asset_id,
                    title=parameters.get("title"),
                )

            elif action == "canva.import_design":
                content_hex = parameters.get("content_bytes_hex")
                title = parameters.get("title")
                if not content_hex or not title:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="content_bytes_hex and title are required")
                job = await canva_client.import_design(
                    access_token, bytes.fromhex(content_hex), title, mime_type=parameters.get("mime_type"),
                )
                job = await canva_client.poll_import_job(access_token, job["id"], timeout_s=30.0)
                data = _import_job_payload(job)

            elif action == "canva.get_import_job_status":
                job_id = parameters.get("job_id")
                if not job_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="job_id is required")
                job = await canva_client.poll_import_job(access_token, job_id, timeout_s=0.0)
                data = _import_job_payload(job)

            elif action == "canva.export_design":
                design_id, export_format = parameters.get("design_id"), parameters.get("format")
                if not design_id or export_format not in ("png", "pdf"):
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="design_id and format ('png'|'pdf') are required")
                job = await canva_client.create_export_job(access_token, design_id, export_format)
                job = await canva_client.poll_export_job(access_token, job["id"], timeout_s=25.0)
                data = _export_job_payload(job)

            elif action == "canva.get_export_status":
                job_id = parameters.get("job_id")
                if not job_id:
                    return ConnectorActionResult(success=False, action=action, error_code="MISSING_PARAMETER",
                                                  error_message="job_id is required")
                job = await canva_client.poll_export_job(access_token, job_id, timeout_s=0.0)
                data = _export_job_payload(job)

            else:
                return ConnectorActionResult(success=False, action=action, error_code="NOT_IMPLEMENTED")
        except canva_client.CanvaApiError as exc:
            return ConnectorActionResult(
                success=False, action=action, error_code=f"CANVA_API_ERROR_{exc.status_code}", error_message=str(exc),
            )

        await self._mark_action_success(db, user_id)
        return ConnectorActionResult(success=True, action=action, data=data)

    async def health_check(self, db: Session, user_id: str):
        from ...base import HealthStatus
        result = await self.execute_action(db, user_id, "canva.get_profile", {})
        return HealthStatus(healthy=result.success, detail=result.error_message)


canva_connector = CanvaConnector()
