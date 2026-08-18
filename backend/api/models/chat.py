"""Pydantic models for the chat feature."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


class Message(BaseModel):
    id: str
    role: str  # "user" | "assistant"
    content: str
    image_url: Optional[str] = None
    created_at: str


class ConversationInput(BaseModel):
    title: Optional[str] = None


class Conversation(BaseModel):
    id: str
    title: str
    created_at: str
    message_count: int
    last_message: Optional[str] = None
    workspace_id: Optional[str] = None


class ConversationWithMessages(BaseModel):
    id: str
    title: str
    created_at: str
    messages: List[Message]
    workspace_id: Optional[str] = None


class ChatMessageInput(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    image_base64: Optional[str] = None
    image_filename: Optional[str] = None
    agent_mode: Optional[str] = None  # general | research | physics | patent | vision | maintenance | training | innovation
    workspace_id: Optional[str] = None  # AI Chat Workspace — routes this turn through the workspace agent loop
    provider_override: Optional[str] = None  # "auto" | a registered provider id (e.g. "gemini", "claude") — "auto" or unset uses automatic task routing


class ChatResponse(BaseModel):
    message: str
    conversation_id: str
    provider_used: str
