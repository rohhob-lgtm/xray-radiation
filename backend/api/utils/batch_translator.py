"""
Parallel, token-aware batch translation for large documents.

Replaces one-LLM-call-per-segment (which made a 1,605-segment presentation
take ~2.2 hours at a 12 RPM pace, or return incomplete under the old 400-
segment cap) with:

  - Segments grouped into token-budgeted batches (~10-20 segments/request)
    translated with a single structured-JSON prompt instead of one call each.
  - Many batches in flight concurrently, paced by an adaptive rate limiter
    that starts at the account's configured RPM and backs off/recovers
    around real 429s instead of a blind guessed constant.
  - A JSON checkpoint file so an interrupted run resumes from where it left
    off — already-translated segments are never re-sent (no lost work, no
    duplicate API cost).
  - Per-batch structured-JSON parsing with a per-segment fallback: any
    segment a batch fails to return cleanly is retried individually rather
    than silently dropped.

Callers must treat a segment lacking `target` afterward as a hard failure —
this module does not itself decide whether that's acceptable.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)

_MAX_SEGMENTS_PER_BATCH = 18
_MAX_TOKENS_PER_BATCH = 3000
_MAX_CONCURRENT_BATCHES = 10
_BATCH_RETRY_ATTEMPTS = 4


def _estimate_tokens(text: str) -> int:
    """Cheap, dependency-free token estimate (~4 chars/token holds reasonably
    for both Latin and Arabic script at this scale) — good enough for batch
    sizing, not for billing accuracy."""
    return max(1, len(text) // 4)


def _build_batches(
    segments: list[dict],
    max_per_batch: int = _MAX_SEGMENTS_PER_BATCH,
    max_tokens_per_batch: int = _MAX_TOKENS_PER_BATCH,
) -> list[list[int]]:
    """Returns lists of segment indices (into `segments`), grouped by token
    budget and count. Segments with empty/whitespace-only source are
    excluded entirely — callers should already set target="" for those."""
    batches: list[list[int]] = []
    current: list[int] = []
    current_tokens = 0

    for idx, seg in enumerate(segments):
        src = (seg.get("source") or "").strip()
        if not src:
            continue
        t = _estimate_tokens(src)
        if current and (len(current) >= max_per_batch or current_tokens + t > max_tokens_per_batch):
            batches.append(current)
            current = []
            current_tokens = 0
        current.append(idx)
        current_tokens += t

    if current:
        batches.append(current)
    return batches


class _AdaptiveRateLimiter:
    """Token-bucket paced at a target RPM, with 429-driven backoff and
    cautious recovery — the practical stand-in for "read the account's real
    limit": there is no generic API to query a Gemini API key's live quota,
    so the configured RPM (read from GEMINI_RPM_LIMIT, set to the account's
    actual stated limit) is the starting target, and this limiter adapts
    around it in response to real rate-limit responses instead of trusting
    that number blindly."""

    def __init__(self, target_rpm: int):
        self._min_rpm = max(5, target_rpm // 10)
        self._max_rpm = target_rpm
        self._rpm = target_rpm
        self._lock = asyncio.Lock()
        self._next_slot = 0.0
        self._consecutive_successes = 0

    def _interval(self) -> float:
        return 60.0 / max(1, self._rpm)

    async def acquire(self) -> None:
        async with self._lock:
            now = time.monotonic()
            start = max(now, self._next_slot)
            self._next_slot = start + self._interval()
            wait = start - now
        if wait > 0:
            await asyncio.sleep(wait)

    async def report_rate_limited(self) -> None:
        async with self._lock:
            self._rpm = max(self._min_rpm, int(self._rpm * 0.7))
            self._consecutive_successes = 0
            log.warning("Batch translator: rate-limited, backing off to %d RPM", self._rpm)

    async def report_success(self) -> None:
        async with self._lock:
            self._consecutive_successes += 1
            if self._consecutive_successes >= 8 and self._rpm < self._max_rpm:
                self._rpm = min(self._max_rpm, self._rpm + max(1, self._rpm // 10))
                self._consecutive_successes = 0


def _configured_rpm() -> int:
    """Reads GEMINI_RPM_LIMIT — set this to the account's actual stated RPM
    limit (not a guessed constant). Falls back to a conservative default
    only when unset."""
    try:
        return max(1, int(os.environ.get("GEMINI_RPM_LIMIT", "") or 60))
    except ValueError:
        return 60


_BATCH_SYSTEM_PROMPT_SUFFIX = (
    "\n\nYou will receive multiple numbered text segments in one request. "
    "Translate each one independently. Return ONLY a JSON array, no other "
    "text, markdown fences, or commentary — exactly this shape:\n"
    '[{"id": <segment id>, "translation": "<translated text>"}, ...]\n'
    "Include exactly one entry per input segment, preserving its \"id\" "
    "exactly. Do not merge, skip, or reorder segments."
)


def _parse_batch_response(raw: str, expected_ids: set[int]) -> dict[int, str]:
    """Best-effort JSON parse of a batch response. Returns {id: translation}
    for whichever ids were successfully parsed — may be a subset of
    expected_ids, which the caller must reconcile."""
    text = raw.strip()
    # Strip a markdown code fence if the model added one despite instructions.
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)

    def _try_parse(s: str) -> Optional[list]:
        try:
            data = json.loads(s)
            return data if isinstance(data, list) else None
        except Exception:
            return None

    data = _try_parse(text)
    if data is None:
        m = re.search(r"\[.*\]", text, re.S)
        if m:
            data = _try_parse(m.group(0))
    if data is None:
        return {}

    out: dict[int, str] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        try:
            sid = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        translation = item.get("translation")
        if sid in expected_ids and isinstance(translation, str):
            out[sid] = translation
    return out


class _Checkpoint:
    """Simple JSON-on-disk checkpoint keyed by segment id, so an interrupted
    or re-run translation resumes instead of re-translating (and re-billing)
    everything from scratch."""

    def __init__(self, path: Path):
        self.path = path
        self.data: dict[str, str] = {}
        if path.exists():
            try:
                self.data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                log.warning("Checkpoint at %s unreadable — starting fresh", path)
                self.data = {}

    def get(self, seg_id: int) -> Optional[str]:
        return self.data.get(str(seg_id))

    def set_many(self, items: dict[int, str]) -> None:
        for sid, translation in items.items():
            self.data[str(sid)] = translation
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def clear(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except Exception:
            pass


async def _translate_single(provider: Any, system_prompt: str, text: str) -> str:
    response = await provider.chat([{"role": "user", "content": text}], system_prompt=system_prompt)
    return response.strip()


async def _translate_batch_with_retry(
    provider: Any,
    system_prompt: str,
    segments: list[dict],
    batch_ids: list[int],
    limiter: _AdaptiveRateLimiter,
    checkpoint: _Checkpoint,
) -> dict[int, str]:
    import openai

    payload = [{"id": sid, "text": (segments[sid].get("source") or "").strip()} for sid in batch_ids]
    prompt = "Segments:\n" + json.dumps(payload, ensure_ascii=False)
    expected = set(batch_ids)
    results: dict[int, str] = {}

    for attempt in range(_BATCH_RETRY_ATTEMPTS):
        await limiter.acquire()
        try:
            raw = await _translate_single(provider, system_prompt + _BATCH_SYSTEM_PROMPT_SUFFIX, prompt)
        except openai.RateLimitError:
            await limiter.report_rate_limited()
            await asyncio.sleep(min(30, 2 ** attempt))
            continue
        except Exception as exc:
            log.warning("Batch translation attempt %d failed: %s", attempt, exc)
            await asyncio.sleep(min(15, 2 ** attempt))
            continue

        await limiter.report_success()
        parsed = _parse_batch_response(raw, expected)
        results.update(parsed)
        expected -= set(parsed.keys())
        if not expected:
            break

    if expected:
        # Structured batch parsing didn't cover every segment even after
        # retries — fall back to translating just the missing ones
        # individually rather than losing them. Dispatched CONCURRENTLY, not
        # one-at-a-time: a sequential per-segment retry loop compounds badly
        # under real rate-limit pressure (each segment paying its own full
        # backoff before the next one even starts), which is what turned a
        # ~15s job into a ~28 minute one in practice — the limiter already
        # enforces the actual pacing, so concurrent dispatch here doesn't
        # violate it, it just stops the backoff sleeps from stacking serially.
        async def _fallback_one(sid: int) -> None:
            for attempt in range(_BATCH_RETRY_ATTEMPTS):
                await limiter.acquire()
                try:
                    translated = await _translate_single(
                        provider, system_prompt, (segments[sid].get("source") or "").strip()
                    )
                    results[sid] = translated
                    await limiter.report_success()
                    return
                except openai.RateLimitError:
                    await limiter.report_rate_limited()
                    await asyncio.sleep(min(15, 2 ** attempt))
                except Exception as exc:
                    log.warning("Per-segment fallback for id=%d attempt %d failed: %s", sid, attempt, exc)
                    await asyncio.sleep(min(8, 2 ** attempt))

        await asyncio.gather(*(_fallback_one(sid) for sid in expected))

    if results:
        checkpoint.set_many(results)
    return results


async def translate_segments_parallel(
    segments: list[dict],
    provider: Any,
    system_prompt: str,
    checkpoint_path: Path,
    max_concurrent_batches: int = _MAX_CONCURRENT_BATCHES,
) -> list[str]:
    """Mutates `segments[i]["target"]` in place for every segment with
    non-empty source. Returns a list of segment ids (into `segments`) that
    still lack a target after all retries — empty means every segment was
    translated. Callers must check this and refuse to export if non-empty.
    """
    checkpoint = _Checkpoint(checkpoint_path)
    limiter = _AdaptiveRateLimiter(_configured_rpm())

    for seg in segments:
        if not (seg.get("source") or "").strip():
            seg["target"] = ""

    pending_ids = [i for i, seg in enumerate(segments) if (seg.get("source") or "").strip()]
    resumed = 0
    for sid in list(pending_ids):
        cached = checkpoint.get(sid)
        if cached is not None:
            segments[sid]["target"] = cached
            pending_ids.remove(sid)
            resumed += 1
    if resumed:
        log.info("Batch translator: resumed %d segment(s) from checkpoint", resumed)

    if not pending_ids:
        return []

    pending_segments = [s for s in segments]  # same objects, indices preserved
    batches = _build_batches(
        [segments[i] if i in pending_ids else {"source": ""} for i in range(len(segments))],
    )
    # Only keep batches that actually contain pending ids (they will, since
    # _build_batches skips empty-source segments and we blanked resumed ones
    # above only in `target`, not `source` — filter explicitly for safety).
    pending_set = set(pending_ids)
    batches = [[i for i in b if i in pending_set] for b in batches]
    batches = [b for b in batches if b]

    semaphore = asyncio.Semaphore(max_concurrent_batches)

    async def _run_batch(batch_ids: list[int]) -> None:
        async with semaphore:
            results = await _translate_batch_with_retry(
                provider, system_prompt, segments, batch_ids, limiter, checkpoint,
            )
            for sid, translation in results.items():
                segments[sid]["target"] = translation

    await asyncio.gather(*(_run_batch(b) for b in batches))

    still_missing = [
        i for i in pending_ids
        if not (segments[i].get("target") or "").strip() and (segments[i].get("source") or "").strip()
    ]
    if not still_missing:
        checkpoint.clear()
    return still_missing
