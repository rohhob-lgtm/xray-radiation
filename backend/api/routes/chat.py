"""Chat routes — persistent conversations with real RAG QA and image retrieval."""
from __future__ import annotations
import asyncio
import json
import logging
import re
import time
import uuid
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel

_log = logging.getLogger(__name__)
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from api.db import get_db
from api.db import crud
from api.db.crud import (
    create_conversation, get_conversation, list_conversations,
    delete_conversation, add_message, get_messages,
    conversation_to_dict,
)
from api.db.models import ChatUsage
from api.middleware.auth import optional_auth, require_auth
from api.models.chat import (
    ChatMessageInput, ChatResponse, ConversationInput,
    Conversation, ConversationWithMessages, Message,
)
from api.services.ai_providers.registry import provider_registry
from api.services.rag_service import (
    retrieve_chunks, build_qa_system_prompt, build_qa_system_prompt_from_results, search_rag_images,
)
from api.services.xray_knowledge import XRAY_SYSTEM_PROMPT, build_platform_identity_prompt
from api.services.gallery_service import (
    detect_intent, extract_gallery_query, search_images_with_fallback,
    translate_image_query,
)
from api.services.canva_chat_intent import detect_canva_intent
from api.services.connector_chat_router import detect_connector_tool_intent
from api.services.document_chat_intent import detect_document_generation_intent, detect_workspace_task_intent
from api.services.research_agent_chat_intent import detect_research_agent_intent, handle_research_agent_intent
from api.services.connectors.providers.canva.connector import canva_connector
from api.services.connectors.service import connector_service
from api.services.design_content import detect_design_intent, detect_design_edit_intent, generate_design_spec
from api.services.design_orchestrator import design_orchestrator
from api.services.agent_orchestrator.intents import wants_drive_save
from api.services.agent_orchestrator.runner import agent_orchestrator_runner
from api.services.identity import get_identity, MemoryScope
from api.services import memory_service, learning_service, graph_service
from api.services.orchestrator_service import plan_request, RequestPlan
from api.services.retrieval_utils import MemoryResult
from api.services.workspace_index import ensure_fresh
from api.config import settings

router = APIRouter(tags=["chat"])

# Per-provider default was too low (2048) for some real replies to complete
# without truncation — raised uniformly for the AI Chat feature. Providers
# that don't support a configurable ceiling simply ignore this value.
_CHAT_MAX_TOKENS = 8192
# Image-request explanations are meant to be a concise, sourced answer beside
# the image grid — not a full essay. A tighter cap keeps the turn responsive.
_IMAGE_ANSWER_MAX_TOKENS = 1024

# Urgent regression fix: some providers occasionally hallucinate a fake
# tool-call-shaped JSON blob (e.g. {"action": "dalle.text2im", ...}) as
# plain answer text when asked for something they have no real tool for —
# observed live with Google Gemini on image-generation requests. Plain chat
# never registers any tools (see gemini_provider.chat/stream_chat — only
# chat_with_tools does), so this is pure hallucination, not a real call.
# Internal-looking payloads must never reach the user.
_TOOL_CALL_LEAK_RE = re.compile(r'^\s*\{\s*"(?:action|tool|tool_call|function_call)"\s*:', re.IGNORECASE)
_TOOL_CALL_LEAK_SNIFF_CHARS = 40
_TOOL_CALL_LEAK_FALLBACK = (
    "I don't have a built-in tool to generate a custom image for that. "
    "I can search the Knowledge Base and the internet for a real reference "
    "image instead — try asking me to show you a picture of it."
)


async def _leak_guarded_stream_chat(provider, history, system_prompt, max_tokens):
    """Wraps provider.stream_chat(...): sniffs the first ~40 characters of
    the reply and, if they look like a tool-call JSON blob, substitutes
    _TOOL_CALL_LEAK_FALLBACK and swallows the rest of the hallucinated
    stream instead of forwarding it. Ordinary replies pass through
    unchanged (the sniffed prefix is yielded once buffering completes)."""
    buffer = ""
    sniffed = False
    leaking = False
    async for chunk in provider.stream_chat(history, system_prompt=system_prompt, max_tokens=max_tokens):
        if not sniffed:
            buffer += chunk
            if len(buffer) < _TOOL_CALL_LEAK_SNIFF_CHARS:
                continue
            sniffed = True
            if _TOOL_CALL_LEAK_RE.match(buffer):
                leaking = True
                yield _TOOL_CALL_LEAK_FALLBACK
            else:
                yield buffer
            continue
        if leaking:
            continue
        yield chunk
    if not sniffed:
        if _TOOL_CALL_LEAK_RE.match(buffer):
            yield _TOOL_CALL_LEAK_FALLBACK
        elif buffer:
            yield buffer


def _format_source_trust_block(s: dict) -> str:
    """Every trust-related chat response goes through this — never claim a
    source is (dis)trusted without static/dynamic/effective scores, status,
    top reasons, and when it was last calculated (Phase 2B.3 requirement)."""
    if not s:
        return "No source information available."
    reasons = s.get("trust_signal_summary") or []
    reasons_text = (
        "; ".join(f"{r.get('reason_code')} ({r.get('delta'):+.1f})" for r in reasons[:5])
        if reasons else "no dynamic signals recorded yet"
    )
    return (
        f"**{s.get('title') or s.get('url')}** — {s.get('domain')}\n"
        f"- Static quality: {s.get('quality_score')}/100 ({s.get('quality_label')})\n"
        f"- Dynamic trust: {s.get('dynamic_trust_score')}/100\n"
        f"- Effective trust: {s.get('effective_trust_score')}/100 — status: **{s.get('trust_status')}**\n"
        f"- Top reasons: {reasons_text}\n"
        f"- Last calculated: {s.get('last_trust_calculated_at') or 'never'} "
        f"(algorithm v{s.get('trust_algorithm_version')})"
    )


def _format_topic_memory_block(m: dict) -> str:
    """Every Research Memory chat response goes through this — always shows
    when research last happened and what's been learned so far, never just
    a templated "OK" (Phase 2B.4 requirement)."""
    if not m:
        return "No topic memory available."
    return (
        f"**Topic**: {m.get('topic_key')} ({m.get('content_category')})\n"
        f"- Last research: {m.get('last_research') or 'never'}\n"
        f"- Last knowledge update: {m.get('last_update') or 'never'}\n"
        f"- Freshness: **{m.get('freshness_status')}**\n"
        f"- New facts found: {m.get('new_facts_count')}, updated: {m.get('updated_facts_count')}, "
        f"conflicts found: {m.get('conflicts_found_count')}\n"
        f"- Files downloaded: {m.get('downloaded_files_count')}, next refresh due: {m.get('next_refresh') or 'not scheduled'}"
    )


def _resolve_provider(provider_override: Optional[str], preferred_task_hint: Optional[str]):
    """Manual Auto/Gemini/Claude selection wins over automatic task routing;
    falling back to get_for_task() preserves existing behavior when unset or
    when the requested provider isn't actually configured."""
    if provider_override and provider_override != "auto":
        explicit = provider_registry.get(provider_override)
        if explicit and explicit.is_configured:
            return explicit
    return provider_registry.get_for_task(preferred_task_hint)


async def _summarize_in_background(conversation_id: str) -> None:
    """
    Fire-and-forget conversation summarization (every ~20-30 turns, per
    settings.memory_summary_every_n_messages) — runs outside the request's
    DB session lifecycle, so it opens its own.
    """
    from api.db.base import SessionLocal
    bg_db = SessionLocal()
    try:
        await memory_service.summarize_conversation_if_due(
            bg_db, conversation_id, every_n=settings.memory_summary_every_n_messages,
        )
    except Exception:
        _log.exception("Background conversation summarization failed for conversation_id=%s", conversation_id)
    finally:
        bg_db.close()


# ──────────────────────────────────────────────────────────
# AI Chat Workspace agent turn — additive branch of /chat/stream.
# Entered only when the request carries a workspace_id; every existing
# text/vision/gallery code path above and below is untouched otherwise.
# ──────────────────────────────────────────────────────────

