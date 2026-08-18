"""LinkedIn post generation routes — persisted to PostgreSQL."""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from api.db import get_db
from api.db.crud import (
    create_linkedin_post, list_linkedin_posts, delete_linkedin_post, linkedin_post_to_dict
)
from api.middleware.auth import optional_auth
from api.models.linkedin import LinkedInPostInput
from api.services.ai_providers.registry import provider_registry

router = APIRouter(tags=["linkedin"])


@router.get("/linkedin/posts")
def list_posts(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    user_id = user["id"] if user else None
    posts = list_linkedin_posts(db, user_id=user_id)
    return [linkedin_post_to_dict(p) for p in posts]


@router.post("/linkedin/generate")
async def generate_post(
    body: LinkedInPostInput,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    provider = provider_registry.get_active()
    if not provider:
        raise HTTPException(status_code=503, detail="No AI provider available")

    try:
        content, hashtags = await provider.generate_linkedin_post(
            topic=body.topic, tone=body.tone, length=body.length, keywords=body.keywords
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Provider error: {exc}")

    user_id = user["id"] if user else None
    post = create_linkedin_post(
        db, user_id=user_id, topic=body.topic, tone=body.tone, length=body.length,
        content=content, hashtags=hashtags if body.include_hashtags else []
    )
    return linkedin_post_to_dict(post)


@router.delete("/linkedin/posts/{post_id}", status_code=204)
def delete_post(post_id: str, db: Session = Depends(get_db)):
    if not delete_linkedin_post(db, post_id):
        raise HTTPException(status_code=404, detail="Post not found")
