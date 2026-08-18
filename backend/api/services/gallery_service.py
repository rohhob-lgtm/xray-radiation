"""
Gallery search service — intent detection, query extraction, and image search.
Powers the AI Chat → Image Gallery connection.
"""
from __future__ import annotations
import json
import logging
import math
import re
from typing import List, Optional, Dict, Any, TYPE_CHECKING

from sqlalchemy.orm import Session

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Intent detection
# ──────────────────────────────────────────────────────────

# Patterns that strongly indicate the user wants images from the gallery
_IW = r"(?:images?|photos?|pictures?|scans?\b|diagrams?|figures?|charts?|screenshots?)"

_GALLERY_INTENT_RE = re.compile(
    r"\b("
    # Explicit gallery commands
    r"search\s+gallery|gallery\s+search|image\s+search|"
    # "search [for] NOUN images" — image word at end
    r"search\s+(?:for\s+)?(?:[\w-]+\s+){0,5}" + _IW + r"\b|"
    # "show [me] NOUN images" — image word at end
    r"show\s+(?:me\s+)?(?:[\w-]+\s+){0,5}" + _IW + r"\b|"
    # "show [me] images of NOUN" — image word right after show/me
    r"show\s+(?:me\s+)?" + _IW + r"\s+of\s+|"
    # "find [me] NOUN images/photo"
    r"find\s+(?:me\s+)?(?:[\w-]+\s+){0,5}" + _IW + r"\b|"
    # display / open / browse / view
    r"display\s+(?:[\w-]+\s+){0,4}" + _IW + r"\b|"
    r"open\s+gallery|browse\s+gallery|view\s+gallery|"
    # get / retrieve / look for
    r"look\s+(?:up|for)\s+(?:[\w-]+\s+){0,4}" + _IW + r"\b|"
    r"get\s+(?:me\s+)?(?:[\w-]+\s+){0,4}" + _IW + r"\b|"
    r"retrieve\s+(?:[\w-]+\s+){0,4}" + _IW + r"\b|"
    # descriptive
    r"what\s+does\s+.+\s+look\s+like|"
    r"" + _IW + r"\s+of\b"
    r")",
    re.IGNORECASE,
)

# Patterns for bare "search gallery" with no subject
_BARE_GALLERY_RE = re.compile(
    r"^(search\s+gallery|open\s+gallery|browse\s+gallery|view\s+gallery|gallery)$",
    re.IGNORECASE,
)

# "Show me a/an/the <object>" — the common elliptical way people ask for a
# reference photo without ever saying "picture"/"photo"/"image" explicitly
# ("Show me a magnetron" == "Show me a photo of a magnetron"). Deliberately
# narrow (a bare 1-3 word noun phrase, nothing else in the message) so it
# doesn't swallow "show me a summary/example/way to..." meta-requests —
# those are excluded via _BARE_NOUN_META_STOPLIST below regardless of how
# well they'd otherwise match the shape.
_BARE_NOUN_IMAGE_RE = re.compile(
    r"^show\s+me\s+(?:a|an|the)\s+([a-z][\w-]*(?:\s+[a-z][\w-]*){0,2})[.?!]*$",
    re.IGNORECASE,
)
_BARE_NOUN_META_STOPLIST = {
    "summary", "example", "overview", "way", "list", "explanation", "answer",
    "breakdown", "comparison", "table", "guide", "tutorial", "walkthrough",
    "demo", "demonstration", "code", "script", "command", "report", "plan",
    "sample", "outline", "description", "definition", "recap",
}


def _is_bare_noun_image_request(message: str) -> bool:
    m = _BARE_NOUN_IMAGE_RE.match(message.strip())
    if not m:
        return False
    phrase = m.group(1).strip().lower()
    if phrase in _BARE_NOUN_META_STOPLIST:
        return False
    # Also reject when the head noun itself is a meta-word ("the way
    # forward", "an overview here") — the stoplist check above only
    # catches an exact single-word match.
    return phrase.split()[0] not in _BARE_NOUN_META_STOPLIST