async def _stream_workspace_turn(
    db: Session,
    conv_id: str,
    user_id: Optional[str],
    workspace_id: str,
    message: str,
    history: list[dict],
    req_id: str,
):
    import json as _json
    from api.db import crud as _crud
    from api.services.ai_providers.registry import provider_registry as _registry
    from api.services.workspace_agent.agent import run_workspace_turn

    if not user_id:
        yield f"data: {_json.dumps({'type': 'error', 'error': 'Sign in to use file/folder workspaces.', 'request_id': req_id})}\n\n"
        return

    ws = _crud.get_workspace(db, workspace_id, user_id)
    if not ws:
        yield f"data: {_json.dumps({'type': 'error', 'error': 'Workspace not found or you do not have access to it.', 'request_id': req_id})}\n\n"
        return

    conv = _crud.get_conversation(db, conv_id)
    if conv and conv.workspace_id != ws.id:
        _crud.link_conversation_workspace(db, conv_id, ws.id)

    provider = _registry.get_active()
    if not provider:
        yield f"data: {_json.dumps({'type': 'error', 'error': 'No AI provider available', 'request_id': req_id})}\n\n"
        return

    model_name = getattr(provider, "model", "") or getattr(provider, "model_name", "") or ""
    # History for the workspace turn excludes the just-added current user
    # message (run_workspace_turn appends it itself with the workspace's
    # own system prompt), and excludes any raw tool-call scaffolding.
    plain_history = [h for h in history[:-1] if h.get("role") in ("user", "assistant")]

    yield f"data: {_json.dumps({'type': 'start', 'conversation_id': conv_id, 'provider': provider.provider_name, 'model': 'workspace-agent', 'request_id': req_id})}\n\n"

    saved = False
    try:
        async for event in run_workspace_turn(db, ws, conv, message, plain_history, provider, model_name):
            etype = event.get("type")
            if etype == "done":
                add_message(db, conv_id, "assistant", event["content"], image_url=None)
                saved = True
                asyncio.create_task(_summarize_in_background(conv_id))
                yield f"data: {_json.dumps({'type': 'done', 'conversation_id': conv_id, 'request_id': req_id, 'finish_reason': 'stop', 'task_id': event.get('task_id'), 'status': event.get('status')})}\n\n"
            else:
                yield f"data: {_json.dumps({**event, 'request_id': req_id})}\n\n"
    except Exception as exc:
        _log.exception("[chat:%s] workspace agent turn failed", req_id)
        if not saved:
            yield f"data: {_json.dumps({'type': 'error', 'error': str(exc), 'request_id': req_id})}\n\n"


# ──────────────────────────────────────────────────────────
# Conversations
# ──────────────────────────────────────────────────────────

@router.get("/conversations")
def list_conversations_endpoint(
    request: Request,
    db: Session = Depends(get_db),
    scope: MemoryScope = Depends(get_identity),
):
    convs = list_conversations(db, user_id=scope.user_id, anon_session_id=scope.anon_session_id)
    return [conversation_to_dict(c) for c in convs]


@router.post("/conversations", status_code=201)
def create_conversation_endpoint(
    body: ConversationInput,
    request: Request,
    db: Session = Depends(get_db),
    scope: MemoryScope = Depends(get_identity),
):
    conv = create_conversation(
        db, user_id=scope.user_id, title=body.title, anon_session_id=scope.anon_session_id,
    )
    return conversation_to_dict(conv)


@router.get("/conversations/{conversation_id}")
def get_conversation_endpoint(
    conversation_id: str,
    db: Session = Depends(get_db),
):
    conv = get_conversation(db, conversation_id)
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = get_messages(db, conversation_id)
    return {
        "id": conv.id,
        "title": conv.title,
        "created_at": conv.created_at.isoformat(),
        "workspace_id": conv.workspace_id,
        "messages": [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "image_url": m.image_url,
                "created_at": m.created_at.isoformat(),
            }
            for m in msgs
        ],
    }


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation_endpoint(conversation_id: str, db: Session = Depends(get_db)):
    if not delete_conversation(db, conversation_id):
        raise HTTPException(status_code=404, detail="Conversation not found")


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

AGENT_SYSTEM_PROMPTS = {
    "research": """You are an elite X-ray science research agent specializing in academic and scientific content.

Your capabilities:
- Generate IEEE, Elsevier, and Nature-format research papers
- Write literature reviews with proper citation formatting [Author, Year]
- Identify research gaps and propose novel experiments
- Structure scientific arguments with hypotheses, methodology, and conclusions
- Apply statistical analysis and interpret experimental data
- Reference current X-ray research: dual-energy CT, photon counting detectors, AI-driven ATR

Always respond with academic rigor, precise technical language, and structured formatting (Abstract, Introduction, Methods, Results, Conclusion). Include equations where relevant using LaTeX notation like $E = hf$.""",

    "physics": """You are an expert X-ray physics and radiation science agent.

Your specializations:
- Radiation physics: photon interactions (photoelectric effect, Compton scatter, pair production)
- X-ray tube physics: bremsstrahlung, characteristic radiation, kVp/mAs relationships
- Detector physics: scintillators, direct conversion, CdTe, Si, Ge detectors
- Radiation safety: ALARA, shielding design, HVL/TVL calculations, dose optimization
- Beer-Lambert law: I = I₀·e^(-μx), mass attenuation coefficients, buildup factors
- Geometry: magnification, penumbra, spatial resolution, MTF, DQE

Always show your calculations step-by-step. Present formulas in LaTeX notation. Specify units (keV, mGy, cm², g). Reference IAEA, NCRP, ICRU standards where applicable.""",

    "patent": """You are a specialized X-ray technology patent and intellectual property agent.

Your expertise:
- Analyze novelty and inventive step of X-ray imaging innovations
- Identify prior art in security scanning, medical imaging, and industrial NDT
- Draft patent claims (independent, dependent, method, apparatus, system claims)
- Assess freedom-to-operate for new detector designs, algorithms, and systems
- Generate invention disclosures for cargo scanning, baggage screening, CT reconstruction
- Map competitive patent landscapes for major X-ray manufacturers (Smiths Detection, L3 Technologies, Nuctech, Rapiscan, Analogic)

Always structure responses with: Novelty Analysis → Prior Art Assessment → Claim Strategy → Commercial Opportunity → Next Steps.""",

    "vision": """You are an expert X-ray image analysis and threat detection agent.

Your capabilities:
- Analyze X-ray scan images for threats: IEDs, firearms, blades, narcotics, currency
- Identify organic, inorganic, metallic, and composite materials by attenuation patterns
- Apply dual-energy discrimination: effective atomic number (Zeff), density differentiation
- Assess image quality: spatial resolution, contrast, noise, artifacts
- Recommend ATR algorithm parameters and detection thresholds
- Interpret density profiles, edge enhancement, and material segmentation

When analyzing images, structure your response:
1. Image Quality Assessment
2. Object Identification (with confidence levels)
3. Threat Assessment
4. Recommended Actions
5. Image Enhancement Suggestions""",

    "maintenance": """You are an expert X-ray equipment maintenance and field service agent.

Your knowledge covers:
- Preventive and corrective maintenance for ZBV, LZBV, and cargo scanning systems
- X-ray source maintenance: tube replacement, HV power supply, cooling systems
- Detector array calibration: gain/offset correction, bad pixel mapping, flat-field correction
- Conveyor and mechanical system maintenance: belt tensioning, drive motor diagnostics
- Electronic fault diagnosis: fault codes, diagnostic procedures, replacement protocols
- Radiation safety during maintenance: interlocks, personal dosimetry, area monitoring

Always provide: Symptom Analysis → Root Cause → Step-by-Step Procedure → Safety Precautions → Verification Test → Preventive Recommendation.""",

    "training": """You are an expert X-ray operator training and education agent.

Your specializations:
- Operator competency development for Level 1, 2, and 3 certification
- Lesson plan design using adult learning principles (ADDIE, Bloom's taxonomy)
- Quiz and exam creation covering: physics, operations, safety, threat recognition
- Training needs analysis and gap identification
- Scenario-based learning for threat detection decision-making
- Certificate program development aligned with ECAC, TSA, EU Regulation 2015/1998

Always adapt content to the learner's level (beginner/intermediate/advanced) and role (operator/supervisor/instructor/engineer).""",

    "innovation": """You are a cutting-edge X-ray technology innovation and invention agent.

Your focus areas:
- Next-generation detector technologies: photon counting, spectral CT, CMOS sensors
- AI and deep learning for threat detection: CNNs, transformers, federated learning
- Novel X-ray source designs: carbon nanotube, inverse Compton, compact synchrotron
- Advanced reconstruction algorithms: iterative CT, compressed sensing, neural reconstruction
- Compact system architectures for checkpoints, ports, and mobile deployment
- Integration with emerging tech: robotics, quantum sensors, THz imaging

Always frame innovations with: Current Limitation → Novel Solution → Technical Feasibility → Patent Potential → Development Roadmap → Market Impact.""",

    # General mode: full expert identity injected even when no specialized agent is selected.
    # This ensures "What can you do?" and identity questions always get a professional answer.
    "general": XRAY_SYSTEM_PROMPT,
}


def _base_identity_prompt(agent_prompt: Optional[str], agent_mode: str) -> str:
    """Resolve the no-knowledge-context system prompt.

    For the general identity persona (the "who are you / what can you do?"
    path) return the platform identity plus the runtime-resolved capability
    list, so Chat's self-description tracks the live capability flags. A
    specialized agent persona (research/physics/…) is returned unchanged to
    keep its focus and avoid token bloat on domain answers.
    """
    if agent_prompt is None or agent_mode == "general":
        return build_platform_identity_prompt(settings)
    return agent_prompt


