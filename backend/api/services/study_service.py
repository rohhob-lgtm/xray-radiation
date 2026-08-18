"""
Document Study Service — 11-phase self-learning pipeline.

Phases:
  1  Read          — full document text loaded
  2  Analyze       — extract entities (systems, components, procedures, etc.)
  3  Understand    — semantic understanding, audience, difficulty, relationships
  4  Build Knowledge — knowledge graph nodes + edges
  5  AI Memory     — structured knowledge already stored via phases 2-4
  6  Training Profile — learning objectives, quiz ideas, scenarios
  7  Quality Score — 8-dimension scoring
  8  Approve       — admin action (separate API endpoint)
  9  Future Use    — knowledge queried by generation routes (separate layer)
  10 Never Relearn — hash dedup (checked before this service is invoked)
  11 Report        — per-document study report (counts + confidence)

Cost strategy:
  - One GPT-4o call per document covers phases 2-7 entirely.
  - Result stored permanently in StudyJob → never repeated.
  - Only reasoning/educational tasks use OpenAI; extraction logic is local-first.
"""
from __future__ import annotations
import asyncio
import hashlib
import json
import logging
import os
import re
import traceback
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy.orm import Session

from api.config import settings
from api.db import crud
from api.db.models import (
    DocumentHash, StudyJob, KnowledgeNode, KnowledgeEdge, RagDocument
)
from api.services.ai_providers.registry import provider_registry
from api.services.knowledge_governance.governance_service import governance

log = logging.getLogger(__name__)

_STUDY_PROMPT = """\
You are an expert X-Ray security screening technical educator. Carefully read the document below and respond ONLY with a valid JSON object using this exact schema. Do not add markdown fences.

{
  "phase2": {
    "systems": ["list of main systems described"],
    "subsystems": ["list of subsystems"],
    "components": ["list of components and sub-components"],
    "functions": ["list of system/component functions"],
    "operating_principles": ["key operating principles"],
    "operating_procedures": ["step-by-step procedures"],
    "maintenance_procedures": ["maintenance procedures"],
    "troubleshooting": [{"symptom": "...", "cause": "...", "remedy": "..."}],
    "safety_warnings": ["safety warnings verbatim or paraphrased"],
    "radiation_info": ["radiation-related facts"],
    "specifications": [{"name": "...", "value": "..."}],
    "terminology": [{"term": "...", "definition": "..."}],
    "abbreviations": [{"abbr": "...", "expansion": "..."}],
    "fault_codes": [{"code": "...", "meaning": "..."}],
    "alarms": [{"alarm": "...", "condition": "..."}],
    "repair_methods": ["repair methods"]
  },
  "phase3": {
    "document_purpose": "one sentence describing what this document teaches",
    "intended_audience": "operator | maintenance | engineer | management | mixed",
    "difficulty_level": "beginner | intermediate | advanced",
    "prerequisite_knowledge": ["list of prerequisite topics"],
    "new_information": ["topics that are new or unique in this document"],
    "missing_topics": ["important topics that seem absent"],
    "contradictions": ["any internal contradictions found"],
    "confidence_score": 0.85
  },
  "phase4": {
    "nodes": [
      {"label": "...", "type": "System|Subsystem|Component|Function|Failure|Cause|Repair|Safety|Procedure|Specification|Alarm", "description": "..."}
    ],
    "edges": [
      {"from": "label of source node", "to": "label of target node", "relationship": "contains|causes|repairs|requires|triggers|prevents|sequence_step"}
    ]
  },
  "phase6": {
    "learning_objectives": ["By the end of this module, the learner will be able to..."],
    "instructor_notes": ["tips for instructors delivering this content"],
    "quiz_ideas": [{"question": "...", "correct_answer": "...", "bloom_level": "remember|understand|apply|analyze|evaluate|create"}],
    "practical_scenarios": ["real-world scenario descriptions"],
    "common_mistakes": ["mistakes learners commonly make"],
    "hands_on_exercises": ["hands-on exercise descriptions"],
    "field_tips": ["real field tips from the document"]
  },
  "phase7": {
    "educational_value": 80,
    "technical_quality": 75,
    "image_quality": 60,
    "diagram_quality": 65,
    "reference_quality": 70,
    "safety_coverage": 85,
    "maintenance_coverage": 80,
    "overall": 75,
    "comments": "brief quality justification"
  }
}

=== DOCUMENT START ===
{document_text}
=== DOCUMENT END ===
"""

