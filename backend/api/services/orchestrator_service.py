"""
Cognitive Layer (Phase 2): AI Orchestrator.

A thin, additive decision layer — NOT a rewrite of chat's existing routing.
routes/chat.py already has working, tested branches (gallery search, vision
analysis, text RAG, the workspace-agent turn) driven by
gallery_service.detect_intent(). The Orchestrator runs alongside that and
hands back a RequestPlan of *additional* capability hints (memory, workspace,
OCR, translation, web, code, graph, proven-solution reuse, preferred model)
that the caller can act on — it never replaces the branching.

plan_request() is cheap deterministic regex/keyword heuristics, matching the
style already used by gallery_service.detect_intent() — not an extra LLM
call on every message, per the same cost/latency principle Phase 1 applied
to conversation summarization.
"""
from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from typing import Optional

_TRANSLATE_RE = re.compile(
    r"\b(translate|translation|in\s+(arabic|french|german|spanish|chinese|english|italian|portuguese))\b",
    re.IGNORECASE,
)
_OCR_HINT_RE = re.compile(r"\b(text|read|extract|ocr|words?)\b", re.IGNORECASE)
_CODE_RE = re.compile(
    r"\b(code|script|function|traceback|stack\s*trace|exception|syntax\s*error|"
    r"debug(ging)?|python|javascript|typescript|api\s*endpoint|regex)\b",
    re.IGNORECASE,
)
_WEB_RE = re.compile(
    r"\b(latest|current(ly)?|recent(ly)?|news|published\s+in\s+20\d\d|this\s+year|as\s+of\s+\d{4})\b",
    re.IGNORECASE,
)
_RELATIONAL_RE = re.compile(
    r"\b(what\s+depends\s+on|who\s+(worked|created|made|wrote)|related\s+to|connected\s+to|"
    r"linked\s+to|which\s+files?|what\s+changed|history\s+of)\b",
    re.IGNORECASE,
)
_PROBLEM_RE = re.compile(
    r"\b(fix|bug|broken|error|issue|problem|not\s+working|fails?|crash(es|ed)?|troubleshoot)\b",
    re.IGNORECASE,
)


@dataclass
class RequestPlan:
    use_memory: bool = True            # Global AI Brain search — already always-on today
    use_workspace: bool = False
    use_knowledge_base: bool = True
    use_ocr: bool = False
    use_translation: bool = False
    use_web_hint: bool = False         # advisory only — see orchestrator_service module docstring
    use_code: bool = False
    use_graph: bool = False
    check_proven_solution: bool = False
    preferred_task_hint: Optional[str] = None   # for provider_registry.get_for_task()

    def to_dict(self) -> dict:
        return asdict(self)


def plan_request(message: str, workspace_id: Optional[str] = None, has_image: bool = False) -> RequestPlan:
    q = (message or "").strip()

    plan = RequestPlan(
        use_workspace=bool(workspace_id),
        use_ocr=has_image and bool(_OCR_HINT_RE.search(q)),
        use_translation=bool(_TRANSLATE_RE.search(q)),
        use_web_hint=bool(_WEB_RE.search(q)),
        use_code=bool(_CODE_RE.search(q)),
        use_graph=bool(_RELATIONAL_RE.search(q)),
        check_proven_solution=bool(_PROBLEM_RE.search(q)),
    )

    # Multi-model routing hint — provider_registry.get_for_task() falls back
    # to get_active() whenever no override is configured, so this is
    # advisory only and changes nothing unless an admin sets one up.
    if plan.use_translation:
        plan.preferred_task_hint = "translation"
    elif has_image:
        plan.preferred_task_hint = "vision"
    elif plan.use_code:
        plan.preferred_task_hint = "code"

    return plan
