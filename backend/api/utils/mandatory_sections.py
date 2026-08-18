"""
Mandatory tail sections for Innovation Engine reports (§13–§17).

Sections 13-17 are ALWAYS built by this pipeline, never by the LLM.
The LLM generates a dynamic body (cover page + §1-12); this module
appends the five mandatory closing sections regardless of what the LLM produced.

Section assignment (Patent Mode spec):
  §13 References           — KB filenames + GPT-4o external refs (≥5 papers, ≥3 patents, ≥2 standards)
  §14 Related Patents      — GPT-4o: tabular (Number, Country, Year, URL, Similarity, Novelty Difference)
  §15 Standards            — GPT-4o: ISO, IEC, ASTM, IAEA, NIST, FDA, DHS, TSA, ECAC, ICAO
  §16 Knowledge Base Sources — deterministic from kb_chunks
  §17 Commercialisation    — GPT-4o: market, customers, manufacturing, licensing, valuation

Usage:
    body, tail = await build_mandatory_sections(
        body=llm_output,
        topic=..., domain_label=..., mode=...,
        kb_chunks=..., output_id=..., client=openai_async_client,
    )
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timezone
from typing import Any

log = logging.getLogger(__name__)

# ─── Patterns that identify mandatory sections ────────────────────────────────
# Used to strip any LLM-generated versions before appending pipeline versions.

_MANDATORY_HEADING_RE = re.compile(
    r'^#{1,3}\s+(?:'
    r'1[3-7]\.'                     # ## 13.  ## 14.  … ## 17.
    r'|R(?:1[3-7])\.'              # ## R13. … ## R17.
    r'|REFERENCES?'                 # ## REFERENCES
    r'|RELATED\s+PATENTS'           # ## RELATED PATENTS
    r'|STANDARDS?'                  # ## STANDARDS
    r'|KNOWLEDGE\s+BASE'            # ## KNOWLEDGE BASE SOURCES
    r'|COMMERCIALI[SZ]ATION'        # ## COMMERCIALISATION / COMMERCIALIZATION
    r'|REVISION\s+HISTORY'          # ## REVISION HISTORY (legacy)
    r')',
    re.IGNORECASE | re.MULTILINE,
)

_INLINE_CITE_RE = re.compile(r'\[(\d{1,3})\]')
_REF_ENTRY_RE   = re.compile(r'^\[(\d{1,3})\]\s+\S', re.MULTILINE)

# ─── Strip LLM-generated mandatory sections ───────────────────────────────────

def strip_mandatory_sections(content: str) -> str:
    """
    Remove any LLM-generated §13-17 (or References/Standards/etc. headings)
    from content so the pipeline can append clean, authoritative versions.
    Returns the body text only (cover page + §1-12).
    """
    m = _MANDATORY_HEADING_RE.search(content)
    if m:
        return _normalize_main_section_numbering(content[: m.start()].rstrip())
    return _normalize_main_section_numbering(content.rstrip())


def _normalize_main_section_numbering(content: str) -> str:
    """
    Normalize malformed H2 numbering from the model body before appending §13-§17.
    Fixes cases such as "## 1. 1. Title" or jumps that break TOC readability.
    """
    lines = content.splitlines()
    section_idx = 1
    out: list[str] = []
    for line in lines:
        m = re.match(r"^##\s+(.+)$", line)
        if not m:
            out.append(line)
            continue
        title = m.group(1).strip()
        if not re.match(r"^(?:R)?\d{1,2}\.\s+", title):
            # Keep unnumbered H2 headings (e.g., "PATENT COVER PAGE") untouched.
            out.append(line)
            continue
        title = re.sub(r"^(?:R)?\d{1,2}\.\s+", "", title)
        title = re.sub(r"^\d{1,2}\.\s+", "", title)
        out.append(f"## {section_idx}. {title}")
        section_idx += 1
    return "\n".join(out).strip()


# ─── §13 References ───────────────────────────────────────────────────────────

async def _build_references(
    body: str,
    topic: str,
    domain_label: str,
    kb_chunks: list,
    external_sources: list[Any],
    external_search_date: str,
    external_search_targets: list[str],
) -> str:
    """
    §13 References.
    Deterministic assembly from verified external retrieval + local KB.
    """
    lines: list[str] = []
    ref_n = 1

    lines.append("### Research Search Method")
    lines.append(f"- Search date (UTC): {external_search_date}")
    if external_search_targets:
        lines.append("- External sources searched:")
        for s in external_search_targets:
            lines.append(f"  - {s}")
    lines.append(f"- Topic: {topic}")
    lines.append(f"- Domain: {domain_label}")
    lines.append("")

    lines.append("### A. Public External References (Verified)")
    if external_sources:
        for src in external_sources:
            year = getattr(src, "year", "") or "n.d."
            title = getattr(src, "title", "Untitled source")
            publisher = getattr(src, "publisher", "")
            doi = getattr(src, "doi", "")
            url = getattr(src, "url", "")
            patent_number = getattr(src, "patent_number", "")
            standard_number = getattr(src, "standard_number", "")
            verified_by = getattr(src, "verified_by", "Authoritative source")
            authors = getattr(src, "authors", "")
            stype = getattr(src, "source_type", "external")

            meta = []
            if authors:
                meta.append(authors)
            if publisher:
                meta.append(publisher)
            meta.append(str(year))
            if patent_number:
                meta.append(f"Patent: {patent_number}")
            if standard_number:
                meta.append(f"Standard: {standard_number}")
            if doi:
                meta.append(f"DOI: {doi}")

            lines.append(f"[{ref_n}] [{stype.upper()}] {title}")
            lines.append(f"    {' | '.join(meta)}")
            lines.append(f"    URL: {url}")
            lines.append(f"    Verified via: {verified_by}")
            ref_n += 1
    else:
        lines.append(
            "No verified external references available. External internet research could not be completed."
        )

    lines.append("")
    lines.append("### B. Local Knowledge Base Sources")
    seen: set[str] = set()
    had_kb = False
    for chunk in kb_chunks:
        fname = getattr(chunk, "filename", None) or "Unknown document"
        if fname in seen:
            continue
        seen.add(fname)
        had_kb = True
        lines.append(f"[{ref_n}] [LOCAL-KB] {fname}, Internal Knowledge Base, X-Ray Academy.")
        ref_n += 1
    if not had_kb:
        lines.append("No local knowledge-base documents were retrieved.")

    return "\n".join(lines)


# ─── §14 Related Patents ──────────────────────────────────────────────────────

async def _build_related_patents(
    topic: str,
    domain_label: str,
    external_sources: list[Any],
    external_search_targets: list[str],
    external_warnings: list[str],
) -> str:
    """
    §14 Related Patents.
    Deterministic from verified external patent retrieval.
    """
    patents = [s for s in external_sources if getattr(s, "source_type", "") == "patent"]
    if not patents:
        searched = ", ".join(external_search_targets) if external_search_targets else "configured external patent sources"
        provider_down = any("PATENT_PROVIDER_UNAVAILABLE" in s for s in external_warnings)
        if provider_down:
            return (
                "Patent search could not be completed because one or more patent providers were unavailable.\n\n"
                f"Searched: {searched}\n\n"
                "This section intentionally avoids fabricated or unverifiable patent records."
            )
        return (
            "No relevant verified patent was found after searching external sources.\n\n"
            f"Searched: {searched}\n\n"
            "This section intentionally omits unverifiable patent candidates."
        )

    lines = [
        "| Patent Number | Year | Official URL | Verification |",
        "|---|---|---|---|",
    ]
    for s in patents[:12]:
        pnum = getattr(s, "patent_number", "") or "Not provided"
        year = getattr(s, "year", "") or "n.d."
        url = getattr(s, "url", "") or ""
        vfy = getattr(s, "verified_by", "") or "Authoritative source"
        lines.append(f"| {pnum} | {year} | {url} | {vfy} |")
    return "\n".join(lines)


# ─── §15 Standards ────────────────────────────────────────────────────────────

async def _build_standards(
    topic: str,
    domain_label: str,
    external_sources: list[Any],
    external_search_targets: list[str],
    external_warnings: list[str],
) -> str:
    """
    §15 Standards.
    Deterministic from verified standards/regulatory retrieval.
    """
    standards = [
        s for s in external_sources
        if getattr(s, "source_type", "") in {"standard", "regulator"}
    ]
    if not standards:
        searched = ", ".join(external_search_targets) if external_search_targets else "configured external standards sources"
        provider_down = any("STANDARDS_PROVIDER_UNAVAILABLE" in s for s in external_warnings)
        if provider_down:
            return (
                "Standards search could not be completed because standards/regulatory providers were unavailable.\n\n"
                f"Searched: {searched}\n\n"
                "This section intentionally avoids fabricated or unverifiable standards references."
            )
        return (
            "No relevant verified standard was found after searching external standards and regulator sources.\n\n"
            f"Searched: {searched}\n\n"
            "This section intentionally omits unverifiable standard candidates."
        )

    lines = []
    for i, s in enumerate(standards[:12], 1):
        snum = getattr(s, "standard_number", "") or "Regulatory/Guidance document"
        title = getattr(s, "title", "Untitled source")
        year = getattr(s, "year", "") or "n.d."
        url = getattr(s, "url", "") or ""
        vfy = getattr(s, "verified_by", "") or "Authoritative source"
        lines.append(f"{i}. **{snum}** - {title} ({year})")
        lines.append(f"   URL: {url}")
        lines.append(f"   Verified via: {vfy}")
    return "\n".join(lines)


# ─── §16 Knowledge Base Sources ───────────────────────────────────────────────

def _build_kb_sources(kb_chunks: list) -> str:
    """
    §16 Knowledge Base Sources.
    Lists every distinct source document retrieved from the KB.
    Deterministic — no GPT call.
    """
    if not kb_chunks:
        return "_No knowledge base documents were retrieved for this report._"

    seen: set[str] = set()
    lines: list[str] = []
    for i, chunk in enumerate(kb_chunks, 1):
        fname   = getattr(chunk, "filename", None) or "Unknown"
        content = (getattr(chunk, "content", "") or "").strip()
        snippet = " ".join(content[:250].split()).replace("\n", " ")

        # Attempt to extract page info from chunk metadata if present
        page = getattr(chunk, "page_number", None) or getattr(chunk, "page", None)
        section = getattr(chunk, "section", None)

        if fname in seen:
            continue
        seen.add(fname)

        meta_parts = []
        if page:
            meta_parts.append(f"Page {page}")
        if section:
            meta_parts.append(f"Section: {section}")
        meta_str = f" — {', '.join(meta_parts)}" if meta_parts else ""

        lines.append(f"**{i}.** `{fname}`{meta_str}")
        if snippet:
            lines.append(f"   > {snippet}…")
        lines.append("")

    return "\n".join(lines).strip()


# ─── §17 Commercialisation ────────────────────────────────────────────────────

async def _build_commercialisation(
    topic: str,
    domain_label: str,
    client,
) -> str:
    """
    §17 Commercialisation.
    Covers: estimated market, target customers, manufacturing estimate,
    licensing opportunities, patent valuation.
    """
    prompt = f"""You are a technology commercialisation consultant specialising in
