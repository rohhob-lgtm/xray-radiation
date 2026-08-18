"""
Hybrid external research for Innovation Engine.

This module performs live internet retrieval from authoritative sources and
returns only verifiable references. It is intentionally scoped to Innovation
Engine report generation.
"""
from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import parse_qs, quote_plus, unquote, urlparse

import httpx

from api.services.research_agent.provider_throttle import call_with_throttle

log = logging.getLogger(__name__)


@dataclass
class ExternalSource:
    title: str
    source_type: str  # academic | patent | standard | regulator | university
    url: str
    year: str = ""
    authors: str = ""
    publisher: str = ""
    doi: str = ""
    patent_number: str = ""
    standard_number: str = ""
    verified_by: str = ""
    abstract: str = ""
    relevance_score: float = 0.0
    provider: str = ""
    citation_count: int | None = None
    is_peer_reviewed: bool | None = None
    doi_verified: bool = False
    is_retracted: bool = False
    quality_score: float = 0.0
    # Phase 2B.5 — legal/copyright compliance for academic learning. Populated
    # from data ALREADY present in each provider's own JSON response (no new
    # API calls): is_open_access gates whether crawler_orchestrator.py may
    # fetch/ingest the full text at all, or must store metadata+abstract only.
    is_open_access: bool = False
    fulltext_url: str = ""
    # paper | thesis | patent | standard | technical_report
    academic_source_type: str = "paper"
    degree_type: str = ""


@dataclass
class ExternalResearchResult:
    sources: list[ExternalSource]
    searched_at_utc: str
    searched_sources: list[str]
    warnings: list[str]


_STD_NUMBER_RE = re.compile(
    r"\\b(IEC|ISO|ASTM|EN|NIST|IAEA|ANSI)\\s*[-:]?\\s*\\d{2,6}(?:-\\d+)*(?::\\d{4})?\\b",
    re.IGNORECASE,
)

_PATENT_NUMBER_RE = re.compile(
    r"\\b(?:US|EP|WO|GB|JP|CN|KR)\\s?\\d{4,12}(?:[A-Z]\\d?|\\s?[A-Z]\\d?)?\\b",
    re.IGNORECASE,
)

_TRUSTED_HOSTS = {
    "doi.org",
    "api.crossref.org",
    "pubmed.ncbi.nlm.nih.gov",
    "arxiv.org",
    "patents.google.com",
    "patentscope.wipo.int",
    "worldwide.espacenet.com",
    "uspto.gov",
    "www.uspto.gov",
    "ieeexplore.ieee.org",
    "sciencedirect.com",
    "www.sciencedirect.com",
    "link.springer.com",
    "www.nature.com",
    "www.mdpi.com",
    "www.spiedigitallibrary.org",
    "www.nist.gov",
    "www.iaea.org",
    "www.iso.org",
    "www.iec.ch",
    "www.astm.org",
    "www.dhs.gov",
    "www.tsa.gov",
    "www.icao.int",
    "www.ecac-ceac.org",
    "rapiscansystems.com",
    "www.rapiscansystems.com",
    "smithsdetection.com",
    "www.smithsdetection.com",
    "nuctech.com",
    "www.nuctech.com",
    "leidos.com",
    "www.leidos.com",
    "astrophysicsinc.com",
    "www.astrophysicsinc.com",
}

_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "using", "used", "use",
    "study", "analysis", "based", "method", "methods", "approach", "system", "systems", "model",
    "models", "data", "results", "research", "paper", "review", "toward", "through", "across",
    "between", "within", "their", "than", "have", "has", "had", "were", "was", "are", "is",
}

_POSITIVE_TERMS = {
    "xray", "x", "ray", "radiation", "detector", "detectors", "scintillator", "photon",
    "dual", "energy", "multi", "spectral", "backscatter", "cargo", "container", "vehicle",
    "baggage", "inspection", "screening", "security", "threat", "contraband", "material",
    "discrimination", "throughput", "false", "alarm", "high", "voltage", "generator",
}

_NEGATIVE_MEDICAL_TERMS = {
    "patient", "patients", "clinical", "diagnostic", "radiology",
    "therapy", "hospital", "disease", "medical", "medicine", "dose reconstruction",
    "leaf", "crop", "plant", "agricultural", "veterinary",
}

# Unambiguous medical-imaging markers — these essentially never appear in a
# security-screening paper (a security X-ray paper says "baggage X-ray" or
# "cargo X-ray", never "chest X-ray"), so a single hit is enough to veto
# unconditionally. The weaker _NEGATIVE_MEDICAL_TERMS set above requires
# multiple hits and yields to an explicit security-context mention, because
# a word like "medical" or "disease" alone could plausibly appear in a
# security-context sentence ("unlike medical scanners") without the paper
# actually being medical.
_STRONG_NEGATIVE_MEDICAL_TERMS = {
    "pneumonia", "covid", "mammography", "oncology", "tumor", "tumour",
    "cancer", "cardiology", "cardiac", "coronary", "lesion", "biopsy",
    "chest", "lung", "lungs", "thorax", "tuberculosis",
}