_MAX_DOC_CHARS = 90_000  # ~22k tokens, leaves room for JSON response
_AI_TIMEOUT_SECONDS = max(300, int(os.environ.get("STUDY_AI_TIMEOUT_SECONDS", "300")))
_AI_MAX_RETRIES = 3


class StudyAIError(RuntimeError):
    """Structured AI-analysis failure with stage and diagnostics."""

    def __init__(self, stage: str, message: str, diagnostics: Optional[dict] = None):
        super().__init__(f"{stage}: {message}")
        self.stage = stage
        self.message = message
        self.diagnostics = diagnostics or {}


def _stage_log(event: str, **meta) -> None:
    """Emit consistent pipeline stage logs with JSON metadata."""
    try:
        payload = json.dumps(meta, ensure_ascii=True, default=str)
    except Exception:
        payload = str(meta)
    log.info("%s | %s", event, payload)


def _clip(value: object, limit: int = 3000) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + "...[truncated]"


def _validate_study_json(payload: object) -> dict:
    """Validate minimum JSON structure before any DB writes."""
    if not isinstance(payload, dict):
        raise StudyAIError("Invalid JSON", "Top-level response is not a JSON object")

    required = ("phase2", "phase3", "phase4", "phase6", "phase7")
    missing = [k for k in required if k not in payload]
    if missing:
        raise StudyAIError("Invalid JSON", f"Missing required sections: {', '.join(missing)}")

    for key in required:
        if not isinstance(payload.get(key), dict):
            raise StudyAIError("Invalid JSON", f"Section '{key}' must be an object")

    return payload


def _provider_plan() -> list[dict]:
    """
    Build provider order for study calls with automatic OpenAI/Gemini fallback.
    If active provider is one of them, keep it primary.
    """
    openai_key = os.environ.get("OPENAI_API_KEY") or settings.openai_api_key
    gemini_key = os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key

    openai_cfg = {
        "provider": "openai",
        "api_key": openai_key,
        "url": "https://api.openai.com/v1/chat/completions",
        "model": (getattr(provider_registry.get("openai"), "model", "") or settings.openai_model or "gpt-4o"),
    }
    gemini_cfg = {
        "provider": "gemini",
        "api_key": gemini_key,
        "url": "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
        "model": (getattr(provider_registry.get("gemini"), "model", "") or settings.gemini_model or "gemini-3.1-flash-lite"),
    }

    active = (provider_registry.active_id or "").strip().lower()
    ordered: list[dict] = []
    if active == "gemini":
        ordered = [gemini_cfg, openai_cfg]
    elif active == "openai":
        ordered = [openai_cfg, gemini_cfg]
    else:
        ordered = [openai_cfg, gemini_cfg]

    # Only keep configured providers.
    return [p for p in ordered if p.get("api_key")]


def compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_duplicate(db: Session, sha256: str) -> Optional[str]:
    """Return existing doc_id if already processed, else None."""
    row = db.query(DocumentHash).filter(DocumentHash.sha256 == sha256).first()
    return row.doc_id if row else None


def register_hash(db: Session, sha256: str, doc_id: str, filename: str) -> None:
    existing = db.query(DocumentHash).filter(DocumentHash.sha256 == sha256).first()
    if not existing:
        db.add(DocumentHash(sha256=sha256, doc_id=doc_id, filename=filename))
        db.commit()


