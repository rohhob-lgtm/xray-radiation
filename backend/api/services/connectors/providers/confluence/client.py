"""
Thin wrappers around the real Confluence Cloud REST API via Atlassian's
API gateway. Every Confluence Cloud API call is scoped to a specific site
(cloud id), resolved once via the accessible-resources endpoint after
OAuth and cached alongside the stored credentials.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

ACCESSIBLE_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"


class ConfluenceApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}", "Accept": "application/json"}


async def get_accessible_resources(access_token: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(ACCESSIBLE_RESOURCES_URL, headers=_headers(access_token))
    if resp.status_code != 200:
        raise ConfluenceApiError(f"get_accessible_resources failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


def _base(cloud_id: str) -> str:
    return f"https://api.atlassian.com/ex/confluence/{cloud_id}/wiki/rest/api"


async def list_spaces(access_token: str, cloud_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{_base(cloud_id)}/space", headers=_headers(access_token))
    if resp.status_code != 200:
        raise ConfluenceApiError(f"list_spaces failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def get_page(access_token: str, cloud_id: str, page_id: str) -> dict[str, Any]:
    params = {"expand": "body.storage"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{_base(cloud_id)}/content/{page_id}", headers=_headers(access_token), params=params)
    if resp.status_code != 200:
        raise ConfluenceApiError(f"get_page failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def search(access_token: str, cloud_id: str, cql: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{_base(cloud_id)}/content/search", headers=_headers(access_token), params={"cql": cql})
    if resp.status_code != 200:
        raise ConfluenceApiError(f"search failed: {resp.text[:500]}", resp.status_code)
    return resp.json()
