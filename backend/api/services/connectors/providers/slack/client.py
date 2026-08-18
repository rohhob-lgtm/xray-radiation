"""
Thin wrappers around the real Slack Web API (slack.com/api).

Slack's Web API always returns HTTP 200 with an {"ok": bool, "error": str}
envelope, even on failure — every call here checks `ok` explicitly rather
than trusting the HTTP status code.
"""
from __future__ import annotations

from typing import Any, Optional

import httpx

API_BASE = "https://slack.com/api"


class SlackApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def _check(resp: httpx.Response, action: str) -> dict[str, Any]:
    body = resp.json()
    if not body.get("ok"):
        raise SlackApiError(f"{action} failed: {body.get('error', 'unknown_error')}", resp.status_code)
    return body


async def auth_test(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{API_BASE}/auth.test", headers=_headers(access_token))
    return await _check(resp, "auth_test")


async def list_channels(access_token: str, limit: int = 25) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/conversations.list", headers=_headers(access_token), params={"limit": limit})
    return await _check(resp, "list_channels")


async def send_message(access_token: str, channel: str, text: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{API_BASE}/chat.postMessage", headers=_headers(access_token),
                                  json={"channel": channel, "text": text})
    return await _check(resp, "send_message")
