"""Thin wrappers around the real Google Calendar API v3 (googleapis.com/calendar/v3)."""
from __future__ import annotations

from typing import Any, Optional

import httpx

API_BASE = "https://www.googleapis.com/calendar/v3"


class GoogleCalendarApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def get_calendar(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/calendars/primary", headers=_headers(access_token))
    if resp.status_code != 200:
        raise GoogleCalendarApiError(f"get_calendar failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_events(access_token: str, max_results: int = 25) -> dict[str, Any]:
    params = {"maxResults": min(max(max_results, 1), 100), "singleEvents": "true", "orderBy": "startTime"}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/calendars/primary/events", headers=_headers(access_token), params=params)
    if resp.status_code != 200:
        raise GoogleCalendarApiError(f"list_events failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def create_event(access_token: str, summary: str, start_iso: str, end_iso: str) -> dict[str, Any]:
    body = {"summary": summary, "start": {"dateTime": start_iso}, "end": {"dateTime": end_iso}}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{API_BASE}/calendars/primary/events", headers=_headers(access_token), json=body)
    if resp.status_code not in (200, 201):
        raise GoogleCalendarApiError(f"create_event failed: {resp.text[:500]}", resp.status_code)
    return resp.json()
