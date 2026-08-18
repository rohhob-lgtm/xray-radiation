"""
Phase 2B.5 — Autonomous Internet Learning + Manufacturer & Scientific
Intelligence tests.

Covers: is_safe_url() security gate (replacing the old trusted-domain
discovery-time reject), generalized (novel, not-hardcoded) manufacturer
detection, is_manufacturer_domain() generalization, Product/Patent/Training
node types + manufactures edge, structured paper-section extraction with
graceful degradation, aggregate_coverage(), the 2 new chat commands, and
two full end-to-end acceptance tests run through the REAL
run_mission()/discover_sources()/process_next_queue_item() pipeline with
ONLY the httpx I/O boundary mocked — proving the system genuinely
discovers, crawls, evaluates trust, dedupes, and updates the knowledge
graph on its own, from one command, with no URLs supplied by hand.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("SESSION_SECRET", "test-session-secret-at-least-16-chars")

import uuid

import httpx
import pytest

from api.config import settings
from api.db.base import SessionLocal
from api.db import crud
from api.db.models import User
from api.services.research_agent import provider_throttle as pt

USER = {"id": "phase2b5-test-user", "username": "learner-tester@example.com", "name": "Learner Tester"}

_created_mission_ids: list[str] = []


def _tag() -> str:
    return uuid.uuid4().hex[:10]


def _ensure_user() -> None:
    s = SessionLocal()
    try:
        if not s.get(User, USER["id"]):
            s.add(User(id=USER["id"], username=USER["username"], name=USER["name"]))
            s.commit()
    finally:
        s.close()


def _new_mission(db, *, mission_text=None, mode="quick_scan", limits=None):
    mission_text = mission_text or f"phase2b5 test {_tag()}"
    m = crud.create_research_mission(
        db, user_id=USER["id"], mission_text=mission_text, mode=mode, free_mode=True,
        limits=limits or {"max_pages": 15, "max_files": 15, "max_storage_mb": 50, "max_depth": 1,
                           "min_relevance_score": 0.0, "min_quality_score": 0.0},
    )
    _created_mission_ids.append(m.id)
    return m


@pytest.fixture(autouse=True)
def _archive_created_missions():
    """Same convention as test_research_memory.py/test_mission_scheduler.py."""
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


@pytest.fixture(autouse=True)
def _fast_provider_throttle(monkeypatch):
    """The two acceptance tests below drive the REAL discover_sources() ->
    perform_hybrid_external_research()/call_with_throttle() path across
    several topics/queries — call_with_throttle's per-provider token bucket
    defaults (e.g. web_search=15 RPM, i.e. one real call every 4s) are
    correct for production but would make one test take minutes. _states is
    a module-level cache built once per provider on first use (see
    provider_throttle._get_state()) and never rebuilt afterward — same
    pattern test_provider_throttle.py's own _reset_provider_state fixture
    already established, reused here rather than reinvented. Raising the
    RPM ceiling (not bypassing the throttle mechanism itself, which still
    runs for real) is what actually makes this fast."""
    for name in pt.PROVIDER_NAMES:
        monkeypatch.setattr(settings, f"research_provider_{name}_rpm", 100_000, raising=False)
        monkeypatch.setattr(settings, f"research_provider_{name}_concurrency", 20, raising=False)
    pt._states.clear()

    # Politeness delays (discovery.py's 0.5s between DDG queries, job_runner.py's
    # 1.0s between crawl-loop iterations) are real, deliberate, and correct in
    # production, but have no bearing on correctness here — same "no test needs
    # wall-clock delay to pass" justification test_provider_throttle.py's own
    # fixture already used for its sleeps. Captures the REAL asyncio.sleep
    # BEFORE patching (same as that fixture) — _instant_sleep must call the
    # captured original, not look it up dynamically, or it recurses into itself
    # (asyncio is a process-wide singleton module: patching discovery.asyncio.sleep
    # IS patching the global asyncio.sleep).
    import asyncio as _asyncio_module
    from api.services.research_agent import discovery as _discovery_mod
    from api.services.research_agent import job_runner as _job_runner_mod

    _real_sleep = _asyncio_module.sleep

    async def _instant_sleep(*_a, **_k):
        await _real_sleep(0)

    monkeypatch.setattr(_discovery_mod.asyncio, "sleep", _instant_sleep)
    monkeypatch.setattr(_job_runner_mod.asyncio, "sleep", _instant_sleep)
    yield
    pt._states.clear()


@pytest.fixture(autouse=True)
def _no_real_start_mission(monkeypatch):
    """This file calls run_mission() directly (never through start_mission's
    asyncio.create_task fire-and-forget) — but chat-intent tests below go
    through handle_research_agent_intent's "start" action, which DOES call
    start_mission(); keep that a no-op there, same convention as every
    other test file in this suite."""
    monkeypatch.setattr("api.services.research_agent.job_runner.start_mission", lambda mission_id: None)
    monkeypatch.setattr("api.routes.research_agent.start_mission", lambda mission_id: None)


# ──────────────────────────────────────────────────────────
# is_safe_url — security gate
# ──────────────────────────────────────────────────────────

def test_is_safe_url_blocks_localhost_and_private_ips():
    from api.services.research_agent.discovery import is_safe_url
    assert is_safe_url("http://localhost/x") is False
    assert is_safe_url("http://127.0.0.1/x") is False
    assert is_safe_url("http://169.254.169.254/latest/meta-data") is False
    assert is_safe_url("http://10.0.0.5/internal") is False
    assert is_safe_url("http://192.168.1.1/router") is False


def test_is_safe_url_blocks_non_http_scheme():
    from api.services.research_agent.discovery import is_safe_url
    assert is_safe_url("ftp://example.com/x") is False
    assert is_safe_url("file:///etc/passwd") is False
    assert is_safe_url("javascript:alert(1)") is False


def test_is_safe_url_allows_ordinary_hostname():
    from api.services.research_agent.discovery import is_safe_url
    assert is_safe_url("https://www.example.com/page") is True
    assert is_safe_url("https://random-manufacturer-site.example/products") is True


@pytest.mark.asyncio
async def test_web_search_trusted_no_longer_rejects_untrusted_domain(monkeypatch):
    """The core "widen discovery" change: a DuckDuckGo hit on a domain NOT
    in TRUSTED_DOMAINS must now come back, not be silently dropped."""
    from api.services.research_agent import discovery

    html = '<a class="result__a" href="https://www.totally-unlisted-vendor.example/">Vendor</a>'

    async def _fake_get(self, url, *a, **k):
        return httpx.Response(200, text=html, request=httpx.Request("GET", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    async with httpx.AsyncClient() as client:
        results = await discovery._web_search_trusted("some query", client)
    assert any("totally-unlisted-vendor.example" in r["url"] for r in results)


# ──────────────────────────────────────────────────────────
# Generalized manufacturer detection
# ──────────────────────────────────────────────────────────

def test_planner_detects_novel_manufacturer_via_trigger_word():
    from api.services.research_brain.planner import _detect_manufacturer
    assert _detect_manufacturer("Tell me about the manufacturer called Delta Screening") == "Delta Screening"
    assert _detect_manufacturer("Learn about Acme Security's X-ray scanners") == "Acme Security"


def test_planner_detects_novel_manufacturer_arabic():
    from api.services.research_brain.planner import _detect_manufacturer
    result = _detect_manufacturer("ابحث عن شركة الفا للأمن")
    assert result is not None and "الفا" in result


def test_planner_generic_topic_does_not_misfire_as_manufacturer():
    from api.services.research_brain.planner import _detect_manufacturer
    assert _detect_manufacturer("Learn about generic X-ray detectors") is None
    assert _detect_manufacturer("Learn everything about X-ray tube maintenance") is None


def test_planner_still_uses_known_manufacturers_fast_path():
    from api.services.research_brain.planner import _detect_manufacturer
    assert _detect_manufacturer("Learn everything about Rapiscan X-ray systems") == "Rapiscan"


def test_is_manufacturer_domain_generalizes_via_name_hint():
    from api.services.source_trust import source_trust_service as sts
    # Known hardcoded domain — unaffected by the new optional param.
    assert sts.is_manufacturer_domain("https://rapiscansystems.com/x") is True
    # A brand-new manufacturer's own domain — invisible without the hint...
    assert sts.is_manufacturer_domain("https://www.meridianscansystems.example/x") is False
    # ...and correctly recognized once the mission's detected name is passed.
    assert sts.is_manufacturer_domain("https://www.meridianscansystems.example/x", "Meridian Scan Systems") is True
    assert sts.is_manufacturer_domain("https://nist.gov/x", "Meridian Scan Systems") is False


# ──────────────────────────────────────────────────────────
# Manufacturer Intelligence graph vocabulary
# ──────────────────────────────────────────────────────────

def test_local_extraction_valid_node_types_include_new_types():
    from api.services.research_brain.local_extraction import _VALID_NODE_TYPES, _VALID_RELATIONSHIPS
    for t in ("Product", "Patent", "Training", "Paper", "Author", "Institution"):
        assert t in _VALID_NODE_TYPES
    for r in ("manufactures", "authored_by", "affiliated_with", "cites"):
        assert r in _VALID_RELATIONSHIPS


def test_deterministic_extract_accepts_manufacturer_hint_produces_product_patent_training():
    from api.services.research_brain.deterministic_extraction import deterministic_extract

    text = (
        "Meridian Scan Systems X9 is our flagship baggage scanner. "
        "See patent US 9876543 for the detector design. "
        "New operators must complete operator training before certification."
    )
    result = deterministic_extract(text, manufacturer_hint="Meridian Scan Systems")
    node_types = {(n["label"], n["type"]) for n in result.nodes}
    assert ("Meridian Scan Systems", "Manufacturer") in node_types
    assert any(t == "Product" and "Meridian Scan Systems" in label for label, t in node_types)
    assert any(t == "Patent" for _, t in node_types)
    assert any(t == "Training" for _, t in node_types)
    assert any(e["relationship"] == "manufactures" for e in result.edges)


# ──────────────────────────────────────────────────────────
# Structured paper-section extraction
# ──────────────────────────────────────────────────────────

def test_paper_extraction_extracts_recognized_sections():
    from api.services.research_brain.paper_extraction import extract_paper_sections

    text = (
        "Abstract\nThis thesis investigates LINAC electron guns.\n\n"
        "Introduction\nLinear accelerators require efficient electron guns.\n\n"
        "Methodology\nWe used a thermionic cathode and a Faraday cup.\n\n"
        "Results\nBeam current reached 50 mA at 6 MeV.\n\n"
        "Limitations\nSpace-charge effects were not measured.\n\n"
        "Future Work\nExplore photocathode alternatives.\n\n"
        "References\nSee doi:10.1234/example.2020 for related work.\n"
    )
    sections = extract_paper_sections(text, {"abstract": "fallback abstract"})
    assert sections["abstract"] == "fallback abstract"
    assert "electron guns" in sections["research_problem"]
    assert "thermionic cathode" in sections["methodology"]
    assert "50 mA" in sections["results"]
    assert "space-charge" in sections["limitations"].lower()
    assert "photocathode" in sections["future_work"]
    assert "10.1234/example.2020" in sections["citations"]


def test_paper_extraction_degrades_gracefully_without_headers():
    from api.services.research_brain.paper_extraction import extract_paper_sections

    sections = extract_paper_sections("just some unstructured prose with no headings at all", {"abstract": "abs"})
    assert sections["abstract"] == "abs"
    assert sections["methodology"] == ""
    assert sections["citations"] == []


# ──────────────────────────────────────────────────────────
# Coverage-target auto-continue loop
# ──────────────────────────────────────────────────────────

def test_aggregate_coverage_mean_and_empty_case():
    from api.services.research_brain.gap_detector import aggregate_coverage
    assert aggregate_coverage([]) == 100.0
    assert aggregate_coverage([{"coverage_pct": 40.0}, {"coverage_pct": 80.0}]) == 60.0


# ──────────────────────────────────────────────────────────
# Chat commands
# ──────────────────────────────────────────────────────────

def test_chat_intent_detects_what_learned_and_what_unknown():
    from api.services.research_agent_chat_intent import detect_research_agent_intent
    assert detect_research_agent_intent("What have you learned?")["action"] == "what_learned"
    assert detect_research_agent_intent("ماذا تعلمت؟")["action"] == "what_learned"
    assert detect_research_agent_intent("What do you still not know?")["action"] == "what_unknown"
    assert detect_research_agent_intent("ما الذي ما زلت لا تعرفه؟")["action"] == "what_unknown"


@pytest.mark.asyncio
async def test_chat_handle_what_learned_and_what_unknown_return_real_data():
    from api.services.research_agent_chat_intent import handle_research_agent_intent

    db = SessionLocal()
    try:
        mission = _new_mission(db)
        result = await handle_research_agent_intent(db, USER["id"], {"action": "what_learned"})
        assert result["type"] == "research_what_learned"
        assert result["mission"]["id"] == mission.id

        result2 = await handle_research_agent_intent(db, USER["id"], {"action": "what_unknown"})
        assert result2["type"] == "research_what_unknown"
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# Acceptance test 1 — novel manufacturer, real run_mission() end-to-end
# ──────────────────────────────────────────────────────────

_MERIDIAN_PRODUCT_HTML = """
<html><body>
<h1>Product Catalog</h1>
<p>Meridian Scan Systems X9 is our flagship dual-energy X-ray baggage and cargo scanner for
airport and border security screening. The X9 detector array uses advanced scintillation
crystals to identify threat materials with industry-leading image quality. Its high-voltage
generator delivers stable kVp output for consistent penetration through dense cargo.
Installation, calibration, and routine maintenance follow our standard operating procedures
(SOP) and technical manual, and every unit meets IEC and ANSI safety and shielding requirements
to limit operator radiation dose. The conveyor system and collimator assembly are engineered
for reliable throughput in high-volume screening environments, with troubleshooting guides
available for field technicians.</p>
</body></html>
"""


@pytest.mark.asyncio
async def test_run_mission_full_pipeline_generalizes_to_novel_manufacturer(monkeypatch):
    from api.services.research_agent.job_runner import run_mission
    from api.db import crud as _crud

    product_url = "https://www.meridianscansystems.example/products"
    ddg_html = f'<a class="result__a" href="{product_url}">Meridian Scan Systems</a>'

    async def _fake_get(self, url, *a, **k):
        if url.rstrip("/").endswith("/robots.txt"):
            return httpx.Response(200, text="", request=httpx.Request("GET", url))
        if "duckduckgo.com" in url:
            return httpx.Response(200, text=ddg_html, request=httpx.Request("GET", url))
        if url.startswith(product_url):
            return httpx.Response(200, text=_MERIDIAN_PRODUCT_HTML, request=httpx.Request("GET", url))
        return httpx.Response(200, json={}, request=httpx.Request("GET", url))

    async def _fake_post(self, url, *a, **k):
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    db = SessionLocal()
    try:
        mission = _new_mission(db, mission_text="Learn about the manufacturer called Meridian Scan Systems")
        mission_id = mission.id
    finally:
        db.close()

    await run_mission(mission_id)

    db = SessionLocal()
    try:
        mission = _crud.get_research_mission(db, mission_id)
        assert mission.status == "completed"
        assert mission.detected_manufacturer == "Meridian Scan Systems"

        sources = _crud.list_research_sources(db, mission_id)
        assert any("meridianscansystems.example" in s.url for s in sources)
        matched = next(s for s in sources if "meridianscansystems.example" in s.url)
        assert matched.trust_status == "unproven"

        manufacturer_node = _crud.get_knowledge_node_by_label(db, "Meridian Scan Systems", "Manufacturer")
        assert manufacturer_node is not None
        product_node = _crud.get_knowledge_node_by_label(db, "Meridian Scan Systems X9", "Product")
        assert product_node is not None

        from api.db.models import KnowledgeEdge
        manufactures_edge = (
            db.query(KnowledgeEdge)
            .filter(KnowledgeEdge.from_node_id == manufacturer_node.id, KnowledgeEdge.relationship == "manufactures")
            .first()
        )
        assert manufactures_edge is not None
        assert manufactures_edge.to_node_id == product_node.id

        assert mission.coverage_rounds_completed >= 1
    finally:
        db.close()


# ──────────────────────────────────────────────────────────
# Acceptance test 2 — LINAC scientific literature, real run_mission()
# ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_mission_full_pipeline_learns_from_open_access_linac_thesis(monkeypatch):
    """The user's own acceptance scenario: 'Learn from published theses and
    papers about LINAC components and the latest X-ray source technologies.'

    All identifying strings/content below are tagged per-invocation (_tag())
    — this suite reuses a persistent scratch DB across repeated runs (see
    tests/conftest.py), so a fixed DOI/full-text would hash-collide with an
    earlier run's already-ingested content on the second+ run and silently
    skip extraction as "already known" (Research Memory dedup working
    correctly, just against this test's own stale fixture data)."""
    from api.services.research_agent.job_runner import run_mission
    from api.db import crud as _crud

    run_tag = _tag()
    linac_doi = f"10.9999/linac-thesis-{run_tag}"
    linac_doi_url = f"https://doi.org/{linac_doi}"
    linac_title = f"Design and Optimization of a Compact LINAC Electron Gun for X-Ray Sources {run_tag}"

    openalex_linac_item = {
        "display_name": linac_title,
        "doi": linac_doi_url,
        "id": f"https://openalex.org/W{run_tag}",
        "type": "dissertation",
        "publication_year": 2024,
        "cited_by_count": 3,
        "authorships": [
            {"author": {"display_name": f"Sara Ahmed {run_tag}"}},
            {"author": {"display_name": f"John Miller {run_tag}"}},
        ],
        "primary_location": {"source": {"display_name": f"Massachusetts Institute of Technology {run_tag}"}},
        "open_access": {"is_oa": True, "oa_url": linac_doi_url},
    }

    linac_full_text_html = f"""
<html><body>
<h2>Abstract</h2>
<p>This thesis {run_tag} investigates LINAC electron gun design for compact X-ray sources used in cargo screening.</p>
<h2>Introduction</h2>
<p>Linear accelerators require efficient electron guns to generate high-energy X-rays for security screening applications.</p>
<h2>Methodology</h2>
<p>We used a thermionic cathode and measured beam current with a Faraday cup under vacuum conditions.</p>
<h2>Results</h2>
<p>Beam current reached 50 mA at 6 MeV with stable pulse repetition.</p>
<h2>Limitations</h2>
<p>The measurement setup did not account for space-charge effects at higher currents.</p>
<h2>Future Work</h2>
<p>Future studies should explore photocathode alternatives for higher brightness beams.</p>
<h2>References</h2>
<p>See doi:10.1111/other-paper-{run_tag}.2019 for related work on klystron RF sources.</p>
</body></html>
"""

    # A NOT-open-access paper — proves the legal/copyright gate: metadata-only,
    # no crawl, no embedding, no graph extraction.
    paywalled_doi = f"10.5555/paywalled-paper-{run_tag}"
    paywalled_doi_url = f"https://doi.org/{paywalled_doi}"
    crossref_paywalled_item = {
        "DOI": paywalled_doi,
        "title": [f"Klystron RF Source Efficiency for X-Ray Radiation Generation in LINAC Systems {run_tag}"],
        "author": [{"given": "Klaus", "family": "Weber"}],
        "issued": {"date-parts": [[2022]]},
        "container-title": ["Journal of Accelerator Physics"],
        "type": "journal-article",
        "abstract": "A closed-access study of klystron RF source efficiency and its effect on X-ray radiation output and detector response in LINAC-based imaging systems.",
    }

    async def _fake_get(self, url, *a, **k):
        if url.rstrip("/").endswith("/robots.txt"):
            return httpx.Response(200, text="", request=httpx.Request("GET", url))
        if "api.openalex.org" in url:
            return httpx.Response(200, json={"results": [openalex_linac_item]}, request=httpx.Request("GET", url))
        if "api.crossref.org" in url:
            return httpx.Response(200, json={"message": {"items": [crossref_paywalled_item]}}, request=httpx.Request("GET", url))
        if "duckduckgo.com" in url:
            return httpx.Response(200, text="<html><body>no results</body></html>", request=httpx.Request("GET", url))
        if url.startswith(linac_doi_url):
            return httpx.Response(200, text=linac_full_text_html, request=httpx.Request("GET", url))
        if url.startswith(paywalled_doi_url):
            # Must never actually be fetched — the OA gate should skip the
            # crawl entirely for this source. If this branch is hit, the
            # test's later "no crawl happened" assertion will catch it.
            return httpx.Response(200, text="<html><body>SHOULD NOT BE FETCHED</body></html>", request=httpx.Request("GET", url))
        return httpx.Response(200, json={}, request=httpx.Request("GET", url))

    async def _fake_post(self, url, *a, **k):
        return httpx.Response(200, json={}, request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx.AsyncClient, "get", _fake_get)
    monkeypatch.setattr(httpx.AsyncClient, "post", _fake_post)

    db = SessionLocal()
    try:
        mission = _new_mission(
            db,
            mission_text=f"تعلّم من رسائل الدكتوراه والأبحاث المنشورة عن مكونات LINAC وأحدث تقنيات مصادر X-Ray {run_tag}",
        )
        mission_id = mission.id
    finally:
        db.close()

    await run_mission(mission_id)

    db = SessionLocal()
    try:
        mission = _crud.get_research_mission(db, mission_id)
        assert mission.status == "completed"

        sources = _crud.list_research_sources(db, mission_id)
        oa_source = next((s for s in sources if s.source_doi == linac_doi), None)
        assert oa_source is not None, "the real discovery chain (discover_sources -> perform_hybrid_external_research -> OpenAlex) must have surfaced this source"

        paywalled_source = next((s for s in sources if s.source_doi == paywalled_doi), None)
        assert paywalled_source is not None, "the paywalled source must still be recorded (metadata-only)"
        assert paywalled_source.accepted_into_kb is False
        assert paywalled_source.content_hash is None  # never actually crawled

        # The open-access thesis was fully sectioned into AcademicPaperMetadata.
        paper_meta = _crud.get_academic_paper_metadata_by_source(db, oa_source.id)
        assert paper_meta is not None
        assert "thermionic cathode" in paper_meta.methodology
        assert "50 mA" in paper_meta.results
        assert "space-charge" in paper_meta.limitations.lower()
        assert paper_meta.is_open_access is True

        # Paper/Author/Institution graph nodes + edges.
        paper_node = _crud.get_knowledge_node_by_label(db, linac_title, "Paper")
        assert paper_node is not None
        author_node = _crud.get_knowledge_node_by_label(db, f"Sara Ahmed {run_tag}", "Author")
        assert author_node is not None
        institution_node = _crud.get_knowledge_node_by_label(db, f"Massachusetts Institute of Technology {run_tag}", "Institution")
        assert institution_node is not None

        from api.db.models import KnowledgeEdge
        authored_by_edge = (
            db.query(KnowledgeEdge)
            .filter(KnowledgeEdge.from_node_id == paper_node.id, KnowledgeEdge.relationship == "authored_by")
            .first()
        )
        assert authored_by_edge is not None
        affiliated_edge = (
            db.query(KnowledgeEdge)
            .filter(KnowledgeEdge.from_node_id == author_node.id, KnowledgeEdge.relationship == "affiliated_with")
            .first()
        )
        assert affiliated_edge is not None

        # Research Memory recorded real activity for this mission's topics.
        topics = _crud.list_research_topics(db, mission_id)
        memory_ids = {t.topic_memory_id for t in topics if t.topic_memory_id}
        assert memory_ids
        any_activity = False
        for mid in memory_ids:
            mem = _crud.get_topic_research_memory(db, mid)
            if mem and (mem.downloaded_files_count > 0 or mem.processed_hashes_count > 0):
                any_activity = True
        assert any_activity

        # Trust was computed (bootstrap default) for the open-access source.
        assert oa_source.trust_status == "unproven"

        # Coverage-round loop actually ran.
        assert mission.coverage_rounds_completed >= 1

        # Duplicate protection: the platform-wide "don't re-queue/re-fetch an
        # already-known URL" guarantee (crud.enqueue_research_urls' own
        # per-mission dedup, which is exactly why the coverage-round loop
        # above — re-discovering this SAME OpenAlex item across 3 rounds —
        # never created more than one ResearchSource/AcademicPaperMetadata/
        # Paper node for it) holds when attempted again explicitly: no new
        # queue row is created for a URL already queued for this mission.
        topic_for_oa = next((t for t in topics if t.id), None)
        newly_queued = _crud.enqueue_research_urls(
            db, mission_id, [{"url": oa_source.url, "topic_id": topic_for_oa.id if topic_for_oa else None}],
        )
        assert newly_queued == [], "re-enqueueing an already-known URL must not create a duplicate queue item"

        # And the graph itself has exactly one Paper node for this thesis,
        # despite 3 coverage rounds of re-discovering the same source.
        from api.db.models import KnowledgeNode
        paper_nodes_with_label = (
            db.query(KnowledgeNode)
            .filter(KnowledgeNode.label == linac_title, KnowledgeNode.node_type == "Paper")
            .count()
        )
        assert paper_nodes_with_label == 1
    finally:
        db.close()
