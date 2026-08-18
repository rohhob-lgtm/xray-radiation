"""Thin wrappers around the real Gmail API v1 (gmail.googleapis.com)."""
from __future__ import annotations

import base64
from email.mime.text import MIMEText
from typing import Any, Optional

import httpx

API_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


class GmailApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def get_profile(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/profile", headers=_headers(access_token))
    if resp.status_code != 200:
        raise GmailApiError(f"get_profile failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_messages(access_token: str, query: Optional[str] = None, max_results: int = 25) -> dict[str, Any]:
    params: dict[str, Any] = {"maxResults": min(max(max_results, 1), 100)}
    if query:
        params["q"] = query
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/messages", headers=_headers(access_token), params=params)
    if resp.status_code != 200:
        raise GmailApiError(f"list_messages failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def get_message(access_token: str, message_id: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/messages/{message_id}", headers=_headers(access_token), params={"format": "full"})
    if resp.status_code != 200:
        raise GmailApiError(f"get_message failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def send_message(access_token: str, to: str, subject: str, body: str) -> dict[str, Any]:
    mime = MIMEText(body)
    mime["to"] = to
    mime["subject"] = subject
    raw = base64.urlsafe_b64encode(mime.as_bytes()).decode("ascii")
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{API_BASE}/messages/send", headers=_headers(access_token), json={"raw": raw})
    if resp.status_code != 200:
        raise GmailApiError(f"send_message failed: {resp.text[:500]}", resp.status_code)
    return resp.json()
