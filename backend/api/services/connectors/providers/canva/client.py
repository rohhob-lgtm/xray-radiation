"""
Thin wrappers around the real Canva Connect REST API (api.canva.com/rest/v1).

Every function here makes an actual HTTP call — nothing in this module
fabricates or mocks a Canva response. Callers get back the raw parsed JSON
(or raise CanvaApiError) so the connector layer decides what to persist/log.
"""
from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://api.canva.com/rest/v1"


class CanvaApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _auth_headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _log_response(action: str, resp: httpx.Response) -> None:
    """Diagnostics for real Canva API calls — status/headers/body only, never the bearer token."""
    safe_headers = {k: v for k, v in resp.headers.items() if k.lower() != "authorization"}
    log.info(
        "[canva_api] action=%s status=%s headers=%s body=%s",
        action, resp.status_code, safe_headers, resp.text[:1000],
    )


async def get_profile(access_token: str) -> dict[str, Any]:
    """GET /users/me/profile — scope profile:read. Returns {"profile": {"display_name": str}}."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/users/me/profile", headers=_auth_headers(access_token))
    _log_response("get_profile", resp)
    if resp.status_code != 200:
        raise CanvaApiError(f"get_profile failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


_VALID_SORT_BY = {"relevance", "modified_descending", "modified_ascending", "title_descending", "title_ascending"}


async def list_designs(
    access_token: str, query: Optional[str] = None, limit: int = 25, sort_by: Optional[str] = None,
) -> dict[str, Any]:
    """GET /designs — scope design:meta:read. Returns {"items": [...], "continuation": str|None}."""
    params: dict[str, Any] = {"limit": min(max(limit, 1), 100)}
    if query:
        params["query"] = query[:255]
    if sort_by and sort_by in _VALID_SORT_BY:
        params["sort_by"] = sort_by
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/designs", headers=_auth_headers(access_token), params=params)
    _log_response("list_designs", resp)
    if resp.status_code != 200:
        raise CanvaApiError(f"list_designs failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def get_design(access_token: str, design_id: str) -> dict[str, Any]:
    """GET /designs/{id} — scope design:meta:read. Returns {"design": {..., "urls": {"edit_url": ...}}}."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/designs/{design_id}", headers=_auth_headers(access_token))
    _log_response("get_design", resp)
    if resp.status_code != 200:
        raise CanvaApiError(f"get_design failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def get_design_dataset(access_token: str, design_id: str) -> dict[str, Any]:
    """GET /designs/{id}/dataset — scope design:content:read. Same shape as
    get_brand_template_dataset but for an existing (non-brand-template) design
    that itself has autofillable fields — used for the 'autofill-enabled
    designs' half of Mode 1 discovery when a specific design_id is already
    in play (e.g. a follow-up "use this design as a template")."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/designs/{design_id}/dataset", headers=_auth_headers(access_token))
    _log_response("get_design_dataset", resp)
    if resp.status_code != 200:
        raise CanvaApiError(f"get_design_dataset failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def get_user_capabilities(access_token: str) -> dict[str, Any]:
    """GET /users/me/capabilities — scope profile:read. Returns {"capabilities": [str, ...]}.
    Notably: "autofill" requires Canva Enterprise; "brand_template" requires Pro/Teams/Enterprise —
    the Design Orchestrator must check this before ever attempting Mode 1 (Autofill)."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/users/me/capabilities", headers=_auth_headers(access_token))
    _log_response("get_user_capabilities", resp)
    if resp.status_code != 200:
        raise CanvaApiError(f"get_user_capabilities failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_brand_templates(
    access_token: str, query: Optional[str] = None, limit: int = 25,
    dataset: Optional[str] = None, sort_by: Optional[str] = None,
) -> dict[str, Any]:
    """GET /brand-templates — scope brandtemplate:meta:read. `dataset="non_empty"` filters
    to templates that actually have autofillable fields — the only ones Mode 1 can use.
    Returns {"items": [{"id", "title", "thumbnail": {"url"}, "view_url", ...}], "continuation": str|None}."""
    params: dict[str, Any] = {"limit": min(max(limit, 1), 100)}
    if query:
        params["query"] = query[:255]
    if dataset in ("any", "non_empty"):
        params["dataset"] = dataset
    if sort_by:
        params["sort_by"] = sort_by
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/brand-templates", headers=_auth_headers(access_token), params=params)
    _log_response("list_brand_templates", resp)
    if resp.status_code != 200:
        raise CanvaApiError(f"list_brand_templates failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def get_brand_template_dataset(access_token: str, brand_template_id: str) -> dict[str, Any]:
    """GET /brand-templates/{id}/dataset — scope brandtemplate:content:read.
    Returns {"dataset": {fieldName: {"type": "text"|"image"|"chart"}}}."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/brand-templates/{brand_template_id}/dataset", headers=_auth_headers(access_token))
    _log_response("get_brand_template_dataset", resp)
    if resp.status_code != 200:
        raise CanvaApiError(f"get_brand_template_dataset failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def _poll_job(access_token: str, url: str, action: str, timeout_s: float, interval_s: float = 1.5) -> dict[str, Any]:
    """Shared bounded poll loop for Canva's async job resources (asset-uploads,
    autofills, imports, exports all share the same {"job": {"status": ...}} shape)."""
    elapsed = 0.0
    async with httpx.AsyncClient(timeout=15.0) as client:
        while True:
            resp = await client.get(url, headers=_auth_headers(access_token))
            _log_response(action, resp)
            if resp.status_code != 200:
                raise CanvaApiError(f"{action} failed: {resp.text[:500]}", resp.status_code)
            job = resp.json().get("job", {})
            status = job.get("status")
            if status == "success":
                return job
            if status == "failed":
                error = job.get("error") or {}
                raise CanvaApiError(f"{action} job failed: {error.get('code')} {error.get('message', '')}".strip())
            if elapsed >= timeout_s:
                return job  # still in_progress — caller decides whether to report as pending
            await asyncio.sleep(interval_s)
            elapsed += interval_s


async def upload_asset(access_token: str, file_bytes: bytes, name: str) -> dict[str, Any]:
    """POST /asset-uploads — scope asset:write. Name is base64-encoded per Canva's
    Asset-Upload-Metadata header contract (max 50 unencoded characters)."""
    name_b64 = base64.b64encode(name[:50].encode("utf-8")).decode("ascii")
    headers = {
        **_auth_headers(access_token),
        "Content-Type": "application/octet-stream",
        "Asset-Upload-Metadata": f'{{"name_base64": "{name_b64}"}}',
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{API_BASE}/asset-uploads", headers=headers, content=file_bytes)
    _log_response("upload_asset", resp)
    if resp.status_code not in (200, 201):
        raise CanvaApiError(f"upload_asset failed: {resp.text[:500]}", resp.status_code)
    return resp.json().get("job", {})


async def poll_asset_upload(access_token: str, job_id: str, timeout_s: float = 20.0) -> Optional[str]:
    """Polls GET /asset-uploads/{job_id} until done. Returns the new asset id, or
    None if it's still in_progress after `timeout_s` (caller decides how to report that)."""
    job = await _poll_job(access_token, f"{API_BASE}/asset-uploads/{job_id}", "poll_asset_upload", timeout_s)
    if job.get("status") != "success":
        return None
    return (job.get("asset") or {}).get("id")


