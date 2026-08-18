"""
HealthMonitor — in-process asyncio background loop that periodically checks
every connected account whose connector declares supports_health_check.

After _FAILURE_THRESHOLD consecutive failed checks, the account's
connection_status flips to "error" so the frontend surfaces it without
waiting for the user to trigger an action that happens to fail. The
failure-streak counter is in-memory (best-effort monitoring signal, not the
system of record — execute_action's own error handling remains the
authoritative path for marking a connection broken), so it resets on
restart, which is an acceptable trade-off for a lightweight health sweep.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict

from api.db.base import SessionLocal
from api.db import crud

from .registry import connector_registry
from .events import log_event
from .credential_store import mark_status

log = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 300
_FAILURE_THRESHOLD = 3


class HealthMonitor:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None
        self._failure_streaks: dict[str, int] = defaultdict(int)

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        log.info("HealthMonitor started (poll every %ds)", _POLL_INTERVAL_SECONDS)

    async def stop(self) -> None:
        if self._task is None:
            return
        assert self._stop_event is not None
        self._stop_event.set()
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        log.info("HealthMonitor stopped")

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("HealthMonitor tick failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> int:
        """Run one sweep. Public so tests can call it directly. Returns the number checked."""
        db = SessionLocal()
        checked = 0
        try:
            for account in crud.list_connected_accounts(db):
                connector_row = crud.get_connector_by_id(db, account.connector_id)
                if not connector_row or not connector_row.enabled:
                    continue
                if not connector_registry.is_registered(connector_row.provider):
                    continue
                connector = connector_registry.get(connector_row.provider)
                if not connector.manifest.supports_health_check:
                    continue

                checked += 1
                key = f"{account.user_id}:{connector_row.id}"
                try:
                    result = await connector.health_check(db, account.user_id)
                except Exception as exc:
                    log.warning("Health check raised for provider=%s user=%s: %s",
                                connector_row.provider, account.user_id, exc)
                    result = None

                healthy = bool(result and result.healthy)
                if healthy:
                    self._failure_streaks[key] = 0
                else:
                    self._failure_streaks[key] += 1
                    if self._failure_streaks[key] >= _FAILURE_THRESHOLD:
                        mark_status(
                            db, account.user_id, connector_row.id,
                            connection_status="error",
                            error_message=(result.detail if result else "Health check failed"),
                        )

                log_event(
                    db, account.user_id, connector_row.id, event_type="health",
                    status="success" if healthy else "error",
                    error_message=(result.detail if result else "health_check raised an exception"),
                )
        finally:
            db.close()
        return checked


health_monitor = HealthMonitor()