# Patterns for extracting the search subject from image requests
_IMAGE_WORDS = r"(?:images?|photos?|pictures?|scans?\b|diagrams?|figures?|charts?|screenshots?)"
_QUERY_EXTRACTION_PATTERNS = [
    # "search gallery for LZBV-S [images]"
    re.compile(r"search\s+gallery\s+for\s+(.+?)(?:\s+" + _IMAGE_WORDS + r")?$", re.IGNORECASE),
    # "search for LZBV-S images"
    re.compile(r"search\s+for\s+(.+?)\s+" + _IMAGE_WORDS + r"$", re.IGNORECASE),
    # "show me vehicle scanner images" / "show LZBV-S photos"
    re.compile(r"show\s+(?:me\s+)?(.+?)\s+" + _IMAGE_WORDS + r"$", re.IGNORECASE),
    # "find LZBV-S images" / "find cargo scanner photo"
    re.compile(r"find\s+(?:me\s+)?(.+?)\s+" + _IMAGE_WORDS + r"$", re.IGNORECASE),
    # "display image of LZBV-S"
    re.compile(r"display\s+" + _IMAGE_WORDS + r"\s+of\s+(.+?)$", re.IGNORECASE),
    # "image of LZBV-S" / "photo of vehicle scanner"
    re.compile(r"" + _IMAGE_WORDS + r"\s+of\s+(.+?)$", re.IGNORECASE),
    # "search gallery" bare — handled upstream, returns None
    re.compile(r"search\s+gallery$", re.IGNORECASE),
    # fallback: "show me LZBV-S" (image word already stripped by intent)
    re.compile(r"show\s+(?:me\s+)?(.+?)$", re.IGNORECASE),
]

_STOP_QUERY_WORDS = {
    "me", "the", "a", "an", "some", "any", "all", "please", "can", "you",
    "could", "would", "i", "we", "my", "our", "get", "find", "show", "search",
    "for", "of", "in", "from", "gallery", "image", "images", "photo", "photos",
    "picture", "pictures", "scan", "scans", "diagram", "diagrams", "figure",
    "figures", "related", "similar", "about", "like",
}

# ──────────────────────────────────────────────────────────
# Arabic reference-image lookup (urgent regression fix)
# ──────────────────────────────────────────────────────────
# _GALLERY_INTENT_RE above is English-only, so an Arabic reference-image
# request like "اعرض صورة للـ LINAC" never reached IMAGE_SEARCH — it fell
# through to plain general chat instead, where the model has no image tool
# at all and would sometimes hallucinate a fake tool-call JSON blob as its
# answer text (see chat.py's leak guard). Generation verbs (ارسم/صمم/ولّد =
# draw/design/generate) are deliberately excluded here: those aren't a
# reference-image lookup and must not trigger a gallery/internet search for
# the word "draw" itself.
_AR_GENERATION_VERBS_RE = re.compile(
    r"(ارسم|ارسمي|صمم|صممي|أنشئ|انشئ|اصنع|اصنعي|ولّد|ولد|وضح\s+بالرسم)"
)

_AR_IMAGE_LOOKUP_RE = re.compile(
    r"(اعرض|اعرضي|أرني|ارني|وريني|أظهر|اظهر|ابحث(?:\s+لي)?|دور(?:\s+لي)?|هات|جيب(?:\s+لي)?)"
    r"[^.؟!\n]{0,25}"
    r"(صور[ةه]?|رسم(?:\s+توضيحي)?|مخطط|شكل\s+توضيحي)"
)

# Trims trailing meta-instructions ("search the internet or the database")
# that aren't part of the actual search subject.
_AR_QUERY_STOP_RE = re.compile(r"\s*(ابحث.*|في\s+الانترنت.*|في\s+قاعد[ةه].*)$")

_AR_QUERY_EXTRACTION_RE = re.compile(
    r"(?:صور[ةه]?|رسم(?:\s+توضيحي)?|مخطط|شكل\s+توضيحي)\s*(.+)$"
)
_AR_QUERY_PREFIX_RE = re.compile(r"^(?:لل|ل|عن|من)?[ـ\s]*")


def _is_arabic_image_lookup(message: str) -> bool:
    if not message or _AR_GENERATION_VERBS_RE.search(message):
        return False
    return bool(_AR_IMAGE_LOOKUP_RE.search(message))


