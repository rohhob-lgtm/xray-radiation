"""X-Ray Academy AI — lightweight, READ-ONLY Capability Registry.

This module is descriptive metadata only. It does NOT route, orchestrate,
execute, or own any business logic — the existing routers and services remain
solely responsible for execution. Its single job is to answer one question
honestly: *"Which capabilities does this platform actually have right now, and
which existing service is responsible for each?"*

Every capability listed here is mapped to a verified, existing code path
(``service``) and, where a real runtime kill-switch exists, to the exact
``api.config.settings`` flag that gates it (``enabled_flag``). Capabilities
without a flag are always-on structural capabilities of the platform.

Two consumers read this registry:

  * ``api.routes.capabilities`` — exposes it read-only over HTTP so the UI and
    any client can see the true capability surface.
  * ``api.services.xray_knowledge.build_platform_identity_prompt`` — renders a
    compact "currently-enabled capabilities" block into the AI Chat identity
    prompt, so AI Chat's self-description stays truthful and tracks the flags
    (a disabled capability disappears from what Chat claims it can do).

The platform registry — NOT the foundation model's self-description — is the
source of truth for what X-Ray Academy AI can do.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from api.config import Settings, settings as _default_settings

# Cost / access classification.
FREE = "free"          # bounded external calls that use only free/public tiers
LOCAL = "local"        # runs entirely on local knowledge/compute, no external cost
PAID = "paid"          # may incur paid API cost (respects cost settings / Free Mode)
EXTERNAL = "external"  # third-party connector, per-user connection required

# Execution mode.
SYNC = "sync"
BACKGROUND = "background"


@dataclass(frozen=True)
class Capability:
    """One descriptive record for a real, existing platform capability."""

    key: str
    name: str
    category: str
    #: Dotted path to the existing service/router responsible for execution.
    service: str
    cost: str
    execution: str
    description: str
    #: Name of the ``api.config.settings`` bool that gates this capability at
    #: runtime, or ``None`` for always-on structural capabilities.
    enabled_flag: Optional[str] = None
    #: Human-readable availability caveat (e.g. per-user connection required).
    availability_note: Optional[str] = None

    def is_enabled(self, settings: Settings) -> bool:
        """Resolved runtime state. Structural capabilities (no flag) are always
        enabled; flagged capabilities follow their config kill-switch."""
        if self.enabled_flag is None:
            return True
        return bool(getattr(settings, self.enabled_flag, False))


# ──────────────────────────────────────────────────────────────────────────
# The registry. Ordered roughly UNDERSTAND → SEARCH → VERIFY → LEARN → REASON
# → SYNTHESIZE → EXPLAIN → CREATE → PRESERVE, mirroring the platform mission.
# Each entry is verified against an existing module in this codebase.
# ──────────────────────────────────────────────────────────────────────────
_REGISTRY: tuple[Capability, ...] = (
    Capability(
        key="knowledge_retrieval",
        name="Knowledge Retrieval (RAG)",
        category="retrieval",
        service="api.services.rag_service",
        cost=LOCAL,
        execution=SYNC,
        description="Semantic retrieval over the platform + uploaded knowledge base.",
    ),
    Capability(
        key="knowledge_graph",
        name="Knowledge Graph",
        category="retrieval",
        service="api.services.research_brain.graph_query",
        cost=LOCAL,
        execution=SYNC,
        description="Versioned entity/relationship facts queried alongside RAG.",
    ),
    Capability(
        key="research_memory",
        name="Research Memory",
        category="retrieval",
        service="api.services.research_brain.research_memory",
        cost=LOCAL,
        execution=SYNC,
        description="Cross-mission topic memory and knowledge-freshness tracking.",
    ),
    Capability(
        key="internet_research",
        name="Internet Research (Research Agent)",
        category="research",
        service="api.services.research_agent.quick_research",
        cost=FREE,
        execution=BACKGROUND,
        description="Bounded live web research pass through the existing Research Agent.",
    ),
    Capability(
        key="auto_live_research",
        name="Automatic Live-Research Fallback",
        category="research",
        service="api.services.knowledge_router",
        cost=FREE,
        execution=BACKGROUND,
        description="AI Chat's automatic fallback to a bounded research pass on low-confidence, research-worthy questions.",
        enabled_flag="knowledge_router_enabled",
    ),
    Capability(
        key="deep_research",
        name="Deep Research / LEARN_TOPIC",
        category="research",
        service="api.services.research_agent_chat_intent",
        cost=FREE,
        execution=BACKGROUND,
        description="Broad-coverage deep-research missions (manufacturers, papers, patents, standards) launched by explicit learning requests.",
    ),
    Capability(
        key="internet_image_retrieval",
        name="Internet Image Retrieval",
        category="research",
        service="api.services.research_agent.image_discovery",
        cost=FREE,
        execution=SYNC,
        description="Bounded reference-image retrieval fallback when the Knowledge Base has no matching image.",
        enabled_flag="image_retrieval_enabled",
    ),
    Capability(
        key="knowledge_images",
        name="Knowledge Images / Gallery",
        category="retrieval",
        service="api.services.gallery_service",
        cost=LOCAL,
        execution=SYNC,
        description="Reference-image search over the platform's own knowledge base and gallery.",
    ),
    Capability(
        key="source_trust",
        name="Source Trust",
        category="verification",
        service="api.services.research_agent.quality_scorer",
        cost=LOCAL,
        execution=SYNC,
        description="Dynamic per-source trust/quality scoring of discovered evidence.",
    ),
    Capability(
        key="governance",
        name="Governance",
        category="verification",
        service="api.services.knowledge_governance.governance_service",
        cost=LOCAL,
        execution=BACKGROUND,
        description="Governed ingestion of newly discovered knowledge into the knowledge base.",
    ),
    Capability(
        key="provenance",
        name="Provenance",
        category="verification",
        service="api.services.knowledge_governance.provenance",
        cost=LOCAL,
        execution=SYNC,
        description="Traceable origin/versioning metadata for stored knowledge.",
    ),
    Capability(
        key="conflict_resolution",
        name="Conflict Resolution",
        category="verification",
        service="api.services.knowledge_governance.conflict_resolver",
        cost=LOCAL,
        execution=SYNC,
        description="Detects and preserves conflicting evidence rather than silently overwriting.",
    ),
    Capability(
        key="expert_reasoning",
        name="Expert Reasoning Engine",
        category="reasoning",
        service="api.services.research_brain.reasoning_engine",
        cost=LOCAL,
        execution=SYNC,
        description="Read-only context-assembly layer over the Knowledge Graph for expert reasoning.",
        enabled_flag="reasoning_engine_enabled",
    ),
    Capability(
        key="ai_scientist",
        name="Proactive AI Scientist",
        category="reasoning",
        service="api.services.research_brain.ai_scientist",
        cost=FREE,
        execution=BACKGROUND,
        description="Proactive classification/alerting over scheduler, research memory and trust signals.",
        enabled_flag="ai_scientist_enabled",
    ),
    Capability(
        key="knowledge_health",
        name="Knowledge Health",
        category="reasoning",
        service="api.services.research_brain.knowledge_health",
        cost=LOCAL,
        execution=SYNC,
        description="Cached scoring/aggregation of knowledge coverage, trust and freshness.",
        enabled_flag="knowledge_health_enabled",
    ),
    Capability(
        key="research_studio",
        name="Research Studio",
        category="authoring",
        service="api.services.research_pipeline",
        cost=FREE,
        execution=BACKGROUND,
        description="Evidence-grounded scientific research & authoring workspace (papers, reports, reviews).",
    ),
    Capability(
        key="book_authoring",
        name="Research / Book Authoring",
        category="authoring",
        service="api.services.book_service",
        cost=FREE,
        execution=BACKGROUND,
        description="Long-form book and chapter authoring over the research pipeline.",
    ),
    Capability(
        key="translation",
        name="Translation",
        category="authoring",
        service="api.utils.translator",
        cost=PAID,
        execution=SYNC,
        description="Domain-aware translation (local glossary plus optional external providers).",
    ),
    Capability(
        key="document_export",
        name="Document Export",
        category="authoring",
        service="api.utils.docgen",
        cost=LOCAL,
        execution=SYNC,
        description="Professional export to DOCX/PPTX/XLSX/PDF via the existing document pipeline.",
    ),
    Capability(
        key="workspace_agent",
        name="Workspace / File Tools",
        category="authoring",
        service="api.services.workspace_agent.agent",
        cost=LOCAL,
        execution=SYNC,
        description="Workspace-scoped file/document operations.",
        availability_note="Requires an active workspace.",
    ),
    Capability(
        key="canva_design",
        name="Canva Design",
        category="creation",
        service="api.services.connectors.providers.canva",
        cost=EXTERNAL,
        execution=SYNC,
        description="Generated design/artwork through the Canva connector.",
        availability_note="Requires a per-user connected Canva account.",
    ),
    Capability(
        key="connectors",
        name="Connectors",
        category="creation",
        service="api.services.connectors.service",
        cost=EXTERNAL,
        execution=SYNC,
        description="Connected-tool framework (Drive, Gmail, GitHub, Confluence, Canva, …).",
        availability_note="Each connector requires a per-user connection.",
    ),
)


def all_capabilities() -> tuple[Capability, ...]:
    """The full descriptive registry, regardless of runtime enabled state."""
    return _REGISTRY


def get_capabilities(settings: Optional[Settings] = None) -> list[dict]:
    """Registry resolved against runtime config, as plain serialisable dicts.

    Used by the read-only ``/capabilities`` endpoint.
    """
    s = settings or _default_settings
    return [
        {
            "key": c.key,
            "name": c.name,
            "category": c.category,
            "service": c.service,
            "cost": c.cost,
            "execution": c.execution,
            "description": c.description,
            "enabled": c.is_enabled(s),
            "enabled_flag": c.enabled_flag,
            "availability_note": c.availability_note,
        }
        for c in _REGISTRY
    ]


def enabled_capabilities(settings: Optional[Settings] = None) -> list[Capability]:
    """Only the capabilities whose runtime kill-switch (if any) is on."""
    s = settings or _default_settings
    return [c for c in _REGISTRY if c.is_enabled(s)]


def render_capability_awareness(settings: Optional[Settings] = None) -> str:
    """A compact, prompt-friendly block naming the platform's currently-enabled
    capabilities. Injected into the AI Chat identity prompt so Chat's
    self-description is truthful and tracks the config flags — a capability
    disabled via its flag drops out of this list and Chat stops claiming it.

    Deliberately terse (one line per capability) to keep the token cost
    negligible next to the full identity prompt.
    """
    caps = enabled_capabilities(settings)
    lines = [
        "PLATFORM CAPABILITIES CURRENTLY ENABLED (these belong to the X-Ray Academy "
        "AI platform — not to the underlying model — and are operational right now):"
    ]
    for c in caps:
        note = f" — {c.availability_note}" if c.availability_note else ""
        lines.append(f"• {c.name}: {c.description}{note}")
    return "\n".join(lines)
