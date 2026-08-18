"""Pydantic models for LinkedIn post generation."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


class LinkedInPostInput(BaseModel):
    topic: str
    tone: str = "professional"          # professional | educational | thought_leadership | case_study | tips
    length: str = "medium"              # short | medium | long
    keywords: Optional[List[str]] = None
    include_hashtags: bool = True


class LinkedInPost(BaseModel):
    id: str
    topic: str
    tone: str
    length: str
    content: str
    hashtags: List[str]
    created_at: str