def _extract_arabic_gallery_query(message: str) -> Optional[str]:
    m = _AR_QUERY_EXTRACTION_RE.search(message)
    if not m:
        return None
    raw = m.group(1).strip()
    raw = _AR_QUERY_STOP_RE.sub("", raw).strip()
    raw = _AR_QUERY_PREFIX_RE.sub("", raw, count=1).strip(" .؟!")
    return raw or None


def detect_intent(query: str) -> str:
    """
    Returns one of: "IMAGE_SEARCH" | "DOCUMENT_SEARCH" | "GENERAL_CHAT"
    IMAGE_SEARCH → route to gallery search API
    DOCUMENT_SEARCH → route to text RAG
    GENERAL_CHAT → use agent system prompt + general knowledge
    """
    q = query.strip()
    if _GALLERY_INTENT_RE.search(q) or _is_arabic_image_lookup(q) or _is_bare_noun_image_request(q):
        logger.info("[intent] IMAGE_SEARCH detected for: %r", q[:80])
        return "IMAGE_SEARCH"
    return "GENERAL_CHAT"


def extract_gallery_query(message: str) -> Optional[str]:
    """
    Extract the actual search subject from an image request.
    "search gallery for LZBV-S" → "LZBV-S"
    "show me vehicle scanner images" → "vehicle scanner"
    "search gallery" → None  (bare command — show recent/browse)
    """
    msg = message.strip()

    # Bare gallery command → no search term
    if _BARE_GALLERY_RE.match(msg):
        return None

    if _is_arabic_image_lookup(msg):
        result = _extract_arabic_gallery_query(msg)
        if result:
            logger.info("[intent] extracted Arabic gallery query: %r -> %r", msg[:60], result)
            return result

    for pat in _QUERY_EXTRACTION_PATTERNS:
        m = pat.search(msg)
        if m:
            raw = m.group(1).strip()
            # Filter stop words from the extracted query
            words = [w for w in raw.split() if w.lower() not in _STOP_QUERY_WORDS]
            if words:
                result = " ".join(words)
                logger.info("[intent] extracted gallery query: %r → %r", msg[:60], result)
                return result

    return None


# ──────────────────────────────────────────────────────────
# Fuzzy / normalized matching helpers
# ──────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Normalize model names: remove spaces, hyphens, underscores, lowercase."""
    return re.sub(r"[\s\-_]", "", text).lower()


def _model_match_score(query: str, field: str) -> float:
    """Return 1.0 on exact normalized match, 0.5 on partial, 0.0 otherwise."""
    qn = _normalize(query)
    fn = _normalize(field)
    if not qn or not fn:
        return 0.0
    if qn == fn:
        return 1.0
    if qn in fn or fn in qn:
        return 0.7
    # Check all individual query words
    parts = [_normalize(w) for w in query.split()]
    if any(p in fn for p in parts if len(p) >= 3):
        return 0.4
    return 0.0


def _keyword_score(query: str, text: str) -> float:
    """Simple keyword overlap score ignoring case."""
    if not query or not text:
        return 0.0
    terms = [t.lower() for t in re.findall(r"\b\w{2,}\b", query) if t.lower() not in _STOP_QUERY_WORDS]
    if not terms:
        return 0.0
    lower = text.lower()
    hits = sum(1 for t in terms if t in lower)
    return hits / len(terms)


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


# ──────────────────────────────────────────────────────────
# Gallery search
# ──────────────────────────────────────────────────────────

def _gallery_record_to_dict(g) -> Dict[str, Any]:
    return {
        "image_id": g.rag_page_id,
        "gallery_index_id": g.id,
        "title": g.title or g.doc_filename,
        "image_url": g.image_url or f"/api/rag/pages/{g.rag_page_id}",
        "thumbnail_url": g.thumbnail_url or f"/api/rag/pages/{g.rag_page_id}",
        "caption": g.caption or "",
        "tags": g.tags or [],
        "source_document": g.doc_filename,
        "page_number": g.page_num,
        "scanner_model": g.scanner_model or "",
        "manufacturer": g.manufacturer or "",
        "category": g.category or "",
    }