async def create_design(
    access_token: str, *, width: Optional[int] = None, height: Optional[int] = None,
    asset_id: Optional[str] = None, title: Optional[str] = None,
) -> dict[str, Any]:
    """POST /designs — scope design:content:write. Canva's only preset design_type
    names are doc/email/presentation/whiteboard (verified against the live API
    reference) — every other design type (poster/flyer/infographic/etc.) must use
    a custom width/height instead, which is what this always does. `asset_id`
    seeds the design's initial content with an uploaded image (see upload_asset)."""
    body: dict[str, Any] = {}
    if width and height:
        body["design_type"] = {"type": "custom", "width": width, "height": height}
    if asset_id:
        body["asset_id"] = asset_id
    if title:
        body["title"] = title[:255]
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(f"{API_BASE}/designs", headers=_auth_headers(access_token), json=body)
    _log_response("create_design", resp)
    if resp.status_code not in (200, 201):
        raise CanvaApiError(f"create_design failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def create_autofill_job(
    access_token: str, data: dict[str, Any], *,
    brand_template_id: Optional[str] = None, design_id: Optional[str] = None, title: Optional[str] = None,
) -> dict[str, Any]:
    """POST /autofills — scopes brandtemplate:content:read + design:content:write.
    Exactly one of brand_template_id/design_id must be given. `data` maps dataset
    field names to {"type":"text","text":...} / {"type":"image","asset_id":...} /
    {"type":"chart","chart_data":{...}} values — the field names and types must
    come from get_brand_template_dataset/get_design_dataset, never guessed."""
    if brand_template_id:
        body: dict[str, Any] = {"type": "create_from_brand_template", "brand_template_id": brand_template_id, "data": data}
    elif design_id:
        body = {"type": "create_from_design", "design_id": design_id, "data": data}
    else:
        raise ValueError("create_autofill_job requires brand_template_id or design_id")
    if title:
        body["title"] = title[:255]
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(f"{API_BASE}/autofills", headers=_auth_headers(access_token), json=body)
    _log_response("create_autofill_job", resp)
    if resp.status_code not in (200, 201):
        raise CanvaApiError(f"create_autofill_job failed: {resp.text[:500]}", resp.status_code)
    return resp.json().get("job", {})


