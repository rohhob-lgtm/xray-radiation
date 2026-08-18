"""PowerPoint generation for the workspace agent — thin wrapper over the
existing Rapiscan training-style builder (api.utils.pptx_gen.build_pptx),
reused rather than duplicated. Fits the spec's own example instruction
("create a training presentation from these manuals").
"""
from __future__ import annotations

from api.utils.pptx_gen import build_pptx


def build_training_pptx(
    course_title: str,
    slides_outline: list[dict],
    *,
    manufacturer: str = "",
    equipment_model: str = "",
    audience: str = "General",
    training_type: str = "Technical Training",
    language: str = "en",
    manual_filename: str = "",
) -> bytes:
    """slides_outline: [{"title": str, "bullets": [str, ...], "notes": str}, ...]

    Wraps the outline into pptx_gen.build_pptx's expected {project, slides}
    shape: a title slide, an auto-generated agenda, one content slide per
    outline entry, and a closing summary slide.
    """
    project = {
        "course_title": course_title,
        "manufacturer": manufacturer,
        "equipment_model": equipment_model,
        "audience": audience,
        "training_type": training_type,
        "language": language,
        "manual_filename": manual_filename,
    }

    slides: list[dict] = [
        {"type": "title", "title": course_title, "bullets": [], "speaker_notes": "", "is_visible": True},
        {
            "type": "agenda",
            "title": "Agenda",
            "bullets": [s.get("title", f"Topic {i + 1}") for i, s in enumerate(slides_outline)],
            "speaker_notes": "",
            "is_visible": True,
        },
    ]
    for s in slides_outline:
        slides.append({
            "type": "content",
            "title": s.get("title", ""),
            "bullets": s.get("bullets", []),
            "speaker_notes": s.get("notes", ""),
            "is_visible": True,
        })
    slides.append({
        "type": "summary",
        "title": "Summary",
        "bullets": [s.get("title", "") for s in slides_outline],
        "speaker_notes": "",
        "is_visible": True,
    })

    return build_pptx(project, slides, version="combined")
