"""X-ray image analysis routes — persisted to PostgreSQL."""
from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Request
from sqlalchemy.orm import Session

from api.db import get_db
from api.db.crud import (
    create_xray_analysis, list_xray_analyses, delete_xray_analysis, xray_analysis_to_dict
)
from api.middleware.auth import optional_auth
from api.models.upload import XrayAnalysisInput
from api.services.ai_providers.registry import provider_registry

router = APIRouter(tags=["upload"])


@router.get("/upload/analyses")
def list_analyses(
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    user_id = user["id"] if user else None
    analyses = list_xray_analyses(db, user_id=user_id)
    return [xray_analysis_to_dict(a) for a in analyses]


@router.post("/upload/analyze")
async def analyze_image(
    body: XrayAnalysisInput,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    provider = provider_registry.get_active()
    if not provider:
        raise HTTPException(status_code=503, detail="No AI provider available")

    try:
        findings, threat_level, recommendations = await provider.analyze_xray_image(
            image_base64=body.image_base64,
            scanner_type=body.scanner_type,
            context=body.context,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Provider error: {exc}")

    user_id = user["id"] if user else None
    analysis = create_xray_analysis(
        db, user_id=user_id, filename=body.filename, scanner_type=body.scanner_type,
        findings=findings, threat_level=threat_level, recommendations=recommendations
    )
    return xray_analysis_to_dict(analysis)


@router.delete("/upload/analyses/{analysis_id}", status_code=204)
def delete_analysis(analysis_id: str, db: Session = Depends(get_db)):
    if not delete_xray_analysis(db, analysis_id):
        raise HTTPException(status_code=404, detail="Analysis not found")