async def _build_system_prompt(
    message: str,
    db: Session,
    agent_mode: str = "general",
    scope: Optional[MemoryScope] = None,
    workspace_id: Optional[str] = None,
    plan: Optional["RequestPlan"] = None,
) -> str:
    """
    Build the system prompt for this query.
    Agent mode selects a specialized domain expert persona.

    When `scope` is provided, this is the Global AI Brain's semantic-search-
    before-every-response entry point: documents, durable memory/decisions/
    preferences, conversation summaries, and (if workspace_id is set)
    workspace files are all searched and merged. Without a scope (any other
    caller that hasn't adopted identity resolution), falls back to the
    original document-only RAG behavior.

    `plan` (from orchestrator_service.plan_request) is additive: when it
    flags check_proven_solution / use_graph, the Learning Engine / Knowledge
    Graph results are appended to the same merged result list — the existing
    doc/memory/summary/workspace merge from search_global_brain is untouched.
    """
    agent_prompt = AGENT_SYSTEM_PROMPTS.get(agent_mode)

    if scope is not None:
        results = await memory_service.search_global_brain(
            db, scope, message, workspace_id=workspace_id, top_k=8,
        )

        if plan and plan.check_proven_solution:
            solution = await learning_service.find_proven_solution(db, scope, agent_mode, message)
            if solution:
                results.append(solution)

        if plan and plan.use_graph and workspace_id:
            related = await graph_service.find_related(db, scope, "project", workspace_id, depth=2, query=message)
            for r in related[:5]:
                node = r["node"]
                results.append(MemoryResult(
                    source_kind="graph",
                    title=f"{node['entity_type']}: {node['label'] or node['entity_ref']}",
                    content=f"{r['relationship']} (hop {r['hop_distance']})",
                    score=r["score"],
                    meta=node,
                ))

        if results:
            qa_prompt = build_qa_system_prompt_from_results(results)
            if agent_prompt:
                return agent_prompt + "\n\n---\n\n" + qa_prompt
            return qa_prompt
        return _base_identity_prompt(agent_prompt, agent_mode)

    chunks = await retrieve_chunks(message, db, top_k=5)
    if chunks:
        # Knowledge Evolution Engine (Sub-Phase 2A) — Unified Brain: versioned
        # graph facts alongside RAG chunks, via the same shared prompt builder.
        from api.services.research_brain.graph_query import get_relevant_facts
        graph_facts = get_relevant_facts(db, message)
        qa_prompt = build_qa_system_prompt(chunks, graph_facts=graph_facts)
        if agent_prompt:
            # Prepend agent persona before the QA context
            return agent_prompt + "\n\n---\n\n" + qa_prompt
        return qa_prompt

    return _base_identity_prompt(agent_prompt, agent_mode)


async def _handle_image_query(
    message: str,
    db: Session,
) -> tuple[str, Optional[str]]:
    """
    Search knowledge-base images using two complementary pipelines, then merge:

    1. ColPali visual search (primary) — retrieves rendered PDF pages ranked by
       MaxSim over multi-vector visual embeddings (ColQwen2 or OpenCLIP).
    2. Caption text search (fallback) — cosine similarity over GPT-5.4 vision
       captions on individually extracted figures.

    Returns (text_reply, relative_image_url_or_None).
    """
    from api.services.colpali_service import search_pages_colpali, get_backend

    # ── 1. ColPali visual search ───────────────────────────────
    colpali_pages = await search_pages_colpali(message, db, top_k=5)

    # ── 2. Caption/text search on extracted figures ───────────
    caption_images = await search_rag_images(message, db)

    # ── Merge: prefer ColPali when indexed pages exist ─────────
    # Use ColPali result if at least one page has been visually indexed;
    # otherwise fall through to the caption-based extracted figure.
    colpali_hit = next((p for p in colpali_pages if p.colpali_vecs), None)
    caption_hit = caption_images[0] if caption_images else None

    if colpali_hit:
        image_url = f"/api/rag/pages/{colpali_hit.id}"
        backend   = await get_backend()
        reply = (
            f"Found a matching page from **{colpali_hit.doc_filename}** "
            f"(page {colpali_hit.page_num}) using **{backend}** visual search:\n\n"
            f"*(Source: {colpali_hit.doc_filename}, p. {colpali_hit.page_num})*"
        )
        # Mention other top page hits
        others = [p for p in colpali_pages[1:4] if p.colpali_vecs]
        if others:
            reply += "\n\nAlso relevant: " + ", ".join(
                f"{p.doc_filename} p.{p.page_num}" for p in others
            )
        return reply, image_url

    if caption_hit:
        image_url = f"/api/rag/images/{caption_hit.id}"
        reply = (
            f"Found an image from **{caption_hit.doc_filename}** "
            f"(page {caption_hit.page_num}) via caption search:\n\n"
            f"*(Source: {caption_hit.doc_filename}, p. {caption_hit.page_num})*"
        )
        others = caption_images[1:4]
        if others:
            reply += "\n\nAlso available: " + ", ".join(
                f"{i.doc_filename} p.{i.page_num}" for i in others
            )
        return reply, image_url

    return (
        "No images were found in the knowledge base for this query.\n\n"
        "**Tip:** Upload a PDF — pages are automatically rendered and indexed "
        "for visual search, and embedded figures are extracted and captioned.",
        None,
    )


# ──────────────────────────────────────────────────────────
# Chat (standard / non-streaming)
# ──────────────────────────────────────────────────────────

