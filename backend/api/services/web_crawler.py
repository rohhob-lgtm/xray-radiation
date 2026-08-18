"""
web_crawler.py — Enterprise-grade website crawler for X-Ray Academy.

Strategy:
  1. Fetch with full Chrome browser headers (httpx).
  2. On 403/blocked: detect the anti-bot mechanism, then retry with Playwright
     headless Chromium.
  3. Parse robots.txt and skip disallowed paths.
  4. Follow same-origin links up to max_pages.
  5. Return a rich CrawlReport with per-page status, blocking info, and text.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import httpx
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────────

# Full Chrome 124 User-Agent — identical to what real browsers send
_UA_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

_BASE_HEADERS = {
    "User-Agent": _UA_CHROME,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Cache-Control": "max-age=0",
}

# Patterns that indicate anti-bot / access-control walls
_BLOCK_PATTERNS = {
    "cloudflare": [
        r"cloudflare",
        r"cf-ray",
        r"checking your browser",
        r"ddos.protection",
        r"attention required",
        r"just a moment",
    ],
    "captcha": [
        r"captcha",
        r"recaptcha",
        r"hcaptcha",
        r"bot.detection",
        r"verify you are human",
    ],
    "auth_wall": [
        r"login required",
        r"sign in to",
        r"please log in",
        r"authentication required",
        r"access denied",
        r"you must be logged",
        r"members only",
        r"subscriber",
    ],
    "rate_limit": [
        r"too many requests",
        r"rate limit",
        r"slow down",
        r"retry after",
    ],
    "geo_block": [
        r"not available in your",
        r"geographic restriction",
        r"country is not supported",
    ],
}

_ROBOTS_CACHE: dict[str, RobotFileParser] = {}


# ── Technical relevance scoring ────────────────────────────────────────────────

# X-ray / radiation / security-screening domain terms
_TECH_TERM_PATTERNS = [
    r"\bx[-\s]?ray\b", r"\bradiation\b", r"\bdetector\b", r"\bgenerator\b",
    r"\blinac\b", r"\baccelerat", r"\bscintillat", r"\bbaggage\b",
    r"\bcargo\b", r"\bscreening\b", r"\bthreat\b", r"\bdose\b",
    r"\bkev\b", r"\bmev\b", r"\bkv[ap]?\b", r"\bvoltage\b",
    r"\bconveyor\b", r"\bcollimator\b", r"\bbeam\b",
    r"\bprocedure\b", r"\binstallat", r"\bconfigur", r"\bcalibrat",
    r"\bmaintenance\b", r"\btroubleshoot", r"\bspecification\b",
    r"\biaea\b", r"\bicrp\b", r"\biec\b", r"\biso\b", r"\bansi\b",
    r"\bncrp\b", r"\bastm\b", r"\bsafety\b", r"\bshielding\b",
    r"\bbremsstrahlung\b", r"\bcompton\b", r"\bphotoelectric\b",
    r"\bimage\s+quality\b", r"\bpenetrat", r"\bbackscatter\b",
    r"\bct\s+scan\b", r"\btechnical\s+manual\b", r"\bsop\b",
]

_LOW_QUALITY_PATTERNS = [
    r"cookie\s+policy", r"privacy\s+policy", r"terms\s+of\s+(service|use)",
    r"newsletter\s+sign[-\s]?up", r"subscribe\s+to\s+our",
    r"career\s+opportunit", r"job\s+open", r"press\s+release",
    r"social\s+media", r"follow\s+us\s+on", r"all\s+rights\s+reserved",
]

# Path prefixes that match each knowledge source type
_SOURCE_PATH_HINTS: dict[str, list[str]] = {
    "documentation": [
        "/doc", "/docs", "/documentation", "/guide", "/guides", "/help",
        "/reference", "/wiki", "/manual", "/knowledge", "/learn", "/tutorial",
    ],
    "technical_manuals": [
        "/manual", "/technical", "/specification", "/spec", "/datasheet",
        "/handbook", "/engineering", "/instruction",
    ],
    "standards": [
        "/standard", "/regulation", "/compliance", "/safety", "/norm",
        "/guideline", "/requirement", "/code",
    ],
}

# Default blocked paths for technical content acquisition
DEFAULT_BLOCKED_PATHS: list[str] = [
    "/news", "/blog", "/careers", "/jobs", "/privacy", "/contact",
    "/events", "/media", "/store", "/login", "/register", "/cart",
    "/checkout", "/about-us", "/team", "/press", "/social",
]


def _score_technical_relevance(text: str) -> float:
    """Score text for technical relevance: 0.0 (irrelevant) → 1.0 (highly technical)."""
    if not text or len(text) < 50:
        return 0.0
    text_lower = text.lower()
    tech_hits = sum(1 for pat in _TECH_TERM_PATTERNS if re.search(pat, text_lower))
    tech_score = min(1.0, tech_hits / max(5, len(_TECH_TERM_PATTERNS) * 0.25))
    lq_hits = sum(1 for pat in _LOW_QUALITY_PATTERNS if re.search(pat, text_lower))
    quality_penalty = min(0.5, lq_hits * 0.12)
    length_bonus = min(0.2, len(text) / 15_000)
    return round(max(0.0, min(1.0, tech_score + length_bonus - quality_penalty)), 3)


def _is_blocked_path(url: str, blocked_paths: list[str]) -> bool:
    """True if the URL path matches any blocked path prefix."""
    path = urlparse(url).path.rstrip("/").lower()
    for bp in blocked_paths:
        bp_lower = bp.rstrip("/").lower()
        if path == bp_lower or path.startswith(bp_lower + "/"):
            return True
    return False


def _path_fits_source(url: str, knowledge_source: str) -> bool:
    """True if the URL path looks like it contains the requested content type."""
    hints = _SOURCE_PATH_HINTS.get(knowledge_source, [])
    if not hints:
        return True  # no path filtering for entire_website, pdfs_only, selected_urls, sitemap
    path = urlparse(url).path.lower()
    return any(path.startswith(h) or ("/" + h.strip("/") + "/") in path for h in hints)


async def _discover_sitemap_urls(
    base_url: str,
    client: httpx.AsyncClient,
    blocked_paths: list[str],
    max_urls: int = 500,
) -> list[str]:
    """Discover URLs from sitemap.xml or sitemap_index.xml. Returns de-duped URL list."""
    from xml.etree import ElementTree as ET

    parsed = urlparse(base_url)
    origin = f"{parsed.scheme}://{parsed.netloc}"
    candidates = [
        f"{origin}/sitemap.xml",
        f"{origin}/sitemap_index.xml",
        f"{origin}/sitemap-index.xml",
    ]
    ns = "http://www.sitemaps.org/schemas/sitemap/0.9"
    urls: list[str] = []

    async def _parse_sitemap_xml(xml_text: str, depth: int = 0) -> None:
        if depth > 2 or len(urls) >= max_urls:
            return
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError:
            return
        # Sitemap index → recurse
        for elem in root.findall(f"{{{ns}}}sitemap/{{{ns}}}loc"):
            sub_url = (elem.text or "").strip()
            if sub_url and len(urls) < max_urls:
                try:
                    r = await client.get(sub_url, headers=dict(_BASE_HEADERS), timeout=10)
                    if r.status_code == 200:
                        await _parse_sitemap_xml(r.text, depth + 1)
                except Exception:
                    pass
        # Regular sitemap entries
        for elem in root.findall(f"{{{ns}}}url/{{{ns}}}loc"):
            loc = (elem.text or "").strip()
            if loc and len(urls) < max_urls and not _is_blocked_path(loc, blocked_paths):
                urls.append(loc)

    for candidate in candidates:
        try:
            resp = await client.get(candidate, headers=dict(_BASE_HEADERS), timeout=10)
            if resp.status_code == 200 and ("<url" in resp.text or "<sitemap" in resp.text):
                await _parse_sitemap_xml(resp.text)
                if urls:
                    break
        except Exception as exc:
            log.debug("Sitemap fetch failed for %s: %s", candidate, exc)

    return urls


# ── Data classes ───────────────────────────────────────────────────────────────

@dataclass
class PageResult:
    url: str
    http_status: int
    http_reason: str
    accessible: bool
    blocking_mechanism: Optional[str]  # cloudflare | captcha | auth_wall | rate_limit | geo_block | None
    browser_rendering_attempted: bool
    browser_rendering_succeeded: bool
    text: str                           # extracted clean text
    links: list[str] = field(default_factory=list)
    # Multimodal Internet Image Retrieval — {"src": absolute_url, "alt": str}
    # per <img>, filtered of data: URIs and obvious icon/logo/sprite paths.
    # Metadata only (src/alt) — the crawler never fetches the image bytes
    # themselves, only the page HTML, same as every other page-level field
    # on this dataclass.
    images: list[dict] = field(default_factory=list)
    error: Optional[str] = None
    technical_relevance: float = 0.0   # 0.0–1.0 technical content score
    depth: int = 0                      # link depth from seed URL
    # Phase 2B.4 — incremental research. Captured from response headers when
    # present; None for every caller that doesn't ask for conditional
    # requests (the default). not_modified=True means the caller's
    # if_none_match/if_modified_since matched (HTTP 304) — no body was
    # re-fetched, text is empty, and this is not an error.
    etag: Optional[str] = None
    last_modified: Optional[str] = None
    not_modified: bool = False


@dataclass
class CrawlReport:
    seed_url: str
    pages_attempted: int
    pages_indexed: int
    combined_text: str
    page_results: list[PageResult]
    robots_txt_honored: bool
    playwright_available: bool
    sitemap_urls_found: int = 0
    avg_technical_relevance: float = 0.0

    @property
    def summary(self) -> str:
        lines = [
            f"Crawl of {self.seed_url}",
            f"  Pages attempted   : {self.pages_attempted}",
            f"  Pages indexed     : {self.pages_indexed}",
            f"  robots.txt honored: {'yes' if self.robots_txt_honored else 'no'}",
            f"  Playwright ready  : {'yes' if self.playwright_available else 'no (headless fallback unavailable)'}",
        ]
        for p in self.page_results:
            status_str = f"HTTP {p.http_status} {p.http_reason}"
            block = f" [{p.blocking_mechanism}]" if p.blocking_mechanism else ""
            br = ""
            if p.browser_rendering_attempted:
                br = " [browser: OK]" if p.browser_rendering_succeeded else " [browser: failed]"
            rel = f" [{int(p.technical_relevance*100)}% relevant]" if p.technical_relevance else ""
            lines.append(f"  {'✓' if p.accessible else '✗'} {p.url}  {status_str}{block}{br}{rel}")
        return "\n".join(lines)


# ── robots.txt ─────────────────────────────────────────────────────────────────

async def _get_robots(base_url: str) -> RobotFileParser:
    parsed = urlparse(base_url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    if robots_url in _ROBOTS_CACHE:
        return _ROBOTS_CACHE[robots_url]
    rp = RobotFileParser()
    rp.set_url(robots_url)
    try:
        async with httpx.AsyncClient(timeout=8.0, follow_redirects=True) as client:
            resp = await client.get(robots_url, headers={"User-Agent": _UA_CHROME})
            if resp.status_code == 200:
                rp.parse(resp.text.splitlines())
    except Exception as e:
        log.debug("robots.txt fetch failed for %s: %s", robots_url, e)
    _ROBOTS_CACHE[robots_url] = rp
    return rp


def _robots_allows(rp: RobotFileParser, url: str) -> bool:
    try:
        return rp.can_fetch(_UA_CHROME, url)
    except Exception:
        return True  # be permissive on parse errors


# ── Blocking mechanism detection ───────────────────────────────────────────────

def _detect_blocking(response_html: str, headers: dict, status: int) -> Optional[str]:
    """Inspect response body + headers for known anti-bot / access-control signals."""
    text_lower = response_html.lower()
    header_lower = {k.lower(): v.lower() for k, v in headers.items()}

    # Cloudflare: header fingerprint
    if "cf-ray" in header_lower or "cf-mitigated" in header_lower:
        return "cloudflare"

    for mechanism, patterns in _BLOCK_PATTERNS.items():
        for pat in patterns:
            if re.search(pat, text_lower):
                return mechanism

    return None


# ── HTML text + link extraction ────────────────────────────────────────────────

_SKIP_TAGS = {"script", "style", "nav", "footer", "head", "noscript", "aside", "header"}


# Multimodal Internet Image Retrieval — light, disclosed heuristic (not a
# claim of perfect precision): common non-content image paths that show up
# on virtually every page regardless of topic (nav icons, tracking pixels,
# sprites) and are never what a "show me a photo of X" request wants.
_NON_CONTENT_IMAGE_PATTERN = re.compile(
    r"/(icons?|logos?|sprites?|badges?|avatars?|pixel|tracking|funders?|sponsors?|static/base)/|"
    r"[_-](?:logo|icon|badge|sprite)s?[_.-]|"
    r"(?:^|/)(?:favicon|spacer|blank|1x1)\.(?:png|gif|jpe?g|svg|webp)$",
    re.IGNORECASE,
)


def _extract_images(soup: BeautifulSoup, base_url: str) -> list[dict]:
    """Return [{"src": absolute_url, "alt": str}] for <img> tags worth
    considering as candidate reference images — filters data: URIs and
    obvious non-content paths, nothing more. Real relevance ranking happens
    downstream (api.services.research_agent.image_discovery), which also
    has the query text this function does not."""
    images: list[dict] = []
    seen: set[str] = set()
    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if not src or src.startswith("data:"):
            continue
        absolute = urljoin(base_url, src)
        if absolute in seen or _NON_CONTENT_IMAGE_PATTERN.search(absolute):
            continue
        seen.add(absolute)
        images.append({"src": absolute, "alt": (img.get("alt") or "").strip()})
    return images


def _extract_text_and_links(html: str, base_url: str) -> tuple[str, list[str], list[dict]]:
    """Return (clean_text, [absolute_links], [images])."""
    soup = BeautifulSoup(html, "lxml")

    # Images are collected before boilerplate tags are stripped — nav/footer
    # icons already get filtered by _NON_CONTENT_IMAGE_PATTERN above, and a
    # genuine content image (e.g. a figure inside an <aside>) shouldn't be
    # lost just because that tag is decomposed for the text extraction below.
    images = _extract_images(soup, base_url)

    # Remove boilerplate tags
    for tag in soup(_SKIP_TAGS):
        tag.decompose()

    # Extract links before stripping tags
    raw_links: list[str] = []
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href and not href.startswith(("#", "mailto:", "tel:", "javascript:")):
            raw_links.append(urljoin(base_url, href))

    text = soup.get_text(separator="\n")
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, raw_links, images


def _same_origin(url: str, base: str) -> bool:
    pu, pb = urlparse(url), urlparse(base)
    return pu.netloc == pb.netloc


def _normalise_url(url: str) -> str:
    """Strip fragments and normalise trailing slash."""
    p = urlparse(url)
    return p._replace(fragment="").geturl()


# ── HTTP fetch with browser headers ───────────────────────────────────────────

async def _http_get(
    client: httpx.AsyncClient, url: str, referer: Optional[str] = None,
    if_none_match: Optional[str] = None, if_modified_since: Optional[str] = None,
) -> httpx.Response:
    headers = dict(_BASE_HEADERS)
    if referer:
        headers["Referer"] = referer
        headers["Sec-Fetch-Site"] = "same-origin"
    # Phase 2B.4 — conditional GET, only ever set by a caller that already
    # knows this URL's last-seen ETag/Last-Modified (research_agent's
    # refresh path); every other caller leaves these None and gets the
    # exact same request as before.
    if if_none_match:
        headers["If-None-Match"] = if_none_match
    if if_modified_since:
        headers["If-Modified-Since"] = if_modified_since
    return await client.get(url, headers=headers)


# ── Playwright fallback ────────────────────────────────────────────────────────

# ── Playwright system library setup (NixOS / Replit) ──────────────────────────

def _setup_playwright_ld_path() -> None:
    """
    On NixOS (Replit), Playwright's bundled Chromium needs system libraries
    that live in the nix store rather than /lib. This function finds them and
    sets LD_LIBRARY_PATH so Chromium can load them.

    Uses fast targeted nix-eval to find the canonical store paths; falls back
    to checking ~/.nix-profile/lib and /run/current-system/sw/lib.
    """
    import os
    import subprocess

    extra_dirs: list[str] = []

    # 1. nix-profile lib (populated by `nix-env -i` / system deps install)
    profile_lib = os.path.expanduser("~/.nix-profile/lib")
    if os.path.isdir(profile_lib):
        extra_dirs.append(profile_lib)

    # 2. NixOS system lib
    system_lib = "/run/current-system/sw/lib"
    if os.path.isdir(system_lib):
        extra_dirs.append(system_lib)

    # 3. Resolve specific packages we know Chromium needs via nix eval
    #    nix eval --raw is fast (cached) and gives the exact store path.
    nix_packages = [
        "nixpkgs#nspr",
        "nixpkgs#nss",
        "nixpkgs#nss_latest",
        "nixpkgs#atk",
        "nixpkgs#at-spi2-atk",
        "nixpkgs#at-spi2-core",
        "nixpkgs#pango",
        "nixpkgs#cairo",
        "nixpkgs#glib",
        "nixpkgs#alsa-lib",
        "nixpkgs#libdrm",
        "nixpkgs#libxkbcommon",
        "nixpkgs#expat",
        "nixpkgs#dbus",
        "nixpkgs#cups",
        "nixpkgs#mesa",
        "nixpkgs#gtk3",
        "nixpkgs#gdk-pixbuf",
        # X11 / Xorg
        "nixpkgs#xorg.libX11",
        "nixpkgs#xorg.libXcomposite",
        "nixpkgs#xorg.libXdamage",
        "nixpkgs#xorg.libXext",
        "nixpkgs#xorg.libXfixes",
        "nixpkgs#xorg.libXrandr",
        "nixpkgs#xorg.libXrender",
        "nixpkgs#xorg.libxcb",
        "nixpkgs#xorg.libXi",
        "nixpkgs#xorg.libXtst",
        "nixpkgs#xorg.libXau",
        "nixpkgs#xorg.libxshmfence",
    ]
    for pkg in nix_packages:
        try:
            r = subprocess.run(
                ["nix", "eval", "--raw", f"{pkg}.outPath"],
                capture_output=True, text=True, timeout=5,
            )
            if r.returncode == 0 and r.stdout.strip():
                lib_dir = r.stdout.strip() + "/lib"
                if os.path.isdir(lib_dir):
                    extra_dirs.append(lib_dir)
        except Exception:
            pass

    if extra_dirs:
        existing = os.environ.get("LD_LIBRARY_PATH", "")
        new_dirs = ":".join(dict.fromkeys(extra_dirs))  # deduplicate, preserve order
        os.environ["LD_LIBRARY_PATH"] = (
            f"{new_dirs}:{existing}" if existing else new_dirs
        )
        log.debug("Playwright LD_LIBRARY_PATH set: %s", new_dirs[:200])


_PLAYWRIGHT_LD_SET = False


def _patch_playwright_binary() -> bool:
    """
    Use patchelf to bake the nix library paths directly into the Chromium binary's
    RPATH.  This is the correct NixOS fix — LD_LIBRARY_PATH alone is unreliable
    across process boundaries.  The patch is idempotent: running it again is safe.
    Returns True if the binary was patched (or was already patched).
    """
    import glob
    import os
    import subprocess

    # Find the Playwright Chromium headless shell binary
    home = os.path.expanduser("~")
    pattern = os.path.join(
        home,
        ".cache/ms-playwright/chromium*headless*shell*/*/chrome-headless-shell",
    )
    binaries = glob.glob(pattern)
    if not binaries:
        log.debug("patchelf: Playwright binary not found at %s", pattern)
        return False

    binary = binaries[0]

    # Collect library directories
    lib_dirs: list[str] = []

    # Profile and system paths
    for d in [
        os.path.expanduser("~/.nix-profile/lib"),
        "/run/current-system/sw/lib",
    ]:
        if os.path.isdir(d):
            lib_dirs.append(d)

    # Resolve nix packages via nix eval (fast, uses nix eval cache)
    nix_packages = [
        "nixpkgs#nspr",
        "nixpkgs#nss",
        "nixpkgs#nss_latest",
        "nixpkgs#atk",
        "nixpkgs#at-spi2-atk",
        "nixpkgs#at-spi2-core",
        "nixpkgs#pango",
        "nixpkgs#cairo",
        "nixpkgs#glib",
        "nixpkgs#alsa-lib",
        "nixpkgs#libdrm",
        "nixpkgs#libxkbcommon",
        "nixpkgs#expat",
        "nixpkgs#dbus",
        "nixpkgs#cups",
        "nixpkgs#mesa",
        "nixpkgs#libudev-zero",
        "nixpkgs#gtk3",
        "nixpkgs#gdk-pixbuf",
        "nixpkgs#xorg.libX11",
        "nixpkgs#xorg.libXcomposite",
        "nixpkgs#xorg.libXdamage",
        "nixpkgs#xorg.libXext",
        "nixpkgs#xorg.libXfixes",
        "nixpkgs#xorg.libXrandr",
        "nixpkgs#xorg.libXrender",
        "nixpkgs#xorg.libxcb",
        "nixpkgs#xorg.libXi",
        "nixpkgs#xorg.libXtst",
        "nixpkgs#xorg.libXau",
        "nixpkgs#xorg.libxshmfence",
    ]
    for pkg in nix_packages:
        try:
            r = subprocess.run(
                ["nix", "eval", "--raw", f"{pkg}.outPath"],
                capture_output=True, text=True, timeout=6,
            )
            if r.returncode == 0 and r.stdout.strip():
                store_path = r.stdout.strip()
                for sub in ["/lib", "/lib/gbm"]:
                    d = store_path + sub
                    if os.path.isdir(d):
                        lib_dirs.append(d)
        except Exception:
            pass

    if not lib_dirs:
        log.warning("patchelf: no nix library dirs found — cannot patch Playwright binary")
        return False

    # Deduplicate
    seen: set[str] = set()
    rpath_dirs: list[str] = []
    for d in lib_dirs:
        if d not in seen:
            seen.add(d)
            rpath_dirs.append(d)

    rpath = ":".join(rpath_dirs)

    try:
        result = subprocess.run(
            ["patchelf", "--set-rpath", rpath, binary],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.warning("patchelf failed: %s", result.stderr[:200])
            return False

        # Quick ldd verification
        ldd = subprocess.run(["ldd", binary], capture_output=True, text=True, timeout=10)
        missing = [l for l in ldd.stdout.splitlines() if "not found" in l]
        if missing:
            log.warning("After patchelf, still missing: %s", missing)
            return False

        log.info("patchelf: Playwright Chromium patched with %d lib dirs", len(rpath_dirs))
        return True
    except Exception as exc:
        log.warning("patchelf error: %s", exc)
        return False


def _ensure_playwright_ld_path() -> None:
    global _PLAYWRIGHT_LD_SET
    if not _PLAYWRIGHT_LD_SET:
        _setup_playwright_ld_path()
        _PLAYWRIGHT_LD_SET = True


# ── Playwright availability check ──────────────────────────────────────────────

_PLAYWRIGHT_STATUS: Optional[str] = None  # None=untested, "ok", "unavailable:<reason>"


async def _playwright_available() -> bool:
    """Check whether Playwright + Chromium are usable in this environment."""
    global _PLAYWRIGHT_STATUS

    if _PLAYWRIGHT_STATUS is not None:
        return _PLAYWRIGHT_STATUS == "ok"

    try:
        from playwright.async_api import async_playwright
    except ImportError:
        _PLAYWRIGHT_STATUS = "unavailable:not_installed"
        return False

    # Ensure Playwright binary has correct RPATH for NixOS system libraries
    _ensure_playwright_ld_path()
    _patch_playwright_binary()
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-dev-shm-usage"],
            )
            await browser.close()
        _PLAYWRIGHT_STATUS = "ok"
        log.info("Playwright Chromium: available and working")
        return True
    except Exception as exc:
        _PLAYWRIGHT_STATUS = f"unavailable:{exc}"
        log.warning("Playwright Chromium unavailable: %s", exc)
        return False


async def _fetch_with_playwright(url: str) -> tuple[int, str, str]:
    """
    Render the page with headless Chromium.
    Returns (http_status, reason, html_content).
    On failure returns (0, reason, "").
    """
    try:
        from playwright.async_api import async_playwright, TimeoutError as PWTimeout
    except ImportError:
        return 0, "Playwright not installed", ""

    _ensure_playwright_ld_path()

    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                    "--single-process",
                ],
            )
            ctx = await browser.new_context(
                user_agent=_UA_CHROME,
                locale="en-US",
                extra_http_headers={"Accept-Language": "en-US,en;q=0.9"},
                viewport={"width": 1280, "height": 800},
                java_script_enabled=True,
            )
            page = await ctx.new_page()

            # Block heavy tracking/ad scripts to speed up page load
            async def _maybe_abort(route):
                if any(p in route.request.url for p in
                       ["analytics", "/ads/", "/tracking/", "/pixel/", "beacon"]):
                    await route.abort()
                else:
                    await route.continue_()

            await page.route("**/*", _maybe_abort)

            response = None
            try:
                response = await page.goto(url, wait_until="domcontentloaded", timeout=25_000)
                # Give JS-heavy pages time to render visible content
                await page.wait_for_timeout(2000)
            except PWTimeout:
                log.warning("Playwright timeout on %s", url)
                await browser.close()
                return 0, "Timeout (25s)", ""

            status = response.status if response else 0
            reason = response.status_text if response else "No response"
            html = await page.content()
            await browser.close()
            return status, reason, html

    except Exception as exc:
        log.error("Playwright error on %s: %s", url, exc)
        return 0, str(exc), ""


# ── Single-page fetch (HTTP → Playwright fallback) ────────────────────────────

async def _fetch_page(
    client: httpx.AsyncClient,
    url: str,
    referer: Optional[str],
    rp: RobotFileParser,
    pw_available: bool,
    if_none_match: Optional[str] = None,
    if_modified_since: Optional[str] = None,
) -> PageResult:
    """Fetch one page, falling back to Playwright on 403/blocked.

    if_none_match/if_modified_since (Phase 2B.4) are only ever set by
    research_agent's refresh path re-checking a URL it has already
    processed — every other caller leaves them None and gets identical
    behavior to before this parameter existed."""

    # robots.txt gate
    if not _robots_allows(rp, url):
        return PageResult(
            url=url,
            http_status=0,
            http_reason="Blocked by robots.txt",
            accessible=False,
            blocking_mechanism=None,
            browser_rendering_attempted=False,
            browser_rendering_succeeded=False,
            text="",
            error="robots.txt disallows this path",
        )

    # ── Stage 1: plain HTTP request ────────────────────────────────────────────
    http_status = 0
    http_reason = ""
    html = ""
    blocking: Optional[str] = None
    browser_attempted = False
    browser_ok = False
    links: list[str] = []
    text = ""
    images: list[dict] = []
    resp_etag: Optional[str] = None
    resp_last_modified: Optional[str] = None

    try:
        resp = await _http_get(client, url, referer, if_none_match, if_modified_since)
        http_status = resp.status_code
        http_reason = resp.reason_phrase or ""
        resp_headers = dict(resp.headers)
        resp_etag = resp_headers.get("ETag") or resp_headers.get("etag")
        resp_last_modified = resp_headers.get("Last-Modified") or resp_headers.get("last-modified")

        if http_status == 304:
            return PageResult(
                url=url, http_status=304, http_reason=http_reason,
                accessible=False, blocking_mechanism=None,
                browser_rendering_attempted=False, browser_rendering_succeeded=False,
                text="", etag=resp_etag, last_modified=resp_last_modified, not_modified=True,
            )

        if resp.is_success:
            html = resp.text
        else:
            html = resp.text  # still read body for block detection
            blocking = _detect_blocking(html, resp_headers, http_status)
            log.info(
                "Non-2xx response for %s: HTTP %d %s | blocking=%s",
                url, http_status, http_reason, blocking,
            )

    except httpx.HTTPStatusError as exc:
        http_status = exc.response.status_code
        http_reason = exc.response.reason_phrase or ""
        html = exc.response.text
        blocking = _detect_blocking(html, dict(exc.response.headers), http_status)
        log.info("HTTPStatusError for %s: %d %s | blocking=%s", url, http_status, http_reason, blocking)
    except Exception as exc:
        http_status = 0
        http_reason = str(exc)
        log.warning("HTTP fetch failed for %s: %s", url, exc)

    # ── Stage 2: Playwright fallback if blocked ────────────────────────────────
    needs_browser = (
        http_status in (403, 401, 429, 503, 0)
        or blocking in ("cloudflare", "captcha")
    )

    if needs_browser:
        browser_attempted = True
        if not pw_available:
            log.info("Playwright not available for %s — reporting reason", url)
        else:
            log.info("Retrying %s with Playwright headless browser", url)
            pw_status, pw_reason, pw_html = await _fetch_with_playwright(url)
            if pw_html and (pw_status == 0 or 200 <= pw_status < 300):
                # Accept the Playwright result
                html = pw_html
                if pw_status:
                    http_status = pw_status
                    http_reason = pw_reason
                browser_ok = True
                # Re-check blocking after browser render
                blocking = _detect_blocking(html, {}, http_status)
                if blocking:
                    browser_ok = False
                    log.info("Playwright rendered %s but blocking still detected: %s", url, blocking)
            else:
                log.info("Playwright could not access %s: %s", url, pw_reason)

    # ── Extract text + links from whichever HTML we have ──────────────────────
    accessible = False
    if html:
        try:
            text, links, images = _extract_text_and_links(html, url)
            # Consider accessible if we got real content (>200 chars) and no unresolved blocking
            if len(text) >= 100 and not blocking:
                accessible = True
            elif len(text) >= 100 and browser_ok:
                accessible = True
        except Exception as exc:
            log.warning("Parse error for %s: %s", url, exc)

    error_msg: Optional[str] = None
    if not accessible:
        if blocking == "cloudflare":
            error_msg = (
                f"HTTP {http_status} {http_reason} — Cloudflare anti-bot protection detected. "
                + ("Playwright did not bypass it." if browser_attempted and not browser_ok
                   else "Browser rendering not attempted." if not browser_attempted
                   else "")
            )
        elif blocking == "captcha":
            error_msg = f"HTTP {http_status} {http_reason} — CAPTCHA challenge detected (automated access blocked)."
        elif blocking == "auth_wall":
            error_msg = f"HTTP {http_status} {http_reason} — Login / authentication required to access this page."
        elif blocking == "rate_limit":
            error_msg = f"HTTP {http_status} {http_reason} — Rate limit detected."
        elif blocking == "geo_block":
            error_msg = f"HTTP {http_status} {http_reason} — Geographic access restriction."
        elif http_status == 403:
            if browser_attempted and not pw_available:
                error_msg = (
                    f"HTTP 403 {http_reason} — Access denied. "
                    "Browser rendering is installed but could not bypass this restriction. "
                    "The page may require a real user session."
                )
            elif browser_attempted and browser_ok:
                pass  # actually succeeded via browser
            else:
                error_msg = f"HTTP {http_status} {http_reason} — Access denied (not a URL error — the URL is valid)."
        elif http_status >= 400:
            error_msg = f"HTTP {http_status} {http_reason}"
        elif http_status == 0:
            error_msg = f"Connection failed: {http_reason}"
        elif len(text) < 100:
            error_msg = "Page accessible but no readable text content found."

    return PageResult(
        url=url,
        http_status=http_status,
        http_reason=http_reason,
        accessible=accessible,
        blocking_mechanism=blocking,
        browser_rendering_attempted=browser_attempted,
        browser_rendering_succeeded=browser_ok,
        text=text,
        links=links,
        images=images,
        error=error_msg,
        etag=resp_etag,
        last_modified=resp_last_modified,
    )


# ── Multi-page crawl ───────────────────────────────────────────────────────────

async def crawl(
    seed_url: str,
    max_pages: int = 10,
    max_depth: int = 3,
    same_origin_only: bool = True,
    request_delay: float = 0.5,
    blocked_paths: Optional[list[str]] = None,
    knowledge_source: str = "entire_website",
    include_sitemap: bool = True,
    min_relevance_score: float = 0.0,
    seed_urls: Optional[list[str]] = None,
    if_none_match: Optional[str] = None,
    if_modified_since: Optional[str] = None,
) -> CrawlReport:
    """
    Crawl up to max_pages pages starting from seed_url (or seed_urls list).

    Parameters:
        seed_url:           Primary URL to start crawling from.
        max_pages:          Maximum pages to fetch (capped at 50).
        max_depth:          Maximum link-follow depth from the seed URL.
        same_origin_only:   Only follow links to the same domain.
        request_delay:      Seconds between requests (politeness).
        blocked_paths:      URL path prefixes to skip (defaults to DEFAULT_BLOCKED_PATHS).
        knowledge_source:   Content-type filter: entire_website | documentation |
                            technical_manuals | standards | pdfs_only | sitemap | selected_urls.
        include_sitemap:    Try to discover sitemap.xml before link-following.
        min_relevance_score: Minimum technical relevance to include (0.0 = accept all).
        seed_urls:          For selected_urls mode — explicit list of URLs to fetch.
        if_none_match:      Phase 2B.4 — conditional GET (ETag). Only meaningful for
                            single-URL calls (max_pages=1); applied to every fetch in
                            this crawl, so leave None for ordinary multi-page crawls.
        if_modified_since:  Phase 2B.4 — conditional GET (Last-Modified). Same caveat.

    Returns:
        CrawlReport with per-page breakdown, combined text, and quality metrics.
    """
    seed_url = _normalise_url(seed_url)
    max_pages = max(1, min(max_pages, 50))
    if blocked_paths is None:
        blocked_paths = list(DEFAULT_BLOCKED_PATHS)

    pw_available = await _playwright_available()
    rp = await _get_robots(seed_url)

    # Queue: list of (url, depth)
    if seed_urls:
        # selected_urls mode — crawl exactly the provided list at depth 0
        queue: list[tuple[str, int]] = [(u.strip(), 0) for u in seed_urls if u.strip()]
    else:
        queue = [(seed_url, 0)]

    visited: set[str] = set()
    results: list[PageResult] = []
    texts: list[str] = []
    robots_honored = True
    sitemap_urls_found = 0

    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=25.0,
        limits=httpx.Limits(max_connections=4),
    ) as client:

        # ── Sitemap discovery ──────────────────────────────────────────────────
        if include_sitemap and not seed_urls:
            try:
                sm_urls = await _discover_sitemap_urls(seed_url, client, blocked_paths)
                if sm_urls:
                    sitemap_urls_found = len(sm_urls)
                    log.info("Sitemap: %d URLs discovered for %s", sitemap_urls_found, seed_url)
                    if knowledge_source == "sitemap":
                        # Replace queue entirely with sitemap URLs
                        queue = [(u, 0) for u in sm_urls[: max_pages * 5]]
                    else:
                        # Supplement normal crawl with sitemap URLs (depth=1)
                        existing = {u for u, _ in queue}
                        for u in sm_urls:
                            n = _normalise_url(u)
                            if n not in existing and not _is_blocked_path(n, blocked_paths):
                                queue.append((n, 1))
                                existing.add(n)
            except Exception as exc:
                log.debug("Sitemap discovery error for %s: %s", seed_url, exc)

        while queue and len(results) < max_pages:
            url, depth = queue.pop(0)
            url = _normalise_url(url)
            if url in visited:
                continue
            visited.add(url)

            # Domain filter
            if same_origin_only and not seed_urls and not _same_origin(url, seed_url):
                continue

            # Blocked path filter
            if _is_blocked_path(url, blocked_paths):
                log.debug("Blocked path skipped: %s", url)
                continue

            # Knowledge-source path filter (seed URL always qualifies; child pages are filtered)
            if depth > 0 and not _path_fits_source(url, knowledge_source):
                log.debug("Off-topic for source=%s, skipped: %s", knowledge_source, url)
                continue

            referer = seed_url if url != seed_url else None
            log.info("Crawling [%d/%d] depth=%d: %s", len(results) + 1, max_pages, depth, url)

            result = await _fetch_page(client, url, referer, rp, pw_available, if_none_match, if_modified_since)

            # Score technical relevance
            result.technical_relevance = _score_technical_relevance(result.text)
            result.depth = depth
            results.append(result)

            # Accept page content based on accessibility + relevance threshold
            if result.accessible and result.text:
                if result.technical_relevance >= min_relevance_score:
                    texts.append(f"=== {url} ===\n{result.text}")
                else:
                    log.debug(
                        "Low-relevance page excluded (%.2f < %.2f): %s",
                        result.technical_relevance, min_relevance_score, url,
                    )

            # Queue discovered links (respect depth limit)
            if depth < max_depth and result.accessible:
                queued_urls = {u for u, _ in queue}
                skip_exts = {".zip", ".png", ".jpg", ".gif", ".svg", ".css", ".js",
                             ".mp4", ".mp3", ".exe", ".dmg", ".tar", ".gz"}
                # Separate set for PDFs (allowed in some modes)
                pdf_ok_sources = {"pdfs_only", "entire_website", "documentation",
                                  "technical_manuals", "standards"}

                for link in result.links:
                    link = _normalise_url(link)
                    if link in visited or link in queued_urls:
                        continue
                    if same_origin_only and not seed_urls and not _same_origin(link, seed_url):
                        continue
                    if _is_blocked_path(link, blocked_paths):
                        continue
                    lp = urlparse(link).path.lower()
                    if any(lp.endswith(ext) for ext in skip_exts):
                        continue
                    if lp.endswith(".pdf") and knowledge_source not in pdf_ok_sources:
                        continue
                    queue.append((link, depth + 1))

            if request_delay > 0 and queue:
                await asyncio.sleep(request_delay)

    pages_indexed = sum(1 for r in results if r.accessible)
    combined_text = "\n\n".join(texts)
    relevant_scores = [r.technical_relevance for r in results if r.accessible and r.text]
    avg_relevance = round(sum(relevant_scores) / max(1, len(relevant_scores)), 3) if relevant_scores else 0.0

    return CrawlReport(
        seed_url=seed_url,
        pages_attempted=len(results),
        pages_indexed=pages_indexed,
        combined_text=combined_text,
        page_results=results,
        robots_txt_honored=robots_honored,
        playwright_available=pw_available,
        sitemap_urls_found=sitemap_urls_found,
        avg_technical_relevance=avg_relevance,
    )
