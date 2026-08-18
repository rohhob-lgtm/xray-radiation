"""
Shared Microsoft Office desktop COM availability probing + hang-timeout
helpers, used by both ``word_com_finalizer`` and ``powerpoint_com_finalizer``.

Two problems these solve:

1. Both finalizer modules previously only discovered Office/COM was
   unavailable *reactively*, mid-translation-job, after real work had already
   happened. ``check_word_available()``/``check_powerpoint_available()`` give
   callers (the pipeline, a health endpoint) a cheap, cached upfront probe —
   launch the real application via COM and immediately quit, no document
   opened.

2. Blocking COM calls (``Documents.Open``, ``ExportAsFixedFormat``, ...) have
   no timeout of their own — a hung call can stall a request indefinitely.
   ``run_with_timeout`` runs such a call in a worker thread and enforces a
   wall-clock deadline; the caller supplies an ``on_timeout_kill`` callback
   (typically a force-kill of the orphaned WINWORD.EXE/POWERPNT.EXE process)
   since Python cannot forcibly terminate a thread.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import time
from typing import Callable, TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")

_CACHE_TTL_S = 60.0
_availability_cache: dict[str, tuple[float, bool]] = {}


def _probe_app_uncached(prog_id: str) -> bool:
    if os.name != "nt":
        return False
    try:
        import pythoncom
        import win32com.client
    except ImportError:
        return False

    pythoncom.CoInitialize()
    app = None
    try:
        app = win32com.client.DispatchEx(prog_id)
        return True
    except Exception as exc:
        log.debug("Office COM availability probe failed for %s: %s", prog_id, exc)
        return False
    finally:
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


def _probe_app(prog_id: str, cache_key: str) -> bool:
    now = time.time()
    cached = _availability_cache.get(cache_key)
    if cached is not None and (now - cached[0]) < _CACHE_TTL_S:
        return cached[1]

    available = _probe_app_uncached(prog_id)
    _availability_cache[cache_key] = (now, available)
    return available


def check_word_available() -> bool:
    """Cheap, cached check for whether Microsoft Word desktop COM automation
    is usable right now — no document is opened."""
    return _probe_app("Word.Application", "word")


def check_powerpoint_available() -> bool:
    """Cheap, cached check for whether Microsoft PowerPoint desktop COM
    automation is usable right now — no presentation is opened."""
    return _probe_app("PowerPoint.Application", "powerpoint")


def clear_availability_cache() -> None:
    """Test/ops hook — force the next check_*_available() call to re-probe
    instead of returning a cached result."""
    _availability_cache.clear()


def run_with_timeout(
    fn: Callable[[], T],
    timeout_s: float,
    *,
    on_timeout_kill: Callable[[], None] | None = None,
) -> T:
    """
    Run a blocking call in a worker thread and enforce a wall-clock timeout.

    Python cannot forcibly terminate a running thread, so on timeout the
    worker thread is simply abandoned (it will keep running, or eventually
    error out on its own once the COM server it was talking to disappears);
    ``on_timeout_kill`` is invoked so the caller can force-kill the orphaned
    Office process so it cannot linger or corrupt a retry attempt.

    Raises ``concurrent.futures.TimeoutError`` on timeout — callers should
    catch this and translate it into their own automation-error type.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(fn)
        try:
            return future.result(timeout=timeout_s)
        except concurrent.futures.TimeoutError:
            log.warning("Office COM call exceeded %.0fs timeout — treating as hung", timeout_s)
            if on_timeout_kill is not None:
                try:
                    on_timeout_kill()
                except Exception:
                    log.warning("on_timeout_kill callback failed", exc_info=True)
            raise
