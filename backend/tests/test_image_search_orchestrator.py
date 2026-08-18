"""
Unified image-search orchestrator (gallery_service.search_images_with_fallback)
and its integration with /api/chat/stream.

Regression target: an image request like "show me photo for X-ray material
discrimination" used to return "No matching images found" and stop — the
internet fallback was gated on an authenticated user_id, so an anonymous /
local-developer session never reached it. These tests prove:

  * synonym expansion broadens a domain image query,
  * the orchestrator merges local + web results, de-dupes, and tags origin,
  * the web fallback runs for an ANONYMOUS session (no user_id),
  * a strong local hit still skips the web entirely (no needless crawl).
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import optional_auth
from api.db.base import SessionLocal
from api.db import crud
from api.services import gallery_service
from api.services.gallery_service import expand_image_query, search_images_with_fallback
from api.services.research_agent.image_discovery import (
    _domain_biased_query, _is_off_domain_medical,
)


# ── Domain understanding: drop clinical false-positives, no security-only lock ──

def test_medical_dexa_dropped_for_non_medical_query():
    # The reported bug: DEXA bone-density scans surfaced for a screening concept.
    dexa = "Dual-energy X-ray absorptiometry (DEXA) scan of a patient's spine"
    assert _is_off_domain_medical(dexa, "X-ray material discrimination") is True


def test_medical_kept_when_query_is_medical():
    dexa = "Dual-energy X-ray absorptiometry (DEXA) bone densitometry"
    assert _is_off_domain_medical(dexa, "medical bone densitometry X-ray") is False


def test_non_medical_image_never_dropped():
    assert _is_off_domain_medical("Baggage scanner dual-energy colour image", "material discrimination") is False
    assert _is_off_domain_medical("Magnetron cutaway diagram", "show me a magnetron") is False


def test_domain_bias_is_not_security_only_lock():
    # A light x-ray context is added for a bare concept...
    assert _domain_biased_query("material discrimination") == "material discrimination x-ray"
    # ...but equipment/object queries are NOT forced into baggage/cargo/security.
    biased = _domain_biased_query("magnetron")
    assert "security" not in biased and "baggage" not in biased and "cargo" not in biased
    # Queries that already carry x-ray/medical context are left untouched.
    assert _domain_biased_query("dual-energy x-ray") == "dual-energy x-ray"
    assert _domain_biased_query("medical bone density") == "medical bone density"


# ── Synonym expansion ────────────────────────────────────────────────────

def test_expand_image_query_broadens_material_discrimination():
    expanded = expand_image_query("X-ray material discrimination")
    # Original always first, highest precision.
    assert expanded[0] == "X-ray material discrimination"
    joined = " ".join(expanded).lower()
    # Interchangeable phrasings must be pulled in so equivalently-indexed
    # figures (and the web query) still match.
    assert "dual-energy x-ray" in joined or "dual energy x-ray" in joined
    assert "z-effective" in joined or "effective atomic number" in joined


def test_expand_image_query_unrelated_query_has_no_expansions():
    assert expand_image_query("purchase order summary") == ["purchase order summary"]


def test_expand_image_query_empty():
    assert expand_image_query(None) == []
    assert expand_image_query("   ") == []


# ── Orchestrator: local empty → web fallback merges & tags origin ─────────

@pytest.mark.asyncio
async def test_orchestrator_falls_back_to_web_when_local_empty(monkeypatch):
    async def _empty_local(query, db, top_k=6):
        return []

    async def _fake_discover(query, max_images=None):
        return [{"src": "https://example.org/md.jpg", "alt": "material discrimination",
                 "page_url": "https://example.org/p", "page_title": "MD"}]

    async def _fake_store(db, query, images):
        return [{
            "image_id": "web-md-1", "gallery_index_id": None, "title": "Material discrimination",
            "image_url": images[0]["src"], "thumbnail_url": images[0]["src"],
            "caption": "dual-energy colour coding", "tags": [], "source_document": "example.org",
            "page_number": None, "source_url": images[0]["page_url"],
            "retrieved_at": "2026-01-01T00:00:00+00:00", "confidence": 61.0,
        }]

    monkeypatch.setattr("api.services.gallery_service.search_gallery", _empty_local)
    monkeypatch.setattr(
        "api.services.research_agent.image_discovery.discover_public_images", _fake_discover)
    monkeypatch.setattr(
        "api.services.research_agent.image_discovery.store_discovered_images", _fake_store)

    db = SessionLocal()
    try:
        payload = await search_images_with_fallback("X-ray material discrimination", db)
    finally:
        db.close()

    assert payload["count"] == 1
    img = payload["images"][0]
    assert img["image_id"] == "web-md-1"
    assert img["origin"] == "web"
    assert img["source_url"] == "https://example.org/p"
    assert payload["sources_used"].get("web") == 1


@pytest.mark.asyncio
async def test_orchestrator_local_hit_skips_web(monkeypatch):
    async def _one_local(query, db, top_k=6):
        return [{
            "image_id": "kb-9", "title": "KB figure", "image_url": "https://kb.local/9.png",
            "thumbnail_url": "https://kb.local/9.png", "caption": "", "tags": [],
            "source_document": "manual.pdf", "page_number": 3,
        }]

    async def _must_not_run(*args, **kwargs):
        raise AssertionError("web fallback must not run when the local KB already has a match")

    monkeypatch.setattr("api.services.gallery_service.search_gallery", _one_local)
    monkeypatch.setattr(
        "api.services.research_agent.image_discovery.discover_public_images", _must_not_run)

    db = SessionLocal()
    try:
        payload = await search_images_with_fallback("baggage scanner", db)
    finally:
        db.close()

    assert payload["count"] == 1
    assert payload["images"][0]["origin"] == "local"
    assert "web" not in payload["sources_used"]


# ── E2E: ANONYMOUS session (no user_id) still gets the web fallback ───────

@pytest.fixture
def anon_client():
    """Client whose requests carry NO authenticated user — reproduces the
    Local Developer / anonymous session from the reported bug."""
    app.dependency_overrides[optional_auth] = lambda: None
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.pop(optional_auth, None)


def test_e2e_anonymous_session_triggers_web_fallback(anon_client, monkeypatch):
    async def _empty_local(query, db, top_k=6):
        return []

    async def _fake_discover(query, max_images=None):
        return [{"src": "https://example.org/anon.jpg", "alt": "material discrimination",
                 "page_url": "https://example.org/anon", "page_title": "MD"}]

    async def _fake_store(db, query, images):
        return [{
            "image_id": "web-anon-1", "gallery_index_id": None, "title": "MD",
            "image_url": images[0]["src"], "thumbnail_url": images[0]["src"], "caption": "",
            "tags": [], "source_document": "example.org", "page_number": None,
            "source_url": images[0]["page_url"], "retrieved_at": "2026-01-01T00:00:00+00:00",
            "confidence": 58.0,
        }]

    monkeypatch.setattr("api.services.gallery_service.search_gallery", _empty_local)
    monkeypatch.setattr(
        "api.services.research_agent.image_discovery.discover_public_images", _fake_discover)
    monkeypatch.setattr(
        "api.services.research_agent.image_discovery.store_discovered_images", _fake_store)

    db = SessionLocal()
    try:
        conv = crud.create_conversation(db, user_id=None, anon_session_id="anon-test-1")
        conv_id = conv.id
    finally:
        db.close()

    resp = anon_client.post(
        "/api/chat/stream",
        json={"message": "show me photo for X-ray material discrimination",
              "conversation_id": conv_id},
        headers={"X-Anon-Session-Id": "anon-test-1"},
    )
    assert resp.status_code == 200
    assert '"type": "gallery_results"' in resp.text
    assert "web-anon-1" in resp.text


# ── Arabic → English image-query bridge ──
# Regression target: an Arabic image request ("اعرض صوره لتمييز الالوان … باشعه
# اكس") routed to IMAGE_SEARCH correctly but returned ZERO images — the web
# channels and synonym expansion are English-indexed, so the raw Arabic query
# matched nothing while the identical English request resolved to 6 web images.
# The bridge translates the Arabic domain query to English BEFORE searching.

from api.services.gallery_service import (  # noqa: E402
    translate_image_query, _arabic_to_english_image_query, extract_gallery_query,
)


def _bridge(message: str) -> str:
    """End-to-end static path a request takes: extract subject, then bridge."""
    import asyncio
    gq = extract_gallery_query(message)
    # provider=None ⇒ static map only (no LLM, deterministic).
    return asyncio.run(translate_image_query(gq, provider=None))


def test_arabic_color_discrimination_bridges_to_material_discrimination():
    # The exact reported query. Must reach the "material discrimination" concept
    # so synonym expansion pulls in "dual-energy x-ray" (the proven web hit).
    out = _bridge("اعرض صوره لتمييز الالوان او فصل الالوان في انظمه فحص السيارات باشعه اكس")
    assert "material discrimination" in out
    assert len(expand_image_query(out)) > 1  # landed on a synonym group
    assert "dual-energy x-ray" in expand_image_query(out)


def test_arabic_domain_terms_bridge_to_english():
    assert "magnetron" in _bridge("اعرض صوره لماجنترون")
    assert "baggage scanner" in _bridge("أرني صورة ماسح الحقائب بالاشعة السينية")
    assert "dual-energy x-ray" in _bridge("اعرض صور الطاقه المزدوجه للكشف عن المتفجرات")


def test_english_query_passes_through_unchanged():
    # No Arabic ⇒ no bridging, no LLM call, identical string (zero regression).
    q = "X-ray material discrimination"
    import asyncio
    out = asyncio.run(translate_image_query(q, provider=None))
    assert out == q


def test_unrecognised_arabic_without_provider_falls_back_to_original():
    # Static map misses and there is no provider ⇒ keep the original (the turn
    # must never break); at runtime a provider would LLM-translate instead.
    assert _arabic_to_english_image_query("اعرض صوره لقطه جميلة") is None
