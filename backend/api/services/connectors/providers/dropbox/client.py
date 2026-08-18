"""
Thin wrappers around the real Dropbox API v2.

Note the two hosts Dropbox uses: api.dropboxapi.com for RPC-style calls
(JSON body), content.dropboxapi.com for content transfer (upload/download,
which pass call args in the Dropbox-API-Arg header instead of the body).
"""
from __future__ import annotations

import json
from typing import Any, Optional

import httpx

API_BASE = "https://api.dropboxapi.com/2"
CONTENT_BASE = "https://content.dropboxapi.com/2"


class DropboxApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(access_token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {access_token}"}


async def get_current_account(access_token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{API_BASE}/users/get_current_account", headers=_headers(access_token))
    if resp.status_code != 200:
        raise DropboxApiError(f"get_current_account failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_folder(access_token: str, path: str = "") -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            f"{API_BASE}/files/list_folder", headers=_headers(access_token), json={"path": path},
        )
    if resp.status_code != 200:
        raise DropboxApiError(f"list_folder failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def download_file(access_token: str, path: str, max_bytes: int = 2_000_000) -> bytes:
    headers = {**_headers(access_token), "Dropbox-API-Arg": json.dumps({"path": path})}
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{CONTENT_BASE}/files/download", headers=headers)
    if resp.status_code != 200:
        raise DropboxApiError(f"download_file failed: {resp.text[:500]}", resp.status_code)
    return resp.content[:max_bytes]