async def poll_autofill_job(access_token: str, job_id: str, timeout_s: float = 25.0) -> dict[str, Any]:
    """Polls GET /autofills/{job_id} until done. Returns the final job dict
    (job["result"]["design"] holds id/thumbnail/urls on success)."""
    return await _poll_job(access_token, f"{API_BASE}/autofills/{job_id}", "poll_autofill_job", timeout_s)


async def import_design(access_token: str, file_bytes: bytes, title: str, mime_type: Optional[str] = None) -> dict[str, Any]:
    """POST /imports — scope design:content:write. Accepts PDF/PPTX/DOCX/PNG/JPG.
    PPTX/PDF preserve real editable structure in the resulting Canva design; PNG
    import is just a flattened background image — prefer PPTX/PDF when available."""
    title_b64 = base64.b64encode(title[:50].encode("utf-8")).decode("ascii")
    metadata = f'{{"title_base64": "{title_b64}"' + (f', "mime_type": "{mime_type}"' if mime_type else "") + "}"
    headers = {
        **_auth_headers(access_token),
        "Content-Type": "application/octet-stream",
        "Import-Metadata": metadata,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{API_BASE}/imports", headers=headers, content=file_bytes)
    _log_response("import_design", resp)
    if resp.status_code not in (200, 201):
        raise CanvaApiError(f"import_design failed: {resp.text[:500]}", resp.status_code)
    return resp.json().get("job", {})


async def poll_import_job(access_token: str, job_id: str, timeout_s: float = 30.0) -> dict[str, Any]:
    """Polls GET /imports/{job_id} until done. Returns the final job dict
    (job["result"]["designs"][0] holds id/thumbnail/urls on success)."""
    return await _poll_job(access_token, f"{API_BASE}/imports/{job_id}", "poll_import_job", timeout_s)


async def create_export_job(access_token: str, design_id: str, export_format: str) -> dict[str, Any]:
    """POST /exports — scope design:content:read. export_format is "png" or "pdf"."""
    fmt: dict[str, Any] = {"type": export_format}
    if export_format == "png":
        fmt["lossless"] = True
    body = {"design_id": design_id, "format": fmt}
    async with httpx.AsyncClient(timeout=20.0) as client:
        resp = await client.post(f"{API_BASE}/exports", headers=_auth_headers(access_token), json=body)
    _log_response("create_export_job", resp)
    if resp.status_code not in (200, 201):
        raise CanvaApiError(f"create_export_job failed: {resp.text[:500]}", resp.status_code)
    return resp.json().get("job", {})


async def poll_export_job(access_token: str, job_id: str, timeout_s: float = 25.0) -> dict[str, Any]:
    """Polls GET /exports/{job_id} until done. Returns the final job dict
    (job["urls"] holds the download URLs, 24h expiry, on success)."""
    return await _poll_job(access_token, f"{API_BASE}/exports/{job_id}", "poll_export_job", timeout_s)
