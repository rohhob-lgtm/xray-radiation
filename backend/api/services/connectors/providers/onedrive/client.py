"""Thin wrappers around the real Microsoft Graph API for OneDrive (graph.microsoft.com/v1.0/me/drive)."""
from __future__ import annotations

from typing import Any, Optional

import httpx

from .._shared.microsoft_oauth import GRAPH_API_BASE


class GraphApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def get_drive(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GRAPH_API_BASE}/me/drive", headers=_headers(access_token))
    if resp.status_code != 200:
        raise GraphApiError(f"get_drive failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_files(access_token: str, folder_path: Optional[str] = None) -> dict[str, Any]:
    suffix = f"/root:/{folder_path}:/children" if folder_path else "/root/children"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GRAPH_API_BASE}/me/drive{suffix}", headers=_headers(access_token))
    if resp.status_code != 200:
        raise GraphApiError(f"list_files failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def download_file(access_token: str, item_id: str, max_bytes: int = 2_000_000) -> bytes:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(f"{GRAPH_API_BASE}/me/drive/items/{item_id}/content", headers=_headers(access_token))
    if resp.status_code != 200:
        raise GraphApiError(f"download_file failed: {resp.text[:500]}", resp.status_code)
    return resp.content[:max_bytes]
