"""Phase 2B.7 — Expert Reasoning Engine.

A read-only context-assembly layer over the existing Knowledge Graph — NOT a
new LLM pipeline. The single existing provider.stream_chat(history,
system_prompt=...) call in api.routes.chat.py stays the only LLM
invocation; this module only changes what goes into `system_prompt`,
turning a flat fact list into a structured bundle (related entities, causal
edges, open conflicts, trust scores) plus explicit rules for reasoning over
it. No writes anywhere — every lookup here goes through existing public
reads (crud.list_knowledge_evidence, the new
crud.list_knowledge_edges_for_node, conflict_resolver.get_conflict_trust_snapshot).

Deliberately independent of api.services.knowledge_router (Phase 2B.6):
this module is never imported by it and never imports it — the two layers
compose in api.routes.chat.py without either one knowing about the other.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from api.db import crud
from api.db.models import KnowledgeNode
from api.services.retrieval_utils import tokenize, keyword_score

# ── Intent classification — deterministic, no LLM call ──────────────────────

COMPARE = "COMPARE"
CAUSAL = "CAUSAL"
TRADEOFF = "TRADEOFF"
EVIDENCE = "EVIDENCE"
SYNTHESIS = "SYNTHESIS"

# Checked in this order: a "why is X better than Y" question is fundamentally
# a comparison needing both entities' facts, so COMPARE/TRADEOFF phrasing is
# checked before the generic "why" (CAUSAL) pattern would otherwise claim it.
_COMPARE_RE = re.compile(
    r"\bcompare\b|\bcompared\s+to\b|\bversus\b|\bvs\.?\b|\bbetter\s+than\b|"
    r"\bwhich\s+(?:\w+\s+){0,3}(?:is\s+)?(?:most\s+promising|better|best)\b|"
    r"قارن|مقارنة|أيهما\s+أفضل",
    re.IGNORECASE,
)
_TRADEOFF_RE = re.compile(
    r"\badvantages?\b|\blimitations?\b|\bpros\s+and\s+cons\b|\bbenefits?\s+and\s+drawbacks?\b|"
    r"\btrade-?offs?\b|\bstrengths?\s+and\s+weaknesses\b|"
    r"مزايا|عيوب|إيجابيات|سلبيات",
    re.IGNORECASE,
)
_CAUSAL_RE = re.compile(
    r"^\s*why\b|\bwhy\s+(?:is|are|does|do|did)\b|\bwhat\s+causes?\b|\broot\s+cause\b|"
    r"\bwhat\s+(?:is|are)\s+the\s+cause\b|\bfailure\s+mode\b|"
    r"لماذا|ما\s+سبب|السبب\s+الجذري",
    re.IGNORECASE,
)
_EVIDENCE_RE = re.compile(
    r"\bwhat\s+evidence\b|\bhow\s+confident\b|\bwhat\s+supports?\b|\bis\s+this\s+proven\b|"
    r"\bhow\s+(?:sure|certain)\b|"
    r"ما\s+الدليل|ما\s+مدى\s+ثقتك",
    re.IGNORECASE,
)
_SYNTHESIS_RE = re.compile(
    r"\bsummari[sz]e\b.*\b(?:papers?|research|studies|sources)\b|"
    r"\b(?:papers?|research|studies)\b.*\bsummari[sz]e\b|"
    r"لخص.*(?:الأبحاث|الأوراق|الدراسات)",
    re.IGNORECASE,
)


def classify_reasoning_intent(message: str) -> str | None:
    """Deterministic keyword classification — same philosophy as
    knowledge_router.classify_knowledge_gap: no LLM call, so a message that
    matches nothing (the common case) costs one set of regex checks and
    changes nothing downstream."""
    if not message:
        return None
    if _COMPARE_RE.search(message):
        return COMPARE
    if _TRADEOFF_RE.search(message):
        return TRADEOFF
    if _CAUSAL_RE.search(message):
        return CAUSAL
    if _EVIDENCE_RE.search(message):
        return EVIDENCE
    if _SYNTHESIS_RE.search(message):
        return SYNTHESIS
    return None


# ── Entity resolution ────────────────────────────────────────────────────────

_COMPARE_SPLIT_RE = re.compile(
    r"\bversus\b|\bvs\.?\b|\bcompared\s+to\b|\bcompare\b|\band\b|\bor\b|"
    r"مقابل|\bو\b",
    re.IGNORECASE,
)


def split_compare_entities(message: str) -> list[str]:
    """Best-effort split of a comparison question into candidate entity
    phrases — e.g. "Compare LINAC and Betatron" -> ["LINAC", "Betatron"].
    A message with no clean split (e.g. "Which detector technology is most
    promising?") yields a single phrase, which callers treat as a
    multi-candidate lookup instead of an A-vs-B comparison — a disclosed
    degrade path, not a failure."""
    parts = [p.strip(" ?.!") for p in _COMPARE_SPLIT_RE.split(message) if p.strip(" ?.!")]
    # Drop tiny leading fragments like "which" / "is" left over from a
    # leading clause — keep only fragments with at least one real token.
    parts = [p for p in parts if tokenize(p)]
    return parts[:2] if len(parts) >= 2 else (parts[:1] if parts else [])


def find_matching_nodes(db: Session, phrase: str, top_k: int = 3, statuses: tuple[str, ...] = ("current", "experimental")) -> list[KnowledgeNode]:
    """Same keyword-overlap technique graph_query.get_relevant_facts() uses,
    returning raw nodes (not a dict projection) so edges/evidence can be
    walked. Includes "experimental" nodes (hypotheses) alongside "current"
    ones — a comparison/causal question should surface a hypothesis too,
    clearly labeled as such by format_reasoning_context(), not hide it."""
    query_tokens = tokenize(phrase)
    if not query_tokens:
        return []
    nodes = db.query(KnowledgeNode).filter(KnowledgeNode.status.in_(statuses)).all()
    scored: list[tuple[float, KnowledgeNode]] = []
    for node in nodes:
        text = f"{node.label} {node.description or ''}"
        score = keyword_score(query_tokens, text)
        if score > 0:
            scored.append((score, node))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [node for _, node in scored[:top_k]]


# ── Context assembly ─────────────────────────────────────────────────────────

@dataclass
class ReasoningContext:
    intent: str
    entities: list[dict] = field(default_factory=list)  # [{"phrase", "nodes": [...], "edges": [...], "conflicts": [...]}]


def _conflicts_for_node(db: Session, node: KnowledgeNode) -> list:
    return crud.list_knowledge_conflicts(db, status="Open", subject_node_id=node.id)


def _entity_bundle(db: Session, phrase: str, nodes: list[KnowledgeNode]) -> dict:
    edges: list = []
    conflicts: list = []
    for node in nodes:
        edges.extend(crud.list_knowledge_edges_for_node(db, node.id))
        conflicts.extend(_conflicts_for_node(db, node))
    return {"phrase": phrase, "nodes": nodes, "edges": edges, "conflicts": conflicts}


def build_reasoning_context(db: Session, message: str, intent: str) -> ReasoningContext | None:
    """Dispatches per intent. Returns None when nothing in the graph
    matches — the LLM then answers exactly as it does today, no
    hallucinated context ever injected."""
    if intent == COMPARE:
        phrases = split_compare_entities(message)
        if not phrases:
            phrases = [message]
        entities = []
        for phrase in phrases:
            nodes = find_matching_nodes(db, phrase, top_k=3 if len(phrases) == 1 else 2)
            if nodes:
                entities.append(_entity_bundle(db, phrase, nodes))
        if not entities:
            return None
        return ReasoningContext(intent=intent, entities=entities)

    if intent == SYNTHESIS:
        nodes = [n for n in find_matching_nodes(db, message, top_k=5) if n.node_type == "Paper"]
        if not nodes:
            return None
        return ReasoningContext(intent=intent, entities=[_entity_bundle(db, message, nodes)])

    # CAUSAL / TRADEOFF / EVIDENCE — single subject.
    nodes = find_matching_nodes(db, message, top_k=2)
    if not nodes:
        return None
    return ReasoningContext(intent=intent, entities=[_entity_bundle(db, message, nodes)])


# ── Rendering ────────────────────────────────────────────────────────────────

REASONING_RULES = (
    "You have been given a structured bundle of facts, relationships, and evidence from the "
    "platform's Knowledge Graph, assembled specifically for this question. Reason over it like a "
    "senior X-ray engineer:\n"
    "- Never invent a fact that is not present in the bundle below or in the uploaded-document "
    "context — draw on your own general expertise only to explain and connect the given facts, "
    "not to fabricate new ones about this specific equipment/technology/source.\n"
    "- Explicitly separate, in your answer: **known facts** (well-evidenced), **inference** (your "
    "reasoning connecting facts), **hypothesis** (marked experimental/unproven in the bundle), and "
    "**live-research findings** (freshly learned this turn, if any appear below).\n"
    "- Cite confidence and, when two sources disagree, cite their trust scores rather than picking "
    "a side silently.\n"
    "- If the evidence for something is thin or conflicting, say so plainly and recommend further "
    "research instead of guessing."
)


def _confidence_band(node: KnowledgeNode) -> str:
    if node.status == "experimental":
        return "HYPOTHESES"
    if node.status in ("deprecated", "historical"):
        return "SUPERSEDED"
    if node.confidence >= 0.7 and node.evidence_count >= 2:
        return "KNOWN FACTS"
    return "TENTATIVE FACTS"


def _format_node(node: KnowledgeNode) -> str:
    return (
        f"- [{node.node_type}] {node.label}"
        + (f": {node.description}" if node.description else "")
        + f" (confidence {round(node.confidence * 100)}%, {node.evidence_count} evidence source(s)"
        + (f", {node.status}" if node.status != "current" else "")
        + ")"
    )


def _format_edges(edges: list, node_labels: dict[str, str]) -> list[str]:
    lines = []
    for edge in edges:
        frm = node_labels.get(edge.from_node_id, edge.from_node_id)
        to = node_labels.get(edge.to_node_id, edge.to_node_id)
        lines.append(f"- {frm} --[{edge.relationship}]--> {to}")
    return lines


def format_reasoning_context(db: Session, context: ReasoningContext) -> str:
    """Renders the bundle into labeled sections the model can cite directly.
    Never includes a fact not present in `context` — this function only
    formats, it never fetches or infers anything new (the one exception —
    resolving each conflict's current trust snapshot — reuses the caller's
    own `db` session rather than opening a new one)."""
    from api.services.knowledge_governance.conflict_resolver import get_conflict_trust_snapshot

    bands: dict[str, list[str]] = {"KNOWN FACTS": [], "TENTATIVE FACTS": [], "HYPOTHESES": [], "SUPERSEDED": []}
    # Keyed by id — a shared edge/conflict/node touching two compared
    # entities is discovered independently from each entity's own query and
    # must not be rendered twice.
    edges_by_id: dict[str, object] = {}
    conflicts_by_id: dict[str, object] = {}
    node_labels: dict[str, str] = {}
    seen_node_ids: set[str] = set()

    for entity in context.entities:
        for node in entity["nodes"]:
            node_labels[node.id] = node.label
            if node.id not in seen_node_ids:
                seen_node_ids.add(node.id)
                bands[_confidence_band(node)].append(_format_node(node))
        for edge in entity["edges"]:
            edges_by_id[edge.id] = edge
        for conflict in entity["conflicts"]:
            conflicts_by_id[conflict.id] = conflict

    all_edges = list(edges_by_id.values())
    all_conflicts = list(conflicts_by_id.values())

    # An edge's far endpoint (e.g. a CAUSAL effect node reached only via the
    # subject's outgoing edge) is never itself in `entity["nodes"]`, so its
    # label wouldn't otherwise be known — resolve those explicitly so
    # RELATIONSHIPS never falls back to a raw node id.
    unresolved_ids = {
        node_id for edge in all_edges for node_id in (edge.from_node_id, edge.to_node_id)
        if node_id not in node_labels
    }
    for node_id in unresolved_ids:
        other = crud.get_knowledge_node(db, node_id)
        if other:
            node_labels[node_id] = other.label

    sections: list[str] = [f"REASONING CONTEXT (intent: {context.intent})"]
    for label in ("KNOWN FACTS", "TENTATIVE FACTS", "HYPOTHESES", "SUPERSEDED"):
        if bands[label]:
            sections.append(f"\n{label}:\n" + "\n".join(bands[label]))

    edge_lines = _format_edges(all_edges, node_labels)
    if edge_lines:
        sections.append("\nRELATIONSHIPS:\n" + "\n".join(edge_lines))

    if all_conflicts:
        conflict_lines = []
        for conflict in all_conflicts:
            snapshot = get_conflict_trust_snapshot(db, conflict)
            trust_a = snapshot["source_a"]
            trust_b = snapshot["source_b"]
            conflict_lines.append(
                f"- ({conflict.conflict_type}, {conflict.severity}): \"{conflict.claim_a}\""
                + (f" (trust {round(trust_a['effective_trust_score'])}%)" if trust_a else "")
                + f" vs. \"{conflict.claim_b}\""
                + (f" (trust {round(trust_b['effective_trust_score'])}%)" if trust_b else "")
            )
        sections.append("\nOPEN CONFLICTS:\n" + "\n".join(conflict_lines))

    return "\n".join(sections)
