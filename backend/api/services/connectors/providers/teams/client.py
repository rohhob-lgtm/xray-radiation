"""Thin wrappers around the real Microsoft Graph API for Teams (graph.microsoft.com/v1.0/teams)."""
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


async def list_joined_teams(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GRAPH_API_BASE}/me/joinedTeams", headers=_headers(access_token))
    if resp.status_code != 200:
        raise GraphApiError(f"list_joined_teams failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_channels(access_token: str, team_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{GRAPH_API_BASE}/teams/{team_id}/channels", headers=_headers(access_token))
    if resp.status_code != 200:
        raise GraphApiError(f"list_channels failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def send_channel_message(access_token: str, team_id: str, channel_id: str, content: str) -> dict[str, Any]:
    body = {"body": {"content": content}}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{GRAPH_API_BASE}/teams/{team_id}/channels/{channel_id}/messages",
            headers=_headers(access_token), json=body,
        )
    if resp.status_code not in (200, 201):
        raise GraphApiError(f"send_channel_message failed: {resp.text[:500]}", resp.status_code)
    return resp.json()
