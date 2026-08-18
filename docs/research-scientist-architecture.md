# Research Studio → Autonomous AI Research Scientist
### System Architecture & Execution Roadmap (v1 — for review)

Status: **DRAFT — awaiting approval before implementation begins.**

This document is the architecture for turning Research Studio from a retrieval-then-write pipeline
into a ten-module research-scientist system: it plans, searches, integrates knowledge, reasons,
innovates, designs methodology, writes, reviews itself, and specializes in X-ray security science.
Nothing here is implemented yet. Once you approve (or redline) this doc, implementation proceeds
phase by phase against it.

---

## 0. What already exists (do not rebuild this)

The current pipeline is real, not a thin LLM wrapper. It is the foundation for Modules 1–3 and 7 below,
not a throwaway prototype.

| Capability | Where | Keep / Replace |
|---|---|---|
| Topic normalization, keyword/synonym expansion | `research_pipeline.py: run_phase1_research_pipeline` (826–1118) | **Keep**, becomes Module 1 core |
| Async multi-source retrieval (Crossref, PubMed, arXiv, patents) | `innovation_external_research.py: _crossref_sources/_pubmed_sources/_arxiv_sources/_patent_sources` | **Keep, refactor into providers** (Module 2) |
| DuckDuckGo HTML scraping for standards/manufacturers | `innovation_external_research.py: _standards_and_regulatory_sources/_manufacturer_sources` (416–516) | **Replace** — ToS-fragile, not a real API. Superseded by DOAJ/CORE + an explicit "regulatory documents" allowlist provider that doesn't scrape search engines. |
| Source verification (DOI format, URL sanity, relevance score) | `research_pipeline.py: verify_sources` (571–623); `innovation_external_research.py: _score_relevance/_is_relevant` (135–182) | **Keep as first-pass filter, extend** with live DOI resolution (Module 2) |
| KB retrieval (internal uploaded documents) | `research_pipeline.py: retrieve_chunks` (947–978) | **Keep** — internal-KB source stays a provider alongside external ones |
| Evidence extraction, literature matrix, gap matrix, outline | `research_pipeline.py` (1029–1099) | **Keep, extend** into Modules 3–4 |
| Per-section LLM synthesis + citation validator | `research_pipeline.py: _llm_write_section/_validate_scientific_manuscript` (1641–1912) | **Keep as Module 7 core**, insert Modules 4–6 and 8 before/around it |
| DOCX/PDF/HTML export | `export.py`, `docgen.py` | **Keep**, extend figure/table embedding (SVG) |
| LLM provider abstraction | `ai_providers/base.py`, `ai_providers/registry.py` | **Reuse the exact pattern** for the new literature-provider layer |
| Generic knowledge-graph tables (`KnowledgeNode`/`KnowledgeEdge`) | `db/models.py:895–930` | **Reuse schema pattern**, scope a parallel graph for research (see §4) — currently scoped to training/equipment manuals, semantics don't fit papers/claims directly |
| `ResearchPipelineRun.artifacts` (JSON blob per run) | `db/models.py:206–223` | **Keep as the artifact bus** connecting modules (see §3) |

What's genuinely missing: Semantic Scholar/OpenAlex/CORE/DOAJ providers, live DOI resolution, a
provider-abstracted licensed-source slot (IEEE/Springer/Elsevier), real novelty scoring (today's
"innovation" module is a relevance filter, not a novelty comparator), a reviewer/revision loop,
SVG figure generation, methodology-derived (not keyword-templated) equations, and any cross-run
memory/learning.

---

## 1. Guiding constraints (carried through every module)

1. **No fabrication.** Every factual/citation claim traces to a retrieved source with a resolvable
   DOI/URL, or is explicitly labeled a *proposed/hypothesized* contribution — never presented as
   an established fact.
2. **No fake citations, ever.** A reference only enters the bibliography after passing DOI/URL
   resolution (Module 2). If resolution fails, the source is dropped, not softened.
3. **No provider hardcoding.** The reasoning/writing engine only talks to `LiteratureSource` DTOs
   (§2.2) — it never knows or cares whether a source came from Crossref or IEEE Xplore.
