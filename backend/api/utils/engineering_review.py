"""
AI Engineering Review — post-translation quality pass.

After the translation provider completes the raw translation, this module
runs a second GPT-4o pass that:
  - Improves engineering and X-ray security terminology
  - Corrects radiation terminology (ALARA, mSv, mGy, etc.)
  - Validates safety-warning phrasing
  - Fixes maintenance and field-service language
  - Checks consistency of repeated terms across the document
  - Flags potential terminology conflicts

The review operates segment-by-segment in batches of 20, examining the
full document context (a vocabulary summary) to ensure consistency.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re

log = logging.getLogger(__name__)

_REVIEW_SYSTEM = """You are a senior X-ray security engineering editor reviewing a translated technical document.

Source language: {source_lang}
Target language: {target_lang}

Your job is to improve the translation quality for these specific domains:
1. X-ray security screening systems (baggage screening, body scanners, cargo inspection)
2. Radiation physics (dose, exposure, ALARA, mSv, mGy, mAs, kVp, focal spot)
3. Electro-mechanical engineering (HV generators, conveyors, gantry, detectors)
4. Maintenance and field service (calibration, fault codes, preventive maintenance)
5. Safety warnings (radiation safety, electrical safety, lockout/tagout)
6. PCB and connector terminology (PCB IDs, connector types, signal labels)

For each segment:
- Fix incorrect technical terminology
- Ensure consistency with the glossary context provided
- Improve safety-warning phrasing
- Preserve all numbers, codes, and units unchanged
- If a segment is already correct, return it unchanged

Return ONLY a JSON object:
{{"reviews": {{"0": {{"improved": "...", "changed": true/false, "reason": "..."}}, ...}}}}

