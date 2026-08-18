"""AI provider management routes."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Depends
from sqlalchemy.orm import Session

from api.models.providers import AIProvider, ProviderActivation, TaskRouteUpdate
from api.services.ai_providers import provider_registry
from api.db.base import get_db
from api.db.models import AppSetting
from api.middleware.auth import require_admin_session

router = APIRouter(tags=["providers"])


def _set_app_setting(db: Session, key: str, value: str) -> None:
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))


def _provider_to_model(p) -> AIProvider:
    warning = provider_registry.get_warning(p.provider_id)
    return AIProvider(
        id=p.provider_id,
        name=p.provider_name,
        type=p.provider_type,
        description=p.description,
        is_configured=p.is_configured,
        is_active=(p.provider_id == provider_registry.active_id),
        model=p.model or None,
        base_url=getattr(p, "base_url", None) or None,
        is_online=provider_registry.is_online(p.provider_id),
        warning=warning,
    )


@router.get("/providers", response_model=list[AIProvider])
async def list_providers():
    return [_provider_to_model(p) for p in provider_registry.all_providers()]


@router.post("/providers/{provider_id}/activate", response_model=AIProvider)
async def activate_provider(
    provider_id: str,
    body: ProviderActivation,
    db: Session = Depends(get_db),
    _admin: None = Depends(require_admin_session),
):
    provider = provider_registry.get(provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if provider_id == "mock":
        provider_registry.set_active("mock")
        _set_app_setting(db, "ai.active_provider", "mock")
        _set_app_setting(db, "ai.fallback_provider", "mock")
        _set_app_setting(db, "ai.provider_enabled", "false")
        _set_app_setting(db, "ai.provider_configured", "false")
        _set_app_setting(db, "ai.active_model", "")
        db.commit()
        return _provider_to_model(provider)

    # Update credentials on the provider instance
    provider.api_key = body.api_key
    if body.base_url:
        provider.base_url = body.base_url
    if body.model:
        provider.model = body.model

    if not provider.is_configured:
        if provider_id == "gemini":
            raise HTTPException(
                status_code=400,
                detail="GEMINI_API_KEY is missing. Set GEMINI_API_KEY in .env.",
            )
        raise HTTPException(
            status_code=400,
            detail="Provider credentials are incomplete — check api_key and base_url",
        )

    provider_registry.set_active(provider_id)

    # Persist non-secret runtime configuration and active selection.
    _set_app_setting(db, "ai.active_provider", provider_id)
    _set_app_setting(db, "ai.fallback_provider", provider_id)
    _set_app_setting(db, "ai.provider_enabled", "true")
    _set_app_setting(db, "ai.provider_configured", "true")
    _set_app_setting(db, "ai.active_model", (getattr(provider, "model", "") or "").strip())
    _set_app_setting(db, "ai.last_successful_provider", provider_id)
    if provider_id == "gemini" and body.model:
        _set_app_setting(db, "ai.gemini.model", body.model)
    if provider_id == "claude" and body.model:
        _set_app_setting(db, "ai.claude.model", body.model)
    if provider_id == "openai" and body.model:
        _set_app_setting(db, "ai.openai.model", body.model)
    if provider_id == "ollama":
        _set_app_setting(
            db,
            "ai.ollama.base_url",
            (getattr(provider, "base_url", "") or "http://127.0.0.1:11434").strip(),
        )
        _set_app_setting(
            db,
            "ai.ollama.model",
            (getattr(provider, "model", "") or "qwen2.5-7b-fast6:latest").strip(),
        )
    if provider_id == "copilot":
        if body.base_url:
            _set_app_setting(db, "ai.copilot.base_url", body.base_url)
        if body.model:
            _set_app_setting(db, "ai.copilot.model", body.model)
    db.commit()

    return _provider_to_model(provider)


@router.get("/providers/task-routes")
async def list_task_routes():
    """Per-module/task automatic-routing overrides (task_hint -> provider_id)."""
    return provider_registry.list_task_routes()


@router.put("/providers/task-routes/{task_hint}")
async def set_task_route(task_hint: str, body: TaskRouteUpdate, db: Session = Depends(get_db), _admin: None = Depends(require_admin_session)):
    if body.provider_id == "auto":
        provider_registry.persist_clear_task_route(db, task_hint)
        return {"task_hint": task_hint, "provider_id": "auto"}

    if not provider_registry.get(body.provider_id):
        raise HTTPException(status_code=404, detail=f"Unknown provider '{body.provider_id}'")
    if not provider_registry.persist_task_route(db, task_hint, body.provider_id):
        raise HTTPException(status_code=400, detail="Could not set task route")
    return {"task_hint": task_hint, "provider_id": body.provider_id}