@router.post("/chat")
async def send_chat_message(
    body: ChatMessageInput,
    request: Request,
    db: Session = Depends(get_db),
    scope: MemoryScope = Depends(get_identity),
):
    conv_id = body.conversation_id

    if not conv_id:
        conv = create_conversation(db, user_id=scope.user_id, anon_session_id=scope.anon_session_id)
        conv_id = conv.id
    elif not get_conversation(db, conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    if body.workspace_id:
        await ensure_fresh(db, body.workspace_id)

    add_message(db, conv_id, "user", body.message)
    msgs = get_messages(db, conv_id)
    history = [{"role": m.role, "content": m.content} for m in msgs]

    # AI Orchestrator — additive: decides which extra capabilities/model to
    # use for this turn. Does not replace the branching below.
    req_plan = plan_request(body.message, workspace_id=body.workspace_id, has_image=bool(body.image_base64))
    provider = _resolve_provider(body.provider_override, req_plan.preferred_task_hint)
    if not provider:
        raise HTTPException(status_code=503, detail="No AI provider available")

    image_url: Optional[str] = None

    agent_mode = body.agent_mode or "general"

    # Vision analysis only when an actual image file is attached.
    # Never trigger ColPali/OpenCLIP from text keywords alone.
    if body.image_base64:
        _log.info("[chat] VISION_ANALYSIS: image attachment present filename=%r", body.image_filename)
        reply, image_url = await _handle_image_query(body.message, db)
        system_prompt = await _build_system_prompt(body.message, db, agent_mode, scope=scope, workspace_id=body.workspace_id, plan=req_plan)
        if image_url:
            try:
                extra = await provider.chat(history, system_prompt=system_prompt, max_tokens=_CHAT_MAX_TOKENS)
                reply = reply + "\n\n" + extra
            except Exception:
                pass
        else:
            try:
                text_answer = await provider.chat(history, system_prompt=system_prompt, max_tokens=_CHAT_MAX_TOKENS)
                reply = reply + "\n\n" + text_answer
            except Exception:
                pass
    else:
        # Text-only query — knowledge base RAG + LLM; no vision model invoked
        _log.info("[chat] TEXT_CHAT: knowledge base + LLM")
        system_prompt = await _build_system_prompt(body.message, db, agent_mode, scope=scope, workspace_id=body.workspace_id, plan=req_plan)
        try:
            reply = await provider.chat(history, system_prompt=system_prompt, max_tokens=_CHAT_MAX_TOKENS)
        except Exception as exc:
            raise HTTPException(status_code=502, detail=f"Provider error: {exc}")

    add_message(db, conv_id, "assistant", reply, image_url=image_url)
    asyncio.create_task(_summarize_in_background(conv_id))
    return {
        "message": reply,
        "conversation_id": conv_id,
        "provider_used": provider.provider_name,
        "image_url": image_url,
    }


async def _run_design_pipeline(
    db: Session, user_id: str, conv_id: str, message: str, provider,
    *, design_type: Optional[str] = None, prior_workflow=None, edit: Optional[dict] = None,
) -> tuple[dict, list[dict]]:
    """Runs the Design Orchestrator for one chat turn — either a fresh
    design request (design_type set) or a follow-up edit against an
    existing DesignWorkflow (prior_workflow + edit set). Always returns a
    real `canva_design_result` payload: never silently falls through to a
    text-only reply, per the AI Tool Router's core requirement."""
    progress: list[dict] = [{"type": "stage", "stage": "preparing_content", "message": "Preparing design content..."}]

    force_new_template = False
    if prior_workflow is not None:
        edit = dict(edit or {})
        force_new_template = bool(edit.pop("new_template", False))
        needs_regen = bool(edit.pop("regenerate", False)) or bool(edit.pop("shorten", False)) or ("language" in edit)
        edit.pop("width", None)
        edit.pop("height", None)
        edit.pop("change_layout", None)
        resolved_design_type = prior_workflow.design_type
        if needs_regen or not edit:
            progress.append({"type": "stage", "stage": "generating_assets", "message": "Updating design content..."})
            spec = await generate_design_spec(provider, message, resolved_design_type, prior_spec=prior_workflow.structured_spec)
        else:
            spec = dict(prior_workflow.structured_spec or {})
        spec.update(edit)
    else:
        resolved_design_type = design_type
        progress.append({"type": "stage", "stage": "generating_assets", "message": "Generating design content..."})
        spec = await generate_design_spec(provider, message, resolved_design_type)

    progress.append({"type": "stage", "stage": "checking_templates", "message": "Checking Canva templates..."})
    progress.append({"type": "stage", "stage": "rendering", "message": "Rendering design..."})
    progress.append({"type": "stage", "stage": "creating_design", "message": "Creating Canva design..."})

    result = await design_orchestrator.run(
        db, user_id, conv_id, resolved_design_type, spec,
        prior_workflow=prior_workflow, force_new_template=force_new_template,
    )

    progress.append({"type": "stage", "stage": "completed", "message": "Completed."})

    payload = {
        "type": "canva_design_result",
        "design_type": result.design_type or resolved_design_type,
        "mode": result.mode,
        "canva_design_id": result.canva_design_id,
        "title": result.title or spec.get("title"),
        "thumbnail_url": result.thumbnail_url,
        "edit_url": result.edit_url,
        "view_url": result.view_url,
        "available_actions": result.available_actions,
        "connect_required": result.connect_required,
        "connect_url": result.connect_url,
        "error_message": result.error_message,
        "workflow_id": result.workflow_id,
    }
    return payload, progress


# ──────────────────────────────────────────────────────────
# Chat streaming (SSE)
# ──────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def stream_chat_message(
    body: ChatMessageInput,
    request: Request,
    db: Session = Depends(get_db),
    scope: MemoryScope = Depends(get_identity),
):
    """Streaming chat — returns Server-Sent Events."""
    user_id = scope.user_id
    conv_id = body.conversation_id

    if not conv_id:
        conv = create_conversation(db, user_id=scope.user_id, anon_session_id=scope.anon_session_id)
        conv_id = conv.id
    elif not get_conversation(db, conv_id):
        raise HTTPException(status_code=404, detail="Conversation not found")

    if body.workspace_id:
        await ensure_fresh(db, body.workspace_id)

    add_message(db, conv_id, "user", body.message)
    msgs = get_messages(db, conv_id)
    history = [{"role": m.role, "content": m.content} for m in msgs]

    req_id = uuid.uuid4().hex[:12].upper()

    # ── AI Chat Workspace agent branch ──────────────────────────────────────────
    # Lightweight Intent Router (responsiveness fix): a conversation keeps
    # carrying its workspace_id on every later turn once any earlier message
    # touched a workspace (see _stream_workspace_turn's link_conversation_workspace
    # below) — without the detect_workspace_task_intent() check, an unrelated
    # follow-up like "what can you do?" would still pay for the full Workspace
    # Agent pipeline (list_workspace_files, a tool-calling LLM round-trip, the
    # zero-call corrective retry) before answering. Ordinary conversation now
    # falls through to the plain chat path below unchanged; genuine file/
    # document requests (the same keyword family already used for the
    # no-workspace-yet auto-provision case just below) still get the full
    # pipeline exactly as before.
    if body.workspace_id and detect_workspace_task_intent(body.message):
        _log.info("[chat:%s] route=WORKSPACE_AGENT workspace_id=%s", req_id, body.workspace_id)
        return StreamingResponse(
            _stream_workspace_turn(db, conv_id, user_id, body.workspace_id, body.message, history, req_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # ── Document-generation intent, no workspace attached yet ──────────────────
    # create_word_document / create_excel_workbook / create_powerpoint /
    # create_pdf_report / create_csv are only ever bound to the model inside
    # the Workspace Agent tool-calling loop above — a workspace-less message
    # never reaches them and falls through to the plain provider.chat() call
    # below, where the LLM has no tool to call and can only refuse. Route
    # genuine document-generation requests into the exact same
    # _stream_workspace_turn path, auto-provisioning an empty scratch
    # workspace (the same crud.create_workspace/link_conversation_workspace
    # calls routes/workspaces.py already makes) so the request has a
    # workspace_id to run against. Every other workspace-less message is
    # unaffected.
    if not body.image_base64 and detect_document_generation_intent(body.message):
        doc_workspace_id: Optional[str] = None
        if user_id:
            conv = crud.get_conversation(db, conv_id)
            doc_workspace_id = conv.workspace_id if conv else None
            if not doc_workspace_id:
                doc_workspace_id = crud.create_workspace(db, user_id, name="Documents", conversation_id=conv_id).id
        _log.info("[chat:%s] route=WORKSPACE_AGENT(document_generation) workspace_id=%s", req_id, doc_workspace_id)
        return StreamingResponse(
            _stream_workspace_turn(db, conv_id, user_id, doc_workspace_id, body.message, history, req_id),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # AI Orchestrator — additive: decides which extra capabilities/model to
    # use for this turn. Does not replace the intent-detection routing below.
    req_plan = plan_request(body.message, workspace_id=body.workspace_id, has_image=bool(body.image_base64))
    provider = _resolve_provider(body.provider_override, req_plan.preferred_task_hint)
    if not provider:
        raise HTTPException(status_code=503, detail="No AI provider available")

    agent_mode = body.agent_mode or "general"

    # ── Intent detection ───────────────────────────────────────────────────────
    intent = detect_intent(body.message)
    canva_action = detect_canva_intent(body.message)
    _log.info("[chat:%s] intent=%s canva_action=%s model=%s query=%r",
              req_id, intent, canva_action, agent_mode, body.message[:80])

    # Pre-resolve everything outside the generator (DB access not safe inside async gen)
    gallery_payload: Optional[dict] = None
    image_answer: str = ""
    image_kb_sources: list[str] = []
    found_image_url: Optional[str] = None
    image_preamble: Optional[str] = None
    canva_payload: Optional[dict] = None
    connector_progress_events: list[dict] = []
    research_agent_payload: Optional[dict] = None
    # Phase 2B.6 — Intelligent Knowledge Router: set only when the plain
    # text-chat fallback below decided existing knowledge was insufficient
    # and either completed or timed out on a bounded live-research pass.
    knowledge_router_note: Optional[str] = None

    # ── Autonomous Research Agent — natural-language mission commands ──────────
    # "research and learn about X" / "ابحث وتعلّم..." / "stop the current
    # research" / "resume learning" / "show me the sources you learned from".
    # Routes into the exact same missions api/routes/research_agent.py and the
    # Learning Hub UI use — not a separate research system.
    if user_id and not body.image_base64:
        research_intent = detect_research_agent_intent(body.message)
        if research_intent:
            research_agent_payload = await handle_research_agent_intent(db, user_id, research_intent)
            _log.info("[chat:%s] route=RESEARCH_AGENT action=%s", req_id, research_intent["action"])

    # ── AI Tool Router: visual-design requests (Design Orchestrator) ────────────
    # Deterministic, not an LLM tool-call decision — a poster/infographic/etc.
    # request must never silently fall through to a text-only reply just
    # because the model chose not to call a tool. Takes priority over the
    # generic connector tool router and the keyword Canva fallback below.
    if user_id and not body.image_base64:
        prior_design_workflow = crud.get_latest_design_workflow(db, conv_id)
        design_edit = detect_design_edit_intent(body.message, prior_design_workflow is not None)
        new_design_type = detect_design_intent(body.message)

        # Agent Orchestrator: a single message that both requests a new design
        # AND explicitly asks to save it to Google Drive — chains design
        # generation, export, and Drive upload into one automatic run instead
        # of requiring a second manual "Save to Drive" click. Only fires for
        # brand-new design requests (not follow-up edits), so the existing
        # edit flow and plain design-only flow below are unchanged.
        if new_design_type and not design_edit and wants_drive_save(body.message):
            canva_payload, connector_progress_events, _agent_run = await agent_orchestrator_runner.run(
                db, user_id, conv_id, body.message, new_design_type, provider,
            )
            _log.info("[chat:%s] route=AGENT_ORCHESTRATOR(design+drive) design_type=%s mode=%s",
                      req_id, new_design_type, canva_payload.get("mode"))
        elif design_edit and prior_design_workflow:
            canva_payload, connector_progress_events = await _run_design_pipeline(
                db, user_id, conv_id, body.message, provider,
                prior_workflow=prior_design_workflow, edit=design_edit,
            )
            _log.info("[chat:%s] route=DESIGN_ORCHESTRATOR(edit) mode=%s", req_id, canva_payload.get("mode"))
        elif new_design_type:
            canva_payload, connector_progress_events = await _run_design_pipeline(
                db, user_id, conv_id, body.message, provider, design_type=new_design_type,
            )
            _log.info("[chat:%s] route=DESIGN_ORCHESTRATOR(new) design_type=%s mode=%s",
                      req_id, new_design_type, canva_payload.get("mode"))

    # ── Connector Tool Router — genuine LLM-driven tool calling ─────────────────
    # Regression fix: this used to be offered on every eligible turn
    # unconditionally, which meant even a plain research question paid for
    # (and could be misrouted by) a real LLM tool-decision call — the model's
    # own system prompt tells it to call a tool "even if they don't name the
    # tool explicitly", which is right for genuinely ambiguous platform
    # requests but wrong for a question with nothing to do with any
    # connected platform. detect_connector_tool_intent() is a deterministic,
    # keyword/connector-name pre-gate — the LLM tool-decision call itself
    # only happens when the message plausibly concerns a connected platform
    # (mentioned by name) or an explicit upload/download/sync/file-storage
    # action. Falls back to the keyword-based path below only when the
    # active provider doesn't support tool-calling.
    if (
        canva_payload is None and user_id and not body.image_base64 and intent != "IMAGE_SEARCH"
        and detect_connector_tool_intent(body.message)
    ):
        from api.services.connector_chat_router import run_connector_tool_loop
        canva_payload, connector_progress_events = await run_connector_tool_loop(db, user_id, history, provider)
        if canva_payload is not None:
            _log.info("[chat:%s] route=CONNECTOR_TOOL_ROUTER result_type=%s", req_id, canva_payload.get("type"))

    # ── Keyword-based Canva fallback — only when no tool was used above (either
    # the active provider lacks tool-calling, or the router found nothing to do) ──
    if canva_payload is None and canva_action and user_id:
        if canva_action == "disconnect":
            was_connected = (await canva_connector.get_connection_status(db, user_id)).connection_status == "connected"
            await canva_connector.disconnect(db, user_id)
            canva_payload = {"type": "canva_disconnected", "was_connected": was_connected}
        else:
            status = await canva_connector.get_connection_status(db, user_id)
            if status.connection_status == "connected":
                result = await connector_service.execute_action(db, user_id, "canva", "canva.list_designs", {})
                if result.success:
                    canva_payload = {"type": "canva_designs", "items": (result.data or {}).get("items", [])}
                else:
                    canva_payload = {
                        "type": "canva_error",
                        "error_code": result.error_code, "error_message": result.error_message,
                    }
            else:
                from urllib.parse import quote
                return_to = quote(f"/chat?id={conv_id}&resume_pending=1", safe="")
                canva_payload = {
                    "type": "canva_connect_required",
                    "connect_url": f"/api/connectors/canva/connect?return_to={return_to}",
                }
        _log.info("[chat:%s] route=CANVA_KEYWORD_FALLBACK action=%s result_type=%s",
                  req_id, canva_action, canva_payload.get("type") if canva_payload else None)
    elif canva_payload is None and canva_action and not user_id:
        canva_payload = {"type": "canva_error", "error_code": "AUTH_REQUIRED",
                          "error_message": "Sign in to connect and use Canva."}

    # ── Vision pipeline routing ────────────────────────────────────────────────
    # Priority: actual image attachment > gallery keyword > text-only
    # ColPali/OpenCLIP is NEVER loaded for text-only messages regardless of keywords.
    _vision_loaded = False
    _route_reason  = "text_only_message"

    if canva_payload is not None or connector_progress_events or research_agent_payload is not None:
        pass  # handled entirely in event_generator below

    elif intent == "IMAGE_SEARCH":
        # Unified image search orchestrator (gallery_service.search_images_with_
        # fallback): local Knowledge Base first — rendered pages + extracted
        # figures, keyword + optional text-embedding, synonym-broadened, no
        # ColPali/OpenCLIP — then an AUTOMATIC internet fallback when the local
        # index is thin. The web channel reuses the existing Research Engine
        # (discover_sources/web_crawl/is_safe_url/initialize_trust/
        # KnowledgeProvenance) via image_discovery.py and merges into this SAME
        # gallery_payload, rendering through the SAME gallery_results SSE event
        # / GalleryResultsCard the Knowledge Base path already uses.
        #
        # Deliberately NOT gated on user_id: an anonymous / local-developer
        # session (no user_id) must still get the web fallback when the KB has
        # nothing — only settings.image_retrieval_enabled can turn it off.
        gallery_query = extract_gallery_query(body.message)
        _route_reason  = "gallery_keyword_match"

        # The web image channels (Wikimedia + crawl) and the synonym expansion
        # are English-indexed, so a non-English (Arabic) query returns nothing.
        # Bridge it to English BEFORE searching — static domain map first, a
        # short LLM translation only if that misses (see translate_image_query).
        search_query = await translate_image_query(gallery_query, provider)
        if search_query and search_query != gallery_query:
            _log.info(
                "[chat:%s] IMAGE_SEARCH query bridged AR->EN %r -> %r",
                req_id, gallery_query, search_query,
            )
        else:
            search_query = gallery_query

        # An image request must also be UNDERSTOOD and ANSWERED — not reduced to
        # a bare image grid. But the KB-grounded explanation (RAG + graph +
        # provider LLM) and the image search (local + web crawl) are independent,
        # so they run CONCURRENTLY instead of stacking their latencies — the turn
        # takes ≈max(image, answer), not their sum. The explanation uses its own
        # DB session (a single SQLAlchemy Session is not safe for concurrent use).
        async def _resolve_images() -> dict:
            return await search_images_with_fallback(search_query, db)

        async def _resolve_answer() -> tuple[str, list[str]]:
            from api.db.base import SessionLocal
            adb = SessionLocal()
            try:
                sysp = await _build_system_prompt(
                    body.message, adb, agent_mode, scope=scope,
                    workspace_id=body.workspace_id, plan=req_plan,
                )
                # A concise explanation, not an essay — keeps the turn fast.
                ans = await provider.chat(history, system_prompt=sysp, max_tokens=_IMAGE_ANSWER_MAX_TOKENS)
                from api.services.rag_service import retrieve_chunks as _retrieve_chunks
                kb_chunks = await _retrieve_chunks(body.message, adb, top_k=3)
                srcs = list(dict.fromkeys(c.filename for c in kb_chunks if getattr(c, "filename", None)))
                return ans, srcs
            except Exception:
                _log.exception("[chat:%s] IMAGE_SEARCH explanation generation failed", req_id)
                return "", []
            finally:
                adb.close()

        gallery_payload, (image_answer, image_kb_sources) = await asyncio.gather(
            _resolve_images(), _resolve_answer(),
        )

        _log.info(
            "[chat:%s] route=GALLERY_SEARCH vision_model_loaded=No "
            "reason=%s query=%r sources_used=%s answer_chars=%d kb_sources=%d cost_saved≈$0.00",
            req_id, _route_reason, search_query, gallery_payload.get("sources_used"),
            len(image_answer or ""), len(image_kb_sources),
        )

    elif body.image_base64:
        # Actual image file attached → visual analysis with readiness guard.
        from api.services.colpali_service import get_backend_state, get_backend
        vision_state = get_backend_state()
        _route_reason = "image_attachment_present"

        if vision_state == "not_loaded":
            import asyncio as _asyncio
            _asyncio.create_task(get_backend())
            image_preamble = (
                "The visual search model is initializing in the background. "
                "Your question has been received — I'll answer using the knowledge base while the model loads.\n\n"
            )
            _log.info(
                "[chat:%s] route=VISION_ANALYSIS vision_model_loaded=No "
                "reason=model_not_yet_loaded action=background_load_triggered fallback=text",
                req_id,
            )

        elif vision_state == "loading":
            image_preamble = (
                "The visual search model is currently loading (takes ~30 s on first start). "
                "I'll answer using the knowledge base in the meantime.\n\n"
            )
            _log.info(
                "[chat:%s] route=VISION_ANALYSIS vision_model_loaded=No "
                "reason=model_still_loading fallback=text",
                req_id,
            )

        elif vision_state == "failed":
            image_preamble = (
                "The local visual search model could not be loaded (insufficient resources). "
                "I'll answer using the text knowledge base instead.\n\n"
            )
            _log.info(
                "[chat:%s] route=VISION_ANALYSIS vision_model_loaded=No "
                "reason=model_failed fallback=text",
                req_id,
            )

        else:
            # Model ready — run visual similarity search
            _vision_loaded = True
            image_reply, found_image_url = await _handle_image_query(body.message, db)
            image_preamble = image_reply
            _log.info(
                "[chat:%s] route=VISION_ANALYSIS vision_model_loaded=Yes "
                "reason=%s image_found=%s",
                req_id, _route_reason, found_image_url is not None,
            )

    else:
        # Text-only query — RAG text retrieval + LLM.
        # Never loads ColPali/OpenCLIP for any text-only message,
        # including those mentioning "image", "show", "diagram", "photo", etc.
        _log.info(
            "[chat:%s] route=TEXT_CHAT vision_model_loaded=No "
            "reason=%s cost_saved≈$0.00",
            req_id, _route_reason,
        )

        # ── Intelligent Knowledge Router (Phase 2B.6) ────────────────────────
        # Automatic fallback — no explicit "research and learn about X" needed.
        # Only reachable here: every other route above (workspace agent,
        # explicit research commands, canva/connector/design, gallery/image)
        # has already been decided and returned/short-circuited, so this can
        # never interfere with them. Gated on user_id (anonymous sessions skip
        # it, same convention as the design/research-command routes above)
        # and on the settings kill switch.
        if user_id and settings.knowledge_router_enabled:
            from api.services.knowledge_router import (
                assess_knowledge_confidence, classify_knowledge_gap, format_completed_note,
                LIVE_RESEARCH_CATEGORIES, STILL_LEARNING_NOTE,
            )
            assessment = await assess_knowledge_confidence(db, body.message)
            if assessment["confidence"] < settings.knowledge_router_confidence_threshold:
                category = classify_knowledge_gap(body.message)
                if category in LIVE_RESEARCH_CATEGORIES:
                    from api.services.research_agent.quick_research import (
                        maybe_start_chat_live_research, run_chat_quick_research,
                    )
                    started = maybe_start_chat_live_research(db, user_id, body.message, category)
                    if started:
                        mission, topic, _topic_memory = started
                        task = asyncio.create_task(
                            run_chat_quick_research(mission.id, topic.id, settings.knowledge_router_max_sources)
                        )
                        try:
                            # asyncio.shield(): a timeout here only stops US
                            # waiting — it must NOT cancel the underlying task,
                            # which keeps running and storing knowledge in the
                            # background so a later question benefits from it
                            # even though this turn couldn't wait for it.
                            await asyncio.wait_for(
                                asyncio.shield(task), timeout=settings.knowledge_router_timeout_seconds,
                            )
                            knowledge_router_note = format_completed_note(db, mission.id)
                            _log.info("[chat:%s] route=KNOWLEDGE_ROUTER category=%s result=completed", req_id, category)
                        except asyncio.TimeoutError:
                            knowledge_router_note = STILL_LEARNING_NOTE
                            _log.info("[chat:%s] route=KNOWLEDGE_ROUTER category=%s result=still_running", req_id, category)

    system_prompt = await _build_system_prompt(body.message, db, agent_mode, scope=scope, workspace_id=body.workspace_id, plan=req_plan)

    # ── Expert Reasoning Engine (Phase 2B.7) ──────────────────────────────────
    # Same scope as the Knowledge Router above: only the plain text-only
    # fallback (no workspace/canva/connector/design/research-command/gallery/
    # image route matched). A read-only context-assembly layer over the
    # existing Knowledge Graph — never a new LLM call; it only changes what
    # goes into `system_prompt` before the single existing
    # provider.stream_chat(...) call in event_generator below.
    if (
        user_id and settings.reasoning_engine_enabled
        and canva_payload is None and not connector_progress_events and research_agent_payload is None
        and not gallery_payload and not body.image_base64
    ):
        from api.services.research_brain.reasoning_engine import (
            classify_reasoning_intent, build_reasoning_context, format_reasoning_context, REASONING_RULES,
        )
        reasoning_intent = classify_reasoning_intent(body.message)
        if reasoning_intent:
            reasoning_context = build_reasoning_context(db, body.message, reasoning_intent)
            if reasoning_context:
                system_prompt = (
                    REASONING_RULES + "\n\n" + format_reasoning_context(db, reasoning_context)
                    + "\n\n---\n\n" + system_prompt
                )
                _log.info("[chat:%s] route=REASONING_ENGINE intent=%s", req_id, reasoning_intent)

    async def event_generator() -> AsyncGenerator[str, None]:
        full_reply = ""
        saved_image_url = found_image_url
        t_start = time.monotonic()
        chunk_count = 0
        message_saved = False
        finish_reason = "stop"

        try:
            yield f"data: {json.dumps({'type': 'start', 'conversation_id': conv_id, 'provider': provider.provider_name, 'model': agent_mode, 'request_id': req_id})}\n\n"
            yield f"data: {json.dumps({'type': 'stage', 'stage': 'using_provider', 'message': f'Using {provider.provider_name}...'})}\n\n"

            # ── Connector tool-router / Canva chat intent path ──────────────────
            if canva_payload is not None or connector_progress_events:
                # Progress events first — "Thinking..." already happened (the tool
                # decision call itself), so this starts at "Using X Connector...".
                for event in connector_progress_events:
                    yield f"data: {json.dumps(event)}\n\n"

                if canva_payload is None:
                    # A tool ran but has no dedicated result card (e.g. get_profile).
                    summary = "Done."
                elif canva_payload["type"] == "canva_connect_required":
                    summary = "Connect your Canva account to perform this action."
                elif canva_payload["type"] == "canva_disconnected":
                    summary = (
                        "Your Canva account has been disconnected."
                        if canva_payload.get("was_connected")
                        else "Canva was not connected, so there was nothing to disconnect."
                    )
                elif canva_payload["type"] == "canva_error":
                    summary = f"Canva request failed: {canva_payload.get('error_message') or canva_payload.get('error_code')}"
                elif canva_payload["type"] == "canva_design_result":
                    title = canva_payload.get("title") or "Untitled design"
                    if canva_payload.get("canva_design_id"):
                        summary = f"I've created a new **{canva_payload.get('design_type', 'design')}**: *{title}*. Preview below."
                        if canva_payload.get("connect_required"):
                            summary += "\n\n(Reconnect Canva for full editing there — showing what's available now.)"
                    else:
                        summary = f"I've rendered a **{canva_payload.get('design_type', 'design')}** preview: *{title}*."
                        if canva_payload.get("connect_required"):
                            summary += " Connect your Canva account to save it there, export it, or keep editing it in Canva."
                    if canva_payload.get("error_message") and not canva_payload.get("canva_design_id"):
                        summary += f"\n\n_{canva_payload['error_message']}_"
                    drive_file = canva_payload.get("drive_file")
                    if drive_file and drive_file.get("web_view_link"):
                        summary += f"\n\nSaved to Google Drive: [{drive_file.get('name')}]({drive_file['web_view_link']})"
                else:  # canva_designs
                    items = canva_payload.get("items", [])
                    if items:
                        summary = f"Found **{len(items)}** Canva design{'s' if len(items) != 1 else ''}:\n\n"
                        for design in items:
                            title = design.get("title") or "Untitled design"
                            edit_url = (design.get("urls") or {}).get("edit_url")
                            summary += f"- **{title}**" + (f" — [Open in Canva]({edit_url})" if edit_url else "") + "\n"
                    else:
                        summary = "No designs were found in your Canva account."

                if canva_payload is not None:
                    yield f"data: {json.dumps({'type': 'canva_results', 'payload': canva_payload})}\n\n"

                full_reply = summary
                for word in summary.split(" "):
                    chunk_count += 1
                    yield f"data: {json.dumps({'type': 'chunk', 'chunk': word + ' '})}\n\n"

                content_to_save = "__CANVA__:" + json.dumps(canva_payload) if canva_payload is not None else summary
                add_message(db, conv_id, "assistant", content_to_save, image_url=None)
                message_saved = True
                asyncio.create_task(_summarize_in_background(conv_id))
                duration = round(time.monotonic() - t_start, 3)
                _log.info(
                    "[chat:%s] done intent=CONNECTOR type=%s chunks=%d duration=%.3fs saved=%s",
                    req_id, canva_payload["type"] if canva_payload else "no_card", chunk_count, duration, message_saved,
                )
                yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'request_id': req_id, 'finish_reason': finish_reason, 'duration_s': duration})}\n\n"
                return

            # ── Autonomous Research Agent path ──────────────────────────────────
            if research_agent_payload is not None:
                payload = research_agent_payload
                mission = payload.get("mission") or {}
                if payload["type"] == "research_mission_started":
                    limits = mission.get("limits") or {}
                    summary = (
                        f"Started a research mission: **{(mission.get('mission_text') or '')[:200]}**\n\n"
                        f"- Mode: {mission.get('mode')}\n"
                        f"- Free Mode: {'ON (Estimated Cost = $0.00)' if mission.get('free_mode') else 'OFF'}\n"
                        f"- Limits: {limits.get('max_pages')} pages / {limits.get('max_files')} files / "
                        f"{limits.get('max_storage_mb')} MB\n\n"
                        "I'll discover, crawl, and learn from authoritative sources in the background. "
                        "Say \"show me the sources\" any time, or \"stop the current research job\" to cancel."
                    )
                elif payload["type"] == "research_mission_paused":
                    summary = "Research mission paused."
                elif payload["type"] == "research_mission_resumed":
                    summary = "Research mission resumed."
                elif payload["type"] == "research_mission_stopped":
                    summary = "Research mission stopped."
                elif payload["type"] == "research_sources":
                    sources = payload.get("sources", [])
                    if sources:
                        summary = f"Sources learned from so far ({len(sources)}):\n\n"
                        for s in sources:
                            summary += (
                                f"- **{s.get('title') or s.get('url')}** — {s.get('domain')} · "
                                f"quality: {s.get('quality_label')} ({s.get('quality_score')}/100)\n"
                            )
                    else:
                        summary = "No sources have been learned from yet for the current mission."
                elif payload["type"] == "research_curiosity_questions":
                    questions = payload.get("questions", [])
                    if questions:
                        summary = f"Questions I discovered on my own ({len(questions)}):\n\n"
                        for q in questions:
                            summary += (
                                f"- **{q.get('question_text')}** — {q.get('category')}, "
                                f"status: {q.get('status')} (priority {q.get('priority_score')})\n"
                            )
                    else:
                        summary = "I haven't discovered any follow-up questions yet — they're generated after a mission completes."
                elif payload["type"] == "research_conflicts":
                    conflicts = payload.get("conflicts", [])
                    if conflicts:
                        summary = f"Open conflicts in this mission's knowledge ({len(conflicts)}):\n\n"
                        for c in conflicts:
                            review = " — needs human review" if c.get("human_review_required") else ""
                            summary += (
                                f"- **{c.get('conflict_type')}** ({c.get('severity')}{review}): "
                                f"\"{c.get('claim_a')}\" vs \"{c.get('claim_b')}\"\n"
                            )
                    else:
                        summary = "No open conflicts in this mission's knowledge right now."
                elif payload["type"] == "research_source_trust":
                    s = payload.get("source") or {}
                    summary = _format_source_trust_block(s)
                elif payload["type"] == "research_source_trust_history":
                    s = payload.get("source") or {}
                    # Named to avoid shadowing the enclosing `history` (chat
                    # conversation history, used later for provider.stream_chat) —
                    # Python scopes `history` to this whole generator function if
                    # reassigned anywhere in it, regardless of which branch runs.
                    trust_changes = payload.get("history", [])
                    summary = _format_source_trust_block(s) + "\n\n"
                    if trust_changes:
                        summary += f"Trust history ({len(trust_changes)} change(s)):\n\n"
                        for h in trust_changes:
                            summary += (
                                f"- {h.get('created_at', '')[:19]} — **{h.get('reason_code')}** "
                                f"({h.get('delta'):+.1f}): {h.get('reason_description')}\n"
                            )
                    else:
                        summary += "No trust changes recorded yet for this source."
                elif payload["type"] == "research_source_reviewed":
                    s = payload.get("source") or {}
                    summary = f"Rated **{s.get('title') or s.get('url')}**.\n\n" + _format_source_trust_block(s)
                elif payload["type"] == "research_source_review_reset":
                    s = payload.get("source") or {}
                    summary = f"Your rating for **{s.get('title') or s.get('url')}** has been reset.\n\n" + _format_source_trust_block(s)
                elif payload["type"] == "research_strongest_sources":
                    sources = payload.get("sources", [])
                    topic = payload.get("topic") or "this mission"
                    if sources:
                        summary = f"Strongest sources about {topic}:\n\n"
                        for s in sources:
                            summary += (
                                f"- **{s.get('title') or s.get('url')}** — {s.get('domain')} · "
                                f"effective trust {s.get('effective_trust_score')}/100 ({s.get('trust_status')})\n"
                            )
                    else:
                        summary = f"No sources found for {topic} yet."
                elif payload["type"] == "research_sources_needing_verification":
                    sources = payload.get("sources", [])
                    if sources:
                        summary = f"Sources needing independent verification ({len(sources)}) — every fact they support relies on this source family alone:\n\n"
                        for s in sources:
                            summary += f"- **{s.get('title') or s.get('url')}** — {s.get('domain')} (effective trust {s.get('effective_trust_score')}/100)\n"
                    else:
                        summary = "Every fact in this mission currently has independent corroboration."
                elif payload["type"] == "research_single_source_check":
                    total = payload.get("total_facts", 0)
                    single = payload.get("single_source_facts", 0)
                    if total == 0:
                        summary = "No facts recorded yet for this mission."
                    else:
                        summary = (
                            f"{single} of {total} fact(s) in this mission currently rest on a single source family "
                            f"(no independent corroboration yet)."
                        )
                elif payload["type"] == "research_rejected_sources":
                    sources = payload.get("sources", [])
                    if sources:
                        summary = f"Rejected sources ({len(sources)}):\n\n"
                        for s in sources:
                            summary += f"- **{s.get('title') or s.get('url')}** — {s.get('domain')}\n"
                    else:
                        summary = "No rejected sources for this mission."
                elif payload["type"] == "research_independent_source_search":
                    questions = payload.get("questions", [])
                    if questions:
                        summary = "I've queued research question(s) to find independent corroboration:\n\n"
                        for q in questions:
                            summary += f"- {q.get('question_text')} — {q.get('reason')}\n"
                    else:
                        summary = "Every current fact already has independent corroboration — nothing new to verify right now."
                elif payload["type"] == "research_outdated_topics":
                    topics = payload.get("topics", [])
                    if topics:
                        summary = f"Outdated/aging topics ({len(topics)}):\n\n"
                        for t in topics:
                            summary += f"- **{t.get('topic_key')}** ({t.get('content_category')}) — {t.get('freshness_status')}, last update: {t.get('last_update') or 'never'}\n"
                    else:
                        summary = "No topics are currently outdated or aging."
                elif payload["type"] == "research_topic_last_updated":
                    summary = _format_topic_memory_block(payload.get("topic_memory") or {})
                elif payload["type"] == "research_topic_freshness":
                    m = payload.get("topic_memory") or {}
                    summary = _format_topic_memory_block(m)
                elif payload["type"] == "research_topic_refresh_started":
                    m = payload.get("topic_memory") or {}
                    summary = (
                        f"Started a Knowledge Refresh for **{m.get('topic_key')}** "
                        f"(was {m.get('freshness_status')}) — I'll re-check known sources for changes "
                        "and search for anything new.\n\n" + _format_topic_memory_block(m)
                    )
                elif payload["type"] == "research_topic_whats_changed":
                    m = payload.get("topic_memory") or {}
                    summary = (
                        f"Since research began on **{m.get('topic_key')}** "
                        f"(last research: {m.get('last_research') or 'never'}):\n\n"
                        f"- New facts: {m.get('new_facts_count')}\n"
                        f"- Updated facts: {m.get('updated_facts_count')}\n"
                        f"- Conflicts found: {m.get('conflicts_found_count')}\n"
                    )
                elif payload["type"] == "research_what_learned":
                    m = payload.get("mission") or {}
                    summary = (
                        f"So far on **{(m.get('mission_text') or '')[:200]}**:\n\n"
                        f"- Topics covered: {payload.get('topics_covered')}/{payload.get('topics_total')}\n"
                        f"- Sources learned from: {payload.get('sources_count')}\n"
                        f"- Facts in the knowledge graph: {payload.get('facts_count')}\n"
                        f"- Coverage rounds completed: {m.get('coverage_rounds_completed')}/{m.get('max_coverage_rounds')}"
                    )
                elif payload["type"] == "research_what_unknown":
                    low = payload.get("low_coverage_topics", [])
                    questions = payload.get("open_questions", [])
                    if low:
                        summary = f"Still incomplete ({len(low)} topic(s) below target coverage):\n\n"
                        for t in low:
                            summary += f"- **{t.get('label')}** — {t.get('coverage_pct')}%\n"
                    else:
                        summary = "No topics are currently below the coverage target.\n\n"
                    if questions:
                        summary += f"\nOpen follow-up questions ({len(questions)}):\n\n"
                        for q in questions:
                            summary += f"- {q.get('question_text')}\n"
                elif payload["type"] == "research_scientific_alerts":
                    alerts = payload.get("alerts", [])
                    label = payload.get("query_label", "recent discoveries")
                    if alerts:
                        summary = f"Here's what I found for \"{label}\" ({len(alerts)}):\n\n"
                        for a in alerts:
                            summary += f"- **[{a.get('alert_type')}] {a.get('title')}**\n  {a.get('summary')}\n"
                    else:
                        summary = f"Nothing to report yet for \"{label}\" — I'll keep learning in the background and let you know when something worth mentioning turns up."
                elif payload["type"] == "research_knowledge_health":
                    view = payload.get("view")
                    if view == "overview":
                        overall = payload.get("overall")
                        if overall:
                            summary = (
                                f"Overall knowledge health: **{overall.get('classification')}** "
                                f"({overall.get('score')}/100).\n\n"
                            )
                        else:
                            summary = "I haven't run a knowledge health audit yet — it runs periodically in the background.\n\n"
                        actions = payload.get("recommended_actions") or []
                        if actions:
                            summary += "Top recommendations:\n\n" + "\n".join(f"- {a}" for a in actions)
                    elif view in ("weakest_topics", "dangerous_conflicts"):
                        snapshots = payload.get("snapshots", [])
                        if snapshots:
                            summary = f"{len(snapshots)} area(s) needing attention:\n\n"
                            for s in snapshots:
                                summary += f"- **{s.get('scope_label')}** — {s.get('classification')} ({s.get('score')}/100)\n"
                        else:
                            summary = "Nothing at that severity right now."
                        conflicts = payload.get("conflicts") or []
                        if conflicts:
                            summary += f"\nOpen high-severity conflicts ({len(conflicts)}):\n\n"
                            for c in conflicts:
                                summary += f"- **{c.get('conflict_type')}** ({c.get('severity')}): \"{c.get('claim_a')}\" vs \"{c.get('claim_b')}\"\n"
                    elif view == "learn_next":
                        actions = payload.get("recommended_actions") or []
                        if actions:
                            summary = "What I'd recommend learning next:\n\n" + "\n".join(f"- {a}" for a in actions)
                        else:
                            summary = "No specific gaps stand out right now — knowledge health looks stable."
                    else:
                        summary = "Done."
                else:
                    summary = payload.get("message", "Done.")

                yield f"data: {json.dumps({'type': 'research_agent_results', 'payload': research_agent_payload})}\n\n"

                full_reply = summary
                for word in summary.split(" "):
                    chunk_count += 1
                    yield f"data: {json.dumps({'type': 'chunk', 'chunk': word + ' '})}\n\n"

                content_to_save = "__RESEARCH_AGENT__:" + json.dumps(research_agent_payload)
                add_message(db, conv_id, "assistant", content_to_save, image_url=None)
                message_saved = True
                asyncio.create_task(_summarize_in_background(conv_id))
                duration = round(time.monotonic() - t_start, 3)
                _log.info(
                    "[chat:%s] done intent=RESEARCH_AGENT type=%s chunks=%d duration=%.3fs saved=%s",
                    req_id, research_agent_payload["type"], chunk_count, duration, message_saved,
                )
                yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'request_id': req_id, 'finish_reason': finish_reason, 'duration_s': duration})}\n\n"
                return

            # ── IMAGE_SEARCH path: KB-grounded answer + gallery results ────────
            if gallery_payload is not None:
                images = gallery_payload.get("images", [])
                q = gallery_payload.get("query", "")
                srcs = gallery_payload.get("sources_used", {}) or {}

                # 1. Stream the Knowledge-Base-grounded explanation first, so the
                #    user gets a real, understood answer — not just thumbnails.
                if image_answer:
                    full_reply = image_answer.strip() + "\n\n"
                    for word in full_reply.split(" "):
                        chunk_count += 1
                        yield f"data: {json.dumps({'type': 'chunk', 'chunk': word + ' '})}\n\n"

                # 2. Then the image grid card (local + web, merged & de-duped).
                yield f"data: {json.dumps({'type': 'gallery_results', 'payload': gallery_payload})}\n\n"

                # 3. Then a compact provenance line: what images were shown and
                #    which sources (KB docs / local index / web) backed the turn.
                if images:
                    where = " · ".join(
                        p for p in [
                            f"Local {srcs['local']}" if srcs.get("local") else None,
                            f"Web {srcs['web']}" if srcs.get("web") else None,
                        ] if p
                    )
                    tail = f"\n\n**{len(images)} image{'s' if len(images) != 1 else ''}**"
                    tail += f" for _{q}_" if q else ""
                    tail += f" ({where})" if where else ""
                    tail += ".\n"
                else:
                    tail = (
                        ("\n\n" if image_answer else "")
                        + "_No matching image was found in the local Knowledge Base or on the web"
                        + (f" for **{q}**" if q else "")
                        + " — indexing runs automatically on upload, so newly added documents "
                        "appear here without a manual reindex._\n"
                    )
                if image_kb_sources:
                    tail += "\n**Knowledge Base sources:** " + ", ".join(image_kb_sources[:5]) + "\n"

                full_reply = (full_reply or "") + tail
                for word in tail.split(" "):
                    chunk_count += 1
                    yield f"data: {json.dumps({'type': 'chunk', 'chunk': word + ' '})}\n\n"

                # Persist the explanation + provenance line BEFORE the gallery
                # marker so the saved message keeps its real answer (the frontend
                # renders text-before-marker above the card, not just the grid).
                persisted_text = (full_reply or "").strip()
                content_to_save = (persisted_text + "\n\n" if persisted_text else "") + "__GALLERY__:" + json.dumps(gallery_payload)
                add_message(db, conv_id, "assistant", content_to_save, image_url=None)
                message_saved = True
                asyncio.create_task(_summarize_in_background(conv_id))
                duration = round(time.monotonic() - t_start, 3)
                _log.info(
                    "[chat:%s] done intent=IMAGE_SEARCH chunks=%d duration=%.3fs finish_reason=%s saved=%s",
                    req_id, chunk_count, duration, finish_reason, message_saved,
                )
                yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'request_id': req_id, 'finish_reason': finish_reason, 'duration_s': duration})}\n\n"
                return

            # ── ColPali / caption image path ───────────────────────────────────
            if saved_image_url:
                yield f"data: {json.dumps({'type': 'image', 'image_url': saved_image_url})}\n\n"

            if image_preamble:
                for word in image_preamble.split(" "):
                    token = word + " "
                    full_reply += token
                    chunk_count += 1
                    yield f"data: {json.dumps({'type': 'chunk', 'chunk': token})}\n\n"
                full_reply += "\n\n"
                yield f"data: {json.dumps({'type': 'chunk', 'chunk': chr(10) + chr(10)})}\n\n"
                async for chunk in _leak_guarded_stream_chat(provider, history, system_prompt, _CHAT_MAX_TOKENS):
                    full_reply += chunk
                    chunk_count += 1
                    yield f"data: {json.dumps({'type': 'chunk', 'chunk': chunk})}\n\n"
            else:
                # Regular QA / general chat
                async for chunk in _leak_guarded_stream_chat(provider, history, system_prompt, _CHAT_MAX_TOKENS):
                    full_reply += chunk
                    chunk_count += 1
                    yield f"data: {json.dumps({'type': 'chunk', 'chunk': chunk})}\n\n"

                # Phase 2B.6 — Intelligent Knowledge Router trailer, only ever
                # set on this exact plain-text path (see the else: branch
                # above where knowledge_router_note is computed).
                if knowledge_router_note:
                    full_reply += knowledge_router_note
                    for word in knowledge_router_note.split(" "):
                        chunk_count += 1
                        yield f"data: {json.dumps({'type': 'chunk', 'chunk': word + ' '})}\n\n"

            # ── Save BEFORE emitting done so the message persists even if the
            # ── client disconnects immediately after receiving the last chunk.
            add_message(db, conv_id, "assistant", full_reply.strip(), image_url=saved_image_url)
            message_saved = True
            asyncio.create_task(_summarize_in_background(conv_id))

            duration = round(time.monotonic() - t_start, 3)

            # ── Track usage for Cost Dashboard (token estimates from char counts) ──
            try:
                prompt_chars = sum(len(m.get("content", "")) for m in history)
                if system_prompt:
                    prompt_chars += len(system_prompt)
                prompt_est = max(1, prompt_chars // 4)
                completion_est = max(1, len(full_reply) // 4)
                # gpt-4o default pricing: $5/M in, $15/M out
                _cost_usd = (prompt_est * 5.0 + completion_est * 15.0) / 1_000_000
                _model_name = getattr(provider, "model_name", None) or agent_mode
                _usage_row = ChatUsage(
                    request_id=req_id,
                    conversation_id=conv_id,
                    user_id=user_id,
                    model=_model_name,
                    agent_mode=agent_mode,
                    intent=intent,
                    prompt_tokens=prompt_est,
                    completion_tokens=completion_est,
                    est_cost_usd=_cost_usd,
                    rag_chunks_used=0,
                    duration_secs=duration,
                    finish_reason=finish_reason,
                )
                db.add(_usage_row)
                db.commit()
            except Exception as _ue:
                _log.warning("[chat:%s] ChatUsage save failed: %s", req_id, _ue)
            else:
                _cost_usd = locals().get("_cost_usd", 0.0)

            _log.info(
                "[chat:%s] done intent=%s agent=%s chunks=%d chars=%d "
                "duration=%.3fs finish_reason=%s saved=%s "
                "vision_model_loaded=%s cost_est=$%.6f",
                req_id, intent, agent_mode, chunk_count, len(full_reply),
                duration, finish_reason, message_saved,
                "Yes" if _vision_loaded else "No",
                locals().get("_cost_usd", 0.0),
            )
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conv_id, 'request_id': req_id, 'model': agent_mode, 'finish_reason': finish_reason, 'duration_s': duration, 'completion_status': 'complete'})}\n\n"

        except Exception as exc:
            duration = round(time.monotonic() - t_start, 3)
            disconnect_reason = type(exc).__name__
            _log.error(
                "[chat:%s] error intent=%s agent=%s chunks=%d duration=%.3fs saved=%s reason=%s: %s",
                req_id, intent, agent_mode, chunk_count, duration, message_saved, disconnect_reason, exc,
                exc_info=True,
            )
            # If we already saved the message don't report an error to the client —
            # the frontend can detect content was received and reload the conversation.
            if not message_saved:
                yield f"data: {json.dumps({'type': 'error', 'error': str(exc), 'request_id': req_id})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ──────────────────────────────────────────────────────────
