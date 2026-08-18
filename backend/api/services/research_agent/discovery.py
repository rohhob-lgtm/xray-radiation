"""Autonomous source discovery — always free/keyless, no paid search API.

Two channels, both already used elsewhere in this codebase, wired together
here rather than forked:
  1. Free academic/patent APIs (Crossref, OpenAlex, Semantic Scholar, PubMed,
     arXiv, CORE, DOAJ, PatentsView) via innovation_external_research.py.
  2. General web discovery via the same DuckDuckGo HTML-result extractor
     innovation_external_research.py already uses for standards/manufacturer
     discovery — NOT restricted to a fixed domain allowlist (Phase 2B.5):
     any DuckDuckGo result that passes the mandatory is_safe_url() security
     check is a candidate. TRUSTED_DOMAINS/is_trusted_domain() remain a
     trust-PRIORITY signal only (consumed by quality_scorer.py's scoring
     and source_trust_service.py's manufacturer-domain cap) — discovering a
     brand-new manufacturer's own site is the whole point of this phase, so
     domain trust is earned post-fetch through evidence, never gated at
     discovery time.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
from urllib.parse import quote_plus, urlparse

import httpx

from api.services.innovation_external_research import (
    perform_hybrid_external_research,
    _ddg_extract_result_urls,
)
from api.services.research_agent.provider_throttle import call_with_throttle

log = logging.getLogger(__name__)

# Trusted-domain allowlist per the product spec: .gov/.edu/international
# bodies/standards organizations/manufacturer portals get priority in general
# web discovery so results skew toward authoritative sources instead of
# generic SEO content.
TRUSTED_DOMAIN_SUFFIXES: tuple[str, ...] = (".gov", ".edu", ".ac.uk", ".ac", ".int", ".mil")
TRUSTED_DOMAINS: set[str] = {
    "iaea.org", "www.iaea.org",
    "who.int", "www.who.int",
    "icrp.org", "www.icrp.org",
    "nrc.gov", "www.nrc.gov",
    "fda.gov", "www.fda.gov",
    "epa.gov", "www.epa.gov",
    "home.cern", "cds.cern.ch",
    "nist.gov", "www.nist.gov",
    "osti.gov", "www.osti.gov",
    "ncbi.nlm.nih.gov", "pubmed.ncbi.nlm.nih.gov",
    "arxiv.org",
    "doaj.org",
    "core.ac.uk",
    "semanticscholar.org", "www.semanticscholar.org",
    "crossref.org", "api.crossref.org",
    "rapiscansystems.com", "www.rapiscansystems.com",
    "smithsdetection.com", "www.smithsdetection.com",
    "nuctech.com", "www.nuctech.com",
    "leidos.com", "www.leidos.com",
    "astrophysicsinc.com", "www.astrophysicsinc.com",
    "iso.org", "www.iso.org",
    "iec.ch", "www.iec.ch",
    "astm.org", "www.astm.org",
    "ansi.org", "www.ansi.org",
    "ncrponline.org",
    "tsa.gov", "www.tsa.gov",
    "dhs.gov", "www.dhs.gov",
    "icao.int", "www.icao.int",
    "ecac-ceac.org", "www.ecac-ceac.org",
}

_NON_HTML_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".gif", ".svg", ".css", ".js", ".mp4", ".mp3",
    ".exe", ".dmg", ".zip", ".tar", ".gz",
    ".msi", ".bat", ".cmd", ".sh", ".apk", ".dll", ".scr", ".jar",
}

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "0.0.0.0", "::1"}


def is_trusted_domain(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if not host:
        return False
    if host in TRUSTED_DOMAINS:
        return True
    return host.endswith(TRUSTED_DOMAIN_SUFFIXES)


def is_safe_url(url: str) -> bool:
    """Mandatory security gate on every discovered URL, independent of
    trust/domain status (Phase 2B.5) — blocks non-http(s) schemes and
    localhost/private/link-local/reserved/multicast/unspecified IP-literal
    targets (SSRF-class hosts, including cloud metadata endpoints like
    169.254.169.254). This is a SECURITY control, distinct from
    is_trusted_domain() (a scoring signal) — it must remain mandatory
    regardless of how trusted or unknown a domain is.

    Only catches IP-literal SSRF attempts, not DNS-rebinding (a hostname
    that resolves to a private IP only at fetch time inside web_crawler.py's
    own httpx client) — a disclosed, deferred hardening gap; see the Phase
    2B.5 plan's rollback/deferral notes.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    host = (parsed.hostname or "").lower()
    if not host or host in _BLOCKED_HOSTNAMES:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return True  # ordinary hostname — not an IP literal
    return not (
        ip.is_private or ip.is_loopback or ip.is_link_local
        or ip.is_reserved or ip.is_multicast or ip.is_unspecified
    )


