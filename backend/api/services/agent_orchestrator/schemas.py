"""Machine-readable execution-plan schema + validation.

A plan is built by code today (see plan_builder.py), not an LLM, but every
step still passes through validate_plan() before the runner executes it —
the same "never call an action outside the registered tool schema" guardrail
connector_service.execute_action() already enforces for connector actions,
applied up front so a malformed plan fails before anything runs.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel

from api.services.connectors.registry import connector_registry

# Non-connector "providers" this orchestrator can address directly, and the
# actions each one is allowed to perform. Connector providers (canva,
# google_drive, ...) are instead validated against their registered
# ConnectorManifest — the single source of truth connector_service already
# uses, so there's no second list to keep in sync.
_AI_PROVIDER_ACTIONS: dict[str, set[str]] = {
    "claude": {"generate_design_content"},
    "gemini": {"generate_design_content"},
    "internal_renderer": {"render_design", "export_png", "export_pdf"},
}


class PlanStep(BaseModel):
    id: str
    provider: str
    action: str
    parameters: dict[str, Any] = {}
    depends_on: list[str] = []
    confirmation_required: bool = False


class ExecutionPlan(BaseModel):
    intent: str
    steps: list[PlanStep]
    expected_outputs: list[str] = []


class PlanValidationError(Exception):
    pass


def validate_plan(plan: ExecutionPlan) -> None:
    """Raises PlanValidationError if any step addresses an unregistered
    provider or an action outside that provider's declared capability set."""
    step_ids = {step.id for step in plan.steps}
    for step in plan.steps:
        missing_deps = [d for d in step.depends_on if d not in step_ids]
        if missing_deps:
            raise PlanValidationError(
                f"Step '{step.id}' depends on unknown step id(s): {missing_deps}"
            )

        if step.provider in _AI_PROVIDER_ACTIONS:
            if step.action not in _AI_PROVIDER_ACTIONS[step.provider]:
                raise PlanValidationError(
                    f"Action '{step.action}' is not allowed for provider '{step.provider}'"
                )
            continue

        if not connector_registry.is_registered(step.provider):
            raise PlanValidationError(f"Provider '{step.provider}' is not a registered connector")
        connector = connector_registry.get(step.provider)
        capability = connector.manifest.get_capability(step.action)
        if capability is None:
            raise PlanValidationError(
                f"Action '{step.action}' is not declared in the '{step.provider}' connector manifest"
            )
        if not capability.is_implemented:
            raise PlanValidationError(
                f"Action '{step.action}' is declared but not implemented for '{step.provider}'"
            )