X-ray security and industrial imaging systems.

Write a Commercialisation section for a patent disclosure about:
  Topic:  {topic}
  Domain: {domain_label}

Cover ALL of the following subsections with specific, realistic figures:

### Estimated Market
Global addressable market size (USD), CAGR, key market drivers,
regional breakdown (North America, Europe, Middle East & Asia-Pacific).

### Target Customers
Primary and secondary customer segments with specific named organisations
(government agencies, defence contractors, airport operators, port authorities,
customs agencies, OEMs).

### Manufacturing Estimate
Unit cost estimate at different production volumes (prototype / 100 units / 1000 units),
key manufacturing challenges, preferred supply chain approach (in-house vs. ODM vs. OEM).

### Licensing Opportunities
Recommended IP licensing strategy: exclusive vs. non-exclusive, territory, royalty rate range,
potential licensees (named companies), cross-licensing opportunities.

### Patent Valuation
Estimated patent portfolio value (USD range), key value drivers, comparable patent transactions
in this domain, recommended filing strategy (PCT / national phase countries).

Write in professional business-plan language. Include specific numbers.
Use Markdown subsection headings (###)."""

    if client is None:
        return (
            "### Estimated Market\n"
            "Market assessment is pending and should be completed during business review.\n\n"
            "### Target Customers\n"
            "Primary customer segmentation requires program-level validation with end users.\n\n"
            "### Manufacturing Estimate\n"
            "Manufacturing and supply-chain estimates should be completed with procurement input.\n\n"
            "### Licensing Opportunities\n"
            "Licensing strategy should be finalized with legal and strategy teams.\n\n"
            "### Patent Valuation\n"
            "Patent valuation is pending formal IP and market benchmarking."
        )

    try:
        resp = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_completion_tokens=900,
            temperature=0.3,
        )
        try:
            from api.utils.usage_recorder import record_usage_from_response
            record_usage_from_response(
                "Innovation Engine", resp,
                sub_feature="mandatory_commercialisation",
                meta={"topic": topic, "domain": domain_label},
            )
        except Exception:
            pass
        return (resp.choices[0].message.content or "").strip()
    except Exception as exc:
        log.warning("§17 Commercialisation GPT call failed: %s", exc)
        return (
            "### Estimated Market\n"
            "Market assessment is pending and should be completed during business review.\n\n"
            "### Target Customers\n"
            "Primary customer segmentation requires program-level validation with end users.\n\n"
            "### Manufacturing Estimate\n"
            "Manufacturing and supply-chain estimates should be completed with procurement input.\n\n"
            "### Licensing Opportunities\n"
            "Licensing strategy should be finalized with legal and strategy teams.\n\n"
            "### Patent Valuation\n"
            "Patent valuation is pending formal IP and market benchmarking."
        )


