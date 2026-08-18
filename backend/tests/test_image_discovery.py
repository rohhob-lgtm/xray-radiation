"""
Multimodal Internet Image Retrieval (Phase K) — targeted tests per the
approved plan (soft-greeting-nova.md).

Covers: _extract_images() filtering, discover_public_images() bounds/safety
filtering, store_discovered_images() provenance + never-fetch-bytes
guarantee, end-to-end /api/chat/stream fallback behavior, and a regression
guard proving research questions / Canva requests never reach this module.
"""
import os
import random
import string
import sys
from unittest.mock import AsyncMock, patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import pytest
from bs4 import BeautifulSoup
from fastapi.testclient import TestClient

from main import app
from api.middleware.auth import require_auth, optional_auth
from api.db.base import SessionLocal
from api.db.models import User, KnowledgeNode, KnowledgeProvenance, ResearchFile, ResearchMission
from api.db import crud
from api.services.web_crawler import _extract_images, PageResult
from api.services.research_agent.image_discovery import (
    discover_public_images, store_discovered_images,
)

USER = {"id": "image-discovery-test-user", "username": "image-tester@example.com", "name": "Image Tester"}

_created_mission_ids: list[str] = []


def _word_tag() -> str:
    return "".join(random.choices(string.ascii_lowercase, k=10))


@pytest.fixture(autouse=True)
def _archive_created_missions():
    _created_mission_ids.clear()
    yield
    if not _created_mission_ids:
        return
    db = SessionLocal()
    try:
        for mission_id in _created_mission_ids:
            crud.update_research_mission(db, mission_id, status="archived")
    finally:
        db.close()
    _created_mission_ids.clear()


def _ensure_user():
    s = SessionLocal()
    try:
        if not s.get(User, USER["id"]):
            s.add(User(id=USER["id"], username=USER["username"], name=USER["name"]))
            s.commit()
    finally:
        s.close()


@pytest.fixture
def client():
    _ensure_user()
    app.dependency_overrides[require_auth] = lambda: USER
    app.dependency_overrides[optional_auth] = lambda: USER
    yield TestClient(app)
    app.dependency_overrides.pop(require_auth, None)
    app.dependency_overrides.pop(optional_auth, None)


def _make_conversation(db):
    return crud.create_conversation(db, user_id=USER["id"], anon_session_id=None)


# ──────────────────────────────────────────────────────────
# 1. _extract_images() — HTML filtering
# ──────────────────────────────────────────────────────────

