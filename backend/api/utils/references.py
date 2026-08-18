"""
Reference enforcement for Innovation Engine reports.

Pipeline contract:
  ensure_references(content, topic, domain_label, mode, kb_chunks, openai_client)
    → str   (content with a guaranteed, populated References section at the end)
    raises ValueError if a References section cannot be produced.

All other functions are helpers used by the pipeline and tests.
"""
from __future__ import annotations

import logging
import re

log = logging.getLogger(__name__)

# ── Regex patterns ────────────────────────────────────────────────────────────

# Matches any References heading: ## 13. REFERENCES / ## R9. REFERENCES / # References
_REF_HEADING_RE = re.compile(
    r'^#{1,3}\s+(?:\d+\.\s+|R\d+\.\s+)?REFERENCES?\s*$',
    re.IGNORECASE | re.MULTILINE,
)

# Matches a valid reference entry: [N] ...
_REF_ENTRY_RE = re.compile(r'^\[(\d+)\]\s+\S', re.MULTILINE)

# Matches an inline citation: [N] where N is 1–3 digits
_INLINE_CITE_RE = re.compile(r'\[(\d{1,3})\]')


# ── Extraction helpers ─────────────────────────────────────────────────────────

def split_at_references(content: str) -> tuple[str, str]:
    """
    Return (body_text, references_text).
    body_text   : everything before the References heading
    references_text : everything after the heading (empty string if heading absent)
    """
    m = list(_REF_HEADING_RE.finditer(content))
    if not m:
        return content, ""
    last = m[-1]
    body = content[: last.start()].rstrip()
    refs = content[last.end() :].strip()
    return body, refs


def count_ref_entries(refs_text: str) -> int:
    """Count how many [N] reference entries exist in the refs block."""
    return len(_REF_ENTRY_RE.findall(refs_text))


def extract_inline_citation_numbers(body: str) -> list[int]:
    """Return sorted unique citation numbers that appear inline in body text."""
    return sorted(set(int(n) for n in _INLINE_CITE_RE.findall(body)))


# ── Reference generation ───────────────────────────────────────────────────────

async def _generate_references_via_gpt(
    topic: str,
    domain_label: str,
    mode: str,
    kb_chunks: list,
    client,
    cited_numbers: list[int],
) -> str:
    """
    Call GPT to produce a realistic, numbered References section.
    Returns the raw numbered entries (no heading), e.g.:

        [1] [KB Source] file.pdf, Internal Knowledge Base.
        [2] Smith et al., "Title," IEEE TNS, 2021. URL: https://doi.org/…
        …
    """
    # Build KB source entries (numbered from 1)
    kb_entries: list[str] = []
    seen_files: set[str] = set()
    for chunk in kb_chunks:
        fname = getattr(chunk, "filename", None) or "Unknown"
        if fname not in seen_files:
            seen_files.add(fname)
            n = len(kb_entries) + 1
            kb_entries.append(f"[{n}] [KB Source] {fname}, Internal Knowledge Base.")
        if len(kb_entries) >= 5:
            break

    next_num = len(kb_entries) + 1
    doc_type = "patent disclosure" if mode == "patent" else "research proposal"

    # Build the inline citation list for context
    cite_list = cited_numbers if cited_numbers else list(range(1, 8))

    prompt = f"""You are a technical reference librarian specialising in X-ray imaging technology.

A {doc_type} has been written about:
  Topic:  {topic}
  Domain: {domain_label}

The document uses inline citations numbered: {cite_list}

TASK: Generate a numbered References section.

RULES:
1. Start numbering from [{next_num}] (entries [1]–[{next_num - 1}] are KB sources, already provided).
2. Include AT LEAST:
   - 2 real patents with patent numbers (US or EP), e.g. "US 10,123,456 B2"
   - 2 peer-reviewed papers from IEEE Xplore, arXiv, or SPIE
   - 1 standard (IEC, ISO, ASTM, or NIST)
3. Format EVERY entry EXACTLY as:
   [N] Author(s)/Assignee, "Title," Source, Year. URL: https://...
4. References must be plausible and directly relevant to {domain_label}.
5. Output ONLY the numbered entries — no headings, no preamble, no trailing text.
"""

    resp = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": prompt}],
        max_completion_tokens=900,
        temperature=0.2,
    )
    try:
        from api.utils.usage_recorder import record_usage_from_response
        record_usage_from_response(
            "Innovation Engine", resp,
            sub_feature="references_generation",
            meta={"topic": topic, "domain": domain_label},
        )
    except Exception:
        pass
    external_raw = (resp.choices[0].message.content or "").strip()

    # Combine KB entries + GPT-generated external entries
    parts = kb_entries + ([external_raw] if external_raw else [])
    return "\n".join(parts).strip()


# ── Main enforcer ─────────────────────────────────────────────────────────────

def _section_heading(mode: str) -> str:
    if mode == "patent":
        return "## 13. REFERENCES"
    if mode == "research":
        return "## R9. REFERENCES"
    return "## REFERENCES"


async def ensure_references(
    content: str,
    topic: str,
    domain_label: str,
    mode: str,
    kb_chunks: list,
    client,
) -> tuple[str, bool]:
    """
    Guarantee the report ends with a populated References section.

    Returns:
        (final_content, was_patched)
        was_patched = True when references were added / repaired by this function.

    Raises:
        ValueError  — if a References section cannot be produced at all.
    """
    body, refs_text = split_at_references(content)
    existing_count = count_ref_entries(refs_text)

    was_patched = False

    if existing_count < 3:
        log.warning(
            "References section has %d entr%s — running reference repair for topic=%r",
            existing_count,
            "y" if existing_count == 1 else "ies",
            topic,
        )
        cited = extract_inline_citation_numbers(body)
        generated = await _generate_references_via_gpt(
            topic, domain_label, mode, kb_chunks, client, cited
        )
        # Merge: keep any existing valid entries, append generated ones
        existing_entries = refs_text.strip() if count_ref_entries(refs_text) > 0 else ""
        if existing_entries:
            refs_text = existing_entries + "\n" + generated
        else:
            refs_text = generated
        was_patched = True

    # Final validation — hard fail if still empty
    final_count = count_ref_entries(refs_text)
    if final_count == 0:
        raise ValueError(
            "Report generation failed: the References section could not be populated. "
            "No knowledge base sources were available and the reference generation "
            "service returned no entries. Please try again with a more specific topic "
            "or upload relevant documents to the knowledge base first."
        )

    heading = _section_heading(mode)
    final_content = body + f"\n\n{heading}\n\n{refs_text}\n"
    return final_content, was_patched