async def search_gallery(
    query: Optional[str],
    db: Session,
    top_k: int = 6,
) -> List[Dict[str, Any]]:
    """
    Search the gallery index. If query is None, return recent images.

    Cost cascade (cheapest first — skips expensive steps when early match is strong):
      1. Text/keyword scoring   — zero API calls, zero cost
      2. Semantic embedding     — one OpenAI call (~$0.000020), skipped when
                                  keyword score already ≥ 0.80 for the top result

    Results are cached for 5 minutes (TTL) to avoid repeated DB scans and
    embedding calls for the same query. ColPali/OpenCLIP is NEVER loaded here.
    """
    import time as _time
    from api.services.cache_service import gallery_cache, embed_cache
    from api.db.models import GalleryIndex

    t0 = _time.monotonic()
    cache_key = f"gallery:{(query or '').lower().strip()}:{top_k}"

    # ── Cache hit — return immediately, zero cost ──────────────────────────
    cached = gallery_cache.get(cache_key)
    if cached is not None:
        logger.info("[gallery_search] cache_hit query=%r results=%d cost=$0.000000",
                    query, len(cached))
        return cached

    records = db.query(GalleryIndex).all()
    if not records:
        return []

    if not query:
        # No query — return most recently indexed images
        recent = sorted(records, key=lambda r: r.indexed_at, reverse=True)
        result = [_gallery_record_to_dict(r) for r in recent[:top_k]]
        gallery_cache.set(cache_key, result)
        return result

    # ── Step 1: keyword scoring (free) ────────────────────────────────────
    scored_kw = []
    for g in records:
        model_score  = _model_match_score(query, g.scanner_model) if g.scanner_model else 0.0
        tag_text     = " ".join(g.tags) if g.tags else ""
        tag_score    = _keyword_score(query, tag_text) * 0.9
        caption_score= _keyword_score(query, (g.caption or "") + " " + (g.description or "")) * 0.7
        title_score  = _keyword_score(query, (g.title or "") + " " + g.doc_filename) * 0.6
        ocr_score    = _keyword_score(query, g.ocr_text or "") * 0.4
        kw_total     = max(model_score, tag_score) + caption_score + title_score + ocr_score
        scored_kw.append((kw_total, g))

    scored_kw.sort(key=lambda x: x[0], reverse=True)
    top_kw_score = scored_kw[0][0] if scored_kw else 0.0

    # ── Step 2: semantic boost (1 OpenAI call) — only when keyword match is weak
    # If the best keyword score is already strong (≥ 0.80) the embedding adds
    # almost nothing; skip the API call entirely to save cost.
    query_embedding: Optional[List[float]] = None
    embedding_used  = False
    embedding_cost  = 0.0

    if top_kw_score < 0.80:
        embed_key = f"embed:{query[:200].lower()}"
        query_embedding = embed_cache.get(embed_key)
        if query_embedding is None:
            try:
                from api.services.rag_service import _get_embedding
                query_embedding = await _get_embedding(query)
                if query_embedding:
                    embed_cache.set(embed_key, query_embedding)
                    embedding_used = True
                    # text-embedding-3-small: $0.020 / 1M tokens; query ≈ 10 tokens
                    embedding_cost = round(10 * 0.020 / 1_000_000, 8)
            except Exception:
                pass
        else:
            embedding_used = True  # served from cache — $0 cost

    # ── Combine scores ────────────────────────────────────────────────────
    scored: List[tuple] = []
    for kw_total, g in scored_kw:
        sem_score = 0.0
        if query_embedding and g.embedding:
            sem_score = max(0.0, _cosine(query_embedding, g.embedding)) * 0.5
        total = kw_total + sem_score
        if total > 0.05:
            scored.append((total, g))

    scored.sort(key=lambda x: x[0], reverse=True)
    result = [_gallery_record_to_dict(g) for _, g in scored[:top_k]]

    elapsed = round(_time.monotonic() - t0, 3)
    logger.info(
        "[gallery_search] query=%r → %d candidates, %d results "
        "keyword_score=%.2f embedding_used=%s cost=$%.6f elapsed=%.3fs "
        "vision_model_loaded=No",
        query, len(records), len(result),
        top_kw_score, embedding_used, embedding_cost, elapsed,
    )

    gallery_cache.set(cache_key, result)
    return result