def test_extract_images_keeps_real_content_drops_icons_logos_and_data_uris():
    html = """
    <html><body>
      <img src="/icons/menu.svg" alt="menu">
      <img src="data:image/png;base64,AAAA" alt="inline">
      <img src="/images/linac-diagram.jpg" alt="LINAC diagram schematic">
      <img data-src="/media/baggage-scanner.png" alt="Baggage scanner">
      <img src="/logo/brand-logo.png" alt="logo">
      <img src="/favicon.png">
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    images = _extract_images(soup, "https://example.org/page")
    srcs = {img["src"] for img in images}
    assert "https://example.org/images/linac-diagram.jpg" in srcs
    assert "https://example.org/media/baggage-scanner.png" in srcs
    assert len(images) == 2
    assert not any("icons" in s for s in srcs)
    assert not any("logo" in s for s in srcs)
    assert not any(s.startswith("data:") for s in srcs)


def test_extract_images_dedupes_repeated_src():
    html = """
    <html><body>
      <img src="/images/x.jpg" alt="first">
      <img src="/images/x.jpg" alt="duplicate">
    </body></html>
    """
    soup = BeautifulSoup(html, "lxml")
    images = _extract_images(soup, "https://example.org/page")
    assert len(images) == 1


# ──────────────────────────────────────────────────────────
# 2. discover_public_images — bounds + safety filtering
# ──────────────────────────────────────────────────────────

def _fake_page_result(url: str, images: list[dict]) -> PageResult:
    return PageResult(
        url=url, http_status=200, http_reason="OK", accessible=True,
        blocking_mechanism=None, browser_rendering_attempted=False,
        browser_rendering_succeeded=False, text="LINAC magnetron reference page",
        links=[], images=images,
    )


class _FakeCrawlReport:
    def __init__(self, page_results):
        self.page_results = page_results


@pytest.mark.asyncio
async def test_discover_public_images_respects_max_images_bound():
    candidates = [{"url": f"https://example.org/page{i}"} for i in range(5)]

    async def _fake_discover_sources(*args, **kwargs):
        return candidates

    async def _fake_crawl(url, **kwargs):
        return _FakeCrawlReport([
            _fake_page_result(url, [{"src": f"{url}/img.jpg", "alt": "LINAC magnetron"}]),
        ])

    with patch("api.services.research_agent.image_discovery.discover_sources", _fake_discover_sources), \
         patch("api.services.research_agent.image_discovery.web_crawl", _fake_crawl):
        results = await discover_public_images("LINAC magnetron", max_images=2)

    assert len(results) <= 2
    assert all(r["src"].startswith("https://example.org/") for r in results)


@pytest.mark.asyncio
async def test_discover_public_images_drops_unsafe_urls():
    async def _fake_discover_sources(*args, **kwargs):
        return [
            {"url": "https://example.org/safe-page"},
            {"url": "http://169.254.169.254/metadata"},  # SSRF-class, must be dropped
        ]

    async def _fake_crawl(url, **kwargs):
        if "169.254" in url:
            raise AssertionError("web_crawl must never be called on an unsafe URL")
        return _FakeCrawlReport([
            _fake_page_result(url, [
                {"src": "http://169.254.169.254/img.jpg", "alt": "unsafe image src"},
                {"src": f"{url}/real.jpg", "alt": "LINAC magnetron diagram"},
            ]),
        ])

    with patch("api.services.research_agent.image_discovery.discover_sources", _fake_discover_sources), \
         patch("api.services.research_agent.image_discovery.web_crawl", _fake_crawl):
        results = await discover_public_images("LINAC magnetron", max_images=6)

    assert all("169.254" not in r["src"] for r in results)
    assert any("real.jpg" in r["src"] for r in results)


# ──────────────────────────────────────────────────────────
# 3. store_discovered_images — provenance + never-fetch-bytes
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_store_discovered_images_creates_provenance_and_never_downloads():
    tag = _word_tag()
    images = [{
        "src": f"https://example.org/{tag}/magnetron.jpg",
        "alt": f"Magnetron cross-section {tag}",
        "page_url": f"https://example.org/{tag}/page",
        "page_title": f"Magnetron reference {tag}",
    }]

    db = SessionLocal()
    try:
        with patch("httpx.AsyncClient.get") as mock_async_get, patch("httpx.get") as mock_get:
            results = await store_discovered_images(db, f"magnetron query {tag}", images)

        mock_async_get.assert_not_called()
        mock_get.assert_not_called()

        assert len(results) == 1
        result = results[0]
        assert result["source_url"] == images[0]["page_url"]
        assert result["image_url"] == images[0]["src"]
        assert result["retrieved_at"]
        assert result["confidence"] > 0

        node = (
            db.query(KnowledgeNode)
            .filter(KnowledgeNode.node_type == "Image", KnowledgeNode.label.like(f"%{tag}%"))
            .first()
        )
        assert node is not None
        assert node.approved is False

        provenance = (
            db.query(KnowledgeProvenance)
            .filter(KnowledgeProvenance.node_id == node.id)
            .first()
        )
        assert provenance is not None
        assert provenance.created_by_service == "image_discovery"
        assert provenance.original_url == images[0]["src"]

        file_row = (
            db.query(ResearchFile)
            .filter(ResearchFile.file_type == "image", ResearchFile.filename.like(f"%{tag}%"))
            .first()
        )
        assert file_row is not None
        assert file_row.downloaded is False
        assert file_row.size_bytes == 0

        missions = db.query(ResearchMission).filter(
            ResearchMission.origin == "chat_image_retrieval",
            ResearchMission.mission_text.like(f"%{tag}%"),
        ).all()
        for m in missions:
            _created_mission_ids.append(m.id)
    finally:
        db.close()


@pytest.mark.asyncio
async def test_store_discovered_images_drops_low_trust_images(monkeypatch):
    from api.config import settings
    monkeypatch.setattr(settings, "image_retrieval_min_trust_score", 200.0)  # unreachable -> always dropped

    tag = _word_tag()
    images = [{
        "src": f"https://example.org/{tag}/x.jpg", "alt": "x",
        "page_url": f"https://example.org/{tag}/page", "page_title": "x",
    }]
    db = SessionLocal()
    try:
        results = await store_discovered_images(db, f"query {tag}", images)
        assert results == []
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# 4. End-to-end /api/chat/stream fallback
# ──────────────────────────────────────────────────────────

def test_e2e_kb_hit_skips_internet_fallback(client, monkeypatch):
    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("discover_public_images must not be called when the KB already has images")

    monkeypatch.setattr(
        "api.services.research_agent.image_discovery.discover_public_images", _fail_if_called,
    )

    async def _fake_search_gallery(query, db, top_k=6):
        return [{
            "image_id": "kb-1", "title": "LINAC photo", "image_url": "https://kb.local/linac.jpg",
            "thumbnail_url": "https://kb.local/linac.jpg", "caption": "", "tags": [],
            "source_document": "kb", "page_number": None,
        }]

    monkeypatch.setattr("api.services.gallery_service.search_gallery", _fake_search_gallery)

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "Show me a LINAC photo", "conversation_id": conv_id},
    )
    assert resp.status_code == 200
    assert '"type": "gallery_results"' in resp.text


def test_e2e_kb_empty_triggers_internet_fallback(client, monkeypatch):
    async def _fake_search_gallery(query, db, top_k=6):
        return []

    monkeypatch.setattr("api.services.gallery_service.search_gallery", _fake_search_gallery)

    async def _fake_discover(query, max_images=None):
        return [{"src": "https://example.org/linac.jpg", "alt": "LINAC", "page_url": "https://example.org/page", "page_title": "LINAC"}]

    async def _fake_store(db, query, images):
        return [{
            "image_id": "web-1", "gallery_index_id": None, "title": "LINAC",
            "image_url": images[0]["src"], "thumbnail_url": images[0]["src"], "caption": "LINAC",
            "tags": [], "source_document": "example.org", "page_number": None,
            "scanner_model": None, "manufacturer": None, "category": None,
            "source_url": images[0]["page_url"], "retrieved_at": "2026-01-01T00:00:00+00:00",
            "confidence": 55.0,
        }]

    monkeypatch.setattr("api.services.research_agent.image_discovery.discover_public_images", _fake_discover)
    monkeypatch.setattr("api.services.research_agent.image_discovery.store_discovered_images", _fake_store)

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "Show me a LINAC photo", "conversation_id": conv_id},
    )
    assert resp.status_code == 200
    assert '"type": "gallery_results"' in resp.text
    assert "web-1" in resp.text
    assert '"source_url"' in resp.text
    assert '"confidence": 55.0' in resp.text


# ──────────────────────────────────────────────────────────
# 5. Regression guard — research/Canva requests never reach image_discovery
# ──────────────────────────────────────────────────────────

def test_research_question_never_reaches_image_discovery(client, monkeypatch):
    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("image_discovery must not be reached for a plain research question")

    monkeypatch.setattr(
        "api.services.research_agent.image_discovery.discover_public_images", _fail_if_called,
    )

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "What is the newest LINAC technology?", "conversation_id": conv_id},
    )
    assert resp.status_code == 200


def test_canva_design_request_never_reaches_image_discovery(client, monkeypatch):
    async def _fail_if_called(*args, **kwargs):
        raise AssertionError("image_discovery must not be reached for a Canva design request")

    monkeypatch.setattr(
        "api.services.research_agent.image_discovery.discover_public_images", _fail_if_called,
    )

    async def _fake_design_orchestrator_run(*args, **kwargs):
        return {"type": "canva_designs", "items": []}, [], None

    monkeypatch.setattr(
        "api.services.design_orchestrator.run_design_request", _fake_design_orchestrator_run, raising=False,
    )

    db = SessionLocal()
    try:
        conv = _make_conversation(db)
        conv_id = conv.id
    finally:
        db.close()

    resp = client.post(
        "/api/chat/stream",
        json={"message": "Create a poster about baggage scanning", "conversation_id": conv_id},
    )
    assert resp.status_code == 200
