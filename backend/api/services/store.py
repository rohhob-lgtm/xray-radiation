"""
In-memory data store for conversations, LinkedIn posts, and X-ray analyses.

This is intentionally simple for the initial build. All data resets on
server restart. Replace with a real database (e.g. PostgreSQL via SQLAlchemy)
when persistence is required.
"""
from __future__ import annotations
import uuid
from datetime import datetime, timezone
from typing import Dict, List, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid() -> str:
    return str(uuid.uuid4())


# ──────────────────────────────────────────────────────────
# Conversations
# ──────────────────────────────────────────────────────────

_conversations: Dict[str, dict] = {}
_messages: Dict[str, List[dict]] = {}  # conversation_id → messages


def create_conversation(title: Optional[str] = None) -> dict:
    cid = _uid()
    conv = {
        "id": cid,
        "title": title or "New Conversation",
        "created_at": _now(),
        "message_count": 0,
        "last_message": None,
    }
    _conversations[cid] = conv
    _messages[cid] = []
    return conv


def get_conversation(conversation_id: str) -> Optional[dict]:
    return _conversations.get(conversation_id)


def list_conversations() -> List[dict]:
    return sorted(_conversations.values(), key=lambda c: c["created_at"], reverse=True)


def delete_conversation(conversation_id: str) -> bool:
    if conversation_id not in _conversations:
        return False
    del _conversations[conversation_id]
    _messages.pop(conversation_id, None)
    return True


def add_message(conversation_id: str, role: str, content: str, image_url: Optional[str] = None) -> dict:
    if conversation_id not in _conversations:
        raise KeyError(f"Conversation {conversation_id} not found")

    msg = {
        "id": _uid(),
        "role": role,
        "content": content,
        "image_url": image_url,
        "created_at": _now(),
    }
    _messages[conversation_id].append(msg)

    conv = _conversations[conversation_id]
    conv["message_count"] = len(_messages[conversation_id])
    conv["last_message"] = content[:100] + "..." if len(content) > 100 else content

    # Auto-title from first user message
    if conv["title"] == "New Conversation" and role == "user":
        conv["title"] = content[:60] + ("..." if len(content) > 60 else "")

    return msg


def get_messages(conversation_id: str) -> List[dict]:
    return _messages.get(conversation_id, [])


# ──────────────────────────────────────────────────────────
# LinkedIn Posts
# ──────────────────────────────────────────────────────────

_linkedin_posts: Dict[str, dict] = {}


def save_linkedin_post(post: dict) -> dict:
    _linkedin_posts[post["id"]] = post
    return post


def list_linkedin_posts() -> List[dict]:
    return sorted(_linkedin_posts.values(), key=lambda p: p["created_at"], reverse=True)


# ──────────────────────────────────────────────────────────
# X-ray Analyses
# ──────────────────────────────────────────────────────────

_xray_analyses: Dict[str, dict] = {}


def save_xray_analysis(analysis: dict) -> dict:
    _xray_analyses[analysis["id"]] = analysis
    return analysis


def list_xray_analyses() -> List[dict]:
    return sorted(_xray_analyses.values(), key=lambda a: a["created_at"], reverse=True)