async def search_gallery_for_chat(
    query: Optional[str],
    db: Session,
) -> Dict[str, Any]:
    """
    High-level entry point for chat: returns the full image_results payload.
    """
    images = await search_gallery(query, db, top_k=6)
    return {
        "type": "image_results",
        "query": query or "",
        "count": len(images),
        "images": images,
    }


# ──────────────────────────────────────────────────────────
# Semantic synonym expansion for image queries
# ──────────────────────────────────────────────────────────
# A domain image request rarely uses the exact wording a caption/tag was
# indexed with. "material discrimination", "dual-energy", "Z-effective" and
# "organic/inorganic colour coding" all describe the SAME imaging concept, so
# a literal keyword match on one of them must also surface figures indexed
# under the others — and the same expansion gives the internet-fallback query
# a better chance of a hit. Each set is a group of interchangeable phrases;
# matching any member pulls in the rest as extra search terms.
# Ordered most-distinctive-first: the cap below keeps the head of each list,
# so the canonical alternatives (e.g. "dual-energy x-ray", "z-effective") are
# never dropped in favour of a near-duplicate spelling variant.
_IMAGE_SYNONYM_GROUPS: List[List[str]] = [
    [
        "material discrimination", "dual-energy x-ray", "dual energy",
        "z-effective", "effective atomic number", "organic inorganic color coding",
        "material classification", "material identification",
        "baggage color interpretation", "x-ray color coding", "zeff",
    ],
    [
        "baggage scanner", "baggage x-ray", "cabinet x-ray", "hold baggage",
        "carry-on scanner", "checkpoint scanner", "parcel scanner",
    ],
    [
        "cargo scanner", "vehicle scanner", "container scanner", "gantry scanner",
        "drive-through scanner", "mobile scanner",
    ],
    [
        "computed tomography", "ct scanner", "ct reconstruction", "3d imaging",
        "tomographic reconstruction", "slice reconstruction",
    ],
    [
        "threat detection", "automatic threat recognition", "atr",
        "explosive detection", "weapon detection",
    ],
    [
        "linac", "linear accelerator", "electron accelerator", "magnetron",
        "waveguide", "rf accelerator",
    ],
]


def expand_image_query(query: Optional[str]) -> List[str]:
    """Return ``[original, *synonyms]`` for an image request — the original
    first (highest precision), then any interchangeable domain phrases so
    semantic-equivalent figures still match. Deduplicated, order-stable, and
    capped so a broadened query never explodes into dozens of terms."""
    if not query:
        return []
    original = query.strip()
    if not original:
        return []
    lowered = original.lower()
    expansions: List[str] = []
    seen = {lowered}
    for group in _IMAGE_SYNONYM_GROUPS:
        if any(phrase in lowered for phrase in group):
            for phrase in group:
                if phrase not in seen and phrase not in lowered:
                    seen.add(phrase)
                    expansions.append(phrase)
    return [original] + expansions[:8]


# ──────────────────────────────────────────────────────────
# Arabic → English image-query bridge
# ──────────────────────────────────────────────────────────
# The web image channels (Wikimedia Commons + the discover_sources/web_crawl
# fallback) and the synonym expansion above are all English-indexed. A raw
# Arabic query like "تمييز الالوان في انظمه فحص السيارات باشعه اكس" therefore
# matches nothing and returns zero images, even though the identical request in
# English ("X-ray material discrimination") resolves to real results. This
# bridge maps the Arabic domain vocabulary onto the same canonical English
# phrases the synonym groups are keyed on, so an Arabic request enters the exact
# path that already works. Anything the static map can't place is handed to a
# short LLM translation (hybrid) by translate_image_query().

_ARABIC_CHAR_RE = re.compile(r"[؀-ۿ]")
_AR_DIACRITICS_RE = re.compile(r"[ً-ْٰ]")


def _has_arabic(text: Optional[str]) -> bool:
    return bool(_ARABIC_CHAR_RE.search(text or ""))