# Global AI Brain: durable memory (pin / list / forget)
#
# Persistent memory is authenticated-only (require_auth) — anonymous
# sessions get isolated conversations (see MemoryScope) but never durable
# cross-session memory.
# ──────────────────────────────────────────────────────────

class PinMemoryInput(BaseModel):
    conversation_id: str
    message_id: str
    module: str = "general"
    note: Optional[str] = None
    # "pinned" (default, unchanged from Phase 1) | "solution" (Learning Engine)
    kind: str = "pinned"


@router.post("/memory/pin", status_code=201)
async def pin_memory_endpoint(
    body: PinMemoryInput,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    scope = MemoryScope(user_id=user["id"], anon_session_id=None, is_persistent=True)
    item = await memory_service.pin_message(
        db, scope, body.conversation_id, body.message_id, module=body.module, note=body.note, kind=body.kind,
    )
    if not item:
        raise HTTPException(status_code=404, detail="Message not found in that conversation")
    return crud.memory_item_to_dict(item)


@router.get("/memory")
def list_memory_endpoint(
    module: Optional[str] = None,
    kind: Optional[str] = None,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    items = crud.list_memory_items(db, user["id"], module=module, kind=kind)
    return [crud.memory_item_to_dict(i) for i in items]


@router.delete("/memory/{memory_id}", status_code=204)
def delete_memory_endpoint(
    memory_id: str,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    if not crud.delete_memory_item(db, memory_id, user["id"]):
        raise HTTPException(status_code=404, detail="Memory item not found")
