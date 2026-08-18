"""
SyncScheduler — in-process asyncio background loop that periodically syncs
every connector account due for a sync (manifest.supports_sync=True).

No new infra: reads/writes ConnectorSyncState so due-work survives a
restart; swapping in Celery+Redis later only replaces _run()/_tick(), not
the connector interface (connector.sync() is unchanged either way).

start()/stop() are called from main.py's existing startup/shutdown hooks so
the loop never leaks across app restarts or test runs.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from api.db.base import SessionLocal
from api.db import crud

from .registry import connector_registry
from .events import log_event

log = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 60


class SyncScheduler:
    def __init__(self) -> None:
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

    def start(self) -> None:
        if self._task is not None:
            return
        self._stop_event = asyncio.Event()
        self._task = asyncio.create_task(self._run())
        log.info("SyncScheduler started (poll every %ds)", _POLL_INTERVAL_SECONDS)

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
        log.info("SyncScheduler stopped")

    async def _run(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self.tick()
            except Exception:
                log.exception("SyncScheduler tick failed")
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=_POLL_INTERVAL_SECONDS)
            except asyncio.TimeoutError:
                pass

    async def tick(self) -> int:
        """Run one sweep of due syncs. Public so tests can call it directly
        without waiting on the poll interval. Returns the number processed."""
        db = SessionLocal()
        processed = 0
        try:
            now = datetime.now(timezone.utc)
            for state in crud.list_due_sync_states(db, now):
                connector_row = crud.get_connector_by_id(db, state.connector_id)
                if not connector_row or not connector_row.enabled:
                    continue
                if not connector_registry.is_registered(connector_row.provider):
                    continue
                connector = connector_registry.get(connector_row.provider)
                if not connector.manifest.supports_sync:
                    continue

                processed += 1
                try:
                    result = await connector.sync(db, state.user_id, state.cursor or {})
                except Exception as exc:
                    log.warning("Sync raised for provider=%s user=%s: %s",
                                connector_row.provider, state.user_id, exc)
                    result = None

                status = "success" if (result and result.success) else "error"

                # Hybrid Workspace Awareness trigger #11 (connector synchronization).
                if status == "success":
                    from api.services.workspace_index import mark_dirty
                    mark_dirty(
                        db, "connector_item", f"{connector_row.provider}:{state.user_id}",
                        reason="connector_sync",
                    )

                crud.upsert_connector_sync_state(
                    db, user_id=state.user_id, connector_id=state.connector_id,
                    cursor=(result.next_cursor if result and result.next_cursor else state.cursor),
                    last_sync_at=now, last_sync_status=status,
                    last_sync_error=(result.error_message if result else "sync raised an exception"),
                    next_sync_at=now + timedelta(seconds=state.sync_interval_seconds),
                )
                log_event(
                    db, state.user_id, state.connector_id, event_type="sync", status=status,
                    action="scheduled_sync",
                    error_code=(result.error_code if result else "SYNC_EXCEPTION"),
                    error_message=(result.error_message if result else None),
                )
        finally:
            db.close()
        return processed


sync_scheduler = SyncScheduler()
