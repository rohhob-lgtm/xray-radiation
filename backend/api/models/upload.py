"""Pydantic models for X-ray image upload and analysis."""
from __future__ import annotations
from typing import Optional, List
from pydantic import BaseModel


class XrayAnalysisInput(BaseModel):
    image_base64: str
    filename: str
    scanner_type: str = "general"   # baggage | cargo | vehicle | body | general
    context: Optional[str] = None


class XrayAnalysis(BaseModel):
    id: str
    filename: str
    scanner_type: str
    findings: str
    threat_level: str           # clear | low | medium | high | critical
    recommendations: List[str]
    image_url: Optional[str] = None
    created_at: str