def _tokenize(text: str) -> set[str]:
    raw = re.findall(r"[a-z0-9]+", (text or "").lower())
    return {t for t in raw if len(t) > 2 and t not in _STOPWORDS}


def _build_topic_keywords(topic: str, domain_label: str) -> set[str]:
    base = _tokenize(topic) | _tokenize(domain_label)
    base |= {
        "xray", "radiation", "detector", "security", "screening", "inspection",
        "cargo", "container", "threat", "contraband",
        # AI/ML vocabulary — a paper about AI-based X-ray screening is a hit even
        # when it never uses cargo/customs wording (previously under-weighted,
        # which starved retrieval for AI-focused topics down to hardware papers).
        "artificial", "intelligence", "deep", "learning", "neural", "network",
        "networks", "cnn", "convolutional", "transformer", "transformers", "machine",
        "vision", "algorithm", "algorithms", "classification", "detection", "recognition",
        "automatic", "explainable", "dataset", "datasets",
        # X-ray source/generator/detector physics vocabulary — distinct from
        # the screening/threat-detection track above, so a topic about X-ray
        # source technology or detector physics scores its own literature
        # well instead of only matching security-screening papers.
        "source", "sources", "generator", "generators", "tube", "tubes", "anode",
        "cathode", "voltage", "spectrum", "photon", "photons", "scintillator",
        "sensor", "sensors", "physics", "tomography", "attenuation",
        # Explosives and nuclear/radiological threat detection — distinct
        # detection-technology sub-domains this platform also covers, not
        # just conventional baggage/cargo screening.
        "explosive", "explosives", "bomb", "ied", "nuclear", "radiological",
        "radioactive", "gamma", "neutron", "isotope", "isotopes",
    }
    return base


def _is_cargo_security_context(topic: str, domain_label: str) -> bool:
    """True only for topics genuinely about cargo/vehicle/container inspection.

    Used only to decide whether a source needs an explicit cargo/customs
    mention to count as relevant — narrowed to explicit cargo/vehicle terms
    so AI/ML papers that never mention customs/cargo aren't hard-rejected.
    """
    text = f"{topic} {domain_label}".lower()
    return any(k in text for k in ["cargo", "container", "customs", "border crossing", "vehicle inspection", "freight"])


def _is_security_screening_topic(topic: str, domain_label: str) -> bool:
    """True for any X-ray-security/screening topic, cargo or not.

    Broader than `_is_cargo_security_context` on purpose: this gates the
    medical-paper veto below, and a generic "AI in X-ray screening" topic
    (no literal "cargo") still must not pull in mammography/pneumonia/
    oncology imaging papers just because they also use CNNs on X-rays.
    """
    text = f"{topic} {domain_label}".lower()
    return any(k in text for k in [
        "cargo", "container", "customs", "border", "security", "screening",
        "scanner", "scanning", "baggage", "threat", "inspection", "checkpoint",
    ])


def _score_relevance(source: ExternalSource, topic: str, domain_label: str) -> float:
    title_tokens = _tokenize(source.title)
    abstract_tokens = _tokenize(source.abstract)
    keyword_tokens = _tokenize(f"{source.publisher} {source.patent_number} {source.standard_number}")
    wanted = _build_topic_keywords(topic, domain_label)

    title_hits = len(title_tokens & wanted)
    abstract_hits = len(abstract_tokens & wanted)
    keyword_hits = len(keyword_tokens & wanted)

    # Weighted by evidence quality: title + abstract + structured metadata.
    score = (title_hits * 1.6) + (abstract_hits * 1.2) + (keyword_hits * 0.8)

    neg_hits = len((_tokenize(source.title + " " + source.abstract)) & _NEGATIVE_MEDICAL_TERMS)
    if _is_security_screening_topic(topic, domain_label) and neg_hits >= 2:
        score -= 3.0

    return score


# Unambiguous X-ray/radiation-physics domain markers. Deliberately excludes
# words that are common outside this domain even though they're relevant
# X-ray vocabulary in context — "generator", "source"/"sources", "tube",
# "sensor", "spectrum", "detector" alone are also everyday words in
# electrical engineering, general instrumentation, etc. (a "Doubly Fed
# Induction Generator" paper is about wind-turbine power generators, not
# X-ray tubes) — those still contribute to the relevance *score* via
# _build_topic_keywords, but must not be sufficient on their own to admit a
# source. Every genuinely X-ray/radiation paper's title or abstract contains
# at least one of these unambiguous markers.
_STRONG_XRAY_DOMAIN_TERMS = {
    "ray", "xray", "radiograph", "radiographic", "radiography", "tomography",
    "backscatter", "photon", "photons", "scintillator", "synchrotron",
    "beamline", "radiological", "radioactive", "attenuation", "crystallography",
    "diffraction", "diffractive", "spectroscopy", "gamma", "neutron", "isotope",
    "isotopes", "dose", "radiation", "detector", "detectors", "screening",
    "baggage", "cargo", "explosive", "explosives", "contraband", "scanner",
    "scanning", "imaging", "fluorescence",
}


