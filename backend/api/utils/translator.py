"""
Translation pipeline for the Professional Translation Studio.

Pipeline:
  1. Load custom dictionary for the user
  2. Check translation memory — exact hash matches reused immediately
  3. Send untranslated segments to GPT-4o in batches (technical Arabic prompt)
  4. Save new translations to translation memory
  5. Run quality checker on all translated segments
  6. Return segments with target text + quality metadata

Uses protected placeholders for custom-dictionary terms so GPT
does not alter them.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import time
import uuid
from typing import Any, AsyncGenerator

from sqlalchemy.orm import Session

from api.db.models import TranslationSegment, CustomDictionaryEntry
from api.languages import SUPPORTED_LANGUAGES

# ── Already-in-target-language detection ──────────────────────────────────────
# Many source decks (e.g. P60 ZBx) are already ~80% Arabic because someone
# translated them unofficially before upload. Sending already-Arabic text to the
# model with a "translate English→Arabic" instruction is self-contradictory and
# the model sometimes FLIPS correct Arabic back to English (a whole slide),
# destroying good content. We detect predominantly-Arabic source and keep it
# verbatim instead of ever sending it for translation.
_ARABIC_CHAR_RE = re.compile(r"[؀-ۿݐ-ݿࢠ-ࣿﭐ-﷿ﹰ-﻿]")
_LETTER_RE = re.compile(r"[^\W\d_]", re.UNICODE)


def _is_predominantly_arabic(text: str) -> bool:
    """True if the text is mostly Arabic-script letters (already-translated content)."""
    letters = _LETTER_RE.findall(text or "")
    if len(letters) < 3:
        return False  # too short to judge (codes, numbers, single words)
    arabic = _ARABIC_CHAR_RE.findall(text or "")
    return len(arabic) >= 0.5 * len(letters)

log = logging.getLogger(__name__)

# ── Language pair display names ───────────────────────────────────────────────
# Sourced from the central language registry (api.languages) so this stays in
# sync automatically as languages are added there. Kept as a plain dict (not a
# direct re-export) so callers that do LANG_NAMES.get(code, code) keep working.

LANG_NAMES = {code: lang.name for code, lang in SUPPORTED_LANGUAGES.items()}

# ── System prompts ─────────────────────────────────────────────────────────────
# Parametric on {target_lang} (the target language's display name, e.g.
# "Arabic" / "Russian" / "French" / "Spanish") so the same templates serve
# every supported language — no per-language prompt duplication.

_SYSTEM_FORMAL = """You are a professional certified technical translator specialising in security screening,
X-ray systems, radiation physics, and electro-mechanical engineering.
Translate from {source_lang} to {target_lang}.
Style: Formal {target_lang} — use the standard formal register of {target_lang} with accepted engineering terminology.
Rules:
- Never perform literal word-for-word translation.
- Use accepted engineering and technical terminology as used in {target_lang}-language technical standards.
- Preserve all numbers, units, part numbers, model names, and codes exactly as written.
- Product names and tradenames: preserve in English or transliterate using standard {target_lang} conventions.
- Use correct {target_lang} punctuation, typography, and (where applicable) text-direction conventions.
- Keep-English toggle = {keep_english}: if True, leave English technical terms (component names, acronyms) in English.
- Return ONLY a valid JSON object with a "translations" key mapping index (string) → translated text.
- Do NOT add any commentary, explanation, or text outside the JSON."""

_SYSTEM_TECHNICAL = """You are a senior technical translator at a professional X-ray security and engineering bureau.
Translate from {source_lang} to {target_lang}.
Style: Technical {target_lang} — concise, precise engineering language used in {target_lang} technical manuals and standards.
Use the exact {target_lang} terminology used in IEC, ISO, and IEEE {target_lang} translations.
Domains covered: X-ray security screening, radiation physics, detector electronics,
mechanical engineering, electrical engineering, AI/ML, industrial maintenance, aviation security, nuclear security.
Rules:
- Never use overly literary or colloquial {target_lang} — use professional technical register only.
- Preserve all numbers, units, codes, model numbers, part numbers, serial numbers, and software versions unchanged.
- Never translate product names, brand names, abbreviations, or device identifiers unless an explicit verified glossary mapping is provided.
- Abbreviations: preserve in English followed by the {target_lang} equivalent in parentheses on first use.
- Follow glossary terms consistently across the whole document; do not invent alternate variants.
- Use correct {target_lang} punctuation, typography, accents/diacritics, and (where applicable) text-direction conventions.
- Keep-English toggle = {keep_english}: if True, leave well-known English technical terms in English.
- Return ONLY a valid JSON object with a "translations" key mapping index (string) → translated text.
- Do NOT add any commentary outside the JSON."""

_SYSTEM_BILINGUAL = """You are a bilingual technical documentation specialist.
Translate from {source_lang} to {target_lang} producing bilingual output.
Style: Each translated segment should appear as: [{target_lang} translation] (English original)
The English original is preserved in parentheses after the {target_lang} translation for maximum clarity in bilingual documents.
For very short terms (single words or acronyms), just provide the {target_lang} translation.
Rules:
- Preserve all numbers, units, codes, and part numbers unchanged.
- Use professional technical {target_lang} terminology and correct {target_lang} typography.
- Return ONLY a valid JSON object with a "translations" key mapping index (string) → translated text.
- Do NOT add any commentary outside the JSON."""

_SYSTEM_PROMPTS = {
    "formal":    _SYSTEM_FORMAL,
    "technical": _SYSTEM_TECHNICAL,
    "bilingual": _SYSTEM_BILINGUAL,
}

# ── Glossary helpers ───────────────────────────────────────────────────────────

_PLACEHOLDER_RE = re.compile(r"__GLOSSARY_(\d+)__")


def _build_glossary(
    db: Session,
    user_id: str | None,
    source_lang: str,
    target_lang: str,
) -> dict[str, str]:
    """
    Load custom dictionary entries for this user.

    Includes:
    - Personal entries (user_id == caller's user_id)
    - Shared/system entries (user_id IS NULL)

    Always applies the ownership filter regardless of whether user_id is
    None (anonymous) or a real string.  When user_id is None the filter
    simplifies to user_id IS NULL — only shared entries are returned,
    which is the correct anonymous policy.
    """
    entries = (
        db.query(CustomDictionaryEntry)
        .filter(
            CustomDictionaryEntry.source_lang == source_lang,
            CustomDictionaryEntry.target_lang == target_lang,
            (CustomDictionaryEntry.user_id == user_id) |
            (CustomDictionaryEntry.user_id.is_(None)),
        )
        .all()
    )
    return {e.source_term: e.target_term for e in entries}


def _inject_glossary(text: str, glossary: dict[str, str]) -> tuple[str, dict[str, str]]:
    """
    Replace glossary terms in text with __GLOSSARY_N__ placeholders.
    Returns (modified_text, placeholder_map).
    Sort by length descending to match longest terms first.
    """
    placeholder_map: dict[str, str] = {}
    modified = text
    counter = 0
    for source_term in sorted(glossary.keys(), key=len, reverse=True):
        target_term = glossary[source_term]
        # Case-insensitive whole-word match
        pattern = re.compile(r"\b" + re.escape(source_term) + r"\b", re.IGNORECASE)
        if pattern.search(modified):
            ph = f"__GLOSSARY_{counter}__"
            placeholder_map[ph] = target_term
            modified = pattern.sub(ph, modified)
            counter += 1
    return modified, placeholder_map


def _restore_glossary(translated: str, placeholder_map: dict[str, str]) -> str:
    """Replace __GLOSSARY_N__ placeholders back with target terms."""
    for ph, target in placeholder_map.items():
        translated = translated.replace(ph, target)
    return translated


# ── Translation memory helpers ─────────────────────────────────────────────────

def _source_hash(text: str) -> str:
    """Normalise and hash source text for memory lookup."""
    normalised = " ".join(text.lower().split())
    return hashlib.sha256(normalised.encode()).hexdigest()


def _check_memory(
    db: Session,
    user_id: str | None,
    text: str,
    source_lang: str,
    target_lang: str,
) -> tuple[str, bool] | tuple[None, None]:
    """
    Return (cached_translation, is_shared) if an exact match exists in translation memory.

    Looks up own entries (user_id == caller) OR shared entries (user_id IS NULL).
    The filter is applied unconditionally so anonymous users (user_id=None) only
    see shared entries, not all rows.

    Returns (None, None) when no match is found.
    Returns (target_text, True) when the hit came from a shared (team) entry.
    Returns (target_text, False) when the hit came from the caller's own entry.
    """
    h = _source_hash(text)
    entry = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.source_hash == h,
            TranslationSegment.source_lang == source_lang,
            TranslationSegment.target_lang == target_lang,
            (TranslationSegment.user_id == user_id) |
            (TranslationSegment.user_id.is_(None)),
        )
        .first()
    )
    if entry:
        entry.use_count += 1
        db.commit()
        return entry.target_text, entry.user_id is None
    return None, None


def _check_memory_bulk(
    db: Session,
    user_id: str | None,
    segments: list[dict],
    source_lang: str,
    target_lang: str,
) -> tuple[list[dict], int]:
    """
    Single-query bulk translation memory lookup.

    Replaces the N+1 per-segment _check_memory loop:
      Before: N SELECT queries + N db.commit() calls (one per hit)
      After:  1 SELECT query  + 1 db.commit()  (for all use_count increments)

    Returns:
        (to_translate, memory_hits_count)
        Segments are modified in-place: target/memory_match/team_match set on hits.
    """
    if not segments:
        return [], 0

    # Initialise all segment metadata fields (replaces the old per-seg loop)
    for seg in segments:
        seg["target"] = ""
        seg["memory_match"] = False
        seg["flagged"] = False
        seg["flag_reason"] = ""
        seg["edited"] = False

    # Hash all sources in Python — pure CPU, no I/O
    hashes: list[str] = [_source_hash(seg["source"]) for seg in segments]
    unique_hashes = list(set(hashes))

    # ── Single DB query for all hashes ────────────────────────────────────────
    try:
        entries = (
            db.query(TranslationSegment)
            .filter(
                TranslationSegment.source_hash.in_(unique_hashes),
                TranslationSegment.source_lang == source_lang,
                TranslationSegment.target_lang == target_lang,
                (TranslationSegment.user_id == user_id)
                | (TranslationSegment.user_id.is_(None)),
            )
            .all()
        )
    except Exception as exc:
        log.warning("Bulk memory lookup failed, falling back to empty: %s", exc)
        return segments, 0

    # Build hash → best entry map (prefer caller's own entry over shared/NULL)
    best: dict[str, TranslationSegment] = {}
    for entry in entries:
        h = entry.source_hash
        prev = best.get(h)
        if prev is None or (entry.user_id == user_id and prev.user_id is None):
            best[h] = entry

    # Apply matches in original segment order
    hit_entry_ids: set[int] = set()
    to_translate: list[dict] = []
    memory_hits = 0

    for seg, h in zip(segments, hashes):
        entry = best.get(h)
        if entry is not None:
            seg["target"] = entry.target_text
            seg["memory_match"] = True
            seg["team_match"] = entry.user_id is None
            memory_hits += 1
            hit_entry_ids.add(id(entry))
        else:
            to_translate.append(seg)

    # ── Bulk use_count increment + single commit ───────────────────────────────
    if hit_entry_ids:
        for entry in entries:
            if id(entry) in hit_entry_ids:
                entry.use_count = (entry.use_count or 0) + 1
        try:
            db.commit()
        except Exception as commit_exc:
            log.warning("use_count bulk commit failed (non-fatal): %s", commit_exc)
            db.rollback()

    return to_translate, memory_hits


def _save_to_memory(
    db: Session,
    user_id: str | None,
    source_text: str,
    target_text: str,
    source_lang: str,
    target_lang: str,
) -> None:
    """
    Save or update a segment in translation memory.

    The existence check is scoped to the caller's user_id so that:
    - Each user maintains their own independent memory entry for a given source.
    - Updating one user's memory never touches another user's entry.
    - Shared entries (user_id IS NULL) are never modified by personal saves.
    """
    h = _source_hash(source_text)
    # Scope the lookup to this user's own entries only (not shared)
    existing = (
        db.query(TranslationSegment)
        .filter(
            TranslationSegment.source_hash == h,
            TranslationSegment.source_lang == source_lang,
            TranslationSegment.target_lang == target_lang,
            TranslationSegment.user_id == user_id,   # strict owner match, not OR NULL
        )
        .first()
    )
    if existing:
        existing.target_text = target_text
        existing.use_count += 1
    else:
        db.add(TranslationSegment(
            user_id=user_id,
            source_hash=h,
            source_text=source_text,
            target_text=target_text,
            source_lang=source_lang,
            target_lang=target_lang,
        ))
    db.commit()


# ── GPT translation ────────────────────────────────────────────────────────────

# Billing safety: at most ONE automatic retry for transient API failures.
_MAX_BATCH_RETRIES = 2   # attempts per batch (initial + 1 retry)
_RETRY_BASE_SECS   = 8   # first retry wait; doubles each time


def _model() -> str:
    """Translation model — administrator-configurable, never auto-switched.

    Default: gpt-4o-mini (≈16× cheaper than gpt-4o for segment translation).
    Engineering review always uses gpt-4o regardless of this setting.
    Override: OPENAI_TRANSLATION_MODEL=gpt-4o to restore the original.
    """
    return (os.environ.get("OPENAI_TRANSLATION_MODEL") or "gpt-4o-mini").strip() or "gpt-4o-mini"


async def _translate_batch(
    segments_batch: list[dict],
    system_prompt: str,
    client,
    model_name: str | None = None,
    usage: dict | None = None,
) -> dict[str, str]:
    """
    Translate a batch of segments in one GPT call.
    Returns {batch_idx: translated_text}.

    Retries on RateLimitError / ServiceUnavailableError with exponential
    backoff.  Other unrecoverable errors are re-raised so the caller can
    surface them to the SSE stream rather than silently returning {}.
    """
    import asyncio
    try:
        from openai import RateLimitError as _RateLimitError
        from openai import APIStatusError as _APIStatusError
    except ImportError:
        _RateLimitError = Exception
        _APIStatusError = Exception

    input_map: dict[str, str] = {
        seg["_batch_idx"]: seg["_text_to_translate"]
        for seg in segments_batch
    }

    user_msg = (
        "Translate every value in the JSON object below.\n"
        "Return ONLY a valid JSON object with a single key called \"translations\" "
        "whose value maps each input key to its translated text.\n"
        "Preserve \\n line breaks within values exactly as they appear.\n"
        "Do NOT add explanations, comments, or keys other than \"translations\".\n\n"
        "Input:\n"
        + json.dumps(input_map, ensure_ascii=False)
    )

    last_exc: Exception | None = None
    for attempt in range(_MAX_BATCH_RETRIES):
        raw = "{}"
        try:
            from api.utils.rate_limiter import acquire_slot
            await acquire_slot(model_name or _model())
            resp = await client.chat.completions.create(
                model=(model_name or _model()),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_msg},
                ],
                max_completion_tokens=16000,
                temperature=0.1,
                response_format={"type": "json_object"},
            )
            raw = resp.choices[0].message.content or "{}"
            # Token accounting for cost tracking (best-effort, never fatal)
            try:
                if usage is not None and getattr(resp, "usage", None) is not None:
                    _in  = resp.usage.prompt_tokens or 0
                    _out = resp.usage.completion_tokens or 0
                    usage["in"]  = usage.get("in",  0) + _in
                    usage["out"] = usage.get("out", 0) + _out
                    # Per-stage translate tracking
                    usage["translate_in"]  = usage.get("translate_in",  0) + _in
                    usage["translate_out"] = usage.get("translate_out", 0) + _out
                    usage["translate_calls"] = usage.get("translate_calls", 0) + 1
                    # Prompt-caching savings (OpenAI returns cached_tokens in prompt_tokens_details)
                    _cached = 0
                    _details = getattr(resp.usage, "prompt_tokens_details", None)
                    if _details:
                        _cached = getattr(_details, "cached_tokens", 0) or 0
                    usage["translate_cached"] = usage.get("translate_cached", 0) + _cached
                    if attempt:
                        usage["retries"] = usage.get("retries", 0) + attempt
            except Exception:
                pass
            data = json.loads(raw)

        except json.JSONDecodeError as e:
            log.error("GPT response JSON parse error: %s | raw=%s", e, raw[:300])
            # Attempt partial recovery
            try:
                m = re.search(r'\{.*\}', raw, re.DOTALL)
                if m:
                    data = json.loads(m.group())
                else:
                    return {}
            except Exception:
                return {}

        except _RateLimitError as e:
            last_exc = e
            wait = _RETRY_BASE_SECS * (2 ** attempt)
            log.warning(
                "Rate limit hit (attempt %d/%d) — waiting %ds before retry. Details: %s",
                attempt + 1, _MAX_BATCH_RETRIES, wait, e,
            )
            if attempt < _MAX_BATCH_RETRIES - 1:
                await asyncio.sleep(wait)
                continue
            # All retries exhausted — re-raise so the caller can surface it
            raise RuntimeError(
                f"Rate limit persisted after {_MAX_BATCH_RETRIES} attempts. "
                f"Wait a minute and try again. ({e})"
            ) from e

        except Exception as e:
            # ServiceUnavailable, timeout, network error — retry with backoff
            err_name = type(e).__name__
            retriable = any(kw in err_name for kw in ("ServiceUnavailable", "Timeout", "Connection", "APIError"))
            last_exc = e
            if retriable and attempt < _MAX_BATCH_RETRIES - 1:
                wait = _RETRY_BASE_SECS * (2 ** attempt)
                log.warning("Retriable error %s (attempt %d) — waiting %ds: %s", err_name, attempt + 1, wait, e)
                await asyncio.sleep(wait)
                continue
            # Non-retriable or out of retries — re-raise
            log.error("GPT translation batch failed (non-retriable): %s: %s", err_name, e)
            raise

        # ── Success path ───────────────────────────────────────────────────────
        if "translations" in data and isinstance(data["translations"], dict):
            result = data["translations"]
        else:
            result = {k: v for k, v in data.items() if isinstance(v, str)}

        if not result:
            log.warning("Empty translation result for batch indices %s", list(input_map.keys()))

        log.debug("Batch translated %d/%d segments", len(result), len(segments_batch))
        return result

    # Should not be reached, but satisfy type checker
    raise RuntimeError(f"Batch translation failed after {_MAX_BATCH_RETRIES} attempts: {last_exc}")


# ── Quality checker ────────────────────────────────────────────────────────────

def _check_quality(segments: list[dict]) -> tuple[int, list[dict]]:
    """
    Run quality checks on translated segments.
    Returns (quality_score 0-100, list of issue dicts).
    """
    issues = []
    total = len(segments)
    if total == 0:
        return 100, []

    flagged_count = 0

    for seg in segments:
        source = seg.get("source", "")
        target = seg.get("target", "")

        if not target or not target.strip():
            issues.append({
                "seg_id": seg["id"],
                "type": "missing_translation",
                "severity": "error",
                "message": f"Segment not translated: \"{source[:60]}...\"" if len(source) > 60 else f"Segment not translated: \"{source}\"",
            })
            seg["flagged"] = True
            seg["flag_reason"] = "missing_translation"
            flagged_count += 1
            continue

        # Check numbers preserved
        source_nums = re.findall(r"\b\d+(?:[.,]\d+)*\b", source)
        target_nums = re.findall(r"\b\d+(?:[.,]\d+)*\b", target)
        source_set = set(source_nums)
        target_set = set(target_nums)
        missing_nums = source_set - target_set
        if missing_nums:
            issues.append({
                "seg_id": seg["id"],
                "type": "number_mismatch",
                "severity": "warning",
                "message": f"Numbers missing in translation: {', '.join(missing_nums)}",
            })
            if not seg.get("flagged"):
                seg["flagged"] = True
                seg["flag_reason"] = "number_mismatch"
            flagged_count += 1

        # Check units preserved
        source_units = re.findall(r"\b\d+\s*(?:mm|cm|m|km|kg|g|mg|kV|V|mA|A|W|kW|MHz|GHz|°C|°F|bar|psi|rpm|dB|ms|μs|ns)\b", source)
        target_units = re.findall(r"\b\d+\s*(?:mm|cm|m|km|kg|g|mg|kV|V|mA|A|W|kW|MHz|GHz|°C|°F|bar|psi|rpm|dB|ms|μs|ns)\b", target)
        if source_units and not target_units:
            issues.append({
                "seg_id": seg["id"],
                "type": "unit_mismatch",
                "severity": "warning",
                "message": f"Units may be missing in translation",
            })

    # Score: start at 100, deduct per issue
    error_count = sum(1 for i in issues if i["severity"] == "error")
    warning_count = sum(1 for i in issues if i["severity"] == "warning")
    score = max(0, 100 - (error_count * 10) - (warning_count * 3))

    return score, issues


# ── Main pipeline ──────────────────────────────────────────────────────────────

BATCH_SIZE = 30          # segments per GPT call — 30 fits easily within token budget
_MAX_CONCURRENT_BATCHES = 5  # parallel OpenAI calls; stays well under rate limits


async def translate_segments(
    segments: list[dict],
    source_lang: str,
    target_lang: str,
    style: str,
    keep_english_terms: bool,
    transliterate_names: bool,
    db: Session,
    user_id: str | None,
    client,
    progress_callback=None,
    batch_save_callback=None,
    provider=None,
    model_name: str | None = None,
    usage: dict | None = None,
    cost_ceiling_usd: float | None = None,
) -> tuple[list[dict], int, list[dict]]:
    """
    Full translation pipeline.

    Args:
        segments:           extracted document segments
        source_lang:        e.g. "en"
        target_lang:        e.g. "ar"
        style:              "formal" | "technical" | "bilingual"
        keep_english_terms: if True, leave technical terms in English
        transliterate_names: transliterate proper nouns
        db:                 database session
        user_id:            current user (for per-user memory/dictionary)
        client:             async OpenAI client
        progress_callback:  async callable(step, total, message)
        provider:           optional TranslationProvider instance; when set and
                            it is NOT the OpenAI provider, its translate_batch()
                            is called instead of the internal GPT-4o path.
                            OpenAI provider still uses the internal path (with
                            glossary/retry/JSON-response-format support).

    Returns:
        (translated_segments, quality_score, quality_issues, provider_used, stats)
    """
    source_lang_name = LANG_NAMES.get(source_lang, source_lang)
    target_lang_name = LANG_NAMES.get(target_lang, target_lang)

    _t_job_start = time.perf_counter()

    # ── Step 1: Load glossary ──────────────────────────────────────────────────
    _t0 = time.perf_counter()
    if progress_callback:
        await progress_callback(1, 6, "Loading custom terminology dictionary…")

    # Run in a thread so the event loop (and SSE drain loop) stays responsive
    glossary = await asyncio.to_thread(_build_glossary, db, user_id, source_lang, target_lang)
    _t_glossary = round(time.perf_counter() - _t0, 3)
    log.info("Loaded %d glossary entries [%.3fs]", len(glossary), _t_glossary)

    # ── Step 2: Check translation memory (bulk — 1 query for all segments) ────
    _t0 = time.perf_counter()
    if progress_callback:
        await progress_callback(2, 6, f"Checking translation memory for {len(segments)} segments…")

    # Single bulk query in a thread — keeps the event loop free during the DB round-trip
    # (previously ~979ms blocking; index ix_ts_lookup drops this to ~5ms)
    to_translate, memory_hits = await asyncio.to_thread(
        _check_memory_bulk, db, user_id, segments, source_lang, target_lang
    )

    _t_memory = round(time.perf_counter() - _t0, 3)
    log.info(
        "Memory hits: %d/%d, to translate: %d [bulk lookup: %.3fs]",
        memory_hits, len(segments), len(to_translate), _t_memory,
    )
    if progress_callback:
        await progress_callback(
            2, 6,
            f"Translation memory: {memory_hits}/{len(segments)} hits "
            f"({_t_memory:.1f}s · 1 query)",
        )

    # ── Stage 2b: Skip source that is ALREADY in the target language ───────────
    # Guard against destroying pre-existing Arabic. If the target is Arabic and a
    # segment's source is already predominantly Arabic, keep it verbatim and never
    # send it to the model (which, given a contradictory "EN→AR" instruction, may
    # flip good Arabic back to English). Saves cost and prevents corruption.
    if (target_lang or "").lower() == "ar":
        _kept: list[dict] = []
        _already_target = 0
        for seg in to_translate:
            if _is_predominantly_arabic(seg.get("source", "")):
                seg["target"] = seg["source"]
                seg["already_target_lang"] = True
                _already_target += 1
            else:
                _kept.append(seg)
        to_translate = _kept
        if _already_target:
            log.info(
                "Already-Arabic source: %d segment(s) kept as-is (not re-translated)",
                _already_target,
            )
            if progress_callback:
                await progress_callback(
                    2, 6,
                    f"Kept {_already_target} already-Arabic segment(s) unchanged (no re-translation)",
                )
            if usage is not None:
                usage["already_target_lang"] = usage.get("already_target_lang", 0) + _already_target

    # ── Stage 3: Local-rules bypass ────────────────────────────────────────────
    # Resolve segments whose full source text exactly matches a custom-dictionary
    # entry — without calling any translation API.  Typical hits: short labels,
    # table headings, menu items, safety-warning boilerplate.
    # The glossary dict is already loaded above (source_term → target_term).
    local_rules_hits = 0
    _remaining: list[dict] = []
    for seg in to_translate:
        src_stripped = seg["source"].strip()
        # 1. Exact match
        direct = glossary.get(src_stripped)
        if direct is None:
            # 2. Case-insensitive fallback
            src_lower = src_stripped.lower()
            for k, v in glossary.items():
                if k.lower() == src_lower:
                    direct = v
                    break
        if direct is not None:
            seg["target"] = direct
            seg["local_rules_match"] = True
            local_rules_hits += 1
            # Promote to memory so future runs get a free memory hit
            try:
                _save_to_memory(db, user_id, src_stripped, direct, source_lang, target_lang)
            except Exception:
                pass
        else:
            _remaining.append(seg)
    to_translate = _remaining
    if local_rules_hits:
        log.info("Local-rules hits: %d, remaining to translate: %d", local_rules_hits, len(to_translate))
        if progress_callback:
            await progress_callback(
                3, 6,
                f"Local rules: {local_rules_hits} segment(s) resolved from glossary (no API call)",
            )
    if usage is not None:
        usage["local_rules"] = usage.get("local_rules", 0) + local_rules_hits

    # ── Step 3: Build system prompt ────────────────────────────────────────────
    if progress_callback:
        await progress_callback(3, 6, f"Preparing translation engine ({style} style)…")

    prompt_template = _SYSTEM_PROMPTS.get(style, _SYSTEM_TECHNICAL)
    system_prompt = prompt_template.format(
        source_lang=source_lang_name,
        target_lang=target_lang_name,
        keep_english=keep_english_terms,
    )
    if glossary:
        gloss_note = "\n\nMANDATORY TERMINOLOGY (always use these exact translations):\n"
        gloss_note += "\n".join(f"  {k} → {v}" for k, v in list(glossary.items())[:50])
        system_prompt += gloss_note

    # ── Step 4: Translation in batches ────────────────────────────────────────
    # Determine whether to use an external provider or the internal GPT-4o path.
    # The internal path retains full glossary placeholder, JSON response format,
    # and retry logic. External providers receive plain text and return plain text.
    use_external_provider = (
        provider is not None
        and getattr(provider, "provider_id", "openai") != "openai"
        and getattr(provider, "is_configured", False)
    )
    provider_display = (
        getattr(provider, "display_name", "GPT-4o") if provider else "GPT-4o"
    )

    # Track the provider that actually executed translation (may differ from
    # the requested provider if it falls back to GPT-4o mid-run).
    # We track two states: "all external", "mixed" (some batches fell back),
    # "all fallback" (external was not usable at all).
    _batches_external = 0
    _batches_fallback = 0
    _batches_ceiling = 0

    if progress_callback:
        await progress_callback(
            4, 6,
            f"Translating {len(to_translate)} segments via {provider_display}…",
        )

    # Build batch data — inject glossary placeholders (used by both paths)
    for i, seg in enumerate(to_translate):
        injected, ph_map = _inject_glossary(seg["source"], glossary)
        seg["_text_to_translate"] = injected
        seg["_ph_map"] = ph_map
        seg["_batch_idx"] = str(i)

    # Billing safety: identical source texts are translated ONCE per job and
    # the result reused for duplicates (cross-job reuse is handled by the
    # translation memory above).
    _first_by_text: dict[str, dict] = {}
    unique_to_translate: list[dict] = []
    for seg in to_translate:
        key = seg["_text_to_translate"]
        first = _first_by_text.get(key)
        if first is None:
            _first_by_text[key] = seg
            unique_to_translate.append(seg)
        else:
            seg["_dup_of"] = first["_batch_idx"]
    if len(unique_to_translate) < len(to_translate):
        log.info(
            "In-job dedup: %d duplicate segments reuse %d unique translations",
            len(to_translate) - len(unique_to_translate), len(unique_to_translate),
        )

    batches = [unique_to_translate[i:i+BATCH_SIZE] for i in range(0, len(unique_to_translate), BATCH_SIZE)]
    translated_count = 0
    batch_errors: list[str] = []
    # Per-segment accounting: initial attempt is counted as 1 for all unique segments.
    segment_attempts: dict[str, int] = {seg["_batch_idx"]: 1 for seg in unique_to_translate}
    retried_segment_ids: set[str] = set()
    unresolved_reason: dict[str, str] = {}

    import asyncio as _asyncio

    if progress_callback:
        await progress_callback(
            4, 6,
            f"Translating {len(to_translate)} segments via {provider_display} "
            f"({len(batches)} batches, up to {_MAX_CONCURRENT_BATCHES} parallel)…",
        )

    # ── Concurrent batch execution ─────────────────────────────────────────────
    # All batches run in parallel, capped at _MAX_CONCURRENT_BATCHES simultaneous
    # OpenAI calls.  This replaces the old sequential loop + 1.5 s sleep, cutting
    # wall-clock time from O(N_batches) → O(ceil(N_batches / concurrency)).
    sem = _asyncio.Semaphore(_MAX_CONCURRENT_BATCHES)

    async def _run_batch(batch_num: int, batch: list) -> tuple[int, dict, str, str | None]:
        """Run one translation batch under the semaphore.

        Returns (batch_num, result_dict, path) where path is
        'external' | 'fallback' | 'error'.
        """
        async with sem:
            # Hard stop: once the job's accumulated cost reaches the ceiling,
            # queued batches refuse to start (never silently exceeded).
            if cost_ceiling_usd is not None and usage is not None:
                from api.utils.cost_guard import est_cost_usd as _est_cost
                if _est_cost(usage.get("in", 0), usage.get("out", 0), (model_name or _model())) >= cost_ceiling_usd:
                    return batch_num, {}, "cost_ceiling", "cost_ceiling_reached"
            if use_external_provider:
                try:
                    texts = [seg["_text_to_translate"] for seg in batch]
                    translations = await provider.translate_batch(
                        texts=texts,
                        source_lang=source_lang,
                        target_lang=target_lang,
                    )
                    # External providers return per-batch local indices; remap to
                    # global _batch_idx so the merge step works uniformly.
                    result = {
                        batch[i]["_batch_idx"]: translations[i]
                        for i in range(len(batch))
                        if i < len(translations)
                    }
                    # Track character count for external-provider billing (e.g. DeepL free tier)
                    if usage is not None:
                        usage["chars"] = usage.get("chars", 0) + sum(len(t) for t in texts)
                    log.info(
                        "Provider %s translated %d/%d segments in batch %d",
                        provider_display, len(result), len(batch), batch_num,
                    )
                    return batch_num, result, "external", None
                except Exception as exc:
                    log.warning(
                        "Falling back to GPT-4o for batch %d after %s failure: %s",
                        batch_num, provider_display, exc,
                    )
                    batch_errors.append(f"Batch {batch_num + 1}: {exc}")
                    try:
                        result = await _translate_batch(batch, system_prompt, client, model_name, usage)
                        return batch_num, result, "fallback", None
                    except Exception as fallback_exc:
                        log.error("GPT-4o fallback also failed for batch %d: %s", batch_num, fallback_exc)
                        return batch_num, {}, "error", str(fallback_exc)
            else:
                try:
                    result = await _translate_batch(batch, system_prompt, client, model_name, usage)
                    return batch_num, result, "fallback", None
                except Exception as exc:
                    log.error("Batch %d translation error: %s", batch_num, exc)
                    batch_errors.append(f"Batch {batch_num + 1}: {exc}")
                    return batch_num, {}, "error", str(exc)

    batch_outcomes: list[tuple[int, dict, str, str | None]] = await _asyncio.gather(
        *[_run_batch(i, b) for i, b in enumerate(batches)]
    )

    # ── Merge results back into segments (in original order) ──────────────────
    unresolved_segments: list[dict] = []
    for batch_num, batch_result, path, reason in sorted(batch_outcomes, key=lambda x: x[0]):
        if path == "external":
            _batches_external += 1
        elif path == "fallback":
            _batches_fallback += 1
        elif path == "cost_ceiling":
            _batches_ceiling += 1

        for seg in batches[batch_num]:
            translated_text = batch_result.get(seg["_batch_idx"])
            if translated_text:
                restored = _restore_glossary(translated_text, seg.get("_ph_map", {}))
                seg["target"] = restored
                translated_count += 1

                # Save this segment to translation memory (best-effort)
                try:
                    _save_to_memory(
                        db, user_id,
                        seg["source"], seg["target"],
                        source_lang, target_lang,
                    )
                except Exception as mem_exc:
                    log.warning("Memory save failed (non-fatal): %s", mem_exc)
            else:
                unresolved_segments.append(seg)
                if path == "error":
                    unresolved_reason[seg["_batch_idx"]] = reason or "translation_batch_error"
                elif path == "cost_ceiling":
                    unresolved_reason[seg["_batch_idx"]] = "cost_ceiling_reached"
                else:
                    unresolved_reason[seg["_batch_idx"]] = "empty_or_missing_provider_response"

    async def _retry_untranslated_segments(initial_unresolved: list[dict]) -> None:
        """Retry unresolved segments once, splitting into smaller batches when needed."""
        nonlocal translated_count
        queue: list[tuple[list[dict], bool]] = []
        pending_initial = [s for s in initial_unresolved if not s.get("target")]
        if pending_initial:
            queue.append((pending_initial, False))

        while queue:
            group, was_split = queue.pop(0)
            group = [s for s in group if not s.get("target")]
            if not group:
                continue

            # First retry for unresolved segments should use smaller batches
            # to avoid partial/empty provider JSON responses on large payloads.
            if len(group) > 1 and not was_split:
                split_size = max(1, len(group) // 2)
                for i in range(0, len(group), split_size):
                    queue.append((group[i:i + split_size], True))
                continue

            # Retry each unresolved segment only once (attempt #2).
            retry_group: list[dict] = []
            for seg in group:
                idx = seg["_batch_idx"]
                attempts = segment_attempts.get(idx, 1)
                if attempts >= 2:
                    continue
                segment_attempts[idx] = attempts + 1
                retried_segment_ids.add(idx)
                retry_group.append(seg)

            if not retry_group:
                continue

            _, retry_result, retry_path, retry_reason = await _run_batch(-1, retry_group)

            still_untranslated: list[dict] = []
            for seg in retry_group:
                translated_text = retry_result.get(seg["_batch_idx"])
                if translated_text:
                    restored = _restore_glossary(translated_text, seg.get("_ph_map", {}))
                    seg["target"] = restored
                    translated_count += 1
                    try:
                        _save_to_memory(
                            db, user_id,
                            seg["source"], seg["target"],
                            source_lang, target_lang,
                        )
                    except Exception as mem_exc:
                        log.warning("Memory save failed (non-fatal): %s", mem_exc)
                else:
                    still_untranslated.append(seg)
                    if retry_path == "error":
                        unresolved_reason[seg["_batch_idx"]] = retry_reason or "translation_retry_error"
                    elif retry_path == "cost_ceiling":
                        unresolved_reason[seg["_batch_idx"]] = "cost_ceiling_reached"
                    else:
                        unresolved_reason[seg["_batch_idx"]] = "empty_or_missing_provider_response_after_retry"

    if unresolved_segments:
        await _retry_untranslated_segments(unresolved_segments)

    # Reuse translations for in-job duplicate segments (translated once above)
    _by_idx = {seg["_batch_idx"]: seg for seg in unique_to_translate}
    for seg in to_translate:
        dup_idx = seg.get("_dup_of")
        if dup_idx and not seg["target"]:
            first = _by_idx.get(dup_idx)
            if first is not None and first["target"]:
                seg["target"] = first["target"]
                translated_count += 1

    # Log any segment that still has no translation after retry logic.
    failed_segments: list[dict[str, str]] = []
    for seg in unique_to_translate:
        if seg.get("target", "").strip():
            continue
        idx = seg["_batch_idx"]
        reason = unresolved_reason.get(idx, "translation_failed_after_retry")
        failed_segments.append({
            "id": str(seg.get("id") or idx),
            "batch_idx": idx,
            "reason": reason,
            "source": (seg.get("source") or "")[:160],
        })
        log.warning(
            "Untranslated segment: id=%s batch_idx=%s reason=%s source=%s",
            seg.get("id"),
            idx,
            reason,
            (seg.get("source") or "")[:160],
        )

    # Persist all translated segments once after the concurrent run completes
    if batch_save_callback:
        try:
            await batch_save_callback(segments)
        except Exception as cb_exc:
            log.warning("batch_save_callback error (non-fatal): %s", cb_exc)

    # Cost ceiling reached mid-job: partial work is saved above, then the job
    # stops loudly — it must never continue or silently exceed the limit.
    if _batches_ceiling:
        raise RuntimeError(
            f"Job cost ceiling reached (MAX_COST_PER_JOB_USD) — translation "
            f"stopped after {translated_count}/{len(to_translate)} segments. "
            f"Partial translations are saved; raise the limit to continue."
        )

    if batch_errors:
        log.error(
            "Translation had %d batch error(s): %s",
            len(batch_errors), " | ".join(batch_errors),
        )
        if translated_count == 0 and batch_errors:
            raise RuntimeError(
                f"All translation batches failed — no segments were translated. "
                f"First error: {batch_errors[0]}"
            )

    retry_count = len(retried_segment_ids)
    failed_count = len(failed_segments)
    if progress_callback:
        await progress_callback(
            4,
            6,
            f"Segment coverage: translated={translated_count}, retried={retry_count}, failed={failed_count}",
        )

    # Clean up temporary keys
    for seg in segments:
        for k in ("_text_to_translate", "_ph_map", "_batch_idx", "_dup_of"):
            seg.pop(k, None)

    # ── Step 5: Quality check ─────────────────────────────────────────────────
    _t0 = time.perf_counter()
    if progress_callback:
        await progress_callback(5, 6, "Running quality control checks…")

    quality_score, quality_issues = _check_quality(segments)
    _t_quality = round(time.perf_counter() - _t0, 3)

    # ── Determine effective provider (for accurate attribution) ───────────────
    # The effective provider is what actually ran the translation, which may
    # differ from the requested provider when:
    #  a) provider was not configured (use_external_provider=False)
    #  b) external provider failed on some/all batches and GPT-4o was the fallback
    if use_external_provider and _batches_external > 0 and _batches_fallback == 0:
        effective_provider_display = provider_display          # pure external run
    elif use_external_provider and _batches_external > 0 and _batches_fallback > 0:
        effective_provider_display = f"{provider_display} + GPT-4o (partial fallback)"
    elif use_external_provider and _batches_external == 0:
        effective_provider_display = "GPT-4o (fallback — provider unavailable)"
    else:
        effective_provider_display = (model_name or _model())  # internal path — show actual model

    _t_total = round(time.perf_counter() - _t_job_start, 2)
    log.info(
        "Translation complete: %d translated, %d memory hits, quality=%d, issues=%d, "
        "provider=%s [total=%.2fs glossary=%.3fs memory=%.3fs quality=%.3fs]",
        translated_count, memory_hits, quality_score, len(quality_issues),
        effective_provider_display, _t_total, _t_glossary, _t_memory, _t_quality,
    )
    if failed_segments:
        log.warning(
            "Translation finished with %d failed segment(s) after retry",
            len(failed_segments),
        )

    # ── Step 6: Done ──────────────────────────────────────────────────────────
    if progress_callback:
        await progress_callback(6, 6, f"Translation complete via {effective_provider_display}.")

    stats = {
        "translated_segments": translated_count,
        "retried_segments": retry_count,
        "failed_segments": failed_count,
        "failed_details": failed_segments,
    }

    return segments, quality_score, quality_issues, effective_provider_display, stats