def _normalize_ar(text: str) -> str:
    """Fold the orthographic variants people type informally (أ/إ/آ→ا, ة→ه,
    ى/ئ→ي, ؤ→و) and strip diacritics, so one pattern matches every spelling."""
    s = _AR_DIACRITICS_RE.sub("", text or "")
    for a, b in (("أ", "ا"), ("إ", "ا"), ("آ", "ا"), ("ٱ", "ا"),
                 ("ى", "ي"), ("ئ", "ي"), ("ؤ", "و"), ("ة", "ه")):
        s = s.replace(a, b)
    return s


# (pattern over normalized Arabic) → canonical English phrase(s). Each English
# value is chosen to be a substring of, or equal to, a member of an
# _IMAGE_SYNONYM_GROUPS entry so the existing expansion fires downstream.
_AR_IMAGE_TERM_MAP: List[tuple] = [
    (re.compile(r"(تميي?ز|فصل|ترميز|تلوين)\s*(?:ال)?الوان|الترميز\s+اللوني|التميي?ز\s+اللوني"),
     "material discrimination x-ray color coding"),
    (re.compile(r"(تميي?ز|تصنيف|فصل)\s+(?:ال)?موا?د|عضوي[ه]?\s*و?\s*غير\s*عضوي|المعادن"),
     "material discrimination"),
    (re.compile(r"(?:ال)?طاق[ه]?\s*(?:ال)?مزدوج|(?:ال)?مزدوج[ه]?\s*(?:ال)?طاق|ثنائي[ه]?\s+(?:ال)?طاق|الطاقتين"),
     "dual-energy x-ray"),
    (re.compile(r"العدد\s+الذري|الرقم\s+الذري"), "effective atomic number"),
    (re.compile(r"فحص\s+(?:ال)?سيارات|فحص\s+(?:ال)?مركبات|فحص\s+(?:ال)?شاحنات|ماسح\s+(?:ال)?سيارات|بواب[ه]\s+فحص"),
     "vehicle scanner cargo scanner"),
    (re.compile(r"(?:فحص|ماسح)\s+(?:ال)?حقايب|فحص\s+(?:ال)?امتع[ه]|نقط[ه]\s+تفتيش"),
     "baggage scanner"),
    (re.compile(r"فحص\s+(?:ال)?شحن|الحاويات|ماسح\s+(?:ال)?شحن"), "cargo scanner"),
    (re.compile(r"ماجنترون|مغنطرون"), "magnetron"),
    (re.compile(r"مسرع\s+خطي|المسرع\s+الخطي|ليناك"), "linear accelerator linac"),
    (re.compile(r"التصوير\s+المقطعي|الاشع[ه]\s+المقطعي[ه]"), "computed tomography ct scanner"),
    (re.compile(r"كشف.{0,10}(?:متفجرات|اسلح[ه]|تهديدات)|المتفجرات"),
     "threat detection explosive detection"),
    (re.compile(r"الكثاف[ه]"), "density"),
]
_AR_XRAY_RE = re.compile(r"اشع[ه]\s*اكس|باشع[ه]\s*اكس|الاشع[ه]\s+السيني[ه]|سيني[ه]|اكس\s*راي")


def _arabic_to_english_image_query(query: Optional[str]) -> Optional[str]:
    """Static, zero-latency Arabic→English bridge for image queries. Returns an
    English search phrase built from the recognised domain terms, or None when
    the query carries no Arabic or none of its terms are recognised (caller then
    falls back to an LLM translation)."""
    if not query or not _has_arabic(query):
        return None
    norm = _normalize_ar(query)
    parts: List[str] = []
    for rx, en in _AR_IMAGE_TERM_MAP:
        if rx.search(norm):
            parts.append(en)
    if _AR_XRAY_RE.search(norm):
        parts.append("x-ray")
    if not parts:
        return None
    seen: set = set()
    words: List[str] = []
    for phrase in parts:
        for w in phrase.split():
            if w not in seen:
                seen.add(w)
                words.append(w)
    return " ".join(words)