async def run_study_pipeline(
    db: Session,
    doc_id: str,
    filename: str,
    text: str,
    sha256: Optional[str] = None,
    image_count: int = 0,
) -> StudyJob:
    """
    Execute phases 1-7 and 11 for a document.
    Phase 8 (approval) is a separate admin action.
    Phase 10 (dedup) must be checked before calling this.
    """
    # Create the study job record
    job = StudyJob(
        doc_id=doc_id,
        filename=filename,
        sha256=sha256,
        status="studying",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    try:
        _stage_log("AI_ANALYSIS_PIPELINE_START", doc_id=doc_id, filename=filename, job_id=job.id)

        # ── Mark actual pipeline start ──────────────────────────────────────────
        # started_at is set HERE (after commit, before GPT call) so that if the
        # server restarts between job creation and this point, started_at stays
        # None and the stale-job detector can identify the orphan immediately.
        job.started_at = datetime.now(timezone.utc)
        db.commit()

        # ── Phase 1: text is already provided ──────────────────────────────────
        if not (text or "").strip():
            raise StudyAIError("Parser error", "Extracted text is empty")

        doc_text = text[:_MAX_DOC_CHARS]
        if len(text) > _MAX_DOC_CHARS:
            doc_text += f"\n\n[Document truncated — {len(text):,} chars total, first {_MAX_DOC_CHARS:,} shown]"

        # ── Phases 2-7: single GPT-4o call ─────────────────────────────────────
        # Use replace() not .format() — the prompt contains JSON {} that would
        # be treated as format placeholders and raise KeyError.
        prompt = _STUDY_PROMPT.replace("{document_text}", doc_text)
        _stage_log(
            "AI_ANALYSIS_START",
            doc_id=doc_id,
            filename=filename,
            job_id=job.id,
            text_chars=len(doc_text),
            timeout_seconds=_AI_TIMEOUT_SECONDS,
        )
        result = await _call_gpt(prompt, doc_id=doc_id, filename=filename, job_id=job.id)

        _stage_log("AI_RESPONSE_RECEIVED", doc_id=doc_id, filename=filename, job_id=job.id)

        gpt_json, in_tok, out_tok, model, provider = result
        gpt_json = _validate_study_json(gpt_json)

        # ── Populate StudyJob from parsed JSON ──────────────────────────────────
        p2 = gpt_json.get("phase2", {})
        p3 = gpt_json.get("phase3", {})
        p4 = gpt_json.get("phase4", {})
        p6 = gpt_json.get("phase6", {})
        p7 = gpt_json.get("phase7", {})

        job.extracted_systems = p2.get("systems", []) + p2.get("subsystems", [])
        job.extracted_components = p2.get("components", [])
        job.extracted_procedures = p2.get("operating_procedures", []) + p2.get("maintenance_procedures", [])
        job.extracted_terminology = p2.get("terminology", [])
        job.extracted_warnings = p2.get("safety_warnings", [])
        job.extracted_specs = p2.get("specifications", [])
        job.extracted_fault_codes = p2.get("fault_codes", []) + p2.get("alarms", [])
        job.extracted_abbreviations = p2.get("abbreviations", [])

        job.document_purpose = p3.get("document_purpose")
        job.intended_audience = p3.get("intended_audience")
        job.difficulty_level = p3.get("difficulty_level")
        job.prerequisite_knowledge = p3.get("prerequisite_knowledge", [])
        job.new_information = p3.get("new_information", [])
        job.contradictions = p3.get("contradictions", [])
        job.missing_topics = p3.get("missing_topics", [])
        job.overlapping_docs = []  # cross-document comparison — future enhancement

        job.graph_nodes = p4.get("nodes", [])
        job.graph_edges = p4.get("edges", [])

        job.learning_objectives = p6.get("learning_objectives", [])
        job.instructor_notes = p6.get("instructor_notes", [])
        job.quiz_ideas = p6.get("quiz_ideas", [])
        job.practical_scenarios = p6.get("practical_scenarios", [])
        job.common_mistakes = p6.get("common_mistakes", [])
        job.hands_on_exercises = p6.get("hands_on_exercises", [])
        job.field_tips = p6.get("field_tips", [])

        job.score_educational_value = p7.get("educational_value")
        job.score_technical_quality = p7.get("technical_quality")
        job.score_image_quality = p7.get("image_quality")
        job.score_diagram_quality = p7.get("diagram_quality")
        job.score_reference_quality = p7.get("reference_quality")
        job.score_safety_coverage = p7.get("safety_coverage")
        job.score_maintenance_coverage = p7.get("maintenance_coverage")
        job.score_overall = p7.get("overall")
        job.confidence_score = float(p3.get("confidence_score", 0.75))

        # ── Phase 11: report counts ─────────────────────────────────────────────
        job.report_concepts = (
            len(job.extracted_terminology) + len(job.extracted_abbreviations)
        )
        job.report_systems = len(job.extracted_systems)
        job.report_components = len(job.extracted_components)
        job.report_procedures = len(job.extracted_procedures)
        job.report_troubleshooting = len(p2.get("troubleshooting", []))
        job.report_images_understood = image_count
        job.report_new_info_count = len(job.new_information)
        job.report_duplicate_info_count = 0  # populated on approval if needed
        job.report_graph_nodes_added = len(job.graph_nodes)
        job.report_graph_edges_added = len(job.graph_edges)

        job.input_tokens = in_tok
        job.output_tokens = out_tok
        job.model_used = model
        job.rejection_reason = None
        # Intermediate status — extraction complete, about to integrate
        job.status = "validating"
        _stage_log(
            "DATABASE_SAVE",
            doc_id=doc_id,
            filename=filename,
            job_id=job.id,
            provider=provider,
            model=model,
            input_tokens=in_tok,
            output_tokens=out_tok,
        )
        db.commit()

        # ── Auto-integrate (owner-trusted workflow) ─────────────────────────────
        # Every owner-uploaded source is trusted. No manual review required.
        # Materialise knowledge directly into the permanent graph.
        try:
            job = approve_study_job(db, job, "auto")
            # Consistency rule: only mark "integrated" when knowledge was actually committed.
            # If GPT returned no nodes at all, hold the job for manual review.
            if job.report_graph_nodes_added == 0 and not (job.graph_nodes or []):
                job.status = "awaiting_approval"
                log.warning(
                    "Auto-integration yielded 0 nodes for %s — holding for manual review",
                    filename,
                )
            else:
                # Override "approved" → "integrated" (owner workflow vocabulary)
                job.status = "integrated"
                log.info(
                    "Auto-integrated %s: %d nodes, %d edges, score=%s",
                    filename, job.report_graph_nodes_added, job.report_graph_edges_added, job.score_overall,
                )
            db.commit()
            db.refresh(job)
            _stage_log(
                "ANALYSIS_COMPLETED",
                doc_id=doc_id,
                filename=filename,
                job_id=job.id,
                provider=provider,
                model=model,
                status=job.status,
                graph_nodes=job.report_graph_nodes_added,
                graph_edges=job.report_graph_edges_added,
            )
        except Exception as int_exc:
            log.error("Auto-integration failed for %s: %s", filename, int_exc, exc_info=True)
            # Fall back to awaiting_approval so an admin can still manually approve
            job.status = "awaiting_approval"
            job.rejection_reason = f"Database error: Auto-integration failed: {int_exc}"
            db.commit()
            db.refresh(job)

        return job

    except StudyAIError as exc:
        detail = _clip(exc.message, 2000)
        stage_reason = f"{exc.stage}: {detail}"
        log.error(
            "Study pipeline failed for doc=%s at stage=%s: %s diagnostics=%s",
            doc_id,
            exc.stage,
            exc.message,
            _clip(json.dumps(exc.diagnostics, default=str), 4000),
            exc_info=True,
        )
        job.status = "failed"
        job.rejection_reason = stage_reason
        db.commit()
        return job
    except Exception as exc:
        log.error("Study pipeline failed for doc=%s: %s", doc_id, exc, exc_info=True)
        job.status = "failed"
        job.rejection_reason = f"Unexpected error: {_clip(exc, 2000)}"
        db.commit()
        return job


async def _call_gpt(prompt: str, doc_id: str = "", filename: str = "", job_id: str = ""):
    """
    Call study AI with retries and OpenAI↔Gemini fallback.

    Returns:
      (parsed_json, input_tokens, output_tokens, model, provider)
    """
    import httpx

    providers = _provider_plan()
    if not providers:
        raise StudyAIError(
            "Provider unavailable",
            "No configured OpenAI or Gemini provider is available",
            diagnostics={"openai_configured": bool(os.environ.get("OPENAI_API_KEY") or settings.openai_api_key),
                         "gemini_configured": bool(os.environ.get("GEMINI_API_KEY") or settings.gemini_api_key)},
        )

    all_failures: list[dict] = []

    for cfg in providers:
        provider = cfg["provider"]
        model = cfg["model"]
        url = cfg["url"]
        api_key = cfg["api_key"]

        for attempt in range(1, _AI_MAX_RETRIES + 1):
            _stage_log(
                "AI_REQUEST_SENT",
                doc_id=doc_id,
                filename=filename,
                job_id=job_id,
                provider=provider,
                model=model,
                attempt=attempt,
                timeout_seconds=_AI_TIMEOUT_SECONDS,
            )

            req_payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.2,
                "response_format": {"type": "json_object"},
                "max_tokens": 8000,
            }

            try:
                async with httpx.AsyncClient(timeout=_AI_TIMEOUT_SECONDS) as client:
                    resp = await client.post(
                        url,
                        headers={"Authorization": f"Bearer {api_key}"},
                        json=req_payload,
                    )
                    raw_body = resp.text
                    resp.raise_for_status()
                    data = resp.json()

                raw = data["choices"][0]["message"]["content"]
                parsed = json.loads(raw)
                parsed = _validate_study_json(parsed)
                usage = data.get("usage", {})

                _stage_log(
                    "AI_RESPONSE_RECEIVED",
                    doc_id=doc_id,
                    filename=filename,
                    job_id=job_id,
                    provider=provider,
                    model=data.get("model", model),
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                )
                return (
                    parsed,
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    data.get("model", model),
                    provider,
                )

            except httpx.TimeoutException as exc:
                failure = {
                    "stage": "OpenAI timeout" if provider == "openai" else "Gemini timeout",
                    "provider": provider,
                    "model": model,
                    "timeout_seconds": _AI_TIMEOUT_SECONDS,
                    "attempt": attempt,
                    "tokens": {"input": 0, "output": 0},
                    "response_body": "",
                    "exception": str(exc),
                    "stack_trace": traceback.format_exc(),
                }
                all_failures.append(failure)
                log.error("AI timeout: %s", json.dumps(failure, default=str))
            except httpx.HTTPStatusError as exc:
                body = exc.response.text if exc.response is not None else ""
                stage = "Provider unavailable"
                if provider == "gemini" and exc.response is not None and exc.response.status_code == 429:
                    stage = "Gemini quota exceeded"
                elif provider == "openai" and exc.response is not None and exc.response.status_code == 429:
                    stage = "OpenAI quota exceeded"
                failure = {
                    "stage": stage,
                    "provider": provider,
                    "model": model,
                    "timeout_seconds": _AI_TIMEOUT_SECONDS,
                    "attempt": attempt,
                    "tokens": {"input": 0, "output": 0},
                    "response_body": _clip(body, 4000),
                    "status_code": exc.response.status_code if exc.response is not None else None,
                    "exception": str(exc),
                    "stack_trace": traceback.format_exc(),
                }
                all_failures.append(failure)
                log.error("AI HTTP error: %s", json.dumps(failure, default=str))
            except json.JSONDecodeError as exc:
                failure = {
                    "stage": "Invalid JSON",
                    "provider": provider,
                    "model": model,
                    "timeout_seconds": _AI_TIMEOUT_SECONDS,
                    "attempt": attempt,
                    "tokens": {"input": 0, "output": 0},
                    "response_body": _clip(locals().get("raw", ""), 4000),
                    "exception": str(exc),
                    "stack_trace": traceback.format_exc(),
                }
                all_failures.append(failure)
                log.error("AI JSON decode error: %s", json.dumps(failure, default=str))
            except StudyAIError as exc:
                failure = {
                    "stage": exc.stage,
                    "provider": provider,
                    "model": model,
                    "timeout_seconds": _AI_TIMEOUT_SECONDS,
                    "attempt": attempt,
                    "tokens": {"input": 0, "output": 0},
                    "response_body": _clip(locals().get("raw", ""), 4000),
                    "exception": exc.message,
                    "stack_trace": traceback.format_exc(),
                }
                all_failures.append(failure)
                log.error("AI validation error: %s", json.dumps(failure, default=str))
            except Exception as exc:
                failure = {
                    "stage": "Provider unavailable",
                    "provider": provider,
                    "model": model,
                    "timeout_seconds": _AI_TIMEOUT_SECONDS,
                    "attempt": attempt,
                    "tokens": {"input": 0, "output": 0},
                    "response_body": _clip(locals().get("raw_body", ""), 4000),
                    "exception": str(exc),
                    "stack_trace": traceback.format_exc(),
                }
                all_failures.append(failure)
                log.error("AI request failed: %s", json.dumps(failure, default=str))

            # Retry with exponential backoff on the same provider.
            if attempt < _AI_MAX_RETRIES:
                await asyncio.sleep(2 ** (attempt - 1))

        _stage_log(
            "AI_PROVIDER_FALLBACK",
            doc_id=doc_id,
            filename=filename,
            job_id=job_id,
            failed_provider=provider,
            next_provider=("gemini" if provider == "openai" else "openai"),
        )

    last = all_failures[-1] if all_failures else {}
    stage = str(last.get("stage") or "Provider unavailable")
    raise StudyAIError(
        stage,
        f"{stage} after {_AI_MAX_RETRIES} retries per provider",
        diagnostics={"failures": all_failures},
    )


