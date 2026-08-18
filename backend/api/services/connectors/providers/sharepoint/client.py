"""Thin wrappers around the real Microsoft Graph API for SharePoint (graph.microsoft.com/v1.0/sites)."""
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


async def get_root_site(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GRAPH_API_BASE}/sites/root", headers=_headers(access_token))
    if resp.status_code != 200:
        raise GraphApiError(f"get_root_site failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_sites(access_token: str, query: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GRAPH_API_BASE}/sites", headers=_headers(access_token), params={"search": query})
    if resp.status_code != 200:
        raise GraphApiError(f"list_sites failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_files(access_token: str, site_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GRAPH_API_BASE}/sites/{site_id}/drive/root/children", headers=_headers(access_token))
    if resp.status_code != 200:
        raise GraphApiError(f"list_files failed: {resp.text[:500]}", resp.status_code)
    return resp.json()