async def _llm_translate_image_query(query: str, provider) -> Optional[str]:
    """Last-resort translation for an Arabic image query the static map can't
    place. Kept tiny (short reply, one call) so it only adds latency on the rare
    request that needs it. Never raises — a failure just leaves the query as-is."""
    system_prompt = (
        "You translate a user's IMAGE search request into a concise English search "
        "phrase (3-8 words) using X-ray security / industrial-imaging terminology. "
        "Reply with ONLY the phrase — no quotes, no punctuation, no explanation."
    )
    out = await provider.chat(
        [{"role": "user", "content": query}], system_prompt=system_prompt, max_tokens=32,
    )
    phrase = (out or "").strip().strip('"').strip()
    phrase = phrase.splitlines()[0].strip() if phrase else ""
    # Reject a refusal / non-answer / untranslated echo.
    if not phrase or len(phrase) > 120 or _has_arabic(phrase):
        return None
    return phrase


async def translate_image_query(query: Optional[str], provider=None) -> Optional[str]:
    """Return an English search query for an image request. English (or empty)
    queries pass through unchanged. An Arabic query is bridged to English —
    static domain map first (fast, no LLM), then a short LLM translation only if
    the static map didn't land on a recognised domain concept."""
    if not query or not _has_arabic(query):
        return query
    static = _arabic_to_english_image_query(query)
    # "Landed on a concept" == the English form triggers synonym expansion, which
    # is exactly what makes the web channels resolve. If so, skip the LLM.
    if static and len(expand_image_query(static)) > 1:
        return static
    if provider is not None:
        try:
            llm = await _llm_translate_image_query(query, provider)
            if llm:
                return llm
        except Exception:  # noqa: BLE001 - translation must never break the turn
            logger.info("[image_translate] LLM translation failed for %r", (query or "")[:60])
    return static or query


def _dedup_key(img: Dict[str, Any]) -> str:
    return (img.get("image_url") or img.get("source_url") or img.get("image_id") or "").strip().lower()


async def search_images_with_fallback(
    query: Optional[str],
    db: Session,
    *,
    enable_web: bool = True,
    min_local_results: int = 1,
) -> Dict[str, Any]:
    """Unified image search: local Knowledge Base first (with synonym
    broadening), then an automatic internet fallback when the local index is
    thin — never stops at "No matching images" without trying every allowed
    source. Every image is tagged ``origin`` ("local" | "web") and the payload
    reports which sources actually contributed via ``sources_used``.

    The internet fallback is intentionally NOT gated on an authenticated
    user — an anonymous/local session must still get web images when the KB
    has nothing (only ``settings.image_retrieval_enabled`` can disable it).
    """
    from api.config import settings

    queries = expand_image_query(query)

    # ── A/B/C. Local Knowledge Base (rendered pages + extracted figures) ──
    images: List[Dict[str, Any]] = await search_gallery(query, db, top_k=6)
    if len(images) < min_local_results:
        # Broaden with a bounded number of synonym re-searches (not all of them —
        # each is a DB scan, and 2 extra passes are plenty to catch a rewording).
        for alt in queries[1:3]:
            more = await search_gallery(alt, db, top_k=6)
            existing = {_dedup_key(i) for i in images}
            images.extend(m for m in more if _dedup_key(m) not in existing)
            if len(images) >= min_local_results:
                break
    for img in images:
        img.setdefault("origin", "local")

    sources_used: Dict[str, int] = {"local": len(images)}

    # ── D. Internet fallback — automatic, confidence/coverage driven ──
    if enable_web and settings.image_retrieval_enabled and len(images) < max(min_local_results, 1):
        import asyncio
        # Hard overall wall-clock cap so a slow/empty web round can never hang the
        # turn, regardless of per-attempt timeouts inside _web_image_fallback.
        total_budget = settings.image_retrieval_timeout_seconds * 2 + 2
        try:
            web_images = await asyncio.wait_for(
                _web_image_fallback(db, query, queries), timeout=total_budget,
            )
        except asyncio.TimeoutError:
            logger.info("[image_fallback] overall web budget (%.0fs) exceeded — returning local only", total_budget)
            web_images = []
        existing = {_dedup_key(i) for i in images}
        added = 0
        for w in web_images:
            key = _dedup_key(w)
            if key and key not in existing:
                existing.add(key)
                w.setdefault("origin", "web")
                images.append(w)
                added += 1
        if added:
            sources_used["web"] = added

    return {
        "type": "image_results",
        "query": query or "",
        "count": len(images),
        "images": images,
        "sources_used": sources_used,
    }


