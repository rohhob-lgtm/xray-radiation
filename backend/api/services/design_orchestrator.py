"""
Design Orchestrator — decides which of the two real production modes
handles a visual-design chat request, executes it against the live Canva
(and, for the local-only degrade, no external) API, and persists a
DesignWorkflow row so follow-up edits act on the same design.

Modes, in priority order:
  1. autofill_brand_template — a compatible (non-empty-dataset) Canva brand
     template exists AND the account's plan actually has the "autofill" +
     "brand_template" capabilities (both are Enterprise/Pro-gated — this is
     checked against the real canva.get_user_capabilities response, never
     assumed).
  2. render_and_import — no compatible template: build a single-canvas
     PPTX locally (real text boxes, not flattened pixels) and import it via
     Canva's Design Import API, which reconstructs it as an editable design.
  3. render_only — import unavailable/failed: render a PNG locally and
     create a Canva design seeded with it as an asset (still a real Canva
     design + real preview, just not editable text).
  4. local_render_only — Canva isn't connected/reachable at all, or every
     Canva attempt above failed: the PNG is still rendered and shown
     (embedded as a data: URL — no Canva object exists). This is what
     satisfies "internal rendering still succeeds when Canva is
     unavailable" without ever pretending a Canva design was created.

Each mode's Canva calls go through connector_service.execute_action, so
scope/connection enforcement, rate limiting, and audit logging all still
apply exactly as they do for every other connector action in this app.
"""
from __future__ import annotations

import base64
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.db import crud
from api.services.connectors.providers.canva.connector import canva_connector
from api.services.connectors.service import connector_service
from api.utils.design_pptx_builder import render_design_pptx
from api.utils.design_renderer import render_design
from api.utils.design_specs import resolve_dimensions

log = logging.getLogger(__name__)

_IMPORT_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"

# What's shown for each mode once a design genuinely exists — never
# includes an action whose backend path isn't real and callable.
_BASE_ACTIONS_WITH_CANVA_DESIGN = ("open_in_canva", "export_png", "export_pdf", "save_to_drive", "regenerate", "edit_content")
_LOCAL_ONLY_ACTIONS = ("download_png", "regenerate", "edit_content")


@dataclass
class ModeDecision:
    mode: str  # autofill_brand_template | render_and_import | render_only | unsupported
    reason: str
    templates: list[dict] = field(default_factory=list)


@dataclass
class DesignResult:
    success: bool
    mode: str
    design_type: str
    workflow_id: Optional[str] = None
    canva_design_id: Optional[str] = None
    canva_brand_template_id: Optional[str] = None
    title: Optional[str] = None
    thumbnail_url: Optional[str] = None
    edit_url: Optional[str] = None
    view_url: Optional[str] = None
    available_actions: list[str] = field(default_factory=list)
    error_message: Optional[str] = None
    connect_required: bool = False
    connect_url: Optional[str] = None
    candidate_template_count: int = 0


