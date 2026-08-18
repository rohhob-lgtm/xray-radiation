"""Executes the design-and-drive ExecutionPlan against existing, unmodified
business logic (design_content.generate_design_spec, design_orchestrator.run,
drive_export helpers), persisting an AgentRun/AgentStep/AgentArtifact trail
and emitting progress events in the exact shape the frontend already
understands (AgentEvent: {type, stage?, message?, tool?, ok?}).
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.db import crud
from api.services import design_content
from api.services.design_orchestrator import design_orchestrator, DesignResult
from api.services.drive_export import get_export_bytes, upload_bytes_to_drive, sanitize_filename

from .plan_builder import build_design_and_drive_plan
from .schemas import validate_plan

log = logging.getLogger(__name__)


def _now_ms() -> int:
    return int(time.monotonic() * 1000)


class AgentOrchestratorRunner:
    async def run(
        self, db: Session, user_id: str, conversation_id: str, message: str,
        design_type: str, provider: Any, prior_workflow: Optional[Any] = None,
    ) -> tuple[dict, list[dict], Any]:
        plan = build_design_and_drive_plan(design_type)
        validate_plan(plan)

        run = crud.create_agent_run(
            db, user_id=user_id, conversation_id=conversation_id, intent=plan.intent,
            plan=plan.model_dump(), inputs={"message": message, "design_type": design_type},
        )
        steps_by_key = {
            step.id: crud.create_agent_step(
                db, run_id=run.id, step_key=step.id, provider=step.provider, action=step.action,
                parameters=step.parameters, depends_on=step.depends_on,
                confirmation_required=step.confirmation_required,
            )
            for step in plan.steps
        }
        crud.update_agent_run(db, run.id, status="running")

        events: list[dict] = []

        def emit(stage: str, msg: str) -> None:
            events.append({"type": "stage", "stage": stage, "message": msg})

        run_started = _now_ms()

        def finish_step(step_key: str, status: str, output: Optional[dict] = None,
                        error_code: Optional[str] = None, error_message: Optional[str] = None,
                        started_at: Optional[int] = None) -> None:
            latency = _now_ms() - started_at if started_at is not None else 0
            crud.update_agent_step(
                db, steps_by_key[step_key].id, status=status, output=output,
                error_code=error_code, error_message=error_message, latency_ms=latency,
            )

        def run_failed(error_code: str, error_message: str) -> tuple[dict, list[dict], Any]:
            log.warning("agent_run %s failed at step=%s: %s (%s)", run.id, run.current_step_id, error_message, error_code)
            crud.update_agent_run(db, run.id, status="failed", error_code=error_code,
                                   error_message=error_message, latency_ms=_now_ms() - run_started)
            return (
                {"type": "canva_error", "error_code": error_code, "error_message": error_message},
                events, run,
            )

        # ── Step: content (Claude/active provider generates the structured brief) ──
        emit("understanding", "Understanding your request…")
        emit("planning", f"Planning: generate {design_type} content, render, export, and save to Drive")
        crud.update_agent_run(db, run.id, current_step_id="content")
        t0 = _now_ms()
        emit("using_claude", "Using AI to write the design content…")
        prior_spec = prior_workflow.structured_spec if prior_workflow else None
        try:
            spec = await design_content.generate_design_spec(provider, message, design_type, prior_spec)
        except Exception as exc:
            finish_step("content", "failed", error_message=str(exc), started_at=t0)
            return run_failed("CONTENT_GENERATION_FAILED", str(exc))
        finish_step("content", "completed", output=spec, started_at=t0)

        # ── Step: render (Canva 4-tier fallback, or local-render-only) ──────────
        crud.update_agent_run(db, run.id, current_step_id="render")
        t0 = _now_ms()
        emit("checking_canva", "Checking Canva connection and templates…")
        design_result: DesignResult = await design_orchestrator.run(
            db, user_id, conversation_id, design_type, spec, prior_workflow=prior_workflow,
        )
        emit("rendering_design", f"Rendering design (mode: {design_result.mode})…")
        if not design_result.success:
            finish_step("render", "failed", error_message=design_result.error_message, started_at=t0)
            return run_failed("RENDER_FAILED", design_result.error_message or "Design rendering failed")
        finish_step("render", "completed", output={
            "mode": design_result.mode, "canva_design_id": design_result.canva_design_id,
            "edit_url": design_result.edit_url, "view_url": design_result.view_url,
        }, started_at=t0)
        if design_result.canva_design_id:
            crud.create_agent_artifact(
                db, run_id=run.id, step_key="render", type="canva_design", provider="canva",
                external_id=design_result.canva_design_id, url=design_result.edit_url,
                meta={"view_url": design_result.view_url, "thumbnail_url": design_result.thumbnail_url},
            )

        title = spec.get("title") or f"{design_type}-design"

        # ── Step: export_png ─────────────────────────────────────────────────────
        crud.update_agent_run(db, run.id, current_step_id="export_png")
        t0 = _now_ms()
        emit("exporting_png", "Exporting PNG…")
        png_outcome = await get_export_bytes(db, user_id, design_result, "png")
        if not png_outcome.success:
            finish_step("export_png", "failed", error_code=png_outcome.error_code,
                        error_message=png_outcome.error_message, started_at=t0)
            return run_failed(png_outcome.error_code or "PNG_EXPORT_FAILED",
                               png_outcome.error_message or "PNG export failed")
        finish_step("export_png", "completed", started_at=t0)
        crud.create_agent_artifact(
            db, run_id=run.id, step_key="export_png", type="png", provider="canva" if design_result.canva_design_id else "internal_renderer",
            filename=f"{sanitize_filename(title)}.png", mime_type="image/png",
            size_bytes=len(png_outcome.content_bytes or b""),
        )

        # ── Step: export_pdf (skipped, not failed, when unavailable) ────────────
        crud.update_agent_run(db, run.id, current_step_id="export_pdf")
        t0 = _now_ms()
        emit("exporting_pdf", "Exporting PDF…")
        pdf_outcome = await get_export_bytes(db, user_id, design_result, "pdf")
        if pdf_outcome.success:
            finish_step("export_pdf", "completed", started_at=t0)
            crud.create_agent_artifact(
                db, run_id=run.id, step_key="export_pdf", type="pdf", provider="canva",
                filename=f"{sanitize_filename(title)}.pdf", mime_type="application/pdf",
                size_bytes=len(pdf_outcome.content_bytes or b""),
            )
        else:
            finish_step("export_pdf", "skipped", error_code=pdf_outcome.error_code,
                        error_message=pdf_outcome.error_message, started_at=t0)

        # ── Step: save_to_drive — upload the PDF if we have one, else the PNG ───
        crud.update_agent_run(db, run.id, current_step_id="save_to_drive")
        t0 = _now_ms()
        emit("saving_to_drive", "Saving to Google Drive…")
        upload_outcome = pdf_outcome if pdf_outcome.success else png_outcome
        drive_result = await upload_bytes_to_drive(
            db, user_id, f"{sanitize_filename(title)}.{upload_outcome.format}",
            upload_outcome.content_bytes, upload_outcome.mime_type,
        )
        if not drive_result.success:
            finish_step("save_to_drive", "failed", error_code=drive_result.error_code,
                        error_message=drive_result.error_message, started_at=t0)
            return run_failed(drive_result.error_code or "DRIVE_UPLOAD_FAILED",
                               drive_result.error_message or "Google Drive upload failed")
        finish_step("save_to_drive", "completed", output=drive_result.data, started_at=t0)
        drive_file = drive_result.data or {}
        crud.create_agent_artifact(
            db, run_id=run.id, step_key="save_to_drive", type="drive_file", provider="google_drive",
            external_id=drive_file.get("id"), url=drive_file.get("webViewLink"),
            filename=drive_file.get("name"), mime_type=upload_outcome.mime_type,
            size_bytes=len(upload_outcome.content_bytes or b""),
        )

        emit("completed", "Done — design created and saved to Google Drive.")
        crud.update_agent_run(
            db, run.id, status="completed", progress=100, current_step_id="completed",
            completed_at=datetime.now(timezone.utc), latency_ms=_now_ms() - run_started,
            outputs={"canva_design_id": design_result.canva_design_id, "drive_file_id": drive_file.get("id")},
        )

        payload = {
            "type": "canva_design_result",
            "design_type": design_type,
            "mode": design_result.mode,
            "canva_design_id": design_result.canva_design_id,
            "title": design_result.title or title,
            "thumbnail_url": design_result.thumbnail_url,
            "edit_url": design_result.edit_url,
            "view_url": design_result.view_url,
            "available_actions": design_result.available_actions,
            "connect_required": design_result.connect_required,
            "connect_url": design_result.connect_url,
            "error_message": None,
            "workflow_id": design_result.workflow_id,
            "run_id": run.id,
            "drive_file": {
                "id": drive_file.get("id"), "name": drive_file.get("name"),
                "web_view_link": drive_file.get("webViewLink"),
            } if drive_file.get("id") else None,
        }
        return payload, events, run


agent_orchestrator_runner = AgentOrchestratorRunner()