async def _web_image_fallback(db: Session, query: Optional[str], queries: List[str]) -> List[Dict[str, Any]]:
    """Bounded internet image retrieval via the existing Research Engine
    (``research_agent.image_discovery``). Tries the original query first, then
    a couple of synonym phrasings if it comes back empty, so a request worded
    differently from any indexed source still resolves."""
    import asyncio
    from api.config import settings
    # Imported through the module (not the names) so tests can monkeypatch
    # api.services.research_agent.image_discovery.discover_public_images.
    from api.services.research_agent import image_discovery

    # At most 2 web attempts — each does a live Wikimedia + crawl round-trip, so
    # looping every synonym would stack multi-second timeouts. The first query is
    # already domain-biased inside image_discovery; one synonym retry is enough.
    attempts = [q for q in (queries or [query or ""]) if q][:2]
    if not attempts:
        return []

    for attempt in attempts:
        try:
            found = await asyncio.wait_for(
                image_discovery.discover_public_images(attempt, settings.image_retrieval_max_images),
                timeout=settings.image_retrieval_timeout_seconds,
            )
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001 - fallback must never break the turn
            logger.info("[image_fallback] discover failed/timed out for %r", attempt)
            continue
        if not found:
            continue
        try:
            stored = await asyncio.wait_for(
                image_discovery.store_discovered_images(db, attempt, found),
                timeout=settings.image_retrieval_timeout_seconds,
            )
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            logger.info("[image_fallback] store failed/timed out for %r", attempt)
            continue
        if stored:
            logger.info("[image_fallback] query=%r matched via %r -> %d web image(s)", query, attempt, len(stored))
            return stored
    return []


# ──────────────────────────────────────────────────────────
# Reindex — generate rich metadata via GPT Vision
# ──────────────────────────────────────────────────────────

_REINDEX_PROMPT = """You are an expert X-ray imaging analyst cataloguing a visual knowledge base.

Analyse this document page image and return ONLY a JSON object (no extra text) with:
{
  "title": "Short descriptive title (max 80 chars)",
  "caption": "One concise sentence describing what is shown (max 200 chars)",
  "description": "Detailed description of the page content (2-4 sentences)",
  "tags": ["tag1", "tag2", "tag3", "tag4", "tag5"],
  "scanner_model": "Model name if visible (e.g. LZBV-S, ZBV, HCV, or empty string)",
  "manufacturer": "Manufacturer if identifiable (e.g. Rapiscan, Smiths, Nuctech, or empty string)",
  "category": "One of: x-ray_scan | diagram | chart | table | text | photograph | schematic | manual_page | other",
  "ocr_text": "Any significant text visible in the image (max 500 chars, or empty string)"
}

Tags should include: subject matter, scanner model, document type, key objects visible.
Return ONLY the JSON object, no markdown fences."""


async def reindex_page(page, provider) -> Dict[str, Any]:
    """Generate metadata for a single RagPage using GPT Vision."""
    import base64
    client = provider._client()
    model = provider._model()
    img_b64 = base64.b64encode(page.image_data).decode()
    try:
        resp = await client.chat.completions.create(
            model=model,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": _REINDEX_PROMPT},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                ],
            }],
            max_completion_tokens=600,
        )
        try:
            from api.utils.usage_recorder import record_usage_from_response
            record_usage_from_response(
                "Gallery Reindex", resp,
                sub_feature="page_vision",
                meta={"page_id": str(page.id), "doc": page.doc_filename},
            )
        except Exception:
            pass
        raw = (resp.choices[0].message.content or "").strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
        raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
        return json.loads(raw)
    except Exception as e:
        logger.warning("[reindex] GPT Vision failed for page %s: %s", page.id, e)
        return {
            "title": f"{page.doc_filename} — Page {page.page_num}",
            "caption": "",
            "description": "",
            "tags": [],
            "scanner_model": "",
            "manufacturer": "",
            "category": "other",
            "ocr_text": "",
        }