class DesignOrchestrator:
    async def plan(self, db: Session, user_id: str) -> ModeDecision:
        """Read-only — decides which mode to attempt first without executing anything."""
        status = await canva_connector.get_connection_status(db, user_id)
        if status.connection_status != "connected":
            return ModeDecision(mode="unsupported", reason="canva_not_connected")

        cap_result = await connector_service.execute_action(db, user_id, "canva", "canva.get_user_capabilities", {})
        capabilities = (cap_result.data or {}).get("capabilities", []) if cap_result.success else []
        if "autofill" not in capabilities or "brand_template" not in capabilities:
            return ModeDecision(mode="render_and_import", reason="autofill_capability_not_on_plan")

        templates_result = await connector_service.execute_action(
            db, user_id, "canva", "canva.list_brand_templates", {"dataset": "non_empty", "limit": 25},
        )
        if templates_result.success:
            items = (templates_result.data or {}).get("items", [])
            if items:
                return ModeDecision(mode="autofill_brand_template", reason="compatible_template_found", templates=items)

        return ModeDecision(mode="render_and_import", reason="no_compatible_autofill_template")

    async def run(
        self, db: Session, user_id: str, conversation_id: str, design_type: str, spec: dict[str, Any],
        prior_workflow: Optional[Any] = None, force_new_template: bool = False,
    ) -> DesignResult:
        decision = await self.plan(db, user_id)

        if decision.mode == "unsupported":
            local = self._run_local_only(spec, design_type)
            local.connect_required = True
            local.connect_url = "/api/connectors/canva/connect"
            local.error_message = "Canva isn't connected — showing a locally rendered preview instead."
            self._persist(db, user_id, conversation_id, prior_workflow, local, spec)
            return local

        if decision.mode == "autofill_brand_template":
            result = await self._run_autofill(db, user_id, spec, decision.templates, prior_workflow, force_new_template)
            if result.success:
                self._persist(db, user_id, conversation_id, prior_workflow, result, spec)
                return result
            log.info("Autofill mode failed (%s) — falling back to render_and_import", result.error_message)

        result = await self._run_render_and_import(db, user_id, spec, design_type)
        if result.success:
            self._persist(db, user_id, conversation_id, prior_workflow, result, spec)
            return result
        log.info("render_and_import failed (%s) — falling back to render_only", result.error_message)

        result = await self._run_render_only(db, user_id, spec, design_type)
        if result.success:
            self._persist(db, user_id, conversation_id, prior_workflow, result, spec)
            return result
        log.info("render_only failed (%s) — falling back to local_render_only", result.error_message)

        local = self._run_local_only(spec, design_type)
        local.error_message = "Canva is connected but couldn't complete this design — showing a locally rendered preview instead."
        self._persist(db, user_id, conversation_id, prior_workflow, local, spec)
        return local

    # ── Mode 1: Autofill ────────────────────────────────────────────────────

    async def _run_autofill(
        self, db: Session, user_id: str, spec: dict, templates: list[dict],
        prior_workflow: Optional[Any], force_new_template: bool,
    ) -> DesignResult:
        template_id = None
        if prior_workflow and prior_workflow.canva_brand_template_id and not force_new_template:
            template_id = prior_workflow.canva_brand_template_id
        if not template_id or force_new_template:
            candidates = [t for t in templates if t.get("id") != (prior_workflow.canva_brand_template_id if prior_workflow else None)]
            pick_from = candidates or templates
            if not pick_from:
                return DesignResult(success=False, mode="autofill_brand_template", design_type="",
                                     error_message="No compatible brand template available")
            template_id = pick_from[0]["id"]

        dataset_result = await connector_service.execute_action(
            db, user_id, "canva", "canva.get_brand_template_dataset", {"brand_template_id": template_id},
        )
        if not dataset_result.success:
            return DesignResult(success=False, mode="autofill_brand_template", design_type="",
                                 error_message=dataset_result.error_message or dataset_result.error_code)

        dataset = (dataset_result.data or {}).get("dataset", {})
        data = _map_spec_to_dataset_fields(spec, dataset)
        if not data:
            return DesignResult(success=False, mode="autofill_brand_template", design_type="",
                                 error_message="Template has no text fields to autofill")

        job_result = await connector_service.execute_action(
            db, user_id, "canva", "canva.create_design_autofill_job",
            {"brand_template_id": template_id, "data": data, "title": spec.get("title")},
        )
        if not job_result.success:
            return DesignResult(success=False, mode="autofill_brand_template", design_type="",
                                 error_message=job_result.error_message or job_result.error_code)

        job = job_result.data or {}
        if job.get("status") != "success" or not job.get("design"):
            return DesignResult(success=False, mode="autofill_brand_template", design_type="",
                                 error_message=f"Autofill job status: {job.get('status', 'unknown')}")

        design = job["design"]
        return DesignResult(
            success=True, mode="autofill_brand_template", design_type="", canva_design_id=design.get("id"),
            canva_brand_template_id=template_id, title=design.get("title"),
            thumbnail_url=(design.get("thumbnail") or {}).get("url"),
            edit_url=(design.get("urls") or {}).get("edit_url"), view_url=(design.get("urls") or {}).get("view_url"),
            available_actions=list(_BASE_ACTIONS_WITH_CANVA_DESIGN) + (["change_template"] if len(templates) > 1 else []),
            candidate_template_count=len(templates),
        )

    # ── Mode 2a: Internal render + Canva import ─────────────────────────────

    async def _run_render_and_import(self, db: Session, user_id: str, spec: dict, design_type: str) -> DesignResult:
        pptx_bytes = render_design_pptx(spec, design_type)
        title = (spec.get("title") or "Design")[:50]
        job_result = await connector_service.execute_action(
            db, user_id, "canva", "canva.import_design",
            {"content_bytes_hex": pptx_bytes.hex(), "title": title, "mime_type": _IMPORT_MIME},
        )
        if not job_result.success:
            return DesignResult(success=False, mode="render_and_import", design_type=design_type,
                                 error_message=job_result.error_message or job_result.error_code)
        job = job_result.data or {}
        if job.get("status") != "success" or not job.get("design"):
            return DesignResult(success=False, mode="render_and_import", design_type=design_type,
                                 error_message=f"Import job status: {job.get('status', 'unknown')}")
        design = job["design"]
        return DesignResult(
            success=True, mode="render_and_import", design_type=design_type, canva_design_id=design.get("id"),
            title=design.get("title"), thumbnail_url=(design.get("thumbnail") or {}).get("url"),
            edit_url=(design.get("urls") or {}).get("edit_url"), view_url=(design.get("urls") or {}).get("view_url"),
            available_actions=list(_BASE_ACTIONS_WITH_CANVA_DESIGN),
        )

    # ── Mode 2b: Internal render (PNG) seeded into a new Canva design ──────

    async def _run_render_only(self, db: Session, user_id: str, spec: dict, design_type: str) -> DesignResult:
        png_bytes = render_design(spec, design_type)
        width, height, _ = resolve_dimensions(design_type)
        title = (spec.get("title") or "Design")[:50]
        result = await connector_service.execute_action(
            db, user_id, "canva", "canva.create_design",
            {"width": width, "height": height, "content_bytes_hex": png_bytes.hex(), "title": title},
        )
        if not result.success:
            return DesignResult(success=False, mode="render_only", design_type=design_type,
                                 error_message=result.error_message or result.error_code)
        design = (result.data or {}).get("design", {})
        return DesignResult(
            success=True, mode="render_only", design_type=design_type, canva_design_id=design.get("id"),
            title=design.get("title"), thumbnail_url=(design.get("thumbnail") or {}).get("url"),
            edit_url=(design.get("urls") or {}).get("edit_url"), view_url=(design.get("urls") or {}).get("view_url"),
            available_actions=list(_BASE_ACTIONS_WITH_CANVA_DESIGN) + ["download_png"],
        )

    # ── Mode 4: purely local, no Canva object at all ────────────────────────

    def _run_local_only(self, spec: dict, design_type: str) -> DesignResult:
        png_bytes = render_design(spec, design_type)
        data_url = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('ascii')}"
        return DesignResult(
            success=True, mode="local_render_only", design_type=design_type, title=spec.get("title"),
            thumbnail_url=data_url, available_actions=list(_LOCAL_ONLY_ACTIONS),
        )

    # ── Persistence ──────────────────────────────────────────────────────────

    def _persist(
        self, db: Session, user_id: str, conversation_id: str,
        prior_workflow: Optional[Any], result: DesignResult, spec: dict,
    ) -> None:
        if prior_workflow is not None:
            updated = crud.update_design_workflow(
                db, prior_workflow.id, design_type=result.design_type or prior_workflow.design_type,
                mode=result.mode, structured_spec=spec,
                canva_design_id=result.canva_design_id, canva_brand_template_id=result.canva_brand_template_id,
            )
            result.workflow_id = updated.id if updated else prior_workflow.id
            return
        workflow = crud.create_design_workflow(
            db, user_id=user_id, conversation_id=conversation_id, design_type=result.design_type,
            mode=result.mode, structured_spec=spec,
            canva_design_id=result.canva_design_id, canva_brand_template_id=result.canva_brand_template_id,
        )
        result.workflow_id = workflow.id