def _is_relevant(source: ExternalSource, topic: str, domain_label: str) -> bool:
    score = _score_relevance(source, topic, domain_label)
    source.relevance_score = score

    min_by_type = {
        "academic": 2.8,
        "patent": 2.0,
        "standard": 1.6,
        "regulator": 1.6,
        "university": 2.2,
    }
    threshold = min_by_type.get(source.source_type, 2.2)

    text_tokens = _tokenize(source.title + " " + source.abstract)

    # This platform only ever publishes X-ray/radiation-physics research —
    # an academic source that scores well purely on generic "artificial
    # intelligence" vocabulary (creative-industry AI reviews, power-grid
    # generator design, clinical decision-making frameworks, etc. all
    # legitimately contain "artificial intelligence" without being remotely
    # X-ray-related) must still show an unambiguous X-ray/radiation signal
    # to be admitted. This is unconditional, not just for screening topics —
    # the earlier version only enforced it for cargo/security topics, which
    # is exactly how off-topic AI papers slipped into non-screening (e.g.
    # source/detector-physics) manuscripts.
    if source.source_type == "academic" and not (text_tokens & _STRONG_XRAY_DOMAIN_TERMS):
        return False

    # Guardrail: security/screening topics should reject clearly medical-only
    # papers. This is a genuine veto (not just a score penalty) because a
    # mammography/pneumonia/oncology imaging paper is never useful evidence
    # for an X-ray-security manuscript regardless of how it scores otherwise
    # on generic CNN/deep-learning vocabulary alone.
    if _is_security_screening_topic(topic, domain_label):
        # Unambiguous — an incidental "...similar to security applications"
        # aside in a pneumonia/oncology paper's abstract must not save it;
        # this veto is unconditional, unlike the weaker one below.
        if text_tokens & _STRONG_NEGATIVE_MEDICAL_TERMS:
            return False
        has_security_context = bool(text_tokens & {"cargo", "security", "inspection", "screening", "threat", "baggage", "checkpoint"})
        if not has_security_context and len(text_tokens & _NEGATIVE_MEDICAL_TERMS) >= 2:
            return False

    return score >= threshold