def approve_study_job(
    db: Session,
    job: StudyJob,
    approved_by: str,
) -> StudyJob:
    """
    Phase 8 — Admin approves a study job.
    Materialises all extracted knowledge nodes/edges into the permanent graph.
    """
    nodes_added = 0
    edges_added = 0
    node_map: dict[str, str] = {}  # label → KnowledgeNode.id

    # Upsert nodes — routed through KnowledgeGovernanceService (Phase 2B.2),
    # the only path allowed to write to the graph. Reinforcement stays
    # weight-based (approved=True, weight += 0.1 on repeat) exactly as
    # before; governance now also records provenance and an audit row for
    # every node this study pipeline materialises.
    for raw_node in job.graph_nodes:
        label = str(raw_node.get("label", "")).strip()[:500]
        ntype = str(raw_node.get("type", "Component")).strip()
        desc = str(raw_node.get("description", "")).strip()
        if not label:
            continue

        was_existing = crud.get_knowledge_node_by_label(db, label, ntype) is not None
        node = governance.upsert_node_with_reinforcement(
            db, label=label, node_type=ntype, description=desc or None,
            source_doc_id=job.doc_id, study_job_id=job.id,
        )
        node_map[label] = node.id
        if not was_existing:
            nodes_added += 1

    # Upsert edges (only between nodes we know) — same governance path.
    for raw_edge in job.graph_edges:
        from_label = str(raw_edge.get("from", "")).strip()
        to_label = str(raw_edge.get("to", "")).strip()
        rel = str(raw_edge.get("relationship", "contains")).strip()

        from_id = node_map.get(from_label)
        to_id = node_map.get(to_label)
        if not from_id or not to_id or from_id == to_id:
            continue

        was_existing = crud.get_knowledge_edge_by_relationship(db, from_id, to_id, rel) is not None
        governance.upsert_edge_with_reinforcement(db, from_node_id=from_id, to_node_id=to_id, relationship=rel)
        if not was_existing:
            edges_added += 1

    job.status = "approved"
    job.approved_by = approved_by
    job.approved_at = datetime.now(timezone.utc)
    job.report_graph_nodes_added = nodes_added
    job.report_graph_edges_added = edges_added
    db.commit()
    db.refresh(job)

    log.info("Study job %s approved — %d nodes, %d edges added to graph", job.id, nodes_added, edges_added)
    return job


