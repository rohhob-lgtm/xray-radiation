"""
Identity resolution for the Global AI Brain.

Every memory / workspace-awareness function is scoped by a MemoryScope
instead of a raw user_id so authenticated and anonymous callers share one
code path:

  - Authenticated users get a durable, cross-session scope (is_persistent=True):
    MemoryItem/preferences/decisions are written and searched normally.
  - Anonymous visitors get an isolated, non-durable scope keyed by a
    frontend-generated UUID (X-Anon-Session-Id header) — never the shared
    user_id=NULL bucket other anonymous data in this app collapses to.
    MemoryItem writes are always skipped for these scopes; conversations are
    still saved (permanently, per the base persistence requirement) but kept
    isolated per anon_session_id.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, Request

from api.middleware.auth import optional_auth

ANON_SESSION_HEADER = "X-Anon-Session-Id"


@dataclass(frozen=True)
class MemoryScope:
    user_id: Optional[str]
    anon_session_id: Optional[str]
    is_persistent: bool

    @property
    def conversation_filter_kwargs(self) -> dict:
        """Kwargs for db/crud.py conversation queries — mutually exclusive scoping."""
        if self.is_persistent:
            return {"user_id": self.user_id}
        return {"anon_session_id": self.anon_session_id}


def get_identity(
    request: Request,
    user: Optional[dict] = Depends(optional_auth),
) -> MemoryScope:
    if user:
        return MemoryScope(user_id=user["id"], anon_session_id=None, is_persistent=True)

    anon_session_id = request.headers.get(ANON_SESSION_HEADER) or None
    return MemoryScope(user_id=None, anon_session_id=anon_session_id, is_persistent=False)
