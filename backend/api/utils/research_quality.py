"""
Publication-quality checks for Research Studio outputs.

The scorer is intentionally deterministic: it measures structural completeness,
scientific apparatus, and reference presence so the export layer can reject
generic report-like drafts before they are packaged as DOCX/PDF/HTML.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any
import re


@dataclass
class PublicationQualityResult:
    score: int
    issues: list[str]
    stats: dict[str, int]


class PublicationQualityError(ValueError):
    def __init__(self, result: PublicationQualityResult):
        self.result = result
        super().__init__(f"Publication quality score {result.score} is below the required threshold")


_SECTION_PATTERNS: dict[str, re.Pattern[str]] = {
    "abstract": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?abstract\b"),
    "introduction": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?(?:introduction|background)\b"),
    "literature_review": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?(?:literature review|related work|state of the art)\b"),
    "novel_contributions": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?(?:novel contributions|contributions|main contributions)\b"),
    "methodology": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?(?:methodology|materials and methods|methods)\b"),
    "mathematical_models": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?(?:mathematical models|mathematical modeling|theory and background)\b"),
    "experimental_setup": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?(?:experimental setup|experimental design|materials and methods|experiment setup)\b"),
    "results": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?results\b"),
    "discussion": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?discussion\b"),
    "limitations": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?limitations?\b"),
    "future_work": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?(?:future work|future directions)\b"),
    "conclusion": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?conclusion(?:s)?\b"),
    "references": re.compile(r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?references?\b"),
}

# Matches a "Figure N" caption whether it's a standalone line or the alt
# text of a rendered-image markdown line (![Figure N. Caption](path)) — real
# figures are now emitted as the latter (see figure_renderer.py), not a
# separate caption line, so the optional "![" prefix is required here too.
_FIGURE_RE = re.compile(r"(?im)^(?:!\[)?(?:figure|fig\.)\s*\d+\b")
_TABLE_RE = re.compile(r"(?im)^table\s*\d+\b")
_EQUATION_RE = re.compile(r"(?im)^(?:\$\$|\\begin\{equation\}|\\\[)")
_CITATION_RE = re.compile(r"\[(\d{1,3})\]")
_REF_ENTRY_RE = re.compile(r"(?im)^\[(\d{1,3})\]\s+\S")


def _references_block(content: str) -> str:
    match = _SECTION_PATTERNS["references"].search(content)
    if not match:
        return ""
    return content[match.end():].strip()


def _count_section_matches(content: str) -> dict[str, bool]:
    return {name: bool(pattern.search(content)) for name, pattern in _SECTION_PATTERNS.items()}


def score_publication_quality(content: str, *, mode: str = "") -> PublicationQualityResult:
    text = content or ""
    sections = _count_section_matches(text)
    issues: list[str] = []
    score = 100

    required_sections = [
        ("abstract", 6),
        ("introduction", 7),
        ("literature_review", 7),
        ("novel_contributions", 10),
        ("methodology", 8),
        ("mathematical_models", 8),
        ("experimental_setup", 8),
        ("results", 8),
        ("discussion", 7),
        ("limitations", 5),
        ("future_work", 5),
        ("conclusion", 6),
        ("references", 10),
    ]
    for name, weight in required_sections:
        if not sections[name]:
            score -= weight
            issues.append(f"Missing section: {name.replace('_', ' ').title()}")

    if not re.search(r"(?i)Mohamed\s+Noaman", text):
        score -= 4
        issues.append("Author name Mohamed Noaman is missing")

    if not re.search(r"(?i)(affiliation|x-ray academy|research intelligence platform)", text):
        score -= 4
        issues.append("Affiliation block is missing")

    if not re.search(r"(?i)^#{1,3}\s*keywords\b", text, flags=re.MULTILINE):
        score -= 3
        issues.append("Keywords section is missing")

    if len(_CITATION_RE.findall(text)) < 8:
        score -= 5
        issues.append("Too few inline citations")

    figure_count = len(_FIGURE_RE.findall(text))
    table_count = len(_TABLE_RE.findall(text))
    equation_count = len(_EQUATION_RE.findall(text))
    reference_entries = len(_REF_ENTRY_RE.findall(_references_block(text)))
    doi_or_url_hits = len(re.findall(r"(?i)doi\.org|https?://", _references_block(text)))

    if figure_count < 2:
        score -= 4
        issues.append("Fewer than two figure captions were found")
    if table_count < 2:
        score -= 4
        issues.append("Fewer than two table captions were found")
    if equation_count < 2:
        score -= 4
        issues.append("Fewer than two displayed equations were found")
    if reference_entries < 8:
        score -= 8
        issues.append("References section is too short")
    if doi_or_url_hits < 4:
        score -= 5
        issues.append("References section lacks enough verifiable DOI/URL evidence")

    if mode.startswith("paper_") and not re.search(r"(?i)system architecture|experimental setup|performance comparison", text):
        score -= 3
        issues.append("Scientific figure or architecture language is missing")

    score = max(0, min(100, score))
    stats = {
        "figures": figure_count,
        "tables": table_count,
        "equations": equation_count,
        "citations": len(_CITATION_RE.findall(text)),
        "reference_entries": reference_entries,
        "doi_or_url_hits": doi_or_url_hits,
    }
    return PublicationQualityResult(score=score, issues=issues, stats=stats)


def assert_publication_quality(content: str, *, mode: str = "", threshold: int = 95) -> PublicationQualityResult:
    result = score_publication_quality(content, mode=mode)
    if result.score < threshold:
        raise PublicationQualityError(result)
    return result


# ── Publication-readiness gate ───────────────────────────────────────────────
#
# The 0-100 score above stays informational-only (an arbitrary aggregate bar
# is easy to miss for reasons that don't matter). Export should instead block
# on a short list of *named, specific* defects — the acceptance tests below.

_SECTION_PATTERNS["research_gap"] = re.compile(
    r"(?im)^#{1,3}\s*(?:\d+\.\s*|[IVX]+\.\s*)?(?:research gap|gap analysis)\b"
)

# Modes where a full literature base is the actual deliverable, and a thin
# reference list means the paper failed at its job.
_LITERATURE_HEAVY_MODES = {
    "paper_ieee", "paper_elsevier", "literature_review",
    "technical_report", "patent_analysis", "competitor_landscape",
}
_MIN_REFERENCES_LITERATURE_HEAVY = 20
_MIN_REFERENCES_DEFAULT = 8
_MIN_PEER_REVIEWED_RATIO = 0.6
_MIN_TITLE_ALIGNMENT = 0.9

_PLACEHOLDER_RE = re.compile(r"\[(?:SRC|KB)-\d+\]")
# Only the mermaid language tag is a defect — a generic ``` code fence is
# rendered cleanly (monospace paragraph) by every export path and is not
# itself a problem.
_MERMAID_LEAK_RE = re.compile(r"```\s*mermaid\b", re.IGNORECASE)
_ALIGNMENT_STOPWORDS = {
    "the", "and", "for", "with", "from", "into", "that", "this", "of", "in", "on",
    "a", "an", "to", "by", "is", "are", "at", "as",
    "its", "his", "her", "our", "your", "them", "they", "these", "those", "about",
}
_FABRICATED_RESULT_PATTERNS = [
    re.compile(r"(?i)\bour (?:experiments?|results?|system|method) (?:show|shows|demonstrate|demonstrates|achieved|achieves)\b"),
    re.compile(r"(?i)\bwe (?:achieved|obtained|measured|recorded)\b[^.]{0,40}\d+(?:\.\d+)?\s*%"),
    re.compile(r"(?i)\bexperimental results (?:show|demonstrate|confirm)\b"),
]
_HEDGE_TERMS_RE = re.compile(r"(?i)\bpropos(?:e|ed|al)|simulat(?:e|ed|ion)|would be|future work|hypothesiz")

# Organizational/filler words common in generated paper titles that carry no
# topical meaning of their own ("... Systems Implementations", "... Approach
# Study") — a well-written body legitimately never repeats these verbatim,
# so counting them against alignment would punish good papers, not just
# genuinely mismatched ones.
_TITLE_GENERIC_WORDS = {
    "system", "systems", "implementation", "implementations", "application",
    "applications", "approach", "approaches", "study", "analysis", "review",
    "framework", "method", "methods", "technique", "techniques", "overview",
    "based", "using", "toward", "towards", "impact", "effect", "effects",
    "role", "roles",
}

# Small domain synonym map so alignment isn't defeated by a paper preferring
# a near-synonym over the title's exact word (e.g. "screening"/"detection"
# instead of "scanning") — same spirit as generate_search_keywords' synonym_map.
_ALIGNMENT_SYNONYMS: dict[str, set[str]] = {
    "scanning": {"screening", "scanner", "imaging", "inspection", "detection", "baggage"},
    "scanner": {"screening", "scanning", "imaging", "inspection", "detection"},
    "ray": {"ray", "xray", "radiographic", "radiography"},
    "security": {"security", "screening", "threat", "inspection"},
    # "AI" as a title word is, in real academic prose, expressed through its
    # constituent techniques far more often than the literal phrase
    # "artificial intelligence" — a paper about AI overwhelmingly says "deep
    # learning", "neural network", "CNN", "automated", etc. instead.
    "ai": {
        "ai", "artificial", "intelligence", "deep", "learning", "neural",
        "network", "networks", "cnn", "convolutional", "machine", "algorithm",
        "algorithms", "automated", "automatic", "transformer", "transformers",
    },
    # X-ray source/generator/detector physics — a paper about "X-ray sources"
    # overwhelmingly discusses tubes, generators, anodes/cathodes, and
    # spectra rather than repeating the word "sources" itself; without this,
    # a genuinely on-topic source-physics paper still fails alignment purely
    # because the scorer only checked for the literal word.
    "source": {"source", "sources", "generator", "generators", "tube", "tubes", "anode", "cathode", "spectrum", "voltage"},
    "sources": {"source", "sources", "generator", "generators", "tube", "tubes", "anode", "cathode", "spectrum", "voltage"},
    "detector": {"detector", "detectors", "photon", "photons", "scintillator", "sensor", "sensors", "physics", "radiation"},
    "detectors": {"detector", "detectors", "photon", "photons", "scintillator", "sensor", "sensors", "physics", "radiation"},
}


@dataclass
class PublicationReadinessReport:
    reference_count: int
    verified_doi_count: int
    peer_reviewed_ratio: float
    citation_coverage: float
    unsupported_claim_count: int
    title_content_alignment: float
    novelty_score: float | None
    reproducibility_score: float | None
    figure_rendering_status: str
    critical_issues: list[str]
    polish_score: int
    polish_issues: list[str]

    @property
    def is_publication_ready(self) -> bool:
        return not self.critical_issues


class PublicationReadinessError(ValueError):
    def __init__(self, report: PublicationReadinessReport):
        self.report = report
        super().__init__(
            "Publication readiness check failed: " + "; ".join(report.critical_issues)
        )


def _content_token_list(text: str, min_len: int = 2) -> list[str]:
    return [
        t for t in re.findall(r"[a-z0-9]+", (text or "").lower())
        if len(t) >= min_len and t not in _ALIGNMENT_STOPWORDS
    ]


def title_alignment_score(title: str, corpus_text: str) -> float:
    """Fraction of the title's meaningful, distinctive words that show up
    (directly or via a close domain synonym) among the given corpus's
    dominant (most frequent) vocabulary.

    This is a deterministic proxy for semantic alignment, not true topic
    modeling — but it directly catches the failure mode that motivated this
    check: a title about one subject backed by evidence/content that drifted
    onto an unrelated narrow subject. `corpus_text` can be a manuscript body
    (post-writing check) or a pool of candidate-evidence titles/abstracts
    (pre-writing check, used to decide whether retrieval needs another pass
    before any LLM writing is attempted). Generic organizational title words
    are excluded so well-aligned text that simply phrases things differently
    isn't penalized.
    """
    from collections import Counter

    title_tokens = {t for t in _content_token_list(title) if t not in _TITLE_GENERIC_WORDS}
    if not title_tokens:
        return 1.0

    counts = Counter(_content_token_list(corpus_text))
    if not counts:
        return 0.0
    dominant = {w for w, _ in counts.most_common(60)}

    matched = 0
    for t in title_tokens:
        candidates = _ALIGNMENT_SYNONYMS.get(t, {t})
        if candidates & dominant:
            matched += 1
    return round(matched / len(title_tokens), 3)


def _title_content_alignment(content: str) -> float:
    """Manuscript-body alignment check — see `title_alignment_score` for the
    underlying algorithm. Extracts the title and prose body (tables excluded)
    from a finished manuscript automatically.
    """
    from api.utils.docgen import extract_paper_title

    title = extract_paper_title(content, fallback="")
    ref_match = _SECTION_PATTERNS["references"].search(content)
    body = content[: ref_match.start()] if ref_match else content
    # Exclude table rows (Literature/Comparison/Gap matrices repeat "academic",
    # citation keys, etc. dozens of times — that's structured metadata, not
    # prose, and would swamp the actual narrative vocabulary this check needs).
    prose_lines = [ln for ln in body.splitlines() if not ln.strip().startswith("|")]
    return title_alignment_score(title, "\n".join(prose_lines))


def _reference_stats(reference_meta: list[dict] | None) -> dict[str, Any]:
    academic = [r for r in (reference_meta or []) if r.get("source_type") == "academic"]
    total = len(academic)
    verified_doi = sum(1 for r in academic if r.get("doi_verified"))
    peer_reviewed = sum(1 for r in academic if r.get("is_peer_reviewed"))
    ratio = round(peer_reviewed / total, 3) if total else 0.0
    return {"reference_count": total, "verified_doi_count": verified_doi, "peer_reviewed_ratio": ratio}


def _figure_rendering_status(content: str) -> tuple[str, int]:
    import os as _os
    captions = _FIGURE_RE.findall(content)
    image_paths = re.findall(r"!\[[^\]]*\]\(([^)]+)\)", content)
    if not captions:
        return "no_figures", 0
    resolved = sum(1 for p in image_paths if _os.path.isfile(p.strip()))
    if resolved == 0:
        return "missing_images", 0
    if resolved < len(captions):
        return "partial", resolved
    return "ok", resolved


def _citation_coverage_and_unsupported(content: str) -> tuple[float, int]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", content) if p.strip()]
    substantive = [
        p for p in paragraphs
        if not (
            p.startswith("#") or p.startswith("|") or p.startswith("```")
            or p.startswith("![") or p.startswith("Figure")
        )
    ]
    if not substantive:
        return 1.0, 0
    cited = sum(1 for p in substantive if _CITATION_RE.search(p))
    unsupported = len(substantive) - cited
    return round(cited / len(substantive), 3), unsupported


def generate_publication_readiness_report(
    content: str,
    *,
    mode: str = "",
    reference_meta: list[dict] | None = None,
    has_real_experiment: bool = False,
) -> PublicationReadinessReport:
    text = content or ""
    critical: list[str] = []

    ref_stats = _reference_stats(reference_meta)
    min_refs = _MIN_REFERENCES_LITERATURE_HEAVY if mode in _LITERATURE_HEAVY_MODES else _MIN_REFERENCES_DEFAULT
    if reference_meta is not None and ref_stats["reference_count"] < min_refs:
        critical.append(
            f"Only {ref_stats['reference_count']} verified academic references were retrieved; "
            f"at least {min_refs} are required for this manuscript type."
        )
    if reference_meta is not None and ref_stats["reference_count"] > 0 and ref_stats["peer_reviewed_ratio"] < _MIN_PEER_REVIEWED_RATIO:
        critical.append(
            f"Only {ref_stats['peer_reviewed_ratio']*100:.0f}% of references are peer-reviewed; "
            f"at least {_MIN_PEER_REVIEWED_RATIO*100:.0f}% is required."
        )

    alignment = _title_content_alignment(text)
    if alignment < _MIN_TITLE_ALIGNMENT:
        critical.append(
            f"Title-content alignment is {alignment*100:.0f}%, below the required "
            f"{_MIN_TITLE_ALIGNMENT*100:.0f}% — the body's dominant vocabulary diverges from the title. "
            "Broaden the retrieved evidence base or retitle the manuscript so title and content agree."
        )

    if _PLACEHOLDER_RE.search(text):
        placeholders = sorted(set(_PLACEHOLDER_RE.findall(text)))
        critical.append(f"Unresolved citation placeholder(s) found in the manuscript: {placeholders}")

    if _MERMAID_LEAK_RE.search(text):
        critical.append("Raw Mermaid/code-fence markup survived into the final manuscript.")

    fig_status, fig_count = _figure_rendering_status(text)
    if fig_status in {"missing_images", "partial"}:
        critical.append(f"One or more captioned figures have no resolvable rendered image (status: {fig_status}).")

    citation_coverage, unsupported = _citation_coverage_and_unsupported(text)
    if unsupported > 0:
        critical.append(f"{unsupported} substantive paragraph(s) make a claim without a citation.")

    if not has_real_experiment:
        for pattern in _FABRICATED_RESULT_PATTERNS:
            m = pattern.search(text)
            if m:
                window = text[max(0, m.start() - 60): m.end() + 60]
                if not _HEDGE_TERMS_RE.search(window):
                    critical.append(
                        "Declarative experimental-result language found without a real experiment "
                        "having been run — label this as a proposed/simulated framework instead."
                    )
                    break

    polish = score_publication_quality(text, mode=mode)

    return PublicationReadinessReport(
        reference_count=ref_stats["reference_count"],
        verified_doi_count=ref_stats["verified_doi_count"],
        peer_reviewed_ratio=ref_stats["peer_reviewed_ratio"],
        citation_coverage=citation_coverage,
        unsupported_claim_count=unsupported,
        title_content_alignment=alignment,
        novelty_score=None,
        reproducibility_score=None,
        figure_rendering_status=fig_status,
        critical_issues=critical,
        polish_score=polish.score,
        polish_issues=polish.issues,
    )


def assert_publication_readiness(
    content: str,
    *,
    mode: str = "",
    reference_meta: list[dict] | None = None,
    has_real_experiment: bool = False,
) -> PublicationReadinessReport:
    report = generate_publication_readiness_report(
        content, mode=mode, reference_meta=reference_meta, has_real_experiment=has_real_experiment,
    )
    if report.critical_issues:
        raise PublicationReadinessError(report)
    return report