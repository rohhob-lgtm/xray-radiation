"""
Image classification service — zero API cost.

Uses the already-loaded OpenCLIP (ViT-L/14) to classify RagImages into
predefined categories by scoring the image against text prompt templates.

Falls back to caption-keyword matching if OpenCLIP is unavailable.
"""
from __future__ import annotations
import logging
from typing import Optional

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# ── Category definitions ───────────────────────────────────────────────────────

CATEGORIES = [
    ("x-ray",       "an X-ray scan image showing objects or cargo"),
    ("detector",    "a detector array or sensor panel for X-ray scanning"),
    ("conveyor",    "a conveyor belt system for baggage or cargo screening"),
    ("generator",   "an X-ray generator or high voltage power supply"),
    ("monitor",     "a computer monitor or display screen showing X-ray images"),
    ("component",   "a mechanical or electronic component or circuit board"),
    ("warning",     "a warning label, safety sign, or caution notice"),
    ("operation",   "an operator performing a procedure or operating equipment"),
    ("maintenance", "a maintenance technician servicing or repairing equipment"),
    ("safety",      "personal protective equipment or radiation safety equipment"),
    ("diagram",     "a technical diagram, schematic, or engineering drawing"),
    ("ui",          "a software user interface or graphical user interface"),
]

CATEGORY_NAMES = [c[0] for c in CATEGORIES]


def _classify_by_caption(caption: str) -> tuple[str, float]:
    """Keyword-based classification from GPT-generated caption text."""
    if not caption:
        return "unknown", 0.0

    cap = caption.lower()
    scores: dict[str, float] = {}

    keyword_map = {
        "x-ray":       ["x-ray", "xray", "scan", "radiograph", "attenuation", "cargo inspection"],
        "detector":    ["detector", "sensor", "array", "scintillator", "photomultiplier", "pmt"],
        "conveyor":    ["conveyor", "belt", "tunnel", "baggage", "cargo hold"],
        "generator":   ["generator", "hvps", "high voltage", "power supply", "transformer"],
        "monitor":     ["monitor", "display", "screen", "workstation", "console", "hmi"],
        "component":   ["pcb", "board", "component", "circuit", "module", "bracket", "connector"],
        "warning":     ["warning", "caution", "danger", "radiation", "hazard", "do not", "prohibited"],
        "operation":   ["operator", "operating", "procedure", "step", "press", "click", "select"],
        "maintenance": ["maintenance", "service", "repair", "replace", "install", "remove", "torque"],
        "safety":      ["ppe", "dosimeter", "glove", "shield", "protective", "lead apron"],
        "diagram":     ["diagram", "schematic", "wiring", "flow", "block diagram", "architecture"],
        "ui":          ["screenshot", "gui", "menu", "button", "window", "interface", "software"],
    }

    for category, keywords in keyword_map.items():
        score = sum(1.0 for kw in keywords if kw in cap)
        if score > 0:
            scores[category] = score

    if not scores:
        return "unknown", 0.0

    best = max(scores, key=lambda k: scores[k])
    confidence = min(0.95, scores[best] / 3.0)
    return best, confidence


async def classify_image(image_data: bytes, caption: str = "") -> tuple[str, float, str]:
    """
    Classify an image into a predefined category.
    Returns (category, confidence, model_used).

    Priority:
      1. OpenCLIP visual embedding (if loaded) — most accurate
      2. Caption keyword matching — fast, zero cost
    """
    # Try OpenCLIP first
    try:
        from api.services.colpali_service import (
            _backend, _openclip_model, _openclip_tokenizer
        )
        import asyncio

        if _backend == "openclip" and _openclip_model is not None:
            result = await asyncio.get_event_loop().run_in_executor(
                None, _classify_openclip, image_data
            )
            if result:
                return result[0], result[1], "openclip"
    except Exception as exc:
        log.debug("OpenCLIP classify failed, falling back to caption: %s", exc)

    # Fallback: caption keywords
    category, confidence = _classify_by_caption(caption)
    return category, confidence, "keyword"


def _classify_openclip(image_data: bytes) -> Optional[tuple[str, float]]:
    """Synchronous OpenCLIP scoring — runs in thread pool."""
    try:
        import io
        import torch
        from PIL import Image
        from api.services.colpali_service import (
            _openclip_model, _openclip_preprocess, _openclip_tokenizer
        )

        if _openclip_model is None:
            return None

        # Encode image
        img = Image.open(io.BytesIO(image_data)).convert("RGB")
        img_tensor = _openclip_preprocess(img).unsqueeze(0)

        # Build text prompts
        prompts = [f"a photo of {desc}" for _, desc in CATEGORIES]
        text_tokens = _openclip_tokenizer(prompts)

        with torch.no_grad():
            img_vec = _openclip_model.encode_image(img_tensor, normalize=True)
            txt_vecs = _openclip_model.encode_text(text_tokens, normalize=True)
            # Cosine similarities
            sims = (img_vec @ txt_vecs.T)[0]
            probs = sims.softmax(dim=-1)

        best_idx = int(probs.argmax().item())
        confidence = float(probs[best_idx].item())
        category = CATEGORY_NAMES[best_idx]
        return category, confidence

    except Exception as exc:
        log.warning("OpenCLIP image classify error: %s", exc)
        return None


async def classify_and_store(db: Session, image_id: str,
                              image_data: bytes, caption: str = "") -> Optional[str]:
    """
    Classify a RagImage and persist the result in ImageClassification.
    Returns category string, or None on failure.
    Idempotent — skips if already classified.
    """
    from api.db.models import ImageClassification

    # Idempotency
    existing = db.query(ImageClassification).filter(
        ImageClassification.image_id == image_id
    ).first()
    if existing:
        return existing.category

    try:
        category, confidence, model = await classify_image(image_data, caption)

        db.add(ImageClassification(
            image_id=image_id,
            category=category,
            confidence=confidence,
            model=model,
        ))
        db.commit()
        return category
    except Exception as exc:
        db.rollback()
        log.warning("classify_and_store failed for image %s: %s", image_id, exc)
        return None