def _extension_allowed(url: str, content_types: list[str]) -> bool:
    path = urlparse(url).path.lower()
    if any(path.endswith(ext) for ext in _NON_HTML_EXTENSIONS):
        return False
    if path.endswith(".pdf"):
        return not content_types or "pdf" in content_types
    return True


def _external_source_to_metadata(source) -> dict:
    """Carries the rich academic metadata an ExternalSource already has
    (title/authors/publisher/DOI/abstract/year/citation_count/peer-review/
    open-access) through to the crawl step instead of discarding it down to
    a bare URL (Phase 2B.5) — consumed by crawler_orchestrator.py to
    pre-fill ResearchSource fields and gate full-text ingestion on
    is_open_access, and by paper_extraction.py for structured extraction."""
    return {
        "title": source.title,
        "authors": source.authors,
        "publisher": source.publisher,
        "doi": source.doi,
        "abstract": source.abstract,
        "year": source.year,
        "citation_count": source.citation_count,
        "is_peer_reviewed": source.is_peer_reviewed,
        "provider": source.provider,
        "source_type": source.source_type,
        "is_open_access": source.is_open_access,
        "fulltext_url": source.fulltext_url,
        "academic_source_type": source.academic_source_type,
        "degree_type": source.degree_type,
    }


async def _web_search_trusted(query: str, client: httpx.AsyncClient, limit: int = 5) -> list[dict]:
    url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        async def _do():
            resp = await client.get(url, timeout=15.0)
            resp.raise_for_status()
            return resp
        resp = await call_with_throttle("web_search", _do)
    except Exception as exc:
        log.debug("Trusted web search failed for %r: %s", query, exc)
        return []

    out: list[dict] = []
    for result_url in _ddg_extract_result_urls(resp.text):
        # Phase 2B.5: security gate only — NOT a trusted-domain gate. Any
        # DuckDuckGo result on a genuinely novel, non-pre-listed site is a
        # valid candidate now; is_trusted_domain() still feeds quality_scorer's
        # scoring signal downstream, unchanged.
        if is_safe_url(result_url):
            out.append({"url": result_url, "discovered_via": f"web_search:{query}"})
        if len(out) >= limit:
            break
    return out


async def discover_sources(
    queries: list[str], domain_label: str, content_types: list[str] | None = None,
) -> list[dict]:
    """Discover candidate URLs for a mission.

    Returns a list of {"url", "source_domain", "discovered_via", ...} dicts
    ready for api.db.crud.enqueue_research_urls(). Every channel here is
    free/keyless already, so this function's behavior does not depend on
    Free Mode — Free Mode only matters downstream (embeddings) in ingestion.py.
    """
    content_types = content_types or []
    discovered: list[dict] = []
    seen_urls: set[str] = set()

    # 1. Free academic/patent APIs — already deduped/scored/free.
    try:
        result = await perform_hybrid_external_research(queries, domain_label)
        for source in result.sources:
            if (
                source.url and source.url not in seen_urls
                and is_safe_url(source.url) and _extension_allowed(source.url, content_types)
            ):
                seen_urls.add(source.url)
                discovered.append({
                    "url": source.url,
                    "source_domain": urlparse(source.url).hostname or "",
                    "discovered_via": f"academic_api:{source.source_type}",
                    "academic_metadata": _external_source_to_metadata(source),
                })
    except Exception as exc:
        log.warning("Academic/patent discovery failed: %s", exc)

    # 2. General web discovery — not restricted to a fixed domain allowlist
    # (see is_safe_url()/module docstring above), free DuckDuckGo HTML scrape.
    if "web_pages" in content_types or not content_types:
        async with httpx.AsyncClient(
            headers={"User-Agent": "Mozilla/5.0 (X-Ray Academy Research Agent)"}, follow_redirects=True,
        ) as client:
            for query in queries:
                for item in await _web_search_trusted(query, client):
                    if (
                        item["url"] not in seen_urls
                        and is_safe_url(item["url"]) and _extension_allowed(item["url"], content_types)
                    ):
                        seen_urls.add(item["url"])
                        item["source_domain"] = urlparse(item["url"]).hostname or ""
                        discovered.append(item)
                await asyncio.sleep(0.5)  # politeness delay between DDG queries

    return discovered