4. **No Google Scholar scraping**, ever, in any module. Licensed providers (IEEE/Springer/Elsevier)
   stay disabled until real credentials are configured; they must never partially work with fake
   data.
5. **Degrade, don't crash.** Every external call is timeout-wrapped and optional; the pipeline
   must still produce a valid (smaller) result if 8 of 10 sources are down — this already exists
   today (`asyncio.gather(..., return_exceptions=True)` pattern) and must be preserved everywhere.
6. **Cost-aware.** LLM calls in Modules 4–8 (reasoning, innovation, writing, reviewing) are
   multi-pass and materially more expensive than today's single-pass-per-section writing. This
   needs an explicit cost guard (Module 7 depends on §6).

---

## 2. Module 1 — Research Planner

**Responsibility:** turn a raw research question into an executable research strategy.

Extends the existing topic-normalization/keyword-expansion step (`research_pipeline.py:826-909`)
with an explicit, inspectable plan object instead of falling straight into retrieval.

```
ResearchPlan:
  raw_question: str
  normalized_topic: str
  research_objectives: list[str]          # 3-6 concrete objectives, LLM-drafted, evidence-free
  search_keywords: list[KeywordCluster]    # existing expansion logic, restructured
  kb_scope: KBScope                        # which internal KB domains/tags apply
  provider_scope: list[str]                # which literature providers to query, and why
  expected_paper_type: str                 # "paper_ieee" | "literature_review" | "patent_disclosure" | ...
  novelty_target: str                      # what kind of contribution is being sought (method/architecture/dataset/...)
  created_at, plan_id
```

**Interface:**
```python
class ResearchPlanner:
    async def build_plan(self, question: str, mode: str, kb_scope: KBScope) -> ResearchPlan: ...
```

This is a single LLM call (cheap) plus the existing deterministic keyword-expansion code. The plan
is persisted into `ResearchPipelineRun.artifacts["plan"]` so every later module can see *why* a
search was scoped the way it was — this is what makes the pipeline auditable instead of a black box.

---

## 3. Module 2 — Scientific Search Engine (provider-abstracted)

This is the module you asked to be designed so no future redesign is needed. Full spec below.

### 2.1 Provider interface

Mirrors `BaseAIProvider` (`ai_providers/base.py`) exactly, so the pattern is familiar to anyone who's
touched the LLM provider layer:

```python
class BaseLiteratureProvider(ABC):
    provider_id: str          # "crossref", "openalex", "semantic_scholar", "core", "doaj",
                               # "pubmed", "arxiv", "ieee_xplore", "springer", "sciencedirect"
    provider_name: str
    category: Literal["open", "licensed", "internal"]
    requires_credentials: bool

    @property
    def is_configured(self) -> bool:
        """Licensed providers return False until real API keys are present — never mock data."""

    @abstractmethod
    async def search(self, query: str, filters: SearchFilters) -> list[LiteratureSource]: ...

    @abstractmethod
    async def retrieve_metadata(self, source_id: str) -> LiteratureSource | None: ...

    @abstractmethod
    async def retrieve_abstract(self, source_id: str) -> str | None: ...

    @abstractmethod
    async def retrieve_doi(self, source_id: str) -> str | None: ...

    @abstractmethod
    async def verify_doi(self, doi: str) -> DOIVerificationResult: ...

    @abstractmethod
    async def retrieve_citation_count(self, source_id: str) -> int | None: ...

    @abstractmethod
    async def retrieve_pdf_if_legal(self, source_id: str) -> PDFAvailability: ...
```

`LiteratureSource` is the single DTO every downstream module consumes — provider-agnostic:

```python
class LiteratureSource(BaseModel):
    source_id: str
    provider_id: str
    title: str
    authors: list[str]
    year: int | None
    venue: str                       # journal/conference name
    doi: str | None
    doi_verified: bool
    url: str
    abstract: str | None
    keywords: list[str]
    citation_count: int | None
    is_peer_reviewed: bool | None
    pdf_url: str | None              # only set if retrieve_pdf_if_legal confirmed OA license
    relevance_score: float           # from existing _score_relevance logic
    quality_score: float             # NEW — see 2.4
    retrieved_at: datetime
```

