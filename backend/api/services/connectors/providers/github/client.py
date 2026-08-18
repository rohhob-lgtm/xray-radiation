"""Thin wrappers around the real GitHub REST API (api.github.com)."""
from __future__ import annotations

import base64
from typing import Any, Optional

import httpx

API_BASE = "https://api.github.com"


class GitHubApiError(Exception):
    def __init__(self, message: str, status_code: Optional[int] = None):
        super().__init__(message)
        self.status_code = status_code


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28"}


async def get_authenticated_user(token: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/user", headers=_headers(token))
    if resp.status_code != 200:
        raise GitHubApiError(f"get_authenticated_user failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def list_repos(token: str, per_page: int = 25) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/user/repos", headers=_headers(token), params={"per_page": min(per_page, 100)})
    if resp.status_code != 200:
        raise GitHubApiError(f"list_repos failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def read_file(token: str, owner: str, repo: str, path: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/repos/{owner}/{repo}/contents/{path}", headers=_headers(token))
    if resp.status_code != 200:
        raise GitHubApiError(f"read_file failed: {resp.text[:500]}", resp.status_code)
    data = resp.json()
    if isinstance(data, dict) and data.get("encoding") == "base64" and data.get("content"):
        data["decoded_content"] = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
    return data


async def list_issues(token: str, owner: str, repo: str) -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(f"{API_BASE}/repos/{owner}/{repo}/issues", headers=_headers(token))
    if resp.status_code != 200:
        raise GitHubApiError(f"list_issues failed: {resp.text[:500]}", resp.status_code)
    return resp.json()


async def create_pull_request(token: str, owner: str, repo: str, title: str, head: str, base: str, body: str = "") -> dict[str, Any]:
    payload = {"title": title, "head": head, "base": base, "body": body}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(f"{API_BASE}/repos/{owner}/{repo}/pulls", headers=_headers(token), json=payload)
    if resp.status_code not in (200, 201):
        raise GitHubApiError(f"create_pull_request failed: {resp.text[:500]}", resp.status_code)
    return resp.json()