If a segment needs no change, set changed=false and return the original text in improved."""

_BATCH_SIZE = 40          # segments per review batch
_MAX_CONCURRENT = 5       # parallel review calls
_MAX_REVIEW_RETRIES = 4       # retries on rate-limit before giving up on a batch
_REVIEW_RETRY_BASE_SECS = 4   # exponential backoff base


async def run_engineering_review(
    segments: list[dict],
    source_lang: str,
    target_lang: str,
    client,
    usage: dict | None = None,
    model_name: str = "gpt-4o",
) -> tuple[list[dict], list[dict]]:
    """
    Run AI engineering review on translated segments.

    Args:
        segments:     list of segment dicts with 'source' and 'target' keys
        source_lang:  e.g. "en"
        target_lang:  e.g. "ar"
        client:       AsyncOpenAI client

    Returns:
        (reviewed_segments, changes)
        where changes is a list of {seg_id, before, after, reason}
    """
    lang_names = {
        "en": "English", "ar": "Arabic", "fr": "French",
        "de": "German", "es": "Spanish", "zh": "Chinese",
    }
    src_name = lang_names.get(source_lang, source_lang)
    tgt_name = lang_names.get(target_lang, target_lang)

    # Build a vocabulary context summary from the first 50 translated segments
    # so the reviewer can ensure consistency across the document.
    vocab_sample = segments[:50]
    vocab_lines = [f"  {s['source'][:60]} → {s.get('target','')[:60]}" for s in vocab_sample if s.get("target")]
    vocab_context = "ESTABLISHED TRANSLATIONS (for consistency):\n" + "\n".join(vocab_lines[:30])

    system_prompt = _REVIEW_SYSTEM.format(source_lang=src_name, target_lang=tgt_name)
    changes: list[dict] = []
    reviewed = [dict(s) for s in segments]

    # ── Concurrent batch review ────────────────────────────────────────────────
    # All review batches run in parallel (capped by semaphore) instead of the
    # old sequential loop + 0.5 s sleep between every batch.
    sem = asyncio.Semaphore(_MAX_CONCURRENT)

    async def _review_one(batch_start: int) -> tuple[int, dict]:
        """Return (batch_start, reviews_dict) for one batch."""
        batch = segments[batch_start:batch_start + _BATCH_SIZE]
        batch_segs = {
            str(i): {
                "source": s.get("source", ""),
                "current_translation": s.get("target", ""),
            }
            for i, s in enumerate(batch)
        }
        user_msg = (
            f"{vocab_context}\n\nSEGMENTS TO REVIEW:\n"
            + json.dumps(batch_segs, ensure_ascii=False)
        )
        try:
            from openai import RateLimitError as _RateLimitError
        except ImportError:
            _RateLimitError = Exception

        async with sem:
            for attempt in range(_MAX_REVIEW_RETRIES):
                try:
                    from api.utils.rate_limiter import acquire_slot
                    await acquire_slot(model_name)
                    resp = await client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_msg},
                        ],
                        max_completion_tokens=8000,
                        temperature=0.05,
                        response_format={"type": "json_object"},
                    )
                    # Track actual token usage per review batch
                    try:
                        if usage is not None and getattr(resp, "usage", None) is not None:
                            _in  = resp.usage.prompt_tokens or 0
                            _out = resp.usage.completion_tokens or 0
                            usage["in"]  = usage.get("in",  0) + _in
                            usage["out"] = usage.get("out", 0) + _out
                            usage["review_in"]  = usage.get("review_in",  0) + _in
                            usage["review_out"] = usage.get("review_out", 0) + _out
                            usage["review_calls"] = usage.get("review_calls", 0) + 1
                            _details = getattr(resp.usage, "prompt_tokens_details", None)
                            _cached = getattr(_details, "cached_tokens", 0) if _details else 0
                            usage["review_cached"] = usage.get("review_cached", 0) + (_cached or 0)
                    except Exception:
                        pass
                    raw = resp.choices[0].message.content or "{}"
                    data = json.loads(raw)
                    return batch_start, data.get("reviews", {})
                except _RateLimitError as e:
                    if attempt < _MAX_REVIEW_RETRIES - 1:
                        wait = _REVIEW_RETRY_BASE_SECS * (2 ** attempt)
                        log.warning(
                            "Engineering review batch %d rate-limited (attempt %d/%d) — waiting %ds: %s",
                            batch_start, attempt + 1, _MAX_REVIEW_RETRIES, wait, e,
                        )
                        await asyncio.sleep(wait)
                        continue
                    log.warning("Engineering review batch %d gave up after %d attempts: %s", batch_start, _MAX_REVIEW_RETRIES, e)
                    return batch_start, {}
                except Exception as e:
                    log.warning("Engineering review batch %d failed: %s", batch_start, e)
                    return batch_start, {}
            return batch_start, {}

    batch_starts = list(range(0, len(segments), _BATCH_SIZE))
    outcomes = await asyncio.gather(*[_review_one(bs) for bs in batch_starts])

    # Merge results in order
    for batch_start, reviews in sorted(outcomes, key=lambda x: x[0]):
        for idx_str, review in reviews.items():
            try:
                idx = int(idx_str)
                seg_idx = batch_start + idx
                if seg_idx >= len(reviewed):
                    continue
                improved = review.get("improved", "")
                changed = review.get("changed", False)
                reason = review.get("reason", "")
                if changed and improved and improved != reviewed[seg_idx].get("target", ""):
                    before = reviewed[seg_idx].get("target", "")
                    reviewed[seg_idx]["target"] = improved
                    reviewed[seg_idx]["engineering_reviewed"] = True
                    changes.append({
                        "seg_id": reviewed[seg_idx].get("id", str(seg_idx)),
                        "before": before,
                        "after": improved,
                        "reason": reason,
                    })
            except (ValueError, IndexError, KeyError):
                continue

    log.info("Engineering review complete: %d/%d segments improved", len(changes), len(segments))
    return reviewed, changes


def compute_consistency_score(segments: list[dict]) -> int:
    """
    Compute a consistency score (0-100) based on term reuse consistency.

    Looks for cases where the same source term is translated differently
    across segments — a sign of inconsistency.
    """
    # Build source_term → list of target translations
    term_map: dict[str, list[str]] = {}
    for seg in segments:
        src = seg.get("source", "").strip().lower()
        tgt = seg.get("target", "").strip()
        if not src or not tgt or len(src) < 3:
            continue
        # Extract significant words (≥5 chars) from source
        words = [w for w in re.findall(r'\b[a-z]{5,}\b', src)]
        for word in words[:3]:  # limit per segment
            if word not in term_map:
                term_map[word] = []
            # Find corresponding target word region
            term_map[word].append(tgt[:80])

    if not term_map:
        return 100

    inconsistent = 0
    total = 0
    for term, translations in term_map.items():
        if len(translations) < 2:
            continue
        total += 1
        # Check if translations are similar enough
        unique = set(t[:40] for t in translations)
        if len(unique) > len(translations) * 0.4:
            inconsistent += 1

    if total == 0:
        return 100

    consistency = max(0, 100 - int((inconsistent / total) * 60))
    return consistency