### 2.2 Provider registry (parallel fan-out, not single-active)

Unlike the LLM registry (one *active* provider), literature providers all run concurrently and
results are merged — this reuses the existing `asyncio.gather(..., return_exceptions=True)` fan-out
already in `innovation_external_research.py:549-556`, just generalized:

```python
class LiteratureProviderRegistry:
    def register(self, provider: BaseLiteratureProvider) -> None: ...
    def enabled_providers(self, scope: list[str] | None = None) -> list[BaseLiteratureProvider]:
        """Returns providers where is_configured is True, optionally filtered to plan.provider_scope."""

    async def search_all(self, query: str, filters: SearchFilters) -> list[LiteratureSource]:
        """Fan out to every enabled provider in parallel, timeout each independently,
        merge, dedupe (2.3), rank (2.4). Never raises — a dead provider just contributes zero results."""
```

Bootstrap (`literature_providers/registry.py`), same shape as `ai_providers/registry.py`'s
`_bootstrap_registry`:

```python
registry.register(CrossrefProvider())                                    # open, no key
registry.register(OpenAlexProvider())                                    # open, no key
registry.register(SemanticScholarProvider(api_key=settings.s2_api_key))  # open, optional key (higher rate limit)
registry.register(COREProvider(api_key=settings.core_api_key))           # open, free key required
registry.register(DOAJProvider())                                        # open, no key
registry.register(PubMedProvider())                                      # open, no key — existing code, refactored
registry.register(ArxivProvider())                                       # open, no key — existing code, refactored
registry.register(IEEEXploreProvider(api_key=settings.ieee_api_key))     # licensed, is_configured only if key set
registry.register(SpringerProvider(api_key=settings.springer_api_key))   # licensed, same
registry.register(ScienceDirectProvider(api_key=settings.sciencedirect_api_key))  # licensed, same
registry.register(InternalKBProvider())                                  # internal — wraps existing retrieve_chunks
```

New `Settings` fields in `config.py` (all default `""`, i.e., disabled):
`semantic_scholar_api_key`, `core_api_key`, `ieee_api_key`, `springer_api_key`, `sciencedirect_api_key`.
No env values are assumed to exist — licensed providers stay dark until you supply keys.