def _host_ok(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    if host in _TRUSTED_HOSTS:
        return True
    return host.endswith(".gov") or host.endswith(".edu")


async def _is_url_reachable(client: httpx.AsyncClient, url: str) -> bool:
    try:
        async def _do():
            resp = await client.get(url, follow_redirects=True)
            return resp
        resp = await call_with_throttle("direct_crawl", _do)
        return resp.status_code < 400
    except Exception:
        return False


def _dedupe_sources(sources: list[ExternalSource]) -> list[ExternalSource]:
    seen: set[str] = set()
    out: list[ExternalSource] = []
    for s in sources:
        key = (s.doi or s.url).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


async def _crossref_sources(client: httpx.AsyncClient, query: str, rows: int = 6) -> tuple[list[ExternalSource], Optional[str]]:
    url = f"https://api.crossref.org/works?query={quote_plus(query)}&rows={rows}&sort=relevance"
    try:
        async def _do():
            r = await client.get(url)
            r.raise_for_status()
            return r
        r = await call_with_throttle("crossref", _do)
        items = (r.json().get("message") or {}).get("items") or []
    except Exception as exc:
        log.warning("Crossref lookup failed: %s", exc)
        return [], f"CROSSREF_PROVIDER_UNAVAILABLE: {exc.__class__.__name__}"

    out: list[ExternalSource] = []
    for it in items:
        doi = (it.get("DOI") or "").strip()
        title = ""
        title_list = it.get("title") or []
        if title_list:
            title = str(title_list[0]).strip()
        if not doi or not title:
            continue
        doi_url = f"https://doi.org/{doi}"
        abstract_raw = (it.get("abstract") or "").strip()
        abstract = re.sub(r"<[^>]+>", " ", abstract_raw)
        abstract = re.sub(r"\s+", " ", abstract).strip()

        authors = []
        for a in (it.get("author") or [])[:5]:
            family = (a.get("family") or "").strip()
            given = (a.get("given") or "").strip()
            name = (f"{given} {family}").strip()
            if name:
                authors.append(name)
        year = ""
        issued = (it.get("issued") or {}).get("date-parts") or []
        # CrossRef can return date-parts as [[null]] for undated works — issued[0]
        # is a non-empty (truthy) list even when its only element is None, so the
        # old truthiness check on issued[0] alone let str(None) -> "None" leak
        # into the year field and propagate into every downstream table/chart.
        if issued and issued[0] and issued[0][0] is not None:
            year = str(issued[0][0])

        work_type = (it.get("type") or "").strip()
        container = (it.get("container-title") or [""])[0]

        out.append(
            ExternalSource(
                title=title,
                source_type="academic",
                url=doi_url,
                year=year,
                authors=", ".join(authors),
                publisher=container,
                doi=doi,
                verified_by="Crossref DOI record",
                abstract=abstract,
                provider="crossref",
                citation_count=it.get("is-referenced-by-count"),
                is_peer_reviewed=bool(container) and work_type in {"journal-article", "proceedings-article"},
            )
        )
        if len(out) >= rows:
            break
    return out, None


async def _openalex_sources(client: httpx.AsyncClient, query: str, rows: int = 6) -> tuple[list[ExternalSource], Optional[str]]:
    url = f"https://api.openalex.org/works?search={quote_plus(query)}&per_page={rows}"
    try:
        async def _do():
            r = await client.get(url)
            r.raise_for_status()
            return r
        r = await call_with_throttle("openalex", _do)
        items = r.json().get("results") or []
    except Exception as exc:
        log.warning("OpenAlex lookup failed: %s", exc)
        return [], f"OPENALEX_PROVIDER_UNAVAILABLE: {exc.__class__.__name__}"

    out: list[ExternalSource] = []
    for it in items:
        title = (it.get("display_name") or it.get("title") or "").strip()
        doi_raw = (it.get("doi") or "").strip()
        doi = doi_raw.replace("https://doi.org/", "").strip()
        if not title:
            continue
        url_out = doi_raw or it.get("id") or ""
        if not url_out:
            continue
        authors = []
        for a in (it.get("authorships") or [])[:5]:
            name = ((a.get("author") or {}).get("display_name") or "").strip()
            if name:
                authors.append(name)
        primary_loc = it.get("primary_location") or {}
        source_meta = primary_loc.get("source") or {}
        venue = (source_meta.get("display_name") or "").strip()
        work_type = (it.get("type") or "").strip()
        abstract = ""
        inv_idx = it.get("abstract_inverted_index")
        if isinstance(inv_idx, dict) and inv_idx:
            positions: dict[int, str] = {}
            for word, idxs in inv_idx.items():
                for p in idxs:
                    positions[p] = word
            abstract = " ".join(positions[p] for p in sorted(positions))[:1500]

        oa = it.get("open_access") or {}
        is_thesis = work_type == "dissertation" or "thesis" in venue.lower() or "dissertation" in venue.lower()

        out.append(
            ExternalSource(
                title=title,
                source_type="academic",
                url=url_out,
                year=str(it.get("publication_year") or ""),
                authors=", ".join(authors),
                publisher=venue,
                doi=doi,
                verified_by="OpenAlex work record",
                abstract=abstract,
                provider="openalex",
                citation_count=it.get("cited_by_count"),
                is_peer_reviewed=bool(venue) and work_type in {"article", "review", "proceedings-article"},
                is_retracted=bool(it.get("is_retracted")),
                is_open_access=bool(oa.get("is_oa")),
                fulltext_url=(oa.get("oa_url") or "") if oa.get("is_oa") else "",
                academic_source_type="thesis" if is_thesis else "paper",
                degree_type="Doctoral/Masters" if is_thesis else "",
            )
        )
        if len(out) >= rows:
            break
    return out, None


async def _semantic_scholar_sources(client: httpx.AsyncClient, query: str, rows: int = 6, api_key: str = "") -> tuple[list[ExternalSource], Optional[str]]:
    fields = "title,abstract,year,authors,externalIds,venue,citationCount,publicationTypes,isOpenAccess"
    url = (
        "https://api.semanticscholar.org/graph/v1/paper/search"
        f"?query={quote_plus(query)}&fields={fields}&limit={rows}"
    )
    headers = {"x-api-key": api_key} if api_key else {}
    try:
        async def _do():
            r = await client.get(url, headers=headers)
            r.raise_for_status()
            return r
        r = await call_with_throttle("semantic_scholar", _do)
        items = r.json().get("data") or []
    except Exception as exc:
        log.warning("Semantic Scholar lookup failed: %s", exc)
        return [], f"SEMANTIC_SCHOLAR_PROVIDER_UNAVAILABLE: {exc.__class__.__name__}"

    out: list[ExternalSource] = []
    for it in items:
        title = (it.get("title") or "").strip()
        doi = ((it.get("externalIds") or {}).get("DOI") or "").strip()
        if not title or not doi:
            continue
        authors = [a.get("name", "").strip() for a in (it.get("authors") or [])[:5] if a.get("name")]
        venue = (it.get("venue") or "").strip()
        pub_types = it.get("publicationTypes") or []
        out.append(
            ExternalSource(
                title=title,
                source_type="academic",
                url=f"https://doi.org/{doi}",
                year=str(it.get("year") or ""),
                authors=", ".join(authors),
                publisher=venue,
                doi=doi,
                verified_by="Semantic Scholar record",
                abstract=(it.get("abstract") or "")[:1500],
                provider="semantic_scholar",
                citation_count=it.get("citationCount"),
                is_peer_reviewed=bool(venue) and "JournalArticle" in pub_types or "Conference" in pub_types,
                # isOpenAccess is already in the requested `fields` string
                # above — read it instead of discarding it.
                is_open_access=bool(it.get("isOpenAccess")),
                academic_source_type="thesis" if "Dissertation" in pub_types else "paper",
            )
        )
        if len(out) >= rows:
            break
    return out, None


async def _core_sources(client: httpx.AsyncClient, query: str, rows: int = 6, api_key: str = "") -> tuple[list[ExternalSource], Optional[str]]:
    if not api_key:
        return [], None
    url = f"https://api.core.ac.uk/v3/search/works/?q={quote_plus(query)}&limit={rows}"
    try:
        async def _do():
            r = await client.get(url, headers={"Authorization": f"Bearer {api_key}"})
            r.raise_for_status()
            return r
        r = await call_with_throttle("core", _do)
        items = r.json().get("results") or []
    except Exception as exc:
        log.warning("CORE lookup failed: %s", exc)
        return [], f"CORE_PROVIDER_UNAVAILABLE: {exc.__class__.__name__}"

    out: list[ExternalSource] = []
    for it in items:
        title = (it.get("title") or "").strip()
        doi = (it.get("doi") or "").strip()
        if not title:
            continue
        authors = [a.get("name", "").strip() for a in (it.get("authors") or [])[:5] if a.get("name")]
        venue = ((it.get("journals") or [{}])[0] or {}).get("title", "") if it.get("journals") else ""
        url_out = f"https://doi.org/{doi}" if doi else (it.get("downloadUrl") or it.get("sourceFulltextUrls", [""])[0] if it.get("sourceFulltextUrls") else "")
        if not url_out:
            continue
        out.append(
            ExternalSource(
                title=title,
                source_type="academic",
                url=url_out,
                year=str(it.get("yearPublished") or ""),
                authors=", ".join(authors),
                publisher=venue or "CORE",
                doi=doi,
                verified_by="CORE aggregator record",
                abstract=(it.get("abstract") or "")[:1500],
                provider="core",
                is_peer_reviewed=bool(venue),
                # CORE is an open-access-only aggregator by design — every
                # work it indexes is already legally open.
                is_open_access=True,
                fulltext_url=url_out,
            )
        )
        if len(out) >= rows:
            break
    return out, None


async def _doaj_sources(client: httpx.AsyncClient, query: str, rows: int = 6) -> tuple[list[ExternalSource], Optional[str]]:
    url = f"https://doaj.org/api/search/articles/{quote_plus(query)}?pageSize={rows}"
    try:
        async def _do():
            r = await client.get(url)
            r.raise_for_status()
            return r
        r = await call_with_throttle("doaj", _do)
        items = r.json().get("results") or []
    except Exception as exc:
        log.warning("DOAJ lookup failed: %s", exc)
        return [], f"DOAJ_PROVIDER_UNAVAILABLE: {exc.__class__.__name__}"

    out: list[ExternalSource] = []
    for it in items:
        bib = it.get("bibjson") or {}
        title = (bib.get("title") or "").strip()
        if not title:
            continue
        doi = ""
        url_out = ""
        for ident in bib.get("identifier") or []:
            if (ident.get("type") or "").lower() == "doi":
                doi = (ident.get("id") or "").strip()
        for link in bib.get("link") or []:
            if link.get("url"):
                url_out = link["url"]
                break
        if doi and not url_out:
            url_out = f"https://doi.org/{doi}"
        if not url_out:
            continue
        authors = [a.get("name", "").strip() for a in (bib.get("author") or [])[:5] if a.get("name")]
        venue = (bib.get("journal") or {}).get("title", "")
        year = str((bib.get("journal") or {}).get("year") or "")
        abstract = (bib.get("abstract") or "")[:1500]

        out.append(
            ExternalSource(
                title=title,
                source_type="academic",
                url=url_out,
                year=year,
                authors=", ".join(authors),
                publisher=venue,
                doi=doi,
                verified_by="DOAJ peer-reviewed OA journal index",
                abstract=abstract,
                provider="doaj",
                # DOAJ only indexes journals that meet its peer-review policy requirements.
                is_peer_reviewed=True,
                # DOAJ = Directory of Open Access Journals — open access is
                # the indexing criterion, not an inference.
                is_open_access=True,
                fulltext_url=url_out,
            )
        )
        if len(out) >= rows:
            break
    return out, None


async def _verify_doi(client: httpx.AsyncClient, doi: str, claimed_title: str) -> bool:
    if not doi:
        return False
    try:
        async def _do():
            return await client.get(
                f"https://doi.org/{quote_plus(doi, safe='/')}",
                headers={"Accept": "application/vnd.citationstyles.csl+json"},
            )
        r = await call_with_throttle("doi_resolver", _do)
        if r.status_code >= 400:
            return False
        data = r.json()
        resolved_title = str(data.get("title") or "").strip()
        if not resolved_title:
            return False
        resolved_tokens = _tokenize(resolved_title)
        claimed_tokens = _tokenize(claimed_title)
        if not resolved_tokens or not claimed_tokens:
            return False
        overlap = len(resolved_tokens & claimed_tokens) / max(1, min(len(resolved_tokens), len(claimed_tokens)))
        return overlap >= 0.6
    except Exception:
        return False


async def _pubmed_sources(client: httpx.AsyncClient, query: str, rows: int = 6) -> tuple[list[ExternalSource], Optional[str]]:
    term = quote_plus(query)
    search_url = (
        "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        f"?db=pubmed&retmode=json&retmax={rows}&sort=relevance&term={term}"
    )
    try:
        async def _do_search():
            sr = await client.get(search_url)
            sr.raise_for_status()
            return sr
        sr = await call_with_throttle("pubmed", _do_search)
        ids = ((sr.json().get("esearchresult") or {}).get("idlist") or [])[:rows]
    except Exception as exc:
        log.warning("PubMed search failed: %s", exc)
        return [], f"PUBMED_PROVIDER_UNAVAILABLE: {exc.__class__.__name__}"

    out: list[ExternalSource] = []
    for pmid in ids:
        sum_url = (
            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
            f"?db=pubmed&retmode=json&id={pmid}"
        )
        try:
            async def _do_summary():
                sm = await client.get(sum_url)
                sm.raise_for_status()
                return sm
            sm = await call_with_throttle("pubmed", _do_summary)
            data = sm.json().get("result") or {}
            rec = data.get(str(pmid)) or {}
        except Exception:
            continue

        title = (rec.get("title") or "").strip()
        if not title:
            continue
        pub_url = f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/"
        year = str(rec.get("pubdate") or "").split(" ")[0]
        out.append(
            ExternalSource(
                title=title,
                source_type="academic",
                url=pub_url,
                year=year,
                publisher="PubMed",
                verified_by="PubMed E-utilities",
                provider="pubmed",
                # PubMed indexes the biomedical/clinical literature, which is
                # editorially/peer-reviewed as a condition of indexing.
                is_peer_reviewed=True,
            )
        )
    return out, None


async def _arxiv_sources(client: httpx.AsyncClient, query: str, rows: int = 6) -> tuple[list[ExternalSource], Optional[str]]:
    q = quote_plus(query)
    api = (
        "http://export.arxiv.org/api/query"
        f"?search_query=all:{q}&start=0&max_results={rows}&sortBy=relevance&sortOrder=descending"
    )
    try:
        async def _do():
            r = await client.get(api)
            r.raise_for_status()
            return r
        r = await call_with_throttle("arxiv", _do)
        xml = r.text
    except Exception as exc:
        log.warning("arXiv lookup failed: %s", exc)
        return [], f"ARXIV_PROVIDER_UNAVAILABLE: {exc.__class__.__name__}"

    entries = re.findall(r"<entry>(.*?)</entry>", xml, flags=re.DOTALL)
    out: list[ExternalSource] = []
    for e in entries:
        t = re.search(r"<title>(.*?)</title>", e, flags=re.DOTALL)
        i = re.search(r"<id>(.*?)</id>", e, flags=re.DOTALL)
        p = re.search(r"<published>(.*?)</published>", e, flags=re.DOTALL)
        a = re.search(r"<summary>(.*?)</summary>", e, flags=re.DOTALL)
        if not t or not i:
            continue
        title = re.sub(r"\\s+", " ", t.group(1)).strip()
        url = i.group(1).strip()
        year = (p.group(1)[:4] if p else "")
        abstract = re.sub(r"\s+", " ", (a.group(1) if a else "")).strip()
        if not _host_ok(url):
            continue
        out.append(
            ExternalSource(
                title=title,
                source_type="academic",
                url=url,
                year=year,
                publisher="arXiv",
                verified_by="arXiv API",
                abstract=abstract,
                provider="arxiv",
                # arXiv is a preprint server — explicitly not peer-reviewed.
                is_peer_reviewed=False,
                # arXiv preprints are always freely downloadable, by design.
                is_open_access=True,
                fulltext_url=url,
            )
        )
    return out, None


async def _patent_sources(client: httpx.AsyncClient, topic: str, domain_label: str) -> tuple[list[ExternalSource], Optional[str]]:
    payload = {
        "q": {"_text_any": {"patent_title": f"{topic} {domain_label} x ray detector cargo security"}},
        "f": ["patent_number", "patent_title", "patent_date", "assignee_organization"],
        "o": {"per_page": 4},
    }
    url = "https://api.patentsview.org/patents/query"
    try:
        async def _do():
            r = await client.post(url, json=payload)
            r.raise_for_status()
            return r
        r = await call_with_throttle("patentsview", _do)
        rows = r.json().get("patents") or []
        status: Optional[str] = None
    except Exception as exc:
        log.warning("PatentsView lookup failed: %s", exc)
        rows = []
        status = f"PATENT_PROVIDER_UNAVAILABLE: {exc.__class__.__name__}"

    out: list[ExternalSource] = []
    for row in rows:
        number = (row.get("patent_number") or "").strip()
        title = (row.get("patent_title") or "").strip()
        date = (row.get("patent_date") or "").strip()
        if not number or not title:
            continue
        patent_url = f"https://patents.google.com/patent/US{number}"
        out.append(
            ExternalSource(
                title=title,
                source_type="patent",
                url=patent_url,
                year=(date[:4] if len(date) >= 4 else ""),
                publisher=(row.get("assignee_organization") or "").strip(),
                patent_number=f"US {number}",
                verified_by="PatentsView + Google Patents page",
                # Granted patents are public record — legally accessible in
                # full by design, no paywall/login ever applies.
                is_open_access=True,
                fulltext_url=patent_url,
                academic_source_type="patent",
            )
        )
    if not out and status is None:
        status = "PATENT_SEARCH_VERIFIED_ZERO_RESULTS"
    return out, status


def _ddg_extract_result_urls(html: str) -> list[str]:
    links = re.findall(r'<a[^>]+class="result__a"[^>]+href="([^"]+)"', html)
    out: list[str] = []
    for raw in links:
        href = raw
        if "uddg=" in href:
            qs = parse_qs(urlparse(href).query)
            uddg = qs.get("uddg", [""])[0]
            if uddg:
                href = unquote(uddg)
        if href.startswith("http"):
            out.append(href)
    return out


async def _standards_and_regulatory_sources(client: httpx.AsyncClient, topic: str) -> tuple[list[ExternalSource], Optional[str]]:
    queries = [
        f"{topic} IEC standard",
        f"{topic} ISO standard",
        f"{topic} NIST x-ray guidance",
        f"{topic} IAEA x-ray safety",
        f"{topic} TSA screening standard",
        f"{topic} ECAC security screening specification",
    ]
    out: list[ExternalSource] = []
    query_failures = 0

    for q in queries:
        ddg = f"https://duckduckgo.com/html/?q={quote_plus(q)}"
        try:
            async def _do(ddg=ddg):
                r = await client.get(ddg)
                r.raise_for_status()
                return r
            r = await call_with_throttle("web_search", _do)
        except Exception:
            query_failures += 1
            continue

        for url in _ddg_extract_result_urls(r.text)[:2]:
            if not _host_ok(url):
                continue
            # Avoid full page fetch for title extraction to keep latency bounded.
            title = url

            std_match = _STD_NUMBER_RE.search(title + " " + url)
            standard_number = std_match.group(0).upper() if std_match else ""
            source_type = "standard" if standard_number else "regulator"

            out.append(
                ExternalSource(
                    title=title,
                    source_type=source_type,
                    url=url,
                    standard_number=standard_number,
                    verified_by="Authoritative domain URL check",
                )
            )

    if out:
        return out, None
    if query_failures == len(queries):
        return [], "STANDARDS_PROVIDER_UNAVAILABLE: DuckDuckGo query failed for all standards searches"
    return [], "STANDARDS_SEARCH_VERIFIED_ZERO_RESULTS"


def _extract_html_title(html: str) -> str:
    match = re.search(r"<title[^>]*>(.*?)</title>", html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    title = re.sub(r"\s+", " ", match.group(1)).strip()
    title = re.sub(r"\s*[\-|•|–|—]\s*.*$", "", title)
    return title.strip()


async def _manufacturer_sources(client: httpx.AsyncClient, topic: str) -> tuple[list[ExternalSource], Optional[str]]:
    queries = [
        f"{topic} site:rapiscansystems.com manual datasheet brochure",
        f"{topic} site:smithsdetection.com manual datasheet brochure",
        f"{topic} site:nuctech.com manual datasheet brochure",
        f"{topic} site:leidos.com security screening brochure",
        f"{topic} site:astrophysicsinc.com x-ray inspection brochure",
    ]
    out: list[ExternalSource] = []
    query_failures = 0

    for q in queries:
        ddg = f"https://duckduckgo.com/html/?q={quote_plus(q)}"
        try:
            async def _do_search(ddg=ddg):
                r = await client.get(ddg)
                r.raise_for_status()
                return r
            r = await call_with_throttle("web_search", _do_search)
        except Exception:
            query_failures += 1
            continue

        for url in _ddg_extract_result_urls(r.text)[:3]:
            if not _host_ok(url):
                continue
            try:
                async def _do_fetch(url=url):
                    page = await client.get(url)
                    page.raise_for_status()
                    return page
                page = await call_with_throttle("direct_crawl", _do_fetch)
                title = _extract_html_title(page.text) or url
            except Exception:
                title = url
            out.append(
                ExternalSource(
                    title=title,
                    source_type="manufacturer",
                    url=url,
                    publisher=urlparse(url).hostname or "Manufacturer",
                    verified_by="Manufacturer documentation page",
                )
            )

    if out:
        return out, None
    if query_failures == len(queries):
        return [], "MANUFACTURER_PROVIDER_UNAVAILABLE: DuckDuckGo query failed for all manufacturer searches"
    return [], "MANUFACTURER_SEARCH_VERIFIED_ZERO_RESULTS"


def _source_quality_score(source: ExternalSource) -> float:
    """Deterministic ranking score: recency + citation strength + verification signals.

    Used to rank a large deduped candidate pool down to the strongest references —
    not a relevance filter (that's `_is_relevant`), a quality/authority ranking on
    top of it.
    """
    score = source.relevance_score
    try:
        year = int(source.year) if source.year else 0
    except ValueError:
        year = 0
    if year:
        # Mild recency bonus, capped — a 2024 paper should not automatically
        # outrank a foundational 2015 paper with 10x the citations.
        score += max(0.0, min(2.0, (year - 2010) * 0.08))
    if source.citation_count:
        import math
        score += min(2.5, math.log1p(source.citation_count) * 0.6)
    if source.doi_verified:
        score += 1.5
    if source.is_peer_reviewed:
        score += 1.0
    if source.is_retracted:
        score -= 10.0
    source.quality_score = score
    return score


async def perform_hybrid_external_research(queries: list[str] | str, domain_label: str) -> ExternalResearchResult:
    """
    Run live internet research against authoritative source types.

    `queries` is normally a small set of expanded search queries (base topic +
    synonym variants + relevant concept queries) so retrieval isn't starved down
    to whatever a single narrow query string happens to return. A bare string is
    still accepted (wrapped as a single-element list) for callers that only have
    one topic string.

    Returns only sources that pass basic source-authority and relevance checks,
    ranked by `_source_quality_score` (highest first).
    """
    if isinstance(queries, str):
        queries = [queries]
    queries = [q.strip() for q in queries if q and q.strip()] or [domain_label]
    primary_topic = queries[0]

    try:
        from api.config import settings
        s2_key = settings.semantic_scholar_api_key
        core_key = settings.core_api_key
    except Exception:
        s2_key = ""
        core_key = ""

    timeout = httpx.Timeout(12.0, read=20.0)
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    searched_sources = [
        "Crossref", "OpenAlex", "Semantic Scholar", "PubMed", "arXiv", "CORE", "DOAJ",
        "PatentsView/Google Patents",
        "ISO/IEC/NIST/IAEA/TSA/ECAC authoritative pages",
        "Manufacturer documentation",
    ]

    sem = asyncio.Semaphore(10)

    async def _bounded(coro):
        async with sem:
            return await coro

    async with httpx.AsyncClient(timeout=timeout, headers=headers, follow_redirects=True) as client:
        academic_tasks = []
        for q in queries:
            academic_tasks.append(_bounded(_crossref_sources(client, q)))
            academic_tasks.append(_bounded(_openalex_sources(client, q)))
            academic_tasks.append(_bounded(_semantic_scholar_sources(client, q, api_key=s2_key)))
            academic_tasks.append(_bounded(_pubmed_sources(client, q)))
            academic_tasks.append(_bounded(_arxiv_sources(client, q)))
            academic_tasks.append(_bounded(_core_sources(client, q, api_key=core_key)))
            academic_tasks.append(_bounded(_doaj_sources(client, q)))

        patent_task = _patent_sources(client, primary_topic, domain_label)
        std_task = _standards_and_regulatory_sources(client, primary_topic)
        manufacturer_task = _manufacturer_sources(client, primary_topic)

        academic_results, (patents, patent_status), (standards, standards_status), (manufacturers, manufacturers_status) = await asyncio.gather(
            asyncio.gather(*academic_tasks),
            patent_task,
            std_task,
            manufacturer_task,
        )

    academic_raw: list[ExternalSource] = []
    academic_warnings: list[str] = []
    for sources_batch, status in academic_results:
        academic_raw.extend(sources_batch)
        if status:
            academic_warnings.append(status)
    # Same provider can fail on some queries and succeed on others — only
    # surface a provider-unavailable warning once, not once per query.
    academic_warnings = sorted(set(academic_warnings))

    academic = _dedupe_sources(academic_raw)
    academic = [s for s in academic if _is_relevant(s, primary_topic, domain_label)]

    # Live DOI verification on the surviving deduped set only (not per raw
    # candidate) to keep total HTTP calls bounded.
    async with httpx.AsyncClient(timeout=httpx.Timeout(8.0, read=10.0), headers=headers, follow_redirects=True) as verify_client:
        async def _verify(s: ExternalSource) -> None:
            if s.doi:
                s.doi_verified = await _bounded(_verify_doi(verify_client, s.doi, s.title))
        await asyncio.gather(*(_verify(s) for s in academic))

    for s in academic:
        _source_quality_score(s)
    academic.sort(key=lambda s: s.quality_score, reverse=True)

    raw_sources = academic + patents + standards + manufacturers
    sources = [s for s in raw_sources if s.source_type == "academic" or _is_relevant(s, primary_topic, domain_label)]

    warnings: list[str] = list(academic_warnings)
    for st in [patent_status, standards_status, manufacturers_status]:
        if st:
            warnings.append(st)

    academic_count = sum(1 for s in sources if s.source_type == "academic")
    patent_count = sum(1 for s in sources if s.source_type == "patent")
    standards_count = sum(1 for s in sources if s.source_type in {"standard", "regulator"})
    manufacturer_count = sum(1 for s in sources if s.source_type == "manufacturer")

    if academic_count == 0:
        warnings.append("No verified external academic literature was found during live search.")
    if patent_count == 0:
        if any(w.startswith("PATENT_PROVIDER_UNAVAILABLE") for w in warnings):
            warnings.append("Patent provider unavailable during live prior-art search.")
        else:
            warnings.append("No verified patent records were found during live prior-art search.")
    if standards_count == 0:
        if any(w.startswith("STANDARDS_PROVIDER_UNAVAILABLE") for w in warnings):
            warnings.append("Standards providers were unavailable during live standards search.")
        else:
            warnings.append("No verified standards/regulatory references were found during live standards search.")
    if manufacturer_count == 0:
        if any(w.startswith("MANUFACTURER_PROVIDER_UNAVAILABLE") for w in warnings):
            warnings.append("Manufacturer documentation providers were unavailable during live vendor-document search.")
        else:
            warnings.append("No verified manufacturer documentation was found during live vendor-document search.")
    if not sources:
        warnings.append(
            "External internet research could not be completed. Output must be treated as draft and not submission-ready."
        )

    return ExternalResearchResult(
        sources=sources,
        searched_at_utc=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        searched_sources=searched_sources,
        warnings=warnings,
    )