def get_knowledge_context(db: Session, topic_hint: str = "", limit: int = 200) -> dict:
    """
    Retrieve approved knowledge for use in course/exam generation prompts.
    Returns a structured dict that can be JSON-serialised into a system prompt.
    """
    from sqlalchemy import func as _f

    jobs = (
        db.query(StudyJob)
        .filter(StudyJob.status.in_(["approved", "integrated"]))
        .order_by(StudyJob.approved_at.desc())
        .limit(50)
        .all()
    )

    terminology: list[dict] = []
    components: list[str] = []
    procedures: list[str] = []
    warnings: list[str] = []
    quiz_ideas: list[dict] = []
    learning_objectives: list[str] = []
    field_tips: list[str] = []

    seen_terms: set[str] = set()

    for job in jobs:
        for t in (job.extracted_terminology or []):
            term = t.get("term", "") if isinstance(t, dict) else str(t)
            if term and term not in seen_terms:
                seen_terms.add(term)
                terminology.append(t)
        components.extend(job.extracted_components or [])
        procedures.extend(job.extracted_procedures or [])
        warnings.extend(job.extracted_warnings or [])
        quiz_ideas.extend(job.quiz_ideas or [])
        learning_objectives.extend(job.learning_objectives or [])
        field_tips.extend(job.field_tips or [])

    # Deduplicate lists
    components = list(dict.fromkeys(components))[:limit]
    procedures = list(dict.fromkeys(procedures))[:limit]
    warnings = list(dict.fromkeys(warnings))[:60]

    nodes_count = db.query(_f.count(KnowledgeNode.id)).filter(KnowledgeNode.approved == True).scalar() or 0
    edges_count = db.query(_f.count(KnowledgeEdge.id)).filter(KnowledgeEdge.approved == True).scalar() or 0

    return {
        "approved_docs": len(jobs),
        "graph_nodes": nodes_count,
        "graph_edges": edges_count,
        "terminology": terminology[:150],
        "components": components,
        "procedures": procedures,
        "safety_warnings": warnings,
        "quiz_ideas": quiz_ideas[:50],
        "learning_objectives": learning_objectives[:50],
        "field_tips": field_tips[:40],
    }