Google Scholar is explicitly **not** a provider class. If/when you want it, the only acceptable
path is a user-initiated browser-automation session (you're logged in, you click "search"), which
is a UI feature request, not a `BaseLiteratureProvider` — noted as a non-goal here so it's not
silently attempted later.

### 2.3 Deduplication

Extends existing fusion logic (`research_pipeline.py:979-1019`). Merge key priority: (1) verified
DOI exact match, (2) normalized-title + first-author fuzzy match (existing token-overlap approach,
threshold tuned). When two providers return the same paper, keep the record with the higher
`quality_score` (2.4) and union their metadata (e.g., Crossref has the DOI, Semantic Scholar has
the citation count).

### 2.4 Quality ranking (`quality_score`)

Replaces "relevance-only" ranking with the mission's actual criteria:

```
quality_score = w1*relevance_score + w2*citation_recency_norm + w3*citation_count_norm
              + w4*peer_review_flag + w5*doi_verified_flag - w6*retraction_flag
```
Weights configurable per `expected_paper_type` (a literature review weights recency/coverage
differently than a methods paper). Sources below a floor are dropped before evidence extraction,
same enforcement point as today's `verify_sources`.

### 2.5 Live DOI verification

Today: format-only regex (`_DOI_RE`). New: `verify_doi()` resolves `https://doi.org/{doi}` (or the
provider's own metadata endpoint) and confirms the returned title matches the claimed title
(fuzzy match ≥ threshold). A source with an unverifiable DOI is downgraded (URL-only citation) or
dropped, never presented as DOI-backed if it isn't.

---

## 4. Module 3 — Knowledge Integration Engine

**Responsibility:** turn a flat list of `LiteratureSource` + extracted evidence into a connected,
queryable structure with contradiction and confidence tracking — this is the actual "knowledge
graph" the mission asks for.

**Schema** (new tables, `db/models.py`) — deliberately parallel to the existing `KnowledgeNode`/
`KnowledgeEdge` pattern rather than reusing those tables directly, because node/relationship
semantics for equipment manuals ("Component causes Failure") don't map cleanly onto scientific
claims ("Paper A supports Claim X, Paper B contradicts it"):

```python
class ResearchKnowledgeNode(Base):
    __tablename__ = "research_knowledge_nodes"
    id, run_id (FK -> research_pipeline_runs)
    node_type: str   # Paper | Author | Method | Dataset | Algorithm | Material | Sensor |
                      # Standard | Claim | Concept
    label: str
    source_id: str | None      # -> LiteratureSource.source_id when node_type == Paper
    metadata: JSON              # DOI, year, venue, etc. for Paper nodes; free-form for others

class ResearchKnowledgeEdge(Base):
    __tablename__ = "research_knowledge_edges"
    id, run_id
    from_node_id, to_node_id
    relationship: str   # supports | contradicts | extends | uses_method | uses_dataset |
                          # authored_by | cites | benchmarks_against
    confidence: float    # 0-1, LLM-estimated + evidence-count-weighted
    evidence_source_ids: JSON   # list of LiteratureSource.source_id backing this edge
```

**Pipeline stage:**
```python
class KnowledgeIntegrationEngine:
    async def build_graph(self, run_id: str, sources: list[LiteratureSource],
                           evidence: list[ExtractedFact]) -> ResearchKnowledgeGraph: ...
    async def detect_contradictions(self, graph) -> list[Contradiction]: ...
    async def merge_evidence(self, graph) -> list[MergedClaim]:
        """Group claims from multiple papers that assert the same thing; attach a
        confidence score = f(number of independent supporting sources, their quality_score,
        recency, presence of contradicting sources)."""
```

Fact extraction reuses/extends the existing evidence-extraction step
(`research_pipeline.py:1029-1034`) but outputs structured `(claim, method, subject, source_id)`
tuples instead of prose snippets, so they can become graph edges. Contradiction detection is an
LLM pass over claim clusters sharing a subject/method ("Paper A reports 94% accuracy with dual-energy
CT for organics; Paper B reports 78% on a comparable dataset — flag as contradiction, not
consensus"). This is what later lets the Reasoning Engine say something more useful than "several
papers discuss X."

The graph is queryable per-run (scoped by `run_id`) — this is not a cross-user global graph yet;
cross-run memory is explicitly Module 9's job, not Module 3's.

---

## 5. Module 4 — Scientific Reasoning Engine

**Responsibility:** analyze, don't summarize. Operates on the knowledge graph from Module 3, not
raw source text.

```python
class ScientificReasoningEngine:
    async def analyze_paper_critically(self, source: LiteratureSource, claims: list[MergedClaim]) -> CriticalAnalysis:
        """Per-source structured critique, not prose summary:
        what_was_done, what_was_not_done, assumptions, limitations,
        failure_modes, ai_improvement_potential, open_questions"""

    async def compare_methodologies(self, sources: list[LiteratureSource]) -> MethodologyComparison: ...

    async def discover_gaps(self, graph: ResearchKnowledgeGraph) -> list[RankedGap]:
        """Extends existing gap-matrix logic (research_pipeline.py:1079) — currently a
        heuristic pass over source coverage; becomes graph-driven: a gap is a claim/method
        combination with low source density, single-source support, or unresolved contradictions."""

    async def generate_hypotheses(self, gaps: list[RankedGap]) -> list[Hypothesis]: ...
```

`RankedGap` and `Hypothesis` carry a `confidence` and `evidence_source_ids` field like everything
else in this pipeline — a "gap" is never asserted without pointing at the graph nodes that show
the coverage hole.

**Output → `ResearchPipelineRun.artifacts["reasoning"]`.**

---

## 6. Module 5 — Innovation Engine

**Responsibility:** the actual novelty engine (today's `innovation_external_research.py` is a
relevance filter — this is new logic, not a rename).

```python
class InnovationEngine:
    async def generate_ideas(self, gaps: list[RankedGap], hypotheses: list[Hypothesis],
                              domain_layer: XRayDomainContext) -> list[ResearchIdea]:
        """New algorithms, detector concepts, AI pipelines, architectures,
        optimization methods, workflows, datasets — each idea grounded in a
        specific gap, not free-associated."""

    async def score_novelty(self, idea: ResearchIdea, graph: ResearchKnowledgeGraph) -> NoveltyScore:
        """Compares the idea's core mechanism against every Method/Algorithm node already
        in the graph (embedding similarity + LLM judgment on what's actually different).
        novelty_score in [0,1], with an explicit rationale — never a bare number."""

    async def flag_patent_opportunity(self, idea: ResearchIdea) -> PatentOpportunityFlag | None:
        """Heuristic + LLM check against existing patent sources already retrieved in
        Module 2 (patent provider). Flags 'worth a novelty search before filing' —
        this system never claims to perform prior-art clearance."""
```

This module is the one place fabrication risk is highest (inventing "new" ideas), so its output is
explicitly and visibly labeled: every `ResearchIdea` in the final paper appears under a "Proposed
Contribution" heading with a novelty rationale and citations to the gap it addresses — never
presented as an already-validated result.

---

## 7. Module 6 — Methodology Generator

**Responsibility:** build a methodology section (and equations) derived from the actual proposed
idea and gap, not keyword-matched templates.

```python
class MethodologyGenerator:
    async def design_methodology(self, idea: ResearchIdea, domain_layer: XRayDomainContext) -> Methodology:
        """Experimental workflow, validation strategy, datasets to use/propose,
        evaluation protocol — LLM-drafted against the specific idea, reviewed against
        domain_layer constraints (e.g., radiation dose limits, detector physics)."""

    async def derive_equations(self, methodology: Methodology) -> list[Equation]:
        """Replaces today's keyword-triggered stock-equation lookup
        (research_pipeline.py: _build_equations_section, 1848-1863). Still grounded —
        equations come from a physics/ML formula library (attenuation law, SNR, DQE,
        loss functions, etc.) selected because the methodology actually uses them,
        with symbols matched to the methodology's own variable names, not generic."""
```

The equation *library* stays curated/verified physics and standard ML formulas (no LLM-invented
math) — what changes is that selection and symbol-binding are driven by what the methodology
actually describes, instead of a keyword scan of the topic string.

---

## 8. Module 7 — Paper Generator

This is today's Phase 2 (`build_phase2_research_document`), extended, not replaced:

- Section writing (`_llm_write_section`) now receives `CriticalAnalysis`, `MergedClaim`,
  `ResearchIdea`, `Methodology`, and `Equation` objects as structured context per section,
  instead of raw evidence snippets.
- `_validate_scientific_manuscript` gains checks for the new content types: no `ResearchIdea`
  presented without its "Proposed Contribution" label, no equation without a methodology
  back-reference, no gap claim without `evidence_source_ids`.
- **Figures:** replace Mermaid (`_build_figures_section`, 1820-1845) with server-rendered SVG.
  Reuse the pattern already established for other in-app diagrams — figure *content* (what to
  draw: architecture, pipeline, decision tree, taxonomy, timeline) comes from structured data
  (the plan, methodology, and knowledge graph), and a small SVG template layer renders it. No
  headless-browser/Mermaid-to-image conversion; direct SVG generation keeps output fully
  self-contained for DOCX/PDF embedding via `docgen.py`.
- **Tables:** extend `_build_tables_section` with the new matrix types the mission lists
  (Technology Readiness, Risk, Standards, Dataset Comparison, Algorithm Comparison, Performance,
  Complexity) — generated from the knowledge graph and methodology, not hand-templated.
- Section set grows to match `_SECTION_ORDER` (already defines all 27 target sections;
  Phase 2 currently emits ~8 of them) — Related Work, Scientific Background, Research Gap,
  Novel Contribution, Experimental Design, Limitations, Future Work, Acknowledgments,
  Appendices become real emitted sections, sourced from Modules 3–6's outputs.

---

## 9. Module 8 — Reviewer Engine

**Responsibility:** the self-improvement loop the mission asks for — today's validator rejects;
this iterates.

```python
class ReviewerEngine:
    async def simulate_review(self, draft: ManuscriptDraft) -> list[ReviewerReport]:
        """3 independent LLM passes with distinct reviewer personas/rubrics
        (methodology rigor / novelty & positioning / clarity & structure — mirroring
        real IEEE review criteria), each returning structured weaknesses with
        section references, not prose."""

    async def revise(self, draft: ManuscriptDraft, reports: list[ReviewerReport]) -> ManuscriptDraft:
        """Targeted re-generation of only the flagged sections via _llm_write_section,
        re-validated by _validate_scientific_manuscript each pass."""

    async def run_review_cycle(self, draft: ManuscriptDraft, max_rounds: int = 2) -> ManuscriptDraft:
        """Stops when reviewers report no blocking issues or max_rounds reached —
        capped explicitly for cost control (see §6/Module constraint 6)."""
```

`max_rounds` default 2 (not unbounded "iterate until publication-ready") — cost and latency need a
hard ceiling; the mission's "repeat until publication quality" is honored as "repeat up to a
budgeted number of rounds, then surface remaining reviewer notes to the user" rather than an
open-ended loop with no exit condition.

---

## 10. Module 9 — Continuous Learning Engine

**Responsibility:** cross-run memory — explicitly out of scope for the first implementation phase,
specified here so nothing downstream blocks it later.

- Learns from uploaded documents: already partially true via `InternalKBProvider` (Module 2) and
  the existing RAG pipeline — no new work needed for this part.
- Learns from *generated papers*: after a paper passes review (Module 8), extract its
  `ResearchIdea`/`MergedClaim` nodes into a **persistent** (cross-run) knowledge graph, separate
  from the per-run graph in Module 3, so future `discover_gaps`/`score_novelty` calls also check
  against papers this system has previously produced (avoids re-proposing the same "novel"
  contribution twice).
- Long-term research memory is a materialized view over `ResearchKnowledgeNode`/`Edge`, filterable
  by domain, not a separate ML model — no training/fine-tuning implied.

This module is a Phase-4+ concern (see roadmap) — it depends on Modules 3–5 existing and producing
real graph data first.

---

## 11. Module 10 — X-Ray Expert Knowledge Layer

**Responsibility:** cross-cutting domain context injected into Modules 1, 5, 6, and 7 — not a
pipeline stage of its own.

```python
class XRayDomainContext:
    """Loaded once, passed by reference into planner/innovation/methodology/writer.
    Backed by a curated internal knowledge base (existing RAG documents tagged by domain),
    not free LLM knowledge."""
    subdomains: list[str]   # radiation_physics | detector_technology | dual_energy | ct |
                              # backscatter | material_discrimination | atr | tip |
                              # cargo_inspection | airport_security | customs | border_protection
    constraint_rules: list[DomainConstraint]   # e.g. dose limits, regulatory standards (ANSI/IEC)
                                                 # used by Methodology Generator to sanity-check proposals
    terminology: dict[str, str]                 # canonical term mapping, reused from existing glossary work
```

Concretely: tag existing/ingested RAG documents and retrieved literature sources with a subdomain,
and let `provider_scope` (Module 1) and `constraint_rules` (Module 6) filter/validate against it.
This is largely configuration plus a domain-tag column on existing RAG tables, not new
infrastructure.

---

## 12. End-to-end data flow

```
User question
  -> Module 1  Research Planner            => ResearchPlan
  -> Module 2  Scientific Search Engine     => list[LiteratureSource]  (deduped, quality-ranked, DOI-verified)
  -> Module 3  Knowledge Integration Engine => ResearchKnowledgeGraph  (claims, contradictions, confidence)
  -> Module 4  Scientific Reasoning Engine  => CriticalAnalysis[], RankedGap[], Hypothesis[]
  -> Module 5  Innovation Engine            => ResearchIdea[] (each with NoveltyScore)
  -> Module 6  Methodology Generator        => Methodology, Equation[]
  -> Module 7  Paper Generator              => ManuscriptDraft (all IEEE sections, tables, SVG figures)
  -> Module 8  Reviewer Engine              => ManuscriptDraft (revised, up to max_rounds)
  -> Export (existing docgen.py)            => DOCX / PDF / HTML

Cross-cutting: Module 10 (domain context) feeds 1, 5, 6, 7.
               Module 9 (learning) reads from 3+8 after publication, feeds back into future 3-5 runs.
```

Every arrow above is a checkpoint written to `ResearchPipelineRun.artifacts` (already a JSON field
today) under a stage-named key — this preserves the existing resumability/caching behavior and
gives you an inspectable audit trail per run (you can see the plan, the raw sources, the graph, the
gaps, the ideas, and every reviewer round, not just the final text).

---

## 13. Cost & performance guard (new, addresses Module 7's dependency)

Module 7 (writing) already calls the LLM once per section. Modules 4, 5, 6, and 8 add roughly
5–15 more LLM calls per run (critical analysis per paper, gap ranking, idea generation, novelty
scoring, methodology drafting, up to 2 review rounds × 3 reviewer personas). This needs the same
treatment `cost_guard.py` gives translation today:

- New `research_cost_guard.py`, same shape as `cost_guard.py`: per-user hourly/daily/monthly $ caps,
  configurable via `Settings` (mirrors `disable_translation_rate_limit` etc.).
- Per-run cost estimate shown before execution (Module 1's plan can carry an `estimated_llm_calls`
  field), so a user isn't surprised by a 20-call pipeline run.
- SSE progress events (already exist for Phase 1/2) extend to report cost-so-far per stage.

---

## 14. Implementation roadmap

Phased so each phase ships something usable and testable — no big-bang rewrite, no "final paper
generation" broken mid-migration.

**Phase 1 — Provider layer + real verification (foundation for everything else)**
- `literature_providers/` package: `base.py`, registry, refactor existing Crossref/PubMed/arXiv/
  patent code into provider classes, add OpenAlex, Semantic Scholar, CORE, DOAJ.
- Add disabled-by-default IEEE/Springer/ScienceDirect provider stubs (interface implemented,
  `is_configured` gated on missing keys) — proves the abstraction before licensed access exists.
- Live DOI verification (§2.5). Drop DuckDuckGo scraping.
- Retire nothing user-facing yet — Phase 1 output still feeds today's Phase 1/2 pipeline unchanged.

**Phase 2 — Knowledge graph + reasoning (Modules 3–4)**
- New DB tables, fact-extraction restructuring, contradiction detection, graph-driven gap discovery.
- Still writes into the existing Phase-2 writer via the current evidence-summary path — reasoning
  output is *available* but not yet mandatory input to writing.

**Phase 3 — Innovation + methodology + full paper generator (Modules 5–7)**
- Real novelty scoring, methodology generation, SVG figures, full 27-section output, new table types.
- This is the phase where paper *content* visibly changes for the user.

**Phase 4 — Reviewer loop + cost guard (Module 8, §13)**
- Ships once Phase 3's writer is stable enough that automated critique is meaningful.

**Phase 5 — Domain layer formalization + continuous learning (Modules 9–10)**
- Domain tagging is incremental and can start anytime; continuous learning depends on Phase 3/4
  producing real graph + reviewed-paper data to learn from, so it's sequenced last.

Each phase is independently mergeable and the app stays functional throughout — Research Studio
keeps working with today's pipeline until each new module is ready to take over its slice.

---

## 15. Open questions for you before implementation starts

1. **Free-tier API keys**: Semantic Scholar and CORE work unauthenticated but at low rate limits —
   getting free keys for both (a few minutes each) meaningfully improves Phase 1 throughput. Want
   me to note where to register, or proceed unauthenticated for now?
2. **Cost ceiling**: what should the default per-run $ cap be for the full Phase 3+ pipeline (a
   run may cost noticeably more than today's single-pass generation once reasoning/innovation/
   review are added)?
3. **Phase sequencing**: confirm Phase 1 (providers) first is right, or do you want the knowledge
   graph (Phase 2) prioritized even though it'll initially run on a smaller source set?

Once you confirm/redline this doc, I'll start Phase 1.
