"""Pydantic models for AI provider management."""
from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class AIProvider(BaseModel):
    id: str
    name: str
    type: str           # gemini | claude | openai | ollama | copilot | mock
    description: str
    is_configured: bool
    is_active: bool
    model: Optional[str] = None
    base_url: Optional[str] = None
    is_online: Optional[bool] = None
    warning: Optional[str] = None


class ProviderActivation(BaseModel):
    api_key: str
    base_url: Optional[str] = None
    model: Optional[str] = None


class TaskRouteUpdate(BaseModel):
    provider_id: str  # a real provider id, or "auto" to clear the override