def _map_spec_to_dataset_fields(spec: dict, dataset: dict[str, dict]) -> dict[str, Any]:
    """Maps the LLM-generated spec onto a brand template's REAL dataset field
    names/types (never invented) — text fields only in this pass; image/chart
    fields are left untouched so the template keeps its own default content
    for them rather than us guessing at an asset to fill them with."""
    text_fields = [(name, info) for name, info in dataset.items() if info.get("type") == "text"]
    if not text_fields:
        return {}

    def _pick(keywords: tuple[str, ...]) -> Optional[str]:
        for name, _ in text_fields:
            if any(k in name.lower() for k in keywords):
                return name
        return None

    data: dict[str, Any] = {}
    used: set[str] = set()

    title_field = _pick(("title", "heading", "headline")) or (text_fields[0][0] if text_fields else None)
    if title_field and spec.get("title"):
        data[title_field] = {"type": "text", "text": str(spec["title"])[:500]}
        used.add(title_field)

    remaining = [n for n, _ in text_fields if n not in used]
    subtitle_field = _pick(("subtitle", "sub", "tagline")) or (remaining[0] if remaining else None)
    if subtitle_field and subtitle_field not in used and spec.get("subtitle"):
        data[subtitle_field] = {"type": "text", "text": str(spec["subtitle"])[:500]}
        used.add(subtitle_field)

    remaining = [n for n, _ in text_fields if n not in used]
    bullets = [b for b in (spec.get("bullets") or []) if isinstance(b, str) and b.strip()]
    for field_name, bullet in zip(remaining, bullets):
        data[field_name] = {"type": "text", "text": bullet[:500]}

    return data


design_orchestrator = DesignOrchestrator()
