"""Builds the one concrete ExecutionPlan this session's runner executes:
generate design content -> render a design -> export PNG/PDF -> save to Drive.
"""
from __future__ import annotations

from .intents import IntentType
from .schemas import ExecutionPlan, PlanStep


def build_design_and_drive_plan(design_type: str) -> ExecutionPlan:
    return ExecutionPlan(
        intent=IntentType.VISUAL_DESIGN,
        steps=[
            PlanStep(
                id="content", provider="claude", action="generate_design_content",
                parameters={"design_type": design_type}, depends_on=[],
            ),
            PlanStep(
                id="render", provider="internal_renderer", action="render_design",
                parameters={"design_type": design_type}, depends_on=["content"],
            ),
            PlanStep(
                id="export_png", provider="internal_renderer", action="export_png",
                parameters={}, depends_on=["render"],
            ),
            PlanStep(
                id="export_pdf", provider="internal_renderer", action="export_pdf",
                parameters={}, depends_on=["render"],
            ),
            PlanStep(
                id="save_to_drive", provider="google_drive", action="google_drive.save_generated_file",
                parameters={}, depends_on=["export_png"], confirmation_required=False,
            ),
        ],
        expected_outputs=["canva_design_or_png", "pdf_or_skipped", "drive_file"],
    )
