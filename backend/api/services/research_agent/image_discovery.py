"""Multimodal Internet Image Retrieval.

A bounded fallback used only when AI Chat's Knowledge Base image search
(api.services.gallery_service) genuinely finds nothing for the user's
request — reuses the existing Research Engine end to end:
discovery.discover_sources() for candidate pages, web_crawler.crawl() (now
image-aware — see web_crawler.py's PageResult.images) to find real
in-context images on those pages, is_safe_url() for the same SSRF gate
every other discovered URL goes through, initialize_trust() for scoring,
and KnowledgeProvenance for the same provenance trail every other learned
fact gets. Not a second image system — no new crawler, no new discovery
query mechanism, no new trust model.

Never fetches or stores the actual image bytes: every ResearchFile row
this module creates has downloaded=False, and the URL returned to the
frontend is the original external one, hotlinked directly — the same as
any ordinary web page reference. This is what makes "never cache
copyrighted media beyond metadata" true by construction.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from urllib.parse import quote

import httpx

from api.config import settings
from api.db import crud
from api.services.research_agent.discovery import is_safe_url, discover_sources
from api.services.research_agent.provider_throttle import call_with_throttle
from api.services.retrieval_utils import tokenize, keyword_score
from api.services.source_trust.source_trust_service import initialize_trust
from api.services.web_crawler import crawl as web_crawl

log = logging.getLogger(__name__)

_DOMAIN_LABEL = "X-ray, radiation, and security-screening research"

# This platform is about X-ray / radiation (security screening, industrial
# inspection, X-ray physics and sources) — the query is NEVER hard-forced into
# a security-only box (a request for a magnetron or a LINAC must still return
# those). The only steering applied is:
#   1. a light "x-ray" context added when the query doesn't already mention it,
#      so a bare concept resolves within the platform's imaging domain, and
#   2. a conditional filter that drops results reading as clinical/medical
#      HUMAN imaging (e.g. DEXA bone-density scans) — and ONLY when the user's
#      own query wasn't medical, so a genuinely medical question is untouched.
_XRAY_CONTEXT_TOKENS = ("x-ray", "xray", "x ray", "radiation", "radiograph", "radiography")

# Clinical / medical human-imaging markers — the off-domain false positives the
# reported bug surfaced (DEXA bone-density scans for "material discrimination").
_MEDICAL_NEGATIVE_RE = re.compile(
    r"\b(densitometr|absorptiometr|osteoporos|bone\s+density|dexa\b|dxa\b|"
    r"mammograph|dental|orthodont|patient|clinical|hospital|radiograph\s+of|"
    r"spine|femur|lumbar|vertebra|skeleton|fracture|tibia|pelvis|"
    r"mri\b|angiograph|mammary|thorax|chest\s+x-?ray|abdomen)\b",
    re.IGNORECASE,
)
# If the user genuinely asked about medical imaging, don't filter it out.
_MEDICAL_QUERY_RE = re.compile(
    r"\b(medical|clinical|densitometr|absorptiometr|osteoporos|bone|dexa|dxa|"
    r"mammograph|dental|patient|hospital|radiolog|diagnos)\b",
    re.IGNORECASE,
)


def _domain_biased_query(query: str) -> str:
    """Add a light "X-ray" context to an image query when it carries none, so a
    bare concept resolves within this platform's imaging domain. Deliberately
    NOT a security-only lock — no baggage/cargo terms are forced."""
    lowered = (query or "").lower()
    if _MEDICAL_QUERY_RE.search(lowered):
        return query
    if any(tok in lowered for tok in _XRAY_CONTEXT_TOKENS):
        return query
    return f"{query} x-ray".strip()


def _is_off_domain_medical(text: str, query: str) -> bool:
    """True when an image reads as clinical human imaging and the user did not
    ask for anything medical — those are the off-domain results to drop."""
    if _MEDICAL_QUERY_RE.search(query or ""):
        return False
    return bool(_MEDICAL_NEGATIVE_RE.search(text or ""))

# Wikimedia Commons search — free, keyless, and (unlike the general-web
# DuckDuckGo-scrape channel in discovery.py) not subject to anti-bot/
# rate-limit blocking from typical hosting IPs: live-verified against this
# environment's outbound network (DuckDuckGo's /html/ endpoint returned its
# "error-lite@duckduckgo.com" anomaly page for every query tried — zero
# usable result links — while Commons returned real, relevant images for
# "LINAC", "magnetron", and "baggage x-ray scanner" on the first try).
# Purpose-built for exactly this feature: real, properly licensed reference
# images searchable by topic. Additive, not a replacement — discover_public_
# images() still falls back to the existing discover_sources()+web_crawl
# page-image pipeline below to fill any remaining slots (e.g. a specific
# manufacturer product that isn't on Commons).
_WIKIMEDIA_COMMONS_API = "https://commons.wikimedia.org/w/api.php"
_WIKIMEDIA_USER_AGENT = "XRayAcademyResearchAgent/1.0 (educational reference-image lookup)"
_MIN_USEFUL_DIMENSION_PX = 200  # filters icon/thumbnail-sized files
_ICON_TITLE_RE = re.compile(r"\b(icon|logo|pictogram|clip ?art|silhouette)\b", re.IGNORECASE)
_HTML_TAG_RE = re.compile(r"<[^>]+>")


def _strip_html(raw: str) -> str:
    return _HTML_TAG_RE.sub("", raw or "").strip()


async def _wikimedia_commons_images(query: str, limit: int) -> list[dict]:
    """Returns [{"src", "alt", "page_url", "page_title"}] from a Wikimedia
    Commons full-text search over the File: namespace, already filtered to
    real images (image/* MIME) of a useful size and is_safe_url()-checked."""
    if limit <= 0:
        return []
    params = {
        "action": "query", "generator": "search", "gsrsearch": _domain_biased_query(query),
        "gsrnamespace": 6, "gsrlimit": max(limit * 3, 9),  # over-fetch: some get domain-filtered
        "prop": "imageinfo", "iiprop": "url|mime|size|extmetadata",
        "iiurlwidth": 800, "format": "json",
    }
    try:
        async def _do():
            async with httpx.AsyncClient(
                headers={"User-Agent": _WIKIMEDIA_USER_AGENT}, follow_redirects=True, timeout=12.0,
            ) as client:
                resp = await client.get(_WIKIMEDIA_COMMONS_API, params=params)
                resp.raise_for_status()
                return resp.json()
        data = await call_with_throttle("direct_crawl", _do)
    except Exception as exc:
        log.debug("Wikimedia Commons image search failed for %r: %s", query, exc)
        return []

    out: list[dict] = []
    pages = ((data or {}).get("query") or {}).get("pages") or {}
    for page in pages.values():
        title = page.get("title") or ""
        infos = page.get("imageinfo") or []
        if not title or not infos:
            continue
        info = infos[0]
        if not (info.get("mime") or "").startswith("image/"):
            continue
        width, height = info.get("width") or 0, info.get("height") or 0
        if width and height and (width < _MIN_USEFUL_DIMENSION_PX or height < _MIN_USEFUL_DIMENSION_PX):
            continue
        src = info.get("url") or ""
        if not src or not is_safe_url(src):
            continue
        label = title[5:] if title.startswith("File:") else title
        label = re.sub(r"\.\w{2,4}$", "", label).replace("_", " ").strip()
        if _ICON_TITLE_RE.search(label):
            continue
        extmeta = info.get("extmetadata") or {}
        description = _strip_html((extmeta.get("ImageDescription") or {}).get("value", ""))[:300]
        # Domain guard: drop clinical/medical human-imaging false positives
        # (e.g. DEXA bone-density scans) unless the query was itself medical.
        if _is_off_domain_medical(f"{label} {description}", query):
            continue
        page_url = "https://commons.wikimedia.org/wiki/" + quote(title.replace(" ", "_"))
        out.append({"src": src, "alt": description or label, "page_url": page_url, "page_title": label})
        if len(out) >= limit:
            break
    return out


async def discover_public_images(query: str, max_images: int | None = None) -> list[dict]:
    """Bounded candidate search across two channels — Wikimedia Commons
    first (reliable, free, keyless), then the existing discover_sources()+
    web_crawl page-image pipeline to fill any remaining slots. Returns
    [{"src", "alt", "page_url", "page_title"}], already is_safe_url()-filtered
    and capped at max_images."""
    limit = max_images if max_images is not None else settings.image_retrieval_max_images
    if limit <= 0:
        return []

    results: list[dict] = []
    seen_src: set[str] = set()
    for img in await _wikimedia_commons_images(query, limit):
        if img["src"] not in seen_src:
            seen_src.add(img["src"])
            results.append(img)

    if len(results) >= limit:
        return results[:limit]
    remaining = limit - len(results)

    candidates = await discover_sources([_domain_biased_query(query)], _DOMAIN_LABEL, content_types=["web_pages"])
    candidates = candidates[: max(3, remaining)]  # a handful of pages is enough to find a few images

    query_tokens = tokenize(query)
    scored: list[tuple[float, dict]] = []

    for candidate in candidates:
        page_url = candidate.get("url")
        if not page_url or not is_safe_url(page_url):
            continue
        try:
            async def _do():
                return await web_crawl(page_url, max_pages=1, max_depth=0, include_sitemap=False, min_relevance_score=0.0)
            report = await call_with_throttle("direct_crawl", _do)
        except Exception as exc:
            log.debug("Image-discovery crawl failed for %s: %s", page_url, exc)
            continue

        page = report.page_results[0] if report.page_results else None
        if not page or not page.accessible:
            continue

        page_title = next((line.strip() for line in (page.text or "").splitlines() if line.strip()), page_url)[:200]
        for img in page.images:
            src = img.get("src", "")
            if not src or src in seen_src or not is_safe_url(src):
                continue
            alt = img.get("alt", "")
            # Domain guard: same clinical/medical drop as the Commons channel.
            if _is_off_domain_medical(f"{alt} {page_title}", query):
                continue
            seen_src.add(src)
            relevance = keyword_score(query_tokens, f"{alt} {page_title}") if query_tokens else 0.0
            scored.append((relevance, {"src": src, "alt": alt, "page_url": page_url, "page_title": page_title}))

    # A zero-relevance image (typical of page chrome that slipped past the
    # icon/logo path filter — e.g. a funder badge on an arXiv abstract page
    # that happened to be the only crawlable candidate) must never pad out
    # the result set: better to return fewer images than an irrelevant one.
    scored = [pair for pair in scored if pair[0] > 0]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    results.extend(item for _, item in scored[:remaining])
    return results[:limit]


async def store_discovered_images(db, query: str, images: list[dict]) -> list[dict]:
    """Persists each discovered image as a real, sourced, provenance-linked
    graph fact — same primitives every other learned fact in this codebase
    already uses. Returns dicts shaped like gallery_service.py's
    GalleryImage, plus source_url/retrieved_at/confidence."""
    if not images:
        return []

    mission = crud.create_research_mission(
        db, user_id=None, mission_text=f"[Image Retrieval] {query[:180]}",
        mode="quick_scan", free_mode=True, priority=200, origin="chat_image_retrieval",
    )

    results: list[dict] = []
    min_trust = settings.image_retrieval_min_trust_score
    now = datetime.now(timezone.utc)

    for img in images:
        src = img["src"]
        from urllib.parse import urlparse
        domain = urlparse(src).hostname or urlparse(img.get("page_url", "")).hostname or ""
        title = img.get("alt") or img.get("page_title") or domain

        source = crud.create_research_source(
            db, mission_id=mission.id, url=src, domain=domain, title=title[:1024],
            publisher=domain, content_hash=None, quality_score=60.0, quality_label="useful",
            quality_reasons=["Discovered via Multimodal Internet Image Retrieval"],
            accepted_into_kb=False, source_doi=None,
        )
        initialize_trust(db, source)
        db.refresh(source)

        if source.effective_trust_score < min_trust:
            crud.add_research_activity(
                db, mission.id, "info",
                f"Dropped low-trust image candidate ({source.effective_trust_score}%): {src}",
            )
            continue

        file_row = crud.create_research_file(
            db, mission_id=mission.id, source_id=source.id, filename=title[:500],
            file_type="image", size_bytes=0, status="discovered", downloaded=False,
        )
        node = crud.create_knowledge_node(
            db, node_type="Image", label=title[:512], description=img.get("alt") or None,
            approved=False, confidence=round(source.effective_trust_score / 100.0, 2), evidence_count=1,
        )
        crud.create_knowledge_provenance(
            db, node_id=node.id, mission_id=mission.id, source_id=source.id,
            created_by_service="image_discovery", original_url=src,
        )

        results.append({
            "image_id": file_row.id,
            "gallery_index_id": None,
            "title": title,
            "image_url": src,
            "thumbnail_url": src,
            "caption": img.get("alt") or None,
            "tags": [],
            "source_document": domain,
            "page_number": None,
            "scanner_model": None,
            "manufacturer": None,
            "category": None,
            "source_url": img.get("page_url") or src,
            "retrieved_at": now.isoformat(),
            "confidence": round(source.effective_trust_score, 1),
        })

    crud.add_research_activity(
        db, mission.id, "info", f"Image retrieval for {query[:200]!r}: {len(results)} image(s) kept",
    )
    crud.update_research_mission(db, mission.id, status="completed", current_phase="completed")
    return results
