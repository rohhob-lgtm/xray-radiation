"""
Thin wrappers around the real Google Drive API v3 (googleapis.com/drive/v3)
and the standard Google OAuth2 userinfo endpoint. Every function makes an
actual HTTP call — nothing here fabricates a response.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

log = logging.getLogger(__name__)

API_BASE = "https://www.googleapis.com/drive/v3"
USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

_FILE_FIELDS = "id,name,mimeType,size,modifiedTime,webViewLink,iconLink,thumbnailLink,parents"
_LIST_FIELDS = f"files({_FILE_FIELDS}),nextPageToken"

# Native Google Workspace formats -> their real export mimeType, per Drive API docs.
EXPORT_MIME_TYPES = {
    "google_doc": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "google_slide": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "google_sheet": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}

FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"

# Friendly file_type values the LLM/tool schema can pass -> real Drive mimeType
# filter. Values ending in "/" are prefix-matched (`mimeType contains`);
# everything else is an exact match (`mimeType =`).
FILE_TYPE_MIME_FILTERS = {
    "pdf": "application/pdf",
    "google_doc": "application/vnd.google-apps.document",
    "google_slide": "application/vnd.google-apps.presentation",
    "google_sheet": "application/vnd.google-apps.spreadsheet",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "folder": FOLDER_MIME_TYPE,
    "image": "image/",
}


class GoogleApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


def _log_response(action: str, resp: httpx.Response) -> None:
    safe_headers = {k: v for k, v in resp.headers.items() if k.lower() != "authorization"}
    log.info("[google_drive_api] action=%s status=%s headers=%s body=%s",
              action, resp.status_code, safe_headers, resp.text[:800])


async def get_profile(access_token: str) -> dict[str, Any]:
    """GET the standard Google OAuth2 userinfo endpoint — scope: email, profile."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(USERINFO_URL, headers=_headers(access_token))
    _log_response("get_profile", resp)
    if resp.status_code != 200:
        raise GoogleApiError(f"get_profile failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def about_user(access_token: str) -> dict[str, Any]:
    """GET /about?fields=user — cheapest authenticated Drive call, used for health checks."""
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/about", headers=_headers(access_token), params={"fields": "user"})
    _log_response("about_user", resp)
    if resp.status_code != 200:
        raise GoogleApiError(f"about_user failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_files(
    access_token: str, query: Optional[str] = None, folder_id: Optional[str] = None,
    page_size: int = 25, order_by: Optional[str] = None,
) -> dict[str, Any]:
    """GET /files — scope: drive.readonly. `folder_id` lists one folder's direct children."""
    q_parts = ["trashed = false"]
    if query:
        escaped = query.replace("'", "\\'")
        q_parts.append(f"name contains '{escaped}'")
    if folder_id:
        q_parts.append(f"'{folder_id}' in parents")
    params: dict[str, Any] = {
        "pageSize": min(max(page_size, 1), 100),
        "fields": _LIST_FIELDS,
        "q": " and ".join(q_parts),
    }
    if order_by:
        params["orderBy"] = order_by
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/files", headers=_headers(access_token), params=params)
    _log_response("list_files", resp)
    if resp.status_code != 200:
        raise GoogleApiError(f"list_files failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def get_file_metadata(access_token: str, file_id: str) -> dict[str, Any]:
    params = {"fields": _FILE_FIELDS}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/files/{file_id}", headers=_headers(access_token), params=params)
    _log_response("get_file_metadata", resp)
    if resp.status_code != 200:
        raise GoogleApiError(f"get_file_metadata failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def download_file(access_token: str, file_id: str, max_bytes: int = 20_000_000) -> bytes:
    """Binary download for a regular (non-Google-native) file — PDF, DOCX, images, etc."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(f"{API_BASE}/files/{file_id}", headers=_headers(access_token), params={"alt": "media"})
    _log_response("download_file", resp)
    if resp.status_code != 200:
        raise GoogleApiError(f"download_file failed: {resp.text[:500]}", resp.status_code)
    return resp.content[:max_bytes]


async def export_file(access_token: str, file_id: str, mime_type: str, max_bytes: int = 10_000_000) -> bytes:
    """GET /files/{id}/export — for native Google Docs/Sheets/Slides only (10 MB export cap)."""
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{API_BASE}/files/{file_id}/export", headers=_headers(access_token), params={"mimeType": mime_type},
        )
    _log_response("export_file", resp)
    if resp.status_code != 200:
        raise GoogleApiError(f"export_file failed: {resp.text[:500]}", resp.status_code)
    return resp.content[:max_bytes]


async def create_folder(access_token: str, name: str, parent_id: Optional[str] = None) -> dict[str, Any]:
    """POST /files — scope: drive.file (write). Untested until a write-scoped reconnect happens."""
    body: dict[str, Any] = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        body["parents"] = [parent_id]
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{API_BASE}/files", headers=_headers(access_token), json=body,
                                  params={"fields": _FILE_FIELDS})
    _log_response("create_folder", resp)
    if resp.status_code not in (200, 201):
        raise GoogleApiError(f"create_folder failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def upload_file(
    access_token: str, filename: str, content: bytes, mime_type: str = "application/octet-stream",
    parent_id: Optional[str] = None,
) -> dict[str, Any]:
    """
    POST (multipart upload) to the /upload endpoint — scope: drive.file (write).
    Untested until a write-scoped reconnect happens.
    """
    metadata: dict[str, Any] = {"name": filename}
    if parent_id:
        metadata["parents"] = [parent_id]
    files = {
        "metadata": (None, json.dumps(metadata), "application/json"),
        "file": (filename, content, mime_type),
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(
            "https://www.googleapis.com/upload/drive/v3/files",
            headers=_headers(access_token), params={"uploadType": "multipart", "fields": _FILE_FIELDS},
            files=files,
        )
    _log_response("upload_file", resp)
    if resp.status_code not in (200, 201):
        raise GoogleApiError(f"upload_file failed: {resp.text[:500]}", resp.status_code)
    return resp.json()