# ─── Master assembler ─────────────────────────────────────────────────────────

async def build_mandatory_sections(
    body: str,
    topic: str,
    domain_label: str,
    mode: str,
    kb_chunks: list,
    external_sources: list[Any],
    external_warnings: list[str],
    external_search_date: str,
    external_search_targets: list[str],
    output_id: str,
    client,
) -> tuple[str, str]:
    """
    Strip any LLM-generated mandatory sections from `body`, then build
    §13–§17 in parallel and append them.

    Section order (matches Patent Mode spec):
      §13 References
      §14 Related Patents
      §15 Standards
      §16 Knowledge Base Sources
      §17 Commercialisation

    Returns:
        (full_content, tail_markdown)
        full_content = clean body + mandatory tail
        tail_markdown = just the appended text (streamed to frontend)

    Never raises — failures produce graceful fallback text per section.
    """
    clean_body = strip_mandatory_sections(body)

    # Deterministic source sections + one AI commercialisation section.
    refs_task    = _build_references(
        clean_body,
        topic,
        domain_label,
        kb_chunks,
        external_sources,
        external_search_date,
        external_search_targets,
    )
    patents_task = _build_related_patents(topic, domain_label, external_sources, external_search_targets, external_warnings)
    stds_task    = _build_standards(topic, domain_label, external_sources, external_search_targets, external_warnings)
    comm_task    = _build_commercialisation(topic, domain_label, client)

    refs_text, patents_text, stds_text, comm_text = await asyncio.gather(
        refs_task, patents_task, stds_task, comm_task
    )

    # Deterministic — no GPT
    kb_text = _build_kb_sources(kb_chunks)

    warning_block = ""
    if external_warnings:
        public_warnings = [w for w in external_warnings if "_PROVIDER_" not in w and "_VERIFIED_ZERO_" not in w]
        warning_lines = "\n".join(f"- {w}" for w in public_warnings)
        warning_block = (
            "\n\n## External Research Status\n\n"
            "Note: External research may be incomplete or partially unavailable.\n"
            "This output must be treated as draft and not submission-ready.\n\n"
            f"{warning_lines}\n"
        )

    tail = (
        f"\n\n---\n\n"
        f"{warning_block}"
        f"## 13. References\n\n{refs_text}\n\n"
        f"## 14. Related Patents\n\n{patents_text}\n\n"
        f"## 15. Standards\n\n{stds_text}\n\n"
        f"## 16. Knowledge Base Sources\n\n{kb_text}\n\n"
        f"## 17. Commercialisation\n\n{comm_text}\n"
    )

    full_content = clean_body + tail
    return full_content, tail
