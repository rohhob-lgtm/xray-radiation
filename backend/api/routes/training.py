"""
Training Material Generator — X-Ray Academy
Uploads equipment manuals (PDF), extracts content, and generates professional
training courses (PPTX, DOCX, ZIP) grounded strictly in the uploaded manual.

Generation pipeline (12 stages, streamed via SSE):
    Reading PDF -> Extracting text -> Detecting sections -> Extracting figures/tables
    -> Building technical knowledge map -> Planning course -> Enhancing educational content
    -> Generating diagrams -> Creating assessments -> Formatting output
    -> Performing quality review -> Exporting files
"""
from __future__ import annotations
import hashlib
import io
import json
import logging
import math
import os
import re
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from api.db import get_db
from api.middleware.auth import optional_auth, require_auth

log = logging.getLogger(__name__)
router = APIRouter(tags=["training"])

_EXPORT_ROOT = os.path.join(tempfile.gettempdir(), "xray_training_exports")
os.makedirs(_EXPORT_ROOT, exist_ok=True)


def _safe_course_slug(title: str, max_len: int = 60) -> str:
    slug = re.sub(r"[^\w\s-]", "", title or "Course")[:max_len].strip().replace(" ", "_")
    return slug or "Course"


def _artifact_path(project_id: str, filename: str) -> str:
    proj_dir = os.path.join(_EXPORT_ROOT, project_id)
    os.makedirs(proj_dir, exist_ok=True)
    return os.path.join(proj_dir, filename)


def _write_artifact(path: str, data: bytes) -> int:
    with open(path, "wb") as f:
        f.write(data)
    return os.path.getsize(path)


def _verify_artifact(path: str) -> tuple[bool, int]:
    if not os.path.exists(path):
        return False, 0
    size = os.path.getsize(path)
    return size > 0, size


def _download_url_for(path_template: str, project_id: str, query: str = "") -> str:
    base = f"/api{path_template.format(project_id=project_id)}"
    return f"{base}?{query}" if query else base

# ── Debug helpers ──────────────────────────────────────────────────────────────

_DEBUG_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "debug")
_MANUAL_PDF_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "uploads", "training_manuals")


def _manual_pdf_path(project_id: str) -> str:
    return os.path.join(_MANUAL_PDF_DIR, f"{project_id}.pdf")


def _render_manual_page_images(pdf_path: str, page_numbers: set[int]) -> dict[str, bytes]:
    """Render specific 1-indexed pages of the source manual PDF to PNG bytes.

    Real human-authored training decks lift the manual's own diagrams
    (block diagrams, wiring diagrams, exploded views) directly onto slides
    rather than describing them in prose. Since the manual is a real,
    already-illustrated field service document, rendering the actual page
    containing a given figure is far higher-fidelity than trying to have
    an LLM synthesize a new diagram from scratch.
    """
    images: dict[str, bytes] = {}
    if not page_numbers:
        return images
    try:
        import fitz  # PyMuPDF
        doc = fitz.open(pdf_path)
        try:
            for n in page_numbers:
                idx = n - 1
                if idx < 0 or idx >= doc.page_count:
                    continue
                pix = doc[idx].get_pixmap(dpi=150)
                images[f"PAGE_{n}"] = pix.tobytes("png")
        finally:
            doc.close()
    except Exception as e:
        log.warning("Could not render manual page images from %s: %s", pdf_path, e)
    return images


def _apply_image_tags(slide_dicts: list[dict]) -> None:
    """Set image_tag from the slide's own source_pages[0], deterministically.

    image_tag isn't a persisted DB column (slides round-trip through
    type/title/content/speaker_notes/source_pages/is_visible only), so it
    can't be stored — it's cheap to recompute the same way every time
    instead, both right after generation and at any later standalone
    export call.
    """
    for s in slide_dicts:
        if s.get("type") not in ("image_content", "full_image"):
            continue
        pages = s.get("source_pages") or []
        if pages:
            try:
                n = int(pages[0])
                if n > 0:
                    s["image_tag"] = f"PAGE_{n}"
            except (TypeError, ValueError):
                pass


def _build_images_for_slides(project_id: str, slide_dicts: list[dict]) -> dict[str, bytes]:
    """Build the {image_tag: png_bytes} map build_pptx() needs for any
    type=="image_content"/"full_image" slide, by re-rendering the relevant
    pages from the manual PDF stored at upload time. Stateless by design —
    only the page number (already persisted in source_pages) is needed, so
    this works identically at generation time and at any later export call."""
    pdf_path = _manual_pdf_path(project_id)
    if not os.path.exists(pdf_path):
        return {}
    page_nums: set[int] = set()
    for s in slide_dicts:
        if s.get("type") not in ("image_content", "full_image"):
            continue
        pages = s.get("source_pages") or []
        if pages:
            try:
                n = int(pages[0])
                if n > 0:
                    page_nums.add(n)
            except (TypeError, ValueError):
                pass
    return _render_manual_page_images(pdf_path, page_nums)


def _save_debug(filename: str, data) -> None:
    """Persist intermediate generation data to /debug/ for inspection."""
    try:
        os.makedirs(_DEBUG_DIR, exist_ok=True)
        path = os.path.join(_DEBUG_DIR, filename)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=str, ensure_ascii=False)
        log.info("Debug saved → %s", path)
    except Exception as e:
        log.warning("Could not save debug file %s: %s", filename, e)


async def _generate_with_large_budget(
    provider: Any, prompt: str, system_prompt: str, max_tokens: int,
) -> str:
    """Call the AI provider for a large structured response (a full course
    JSON), which needs far more output tokens than a normal chat reply.

    provider.chat() used to hardcode an internal cap tuned for short
    conversational replies (~2048 tokens on some providers), which cut off a
    full 45-slide course JSON partway through module 3 — observed live on
    Claude specifically, since the old version of this function only raised
    the budget via a direct client for openai/gemini and silently fell back
    to the capped provider.chat() for everything else. BaseAIProvider.chat()
    now accepts an explicit max_tokens override that every provider honors
    (or safely ignores if unsupported), so a single call covers all of them.
    """
    try:
        return await provider.chat(
            [{"role": "user", "content": prompt}], system_prompt=system_prompt, max_tokens=max_tokens,
        )
    except TypeError:
        # Defensive: a provider whose chat() predates the max_tokens param.
        return await provider.chat([{"role": "user", "content": prompt}], system_prompt=system_prompt)


def _sse(obj: dict) -> str:
    return f"data: {json.dumps(obj, default=str)}\n\n"


def _normalized_text(v: Any) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _score_topic_similarity(a: str, b: str) -> float:
    """Return lightweight token overlap score in [0,1] for course-type matching."""
    a_tokens = set(re.findall(r"[a-z0-9]{3,}", _normalized_text(a).lower()))
    b_tokens = set(re.findall(r"[a-z0-9]{3,}", _normalized_text(b).lower()))
    if not a_tokens or not b_tokens:
        return 0.0
    inter = len(a_tokens & b_tokens)
    # Cosine-like normalization is more stable than raw Jaccard for short labels.
    return inter / max(1.0, math.sqrt(len(a_tokens) * len(b_tokens)))


def _json_hash(v: Any) -> str:
    payload = json.dumps(v, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


_BAD_PAGE_RANGE_RE = re.compile(r'(\[|,)(\s*)(\d+-\d+)(\s*)(?=[,\]])')


def _repair_page_range_json_arrays(raw: str) -> str:
    """Quote bare "N-N" page-range tokens the model puts inside JSON arrays.

    The source manual paginates as "chapter-page" (e.g. "p.2-5"), and the
    model sometimes echoes that citation straight into a source_pages array
    as a bare token: "source_pages": [2-5]. That isn't valid JSON — not a
    number, not a string — and a single occurrence anywhere in a
    multi-thousand-token slide-deck response breaks parsing of the entire
    response. Observed live: a 45-slide course collapsed to 6 slides
    because the parser hit "[2-5]" partway through and every slide after
    that point in the raw text was discarded. Quoting the token ("2-5")
    keeps it valid JSON; downstream code already filters source_pages to
    digit-only entries, so a quoted range is dropped harmlessly instead of
    breaking the whole response.
    """
    return _BAD_PAGE_RANGE_RE.sub(lambda m: f'{m.group(1)}{m.group(2)}"{m.group(3)}"{m.group(4)}', raw)


def _safe_parse_json_object(raw: str) -> dict:
    """Parse model output as JSON, allowing surrounding prose/code fences."""
    text = (raw or "").strip()
    if not text:
        return {}
    text = _repair_page_range_json_arrays(text)

    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)

    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    except Exception:
        pass

    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        return {}
    try:
        parsed = json.loads(m.group(0))
        return parsed if isinstance(parsed, dict) else {"data": parsed}
    except Exception:
        return {}


def _settings_cache(settings: dict) -> dict:
    cache = settings.get("_training_cache")
    if not isinstance(cache, dict):
        cache = {}
        settings["_training_cache"] = cache
    return cache


def _detect_heading(line: str) -> bool:
    if not line:
        return False
    if re.match(r"^\d+(?:\.\d+)*\s+[A-Z][A-Za-z0-9\-\s/(),]{3,120}$", line):
        return True
    if re.match(r"^(?:Chapter|Section|Part)\s+\d+[A-Za-z0-9\-\s/(),]{0,120}$", line, re.IGNORECASE):
        return True
    if line.isupper() and 4 <= len(line) <= 120:
        return True
    return False


def _extract_reference_tags(text: str) -> dict:
    fig_nums = sorted(set(re.findall(r"(?i)\bfig(?:ure)?\.?\s*([\d\-]+)", text)))
    tbl_nums = sorted(set(re.findall(r"(?i)\btable\s*([\d\-]+)", text)))
    part_nums = sorted(set(re.findall(r"\b(?:P/N|PN|Part\s*No\.?|Part\s*Number)\s*[:#-]?\s*([A-Z0-9\-]{3,})", text, re.IGNORECASE)))
    units = sorted(set(re.findall(r"\b\d+(?:\.\d+)?\s?(?:kV|mA|mGy|uSv|mSv|mm|cm|kg|Hz|V|A|W|C)\b", text, re.IGNORECASE)))
    values = sorted(set(re.findall(r"\b\d+(?:\.\d+)?\s?(?:kV|mA|mGy|uSv|mSv|mm|cm|kg|Hz|V|A|W|%)?\b", text)))
    warning_level = ""
    if re.search(r"\bdanger\b", text, re.IGNORECASE):
        warning_level = "danger"
    elif re.search(r"\bwarning\b", text, re.IGNORECASE):
        warning_level = "warning"
    elif re.search(r"\bcaution\b", text, re.IGNORECASE):
        warning_level = "caution"
    elif re.search(r"\bnote\b", text, re.IGNORECASE):
        warning_level = "note"
    return {
        "figure_numbers": fig_nums,
        "table_numbers": tbl_nums,
        "part_numbers": part_nums,
        "measurement_units": units,
        "technical_values": values[:20],
        "warning_level": warning_level,
    }


def _extract_manual_index(pages: list[dict]) -> dict:
    """Build a structured local manual index with page/section traceability."""
    categories: dict[str, list[dict]] = {
        "equipment_name_model": [],
        "manufacturer_information": [],
        "system_purpose_applications": [],
        "system_components_subassemblies": [],
        "technical_specifications": [],
        "operating_principles": [],
        "xray_generation_imaging_principles": [],
        "radiation_safety_information": [],
        "operator_controls_user_interface": [],
        "startup_shutdown_procedures": [],
        "operating_procedures": [],
        "image_interpretation_information": [],
        "installation_procedures": [],
        "preventive_maintenance": [],
        "corrective_maintenance": [],
        "calibration_procedures": [],
        "troubleshooting_tables": [],
        "fault_codes_alarm_messages": [],
        "safety_warnings_cautions_notes": [],
        "tools_test_equipment": [],
        "spare_parts_consumables": [],
        "inspection_procedures": [],
        "diagrams_figures_tables_captions": [],
        "technical_terminology_abbreviations": [],
    }

    keyword_map: dict[str, list[str]] = {
        "equipment_name_model": ["model", "equipment", "system"],
        "manufacturer_information": ["manufacturer", "made by", "company"],
        "system_purpose_applications": ["purpose", "application", "intended use"],
        "system_components_subassemblies": ["component", "subassembly", "assembly", "module"],
        "technical_specifications": ["specification", "rated", "voltage", "current", "dimension"],
        "operating_principles": ["principle", "operation theory", "how it works"],
        "xray_generation_imaging_principles": ["x-ray", "xray", "detector", "image formation", "beam"],
        "radiation_safety_information": ["radiation", "dose", "shielding", "interlock"],
        "operator_controls_user_interface": ["control panel", "hmi", "button", "ui", "screen"],
        "startup_shutdown_procedures": ["startup", "start-up", "shutdown", "power off", "power on"],
        "operating_procedures": ["operating procedure", "operation", "workflow"],
        "image_interpretation_information": ["image interpretation", "analysis", "material discrimination"],
        "installation_procedures": ["installation", "commissioning", "site preparation"],
        "preventive_maintenance": ["preventive maintenance", "pm", "inspection schedule"],
        "corrective_maintenance": ["corrective maintenance", "repair", "replacement"],
        "calibration_procedures": ["calibration", "adjustment", "alignment"],
        "troubleshooting_tables": ["troubleshooting", "symptom", "possible cause"],
        "fault_codes_alarm_messages": ["fault code", "alarm", "error code"],
        "safety_warnings_cautions_notes": ["warning", "caution", "danger", "note"],
        "tools_test_equipment": ["tool", "test equipment", "multimeter", "meter"],
        "spare_parts_consumables": ["spare part", "consumable", "replacement part"],
        "inspection_procedures": ["inspection", "checklist", "verify"],
        "diagrams_figures_tables_captions": ["figure", "fig.", "table", "diagram", "caption"],
        "technical_terminology_abbreviations": ["abbreviation", "acronym", "term"],
    }

    sections: list[dict] = []
    figures: list[dict] = []
    tables: list[dict] = []
    warnings: list[dict] = []
    current_section = "General"

    for p in pages:
        page_num = int(p.get("page_num") or 0)
        lines = [ln.strip() for ln in str(p.get("text") or "").splitlines()]
        for line in lines:
            if not line:
                continue
            if _detect_heading(line):
                current_section = line
                if not sections or sections[-1].get("name") != current_section:
                    sections.append({"name": current_section, "page": page_num})

            tags = _extract_reference_tags(line)
            item = {
                "page": page_num,
                "section": current_section,
                "text": line,
                **tags,
            }

            if tags["figure_numbers"]:
                figures.append(item)
            if tags["table_numbers"]:
                tables.append(item)
            if tags["warning_level"]:
                warnings.append(item)

            line_l = line.lower()
            for category, kws in keyword_map.items():
                if any(kw in line_l for kw in kws):
                    categories[category].append(item)

            for abbr in re.findall(r"\b[A-Z]{2,8}(?:-[A-Z0-9]{1,6})?\b", line):
                categories["technical_terminology_abbreviations"].append({
                    "page": page_num,
                    "section": current_section,
                    "text": abbr,
                    "figure_numbers": [],
                    "table_numbers": [],
                    "part_numbers": [],
                    "measurement_units": [],
                    "technical_values": [],
                    "warning_level": "",
                })

    for k, vals in categories.items():
        seen: set[str] = set()
        deduped: list[dict] = []
        for it in vals:
            key = f"{it.get('page')}|{it.get('section')}|{_normalized_text(it.get('text'))}"
            if key in seen:
                continue
            seen.add(key)
            deduped.append(it)
        categories[k] = deduped[:80]

    equipment_name = ""
    equipment_model = ""
    manufacturer = ""
    full_text = "\n".join(str(p.get("text") or "") for p in pages)
    model_match = re.search(r"\bModel\s*[:#-]?\s*([A-Z0-9\-]{2,})\b", full_text, re.IGNORECASE)
    if model_match:
        equipment_model = model_match.group(1).strip()
    mfr_match = re.search(r"\bManufacturer\s*[:#-]?\s*([^\n]{2,80})", full_text, re.IGNORECASE)
    if mfr_match:
        manufacturer = _normalized_text(mfr_match.group(1))
    title_match = re.search(r"\b([A-Z][A-Za-z0-9\-\s]{3,60})\s+Manual\b", full_text)
    if title_match:
        equipment_name = _normalized_text(title_match.group(1))

    return {
        "pages_analyzed": len(pages),
        "sections": sections,
        "figures": figures[:200],
        "tables": tables[:200],
        "warnings": warnings[:200],
        "equipment": {
            "name": equipment_name,
            "model": equipment_model,
            "manufacturer": manufacturer,
        },
        "categories": categories,
    }


def _chunk_manual_for_ai(pages: list[dict], max_chars_per_chunk: int = 5000) -> list[dict]:
    chunks: list[dict] = []
    current_text: list[str] = []
    current_pages: list[int] = []
    current_section = "General"
    current_chars = 0

    for p in pages:
        page_num = int(p.get("page_num") or 0)
        text = str(p.get("text") or "")
        for ln in text.splitlines():
            line = ln.strip()
            if not line:
                continue
            if _detect_heading(line):
                current_section = line
            add_len = len(line) + 1
            if current_chars + add_len > max_chars_per_chunk and current_text:
                chunk_text = "\n".join(current_text)
                chunks.append({
                    "section": current_section,
                    "page_start": min(current_pages),
                    "page_end": max(current_pages),
                    "text": chunk_text,
                    "hash": _json_hash({"section": current_section, "pages": current_pages, "text": chunk_text}),
                })
                current_text = []
                current_pages = []
                current_chars = 0
            current_text.append(line)
            current_pages.append(page_num)
            current_chars += add_len

    if current_text:
        chunk_text = "\n".join(current_text)
        chunks.append({
            "section": current_section,
            "page_start": min(current_pages),
            "page_end": max(current_pages),
            "text": chunk_text,
            "hash": _json_hash({"section": current_section, "pages": current_pages, "text": chunk_text}),
        })

    return chunks


def _fallback_knowledge_map(manual_index: dict) -> dict:
    topics: list[dict] = []
    for cat, items in (manual_index.get("categories") or {}).items():
        if not items:
            continue
        sample = items[:3]
        source = sample[0]
        topics.append({
            "topic_title": cat.replace("_", " ").title(),
            "source_manual_section": source.get("section") or "General",
            "source_page_number": source.get("page") or 0,
            "technical_explanation": " ".join(_normalized_text(x.get("text")) for x in sample),
            "simplified_learner_explanation": "Explain this topic with practical examples while preserving manual values.",
            "key_facts": [_normalized_text(x.get("text")) for x in sample],
            "safety_implications": "Retain original warning limits and levels from manual.",
            "practical_application": "Relate this to normal operation, maintenance, or troubleshooting tasks.",
            "instructor_notes": "Emphasize source traceability and do not modify manufacturer limits.",
            "suggested_visual": "Block diagram or flowchart with module labels.",
            "suggested_exercise": "Short guided exercise grounded in the cited procedure.",
            "suggested_assessment_question": "What is the correct procedure/value stated in the manual?",
            "content_origin": {
                "direct_manual_facts": [_normalized_text(x.get("text")) for x in sample],
                "derived_educational_explanation": [],
                "general_scientific_background": [],
                "instructor_recommendations": ["Use this topic in module recap and safety checks."],
            },
        })
    return {"topics": topics[:40], "background_label": "General scientific background is explicitly labeled when used."}


async def _build_knowledge_map(
    provider: Any,
    project_dict: dict,
    manual_index: dict,
    chunks: list[dict],
    enhance_cfg: dict,
    ppt_refs: dict | None = None,
) -> dict:
    """Create intermediate training knowledge model with source traceability labels."""
    prioritized = []
    preferred = [
        "safety", "radiation", "maintenance", "operation", "calibration", "troubleshooting", "fault", "alarm", "installation",
    ]
    for ch in chunks:
        title = str(ch.get("section") or "").lower()
        if any(k in title for k in preferred):
            prioritized.append(ch)
    if len(prioritized) < 12:
        prioritized = (prioritized + chunks)[:12]
    else:
        prioritized = prioritized[:12]

    chunk_block = "\n\n".join(
        f"[Chunk {i+1}] section={c.get('section')} pages={c.get('page_start')}-{c.get('page_end')}\n{c.get('text')[:2800]}"
        for i, c in enumerate(prioritized)
    )
    enhance_on = bool(enhance_cfg.get("enabled", True))
    options = enhance_cfg.get("options", {})
    ppt_summary = _summarize_ppt_refs_for_prompt(ppt_refs)

    prompt = f"""Build a strict technical training knowledge map from the manual excerpts.

Course context:
- Title: {project_dict.get('course_title')}
- Audience: {project_dict.get('audience')}
- Course type: {project_dict.get('training_type')}
- Enhance training material: {enhance_on}
- Enhancement options: {json.dumps(options, ensure_ascii=False)}

Manual extracted catalog summary:
{json.dumps({
    'equipment': manual_index.get('equipment', {}),
    'sections': manual_index.get('sections', [])[:30],
    'figure_count': len(manual_index.get('figures', [])),
    'table_count': len(manual_index.get('tables', [])),
    'warning_count': len(manual_index.get('warnings', [])),
}, ensure_ascii=False)}

Manual chunks:
{chunk_block}

PowerPoint knowledge-base references (secondary sources):
{ppt_summary}

Return JSON only:
{{
  "topics": [
    {{
      "topic_title": "string",
      "source_manual_section": "string",
      "source_page_number": 0,
      "technical_explanation": "manual-grounded technical explanation",
      "simplified_learner_explanation": "learner-friendly explanation",
      "key_facts": ["facts with units/values exactly preserved"],
      "safety_implications": "safety statement",
      "practical_application": "practical application",
      "instructor_notes": "instructor guidance",
      "suggested_visual": "diagram recommendation",
      "suggested_exercise": "exercise idea",
      "suggested_assessment_question": "assessment question",
      "content_origin": {{
        "direct_manual_facts": ["facts directly stated"],
        "derived_educational_explanation": ["derived but faithful explanations"],
        "general_scientific_background": ["background clearly labeled as GENERAL BACKGROUND"],
        "instructor_recommendations": ["teaching recommendations"]
      }}
    }}
  ],
  "background_label": "Explicit label used for non-manual background statements"
}}

Rules:
- Source priority: (1) uploaded manual, (2) manufacturer-approved PPT references, (3) other relevant PPT references, (4) general background.
- Never invent manufacturer procedures, safety limits, technical values, calibration/electrical/radiation values, part numbers, or fault codes.
- Never overwrite manual facts using PowerPoint references.
- If PowerPoint values conflict with manual values, keep manual value and mark as instructor-review conflict.
- If a detail is not supported by the manual chunks, omit it.
- Keep source_manual_section and source_page_number populated.
"""

    raw = await provider.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16384,
        system_prompt=(
            "You are a technical training extraction engine. Return strict JSON only. "
            "Preserve manual values exactly and separate direct facts from educational augmentation."
        ),
    )
    parsed = _safe_parse_json_object(raw)
    if not parsed.get("topics"):
        return _fallback_knowledge_map(manual_index)
    return parsed


def _fallback_learning_map(knowledge_map: dict) -> dict:
    topics = knowledge_map.get("topics") or []
    sequencing: list[dict] = []
    for idx, t in enumerate(topics[:30], start=1):
        title = _normalized_text(t.get("topic_title")) or f"Topic {idx}"
        text_blob = " ".join([
            _normalized_text(t.get("technical_explanation")),
            " ".join(_normalized_text(x) for x in (t.get("key_facts") or [])[:3]),
        ]).lower()
        sequencing.append({
            "topic": title,
            "priority_order": idx,
            "prerequisites": ["System overview"] if idx > 3 else [],
            "postpone_until": "after core modules" if idx > 20 else "",
            "requires_diagram": any(k in text_blob for k in ["diagram", "flow", "signal", "power", "circuit"]),
            "requires_laboratory": any(k in text_blob for k in ["maintenance", "calibration", "inspection", "procedure", "replace", "test"]),
            "requires_demonstration": True,
            "requires_assessment": True,
            "teaching_intent": "Teach operational reasoning and field execution, not text recall.",
        })
    return {
        "entry_profile": "Assume mixed engineer background and refresh prerequisites early.",
        "sequencing": sequencing,
    }


async def _build_learning_map(
    provider: Any,
    project_dict: dict,
    knowledge_map: dict,
    structure: dict,
) -> dict:
    prompt = f"""Build a LEARNING MAP before any slide generation.

Course context:
- Audience: {project_dict.get('audience')}
- Training type: {project_dict.get('training_type')}
- Duration: {project_dict.get('settings', {}).get('duration', '3 days')}

Knowledge topics:
{json.dumps((knowledge_map.get('topics') or [])[:40], ensure_ascii=False)}

Manual structure summary:
{json.dumps({'page_count': structure.get('page_count', 0), 'headings': (structure.get('headings') or [])[:40]}, ensure_ascii=False)}

Return JSON only:
{{
  "entry_profile": "what students likely already know",
  "sequencing": [
    {{
      "topic": "string",
      "priority_order": 1,
      "prerequisites": ["string"],
      "postpone_until": "string or empty",
      "requires_diagram": true,
      "requires_laboratory": false,
      "requires_demonstration": true,
      "requires_assessment": true,
      "teaching_intent": "why this topic is taught now"
    }}
  ]
}}

Rules:
- Optimize for learning effectiveness, not manual order.
- Manual is raw technical knowledge, not final course structure.
- Split or merge concepts for educational quality.
"""
    raw = await provider.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16384,
        system_prompt="You are a curriculum learning architect. Return strict JSON only.",
    )
    parsed = _safe_parse_json_object(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("sequencing"), list) or not parsed.get("sequencing"):
        return _fallback_learning_map(knowledge_map)
    return parsed


def _fallback_curriculum_map(outline: dict) -> dict:
    modules: list[dict] = []
    for sec in (outline.get("sections") or [])[:30]:
        title = _normalized_text(sec.get("title"))
        topics = [str(x) for x in (sec.get("topics") or [])[:5]]
        lessons = []
        for t in topics[:4]:
            lessons.append({
                "lesson_title": t,
                "sub_lessons": [f"{t} fundamentals", f"{t} field application"],
                "labs": [f"Lab: {t} diagnostic practice"],
                "practical_exercises": [f"Exercise: {t} troubleshooting drill"],
                "assessments": [f"Knowledge check: {t}"],
                "review_points": [f"Review: {t} critical points"],
            })
        modules.append({
            "module_title": title,
            "module_objective": f"Teach {title} for safe and efficient engineering performance.",
            "lessons": lessons,
            "final_module_assessment": f"Scenario-based assessment for {title}",
        })
    return {
        "course_goal": "Professional engineering learning experience, not document conversion.",
        "modules": modules,
        "final_course_assessment": "Integrated troubleshooting and maintenance capstone",
        "learning_path_notes": ["Reorder manual content for pedagogy.", "Keep manual technical values authoritative."],
    }


async def _build_curriculum_map(
    provider: Any,
    project_dict: dict,
    outline: dict,
    learning_map: dict,
    knowledge_map: dict,
    teaching_dna: dict | None = None,
) -> dict:
    prompt = f"""Build a CURRICULUM MAP before slide generation.

Course context:
- Title: {project_dict.get('course_title')}
- Audience: {project_dict.get('audience')}
- Training type: {project_dict.get('training_type')}

Learning map:
{json.dumps(learning_map, ensure_ascii=False)}

Knowledge map topics:
{json.dumps((knowledge_map.get('topics') or [])[:30], ensure_ascii=False)}

Current outline:
{json.dumps((outline.get('sections') or [])[:30], ensure_ascii=False)}

Teaching DNA:
{json.dumps(teaching_dna or {}, ensure_ascii=False)}

Return JSON only:
{{
  "course_goal": "string",
  "modules": [
    {{
      "module_title": "string",
      "module_objective": "string",
      "lessons": [
        {{
          "lesson_title": "string",
          "sub_lessons": ["string"],
          "labs": ["string"],
          "practical_exercises": ["string"],
          "assessments": ["string"],
          "review_points": ["string"]
        }}
      ],
      "final_module_assessment": "string"
    }}
  ],
  "final_course_assessment": "string",
  "learning_path_notes": ["string"]
}}

Rules:
- Reorganize for teaching quality; manual order is optional.
- Ensure each major module has labs, practicals, and assessments.
- Apply Teaching DNA module flow when source material supports it.
"""
    raw = await provider.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16384,
        system_prompt="You are a senior technical curriculum designer. Return strict JSON only.",
    )
    parsed = _safe_parse_json_object(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("modules"), list) or not parsed.get("modules"):
        return _fallback_curriculum_map(outline)
    return parsed


def _fallback_instruction_plan(curriculum_map: dict) -> dict:
    lesson_plans: list[dict] = []
    for m in (curriculum_map.get("modules") or [])[:30]:
        for l in (m.get("lessons") or [])[:10]:
            lesson = _normalized_text(l.get("lesson_title"))
            if not lesson:
                continue
            lesson_plans.append({
                "lesson_title": lesson,
                "teaching_objective": f"Enable learners to execute {lesson} correctly in field conditions.",
                "teaching_strategy": "Explain -> demonstrate -> guided practice -> independent scenario.",
                "visual_strategy": "Use diagrams and flow visuals for mechanism-level understanding.",
                "laboratory_strategy": "Hands-on lab with tools, measurements, and acceptance criteria.",
                "assessment_strategy": "Knowledge check plus troubleshooting scenario and debrief.",
                "instructor_notes_strategy": "Include probes, common mistakes, pacing, and coaching cues.",
                "common_mistakes": ["Skipping prerequisite checks", "Replacing parts before diagnosis"],
            })
    return {"lesson_plans": lesson_plans}


async def _build_instruction_plan(
    provider: Any,
    project_dict: dict,
    curriculum_map: dict,
    learning_map: dict,
    teaching_dna: dict | None = None,
) -> dict:
    prompt = f"""Build an INSTRUCTION PLAN before slide generation.

Course context:
- Audience: {project_dict.get('audience')}
- Training type: {project_dict.get('training_type')}

Learning map:
{json.dumps(learning_map, ensure_ascii=False)}

Curriculum map:
{json.dumps(curriculum_map, ensure_ascii=False)}

Teaching DNA:
{json.dumps(teaching_dna or {}, ensure_ascii=False)}

Return JSON only:
{{
  "lesson_plans": [
    {{
      "lesson_title": "string",
      "teaching_objective": "string",
      "teaching_strategy": "string",
      "visual_strategy": "string",
      "laboratory_strategy": "string",
      "assessment_strategy": "string",
      "instructor_notes_strategy": "string",
      "common_mistakes": ["string"]
    }}
  ]
}}

Rules:
- Every lesson must exist for educational value, not because text exists.
- Do not produce summary-style plans.
- Include explicit instructor actions and speaker-guidance patterns from Teaching DNA.
- Place practical/lab and troubleshooting reasoning before knowledge checks when feasible.
"""
    raw = await provider.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16384,
        system_prompt="You are an expert instructional designer for engineering training. Return strict JSON only.",
    )
    parsed = _safe_parse_json_object(raw)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("lesson_plans"), list) or not parsed.get("lesson_plans"):
        return _fallback_instruction_plan(curriculum_map)
    return parsed


def _topic_queries_from_manual(manual_index: dict, max_topics: int = 12) -> list[str]:
    topics: list[str] = []
    for sec in (manual_index.get("sections") or [])[: max_topics * 2]:
        name = _normalized_text(sec.get("name"))
        if name and name.lower() not in {t.lower() for t in topics}:
            topics.append(name)
        if len(topics) >= max_topics:
            break

    if len(topics) < max_topics:
        for cat, items in (manual_index.get("categories") or {}).items():
            if not items:
                continue
            topics.append(cat.replace("_", " "))
            if len(topics) >= max_topics:
                break
    return topics[:max_topics]


def _summarize_ppt_refs_for_prompt(ppt_refs: dict | None, max_items: int = 16) -> str:
    if not isinstance(ppt_refs, dict):
        return "No suitable PowerPoint reference found."

    rows = ppt_refs.get("selected_references") or []
    if not rows:
        return "No suitable PowerPoint reference found."

    lines: list[str] = []
    for r in rows[:max_items]:
        lines.append(
            f"- {r.get('reference_file')} slide {r.get('reference_slide')} "
            f"[{r.get('reference_category')}] score={r.get('relevance_score')}"
        )
    return "\n".join(lines)


def _normalize_doc_id_list(doc_ids: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for raw in doc_ids:
        doc_id = _normalized_text(raw)
        if not doc_id or doc_id in seen:
            continue
        seen.add(doc_id)
        out.append(doc_id)
    return sorted(out)


def _teaching_dna_storage_key(doc_id: str) -> str:
    return f"training.teaching_dna.{doc_id}"


def _teaching_blueprint_storage_key(doc_ids: list[str]) -> str:
    normalized = _normalize_doc_id_list(doc_ids)
    key_hash = _json_hash(normalized)[:16]
    return f"training.teaching_blueprint.{key_hash}"


def _pattern_key(text: str, max_len: int = 140) -> str:
    norm = _normalized_text(text).lower()
    norm = re.sub(r"[^a-z0-9\u0600-\u06FF\s\-]", "", norm)
    norm = re.sub(r"\s+", " ", norm).strip()
    return norm[:max_len]


MIN_EXPERT_BLUEPRINT_COURSES = 5
MIN_EXPERT_BLUEPRINT_SLIDES = 200


def _record_pattern(pool: dict, key: str, sample: str, doc_id: str) -> None:
    if not key:
        return
    row = pool.setdefault(key, {
        "sample": _normalized_text(sample) or key,
        "courses": set(),
        "occurrences": 0,
    })
    row["occurrences"] = int(row.get("occurrences") or 0) + 1
    row["courses"].add(doc_id)


def _build_repeated_patterns(pool: dict, total_courses: int, max_items: int) -> list[dict]:
    rows: list[dict] = []
    for _k, meta in pool.items():
        supporting_courses = sorted(str(x) for x in (meta.get("courses") or set()))
        supporting_course_count = len(supporting_courses)
        if total_courses > 1 and supporting_course_count < 2:
            # Ignore one-off patterns when multiple expert courses are analyzed.
            continue

        occurrences = int(meta.get("occurrences") or 0)
        coverage = supporting_course_count / max(1, total_courses)
        frequency = min(1.0, occurrences / max(2.0, total_courses * 2.0))
        confidence = round(min(1.0, (0.7 * coverage) + (0.3 * frequency)), 3)

        rows.append({
            "pattern": str(meta.get("sample") or _k),
            "supporting_courses": supporting_courses,
            "supporting_course_count": supporting_course_count,
            "occurrences": occurrences,
            "confidence_score": confidence,
        })

    rows.sort(key=lambda x: (x.get("confidence_score", 0), x.get("supporting_course_count", 0), x.get("occurrences", 0)), reverse=True)
    return rows[:max_items]


def _expert_ppt_slide_role(slide: Any) -> str:
    title = _normalized_text(getattr(slide, "slide_title", "")).lower()
    text_blob = " ".join([
        _normalized_text(getattr(slide, "slide_text", "")),
        _normalized_text(getattr(slide, "speaker_notes", "")),
        _normalized_text(getattr(slide, "table_content", "")),
        _normalized_text(getattr(slide, "diagram_labels", "")),
    ]).lower()

    if any(k in title for k in ["module", "section", "lesson", "chapter"]):
        return "module_introduction"
    if any(k in text_blob for k in ["learning objectives", "by the end", "you will be able", "objective"]):
        return "objectives"
    if any(k in text_blob for k in ["knowledge check", "quiz", "assessment", "question", "true/false", "multiple choice"]):
        return "knowledge_check"
    if any(k in text_blob for k in ["lab exercise", "practical", "hands-on", "laboratory", "exercise"]):
        return "practical_activity"
    if any(k in text_blob for k in ["troubleshoot", "fault", "diagnostic", "decision tree", "isolation", "verification"]):
        return "troubleshooting_reasoning"
    if any(k in text_blob for k in ["summary", "recap", "review", "key takeaway", "debrief"]):
        return "review_transition"
    if any(k in text_blob for k in ["diagram", "schematic", "block", "flow", "signal", "process"]) or bool((getattr(slide, "visual_layout_metadata", {}) or {}).get("image_count", 0) > 0):
        return "visual_diagram"
    return "technical_explanation"


def _compact_teaching_dna_summary(dna: dict) -> dict:
    cs = dna.get("course_structure") if isinstance(dna.get("course_structure"), dict) else {}
    sr = dna.get("slide_role_patterns") if isinstance(dna.get("slide_role_patterns"), dict) else {}
    stats = dna.get("analysis_stats") if isinstance(dna.get("analysis_stats"), dict) else {}

    lab_patterns = dna.get("lab_patterns") or []
    troubleshooting_patterns = dna.get("troubleshooting_patterns") or []
    assessment_patterns = dna.get("assessment_patterns") or []
    visual_patterns = dna.get("visual_patterns") or []
    transition_patterns = dna.get("transition_patterns") or []

    def _avg_conf(rows: list[Any]) -> float:
        vals = [float(r.get("confidence_score") or 0.0) for r in rows if isinstance(r, dict)]
        if not vals:
            return 0.0
        return round(sum(vals) / len(vals), 3)

    return {
        "source_file": dna.get("source_file", ""),
        "expert_courses_count": int(stats.get("expert_courses_count") or 0),
        "total_slides_analyzed": int(stats.get("total_slides_analyzed") or 0),
        "total_instructor_notes_analyzed": int(stats.get("total_instructor_notes_analyzed") or 0),
        "modules_detected": len(cs.get("module_order") or []),
        "role_types": len((sr.get("role_frequency") or {}).keys()),
        "module_sequence_template": sr.get("module_sequence_template") or [],
        "lab_patterns": len(lab_patterns),
        "troubleshooting_patterns": len(troubleshooting_patterns),
        "assessment_patterns": len(assessment_patterns),
        "visual_patterns": len(visual_patterns),
        "transition_patterns": len(transition_patterns),
        "selection_warnings": stats.get("selection_warnings") or [],
        "recommended_dataset": stats.get("recommended_dataset") or {
            "min_courses": 5,
            "recommended_total_slides": 200,
            "warning_below_total_slides": 100,
        },
        "pattern_confidence": {
            "lab_patterns": _avg_conf(lab_patterns),
            "troubleshooting_patterns": _avg_conf(troubleshooting_patterns),
            "assessment_patterns": _avg_conf(assessment_patterns),
            "visual_patterns": _avg_conf(visual_patterns),
            "transition_patterns": _avg_conf(transition_patterns),
        },
    }


async def _gemini_transition_patterns(provider: Any, role_sequence: list[str]) -> list[str]:
    if not provider or not role_sequence:
        return []

    prompt = f"""Analyze this ordered slide-role sequence from one expert human PPT course and return JSON only.

Sequence:
{json.dumps(role_sequence[:240], ensure_ascii=False)}

Return:
{{
  "transition_patterns": ["short actionable transition pattern"]
}}

Rules:
- Extract transition behavior only (sequence and lesson flow).
- Never copy slide content.
- Return 4 to 10 concise patterns.
"""
    try:
        raw = await provider.chat(
            [{"role": "user", "content": prompt}],
            max_tokens=16384,
            system_prompt="You analyze teaching flow patterns. Return strict JSON only.",
        )
        parsed = _safe_parse_json_object(raw)
        patterns = parsed.get("transition_patterns") if isinstance(parsed, dict) else None
        if isinstance(patterns, list):
            return [str(x).strip() for x in patterns if _normalized_text(x)][:10]
    except Exception:
        return []
    return []


async def _compute_teaching_dna(
    db: Session,
    doc_id: str,
    provider: Any,
    force_reanalyze: bool = False,
) -> tuple[dict, bool, str]:
    return await _compute_master_teaching_blueprint(
        db=db,
        doc_ids=[doc_id],
        provider=provider,
        force_reanalyze=force_reanalyze,
    )


async def _compute_master_teaching_blueprint(
    db: Session,
    doc_ids: list[str],
    provider: Any,
    force_reanalyze: bool = False,
) -> tuple[dict, bool, str]:
    from api.db.models import AppSetting, PptxPresentationIndex, PptxSlideIndex

    normalized_doc_ids = _normalize_doc_id_list(doc_ids)
    if not normalized_doc_ids:
        raise HTTPException(status_code=422, detail="Select at least one expert course")

    presentations = (
        db.query(PptxPresentationIndex)
        .filter(PptxPresentationIndex.doc_id.in_(normalized_doc_ids))
        .all()
    )
    by_doc_id = {str(p.doc_id): p for p in presentations}

    selected_presentations: list[Any] = []
    for doc_id in normalized_doc_ids:
        pres = by_doc_id.get(doc_id)
        if not pres:
            raise HTTPException(status_code=404, detail=f"Selected PowerPoint source not found: {doc_id}")
        if bool(pres.obsolete) or bool(pres.do_not_use):
            raise HTTPException(status_code=400, detail=f"Selected PowerPoint is marked obsolete/do-not-use: {pres.filename}")
        if not (bool(pres.trusted) or bool(pres.manufacturer_approved) or bool(pres.internal_training_reference)):
            raise HTTPException(status_code=400, detail=f"Selected PowerPoint is not marked as trusted: {pres.filename}")
        selected_presentations.append(pres)

    key = _teaching_blueprint_storage_key(normalized_doc_ids)
    fingerprint = _json_hash([
        {
            "doc_id": p.doc_id,
            "updated_at": str(p.updated_at),
            "slide_count": int(p.slide_count or 0),
            "filename": p.filename,
        }
        for p in sorted(selected_presentations, key=lambda x: str(x.doc_id))
    ])

    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if row and not force_reanalyze:
        try:
            cached = json.loads(row.value or "{}")
            cached_blueprint = cached.get("master_teaching_blueprint") or cached.get("teaching_dna")
            if cached.get("fingerprint") == fingerprint and isinstance(cached_blueprint, dict):
                return cached, True, key
        except Exception:
            pass

    presentation_ids = [p.id for p in selected_presentations]
    slides = (
        db.query(PptxSlideIndex)
        .filter(PptxSlideIndex.presentation_id.in_(presentation_ids))
        .order_by(PptxSlideIndex.presentation_id.asc(), PptxSlideIndex.slide_number.asc())
        .all()
    )
    if not slides:
        raise HTTPException(status_code=422, detail="No indexed slides found for selected expert courses")

    slides_by_presentation: dict[str, list[Any]] = {}
    for slide in slides:
        slides_by_presentation.setdefault(str(slide.presentation_id), []).append(slide)

    for pres in selected_presentations:
        if not slides_by_presentation.get(str(pres.id)):
            raise HTTPException(status_code=422, detail=f"No indexed slides found for selected source: {pres.filename}")

    role_sequences: dict[str, list[str]] = {}
    role_frequency: dict[str, int] = {}
    total_slides = 0
    total_notes = 0

    module_pool: dict[str, dict] = {}
    action_pool: dict[str, dict] = {}
    lab_pool: dict[str, dict] = {}
    troubleshooting_pool: dict[str, dict] = {}
    assessment_pool: dict[str, dict] = {}
    visual_pool: dict[str, dict] = {}
    transition_pool: dict[str, dict] = {}

    for pres in selected_presentations:
        doc_id = str(pres.doc_id)
        course_slides = slides_by_presentation.get(str(pres.id), [])
        role_sequence: list[str] = []

        for s in course_slides:
            role = _expert_ppt_slide_role(s)
            role_sequence.append(role)
            role_frequency[role] = int(role_frequency.get(role, 0)) + 1

            total_slides += 1
            title = _normalized_text(s.slide_title)
            text_blob = " ".join([
                _normalized_text(s.slide_text),
                _normalized_text(s.speaker_notes),
                _normalized_text(s.table_content),
                _normalized_text(s.diagram_labels),
            ])
            notes = _normalized_text(s.speaker_notes)
            if notes:
                total_notes += 1

            if role == "module_introduction" and title:
                _record_pattern(module_pool, _pattern_key(title), title, doc_id)

            if notes:
                for line in re.split(r"[\n\.!?;]+", notes):
                    l = _normalized_text(line)
                    if not l:
                        continue
                    if re.search(r"\b(ask|explain|demonstrate|point out|emphasize|probe|challenge|debrief|refer)\b", l, re.IGNORECASE) or re.search(r"(اشرح|اطلب|ناقش|اعرض|أكد)", l):
                        _record_pattern(action_pool, _pattern_key(l), l, doc_id)

            if role == "practical_activity":
                sample = title or text_blob[:120]
                _record_pattern(lab_pool, _pattern_key(sample), sample, doc_id)
            if role == "troubleshooting_reasoning":
                sample = title or text_blob[:120]
                _record_pattern(troubleshooting_pool, _pattern_key(sample), sample, doc_id)
            if role == "knowledge_check":
                sample = title or text_blob[:120]
                _record_pattern(assessment_pool, _pattern_key(sample), sample, doc_id)

            layout = s.visual_layout_metadata if isinstance(s.visual_layout_metadata, dict) else {}
            image_count = int(layout.get("image_count") or 0)
            text_boxes = int(layout.get("text_boxes") or 0)
            if role == "visual_diagram" or image_count > 0:
                sample = f"{title or 'visual slide'} | images={image_count} | text_boxes={text_boxes}"
                visual_key = f"role={role}|images={image_count}|text_boxes={text_boxes}"
                _record_pattern(visual_pool, visual_key, sample, doc_id)

        role_sequences[doc_id] = role_sequence
        for idx in range(1, len(role_sequence)):
            pair = f"{role_sequence[idx - 1]} -> {role_sequence[idx]}"
            _record_pattern(transition_pool, pair, f"Transition frequently follows: {pair}", doc_id)

    repeated_modules = _build_repeated_patterns(module_pool, len(selected_presentations), max_items=80)
    repeated_actions = _build_repeated_patterns(action_pool, len(selected_presentations), max_items=60)
    repeated_lab_patterns = _build_repeated_patterns(lab_pool, len(selected_presentations), max_items=40)
    repeated_troubleshooting_patterns = _build_repeated_patterns(troubleshooting_pool, len(selected_presentations), max_items=40)
    repeated_assessment_patterns = _build_repeated_patterns(assessment_pool, len(selected_presentations), max_items=40)
    repeated_visual_patterns = _build_repeated_patterns(visual_pool, len(selected_presentations), max_items=60)
    repeated_transition_patterns = _build_repeated_patterns(transition_pool, len(selected_presentations), max_items=20)

    all_roles: list[str] = []
    for seq in role_sequences.values():
        all_roles.extend(seq)

    gemini_patterns = await _gemini_transition_patterns(provider, all_roles)
    if gemini_patterns and repeated_transition_patterns:
        for idx, gp in enumerate(gemini_patterns[: len(repeated_transition_patterns)]):
            repeated_transition_patterns[idx]["pattern"] = gp

    module_sequence_template = [
        "module_introduction",
        "objectives",
        "technical_explanation",
        "visual_diagram",
        "instructor_notes",
        "practical_activity",
        "troubleshooting_reasoning",
        "knowledge_check",
        "review_transition",
    ]

    recommended_dataset = {
        "min_courses": MIN_EXPERT_BLUEPRINT_COURSES,
        "recommended_total_slides": MIN_EXPERT_BLUEPRINT_SLIDES,
        "warning_below_total_slides": 100,
    }

    selection_warnings: list[str] = []
    if len(selected_presentations) < MIN_EXPERT_BLUEPRINT_COURSES:
        selection_warnings.append("Recommended dataset is at least 5 expert courses for stronger teaching-pattern reliability.")
    if total_slides < MIN_EXPERT_BLUEPRINT_SLIDES:
        selection_warnings.append("Recommended dataset is at least 200 total slides before creating a master teaching blueprint.")
    if total_slides < 100:
        selection_warnings.append("Warning: fewer than 100 slides selected. Blueprint quality may be unstable.")

    teaching_dna = {
        "source_file": f"Expert Course Library ({len(selected_presentations)} courses)",
        "source_files": [p.filename for p in selected_presentations],
        "source_doc_ids": [str(p.doc_id) for p in selected_presentations],
        "course_structure": {
            "module_order": [str(m.get("pattern") or "") for m in repeated_modules][:80],
            "avg_slides_per_module": round(total_slides / max(1, len(repeated_modules)), 2),
            "avg_slides_per_course": round(total_slides / max(1, len(selected_presentations)), 2),
            "observed_slide_count": total_slides,
        },
        "slide_role_patterns": {
            "role_frequency": role_frequency,
            "observed_sequence": all_roles[:260],
            "module_sequence_template": module_sequence_template,
        },
        "instructor_actions": [str(x.get("pattern") or "") for x in repeated_actions],
        "instructor_action_patterns": repeated_actions,
        "lab_patterns": repeated_lab_patterns,
        "troubleshooting_patterns": repeated_troubleshooting_patterns,
        "assessment_patterns": repeated_assessment_patterns,
        "visual_patterns": repeated_visual_patterns,
        "transition_patterns": repeated_transition_patterns,
        "analysis_stats": {
            "expert_courses_count": len(selected_presentations),
            "total_slides_analyzed": total_slides,
            "total_instructor_notes_analyzed": total_notes,
            "selection_warnings": selection_warnings,
            "recommended_dataset": recommended_dataset,
        },
    }

    payload = {
        "source_doc_id": normalized_doc_ids[0] if len(normalized_doc_ids) == 1 else "",
        "source_doc_ids": normalized_doc_ids,
        "fingerprint": fingerprint,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "master_teaching_blueprint": teaching_dna,
        "teaching_dna": teaching_dna,
        "summary": _compact_teaching_dna_summary(teaching_dna),
    }

    value = json.dumps(payload, ensure_ascii=False)
    if row:
        row.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    db.commit()

    return payload, False, key


def _build_ppt_reference_trace(slides: list[dict], ppt_refs: dict | None) -> list[dict]:
    """Build internal traceability list for slides influenced by PPT references."""
    if not isinstance(ppt_refs, dict):
        return []
    refs = ppt_refs.get("selected_references") or []
    if not refs:
        return []

    traces: list[dict] = []
    for s in slides:
        title = _normalized_text(s.get("title"))
        if not title:
            continue
        title_l = title.lower()
        matched = []
        for r in refs:
            ref_title = _normalized_text(r.get("reference_title")).lower()
            if ref_title and (ref_title in title_l or title_l in ref_title):
                matched.append(r)
            elif any(tok in title_l for tok in re.findall(r"[a-z0-9]{4,}", ref_title)[:4]):
                matched.append(r)
        for m in matched[:2]:
            traces.append({
                "slide_title": title,
                "reference_file": m.get("reference_file"),
                "reference_slide": m.get("reference_slide"),
                "reference_category": m.get("reference_category"),
                "how_used": "structure/style/terminology inspiration",
                "relevance_score": m.get("relevance_score"),
            })
    return traces


def _build_source_map(slides: list[dict], manual_index: dict, knowledge_map: dict) -> list[dict]:
    refs: list[dict] = []
    topics_by_title = {
        _normalized_text(t.get("topic_title")).lower(): t
        for t in (knowledge_map.get("topics") or [])
        if isinstance(t, dict)
    }
    for s in slides:
        title = _normalized_text(s.get("title"))
        t = topics_by_title.get(title.lower())
        page_hint = 0
        section = "General"
        if t:
            page_hint = int(t.get("source_page_number") or 0)
            section = _normalized_text(t.get("source_manual_section") or "General")
        elif s.get("source_pages"):
            page_hint = int((s.get("source_pages") or [0])[0] or 0)
        refs.append({
            "module_or_slide": title,
            "manual_section": section,
            "page_number": page_hint,
            "figure_numbers": [],
            "table_numbers": [],
        })

    figs = manual_index.get("figures") or []
    tables = manual_index.get("tables") or []
    for row in refs:
        p = int(row.get("page_number") or 0)
        if p <= 0:
            continue
        row["figure_numbers"] = sorted(set(
            fn for it in figs if int(it.get("page") or 0) == p for fn in it.get("figure_numbers", [])
        ))[:6]
        row["table_numbers"] = sorted(set(
            tn for it in tables if int(it.get("page") or 0) == p for tn in it.get("table_numbers", [])
        ))[:6]
    return refs


# ── PDF extraction ─────────────────────────────────────────────────────────────

def _extract_pdf_pages(pdf_bytes: bytes) -> tuple[int, list[dict]]:
    """
    Extract full text per page from a PDF using PyMuPDF.
    Stores complete text (no truncation) so generation has full context.
    """
    import fitz  # PyMuPDF

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for i, page in enumerate(doc, 1):
        raw = page.get_text("text") or ""
        text = re.sub(r"\n{3,}", "\n\n", raw).strip()
        pages.append({
            "page_num":   i,
            "text":       text,           # full text stored — no truncation
            "char_count": len(text),
        })
    doc.close()
    return len(pages), pages


def _build_manual_context(pages: list[dict], max_chars: int = 60_000) -> str:
    """
    Build a training context string from extracted pages.
    Uses full stored text. Respects a generous token budget.
    """
    parts = []
    total = 0
    for p in pages:
        text = p.get("text", "").strip()
        if not text:
            continue
        entry = f"\n--- PAGE {p['page_num']} ---\n{text}"
        if total + len(entry) > max_chars:
            # Add as much as fits from this page
            remaining = max_chars - total
            if remaining > 200:
                parts.append(entry[:remaining])
            break
        parts.append(entry)
        total += len(entry)
    return "".join(parts)


# ── PDF structure analysis ─────────────────────────────────────────────────────

def _analyze_pdf_structure(pages: list[dict]) -> dict:
    """
    Analyse extracted pages for headings, tables, figures, warnings.
    Works purely from text — no image decoding needed.
    """
    all_text = "\n".join(p.get("text", "") for p in pages)
    total_chars = sum(p.get("char_count", 0) for p in pages)

    # Headings: short all-caps lines or numbered section titles
    heading_patterns = [
        re.compile(r"^[A-Z][A-Z\s\d\-\/\.]{3,70}$", re.MULTILINE),
        re.compile(r"^\d+(?:\.\d+)*\s+[A-Z][^\n]{3,70}$", re.MULTILINE),
        re.compile(r"^(?:Chapter|Section|Part)\s+\d+[^\n]{0,60}$", re.MULTILINE | re.IGNORECASE),
    ]
    headings_raw: list[str] = []
    for pat in heading_patterns:
        headings_raw.extend(m.strip() for m in pat.findall(all_text))
    # Deduplicate preserving order
    seen: set[str] = set()
    headings: list[str] = []
    for h in headings_raw:
        if h not in seen and len(h) > 4:
            seen.add(h)
            headings.append(h)
    headings = headings[:30]

    # Detect tables
    table_matches = re.findall(r"(?i)\btable\s+\d+", all_text)
    # Detect figures
    figure_matches = re.findall(r"(?i)\bfigure\s+\d+", all_text)
    # Detect images referenced (e.g. "Figure 3-2", "Fig. 4")
    fig_refs = re.findall(r"(?i)\bfig(?:ure)?\.?\s*[\d\-]+", all_text)
    # Safety callouts
    warning_count = len(re.findall(r"(?i)\b(?:warning|caution|danger)\b", all_text))

    return {
        "page_count":      len(pages),
        "total_chars":     total_chars,
        "estimated_words": total_chars // 5,
        "headings":        headings,
        "heading_count":   len(headings),
        "table_count":     len(set(table_matches)),
        "figure_count":    len(set(fig_refs)),
        "warning_count":   warning_count,
        "content_pages":   sum(1 for p in pages if p.get("char_count", 0) > 100),
    }


# ── Slide generation prompts ───────────────────────────────────────────────────

# ── Course classification ──────────────────────────────────────────────────────

_MAINTENANCE_KEYWORDS = {
    "maintenance engineer", "field service engineer", "service technician",
    "fse", "maintenance technician", "service engineer",
}
_OPERATOR_KEYWORDS = {
    "operator", "x-ray operator", "security officer", "screener",
}
_RADIATION_KEYWORDS = {
    "radiation safety", "rso", "radiation protection",
}

_MAINTENANCE_COURSE_TYPES = {
    "full service course", "field service course", "maintenance training",
    "corrective maintenance", "preventive maintenance", "service course",
    "maintenance and troubleshooting",
}
_OPERATOR_COURSE_TYPES = {
    "operator training", "user training", "operator awareness",
}

_CHAPTER_CATEGORIES = {
    "safety":          ["safety", "radiation", "hazard", "warning", "ppe", "interlock", "emergency", "protection"],
    "system_overview": ["overview", "introduction", "system description", "architecture", "purpose", "theory"],
    "mechanical":      ["mechanical", "structure", "frame", "chassis", "conveyor", "belt", "housing", "enclosure"],
    "electrical":      ["electrical", "power", "voltage", "circuit", "wiring", "generator", "ups", "distribution", "shore"],
    "xray":            ["x-ray", "xray", "source", "hoop", "tube", "beam", "detector", "backscatter", "dose", "kv", "ma"],
    "hvps":            ["high voltage", "hvps", "hv supply", "high-voltage"],
    "cooling":         ["cooling", "thermal", "temperature", "coolant", "fan", "heat", "chiller", "fluid"],
    "detectors":       ["detector", "pmt", "scintillator", "photomultiplier", "daq", "data acquisition", "image"],
    "electronics":     ["pcb", "board", "controller", "source board", "hoop board", "electronics", "control unit"],
    "software":        ["software", "firmware", "acquisition", "computer", "diagnostic", "hmi", "gui", "screen"],
    "pm":              ["preventive maintenance", "pm schedule", "inspection", "periodic", "interval", "lubrication"],
    "corrective":      ["corrective maintenance", "fault repair", "component replacement", "removal", "installation"],
    "troubleshooting": ["troubleshoot", "fault isolation", "fault diagnosis", "error code", "alarm", "symptom"],
    "calibration":     ["calibration", "functional test", "acceptance test", "test procedure", "commissioning"],
    "practical":       ["exercise", "lab", "practical", "hands-on", "procedure"],
    "assessment":      ["exam", "test", "quiz", "assessment", "question"],
}


_PROCEDURAL_CONTENT_RE = re.compile(
    r"\bstep\s*\d|\btorque\b|\bp/n\b|\bpart\s*number\b|\bremove the\b|\breplace the\b|"
    r"\binstall the\b|\bcalibrat|\btool required\b|\blockout\b|\btagout\b|\bclevis pin\b|"
    r"\bcircuit breaker\b|\bfield replaceable\b|\bpm interval\b|\bwarning:\b|\bcaution:\b",
    re.IGNORECASE,
)


def _manual_has_procedural_content(manual_context: str, min_hits: int = 5) -> bool:
    """Cheap signal for whether the source manual actually describes physical
    procedures (removal/replacement/calibration/torque/lockout steps), as
    opposed to being purely conceptual/theoretical (e.g. a physics-principles
    reference). Audience alone ("Field Service Engineers") isn't enough to
    justify inventing hands-on labs — observed live: a 27-page pure physics
    reference with zero procedures still produced fabricated calibration labs
    because classification was audience-driven only. Require actual textual
    evidence of procedures before treating the course as hands-on/maintenance
    for prompt purposes.
    """
    return len(_PROCEDURAL_CONTENT_RE.findall(manual_context or "")) >= min_hits


def _classify_course(audience: str, training_type: str) -> dict:
    """
    Classify the course and return content priorities, slide targets, and distribution limits.
    """
    aud = audience.lower()
    ctype = training_type.lower()

    is_maintenance = (
        any(k in aud for k in _MAINTENANCE_KEYWORDS)
        or any(k in ctype for k in _MAINTENANCE_COURSE_TYPES)
    )
    is_operator = (
        any(k in aud for k in _OPERATOR_KEYWORDS)
        and not is_maintenance
    )
    is_radiation = any(k in ctype for k in _RADIATION_KEYWORDS)

    if is_maintenance:
        category = "maintenance"
        max_safety_pct = 0.15
        priority_modules = [
            "System Overview & Architecture",
            "Power Generation & Distribution",
            "X-Ray Source & Hoop Assembly",
            "High Voltage Power Supply",
            "Cooling & Thermal Management",
            "Detectors & PMTs",
            "DAQ & Image Acquisition",
            "Control Electronics & PCBs",
            "Software & Diagnostics",
            "Preventive Maintenance",
            "Corrective Maintenance",
            "Fault Isolation & Troubleshooting",
            "Calibration & Functional Testing",
            "Component Removal & Replacement",
            "Practical Maintenance Exercises",
        ]
        required_modules = ["maintenance procedures", "troubleshooting", "diagnostics", "system architecture"]
        depth_note = (
            "This is a MAINTENANCE TRAINING course for engineers. "
            "Safety is mandatory but must NOT dominate — cap at 10–15% of slides. "
            "The bulk of content MUST cover: system architecture, subsystem descriptions, "
            "maintenance procedures, diagnostics, fault isolation, and practical exercises. "
            "Every engineering module must state: purpose, components, signal flow, test points, "
            "common faults, fault-isolation logic, corrective actions, and PM requirements. "
            "Do NOT generate vague overviews. Generate deep engineering content."
        )
    elif is_radiation:
        category = "radiation_safety"
        max_safety_pct = 0.80
        priority_modules = [
            "Radiation Fundamentals",
            "Regulatory Framework",
            "Dose Limits",
            "Detection & Measurement",
            "Protective Measures",
            "Emergency Procedures",
        ]
        required_modules = ["radiation fundamentals", "dose limits", "protective measures"]
        depth_note = "This is a Radiation Safety course. Focus on regulatory standards and protective procedures."
    else:
        category = "operator"
        max_safety_pct = 0.30
        priority_modules = [
            "System Overview",
            "Safety & Radiation Awareness",
            "Control Panel & HMI",
            "Normal Operating Procedures",
            "Alarm Interpretation",
            "Image Interpretation",
            "Emergency Procedures",
        ]
        required_modules = ["operating procedures", "alarm response", "safety"]
        depth_note = (
            "This is an OPERATOR TRAINING course. Focus on operating procedures, "
            "control panel operation, alarm interpretation, and safety awareness. "
            "Technical engineering depth is secondary."
        )

    return {
        "category": category,
        "is_maintenance": is_maintenance,
        "is_operator": is_operator,
        "is_radiation": is_radiation,
        "max_safety_pct": max_safety_pct,
        "priority_modules": priority_modules,
        "required_modules": required_modules,
        "depth_note": depth_note,
    }


def _classify_chapters(headings: list[str]) -> dict[str, list[str]]:
    """Map each detected heading into a content category."""
    classified: dict[str, list[str]] = {cat: [] for cat in _CHAPTER_CATEGORIES}
    classified["other"] = []
    for h in headings:
        hl = h.lower()
        matched = False
        for cat, keywords in _CHAPTER_CATEGORIES.items():
            if any(kw in hl for kw in keywords):
                classified[cat].append(h)
                matched = True
                break
        if not matched:
            classified["other"].append(h)
    return {k: v for k, v in classified.items() if v}


def _target_slide_count(slide_depth: str, duration: str) -> tuple[int, int]:
    """Return (min_slides, max_slides) based on depth and duration."""
    depth_base = {
        "concise":   (40,  80),
        "standard":  (80, 150),
        "detailed":  (150, 220),
        "full_cert": (200, 300),
    }.get(slide_depth, (80, 150))

    dur_l = duration.lower()
    if "5" in dur_l or "full" in dur_l:
        scale = 1.5
    elif "3" in dur_l:
        scale = 1.0
    elif "2" in dur_l:
        scale = 0.7
    else:  # 1 day or half day
        scale = 0.5

    lo = max(30, int(depth_base[0] * scale))
    hi = max(lo + 20, int(depth_base[1] * scale))
    return lo, hi


def _compute_content_distribution(slide_dicts: list[dict], classification: dict) -> dict:
    """Compute content-type distribution and run quality gate checks."""
    total = len(slide_dicts)
    if total == 0:
        return {"passed": False, "errors": ["No slides generated"]}

    type_counts: dict[str, int] = {}
    for s in slide_dicts:
        st = s.get("type", "content")
        type_counts[st] = type_counts.get(st, 0) + 1

    # Count "safety" slides by scanning titles/bullets for safety keywords
    safety_kw = re.compile(r"\b(radiation|safety|hazard|ppe|warning|caution|danger)\b", re.I)
    safety_slides = sum(
        1 for s in slide_dicts
        if safety_kw.search(s.get("title", "")) or
           any(safety_kw.search(str(b)) for b in s.get("bullets", [])[:2])
    )
    safety_pct = safety_slides / total

    maintenance_kw = re.compile(
        r"\b(maintenance|troubleshoot|fault|diagnostic|calibrat|procedure|repair|replace|inspect|test point)\b", re.I
    )
    maint_slides = sum(
        1 for s in slide_dicts
        if maintenance_kw.search(s.get("title", "")) or
           any(maintenance_kw.search(str(b)) for b in s.get("bullets", [])[:2])
    )

    content_slides = type_counts.get("content", 0)
    quiz_slides = type_counts.get("quiz", 0)
    practical_slides = type_counts.get("practical", 0)
    section_slides = type_counts.get("section", 0)

    errors: list[str] = []
    warnings: list[str] = []

    max_safety = classification.get("max_safety_pct", 0.30)
    if safety_pct > max_safety:
        errors.append(
            f"Safety/radiation content is {safety_pct:.0%} of slides "
            f"(limit for {classification['category']} course: {max_safety:.0%}). "
            "The course is dominated by radiation/safety material."
        )

    if classification.get("is_maintenance"):
        if maint_slides < total * 0.30:
            errors.append(
                f"Only {maint_slides}/{total} slides cover maintenance/troubleshooting. "
                "A maintenance course needs at least 30% maintenance content."
            )
        if practical_slides < 3:
            warnings.append("Fewer than 3 practical exercises generated for a maintenance course.")
        if content_slides < 20:
            warnings.append(f"Only {content_slides} content slides. A full service course needs 40+.")

    if quiz_slides < 3:
        warnings.append("Fewer than 3 knowledge checks generated.")

    # Check for truncated question options
    for s in slide_dicts:
        if s.get("type") == "quiz":
            for opt in s.get("bullets", []):
                if isinstance(opt, str) and len(opt) > 0 and opt[0].islower() and opt[0] not in "aeiou":
                    warnings.append(f"Possible truncated quiz option: '{opt[:30]}...'")
                    break

    passed = len(errors) == 0
    return {
        "passed": passed,
        "total_slides": total,
        "safety_pct": round(safety_pct * 100, 1),
        "maintenance_slides": maint_slides,
        "type_counts": type_counts,
        "errors": errors,
        "warnings": warnings,
        "max_safety_pct_allowed": round(max_safety * 100, 1),
    }


_GENERATION_SYSTEM = """You are a certified technical training developer with the style and standards of a
professional Rapiscan Systems Field Service Engineer instructor.

IDENTITY MANDATE (NON-NEGOTIABLE):
You are not a summarizer. You are a world-class instructor team operating as one mind:
- International Technical Trainer
- Subject Matter Expert (SME)
- Senior Field Service Engineer
- Instructional Designer
- Adult Learning Specialist
- Technical Writer
- Training Manager
- Curriculum Designer
- Assessment Designer
- Educational Psychologist
- Visual Communication Designer
- Technical Illustrator
- Troubleshooting Expert
- Maintenance Expert
- Radiation Safety Specialist
- Engineering Mentor

Before generating each lesson, think and design like a human instructor:
- Why this topic matters operationally
- What students usually misunderstand
- What beginners do wrong in the field
- What practical experience must be gained
- Which concepts require diagrams/flowcharts/decision trees
- Which concepts require labs/workshops/discussion
- Which concepts require assessment and reinforcement

STYLE REFERENCE:
You match the instructional design language of the Rapiscan ZBV Level 3 Field Service Course —
a 243-slide professional training deck used to qualify field service engineers on X-ray screening systems.

INSTRUCTIONAL DESIGN RULES (match the reference style exactly):

1. LESSON OBJECTIVE SLIDES — always open with:
   "By the end of this lesson, utilizing student guide materials, you will be able to [describe/identify/perform/state]:"
   Then list 4-6 specific, measurable objectives. Each objective ends with (p.N).

2. CONTENT SLIDES — follow this hierarchy:
   - Main bullet: concise factual statement with (p.N) citation
   - Sub-bullet (starts with 2 spaces): specific detail, measurement, or example
   - Never write more than 6 bullets on one slide
   - Never use vague openers like "This section covers..." — state facts directly

3. KNOWLEDGE CHECK SLIDES — format as:
   - title: A direct question from the content (e.g. "What is the maximum operating voltage?")
   - bullets: Exactly 4 options, one clearly correct (A/B/C/D labels optional in text)
   - answer_index: 0-3 (0=first option is correct)
   - speaker_notes: "Answer: [letter] — [one-sentence explanation with (p.N)]"
   - Place one knowledge check per major section, after the section content

4. PRACTICAL EXERCISE SLIDES — format as:
   - title: "Lab Exercise: [Task Name]" or "Practical: [Task Name]"
   - bullets: Numbered step-by-step procedure, each step ending with (p.N)
   - Steps must be specific and executable, not vague
   - speaker_notes: "Allow [X] minutes. [Solo/Pairs]. [Facilitation tip]."

5. SPEAKER NOTES — write as a professional instructor speaking to another instructor:
   - Use direct language: "Emphasize that...", "Ask the class...", "Point out...", "Refer students to page..."
   - Include timing guidance on practical and exercise slides
   - Flag safety-critical points: "⚠ Safety point: ..."
   - Add discussion prompts on complex topics
   - Never repeat the slide bullets verbatim — add context, emphasis, and facilitation guidance

6. SECTION DIVIDER SLIDES — set the stage:
   - bullets[0]: One sentence describing what this section covers and why it matters
   - speaker_notes: Brief transition note for the instructor

7. CITATIONS — mandatory:
   - Every technical fact, specification, procedure step, and measurement MUST cite (p.N)
   - If a fact appears across multiple pages: (p.N, p.M)
   - Never invent or estimate page numbers
   - If not in the manual: write [Not found in uploaded manual]

8. TECHNICAL ACCURACY:
   - Use only information from the provided manual
   - Copy measurements, part numbers, error codes, and procedures exactly as written
   - Never paraphrase safety warnings — quote them accurately with the page citation
    - If the manual uses specific terminology, use that exact terminology

9. NEVER SUMMARIZE THE MANUAL:
    - You are designing a complete learning experience, not compressing text.
    - Teach diagnostic reasoning, not facts only.
    - In every major lesson include WHY it matters, failure consequences, and how senior engineers think.

10. INSTRUCTOR-GRADE DELIVERY:
    - Instructor notes must include: how to explain, questions to ask, demonstrations, field stories,
      common trainee mistakes, timing guidance, discussion points, and hands-on coaching guidance.
    - Use explicit coaching language: "Ask", "Probe", "Challenge", "Demonstrate", "Debrief".
11. BUILD LEARNING EXPERIENCE, NOT TEXT SUMMARY:
        - Interpret, teach, explain, demonstrate, illustrate, coach, challenge, assess, reinforce.
        - If output starts to read like compressed manual notes, expand depth immediately.
"""

_OUTLINE_SYSTEM = """You are a senior technical training curriculum designer with the standards of a
Rapiscan Systems senior instructor developer.

Your job is to produce a complete, structured course outline grounded entirely in the uploaded manual.
You must classify each module by the type of content it covers, not by generic labels.
You must respect the course type and audience — a maintenance course for engineers must contain
engineering and maintenance content, not operator or radiation-safety theory as the majority."""


_AI_TRAINING_DIRECTOR_ENGINES = [
    "Curriculum Planner",
    "Technical Module Generator",
    "Training Material Generator",
    "Visual & Diagram Engine",
    "Assessment Engine",
    "AI Instructor Review",
]


_AI_TRAINING_DIRECTOR_PIPELINE = [
    "Read manual",
    "Search knowledge base",
    "Search PowerPoint references",
    "Analyze best human-created benchmark courses from knowledge base",
    "Build complete knowledge map",
    "Build learning map",
    "Build curriculum blueprint",
    "Estimate modules, lessons, and slide volume",
    "Plan laboratories, assessments, and diagrams",
    "Plan instructor notes, troubleshooting, and practical exercises",
    "Define quality targets per module",
    "Assign work across specialist generation engines",
    "Build technical modules",
    "Build student material",
    "Perform AI Instructor Review",
    "Assign missing work to the right engine",
    "Repeat improvements until quality target is achieved",
    "Export",
]


def _build_human_course_benchmark(
    db: Session,
    manual_index: dict,
    project_dict: dict,
    ppt_refs: dict,
    topic_queries: list[str],
    max_courses: int = 10,
) -> dict:
    """Build benchmark metrics/patterns from the best human-created KB courses."""
    try:
        from api.db.models import PptxPresentationIndex, PptxSlideIndex
    except Exception as err:
        log.warning("Human benchmark model import failed: %s", err)
        return {
            "courses_analyzed": 0,
            "benchmark_courses": [],
            "quality_metrics": {},
            "teaching_patterns": [],
            "guardrails": ["Never copy slides or text from reference courses."],
        }

    settings = project_dict.get("settings") or {}
    language = _normalized_text(project_dict.get("language") or "english").lower()
    course_type = _normalized_text(project_dict.get("training_type") or project_dict.get("course_type") or "")
    manual_equipment = manual_index.get("equipment") or {}
    model_l = _normalized_text(project_dict.get("equipment_model") or manual_equipment.get("model") or "").lower()
    mfr_l = _normalized_text(project_dict.get("manufacturer") or manual_equipment.get("manufacturer") or "").lower()

    presentations = (
        db.query(PptxPresentationIndex)
        .filter(PptxPresentationIndex.obsolete.is_(False))
        .filter(PptxPresentationIndex.do_not_use.is_(False))
        .all()
    )

    topic_tokens = set()
    for t in topic_queries[:16]:
        topic_tokens.update(re.findall(r"[a-z0-9]{3,}", _normalized_text(t).lower()))

    ranked: list[tuple[float, Any]] = []
    for p in presentations:
        trust_score = (
            1.0 if bool(p.manufacturer_approved) else
            0.9 if bool(p.trusted) else
            0.8 if bool(p.internal_training_reference) else
            0.2
        )
        if trust_score < 0.8:
            continue

        p_model = _normalized_text(getattr(p, "equipment_model", "")).lower()
        p_mfr = _normalized_text(getattr(p, "manufacturer", "")).lower()
        p_course = _normalized_text(getattr(p, "course_type", ""))
        p_topics = " ".join(str(x) for x in (getattr(p, "main_topics", []) or []))
        p_blob = " ".join([p_course, p_topics, _normalized_text(getattr(p, "course_title", ""))]).lower()
        blob_tokens = set(re.findall(r"[a-z0-9]{3,}", p_blob))
        topic_overlap = len(topic_tokens.intersection(blob_tokens)) / max(1.0, math.sqrt(len(topic_tokens) * max(1, len(blob_tokens)))) if topic_tokens else 0.0

        model_match = 1.0 if model_l and p_model and model_l == p_model else (0.6 if model_l and p_model and model_l in p_model else 0.0)
        mfr_match = 1.0 if mfr_l and p_mfr and mfr_l == p_mfr else 0.0
        course_match = _score_topic_similarity(course_type, p_course)
        lang_match = 1.0 if language.startswith(_normalized_text(getattr(p, "language", "english")).lower()[:3]) else 0.3

        score = 0.35 * trust_score + 0.22 * model_match + 0.16 * mfr_match + 0.14 * course_match + 0.09 * topic_overlap + 0.04 * lang_match
        ranked.append((score, p))

    ranked.sort(key=lambda x: x[0], reverse=True)
    selected_presentations = [p for _, p in ranked[:max_courses]]
    if not selected_presentations:
        return {
            "courses_analyzed": 0,
            "benchmark_courses": [],
            "quality_metrics": {},
            "teaching_patterns": [],
            "guardrails": ["Never copy slides or text from reference courses."],
        }

    pres_ids = [p.id for p in selected_presentations]
    slides = db.query(PptxSlideIndex).filter(PptxSlideIndex.presentation_id.in_(pres_ids)).all()
    by_pres: dict[str, list[Any]] = {}
    for s in slides:
        by_pres.setdefault(s.presentation_id, []).append(s)

    total_slides = 0
    total_modules = 0
    total_diagrams = 0
    total_assessments = 0
    total_practicals = 0
    total_notes = 0
    total_images = 0
    total_text_boxes = 0
    quality_accum = 0.0
    quality_count = 0
    total_objectives = 0
    total_summaries = 0
    total_troubleshooting = 0
    total_conceptual = 0
    assessment_intervals: list[int] = []

    benchmark_courses: list[dict] = []
    for p in selected_presentations:
        ps = by_pres.get(p.id, [])
        if not ps:
            continue
        ps_sorted = sorted(ps, key=lambda x: int(getattr(x, "slide_number", 0) or 0))
        total_slides += len(ps)

        module_like = 0
        diagram_like = 0
        assessment_like = 0
        practical_like = 0
        rich_notes = 0
        image_count = 0
        text_box_count = 0
        local_quality = 0.0

        for s in ps:
            title = _normalized_text(s.slide_title).lower()
            blob = " ".join([
                _normalized_text(s.slide_title),
                _normalized_text(s.slide_text),
                _normalized_text(s.speaker_notes),
                _normalized_text(s.table_content),
                _normalized_text(s.diagram_labels),
            ]).lower()
            layout = s.visual_layout_metadata if isinstance(s.visual_layout_metadata, dict) else {}
            q = float(s.quality_score or 0.0)

            if any(k in title for k in ["module", "section", "chapter", "lesson"]):
                module_like += 1
            if any(k in blob for k in ["objective", "outcome", "by the end", "you will be able"]):
                total_objectives += 1
            if any(k in blob for k in ["diagram", "schematic", "flow", "block", "signal", "process"]):
                diagram_like += 1
            if any(k in blob for k in ["quiz", "assessment", "knowledge check", "exam", "question"]):
                assessment_like += 1
            if any(k in blob for k in ["lab", "laboratory", "practical", "exercise", "hands-on"]):
                practical_like += 1
            if any(k in blob for k in ["summary", "recap", "review", "key takeaways", "debrief"]):
                total_summaries += 1
            if any(k in blob for k in ["troubleshoot", "fault", "diagnostic", "isolation", "verification", "decision tree"]):
                total_troubleshooting += 1
            if any(k in blob for k in ["principle", "theory", "concept", "mechanism", "architecture"]):
                total_conceptual += 1
            if len(_normalized_text(s.speaker_notes)) >= 80:
                rich_notes += 1

            image_count += int(layout.get("image_count") or 0)
            text_box_count += int(layout.get("text_boxes") or 0)
            local_quality += q

        assessment_positions = []
        for idx, s in enumerate(ps_sorted, start=1):
            ablob = " ".join([
                _normalized_text(s.slide_title),
                _normalized_text(s.slide_text),
                _normalized_text(s.speaker_notes),
            ]).lower()
            if any(k in ablob for k in ["quiz", "assessment", "knowledge check", "exam", "question"]):
                assessment_positions.append(idx)
        if len(assessment_positions) >= 2:
            for i in range(1, len(assessment_positions)):
                assessment_intervals.append(assessment_positions[i] - assessment_positions[i - 1])

        modules_for_course = max(1, module_like)
        total_modules += modules_for_course
        total_diagrams += diagram_like
        total_assessments += assessment_like
        total_practicals += practical_like
        total_notes += rich_notes
        total_images += image_count
        total_text_boxes += text_box_count
        quality_accum += local_quality
        quality_count += len(ps)

        benchmark_courses.append({
            "filename": p.filename,
            "course_title": p.course_title,
            "course_type": p.course_type,
            "slide_count": len(ps),
            "module_count": modules_for_course,
            "slides_per_module": round(len(ps) / max(1, modules_for_course), 2),
            "diagram_ratio": round(diagram_like / max(1, len(ps)), 3),
            "practical_ratio": round(practical_like / max(1, len(ps)), 3),
            "assessment_ratio": round(assessment_like / max(1, len(ps)), 3),
            "instructor_notes_ratio": round(rich_notes / max(1, len(ps)), 3),
            "avg_quality_score": round(local_quality / max(1, len(ps)), 3),
            "is_manufacturer_approved": bool(p.manufacturer_approved),
            "is_trusted": bool(p.trusted),
        })

    avg_quality = quality_accum / max(1, quality_count)
    avg_slides_per_module = total_slides / max(1, total_modules)
    diagram_ratio = total_diagrams / max(1, total_slides)
    practical_ratio = total_practicals / max(1, total_slides)
    assessment_ratio = total_assessments / max(1, total_slides)
    notes_ratio = total_notes / max(1, total_slides)
    avg_images_per_slide = total_images / max(1, total_slides)
    avg_text_boxes_per_slide = total_text_boxes / max(1, total_slides)
    objectives_per_module = total_objectives / max(1, total_modules)
    summary_ratio = total_summaries / max(1, total_slides)
    troubleshooting_ratio = total_troubleshooting / max(1, total_slides)
    theory_to_practice_ratio = total_conceptual / max(1, total_practicals)
    avg_assessment_interval = (sum(assessment_intervals) / max(1, len(assessment_intervals))) if assessment_intervals else 0.0

    patterns: list[str] = []
    if avg_slides_per_module >= 3:
        patterns.append("Human courses pace modules with sustained depth, not one-slide modules.")
    if diagram_ratio >= 0.18:
        patterns.append("Human courses use frequent diagrams/flows for technical explanation.")
    if practical_ratio >= 0.12:
        patterns.append("Human courses include regular practical/laboratory activities.")
    if assessment_ratio >= 0.10:
        patterns.append("Human courses assess understanding throughout modules, not only at the end.")
    if notes_ratio >= 0.18:
        patterns.append("Human courses contain rich instructor guidance and facilitation notes.")

    designer_principles: list[str] = []
    if objectives_per_module >= 0.7:
        designer_principles.append("Each module explicitly starts with measurable learning outcomes before deep content.")
    if 1.0 <= theory_to_practice_ratio <= 4.0:
        designer_principles.append("Theory and practice are deliberately balanced instead of isolated blocks.")
    if troubleshooting_ratio >= 0.12:
        designer_principles.append("Diagnostic reasoning is embedded across the course, not postponed to the end.")
    if avg_assessment_interval > 0 and avg_assessment_interval <= 12:
        designer_principles.append("Understanding is checked frequently through distributed assessments.")
    if summary_ratio >= 0.06:
        designer_principles.append("Reinforcement and recap moments are inserted to stabilize learning transfer.")

    designer_thinking_profile = {
        "signature": {
            "objectives_per_module": round(objectives_per_module, 3),
            "troubleshooting_ratio": round(troubleshooting_ratio, 3),
            "summary_ratio": round(summary_ratio, 3),
            "theory_to_practice_ratio": round(theory_to_practice_ratio, 3),
            "assessment_interval_slides": round(avg_assessment_interval, 3),
        },
        "principles": designer_principles,
        "mindset": [
            "Design the learning journey first, then distribute technical facts into that journey.",
            "Teach how experts think and decide under field constraints, not just what they memorize.",
            "Use objective -> explanation -> guided practice -> diagnosis -> verification as a repeatable rhythm.",
        ],
    }

    return {
        "courses_analyzed": len(benchmark_courses),
        "benchmark_courses": benchmark_courses,
        "quality_metrics": {
            "target_slides_per_module": round(avg_slides_per_module, 2),
            "target_diagram_ratio": round(diagram_ratio, 3),
            "target_practical_ratio": round(practical_ratio, 3),
            "target_assessment_ratio": round(assessment_ratio, 3),
            "target_instructor_notes_ratio": round(notes_ratio, 3),
            "target_images_per_slide": round(avg_images_per_slide, 3),
            "target_text_boxes_per_slide": round(avg_text_boxes_per_slide, 3),
            "target_overall_quality_score": _score_0_100(avg_quality * 100),
        },
        "teaching_patterns": patterns,
        "designer_thinking_profile": designer_thinking_profile,
        "guardrails": [
            "Use benchmark references to learn teaching patterns only.",
            "Never copy reference slide text or layout verbatim.",
            "Uploaded manual remains the authoritative technical source.",
        ],
    }


def _build_training_director_blueprint(
    project_dict: dict,
    structure: dict,
    manual_index: dict,
    knowledge_map: dict,
    learning_map: dict,
    curriculum_map: dict,
    instruction_plan: dict,
    assessments: dict,
    visuals: list[dict],
    ppt_refs: dict,
    human_benchmark: dict,
) -> dict:
    """Create a pre-slide orchestration blueprint for AI Training Director."""
    settings = project_dict.get("settings") or {}
    min_slides, max_slides = _target_slide_count(settings.get("slide_depth", "standard"), settings.get("duration", "3 days"))

    modules = curriculum_map.get("modules") or []
    sequencing = learning_map.get("sequencing") or []
    lesson_plans = instruction_plan.get("lesson_plans") or []
    visual_count = len(visuals or [])
    assessment_count = len((assessments.get("instructor_answer_key") or []))
    practical_lessons = 0
    troubleshooting_lessons = 0

    for plan in lesson_plans:
        text = " ".join([
            _normalized_text(plan.get("lesson_title")),
            _normalized_text(plan.get("teaching_strategy")),
            _normalized_text(plan.get("laboratory_strategy")),
            _normalized_text(plan.get("assessment_strategy")),
            " ".join(_normalized_text(x) for x in (plan.get("common_mistakes") or [])[:4]),
        ]).lower()
        if any(k in text for k in ["lab", "laboratory", "hands-on", "exercise"]):
            practical_lessons += 1
        if any(k in text for k in ["fault", "troubleshoot", "diagnostic", "isolation", "verification"]):
            troubleshooting_lessons += 1

    lessons_estimate = sum(len(m.get("lessons") or []) for m in modules)
    if lessons_estimate <= 0:
        lessons_estimate = max(6, len(sequencing))

    modules_estimate = len(modules) or max(4, len({str(s.get("topic") or "") for s in sequencing if s.get("topic")}))
    estimated_slides = max(min_slides, min(max_slides, int(round(max(1, lessons_estimate) * 2.6))))

    bench_metrics = human_benchmark.get("quality_metrics") if isinstance(human_benchmark.get("quality_metrics"), dict) else {}
    designer_profile = human_benchmark.get("designer_thinking_profile") if isinstance(human_benchmark.get("designer_thinking_profile"), dict) else {}
    profile_signature = designer_profile.get("signature") if isinstance(designer_profile.get("signature"), dict) else {}
    benchmark_slides_per_module = float(bench_metrics.get("target_slides_per_module") or 0)
    if benchmark_slides_per_module > 0 and modules_estimate > 0:
        benchmark_slide_target = int(round(modules_estimate * benchmark_slides_per_module))
        estimated_slides = max(estimated_slides, min(max_slides, benchmark_slide_target))

    module_quality_targets = []
    for idx, mod in enumerate(modules[:50], start=1):
        title = _normalized_text(mod.get("module_title")) or f"Module {idx}"
        lesson_count = len(mod.get("lessons") or [])
        module_quality_targets.append({
            "module_title": title,
            "lesson_target": max(1, lesson_count),
            "slide_target": max(4, lesson_count * 2),
            "minimum_scores": {
                "technical_completeness": max(78, int(bench_metrics.get("target_overall_quality_score") or 82) - 4),
                "instructional_quality": max(78, int(bench_metrics.get("target_overall_quality_score") or 82) - 3),
                "visual_quality": max(72, int((bench_metrics.get("target_diagram_ratio") or 0.2) * 100)),
                "laboratory_coverage": max(72, int((bench_metrics.get("target_practical_ratio") or 0.15) * 100)),
                "assessment_quality": max(72, int((bench_metrics.get("target_assessment_ratio") or 0.12) * 100)),
            },
        })

    preflight_checks = {
        "manual_analysis": bool(structure.get("page_count")) and bool(manual_index.get("sections")),
        "knowledge_base_search": bool(knowledge_map.get("topics")),
        "powerpoint_search": bool((ppt_refs.get("searched_files") or 0) >= 0),
        "human_course_benchmark_analysis": bool(human_benchmark.get("courses_analyzed", 0) > 0),
        "curriculum_blueprint": bool(modules_estimate > 0),
        "module_estimate": bool(modules_estimate > 0),
        "lesson_estimate": bool(lessons_estimate > 0),
        "slide_estimate": bool(estimated_slides > 0),
        "laboratory_plan": practical_lessons > 0,
        "assessment_plan": assessment_count > 0,
        "diagram_plan": visual_count > 0,
        "instructor_notes_plan": bool(lesson_plans),
        "troubleshooting_plan": troubleshooting_lessons > 0,
        "practical_exercises_plan": practical_lessons > 0,
        "module_quality_targets": bool(module_quality_targets),
    }

    completion_pct = int(round((sum(1 for _, ok in preflight_checks.items() if ok) / max(1, len(preflight_checks))) * 100))

    return {
        "identity": "AI Training Director",
        "objective": "Design, supervise, coordinate, review, and continuously improve end-to-end course generation.",
        "supervised_engines": _AI_TRAINING_DIRECTOR_ENGINES,
        "pre_slide_pipeline": _AI_TRAINING_DIRECTOR_PIPELINE,
        "human_course_benchmark": human_benchmark,
        "human_designer_profile": designer_profile,
        "preflight_checks": preflight_checks,
        "estimates": {
            "modules": modules_estimate,
            "lessons": lessons_estimate,
            "slides": estimated_slides,
            "slide_min": min_slides,
            "slide_max": max_slides,
            "planned_laboratories": max(1, practical_lessons),
            "planned_assessments": max(1, assessment_count),
            "planned_diagrams": max(1, visual_count),
            "planned_instructor_notes": max(1, len(lesson_plans)),
            "planned_troubleshooting_scenarios": max(1, troubleshooting_lessons),
            "planned_practical_exercises": max(1, practical_lessons),
        },
        "quality_targets": {
            "overall_score": max(82, int(bench_metrics.get("target_overall_quality_score") or 82)),
            "minimum_category_score": max(72, int((bench_metrics.get("target_overall_quality_score") or 82) - 10)),
            "benchmark_metrics": bench_metrics,
            "designer_signature_targets": profile_signature,
            "module_targets": module_quality_targets,
        },
        "dashboard": {
            "overall_completion": completion_pct,
            "remaining_tasks": [k for k, ok in preflight_checks.items() if not ok],
        },
    }


def _director_assignments(
    dashboard: dict,
    completeness: dict,
    quality_distribution: dict,
    quality_review: dict,
    benchmark_gaps: dict | None = None,
) -> list[dict]:
    """Map deficiencies to specialized engines instead of generic failure blocking."""
    assignments: list[dict] = []
    category_map = {
        "diagram_coverage": ("Visual & Diagram Engine", "Generate missing technical diagrams and flow visuals."),
        "visual_quality": ("Visual & Diagram Engine", "Improve visual clarity, labels, and educational visual sequence."),
        "technical_depth": ("Technical Module Generator", "Increase subsystem depth, diagnostic logic, and engineering reasoning."),
        "technical_completeness": ("Technical Module Generator", "Add missing specifications, procedures, and field technical depth."),
        "engineering_quality": ("Technical Module Generator", "Strengthen power/signal flow, interlocks, and component interactions."),
        "scientific_accuracy": ("Technical Module Generator", "Correct unsupported technical claims and tighten source-backed accuracy."),
        "laboratory_coverage": ("Curriculum Planner", "Add laboratory activities aligned to each major technical module."),
        "practical_exercises": ("Curriculum Planner", "Add practical exercises with tools, steps, and acceptance criteria."),
        "module_coverage": ("Curriculum Planner", "Add missing modules and rebalance curriculum sequencing."),
        "assessments": ("Assessment Engine", "Add missing knowledge checks and scenario assessments."),
        "assessment_quality": ("Assessment Engine", "Improve assessment quality, alignment, and answer rationale."),
        "learning_progression": ("Training Material Generator", "Improve lesson flow from objective to content to practice and review."),
        "instructional_quality": ("Training Material Generator", "Improve teachability and instructor facilitation quality."),
        "instructor_notes": ("Training Material Generator", "Add richer coaching notes, probing questions, and debrief guidance."),
        "student_engagement": ("Training Material Generator", "Increase interactive prompts and learner engagement moments."),
        "troubleshooting_coverage": ("Technical Module Generator", "Add troubleshooting scenarios with decision paths and verification steps."),
    }

    for cat in dashboard.get("weak_categories") or []:
        engine, directive = category_map.get(cat, ("Curriculum Planner", f"Improve {cat.replace('_', ' ')}."))
        assignments.append({"engine": engine, "category": cat, "directive": directive, "priority": "high"})

    for reason in (completeness.get("reasons") or []):
        txt = _normalized_text(reason).lower()
        if "diagram" in txt:
            engine = "Visual & Diagram Engine"
        elif "assessment" in txt or "quiz" in txt:
            engine = "Assessment Engine"
        elif "practical" in txt or "lab" in txt or "module" in txt:
            engine = "Curriculum Planner"
        elif "troubleshoot" in txt or "technical" in txt:
            engine = "Technical Module Generator"
        else:
            engine = "Training Material Generator"
        assignments.append({"engine": engine, "category": "completeness", "directive": reason, "priority": "high"})

    for issue in (quality_review.get("issues") or [])[:8]:
        assignments.append({
            "engine": "Training Material Generator",
            "category": "quality_review",
            "directive": issue,
            "priority": "medium",
        })

    benchmark_gaps = benchmark_gaps or {}
    for gap in (benchmark_gaps.get("missing_areas") or []):
        txt = _normalized_text(gap).lower()
        if "diagram" in txt or "visual" in txt:
            engine = "Visual & Diagram Engine"
        elif "assessment" in txt or "quiz" in txt:
            engine = "Assessment Engine"
        elif "practical" in txt or "laboratory" in txt:
            engine = "Curriculum Planner"
        elif "technical" in txt or "troubleshoot" in txt:
            engine = "Technical Module Generator"
        else:
            engine = "Training Material Generator"
        assignments.append({"engine": engine, "category": "benchmark_gap", "directive": gap, "priority": "high"})

    # Preserve order while removing duplicates.
    out: list[dict] = []
    seen = set()
    for a in assignments:
        key = (a.get("engine"), _normalized_text(a.get("directive")).lower())
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out[:30]


def _analyze_against_human_benchmark(slides: list[dict], quality_dashboard: dict, benchmark: dict) -> dict:
    metrics = benchmark.get("quality_metrics") if isinstance(benchmark.get("quality_metrics"), dict) else {}
    designer_profile = benchmark.get("designer_thinking_profile") if isinstance(benchmark.get("designer_thinking_profile"), dict) else {}
    designer_signature = designer_profile.get("signature") if isinstance(designer_profile.get("signature"), dict) else {}
    summary = quality_dashboard.get("summary") if isinstance(quality_dashboard.get("summary"), dict) else {}
    if not metrics and not designer_signature:
        return {
            "evaluated": False,
            "passes": True,
            "missing_areas": [],
            "current": {},
            "targets": {},
        }

    total = max(1, len(slides))
    modules = max(1, int(summary.get("modules") or 0))
    practicals = int(summary.get("practicals") or 0)
    assessments = int(summary.get("assessments") or 0)
    diagrams = int(summary.get("diagrams") or 0)
    rich_notes = int(summary.get("rich_instructor_notes") or 0)
    objectives = int(summary.get("objectives") or 0)
    troubleshooting = int(summary.get("troubleshooting") or 0)
    content_slides = int(summary.get("content_slides") or 0)

    current = {
        "slides_per_module": round(total / modules, 3),
        "diagram_ratio": round(diagrams / total, 3),
        "practical_ratio": round(practicals / total, 3),
        "assessment_ratio": round(assessments / total, 3),
        "instructor_notes_ratio": round(rich_notes / total, 3),
        "objectives_per_module": round(objectives / max(1, modules), 3),
        "troubleshooting_ratio": round(troubleshooting / total, 3),
        "summary_ratio": round(int(summary.get("summary_slides") or 0) / total, 3),
        "theory_to_practice_ratio": round(content_slides / max(1, practicals), 3),
        "assessment_interval_slides": round(total / max(1, assessments), 3),
        "overall_quality_score": int(quality_dashboard.get("overall_score") or 0),
    }
    targets = {
        "slides_per_module": float(metrics.get("target_slides_per_module") or 0),
        "diagram_ratio": float(metrics.get("target_diagram_ratio") or 0),
        "practical_ratio": float(metrics.get("target_practical_ratio") or 0),
        "assessment_ratio": float(metrics.get("target_assessment_ratio") or 0),
        "instructor_notes_ratio": float(metrics.get("target_instructor_notes_ratio") or 0),
        "objectives_per_module": float(designer_signature.get("objectives_per_module") or 0),
        "troubleshooting_ratio": float(designer_signature.get("troubleshooting_ratio") or 0),
        "summary_ratio": float(designer_signature.get("summary_ratio") or 0),
        "theory_to_practice_ratio": float(designer_signature.get("theory_to_practice_ratio") or 0),
        "assessment_interval_slides": float(designer_signature.get("assessment_interval_slides") or 0),
        "overall_quality_score": int(metrics.get("target_overall_quality_score") or 0),
    }

    missing: list[str] = []
    if targets["slides_per_module"] > 0 and current["slides_per_module"] + 0.25 < targets["slides_per_module"]:
        missing.append("Lesson pacing is below benchmark (insufficient slides per module depth).")
    if targets["diagram_ratio"] > 0 and current["diagram_ratio"] + 0.03 < targets["diagram_ratio"]:
        missing.append("Insufficient diagram usage versus best human benchmark courses.")
    if targets["practical_ratio"] > 0 and current["practical_ratio"] + 0.03 < targets["practical_ratio"]:
        missing.append("Practical/laboratory exercise density is below benchmark.")
    if targets["assessment_ratio"] > 0 and current["assessment_ratio"] + 0.03 < targets["assessment_ratio"]:
        missing.append("Assessment coverage is weaker than benchmark.")
    if targets["instructor_notes_ratio"] > 0 and current["instructor_notes_ratio"] + 0.03 < targets["instructor_notes_ratio"]:
        missing.append("Instructor guidance density is weaker than benchmark courses.")
    if targets["overall_quality_score"] > 0 and current["overall_quality_score"] < targets["overall_quality_score"]:
        missing.append("Overall educational quality score is below human benchmark target.")
    if targets["objectives_per_module"] > 0 and current["objectives_per_module"] + 0.15 < targets["objectives_per_module"]:
        missing.append("Module learning-objective cadence is below master human designer pattern.")
    if targets["troubleshooting_ratio"] > 0 and current["troubleshooting_ratio"] + 0.03 < targets["troubleshooting_ratio"]:
        missing.append("Troubleshooting and diagnostic-thinking density is below designer benchmark.")
    if targets["summary_ratio"] > 0 and current["summary_ratio"] + 0.02 < targets["summary_ratio"]:
        missing.append("Reinforcement/recap moments are weaker than benchmark designer rhythm.")
    if targets["theory_to_practice_ratio"] > 0 and current["theory_to_practice_ratio"] > targets["theory_to_practice_ratio"] + 1.2:
        missing.append("Theory-to-practice balance is too theoretical versus benchmark designer style.")
    if targets["assessment_interval_slides"] > 0 and current["assessment_interval_slides"] > targets["assessment_interval_slides"] + 1.5:
        missing.append("Assessment cadence is too sparse versus benchmark designer pattern.")

    return {
        "evaluated": True,
        "passes": len(missing) == 0,
        "missing_areas": missing,
        "current": current,
        "targets": targets,
    }


def _build_training_director_dashboard(
    director_blueprint: dict,
    quality_dashboard: dict,
    quality_distribution: dict,
    completeness: dict,
    remaining_tasks: list[dict],
    benchmark_gaps: dict | None = None,
) -> dict:
    scores = quality_dashboard.get("scores") or {}
    educational = int(scores.get("educational_completeness") or 0)
    technical = int(scores.get("technical_completeness") or 0)
    visual = int(scores.get("visual_quality") or 0)
    labs = int(scores.get("laboratory_coverage") or 0)
    assessments = int(scores.get("assessment_quality") or scores.get("assessments") or 0)
    kb_use = int(scores.get("knowledge_base_utilization") or 0)
    ppt_use = int(scores.get("powerpoint_reference_utilization") or 0)

    base_completion = int(director_blueprint.get("dashboard", {}).get("overall_completion") or 0)
    qa_completion = int(round((quality_dashboard.get("overall_score") or 0) * 0.6 + (100 if quality_dashboard.get("passes_threshold") else 60) * 0.4))
    overall_completion = int(round((base_completion * 0.35) + (qa_completion * 0.65)))

    remaining_labels = [
        f"{t.get('engine')}: {t.get('directive')}" for t in remaining_tasks[:16]
    ]
    if not remaining_labels and (completeness.get("reasons") or []):
        remaining_labels = [str(x) for x in (completeness.get("reasons") or [])[:12]]

    benchmark_gaps = benchmark_gaps or {}
    designer_profile = director_blueprint.get("human_designer_profile") if isinstance(director_blueprint.get("human_designer_profile"), dict) else {}
    designer_principles = designer_profile.get("principles") if isinstance(designer_profile.get("principles"), list) else []

    return {
        "overall_completion": _score_0_100(overall_completion),
        "overall_quality_score": int(quality_dashboard.get("overall_score") or 0),
        "educational_completeness": educational,
        "technical_completeness": technical,
        "visual_completeness": visual,
        "laboratory_coverage": labs,
        "assessment_coverage": assessments,
        "knowledge_base_utilization": kb_use,
        "powerpoint_utilization": ppt_use,
        "remaining_tasks": remaining_labels,
        "supervised_engines": _AI_TRAINING_DIRECTOR_ENGINES,
        "quality_targets": director_blueprint.get("quality_targets") or {},
        "human_benchmark": {
            "evaluated": bool(benchmark_gaps.get("evaluated")),
            "passes": bool(benchmark_gaps.get("passes", True)),
            "missing_areas": benchmark_gaps.get("missing_areas") or [],
            "designer_principles": designer_principles[:8],
        },
        "distribution_summary": {
            "total_slides": int(quality_distribution.get("total_slides") or 0),
            "maintenance_slides": int(quality_distribution.get("maintenance_slides") or 0),
            "safety_pct": int(quality_distribution.get("safety_pct") or 0),
        },
    }


async def _generate_outline(
    project_dict: dict,
    manual_context: str,
    structure: dict,
    provider: Any,
    knowledge_map: dict,
    ppt_refs: dict | None = None,
    teaching_dna: dict | None = None,
) -> dict:
    """
    STEP 2: GPT call to derive a complete course outline from the full manual.
    Returns {"course_title": ..., "sections": [{num, title, topics, page_hint, category, planned_slides}]}.
    """
    classification = _classify_course(project_dict.get("audience", ""), project_dict.get("training_type", ""))
    slide_depth = project_dict.get("settings", {}).get("slide_depth", "standard")
    duration = project_dict.get("settings", {}).get("duration", "3 days")
    min_slides, max_slides = _target_slide_count(slide_depth, duration)

    all_headings = structure.get("headings", [])
    chapter_classification = _classify_chapters(all_headings)
    headings_str = "\n".join(f"  - {h}" for h in all_headings[:60]) or "  (none detected)"

    chapter_summary = ""
    for cat, items in chapter_classification.items():
        if items:
            chapter_summary += f"\n  [{cat.upper()}] {', '.join(items[:4])}"

        knowledge_topics = knowledge_map.get("topics") or []
        ppt_summary = _summarize_ppt_refs_for_prompt(ppt_refs)

        prompt = f"""Analyse this equipment manual and create a complete professional course outline.

COURSE SETTINGS:
- Course Title: {project_dict.get('course_title')}
- Audience: {project_dict.get('audience')}
- Training Type: {project_dict.get('training_type')}
- Course Depth: {slide_depth}
- Duration: {duration}
- Target slide count: {min_slides}–{max_slides} slides total

COURSE CLASSIFICATION: {classification['category'].upper()}
{classification['depth_note']}

ALL DETECTED HEADINGS FROM MANUAL ({len(all_headings)} total):
{headings_str}

CHAPTERS BY CATEGORY:
{chapter_summary or '  (auto-classify from headings above)'}

KNOWLEDGE TOPICS (intermediate map, summarized):
{json.dumps(knowledge_topics[:25], ensure_ascii=False)}

MANUAL CONTENT (representative sample):
{manual_context[:15000]}

POWERPOINT KNOWLEDGE-BASE REFERENCES (secondary, optional):
{ppt_summary}

TEACHING DNA (single expert human course pattern):
{json.dumps(teaching_dna or {}, ensure_ascii=False)}

Return a JSON object with EXACTLY this structure:
{{
  "course_title": "string",
    "course_type": "Operator Training|Maintenance Training|Installation Training|Troubleshooting Training|Radiation Safety Training|Train-the-Trainer Course|Complete Technical Course",
  "course_category": "{classification['category']}",
    "course_structure": [
        "Cover page",
        "Course title",
        "Equipment name and model",
        "Course description",
        "Target audience",
        "Prerequisites",
        "Course duration",
        "Learning objectives",
        "Course agenda",
        "System overview",
        "Scientific operating principles",
        "Main components",
        "Control panel and software interface",
        "Safety precautions",
        "Startup procedure",
        "Normal operation",
        "Shutdown procedure",
        "Image interpretation or system output analysis",
        "Routine inspection",
        "Preventive maintenance",
        "Troubleshooting",
        "Fault codes and alarms",
        "Practical exercises",
        "Scenario-based exercises",
        "Knowledge checks",
        "Final assessment",
        "Course summary",
        "Glossary",
        "References",
        "Instructor notes"
    ],
  "sections": [
    {{
      "num": "1",
      "title": "Module/Section title from manual",
      "category": "safety|system_overview|electrical|xray|maintenance|troubleshooting|...",
      "topics": ["specific topic 1", "specific topic 2", "specific topic 3"],
      "page_hint": 1,
      "planned_slides": 5
    }}
  ],
  "total_slides_estimate": {min_slides},
  "content_distribution": {{
    "safety_pct": 12,
    "engineering_pct": 60,
    "maintenance_pct": 20,
    "assessment_pct": 8
  }}
}}

CRITICAL RULES:
0. Source priority: uploaded manual > manufacturer-approved PPT > other PPT > general background.
1. Generate {min_slides}–{max_slides} total slides distributed across all modules.
2. For a {classification['category']} course: safety/radiation slides must be ≤{int(classification['max_safety_pct']*100)}% of total.
3. Module titles should align with manual headings and extracted topics; do not invent unsupported modules.
4. Each module's topics must be specific technical items from the manual, not generic placeholders.
5. Set planned_slides for each module proportional to the technical depth of that section.
6. Do NOT invent content not supported by the manual.
7. The outline must produce a genuine {project_dict.get('training_type')} course, not a generic overview.
8. Include source page hints in each module using manual evidence.
9. Use PPT references for structure/teaching style/terminology only when consistent with manual authority.
10. Respect Teaching DNA module rhythm where supported: module introduction -> objectives -> technical explanation -> visual/diagram -> instructor action -> practical/lab -> troubleshooting -> knowledge check -> review/transition.
11. Return JSON only."""

    raw = await provider.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16384,
        system_prompt=_OUTLINE_SYSTEM,
    )
    result = _safe_parse_json_object(raw)
    if "course_category" not in result:
        result["course_category"] = classification["category"]
    if not result.get("sections"):
        return _build_outline_fallback(project_dict, structure)
    return result


def _build_outline_fallback(project_dict: dict, structure: dict) -> dict:
    """
    Fallback outline when GPT outline generation fails.
    Builds sections from detected headings or generates a generic structure.
    """
    headings = structure.get("headings", [])
    if headings:
        sections = [
            {"num": str(i + 1), "title": h, "topics": [], "page_hint": 0}
            for i, h in enumerate(headings[:10])
        ]
    else:
        # Generic structure for any technical manual
        sections = [
            {"num": "1", "title": "System Overview",           "topics": ["Purpose", "Key features"], "page_hint": 0},
            {"num": "2", "title": "Technical Specifications",  "topics": ["Performance", "Dimensions"], "page_hint": 0},
            {"num": "3", "title": "Safety Precautions",        "topics": ["Warnings", "Hazards"], "page_hint": 0},
            {"num": "4", "title": "Installation & Setup",      "topics": ["Requirements", "Procedures"], "page_hint": 0},
            {"num": "5", "title": "Operating Procedures",      "topics": ["Startup", "Normal operation", "Shutdown"], "page_hint": 0},
            {"num": "6", "title": "Alarms & Fault Responses",  "topics": ["Alarm list", "Corrective actions"], "page_hint": 0},
            {"num": "7", "title": "Maintenance",               "topics": ["Schedules", "Procedures"], "page_hint": 0},
        ]
    return {
        "course_title": project_dict.get("course_title", "Equipment Training"),
        "course_type": project_dict.get("training_type", "Complete Technical Course"),
        "course_structure": [
            "Cover page", "Course title", "Equipment name and model", "Course description",
            "Target audience", "Prerequisites", "Course duration", "Learning objectives",
            "Course agenda", "System overview", "Scientific operating principles", "Main components",
            "Control panel and software interface", "Safety precautions", "Startup procedure",
            "Normal operation", "Shutdown procedure", "Image interpretation or system output analysis",
            "Routine inspection", "Preventive maintenance", "Troubleshooting", "Fault codes and alarms",
            "Practical exercises", "Scenario-based exercises", "Knowledge checks", "Final assessment",
            "Course summary", "Glossary", "References", "Instructor notes",
        ],
        "sections": sections,
        "total_slides_estimate": 30,
        "_source": "fallback",
    }


def _derive_slide_titles(outline: dict, project_dict: dict) -> list[str]:
    """Derive expected slide titles from the outline (Step 3 preview)."""
    titles = [
        project_dict.get("course_title", "Training"),
        "Course Agenda",
        "Learning Objectives",
    ]
    for sec in outline.get("sections", []):
        titles.append(f"{sec.get('num', '')}. {sec.get('title', '')}")
        for topic in sec.get("topics", [])[:3]:
            titles.append(topic)
    titles += ["Course Summary", "References & Sources"]
    return titles


async def _generate_slides_v2(
    project_dict: dict,
    manual_context: str,
    outline: dict,
    provider: Any,
    knowledge_map: dict,
    learning_map: dict,
    curriculum_map: dict,
    instruction_plan: dict,
    benchmark_blueprint: dict | None = None,
    ppt_refs: dict | None = None,
    teaching_dna: dict | None = None,
) -> list[dict]:
    """
    STEP 4: Main slide generation.
    Uses 16 000 token budget. Asks GPT for {"slides": [...]}.
    Handles all unwrapping and partial-JSON recovery.
    """
    settings = project_dict.get("settings", {})
    classification = _classify_course(
        project_dict.get("audience", ""),
        project_dict.get("training_type", ""),
    )
    slide_depth = settings.get("slide_depth", "standard")
    duration = settings.get("duration", "3 days")
    min_slides, max_slides = _target_slide_count(slide_depth, duration)
    outline_estimate = outline.get("total_slides_estimate", min_slides)
    target = max(min_slides, min(outline_estimate, max_slides))

    sections_block = "\n".join(
        f"  Module {s.get('num','?')}: {s.get('title','')} "
        f"[{s.get('category','content')}] — {', '.join(s.get('topics',[]))} "
        f"(~{s.get('planned_slides', 5)} slides)"
        for s in outline.get("sections", [])
    ) or "  (derive sections from manual content below)"

    # Maintenance-specific depth requirements
    engineering_depth_block = ""
    if classification["is_maintenance"]:
        engineering_depth_block = """
ENGINEERING DEPTH REQUIREMENTS FOR MAINTENANCE MODULES:
For each engineering module (electrical, mechanical, x-ray, cooling, detectors, electronics, software):
  1. Purpose — what does this subsystem do and why is it critical?
  2. Main components — list each major component with its designation/part reference (p.N)
  3. Functional description — how does it work? Include signal flow or power flow. (p.N)
  4. Inputs and outputs — power input, signal inputs, outputs, interconnections (p.N)
  5. Normal operating indications — what should the engineer observe? (p.N)
  6. Test points — where to measure, what values to expect (p.N) — only if in manual
  7. Common faults — list the most likely failures for this subsystem (p.N)
  8. Fault isolation — how to diagnose faults step-by-step (p.N)
  9. Corrective actions — specific repair procedures (p.N)
  10. PM requirements — inspection intervals, lubrication, replacement intervals (p.N)

For TROUBLESHOOTING slides, use this format:
  - Symptom: [exact symptom from manual] (p.N)
  - Possible causes: [list from manual] (p.N)
  - Isolation steps: [step-by-step procedure] (p.N)
  - Corrective action: [exact procedure] (p.N)
  - Verification: [acceptance criterion] (p.N)

For PRACTICAL EXERCISE slides, ALWAYS include:
  - Objective
  - Required PPE and tools
  - Safety warnings (quoted exactly from manual)
  - Preconditions / lockout steps
  - Step-by-step procedure with (p.N) for every step
  - Expected readings or indications
  - Acceptance criteria
  If the manual doesn't provide enough detail: write "Insufficient source information for a safe practical procedure."

STRICT CONTENT DISTRIBUTION RULE:
Safety/radiation slides must be ≤15% of total for a maintenance course.
The majority of slides MUST cover: system architecture, subsystems, procedures, diagnostics, troubleshooting.
"""

    # Hands-on labs, fault trees, and repair procedures only belong when the
    # SOURCE MATERIAL actually describes physical procedures — audience
    # ("Field Service Engineers") alone isn't enough, since FSEs are also the
    # audience for pure theory modules. Observed live: generating a course
    # from a 27-page pure physics-concepts reference (X-ray/matter
    # interactions, material separation theory — zero procedures in the
    # source) still produced invented "Modulator Pulse Verification" and
    # "HVPS Discharge" labs with no basis in the source, because
    # classification was audience-driven only and these blocks were
    # unconditional. Require both: audience/type classified as maintenance
    # AND textual evidence the manual itself contains procedures.
    is_hands_on_course = classification["is_maintenance"] and _manual_has_procedural_content(manual_context)
    if is_hands_on_course:
        hands_on_block = """
LESSON DESIGN PACKAGE (MANDATORY FOR EACH MAJOR MODULE):
- Lesson introduction (why this lesson matters)
- Learning objectives and prerequisites
- Scientific explanation and practical explanation
- Component relationship and operational sequence
- Visual explanation (diagram/process/flow)
- Instructor coaching notes (separate from learner bullets)
- Common mistakes and field experience
- Practical exercise and hands-on lab activity
- Knowledge check and troubleshooting scenario
- Review and transition to next lesson

MODULE FLOW REQUIREMENT (MANDATORY WHEN SOURCE SUPPORTS IT):
- Module introduction
- Objectives
- Technical explanation
- Visual or diagram requirement
- Instructor notes (speaker notes area)
- Practical activity or lab
- Troubleshooting reasoning
- Knowledge check
- Review and transition

TROUBLESHOOTING THINKING (MANDATORY):
- Teach diagnostic reasoning, not only failure lists.
- Include fault trees / decision trees / measurement sequence / signal tracing / power tracing
    / isolation procedure / repair verification.

LAB DESIGN REQUIREMENTS (MANDATORY IN MAJOR TECHNICAL CHAPTERS):
- Lab objective
- Required tools and equipment
- Safety precautions
- Step-by-step activity
- Expected observations
- Measurements and acceptance criteria
- Common mistakes
- Discussion points
- Lab completion checklist
"""
    else:
        hands_on_block = """
LESSON DESIGN PACKAGE (MANDATORY FOR EACH MAJOR MODULE):
- Lesson introduction (why this concept matters for this audience)
- Learning objectives and prerequisites
- Conceptual explanation grounded strictly in the manual's own content
- Worked example or interpretation exercise (e.g. "given this image/reading,
    what does it indicate?") instead of a hands-on repair procedure
- Instructor coaching notes (separate from learner bullets)
- Common misconceptions students have about this concept
- Knowledge check that tests understanding, not a physical procedure
- Review and transition to next lesson

DO NOT INVENT MAINTENANCE CONTENT:
- Do not create "Lab:" or "Practical:" slides, fault trees, calibration
  procedures, or repair/troubleshooting steps unless the manual itself
  describes a physical procedure to perform.
- If the source is theoretical/conceptual (e.g. physics fundamentals,
  imaging principles, regulatory background), keep every slide theoretical
  and use conceptual questions and interpretation examples for assessment
  instead of simulated field repairs.
"""

    enhance_cfg = settings.get("enhance_training_material", {})
    if not isinstance(enhance_cfg, dict):
        enhance_cfg = {
            "enabled": bool(settings.get("enhance_training_material", True)),
            "options": settings.get("enhancement_options", {}),
        }
    if "enabled" not in enhance_cfg:
        enhance_cfg["enabled"] = True
    if "options" not in enhance_cfg or not isinstance(enhance_cfg.get("options"), dict):
        enhance_cfg["options"] = {}
    ppt_summary = _summarize_ppt_refs_for_prompt(ppt_refs, max_items=24)
    benchmark_blueprint = benchmark_blueprint if isinstance(benchmark_blueprint, dict) else {}
    benchmark_metrics = benchmark_blueprint.get("quality_metrics") if isinstance(benchmark_blueprint.get("quality_metrics"), dict) else {}
    benchmark_patterns = benchmark_blueprint.get("teaching_patterns") if isinstance(benchmark_blueprint.get("teaching_patterns"), list) else []
    designer_profile = benchmark_blueprint.get("designer_thinking_profile") if isinstance(benchmark_blueprint.get("designer_thinking_profile"), dict) else {}
    designer_signature = designer_profile.get("signature") if isinstance(designer_profile.get("signature"), dict) else {}

    prompt = f"""Generate a complete professional training slide deck. Return only a JSON object with a "slides" key.

COURSE SETTINGS:
- Title: {project_dict.get('course_title')}
- Equipment: {project_dict.get('manufacturer', '')} {project_dict.get('equipment_model', '')}
- Audience: {project_dict.get('audience')}
- Training Type: {project_dict.get('training_type')}
- Course Category: {classification['category'].upper()}
- Difficulty: {project_dict.get('difficulty', 'advanced')}
- Duration: {duration}
- Slide Depth: {slide_depth}
- TARGET: {target} slides (minimum {min_slides}, do not generate fewer)
- Include Knowledge Checks: {settings.get('include_quizzes', True)}
- Include Practical Exercises: {settings.get('include_practical', True)}
- Speaker Notes: {settings.get('include_notes', True)}
- Enhance Training Material: {bool(enhance_cfg.get('enabled', True))}
- Enhancement Options: {json.dumps(enhance_cfg.get('options', {}), ensure_ascii=False)}

{classification['depth_note']}
{engineering_depth_block}

INTERMEDIATE KNOWLEDGE MAP (authoritative planning layer):
{json.dumps((knowledge_map.get('topics') or [])[:30], ensure_ascii=False)}

LEARNING MAP (pre-slide sequencing rules):
{json.dumps((learning_map.get('sequencing') or [])[:40], ensure_ascii=False)}

CURRICULUM MAP (course architecture before slides):
{json.dumps((curriculum_map.get('modules') or [])[:20], ensure_ascii=False)}

INSTRUCTION PLAN (lesson-by-lesson teaching strategy):
{json.dumps((instruction_plan.get('lesson_plans') or [])[:40], ensure_ascii=False)}

HUMAN COURSE BENCHMARK BLUEPRINT (patterns only, never copy text/slides):
- Benchmark metrics: {json.dumps(benchmark_metrics, ensure_ascii=False)}
- Teaching patterns: {json.dumps(benchmark_patterns[:10], ensure_ascii=False)}

HUMAN DESIGNER THINKING PROFILE (extract mindset, never copy artifacts):
- Signature targets: {json.dumps(designer_signature, ensure_ascii=False)}
- Core principles: {json.dumps((designer_profile.get('principles') or [])[:10], ensure_ascii=False)}
- Mindset rules: {json.dumps((designer_profile.get('mindset') or [])[:10], ensure_ascii=False)}

TEACHING DNA (single selected expert course pattern, never copy text/branding/slides):
{json.dumps(teaching_dna or {}, ensure_ascii=False)}

POWERPOINT KNOWLEDGE-BASE REFERENCES (secondary, optional):
{ppt_summary}

COURSE MODULES (follow this structure precisely):
{sections_block}

SLIDE ORDERING RULES (MANDATORY):
- Section divider ALWAYS comes BEFORE the section content, never after
- Correct order within each module:
    1. Section Divider (type=section)
    2. Lesson Objectives (type=objectives)
    3. Content slides (type=content) — 3-8 slides per module for detailed courses
    4. Diagram/Procedure slide (type=content)
    5. Practical Exercise (type=practical) — for maintenance modules
    6. Knowledge Check (type=quiz) — one per module
    7. Module Summary (type=content with summary framing) — optional
- Do NOT stack multiple section dividers together
- Do NOT put a knowledge check before the content it tests
{hands_on_block}
ARCHITECTURE RULE (CRITICAL):
- Do not treat manual pages as one-to-one slide source.
- If ten manual pages teach one concept, merge into one excellent lesson.
- If one manual page contains multiple distinct concepts, split into multiple lessons.
- Reorganize manual order for educational quality when needed.
- Every slide must have a teaching purpose, not just extracted text.

HUMAN BENCHMARK RULE (CRITICAL):
- Match or exceed the educational quality patterns from benchmark courses.
- Never copy slide text, notes, or layout from benchmark references.
- Learn organization, pacing, visual strategy, and theory-practice balance only.
- Manual remains the authoritative technical source for all facts and values.

MASTER-DESIGNER THINKING RULE (CRITICAL — derived by cross-referencing a real
human-authored AS&E field-service deck sentence-by-sentence against its own
source manual; apply this reasoning, do not just extract manual text):
1. Reorganize into your own taxonomy, never transcribe paragraph-by-paragraph.
   Read the raw manual section, extract its facts, then invent a clean
   organizing structure to teach it — e.g. the manual describes several
   stop mechanisms across scattered paragraphs; the human deck opens with
   "There are essentially 3 categories of Safety Stops" as its own
   classification, not a heading that exists in the manual.
2. One concept per slide, not one manual section per slide. Decompose a
   dense manual paragraph into several atomic single-idea slides (e.g.
   "Types" / "Installation" / "Inputs" / "Output" as four separate slides
   instead of one crowded slide covering a whole subsystem).
3. When the manual already has a labeled figure for a topic (Figure N-N:
   "..."), that IS the diagram — cite/embed it rather than inventing a new
   diagram concept from scratch.
4. Instructor notes must carry field judgment and teaching triage the
   manual itself never states — what to physically demonstrate, what to
   deliberately spend LESS time on ("don't spend a lot of time on the
   fuses — what's critical is how errors manifest"), and where real
   consequences live. Never let instructor notes just restate the bullets.
5. State scope boundaries explicitly whenever a component is sealed or
   non-serviceable: tell the trainee what NOT to attempt and what happens
   instead ("we do not service the tank — if it fails, a whole new unit is
   ordered"). The manual describes how things work; the course must also
   say what a field technician is not expected or allowed to do.
6. Mark hands-on practice with a dedicated "Lab:" or "Practical:" divider
   slide — never blend a procedure directly into a content slide without
   flagging it as a distinct practical activity.
7. For any topic with more than one manufacturer, model, or hardware
   revision, use a section-divider slide before each branch (e.g.
   "High Voltage Power Supplies" -> "Gulmay" -> "Spellman"), and compare
   variants side-by-side explicitly ("Older Style / Newer Style") rather
   than describing each version in isolation.
8. Open each safety/orientation topic with a short pointer slide naming the
   authoritative reference document, instead of trying to cram every
   manual caveat onto slides — the deck teaches judgment, the manual stays
   the exhaustive reference.
9. Phrase learning objectives as observable action verbs matched to the
   task (Identify / Locate / Describe / Observe for hands-on and safety
   topics), never abstract verbs like "understand" or "learn about."
10. Keep a repeating instructional rhythm: objective -> explanation ->
    guided practice -> diagnostics -> verification, and ensure each module
    teaches expert decision-making under real field constraints.

MANDATORY COURSE-COMPONENT COVERAGE:
- Ensure the deck includes these components where supported by manual evidence:
    cover, course title, equipment model, description, audience, prerequisites, duration, objectives, agenda,
    system overview, scientific principles, components, control panel/UI, safety precautions.
- Only for a {classification['category'].upper()} course, additionally include where supported:
    {"startup, operation, shutdown, image/system output analysis, inspection, preventive maintenance, troubleshooting, fault codes, practical exercises, scenarios," if classification["is_maintenance"] else ""}
    knowledge checks, final assessment, summary, glossary, references, instructor notes.

EQUIPMENT MANUAL — YOUR ONLY SOURCE OF TRUTH:
{manual_context}

POWERPOINT REFERENCE USAGE RULES:
- Use PowerPoint references for: structure, teaching style, slide organization, visual patterns, terminology, instructor notes, exercises, assessment style, and Arabic formatting.
- Speaker notes are required for instructor guidance and must be stored in slide speaker-notes.
- Do not replace diagram-type slides with plain bullets; add explicit visual placeholders when diagram creation is not possible.
- Never overwrite manual technical facts (specifications, limits, procedures, fault codes, calibration/electrical/radiation values, part numbers).
- If a PPT reference conflicts with manual values, keep manual values and mention conflict in speaker notes as instructor-review item.
- Synthesize and paraphrase; do not blindly copy full slide text.
- Do not copy logos or proprietary markings from references.

REQUIRED OUTPUT FORMAT:
{{
  "slides": [

    {{
      "type": "title",
      "title": "{project_dict.get('course_title', 'Equipment Training')}",
      "bullets": [
        "{project_dict.get('training_type', 'Technical Training')}",
        "Audience: {project_dict.get('audience', 'Technicians')}",
        "{project_dict.get('manufacturer', '')} {project_dict.get('equipment_model', '')}"
      ],
      "speaker_notes": "Put this slide on screen as participants arrive. Welcome the class and introduce yourself.",
      "source_pages": []
    }},

    {{
      "type": "agenda",
      "title": "Course Agenda",
      "bullets": ["Module 1: [Title]", "Module 2: [Title]", "..."],
      "speaker_notes": "Walk through the agenda. Explain breaks and lab times.",
      "source_pages": []
    }},

    {{
      "type": "section",
      "title": "1. [Module Title from Outline]",
      "section_num": "1",
      "bullets": ["[One sentence: what this module covers and why it matters to the {project_dict.get('audience', 'engineer')}]"],
      "speaker_notes": "Transition note for the instructor.",
      "source_pages": []
    }},

    {{
      "type": "objectives",
      "title": "Learning Objectives",
      "bullets": [
        "By the end of this module, utilizing student guide materials, you will be able to describe:",
        "[Specific measurable objective 1] (p.N)",
        "[Specific measurable objective 2] (p.N)",
        "[Specific measurable objective 3] (p.N)"
      ],
      "speaker_notes": "Review objectives. Ask if anyone has prior experience with [topic].",
      "source_pages": []
    }},

    {{
      "type": "content",
      "title": "[Specific topic from manual]",
      "bullets": [
        "[Key fact stated directly — no vague intros] (p.N)",
        "[Second key fact with measurement or specification] (p.N)",
        "  [Supporting detail or component reference] (p.N)",
        "  [Another specific detail] (p.N)",
        "[Third key fact] (p.N)"
      ],
            "speaker_notes": "How to explain: [teaching narrative]. Ask: [diagnostic question]. Demonstration: [what to show]. Field experience: [real-world pitfall]. Common mistake: [typical trainee error]. Timing: [X minutes]. Discussion: [debrief prompt]. ⚠ Safety point if applicable.",
      "source_pages": [N]
    }},

    {{
      "type": "quiz",
      "title": "[Direct technical question from the content just covered]?",
      "bullets": [
        "[Complete plausible wrong answer — full word, do not truncate]",
        "[Complete correct answer from manual — full word, do not truncate]",
        "[Complete plausible wrong answer — full word, do not truncate]",
        "[Complete plausible wrong answer — full word, do not truncate]"
      ],
      "answer_index": 1,
      "speaker_notes": "Answer: B — [explanation citing manual] (p.N). Allow 60 seconds.",
      "source_pages": [N]
    }},

    {{
      "type": "practical",
      "title": "Practical: [Task from Manual Procedure]",
      "bullets": [
                "Lab Objective: [clear measurable objective] (p.N)",
        "⚠ [Safety warning quoted exactly from manual] (p.N)",
        "PPE required: [list from manual] (p.N)",
        "Tools required: [list from manual] (p.N)",
                "Required equipment: [list from manual] (p.N)",
        "Precondition: [isolation/lockout steps] (p.N)",
        "1. [Step 1 exact procedure language] (p.N)",
        "2. [Step 2] (p.N)",
        "3. [Step 3 with expected reading] (p.N)",
                "Expected observations: [what should be seen] (p.N)",
                "Measurements: [values/limits] (p.N)",
                "Common mistakes: [likely trainee errors] (p.N)",
                "Discussion: [what to ask and why] (p.N)",
                "Checklist: [completion checklist] (p.N)",
        "Accept: [acceptance criterion from manual] (p.N)"
      ],
            "speaker_notes": "How to coach this lab, what to demonstrate first, what diagnostic questions to ask, where trainees misdiagnose, timing and facilitation plan, and debrief logic. If source insufficient, state this.",
      "source_pages": [N]
    }},

    {{
      "type": "summary",
      "title": "Course Summary",
      "bullets": [
        "[Most critical fact from module 1] (p.N)",
        "[Most critical fact from module 2] (p.N)",
        "[Safety rule that must be remembered] (p.N)",
        "[Procedure step with highest failure risk] (p.N)"
      ],
      "speaker_notes": "Recap. Announce the written assessment. Any final questions?",
      "source_pages": []
    }},

    {{
      "type": "references",
      "title": "References & Sources",
      "bullets": [
        "[Manual]  {project_dict.get('manual_filename', 'Uploaded Manual')} — primary source",
        "[Note]  All technical content sourced exclusively from the above manual."
      ],
      "speaker_notes": "",
      "source_pages": []
    }}

  ]
}}

CRITICAL RULES:
1. Generate EXACTLY {target} slides (or as many as the manual content supports, minimum {min_slides}).
2. Every technical fact, specification, measurement, and procedure step MUST have (p.N) citation.
3. Do NOT invent specifications, voltages, currents, dimensions, error codes, or procedures.
4. If information is not in the manual: write [Not found in uploaded manual] — never invent.
5. "slides" must be a flat array — no nesting.
6. Sub-bullets start with exactly 2 spaces.
7. Knowledge checks: EXACTLY 4 options, each a COMPLETE sentence or phrase — never truncate the first letter.
8. answer_index is 0-based integer (0=A, 1=B, 2=C, 3=D).
9. Speaker notes: instructor-voice — never repeat slide bullets verbatim.
10. Do NOT add any text outside the JSON object.
11. Content distribution for {classification['category']} course: safety/radiation ≤{int(classification['max_safety_pct']*100)}% of slides.
12. Add source traceability whenever possible in technical slides as: Source: Manual page XX, section X.X.
13. If output feels like a short summary instead of a full instructor course, continue expanding module depth until comprehensive.
14. "source_pages" must be a JSON array of plain integers only, e.g. [4, 5] — never a manual-style
    page-range like [2-5], since that is not valid JSON and breaks parsing of the entire response.
    If a fact spans a page range, list each page as its own integer: [2, 3, 4, 5]."""

    raw = await _generate_with_large_budget(provider, prompt, _GENERATION_SYSTEM, max_tokens=16384)
    finish_reason = "stop"
    raw = _repair_page_range_json_arrays(raw)
    log.info("Training slide generation complete: raw_len=%d", len(raw))

    # Save raw response always for debugging
    _save_debug("slides_raw.json", {"finish_reason": finish_reason, "length": len(raw), "content": raw[:5000]})

    if finish_reason == "length":
        log.warning("GPT response was cut off at token limit — attempting partial JSON recovery")

    parsed = _safe_parse_json_object(raw)
    if not parsed:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as e:
            log.error("JSON parse error: %s", e)
            _save_debug("slides_json_error.txt", raw)
            partial = _recover_partial_slides(raw)
            if partial:
                log.info("Recovered %d slides from partial JSON", len(partial))
                return partial
            raise ValueError(
                f"Model returned invalid JSON (finish_reason={finish_reason}, len={len(raw)}). "
                f"Raw response saved to /debug/slides_json_error.txt. Parse error: {e}"
            )

    # Unwrap from any container dict
    if isinstance(parsed, dict):
        for key in ("slides", "course", "deck", "data", "result", "presentation"):
            if isinstance(parsed.get(key), list) and len(parsed[key]) > 0:
                log.info("Unwrapped slides from key '%s': %d slides", key, len(parsed[key]))
                return parsed[key]
        for key, val in parsed.items():
            if isinstance(val, list) and len(val) > 0:
                log.info("Unwrapped slides from first list key '%s': %d slides", key, len(val))
                return val
        _save_debug("slides_empty_dict.json", parsed)
        raise ValueError(
            f"Model returned a dict but no slides list found. "
            f"Keys present: {list(parsed.keys())}. "
            f"Check /debug/slides_raw.json and /debug/slides_empty_dict.json."
        )

    if isinstance(parsed, list):
        return parsed

    raise ValueError(f"Model returned unexpected type: {type(parsed).__name__}")


def _recover_partial_slides(raw: str) -> list[dict]:
    """
    Attempt to extract complete slide objects from a truncated JSON string.
    Looks for the slides array and extracts all fully-formed objects.
    """
    try:
        # Find the slides array start
        array_start = raw.find('"slides"')
        if array_start == -1:
            array_start = raw.find('[')
        else:
            array_start = raw.find('[', array_start)

        if array_start == -1:
            return []

        # Extract from array start, add closing brackets to make valid JSON
        fragment = raw[array_start:]

        # Count complete objects by finding balanced { }
        slides: list[dict] = []
        depth = 0
        in_string = False
        escape_next = False
        obj_start = -1

        for i, ch in enumerate(fragment):
            if escape_next:
                escape_next = False
                continue
            if ch == '\\' and in_string:
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == '{':
                if depth == 0:
                    obj_start = i
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0 and obj_start != -1:
                    try:
                        obj = json.loads(fragment[obj_start:i + 1])
                        if isinstance(obj, dict) and "type" in obj and "title" in obj:
                            slides.append(obj)
                    except Exception:
                        pass
                    obj_start = -1

        return slides
    except Exception as e:
        log.warning("Partial slide recovery failed: %s", e)
        return []


def _extract_image_refs(structure: dict, pages: list[dict]) -> list[dict]:
    """
    STEP 5: Extract figure/image references from manual text.
    Returns list of {ref, page_num, context}.
    """
    refs: list[dict] = []
    fig_re = re.compile(r"(?i)(?:figure|fig\.?)\s*([\d\-]+)[^\n]{0,80}")
    for page in pages:
        text = page.get("text", "")
        for m in fig_re.finditer(text):
            refs.append({
                "ref":      m.group(0).strip(),
                "fig_num":  m.group(1),
                "page_num": page.get("page_num"),
                "context":  text[max(0, m.start() - 40):m.end() + 40].replace("\n", " "),
            })
    # Deduplicate by fig_num
    seen: set[str] = set()
    unique: list[dict] = []
    for r in refs:
        if r["fig_num"] not in seen:
            seen.add(r["fig_num"])
            unique.append(r)
    return unique[:50]


def _extract_all_citations(slide_dicts: list[dict]) -> list[int]:
    """
    STEP 6: Collect all page citations from slide bullets and source_pages.
    Returns flat list of page numbers (may have duplicates).
    """
    citation_re = re.compile(r"\(p\.(\d+)\)")
    pages: list[int] = []
    for sd in slide_dicts:
        # From source_pages field
        for p in sd.get("source_pages", []):
            try:
                pages.append(int(p))
            except (TypeError, ValueError):
                pass
        # From bullet text
        for bullet in sd.get("bullets", []):
            for m in citation_re.finditer(str(bullet)):
                pages.append(int(m.group(1)))
        # From speaker notes
        for m in citation_re.finditer(sd.get("speaker_notes", "")):
            pages.append(int(m.group(1)))
    return pages


def _validate_and_fix_quiz_slides(slide_dicts: list[dict]) -> None:
    """Downgrade malformed quiz slides to content slides instead of shipping
    them as a broken multiple-choice question.

    The prompt asks for a single direct question as the title — always
    ending in "?" — with exactly 4 plain answer-option bullets. When the
    model doesn't comply, nothing catches it today. Observed in a real
    generated deck: 5 of 6 "quiz" slides had a generic non-question title
    like "Knowledge Check: Motor Control Subsystem" with bullets that were
    actually a "Scenario:" setup followed by 2-3 unrelated sub-questions, or
    four entirely separate "Q1:".."Q4:" questions crammed into one slide's
    answer-option slots — not a single answerable multiple-choice question.
    Detect via the same signal the prompt itself defines (title must end in
    "?") and relabel as a discussion slide rather than guessing at a repair.
    """
    scenario_prefix_re = re.compile(r"^(?:Scenario|Knowledge Check)\s*:\s*", re.IGNORECASE)
    for s in slide_dicts:
        if s.get("type") != "quiz":
            continue
        title = _normalized_text(s.get("title"))
        if title.endswith("?"):
            continue
        s["type"] = "content"
        title_clean = scenario_prefix_re.sub("", title).strip()
        s["title"] = f"Review Discussion: {title_clean}" if title_clean else "Review Discussion"


_MODULE_PREFIX_RE = re.compile(
    r"^(?:(?:Advanced\s+)?Module\s+\d+(?:\s+Expansion)?\s*:\s*|\d+\.\s*)", re.IGNORECASE
)


def _renumber_section_slides(slide_dicts: list[dict]) -> None:
    """Reassign sequential, consistently-formatted module numbers to every
    type=="section" slide, in final deck order.

    Slide generation runs across multiple independent LLM calls — the main
    pass, plus separate "rescue"/expansion calls when the first pass is too
    short — and each call invents its own module numbers with no shared
    counter. Observed in a real generated deck: three different sections
    all titled "Module 3: ...", and modules 5 and 7 never appearing at all,
    while some early sections used a bare "1. Title" format and later ones
    used "Module 3: Title" — two different conventions in the same deck.
    Rather than trying to make several independent LLM calls agree on
    numbering, fix it up deterministically once, after all slides
    (including rescue/expansion additions) exist.

    Also strips a stray "Module N:" prefix from non-section slide titles.
    Observed in the same real deck: a type=="content" slide titled "Module
    8: Cooling System Diagnostic Rhythm" that isn't a section divider at
    all — it reads as a phantom extra module when skimming slide titles,
    even though the real section count tops out at 7.
    """
    n = 0
    for s in slide_dicts:
        if s.get("type") != "section":
            title = _normalized_text(s.get("title"))
            if _MODULE_PREFIX_RE.match(title):
                s["title"] = _MODULE_PREFIX_RE.sub("", title).strip() or title
            continue
        n += 1
        title = _normalized_text(s.get("title"))
        title = _MODULE_PREFIX_RE.sub("", title).strip() or f"Module {n}"
        s["title"] = f"Module {n}: {title}"


def _insert_agenda_slide(slide_dicts: list[dict]) -> None:
    """Insert a course agenda/table-of-contents slide right after the title
    slide, listing every module in order.

    Compared against a real human-authored instructor deck for the same
    equipment: the human deck opens with a full agenda slide listing every
    topic before diving into content — giving the whole course a visible
    structure up front. The generated deck had no equivalent at all; it
    went straight from the title slide into "1. System Safety..." with no
    roadmap. Must run after _renumber_section_slides so the listed module
    numbers/titles are the final, corrected ones.

    The generation prompt's own REQUIRED OUTPUT FORMAT example includes a
    sample type=="agenda" slide, so the model sometimes produces one too —
    with its own, possibly stale, module list. If one already exists, keep
    it (drop any duplicates) and refresh its bullets to the final,
    corrected module titles rather than inserting a second agenda slide.
    """
    section_titles = [s.get("title", "") for s in slide_dicts if s.get("type") == "section"]
    if not section_titles:
        return
    existing = [i for i, s in enumerate(slide_dicts) if s.get("type") == "agenda"]
    if existing:
        slide_dicts[existing[0]]["bullets"] = section_titles
        slide_dicts[existing[0]]["title"] = slide_dicts[existing[0]].get("title") or "Course Agenda"
        for i in reversed(existing[1:]):
            del slide_dicts[i]
        return
    insert_at = 1 if slide_dicts and slide_dicts[0].get("type") == "title" else 0
    slide_dicts.insert(insert_at, {
        "type": "agenda",
        "title": "Course Agenda",
        "bullets": section_titles,
        "speaker_notes": (
            "Walk through the agenda at a high level before starting Module 1 — "
            "this gives students a map of the full course and where each day's "
            "material fits."
        ),
        "source_pages": [],
    })


def _ensure_section_objectives_slides(slide_dicts: list[dict]) -> None:
    """Guarantee every module (type=section) is immediately followed by a
    "Learning Objectives" preview slide (type=objectives).

    The generation prompt already asks for this per module (SLIDE ORDERING
    RULES step 2: "Lesson Objectives (type=objectives)"), but the model
    does not reliably comply. The human-authored reference deck used for
    comparison opens every module with a "what you'll learn" slide; the
    generated deck it was compared against had none at all. Build one
    deterministically from that module's own content-slide titles when the
    model skipped it, instead of leaving the module to start cold.
    """
    i = 0
    while i < len(slide_dicts):
        s = slide_dicts[i]
        if s.get("type") != "section":
            i += 1
            continue
        nxt = slide_dicts[i + 1] if i + 1 < len(slide_dicts) else None
        if nxt is not None and nxt.get("type") == "objectives":
            i += 1
            continue
        topics: list[str] = []
        j = i + 1
        while j < len(slide_dicts) and slide_dicts[j].get("type") != "section":
            if slide_dicts[j].get("type") in ("content", "practical", "lab"):
                t = _normalized_text(slide_dicts[j].get("title"))
                if t:
                    topics.append(t)
            j += 1
        bullets = ["By the end of this module, you will be able to:"]
        bullets += [f"Understand and apply: {t}" for t in topics[:6]] or [
            "Understand and apply the concepts covered in this module."
        ]
        slide_dicts.insert(i + 1, {
            "type": "objectives",
            "title": "Learning Objectives",
            "bullets": bullets,
            "speaker_notes": (
                "Review these objectives before starting the module and ask if "
                "anyone has prior experience with the topic."
            ),
            "source_pages": [],
        })
        i += 2  # past the section divider and the objectives slide just inserted


def _ensure_course_info_slide(slide_dicts: list[dict], project_dict: dict) -> None:
    """Guarantee the deck states prerequisites, duration, audience, and
    evaluation method up front, in one "Course Information" slide.

    The prompt's MANDATORY COURSE-COMPONENT COVERAGE list names
    "prerequisites, duration" explicitly, but nothing enforces it — the
    generated deck compared against the human-authored reference had no
    such slide, while the human deck states this on an early slide before
    diving into Module 1. Build it deterministically from the project's
    own settings so it never depends on the model remembering to include it.
    Must run after _insert_agenda_slide so it lands right after the agenda.
    """
    if any("course information" in _normalized_text(s.get("title")).lower() for s in slide_dicts):
        return

    settings = project_dict.get("settings") or {}
    module_count = len([s for s in slide_dicts if s.get("type") == "section"])
    difficulty = _normalized_text(project_dict.get("difficulty")) or "intermediate"
    bullets = [
        f"Audience: {project_dict.get('audience') or 'Field service technicians'}",
        f"Prerequisites: Basic electrical/mechanical safety training and general familiarity with the "
        f"equipment family ({difficulty} level course)",
        f"Duration: {settings.get('duration') or '3 days'}",
        f"Course structure: {module_count} modules with hands-on labs and knowledge checks throughout",
        "Evaluation: Knowledge check after each module plus a final course assessment",
    ]
    insert_at = 0
    for idx, s in enumerate(slide_dicts):
        if s.get("type") in ("title", "agenda"):
            insert_at = idx + 1
        else:
            break
    slide_dicts.insert(insert_at, {
        "type": "content",
        "title": "Course Information",
        "bullets": bullets,
        "speaker_notes": (
            "Set expectations for prerequisites, course length, and how students "
            "will be evaluated before moving into Module 1."
        ),
        "source_pages": [],
    })


_PAGE_REF_RE = re.compile(r"(?:manual\s+)?p(?:age)?\.?\s*(\d+)", re.IGNORECASE)


def _parse_page_from_source_ref(text: str) -> "int | None":
    m = _PAGE_REF_RE.search(_normalized_text(text))
    if not m:
        return None
    try:
        n = int(m.group(1))
        return n if n > 0 else None
    except ValueError:
        return None


def _match_visual_for_slide(slide_title: str, visuals: list[dict]) -> "dict | None":
    """Find the best _build_visual_plan()/_fallback_visual_plan() entry for a
    slide, by word-overlap between the slide title and each visual's
    related_module/visual_title. Returns None if nothing overlaps."""
    if not visuals:
        return None
    title_words = set(_normalized_text(slide_title).lower().split())
    if not title_words:
        return None
    best, best_score = None, 0
    for v in visuals:
        candidate_text = f"{v.get('related_module', '')} {v.get('visual_title', '')}"
        candidate_words = set(_normalized_text(candidate_text).lower().split())
        score = len(title_words & candidate_words)
        if score > best_score:
            best, best_score = v, score
    return best if best_score > 0 else None


def _enforce_instructor_notes_and_visual_placeholders(
    slide_dicts: list[dict], visuals: "list[dict] | None" = None,
) -> None:
    """Ensure instructor notes exist and diagram-type slides include explicit placeholders when needed.

    `visuals` is the output of stage 8 ("Generate Diagrams",
    _build_visual_plan/_fallback_visual_plan) — real, topic-specific diagram
    specs with captions and manual source references. Previously this
    function never received it, so every slide needing a diagram got the
    exact same generic sentence verbatim regardless of topic. Matching
    against it here gives each placeholder a topic-specific caption.

    When a matched visual resolves to a real manual page number, convert
    the slide to type=="image_content" with that page number in
    source_pages — a real page image (rendered by _build_images_for_slides
    from the stored manual PDF) can then be embedded instead of a text
    placeholder, which is what real human-authored decks do (they screenshot
    the manual's own diagrams rather than describing them in prose).
    """
    diagram_keywords = ["diagram", "schematic", "flow", "block", "signal", "process", "tree"]
    for s in slide_dicts:
        notes = _normalized_text(s.get("speaker_notes"))
        if not notes:
            s["speaker_notes"] = (
                "Instructor guidance: Explain the objective of this slide, connect it to field practice, "
                "and ask one diagnostic question before moving to the next step."
            )

        title_l = _normalized_text(s.get("title")).lower()
        bullets = [str(b) for b in (s.get("bullets") or [])]
        bullets_blob = " ".join(_normalized_text(b).lower() for b in bullets)
        needs_visual = any(k in title_l for k in diagram_keywords) or any(k in bullets_blob for k in ["signal flow", "power flow", "decision tree", "block diagram"])
        has_visual_placeholder = any("visual placeholder" in _normalized_text(b).lower() for b in bullets) or any("diagram:" in _normalized_text(b).lower()[:12] for b in bullets)
        if s.get("type") not in ("content", "objectives", "practical", "lab"):
            continue
        if needs_visual and not has_visual_placeholder:
            matched = _match_visual_for_slide(s.get("title", ""), visuals or [])
            page_num = None
            if matched:
                caption = _normalized_text(matched.get("caption") or matched.get("suggested_caption") or matched.get("required_visual_description"))
                diagram_type = _normalized_text(matched.get("diagram_type")) or "diagram"
                source_ref = _normalized_text(matched.get("source_reference"))
                placeholder_line = f"[DIAGRAM] {diagram_type.capitalize()}: {caption}" if caption else f"[DIAGRAM] {diagram_type.capitalize()} required for {s.get('title', 'this topic')}."
                if source_ref:
                    placeholder_line += f" ({source_ref})"
                page_num = matched.get("original_page_number") or _parse_page_from_source_ref(source_ref)
                try:
                    page_num = int(page_num) if page_num else None
                except (TypeError, ValueError):
                    page_num = None
            else:
                placeholder_line = (
                    f"[DIAGRAM] Required visual for \"{s.get('title', 'this topic')}\": show components, "
                    "inputs/outputs, directional flow arrows, and fault decision points."
                )
            if page_num:
                s["type"] = "image_content"
                s["source_pages"] = [page_num]
                s["bullets"] = [caption or placeholder_line]
            else:
                s["bullets"] = [placeholder_line, *bullets][:8]


def _fallback_visual_plan(outline: dict, manual_index: dict) -> list[dict]:
    visuals: list[dict] = []
    fig_items = manual_index.get("figures") or []
    for sec in (outline.get("sections") or [])[:20]:
        mod = _normalized_text(sec.get("title")) or "Module"
        ref = next((f for f in fig_items if _normalized_text(f.get("section")) == mod), None)
        if ref:
            visuals.append({
                "visual_title": f"Figure-based visual: {mod}",
                "caption": _normalized_text(ref.get("text"))[:180],
                "learning_purpose": "Explain the subsystem with manual figure context.",
                "related_module": mod,
                "diagram_type": "labeled component diagram",
                "source_reference": f"Manual page {ref.get('page')}, section {ref.get('section')}",
                "original_page_number": int(ref.get("page") or 0),
                "placeholder": False,
            })
        else:
            visuals.append({
                "visual_title": f"Required diagram: {mod}",
                "caption": "Create a clean educational diagram for this module.",
                "learning_purpose": "Support visual understanding when source figure is unavailable.",
                "related_module": mod,
                "diagram_type": "block diagram",
                "source_reference": "Manual figure unavailable",
                "placeholder": True,
                "required_visual_description": f"Diagram needed for {mod}",
                "original_page_number": 0,
                "figure_number": "N/A",
                "suggested_caption": f"Conceptual diagram for {mod}",
            })
    return visuals


async def _build_visual_plan(
    provider: Any,
    outline: dict,
    manual_index: dict,
    settings: dict,
    ppt_refs: dict | None = None,
    teaching_dna: dict | None = None,
) -> list[dict]:
    ppt_visual_refs = []
    if isinstance(ppt_refs, dict):
        for r in (ppt_refs.get("selected_references") or []):
            if r.get("reference_category") in {"visual", "arabic_formatting"}:
                ppt_visual_refs.append({
                    "file": r.get("reference_file"),
                    "slide": r.get("reference_slide"),
                    "title": r.get("reference_title"),
                    "category": r.get("reference_category"),
                    "layout": r.get("layout_metadata"),
                })

    prompt = f"""Create a visual plan for the generated training course.

Outline sections:
{json.dumps(outline.get('sections', [])[:30], ensure_ascii=False)}

Detected manual figures/tables summary:
{json.dumps({
    'figures': (manual_index.get('figures') or [])[:30],
    'tables': (manual_index.get('tables') or [])[:20],
}, ensure_ascii=False)}

PowerPoint visual references:
{json.dumps(ppt_visual_refs[:18], ensure_ascii=False)}

Teaching DNA visual patterns:
{json.dumps((teaching_dna or {}).get('visual_patterns', [])[:20], ensure_ascii=False)}

Return JSON only:
{{
  "visuals": [
    {{
      "visual_title": "string",
      "caption": "string",
      "learning_purpose": "string",
      "related_module": "string",
      "diagram_type": "flowchart|block diagram|process diagram|labeled component diagram|comparison diagram|timeline|safety-zone diagram|troubleshooting tree",
      "source_reference": "Manual page XX, section X.X",
      "placeholder": false,
      "required_visual_description": "if placeholder=true",
      "original_page_number": 0,
      "figure_number": "string",
      "suggested_caption": "string"
    }}
  ]
}}

Rules:
- Prefer clear technical diagrams, labels, icons, and arrows.
- Do not generate misleading photorealistic images.
- If original figure cannot be used clearly, output placeholder=true with required fields populated.
- Reuse only non-proprietary layout patterns (title position, hierarchy, spacing, RTL alignment behavior).
- For Arabic courses, prioritize Arabic formatting references when available.
- Aggressively include: system block diagrams, signal flow, power flow, component interaction,
  cable routing, decision trees, maintenance workflow, troubleshooting workflow, inspection workflow.
- Never replace diagram-type slides with plain bullets. If a diagram cannot be produced, emit placeholder=true with an explicit required_visual_description.
"""
    raw = await provider.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16384,
        system_prompt="You are a technical training visual planner. Return JSON only.",
    )
    parsed = _safe_parse_json_object(raw)
    visuals = parsed.get("visuals") if isinstance(parsed, dict) else None
    if isinstance(visuals, list) and visuals:
        return visuals
    return _fallback_visual_plan(outline, manual_index)


def _fallback_assessments(slides: list[dict]) -> dict:
    questions = []
    for s in slides:
        if s.get("type") != "quiz":
            continue
        options = s.get("bullets") or []
        if len(options) < 2:
            continue
        ai = int(s.get("answer_index") or 0)
        ai = max(0, min(ai, len(options) - 1))
        questions.append({
            "question_type": "multiple-choice",
            "question": _normalized_text(s.get("title")) or "Knowledge check",
            "correct_answer": _normalized_text(options[ai]),
            "explanation": _normalized_text(s.get("speaker_notes"))[:240],
            "source_module": _normalized_text(s.get("title")),
            "manual_page_reference": (s.get("source_pages") or [0])[0],
            "difficulty_level": "intermediate",
            "learning_objective": "Check understanding of cited technical content.",
        })
    return {
        "student_version": [{k: v for k, v in q.items() if k not in {"correct_answer", "explanation"}} for q in questions],
        "instructor_answer_key": questions,
    }


async def _build_assessment_bank(
    provider: Any,
    outline: dict,
    knowledge_map: dict,
    slides: list[dict],
    settings: dict,
    ppt_refs: dict | None = None,
    teaching_dna: dict | None = None,
) -> dict:
    ppt_assessment_refs = []
    if isinstance(ppt_refs, dict):
        for r in (ppt_refs.get("selected_references") or []):
            if r.get("reference_category") in {"instructional", "terminology"}:
                ppt_assessment_refs.append({
                    "file": r.get("reference_file"),
                    "slide": r.get("reference_slide"),
                    "title": r.get("reference_title"),
                    "category": r.get("reference_category"),
                })

    prompt = f"""Build an assessment bank from the generated training content.

Assessment level: {settings.get('assessment_level', 'standard')}
Include answer key: {settings.get('include_answer_key', True)}

Outline:
{json.dumps(outline.get('sections', [])[:30], ensure_ascii=False)}

Knowledge map topics:
{json.dumps((knowledge_map.get('topics') or [])[:30], ensure_ascii=False)}

Slide summary:
{json.dumps([{
    'title': s.get('title'),
    'type': s.get('type'),
    'source_pages': s.get('source_pages', []),
} for s in slides[:120]], ensure_ascii=False)}

PowerPoint instructional references:
{json.dumps(ppt_assessment_refs[:20], ensure_ascii=False)}

Teaching DNA assessment patterns:
{json.dumps((teaching_dna or {}).get('assessment_patterns', [])[:20], ensure_ascii=False)}

Return JSON only:
{{
  "questions": [
    {{
      "question_type": "multiple-choice|true-false|matching|short-answer|scenario|practical-checklist|troubleshooting-case",
      "question": "string",
      "correct_answer": "string",
      "explanation": "string",
      "source_module": "string",
      "manual_page_reference": 0,
      "difficulty_level": "basic|intermediate|advanced",
      "learning_objective": "string"
    }}
  ],
  "student_version": [{{"question_type":"...","question":"...","source_module":"..."}}],
  "instructor_answer_key": [{{"question":"...","correct_answer":"...","explanation":"..."}}]
}}

Rules:
- Base questions only on extracted/generated course content tied to manual evidence.
- Do not invent unsupported manufacturer claims or values.
- Use PPT references only for question style and instructional framing.
- Include scenario-based troubleshooting reasoning questions with diagnostic decision steps.
- Follow Teaching DNA quiz placement and assessment rhythm when feasible.
"""
    raw = await provider.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16384,
        system_prompt="You are a strict technical assessment designer. Return JSON only.",
    )
    parsed = _safe_parse_json_object(raw)
    if parsed.get("student_version") and parsed.get("instructor_answer_key"):
        return parsed
    return _fallback_assessments(slides)


def _run_quality_review(
    slides: list[dict],
    structure: dict,
    manual_index: dict,
    visuals: list[dict],
    assessments: dict,
) -> dict:
    issues: list[str] = []
    warnings: list[str] = []
    titles_seen: set[str] = set()
    duplicated = 0

    for s in slides:
        title = _normalized_text(s.get("title")).lower()
        if title in titles_seen and title:
            duplicated += 1
        titles_seen.add(title)
        if not (s.get("bullets") or []) and s.get("type") not in {"title", "section"}:
            issues.append(f"Slide '{s.get('title')}' has no meaningful content.")

    if duplicated > 0:
        warnings.append(f"Detected {duplicated} duplicated slide titles.")

    if not assessments.get("instructor_answer_key"):
        warnings.append("Assessment answer key is empty.")

    bad_placeholders = [v for v in visuals if v.get("placeholder") and not _normalized_text(v.get("required_visual_description"))]
    if bad_placeholders:
        issues.append("One or more visual placeholders are missing required descriptions.")

    if structure.get("warning_count", 0) > 0:
        cited_warning_slides = sum(
            1 for s in slides
            if re.search(r"\bwarning|caution|danger\b", _normalized_text(s.get("title") + " " + " ".join(s.get("bullets", []))), re.IGNORECASE)
        )
        if cited_warning_slides == 0:
            warnings.append("Manual has warnings, but generated slides contain no explicit warning sections.")

    # Instructor-grade pedagogy checks (reject summary-like outputs)
    module_count = len([s for s in slides if s.get("type") == "section"])
    objective_count = len([s for s in slides if s.get("type") == "objectives"])
    practical_count = len([s for s in slides if s.get("type") == "practical"])
    quiz_count = len([s for s in slides if s.get("type") == "quiz"])
    troubleshooting_count = sum(
        1 for s in slides
        if re.search(r"\b(troubleshoot|fault|diagnostic|decision tree|signal tracing|power tracing|isolation)\b",
                     _normalized_text(s.get("title") + " " + " ".join(s.get("bullets", []))), re.IGNORECASE)
    )

    if module_count > 0 and objective_count < max(3, int(module_count * 0.7)):
        issues.append("Insufficient lesson-objective slides for module coverage.")
    if module_count > 0 and practical_count < max(3, int(module_count * 0.4)):
        issues.append("Insufficient practical/lab slides for a technical instructor course.")
    if module_count > 0 and quiz_count < max(3, int(module_count * 0.5)):
        issues.append("Insufficient knowledge-check coverage across modules.")
    if troubleshooting_count < max(3, int(module_count * 0.4)):
        issues.append("Troubleshooting reasoning content is too weak (fault tree/diagnostic flow missing).")

    # Require rich instructor notes (separate pedagogical layer)
    coaching_keywords = re.compile(
        r"\b(ask|question|demonstrat|field|common mistake|timing|discussion|debrief|coach|probe|why)\b",
        re.IGNORECASE,
    )
    rich_notes = 0
    for s in slides:
        notes = _normalized_text(s.get("speaker_notes"))
        if len(notes) >= 80 and coaching_keywords.search(notes):
            rich_notes += 1
    if rich_notes < max(6, int(len(slides) * 0.25)):
        issues.append("Instructor coaching notes are too shallow; course reads like summary instead of instruction.")

    return {
        "passed": len(issues) == 0,
        "issues": issues,
        "warnings": warnings,
        "duplicated_titles": duplicated,
        "modules_generated": len([s for s in slides if s.get("type") in {"section", "content", "objectives"}]),
        "visuals_generated": len(visuals),
        "questions_generated": len(assessments.get("instructor_answer_key") or []),
        "warnings_retained": len(manual_index.get("warnings") or []),
    }


def _is_short_overview_requested(project_dict: dict) -> bool:
    """Return True only when a short overview is explicitly requested."""
    settings = project_dict.get("settings", {}) if isinstance(project_dict.get("settings"), dict) else {}
    title = _normalized_text(project_dict.get("course_title"))
    course_type = _normalized_text(project_dict.get("course_type") or settings.get("course_type"))
    training_type = _normalized_text(project_dict.get("training_type") or settings.get("training_type"))

    probe = " ".join([title, course_type, training_type]).lower()
    explicit_overview_terms = ["short overview", "overview", "brief", "summary", "awareness"]
    if any(term in probe for term in explicit_overview_terms):
        return True

    if bool(settings.get("explicit_short_overview")):
        return True
    return False


def _coverage_targets(structure: dict, classification: dict, project_dict: dict) -> dict:
    settings = project_dict.get("settings", {}) if isinstance(project_dict.get("settings"), dict) else {}
    page_count = int(structure.get("page_count") or 0)
    min_slides, _max_slides = _target_slide_count(
        str(settings.get("slide_depth") or "standard"),
        str(settings.get("duration") or "3 days"),
    )

    short_overview = _is_short_overview_requested(project_dict)
    is_service_or_maintenance = bool(classification.get("is_maintenance")) or any(
        k in " ".join([
            _normalized_text(project_dict.get("training_type")),
            _normalized_text(project_dict.get("course_type") or settings.get("course_type")),
        ]).lower()
        for k in ["service", "maintenance"]
    )

    if page_count > 100 and not short_overview:
        min_slides = max(min_slides, 90)
    if page_count > 140 and is_service_or_maintenance and not short_overview:
        min_slides = max(min_slides, 120)
    if page_count > 180 and is_service_or_maintenance and not short_overview:
        min_slides = max(min_slides, 150)

    min_modules = max(6, min_slides // 14)
    if is_service_or_maintenance and page_count > 100 and not short_overview:
        min_modules = max(min_modules, 10)

    min_practical = 2
    min_assessment = 3
    min_diagram = 4
    if page_count > 100 and not short_overview:
        min_practical = max(min_practical, 4)
        min_assessment = max(min_assessment, 5)
        min_diagram = max(min_diagram, 8)

    return {
        "enforce": bool(page_count > 100 and not short_overview),
        "short_overview_requested": short_overview,
        "page_count": page_count,
        "min_slides": int(min_slides),
        "min_modules": int(min_modules),
        "min_practical": int(min_practical),
        "min_assessment": int(min_assessment),
        "min_diagram": int(min_diagram),
    }


def _evaluate_educational_completeness(
    slides: list[dict],
    structure: dict,
    classification: dict,
    project_dict: dict,
    ppt_refs: dict | None = None,
) -> dict:
    targets = _coverage_targets(structure, classification, project_dict)
    total = len(slides)
    types: dict[str, int] = {}
    for s in slides:
        st = str(s.get("type") or "content").lower()
        types[st] = types.get(st, 0) + 1

    module_count = types.get("section", 0)
    lesson_count = types.get("content", 0) + types.get("objectives", 0)
    practical_count = types.get("practical", 0)
    assessment_count = types.get("quiz", 0)

    diagram_kw = re.compile(r"\b(diagram|schematic|flowchart|block\s*diagram|signal\s*flow|wiring)\b", re.IGNORECASE)
    diagram_count = sum(
        1 for s in slides
        if diagram_kw.search(_normalized_text(s.get("title")))
        or any(diagram_kw.search(_normalized_text(b)) for b in (s.get("bullets") or [])[:3])
    )

    benchmark_max_slides = 0
    if isinstance(ppt_refs, dict):
        benchmark_max_slides = int(ppt_refs.get("benchmark_reference_max_slides") or 0)
        if benchmark_max_slides <= 0:
            benchmark_max_slides = max(
                [int(r.get("presentation_total_slides") or 0) for r in (ppt_refs.get("selected_references") or [])]
                or [0]
            )

    if targets["enforce"] and benchmark_max_slides >= 80:
        ratio = 0.45 if classification.get("is_maintenance") else 0.35
        targets["min_slides"] = max(int(targets["min_slides"]), int(benchmark_max_slides * ratio))
        if classification.get("is_maintenance"):
            targets["min_practical"] = max(int(targets["min_practical"]), int(max(4, benchmark_max_slides * 0.04)))
            targets["min_assessment"] = max(int(targets["min_assessment"]), int(max(5, benchmark_max_slides * 0.03)))

    reasons: list[str] = []
    if targets["enforce"]:
        if total < targets["min_slides"]:
            reasons.append(f"Only {total} slides generated; minimum expected is {targets['min_slides']}.")
        if module_count < targets["min_modules"]:
            reasons.append(f"Only {module_count} module sections generated; minimum expected is {targets['min_modules']}.")
        if lesson_count < max(20, targets["min_modules"] * 4):
            reasons.append("Insufficient lesson-depth slides for a large manual.")
        if practical_count < targets["min_practical"]:
            reasons.append(f"Only {practical_count} practical exercises generated; minimum expected is {targets['min_practical']}.")
        if assessment_count < targets["min_assessment"]:
            reasons.append(f"Only {assessment_count} assessment slides generated; minimum expected is {targets['min_assessment']}.")
        if diagram_count < targets["min_diagram"]:
            reasons.append(f"Only {diagram_count} diagram-oriented slides generated; minimum expected is {targets['min_diagram']}.")
        if benchmark_max_slides >= 80 and total < int(targets["min_slides"]):
            reasons.append(
                f"Generated deck ({total}) is far below human-reference scale ({benchmark_max_slides}) for this manual."
            )

    return {
        "complete": len(reasons) == 0,
        "reasons": reasons,
        "targets": targets,
        "benchmark_reference_max_slides": benchmark_max_slides,
        "current": {
            "total_slides": total,
            "modules": module_count,
            "lessons": lesson_count,
            "practical": practical_count,
            "assessments": assessment_count,
            "diagram": diagram_count,
        },
    }


def _extract_slide_list(raw: str) -> list[dict]:
    parsed = _safe_parse_json_object(raw)
    if isinstance(parsed, dict):
        for k in ("slides", "course", "deck", "data", "result", "presentation"):
            v = parsed.get(k)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
        for _k, v in parsed.items():
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
    if isinstance(parsed, list):
        return [x for x in parsed if isinstance(x, dict)]
    return []


def _dedupe_and_normalize_new_slides(existing: list[dict], new_slides: list[dict]) -> list[dict]:
    existing_keys = {
        (
            _normalized_text(s.get("title")).lower(),
            _normalized_text((s.get("bullets") or [""])[0]).lower(),
            str(s.get("type") or "content").lower(),
        )
        for s in existing
    }
    existing_signatures = {
        (
            str(s.get("type") or "content").lower(),
            _normalized_text(s.get("title")).lower(),
            "|".join(_normalized_text(b).lower() for b in (s.get("bullets") or [])[:4]),
        )
        for s in existing
    }
    cleaned: list[dict] = []
    salvage_candidates: list[dict] = []
    for s in new_slides:
        title = _normalized_text(s.get("title"))
        bullets = s.get("bullets") if isinstance(s.get("bullets"), list) else []
        stype = str(s.get("type") or "content").lower()
        if not title or not bullets:
            continue
        k = (title.lower(), _normalized_text(bullets[0]).lower(), stype)
        sig = (stype, title.lower(), "|".join(_normalized_text(b).lower() for b in bullets[:4]))
        if sig in existing_signatures:
            continue
        if k in existing_keys:
            salvage_candidates.append(s)
            continue
        existing_keys.add(k)
        existing_signatures.add(sig)
        cleaned.append({
            "type": stype,
            "title": title,
            "bullets": [str(b) for b in bullets[:8]],
            "speaker_notes": str(s.get("speaker_notes") or ""),
            "source_pages": [int(p) for p in (s.get("source_pages") or []) if str(p).isdigit()][:6],
        })

    # If the model produced only near-duplicate headings, salvage some slides by uniquifying titles.
    if not cleaned and salvage_candidates:
        for idx, s in enumerate(salvage_candidates[:24], start=1):
            title = _normalized_text(s.get("title"))
            bullets = s.get("bullets") if isinstance(s.get("bullets"), list) else []
            stype = str(s.get("type") or "content").lower()
            if not title or not bullets:
                continue
            cleaned.append({
                "type": stype,
                "title": f"{title} (Expansion {idx})",
                "bullets": [str(b) for b in bullets[:8]],
                "speaker_notes": str(s.get("speaker_notes") or ""),
                "source_pages": [int(p) for p in (s.get("source_pages") or []) if str(p).isdigit()][:6],
            })
    return cleaned


async def _generate_additional_modules(
    provider: Any,
    project_dict: dict,
    manual_context: str,
    outline: dict,
    knowledge_map: dict,
    existing_slides: list[dict],
    completeness: dict,
    ppt_refs: dict | None = None,
    reviewer_context: dict | None = None,
    director_assignments: list[dict] | None = None,
    benchmark_blueprint: dict | None = None,
) -> list[dict]:
    classification = _classify_course(
        project_dict.get("audience", ""), project_dict.get("training_type", ""),
    )
    is_hands_on_course = classification["is_maintenance"] and _manual_has_procedural_content(manual_context)
    if is_hands_on_course:
        expansion_requirements = """- Build a full learning experience per major module, not summary bullets.
- Include: lesson introduction, why it matters, prerequisites, scientific explanation, practical explanation,
  component relationships, operational sequence, visual explanation, coaching notes, common mistakes,
  field experience, practical exercise, hands-on lab, knowledge check, troubleshooting scenario,
  review, transition to next lesson.
- Teach diagnostic reasoning: fault trees, decision trees, measurement sequence, signal tracing, power tracing,
  isolation and repair verification.
- Instructor notes must include how to teach, what to ask, demo ideas, timing, debrief points.
- Every major technical module must include practical/lab + troubleshooting + knowledge check content."""
    else:
        expansion_requirements = """- Build a full learning experience per major module, not summary bullets.
- Include: lesson introduction, why it matters, prerequisites, conceptual explanation grounded in the
  manual, worked/interpretation examples, coaching notes, common misconceptions, knowledge check,
  review, transition to next lesson.
- Do NOT invent "Lab:"/"Practical:" slides, fault trees, calibration procedures, or repair steps —
  the source material is theoretical/conceptual, not a maintenance procedure manual.
- Instructor notes must include how to teach, what to ask, discussion prompts, timing, debrief points."""

    targets = completeness.get("targets") or {}
    needed = max(12, int(targets.get("min_slides", 0)) - len(existing_slides))
    desired = max(12, min(60, needed + 8))
    existing_titles = [_normalized_text(s.get("title")) for s in existing_slides[:200] if _normalized_text(s.get("title"))]
    ppt_summary = _summarize_ppt_refs_for_prompt(ppt_refs, max_items=20)
    reviewer_context = reviewer_context or {}
    director_assignments = director_assignments or []
    benchmark_blueprint = benchmark_blueprint if isinstance(benchmark_blueprint, dict) else {}
    weak_categories = reviewer_context.get("weak_categories") or []
    category_scores = reviewer_context.get("scores") or {}

    prompt = f"""The course is not educationally complete yet. Generate ONLY additional slides to close the coverage gaps.

Coverage gaps:
{json.dumps(completeness.get('reasons') or [], ensure_ascii=False)}

AI Instructor Review weak categories:
{json.dumps(weak_categories, ensure_ascii=False)}

AI Instructor Review category scores (0-100):
{json.dumps(category_scores, ensure_ascii=False)}

AI Training Director assignments (execute ONLY missing work):
{json.dumps(director_assignments[:24], ensure_ascii=False)}

Human benchmark blueprint (patterns only):
{json.dumps(benchmark_blueprint.get('quality_metrics') or {}, ensure_ascii=False)}

Human designer thinking profile (mindset only):
{json.dumps(benchmark_blueprint.get('designer_thinking_profile') or {}, ensure_ascii=False)}

Target add-on volume:
- Generate about {desired} additional slides.
- Include enough new modules, lessons, practical exercises, assessments, and diagram-oriented slides.

Instructor-grade expansion requirements:
{expansion_requirements}

Existing slide titles (avoid duplicates):
{json.dumps(existing_titles, ensure_ascii=False)}

Outline:
{json.dumps(outline.get('sections', [])[:40], ensure_ascii=False)}

Knowledge map topics:
{json.dumps((knowledge_map.get('topics') or [])[:50], ensure_ascii=False)}

PowerPoint references (secondary):
{ppt_summary}

Manual content (authoritative):
{manual_context[:35000]}

Return JSON only in this format:
{{
  "slides": [
    {{
      "type": "section|content|practical|quiz|summary",
      "title": "string",
      "bullets": ["string", "string"],
      "speaker_notes": "string",
      "source_pages": [1,2]
    }}
  ]
}}

Rules:
- Do not repeat existing slides.
- Execute only missing work assigned by the AI Training Director and weak-category evidence.
- Do not overwrite manual facts with PPT references.
- Match or exceed benchmark quality patterns without copying benchmark text/slides.
- Preserve master-designer rhythm: objective -> concept -> practice -> diagnostics -> verification.
- For large manuals, generate comprehensive depth rather than brief summaries.
- Include practical and assessment content as integral modules, not optional extras.
- Keep citations in bullets or notes (p.N) when possible.
- Do not produce manual-summary style output.
"""

    raw = await _generate_with_large_budget(
        provider, prompt,
        (
            "You are a technical training developer. Return strict JSON only with additional slides. "
            "Do not regenerate the whole deck; only missing modules."
        ),
        max_tokens=8000,
    )
    generated = _extract_slide_list(raw)
    return _dedupe_and_normalize_new_slides(existing_slides, generated)


def _score_0_100(value: float) -> int:
    return max(0, min(100, int(round(value))))


def _grade_from_score(score: int) -> str:
    if score >= 96:
        return "A+"
    if score >= 90:
        return "A"
    if score >= 80:
        return "B"
    if score >= 70:
        return "C"
    if score >= 60:
        return "Needs Review"
    return "Reject"


def _compute_quality_dashboard(
    slides: list[dict],
    structure: dict,
    manual_index: dict,
    visuals: list[dict],
    assessments: dict,
    source_map: list[dict],
    ppt_refs: dict,
    knowledge_map: dict,
    classification: dict,
    completeness: dict,
    quality_distribution: dict,
    quality_review: dict,
) -> dict:
    total = max(1, len(slides))
    type_counts: dict[str, int] = {}
    for s in slides:
        st = str(s.get("type") or "content").lower()
        type_counts[st] = type_counts.get(st, 0) + 1

    modules = type_counts.get("section", 0)
    objectives = type_counts.get("objectives", 0)
    practicals = type_counts.get("practical", 0)
    quizzes = type_counts.get("quiz", 0)
    content_slides = type_counts.get("content", 0)

    diagram_kw = re.compile(r"\b(diagram|schematic|flowchart|block\s*diagram|signal\s*flow|power\s*flow|routing|decision tree)\b", re.IGNORECASE)
    diagrams = sum(
        1 for s in slides
        if diagram_kw.search(_normalized_text(s.get("title")))
        or any(diagram_kw.search(_normalized_text(b)) for b in (s.get("bullets") or [])[:4])
    )

    troubleshooting_kw = re.compile(r"\b(troubleshoot|fault|diagnostic|decision tree|signal tracing|power tracing|isolation|verification)\b", re.IGNORECASE)
    troubleshooting = sum(
        1 for s in slides
        if troubleshooting_kw.search(_normalized_text(s.get("title") + " " + " ".join(s.get("bullets") or [])))
    )

    notes_kw = re.compile(r"\b(ask|question|demonstrat|field|common mistake|timing|discussion|debrief|coach|probe|why)\b", re.IGNORECASE)
    rich_notes = sum(
        1 for s in slides
        if len(_normalized_text(s.get("speaker_notes"))) >= 80 and notes_kw.search(_normalized_text(s.get("speaker_notes")))
    )

    cited = sum(1 for s in slides if (s.get("source_pages") or []))
    traceability_ratio = cited / total

    placeholders = len([v for v in visuals if v.get("placeholder")])
    visual_quality = 100 - int((placeholders / max(1, len(visuals))) * 40)

    targets = completeness.get("targets") or {}
    min_slides = max(1, int(targets.get("min_slides") or 1))
    min_modules = max(1, int(targets.get("min_modules") or 1))
    min_practical = max(1, int(targets.get("min_practical") or 1))
    min_assessment = max(1, int(targets.get("min_assessment") or 1))
    min_diagram = max(1, int(targets.get("min_diagram") or 1))

    score_educational = _score_0_100(100 - len(completeness.get("reasons") or []) * 8 - max(0, min_slides - total) * 0.25)
    score_technical = _score_0_100(55 + min(35, (quality_distribution.get("maintenance_slides", 0) / total) * 100 * 0.5) - len(quality_distribution.get("errors") or []) * 6)
    score_scientific = _score_0_100(90 - len(quality_review.get("issues") or []) * 10)
    score_engineering = _score_0_100(min(100, 45 + (quality_distribution.get("maintenance_slides", 0) / total) * 80))
    score_modules = _score_0_100((modules / min_modules) * 100)
    score_progression = _score_0_100(min(100, 45 + (objectives / max(1, modules)) * 35 + (quizzes / max(1, modules)) * 20))
    score_instructional = _score_0_100(min(100, 40 + (objectives / max(1, modules)) * 35 + (rich_notes / total) * 30))
    score_depth = _score_0_100(min(100, 40 + (content_slides / max(1, modules * 4)) * 60))
    score_visual = _score_0_100(visual_quality)
    score_diagram = _score_0_100((diagrams / min_diagram) * 100)
    score_labs = _score_0_100((practicals / min_practical) * 100)
    score_practical = _score_0_100((practicals / min_practical) * 100)
    score_assess = _score_0_100((quizzes / min_assessment) * 100)
    score_assessment_quality = _score_0_100(min(100, 45 + (quizzes / max(1, modules)) * 55))
    score_troubleshoot = _score_0_100((troubleshooting / max(3, int(modules * 0.4) or 1)) * 100)
    score_notes = _score_0_100((rich_notes / max(6, int(total * 0.25))) * 100)
    score_practical_value = _score_0_100(min(100, 35 + practicals * 8 + troubleshooting * 4))
    score_professional_appearance = _score_0_100(min(100, 50 + (100 - placeholders * 10) * 0.5))
    score_trace = _score_0_100(traceability_ratio * 100)
    score_ppt_use = _score_0_100(15 + min(85, len(ppt_refs.get("selected_references") or []) * 6))
    score_kb_use = _score_0_100(20 + min(80, len(knowledge_map.get("topics") or []) * 3))
    score_engagement = _score_0_100(min(100, 35 + quizzes * 6 + practicals * 7 + rich_notes * 2))
    score_instructor_usefulness = _score_0_100(min(100, 40 + rich_notes * 3 + objectives * 2 + troubleshooting * 2))

    scores = {
        "educational_completeness": score_educational,
        "technical_completeness": score_technical,
        "scientific_quality": score_scientific,
        "engineering_quality": score_engineering,
        "module_coverage": score_modules,
        "learning_progression": score_progression,
        "instructional_quality": score_instructional,
        "technical_depth": score_depth,
        "visual_quality": score_visual,
        "diagram_coverage": score_diagram,
        "laboratory_coverage": score_labs,
        "practical_exercises": score_practical,
        "assessments": score_assess,
        "assessment_quality": score_assessment_quality,
        "troubleshooting_coverage": score_troubleshoot,
        "practical_value": score_practical_value,
        "professional_appearance": score_professional_appearance,
        "instructor_notes": score_notes,
        "scientific_accuracy": score_scientific,
        "source_traceability": score_trace,
        "powerpoint_reference_utilization": score_ppt_use,
        "knowledge_base_utilization": score_kb_use,
        "student_engagement": score_engagement,
        "instructor_usefulness": score_instructor_usefulness,
    }

    min_threshold = 72
    overall = _score_0_100(sum(scores.values()) / max(1, len(scores)))
    weak = [k for k, v in scores.items() if v < min_threshold]
    passes = len(weak) == 0 and overall >= 78

    return {
        "overall_score": overall,
        "grade": _grade_from_score(overall),
        "min_threshold": min_threshold,
        "passes_threshold": passes,
        "scores": scores,
        "weak_categories": weak,
        "summary": {
            "slides": total,
            "modules": modules,
            "objectives": objectives,
            "content_slides": content_slides,
            "practicals": practicals,
            "assessments": quizzes,
            "diagrams": diagrams,
            "troubleshooting": troubleshooting,
            "summary_slides": type_counts.get("summary", 0),
            "rich_instructor_notes": rich_notes,
            "traceability_ratio": round(traceability_ratio, 3),
        },
    }


def _quality_improvement_tasks(
    dashboard: dict,
    completeness: dict,
    quality_distribution: dict,
    quality_review: dict,
) -> list[str]:
    tasks = []
    category_task_map = {
        "educational_completeness": "Expand full lesson packages and increase module completeness.",
        "technical_completeness": "Add technical procedures, limits, specs, and field maintenance depth.",
        "scientific_quality": "Strengthen scientific explanations and cause-effect reasoning.",
        "engineering_quality": "Add engineering logic: signal flow, power flow, component interaction.",
        "module_coverage": "Add missing major modules and prerequisite transitions.",
        "learning_progression": "Improve progression: intro -> objectives -> content -> practice -> review.",
        "instructional_quality": "Increase instructor coaching style, learner checks, and facilitation cues.",
        "technical_depth": "Increase diagnostic depth, subsystem detail, and advanced field examples.",
        "visual_quality": "Increase visual clarity, labels, and diagram-oriented explanation slides.",
        "diagram_coverage": "Add missing diagrams: flowchart/block/power/signal/decision tree.",
        "laboratory_coverage": "Add hands-on labs per major technical module.",
        "practical_exercises": "Add practical exercises with tools, steps, observations, acceptance criteria.",
        "assessments": "Add module-level knowledge checks and scenario questions.",
        "assessment_quality": "Improve distractors, explanations, and objective alignment in assessments.",
        "troubleshooting_coverage": "Add fault-tree troubleshooting and measurement-sequence scenarios.",
        "practical_value": "Improve operational field value and repair-verification activities.",
        "professional_appearance": "Improve slide professionalism and instructional visual balance.",
        "instructor_notes": "Enrich instructor notes with ask/probe/demo/debrief instructions.",
        "scientific_accuracy": "Remove unsupported claims and improve source-backed technical correctness.",
        "source_traceability": "Increase page-level source citations for technical claims and procedures.",
        "powerpoint_reference_utilization": "Use relevant PPT references for pedagogy/style without copying facts.",
        "knowledge_base_utilization": "Use more relevant KB topics and references during module expansion.",
        "student_engagement": "Increase learner engagement with interactions, scenarios, and challenge questions.",
        "instructor_usefulness": "Increase trainer usability: pacing, facilitation, remediation, debrief guidance.",
    }
    for cat in dashboard.get("weak_categories") or []:
        tasks.append(category_task_map.get(cat, f"Improve {cat.replace('_', ' ')}"))
    for r in (completeness.get("reasons") or []):
        tasks.append(r)
    for r in (quality_distribution.get("errors") or []):
        tasks.append(r)
    for r in (quality_review.get("issues") or []):
        tasks.append(r)
    # De-duplicate while preserving order.
    seen = set()
    out = []
    for t in tasks:
        k = _normalized_text(t).lower()
        if not k or k in seen:
            continue
        seen.add(k)
        out.append(t)
    return out[:30]


def _critical_quality_failures(dashboard: dict) -> dict:
    # Quality is advisory and should not block export by score.
    return {
        "is_critical": False,
        "overall": int(dashboard.get("overall_score") or 0),
        "critical_categories": [],
    }


def _coverage_snapshot(completeness: dict, dashboard: dict) -> dict:
    current = completeness.get("current") if isinstance(completeness.get("current"), dict) else {}
    summary = dashboard.get("summary") if isinstance(dashboard.get("summary"), dict) else {}
    return {
        "slides": int(current.get("total_slides") or summary.get("slides") or 0),
        "modules": int(current.get("modules") or summary.get("modules") or 0),
        "technical": int(dashboard.get("scores", {}).get("technical_completeness") or 0),
        "overall": int(dashboard.get("overall_score") or 0),
    }


def _weak_area_average(dashboard: dict, weak_categories: list[str]) -> float:
    scores = dashboard.get("scores") if isinstance(dashboard.get("scores"), dict) else {}
    vals = [int(scores.get(k) or 0) for k in weak_categories if k in scores]
    if not vals:
        vals = [int(v or 0) for v in scores.values()]
    if not vals:
        return 0.0
    return float(sum(vals) / max(1, len(vals)))


def _should_keep_candidate_version(
    base_dashboard: dict,
    base_completeness: dict,
    base_benchmark: dict,
    candidate_dashboard: dict,
    candidate_completeness: dict,
    candidate_benchmark: dict,
    weak_categories: list[str],
) -> bool:
    base_cov = _coverage_snapshot(base_completeness, base_dashboard)
    cand_cov = _coverage_snapshot(candidate_completeness, candidate_dashboard)

    base_weak_avg = _weak_area_average(base_dashboard, weak_categories)
    cand_weak_avg = _weak_area_average(candidate_dashboard, weak_categories)

    base_missing = len(base_benchmark.get("missing_areas") or []) if isinstance(base_benchmark, dict) else 0
    cand_missing = len(candidate_benchmark.get("missing_areas") or []) if isinstance(candidate_benchmark, dict) else 0

    no_regression = (
        cand_cov["overall"] >= base_cov["overall"]
        and cand_cov["slides"] >= base_cov["slides"]
        and cand_cov["modules"] >= base_cov["modules"]
    )
    weak_improved = cand_weak_avg >= (base_weak_avg + 0.8)
    benchmark_not_worse = cand_missing <= base_missing

    # Keep candidate only if it improves targeted weak areas without lowering overall course quality/coverage.
    return bool(no_regression and weak_improved and benchmark_not_worse)


def _critical_export_blockers(
    ppt_conflicts: list[dict],
    quality_review: dict,
    slide_dicts: list[dict],
) -> dict:
    blockers: list[str] = []

    # Only unresolved, explicitly critical safety conflicts can block export.
    for c in (ppt_conflicts or []):
        if not isinstance(c, dict):
            continue
        text = " ".join([
            _normalized_text(c.get("category")),
            _normalized_text(c.get("type")),
            _normalized_text(c.get("topic")),
            _normalized_text(c.get("message")),
            _normalized_text(c.get("manual_value")),
            _normalized_text(c.get("ppt_value")),
        ]).lower()
        is_safety = any(k in text for k in ["safety", "dose", "radiation", "interlock", "warning", "danger"])
        is_critical = bool(c.get("critical") or c.get("is_critical") or str(c.get("severity") or "").lower() in {"critical", "high"})
        unresolved = not bool(c.get("resolved"))
        if is_safety and is_critical and unresolved:
            blockers.append("Critical unresolved safety-value conflict detected.")
            break

    # Block only if a claim is explicitly marked critical and has no valid source.
    review_issues = quality_review.get("issues") if isinstance(quality_review.get("issues"), list) else []
    for issue in review_issues:
        txt = _normalized_text(issue).lower()
        if ("critical" in txt) and any(k in txt for k in ["source", "citation", "not found", "unsupported"]):
            blockers.append("Critical technical claim without valid source detected.")
            break

    # If no slides at all, export must be blocked.
    if not slide_dicts:
        blockers.append("No slides available for export.")

    return {
        "is_critical": len(blockers) > 0,
        "blockers": blockers,
    }


# ── Slide generation (legacy single-shot — kept for direct testing) ────────────

async def _generate_slides_json(project: dict, manual_context: str, provider: Any) -> list[dict]:
    """Legacy wrapper — delegates to _generate_slides_v2 with empty outline."""
    outline = _build_outline_fallback(project, {"headings": []})
    return await _generate_slides_v2(
        project,
        manual_context,
        outline,
        provider,
        {"topics": []},
        {"sequencing": []},
        {"modules": []},
        {"lesson_plans": []},
        teaching_dna={},
    )


# ── Request / response schemas ─────────────────────────────────────────────────

class TrainingSettings(BaseModel):
    course_title: str
    manufacturer: str = ""
    equipment_model: str = ""
    audience: str = "X-Ray Operators"
    training_type: str = "Operator Training"
    language: str = "english"
    difficulty: str = "intermediate"
    duration: str = "3 days"
    slide_depth: str = "standard"   # concise | standard | detailed | full_cert
    target_slides: int = 80
    country: str = "International"
    customer_org: str = ""
    instructor_name: str = ""
    include_notes: bool = True
    include_quizzes: bool = True
    include_practical: bool = True
    include_exam: bool = False
    course_type: str = "Complete Technical Course"
    audience_level: str = "mixed"
    output_format: str = "pptx"
    visual_density: str = "balanced"
    assessment_level: str = "standard"
    include_instructor_notes: bool = True
    include_student_workbook: bool = True
    include_answer_key: bool = True
    use_powerpoint_knowledge_base: bool = True
    use_powerpoint_references: bool = True
    use_manufacturer_approved_only: bool = False
    use_powerpoint_technical_support: bool = True
    use_powerpoint_layout_inspiration: bool = True
    use_powerpoint_terminology: bool = True
    use_powerpoint_exercises_assessments: bool = True
    use_arabic_formatting_examples: bool = True
    powerpoint_reference_strictness: str = "balanced"  # strict | balanced | broad
    powerpoint_options: dict = Field(default_factory=lambda: {
        "use_powerpoint_references": True,
        "use_manufacturer_approved_only": False,
        "use_powerpoint_technical_support": True,
        "use_powerpoint_layout_inspiration": True,
        "use_powerpoint_terminology": True,
        "use_powerpoint_exercises_assessments": True,
        "use_arabic_formatting_examples": True,
    })
    enhance_training_material: bool = True
    learn_from_expert_powerpoint: bool = False
    expert_powerpoint_doc_id: str = ""
    expert_powerpoint_doc_ids: list[str] = Field(default_factory=list)
    reanalyze_expert_powerpoint: bool = False
    enhancement_options: dict = Field(default_factory=lambda: {
        "improve_scientific_explanation": True,
        "simplify_complex_technical_language": True,
        "add_instructor_notes": True,
        "add_practical_examples": True,
        "add_safety_emphasis": True,
        "add_diagrams_visual_explanations": True,
        "add_knowledge_checks": True,
        "add_practical_exercises": True,
        "add_troubleshooting_scenarios": True,
        "add_course_summary_glossary": True,
    })


class GenerateRequest(BaseModel):
    project_id: str
    settings: TrainingSettings
    provider_id: Optional[str] = None  # "auto" | a registered provider id (e.g. "claude", "gemini") — unset/"auto" keeps the existing default


class TeachingDnaAnalyzeRequest(BaseModel):
    doc_id: str = ""
    doc_ids: list[str] = Field(default_factory=list)
    force_reanalyze: bool = False


# ── Helper: ORM → dict ─────────────────────────────────────────────────────────

def _project_to_dict(p) -> dict:
    return {
        "id":               p.id,
        "course_title":     p.course_title,
        "manufacturer":     p.manufacturer,
        "equipment_model":  p.equipment_model,
        "manual_filename":  p.manual_filename,
        "manual_page_count": p.manual_page_count,
        "audience":         p.audience,
        "training_type":    p.training_type,
        "language":         p.language,
        "difficulty":       p.difficulty,
        "status":           p.status,
        "version_num":      p.version_num,
        "settings":         p.settings or {},
        "created_at":       p.created_at.isoformat(),
        "updated_at":       p.updated_at.isoformat(),
        "slide_count":      len([s for s in p.slides if s.is_visible]),
    }


def _slide_to_dict(s) -> dict:
    return {
        "id":            s.id,
        "slide_index":   s.slide_index,
        "type":          s.slide_type,
        "title":         s.title,
        "bullets":       s.content or [],
        "speaker_notes": s.speaker_notes,
        "source_pages":  s.source_pages or [],
        "is_visible":    s.is_visible,
    }


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/training/teaching-dna/sources")
def list_teaching_dna_sources(
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import AppSetting, PptxPresentationIndex, PptxSlideIndex

    sources = (
        db.query(PptxPresentationIndex)
        .filter(PptxPresentationIndex.obsolete.is_(False))
        .filter(PptxPresentationIndex.do_not_use.is_(False))
        .all()
    )

    slides = (
        db.query(PptxSlideIndex)
        .filter(PptxSlideIndex.presentation_id.in_([s.id for s in sources] if sources else [-1]))
        .all()
    )
    slides_by_presentation: dict[str, list[Any]] = {}
    for slide in slides:
        slides_by_presentation.setdefault(str(slide.presentation_id), []).append(slide)

    rows = []
    for s in sources:
        if not (bool(s.trusted) or bool(s.manufacturer_approved) or bool(s.internal_training_reference)):
            continue
        key = _teaching_dna_storage_key(s.doc_id)
        cache_row = db.query(AppSetting).filter(AppSetting.key == key).first()
        source_slides = slides_by_presentation.get(str(s.id), [])
        speaker_notes_count = 0
        laboratories_count = 0
        quizzes_count = 0
        troubleshooting_modules_count = 0
        for slide in source_slides:
            if _normalized_text(getattr(slide, "speaker_notes", "")):
                speaker_notes_count += 1
            role = _expert_ppt_slide_role(slide)
            if role == "practical_activity":
                laboratories_count += 1
            elif role == "knowledge_check":
                quizzes_count += 1
            elif role == "troubleshooting_reasoning":
                troubleshooting_modules_count += 1

        rows.append({
            "doc_id": s.doc_id,
            "filename": s.filename,
            "course_title": s.course_title,
            "course_type": s.course_type,
            "manufacturer": s.manufacturer,
            "equipment_model": s.equipment_model,
            "language": s.language,
            "slide_count": int(s.slide_count or 0),
            "trusted": bool(s.trusted),
            "manufacturer_approved": bool(s.manufacturer_approved),
            "internal_training_reference": bool(s.internal_training_reference),
            "cached": bool(cache_row),
            "speaker_notes_count": int(speaker_notes_count),
            "laboratories_count": int(laboratories_count),
            "quizzes_count": int(quizzes_count),
            "troubleshooting_modules_count": int(troubleshooting_modules_count),
            "updated_at": s.updated_at.isoformat() if getattr(s, "updated_at", None) else None,
        })

    rows.sort(key=lambda x: (not x["manufacturer_approved"], not x["trusted"], -(x["slide_count"] or 0)))
    return rows[:100]


@router.post("/training/teaching-dna/upload-courses")
async def upload_teaching_dna_courses(
    files: list[UploadFile] = File(...),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.crud import create_rag_document
    from api.db.models import PptxPresentationIndex, PptxSlideIndex
    from api.services.doc_parser import extract_text
    from api.services.ppt_reference_service import extract_pptx_index, store_pptx_index, update_source_control

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    uploaded: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    user_id = user["id"] if user else None

    for up in files:
        filename = _normalized_text(getattr(up, "filename", "")) or "upload.pptx"
        try:
            data = await up.read()
            try:
                from api.security.uploads import validate_upload
                validate_upload(
                    filename, data,
                    declared_content_type=getattr(up, "content_type", None),
                    allowed_extensions={".pptx"},
                    max_size=200 * 1024 * 1024,
                )
            except HTTPException as ve:
                failed.append({"filename": filename, "error": str(ve.detail)})
                continue
            if len(data) < 100:
                failed.append({"filename": filename, "error": "Uploaded file appears to be empty"})
                continue

            try:
                content = extract_text(filename, data)
            except Exception:
                content = "__pptx_uploaded__"

            doc = create_rag_document(
                db,
                user_id=user_id,
                filename=filename,
                document_type="training_reference_pptx",
                content=content,
                status="ready",
            )

            extracted = extract_pptx_index(filename, data)
            store_info = store_pptx_index(db, doc.id, filename, extracted)
            update_source_control(db, doc.id, {
                "trusted": True,
                "internal_training_reference": True,
                "source_status": "trusted",
            })

            pres = db.query(PptxPresentationIndex).filter(PptxPresentationIndex.doc_id == doc.id).first()
            speaker_notes_count = 0
            laboratories_count = 0
            quizzes_count = 0
            troubleshooting_modules_count = 0

            if pres:
                source_slides = db.query(PptxSlideIndex).filter(PptxSlideIndex.presentation_id == pres.id).all()
                for slide in source_slides:
                    if _normalized_text(getattr(slide, "speaker_notes", "")):
                        speaker_notes_count += 1
                    role = _expert_ppt_slide_role(slide)
                    if role == "practical_activity":
                        laboratories_count += 1
                    elif role == "knowledge_check":
                        quizzes_count += 1
                    elif role == "troubleshooting_reasoning":
                        troubleshooting_modules_count += 1

            uploaded.append({
                "doc_id": doc.id,
                "filename": filename,
                "slide_count": int(store_info.get("slide_count") or 0),
                "speaker_notes_count": int(speaker_notes_count),
                "laboratories_count": int(laboratories_count),
                "quizzes_count": int(quizzes_count),
                "troubleshooting_modules_count": int(troubleshooting_modules_count),
            })
        except Exception as exc:
            failed.append({"filename": filename, "error": str(exc)})

    if not uploaded:
        raise HTTPException(status_code=400, detail={"uploaded": [], "failed": failed})

    return {
        "uploaded": uploaded,
        "failed": failed,
        "uploaded_count": len(uploaded),
    }


@router.post("/training/teaching-dna/analyze")
async def analyze_teaching_dna(
    body: TeachingDnaAnalyzeRequest,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.services.ai_providers.registry import provider_registry

    active = provider_registry.get_active()
    gemini = provider_registry.get("gemini")
    provider = gemini if gemini and gemini.is_configured else active

    requested_doc_ids = _normalize_doc_id_list((body.doc_ids or []) + ([body.doc_id] if _normalized_text(body.doc_id) else []))
    if not requested_doc_ids:
        raise HTTPException(status_code=422, detail="Select at least one expert course")

    payload, cached, storage_key = await _compute_master_teaching_blueprint(
        db=db,
        doc_ids=requested_doc_ids,
        provider=provider,
        force_reanalyze=bool(body.force_reanalyze),
    )
    blueprint = payload.get("master_teaching_blueprint") or payload.get("teaching_dna") or {}
    return {
        "cached": cached,
        "storage_key": storage_key,
        "teaching_dna": blueprint,
        "master_teaching_blueprint": blueprint,
        "summary": payload.get("summary", {}),
        "source_doc_ids": payload.get("source_doc_ids") or requested_doc_ids,
    }


@router.get("/training/teaching-dna/{doc_id}")
def get_teaching_dna_summary(
    doc_id: str,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import AppSetting

    key = _teaching_dna_storage_key(doc_id)
    row = db.query(AppSetting).filter(AppSetting.key == key).first()
    if not row:
        raise HTTPException(status_code=404, detail="Teaching DNA not found for this source")
    try:
        payload = json.loads(row.value or "{}")
    except Exception:
        payload = {}
    return {
        "storage_key": key,
        "summary": payload.get("summary", {}),
        "source_doc_id": payload.get("source_doc_id", doc_id),
        "updated_at": payload.get("updated_at"),
    }

@router.post("/training/upload-manual")
async def upload_manual(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """Upload a PDF manual and extract its text content. Returns a draft project ID."""
    from api.security.uploads import validate_upload

    pdf_bytes = await file.read()
    # Extension + declared MIME + %PDF magic bytes + size ceiling.
    validate_upload(
        file.filename,
        pdf_bytes,
        declared_content_type=file.content_type,
        allowed_extensions={".pdf"},
        max_size=200 * 1024 * 1024,
    )
    if len(pdf_bytes) < 100:
        raise HTTPException(status_code=400, detail="Uploaded file appears to be empty.")

    try:
        page_count, pages = _extract_pdf_pages(pdf_bytes)
    except Exception as exc:
        log.error("PDF extraction error: %s", exc)
        raise HTTPException(status_code=422, detail=f"Could not extract PDF content: {exc}")

    total_chars = sum(p["char_count"] for p in pages)
    content_pages = sum(1 for p in pages if p["char_count"] > 100)

    log.info(
        "PDF uploaded: %s — %d pages, %d content pages, %d total chars",
        file.filename, page_count, content_pages, total_chars,
    )

    # Warn if PDF appears to be image-only
    if total_chars < 500 and page_count > 0:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Extracted only {total_chars} characters from {page_count} pages. "
                "This PDF appears to be image-only (scanned). "
                "Please use a text-searchable PDF or run OCR on it first."
            ),
        )

    # Store full text per page (no truncation — full context available at generation time)
    stored_pages = [
        {
            "page_num":   p["page_num"],
            "text":       p["text"],          # full text, not truncated
            "char_count": p["char_count"],
        }
        for p in pages
    ]

    from api.db.models import TrainingProject
    project = TrainingProject(
        id=str(uuid.uuid4()),
        user_id=user["id"] if user else None,
        course_title=file.filename.removesuffix(".pdf").replace("_", " ").replace("-", " ").title(),
        manual_filename=file.filename,
        manual_page_count=page_count,
        extracted_pages=stored_pages,
        status="ready",
    )
    db.add(project)
    db.commit()

    try:
        os.makedirs(_MANUAL_PDF_DIR, exist_ok=True)
        with open(_manual_pdf_path(project.id), "wb") as f:
            f.write(pdf_bytes)
    except Exception as e:
        log.warning("Could not persist manual PDF for figure extraction (project=%s): %s", project.id, e)

    preview_pages = [
        {"page_num": p["page_num"], "text": p["text"][:300]}
        for p in stored_pages[:5]
    ]
    return {
        "project_id":    project.id,
        "filename":      file.filename,
        "page_count":    page_count,
        "content_pages": content_pages,
        "total_chars":   total_chars,
        "preview_pages": preview_pages,
        "status":        "ready",
    }


@router.post("/training/generate")
async def generate_training(
    body: GenerateRequest,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """Staged training generation via SSE with cache reuse and source traceability."""
    from api.db.models import TrainingProject, TrainingSlide
    from api.services.ai_providers.registry import provider_registry

    project = db.query(TrainingProject).filter_by(id=body.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found.")

    existing_settings = project.settings if isinstance(project.settings, dict) else {}
    existing_cache = existing_settings.get("_training_cache") if isinstance(existing_settings.get("_training_cache"), dict) else {}

    s = body.settings
    project.course_title = s.course_title
    project.manufacturer = s.manufacturer
    project.equipment_model = s.equipment_model
    project.audience = s.audience
    project.training_type = s.training_type
    project.language = s.language
    project.difficulty = s.difficulty
    merged_settings = s.model_dump()
    if existing_cache:
        merged_settings["_training_cache"] = existing_cache
    project.settings = merged_settings
    project.status = "generating"
    db.commit()

    project_dict = {
        "course_title": s.course_title,
        "manufacturer": s.manufacturer,
        "equipment_model": s.equipment_model,
        "audience": s.audience,
        "training_type": s.training_type,
        "language": s.language,
        "difficulty": s.difficulty,
        "settings": merged_settings,
        "manual_filename": project.manual_filename,
    }

    provider = None
    if body.provider_id and body.provider_id != "auto":
        explicit = provider_registry.get(body.provider_id)
        if explicit and explicit.is_configured:
            provider = explicit
    if provider is None:
        # Default (unchanged from before Claude was added): prefer Gemini when
        # configured — curriculum generation benefits from its structured JSON
        # mode — otherwise fall back to whichever provider is globally active.
        active = provider_registry.get_active()
        gemini = provider_registry.get("gemini")
        provider = gemini if gemini and gemini.is_configured else active
    if not provider:
        raise HTTPException(status_code=503, detail="No AI provider is configured for training generation.")

    async def event_stream():  # noqa: C901
        stage_names = [
            "Read Manual",
            "Extract Knowledge",
            "Search Knowledge Base",
            "Search PowerPoint Library",
            "Build Course Blueprint",
            "Build Technical Modules",
            "Enhance Training Materials",
            "Generate Diagrams",
            "Generate Assessments",
            "Assemble Course",
            "AI Training Director",
            "Export",
        ]

        cache = _settings_cache(project.settings)
        failed_optional_stages: list[str] = []
        ppt_refs: dict = {}
        ppt_conflicts: list[dict] = []
        ppt_reference_trace: list[dict] = []
        teaching_dna: dict = {}
        teaching_dna_summary: dict = {}
        human_course_benchmark: dict = {}
        benchmark_gap_analysis: dict = {}
        director_blueprint: dict = {}
        director_dashboard: dict = {}
        director_remaining_assignments: list[dict] = []

        def stage_running(step: int) -> str:
            return _sse({"type": "step", "step": step, "name": stage_names[step - 1], "status": "running"})

        def stage_done(step: int, data: dict | None = None, status: str = "done") -> str:
            payload = {"type": "step", "step": step, "name": stage_names[step - 1], "status": status}
            if data is not None:
                payload["data"] = data
            return _sse(payload)

        extracted_pages = project.extracted_pages or []
        if not extracted_pages:
            yield _sse({"type": "error", "step": 1, "error": "No extracted pages found for this project. Please re-upload the PDF."})
            project.status = "error"
            db.commit()
            return

        manual_hash = _json_hash(extracted_pages)

        yield stage_running(1)
        yield stage_done(1, {"pages": len(extracted_pages), "manual_filename": project.manual_filename})

        yield stage_running(2)
        analysis_cache = cache.get("analysis") if isinstance(cache.get("analysis"), dict) else {}
        if analysis_cache.get("manual_hash") == manual_hash:
            structure = analysis_cache.get("structure", {})
            manual_context = analysis_cache.get("manual_context", "")
        else:
            structure = _analyze_pdf_structure(extracted_pages)
            manual_context = _build_manual_context(extracted_pages)
            cache["analysis"] = {"manual_hash": manual_hash, "structure": structure, "manual_context": manual_context}
            project.settings = project.settings
            db.commit()

        _save_debug("pdf_analysis.json", {
            **structure,
            "manual_context_chars": len(manual_context),
            "manual_context_preview": manual_context[:500],
        })
        if len(manual_context.strip()) < 200:
            yield _sse({
                "type": "error",
                "step": 2,
                "error": (
                    f"PDF text extraction returned only {len(manual_context)} characters from {structure.get('page_count', 0)} pages. "
                    "The PDF may be image-only or encrypted. Use a text-searchable PDF."
                ),
                "debug": structure,
            })
            project.status = "error"
            db.commit()
            return
        yield stage_done(2, {
            "content_pages": structure.get("content_pages", 0),
            "total_chars": structure.get("total_chars", 0),
            "context_chars": len(manual_context),
        })

        yield stage_running(3)
        index_cache = cache.get("manual_index") if isinstance(cache.get("manual_index"), dict) else {}
        if index_cache.get("manual_hash") == manual_hash:
            manual_index = index_cache.get("data", {})
        else:
            manual_index = _extract_manual_index(extracted_pages)
            cache["manual_index"] = {"manual_hash": manual_hash, "data": manual_index}
            project.settings = project.settings
            db.commit()

        chunks = _chunk_manual_for_ai(extracted_pages)
        image_refs = _extract_image_refs(structure, extracted_pages)
        _save_debug("images.json", image_refs)
        yield stage_done(3, {
            "sections_detected": len(manual_index.get("sections") or []),
            "sample_sections": [s.get("name") for s in (manual_index.get("sections") or [])[:8]],
            "chunks": len(chunks),
            "figures_detected": len(manual_index.get("figures") or []),
            "tables_detected": len(manual_index.get("tables") or []),
            "warning_entries": len(manual_index.get("warnings") or []),
            "image_refs": len(image_refs),
        })

        yield stage_running(4)
        ppt_opts = s.powerpoint_options if isinstance(s.powerpoint_options, dict) else {}
        ppt_cfg = {
            "enabled": bool(s.use_powerpoint_knowledge_base and s.use_powerpoint_references),
            "strictness": (s.powerpoint_reference_strictness or "balanced").lower(),
            "use_manufacturer_approved_only": bool(
                ppt_opts.get("use_manufacturer_approved_only", s.use_manufacturer_approved_only)
            ),
            "use_powerpoint_technical_support": bool(
                ppt_opts.get("use_powerpoint_technical_support", s.use_powerpoint_technical_support)
            ),
            "use_powerpoint_layout_inspiration": bool(
                ppt_opts.get("use_powerpoint_layout_inspiration", s.use_powerpoint_layout_inspiration)
            ),
            "use_powerpoint_terminology": bool(
                ppt_opts.get("use_powerpoint_terminology", s.use_powerpoint_terminology)
            ),
            "use_powerpoint_exercises_assessments": bool(
                ppt_opts.get("use_powerpoint_exercises_assessments", s.use_powerpoint_exercises_assessments)
            ),
            "use_arabic_formatting_examples": bool(
                ppt_opts.get("use_arabic_formatting_examples", s.use_arabic_formatting_examples)
            ),
        }
        ppt_cfg["enabled"] = bool(
            s.use_powerpoint_knowledge_base and ppt_opts.get("use_powerpoint_references", s.use_powerpoint_references)
        )

        if ppt_cfg["strictness"] not in {"strict", "balanced", "broad"}:
            ppt_cfg["strictness"] = "balanced"

        topic_queries = _topic_queries_from_manual(manual_index)
        ppt_cache = cache.get("ppt_references") if isinstance(cache.get("ppt_references"), dict) else {}
        ppt_key = _json_hash({
            "manual_hash": manual_hash,
            "equipment": manual_index.get("equipment", {}),
            "course_type": s.course_type,
            "language": s.language,
            "ppt_cfg": ppt_cfg,
            "topic_queries": topic_queries,
        })

        if ppt_cfg["enabled"]:
            if ppt_cache.get("key") == ppt_key:
                ppt_refs = ppt_cache.get("data") or {}
                ppt_conflicts = ppt_cache.get("conflicts") or []
            else:
                try:
                    from api.services.ppt_reference_service import retrieve_pptx_references, detect_manual_conflicts

                    ppt_refs = retrieve_pptx_references(
                        db,
                        equipment_name=manual_index.get("equipment", {}).get("name") or s.course_title,
                        equipment_model=s.equipment_model or manual_index.get("equipment", {}).get("model", ""),
                        manufacturer=s.manufacturer or manual_index.get("equipment", {}).get("manufacturer", ""),
                        course_type=s.course_type or s.training_type,
                        language=s.language,
                        topics=topic_queries,
                        strictness=ppt_cfg["strictness"],
                        use_options=ppt_cfg,
                        max_per_topic=5,
                    )
                    ppt_conflicts = detect_manual_conflicts(manual_index, ppt_refs.get("selected_references") or [])
                except Exception as ppt_err:
                    log.warning("PPT reference retrieval failed: %s", ppt_err)
                    ppt_refs = {
                        "searched_files": 0,
                        "candidate_slides_found": 0,
                        "selected_references": [],
                        "selected_by_topic": {},
                        "message": "No suitable PowerPoint reference found",
                    }
                    ppt_conflicts = []
                    failed_optional_stages.append("ppt-reference-retrieval")

                cache["ppt_references"] = {
                    "key": ppt_key,
                    "data": ppt_refs,
                    "conflicts": ppt_conflicts,
                }
                project.settings = project.settings
                db.commit()
        else:
            ppt_refs = {
                "searched_files": 0,
                "candidate_slides_found": 0,
                "selected_references": [],
                "selected_by_topic": {},
                "message": "PowerPoint knowledge-base references disabled by configuration",
            }

        teaching_dna_enabled = bool(getattr(s, "learn_from_expert_powerpoint", False))
        teaching_dna_doc_ids = _normalize_doc_id_list(
            list(getattr(s, "expert_powerpoint_doc_ids", []) or [])
            + ([getattr(s, "expert_powerpoint_doc_id", "")] if _normalized_text(getattr(s, "expert_powerpoint_doc_id", "")) else [])
        )
        primary_teaching_dna_doc_id = teaching_dna_doc_ids[0] if teaching_dna_doc_ids else ""
        teaching_dna_cached = False
        teaching_dna_status = "disabled"
        if teaching_dna_enabled and teaching_dna_doc_ids:
            tdna_cache = cache.get("teaching_dna") if isinstance(cache.get("teaching_dna"), dict) else {}
            tdna_key = _json_hash({
                "doc_ids": teaching_dna_doc_ids,
                "force": bool(getattr(s, "reanalyze_expert_powerpoint", False)),
            })
            if tdna_cache.get("key") == tdna_key and isinstance(tdna_cache.get("data"), dict):
                teaching_dna = tdna_cache.get("data") or {}
                teaching_dna_summary = tdna_cache.get("summary") or _compact_teaching_dna_summary(teaching_dna)
                teaching_dna_cached = True
                teaching_dna_status = "loaded-from-project-cache"
            else:
                try:
                    dna_payload, dna_cached, _storage_key = await _compute_master_teaching_blueprint(
                        db=db,
                        doc_ids=teaching_dna_doc_ids,
                        provider=provider,
                        force_reanalyze=bool(getattr(s, "reanalyze_expert_powerpoint", False)),
                    )
                    teaching_dna = dna_payload.get("master_teaching_blueprint") or dna_payload.get("teaching_dna") or {}
                    teaching_dna_summary = dna_payload.get("summary") or _compact_teaching_dna_summary(teaching_dna)
                    teaching_dna_cached = bool(dna_cached)
                    teaching_dna_status = "cached" if dna_cached else "analyzed"
                    cache["teaching_dna"] = {
                        "key": tdna_key,
                        "data": teaching_dna,
                        "summary": teaching_dna_summary,
                    }
                    project.settings = project.settings
                    db.commit()
                except Exception as tdna_err:
                    log.warning("Teaching DNA load failed: %s", tdna_err)
                    teaching_dna = {}
                    teaching_dna_summary = {}
                    teaching_dna_status = "failed"
                    failed_optional_stages.append("teaching-dna")
        elif teaching_dna_enabled and not teaching_dna_doc_ids:
            teaching_dna_status = "enabled-without-source"

        yield stage_done(4, {
            "ppt_files_searched": int(ppt_refs.get("searched_files") or 0),
            "ppt_candidate_slides": int(ppt_refs.get("candidate_slides_found") or 0),
            "ppt_reference_slides_used": len(ppt_refs.get("selected_references") or []),
            "ppt_conflicts_detected": len(ppt_conflicts),
            "status": ppt_refs.get("message") or "ok",
            "teaching_dna_enabled": teaching_dna_enabled,
            "teaching_dna_source": primary_teaching_dna_doc_id,
            "teaching_dna_sources": teaching_dna_doc_ids,
            "teaching_dna_status": teaching_dna_status,
            "teaching_dna_cached": teaching_dna_cached,
            "teaching_dna_summary": teaching_dna_summary,
        })

        yield stage_running(5)

        enhance_cfg = {"enabled": bool(s.enhance_training_material), "options": s.enhancement_options or {}}
        km_cache = cache.get("knowledge_map") if isinstance(cache.get("knowledge_map"), dict) else {}
        km_key = _json_hash({
            "manual_hash": manual_hash,
            "audience": s.audience,
            "course_type": s.course_type,
            "enhance": enhance_cfg,
            "ppt_cfg": ppt_cfg,
            "teaching_dna_hash": _json_hash(teaching_dna) if teaching_dna else "",
            "ppt_refs": [
                f"{r.get('reference_file')}#{r.get('reference_slide')}"
                for r in (ppt_refs.get("selected_references") or [])[:40]
            ],
        })
        if km_cache.get("key") == km_key:
            knowledge_map = km_cache.get("data", {})
        else:
            try:
                knowledge_map = await _build_knowledge_map(provider, project_dict, manual_index, chunks, enhance_cfg, ppt_refs)
            except Exception as km_err:
                log.warning("Knowledge map generation fallback: %s", km_err)
                knowledge_map = _fallback_knowledge_map(manual_index)
                failed_optional_stages.append("knowledge-map-enrichment")
            cache["knowledge_map"] = {"key": km_key, "data": knowledge_map}
            project.settings = project.settings
            db.commit()

        lm_cache = cache.get("learning_map") if isinstance(cache.get("learning_map"), dict) else {}
        lm_key = _json_hash({
            "manual_hash": manual_hash,
            "audience": s.audience,
            "training_type": s.training_type,
            "knowledge_hash": _json_hash(knowledge_map),
            "teaching_dna_hash": _json_hash(teaching_dna) if teaching_dna else "",
        })
        if lm_cache.get("key") == lm_key:
            learning_map = lm_cache.get("data", {})
        else:
            try:
                learning_map = await _build_learning_map(provider, project_dict, knowledge_map, structure)
            except Exception as lm_err:
                log.warning("Learning map generation fallback: %s", lm_err)
                learning_map = _fallback_learning_map(knowledge_map)
                failed_optional_stages.append("learning-map-enrichment")
            cache["learning_map"] = {"key": lm_key, "data": learning_map}
            project.settings = project.settings
            db.commit()

        _save_debug("learning_map.json", learning_map)
        yield stage_done(5, {
            "topics": len(knowledge_map.get("topics") or []),
            "learning_sequence_items": len(learning_map.get("sequencing") or []),
            "equipment": manual_index.get("equipment", {}),
        })

        if ppt_conflicts:
            yield _sse({
                "type": "warning",
                "message": f"Detected {len(ppt_conflicts)} potential PPT-manual technical conflicts. Manual values were kept as authoritative.",
                "failed_stages": [],
            })

        yield stage_running(6)
        try:
            outline = await _generate_outline(project_dict, manual_context, structure, provider, knowledge_map, ppt_refs, teaching_dna)
            if not outline.get("sections"):
                raise ValueError("Empty sections list")
        except Exception as outline_err:
            log.warning("Outline generation failed (%s) - using fallback", outline_err)
            outline = _build_outline_fallback(project_dict, structure)
            outline["_fallback_reason"] = str(outline_err)
            failed_optional_stages.append("course-planning")

        cm_cache = cache.get("curriculum_map") if isinstance(cache.get("curriculum_map"), dict) else {}
        cm_key = _json_hash({
            "manual_hash": manual_hash,
            "outline_hash": _json_hash(outline.get("sections") or []),
            "learning_hash": _json_hash(learning_map),
            "knowledge_hash": _json_hash(knowledge_map),
        })
        if cm_cache.get("key") == cm_key:
            curriculum_map = cm_cache.get("data", {})
        else:
            try:
                curriculum_map = await _build_curriculum_map(provider, project_dict, outline, learning_map, knowledge_map, teaching_dna)
            except Exception as cm_err:
                log.warning("Curriculum map generation fallback: %s", cm_err)
                curriculum_map = _fallback_curriculum_map(outline)
                failed_optional_stages.append("curriculum-map-enrichment")
            cache["curriculum_map"] = {"key": cm_key, "data": curriculum_map}
            project.settings = project.settings
            db.commit()

        _save_debug("curriculum_map.json", curriculum_map)
        _save_debug("outline.json", outline)
        yield stage_done(6, {
            "sections": len(outline.get("sections", [])),
            "curriculum_modules": len(curriculum_map.get("modules") or []),
            "course_type": outline.get("course_type") or s.course_type,
            "source": "fallback" if "_fallback_reason" in outline else "ai",
        })

        yield stage_running(7)
        ip_cache = cache.get("instruction_plan") if isinstance(cache.get("instruction_plan"), dict) else {}
        ip_key = _json_hash({
            "curriculum_hash": _json_hash(curriculum_map),
            "learning_hash": _json_hash(learning_map),
            "audience": s.audience,
            "training_type": s.training_type,
        })
        if ip_cache.get("key") == ip_key:
            instruction_plan = ip_cache.get("data", {})
        else:
            try:
                instruction_plan = await _build_instruction_plan(provider, project_dict, curriculum_map, learning_map, teaching_dna)
            except Exception as ip_err:
                log.warning("Instruction plan generation fallback: %s", ip_err)
                instruction_plan = _fallback_instruction_plan(curriculum_map)
                failed_optional_stages.append("instruction-plan-enrichment")
            cache["instruction_plan"] = {"key": ip_key, "data": instruction_plan}
            project.settings = project.settings
            db.commit()

        _save_debug("instruction_plan.json", instruction_plan)
        enhancement_summary = {
            "enabled": bool(enhance_cfg.get("enabled", True)),
            "selected_options": [k for k, v in (enhance_cfg.get("options") or {}).items() if v],
            "instruction_plans": len(instruction_plan.get("lesson_plans") or []),
            "locked_fields": [
                "manufacturer procedures", "safety limits", "technical values", "calibration values",
                "electrical values", "radiation dose values", "part numbers", "fault codes",
            ],
        }
        yield stage_done(7, enhancement_summary)

        yield stage_running(8)
        visual_cache = cache.get("visual_plan") if isinstance(cache.get("visual_plan"), dict) else {}
        vp_key = _json_hash({"outline": outline.get("sections", []), "manual_hash": manual_hash, "density": s.visual_density})
        if visual_cache.get("key") == vp_key:
            visuals = visual_cache.get("data", [])
        else:
            try:
                visuals = await _build_visual_plan(provider, outline, manual_index, project_dict.get("settings", {}), ppt_refs, teaching_dna)
            except Exception as vis_err:
                log.warning("Visual planning failed, using fallback: %s", vis_err)
                visuals = _fallback_visual_plan(outline, manual_index)
                failed_optional_stages.append("visual-plan")
            cache["visual_plan"] = {"key": vp_key, "data": visuals}
            project.settings = project.settings
            db.commit()
        _save_debug("visual_plan.json", visuals)
        yield stage_done(8, {
            "visuals_generated": len(visuals),
            "placeholders": len([v for v in visuals if v.get("placeholder")]),
        })

        yield stage_running(9)
        try:
            assessments = await _build_assessment_bank(provider, outline, knowledge_map, [], project_dict.get("settings", {}), ppt_refs, teaching_dna)
        except Exception as asm_err:
            log.warning("Assessment planning failed, using fallback: %s", asm_err)
            assessments = {"student_version": [], "instructor_answer_key": []}
            failed_optional_stages.append("assessment-plan")
        _save_debug("assessment_bank.json", assessments)
        yield stage_done(9, {
            "questions": len(assessments.get("instructor_answer_key") or []),
            "student_questions": len(assessments.get("student_version") or []),
        })

        human_course_benchmark = _build_human_course_benchmark(
            db=db,
            manual_index=manual_index,
            project_dict=project_dict,
            ppt_refs=ppt_refs,
            topic_queries=topic_queries,
        )
        _save_debug("course_quality_blueprint.json", human_course_benchmark)

        director_blueprint = _build_training_director_blueprint(
            project_dict=project_dict,
            structure=structure,
            manual_index=manual_index,
            knowledge_map=knowledge_map,
            learning_map=learning_map,
            curriculum_map=curriculum_map,
            instruction_plan=instruction_plan,
            assessments=assessments,
            visuals=visuals,
            ppt_refs=ppt_refs,
            human_benchmark=human_course_benchmark,
        )
        _save_debug("training_director_blueprint.json", director_blueprint)

        yield stage_running(10)
        try:
            slide_dicts = await _generate_slides_v2(
                project_dict,
                manual_context,
                outline,
                provider,
                knowledge_map,
                learning_map,
                curriculum_map,
                instruction_plan,
                human_course_benchmark,
                ppt_refs,
                teaching_dna,
            )
        except Exception as gen_err:
            log.error("Slide generation failed: %s", gen_err)
            _save_debug("generation_error.json", {"error": str(gen_err)})
            yield _sse({"type": "error", "step": 10, "error": str(gen_err)})
            project.status = "error"
            db.commit()
            return
        if not slide_dicts:
            yield _sse({"type": "error", "step": 10, "error": "Model returned 0 slides for formatting output."})
            project.status = "error"
            db.commit()
            return
        _enforce_instructor_notes_and_visual_placeholders(slide_dicts, visuals)

        # Rescue path: if first-pass generation is too short (commonly from truncated JSON),
        # expand before AI Instructor Review so quality loop doesn't start from an under-sized deck.
        pre_review_classification = _classify_course(project_dict.get("audience", ""), project_dict.get("training_type", ""))
        pre_review_completeness = _evaluate_educational_completeness(
            slide_dicts,
            structure,
            pre_review_classification,
            project_dict,
            ppt_refs,
        )
        pre_targets = pre_review_completeness.get("targets") or {}
        pre_floor = max(36, int(int(pre_targets.get("min_slides") or 36) * 0.7))
        rescue_round = 0
        while len(slide_dicts) < pre_floor and rescue_round < 4:
            rescue_round += 1
            before = len(slide_dicts)
            rescue_reasons = list(pre_review_completeness.get("reasons") or [])
            rescue_reasons.append(
                f"Initial generation size is too short ({before} slides). Expand coverage to at least {pre_floor} slides before AI Instructor Review."
            )
            rescue_completeness = dict(pre_review_completeness)
            rescue_completeness["reasons"] = rescue_reasons

            yield _sse({
                "type": "warning",
                "message": (
                    f"Pre-review rescue expansion {rescue_round}/4: initial deck is too short ({before} slides). "
                    "Generating additional modules before AI Instructor Review."
                ),
                "failed_stages": [],
            })

            try:
                extra_rescue = await _generate_additional_modules(
                    provider=provider,
                    project_dict=project_dict,
                    manual_context=manual_context,
                    outline=outline,
                    knowledge_map=knowledge_map,
                    existing_slides=slide_dicts,
                    completeness=rescue_completeness,
                    ppt_refs=ppt_refs,
                )
            except Exception as rescue_err:
                log.warning("Pre-review rescue expansion failed in round %d: %s", rescue_round, rescue_err)
                failed_optional_stages.append("pre-review-rescue")
                break

            if not extra_rescue:
                failed_optional_stages.append("pre-review-rescue")
                break

            slide_dicts.extend(extra_rescue)
            _enforce_instructor_notes_and_visual_placeholders(slide_dicts, visuals)
            pre_review_completeness = _evaluate_educational_completeness(
                slide_dicts,
                structure,
                pre_review_classification,
                project_dict,
                ppt_refs,
            )

        yield stage_running(11)
        classification = _classify_course(project_dict.get("audience", ""), project_dict.get("training_type", ""))
        auto_expansion_rounds: list[dict] = []
        quality_improvement_attempts: list[dict] = []
        quality_dashboard: dict = {}
        max_improvement_iterations = 5
        version_history: list[dict] = []
        best_version: dict = {
            "slides": list(slide_dicts),
            "quality_dashboard": {},
            "completeness": {},
            "benchmark_gap_analysis": {},
            "quality_distribution": {},
            "quality_review": {},
            "label": "Version 1",
        }

        yield _sse({
            "type": "warning",
            "message": (
                "AI Training Director is supervising downstream engines and will assign only missing work "
                "to Curriculum Planner, Technical Module Generator, Training Material Generator, "
                "Visual & Diagram Engine, Assessment Engine, and AI Instructor Review."
            ),
            "failed_stages": [],
        })

        for improvement_round in range(0, max_improvement_iterations + 1):
            quality_distribution = _compute_content_distribution(slide_dicts, classification)
            quality_review = _run_quality_review(slide_dicts, structure, manual_index, visuals, assessments)
            completeness = _evaluate_educational_completeness(slide_dicts, structure, classification, project_dict, ppt_refs)
            source_map_snapshot = _build_source_map(slide_dicts, manual_index, knowledge_map)
            quality_dashboard = _compute_quality_dashboard(
                slides=slide_dicts,
                structure=structure,
                manual_index=manual_index,
                visuals=visuals,
                assessments=assessments,
                source_map=source_map_snapshot,
                ppt_refs=ppt_refs,
                knowledge_map=knowledge_map,
                classification=classification,
                completeness=completeness,
                quality_distribution=quality_distribution,
                quality_review=quality_review,
            )
            benchmark_gap_analysis = _analyze_against_human_benchmark(
                slides=slide_dicts,
                quality_dashboard=quality_dashboard,
                benchmark=human_course_benchmark,
            )

            version_history.append({
                "version": f"Version {len(version_history) + 1}",
                "slides": len(slide_dicts),
                "overall_score": int(quality_dashboard.get("overall_score") or 0),
                "module_coverage": int(quality_dashboard.get("scores", {}).get("module_coverage") or 0),
                "technical_coverage": int(quality_dashboard.get("scores", {}).get("technical_completeness") or 0),
            })

            # Always preserve the strongest valid version seen so far.
            if not best_version.get("quality_dashboard"):
                best_version = {
                    "slides": list(slide_dicts),
                    "quality_dashboard": quality_dashboard,
                    "completeness": completeness,
                    "benchmark_gap_analysis": benchmark_gap_analysis,
                    "quality_distribution": quality_distribution,
                    "quality_review": quality_review,
                    "label": version_history[-1]["version"],
                }
            else:
                best_overall = int(best_version.get("quality_dashboard", {}).get("overall_score") or 0)
                cur_overall = int(quality_dashboard.get("overall_score") or 0)
                best_slides = len(best_version.get("slides") or [])
                cur_slides = len(slide_dicts)
                if (cur_overall > best_overall) or (cur_overall == best_overall and cur_slides >= best_slides):
                    best_version = {
                        "slides": list(slide_dicts),
                        "quality_dashboard": quality_dashboard,
                        "completeness": completeness,
                        "benchmark_gap_analysis": benchmark_gap_analysis,
                        "quality_distribution": quality_distribution,
                        "quality_review": quality_review,
                        "label": version_history[-1]["version"],
                    }

            if quality_dashboard.get("passes_threshold", False) and benchmark_gap_analysis.get("passes", True):
                break

            if improvement_round >= max_improvement_iterations:
                break

            director_assignments = _director_assignments(
                dashboard=quality_dashboard,
                completeness=completeness,
                quality_distribution=quality_distribution,
                quality_review=quality_review,
                benchmark_gaps=benchmark_gap_analysis,
            )
            director_remaining_assignments = director_assignments

            tasks = _quality_improvement_tasks(
                dashboard=quality_dashboard,
                completeness=completeness,
                quality_distribution=quality_distribution,
                quality_review=quality_review,
            )
            for gap in (benchmark_gap_analysis.get("missing_areas") or []):
                if gap not in tasks:
                    tasks.append(gap)

            if not tasks and director_assignments:
                tasks = [f"{a.get('engine')}: {a.get('directive')}" for a in director_assignments[:16]]

            yield _sse({
                "type": "warning",
                "message": (
                    f"AI Training Director started supervised improvement cycle {improvement_round + 1}/{max_improvement_iterations}. "
                    f"Weak categories: {', '.join((quality_dashboard.get('weak_categories') or [])[:6])}"
                ),
                "failed_stages": [],
                "director_assignments": director_assignments,
                "benchmark_gaps": benchmark_gap_analysis,
            })

            before_count = len(slide_dicts)
            completeness_for_repair = dict(completeness)
            completeness_for_repair["reasons"] = tasks
            try:
                extra_slides = await _generate_additional_modules(
                    provider=provider,
                    project_dict=project_dict,
                    manual_context=manual_context,
                    outline=outline,
                    knowledge_map=knowledge_map,
                    existing_slides=slide_dicts,
                    completeness=completeness_for_repair,
                    ppt_refs=ppt_refs,
                    reviewer_context=quality_dashboard,
                    director_assignments=director_assignments,
                    benchmark_blueprint=human_course_benchmark,
                )
            except Exception as improve_err:
                log.warning("AI improvement cycle failed in round %d: %s", improvement_round + 1, improve_err)
                quality_improvement_attempts.append({
                    "round": improvement_round + 1,
                    "tasks": tasks,
                    "director_assignments": director_assignments,
                    "added_slides": 0,
                    "error": str(improve_err),
                })
                failed_optional_stages.append("ai-improvement-cycle")
                break

            if not extra_slides:
                quality_improvement_attempts.append({
                    "round": improvement_round + 1,
                    "tasks": tasks,
                    "director_assignments": director_assignments,
                    "added_slides": 0,
                    "error": "No additional slides returned",
                })
                failed_optional_stages.append("ai-improvement-cycle")
                break

            slide_dicts.extend(extra_slides)
            _enforce_instructor_notes_and_visual_placeholders(slide_dicts, visuals)
            candidate_slides = list(slide_dicts)
            candidate_quality_distribution = _compute_content_distribution(candidate_slides, classification)
            candidate_quality_review = _run_quality_review(candidate_slides, structure, manual_index, visuals, assessments)
            candidate_completeness = _evaluate_educational_completeness(candidate_slides, structure, classification, project_dict, ppt_refs)
            candidate_source_map_snapshot = _build_source_map(candidate_slides, manual_index, knowledge_map)
            candidate_quality_dashboard = _compute_quality_dashboard(
                slides=candidate_slides,
                structure=structure,
                manual_index=manual_index,
                visuals=visuals,
                assessments=assessments,
                source_map=candidate_source_map_snapshot,
                ppt_refs=ppt_refs,
                knowledge_map=knowledge_map,
                classification=classification,
                completeness=candidate_completeness,
                quality_distribution=candidate_quality_distribution,
                quality_review=candidate_quality_review,
            )
            candidate_benchmark_gap = _analyze_against_human_benchmark(
                slides=candidate_slides,
                quality_dashboard=candidate_quality_dashboard,
                benchmark=human_course_benchmark,
            )

            keep_candidate = _should_keep_candidate_version(
                base_dashboard=quality_dashboard,
                base_completeness=completeness,
                base_benchmark=benchmark_gap_analysis,
                candidate_dashboard=candidate_quality_dashboard,
                candidate_completeness=candidate_completeness,
                candidate_benchmark=candidate_benchmark_gap,
                weak_categories=quality_dashboard.get("weak_categories") or [],
            )

            if keep_candidate:
                slide_dicts = candidate_slides
                quality_distribution = candidate_quality_distribution
                quality_review = candidate_quality_review
                completeness = candidate_completeness
                quality_dashboard = candidate_quality_dashboard
                benchmark_gap_analysis = candidate_benchmark_gap
                after_count = len(slide_dicts)
                added = max(0, after_count - before_count)
                auto_expansion_rounds.append({
                    "round": improvement_round + 1,
                    "added_slides": added,
                    "total_slides": after_count,
                    "accepted": True,
                })
                quality_improvement_attempts.append({
                    "round": improvement_round + 1,
                    "tasks": tasks,
                    "director_assignments": director_assignments,
                    "added_slides": added,
                    "accepted": True,
                    "error": "",
                })
            else:
                # Restore previous version if targeted weak areas did not improve safely.
                slide_dicts = list(best_version.get("slides") or slide_dicts[:before_count])
                auto_expansion_rounds.append({
                    "round": improvement_round + 1,
                    "added_slides": 0,
                    "total_slides": len(slide_dicts),
                    "accepted": False,
                })
                quality_improvement_attempts.append({
                    "round": improvement_round + 1,
                    "tasks": tasks,
                    "director_assignments": director_assignments,
                    "added_slides": 0,
                    "accepted": False,
                    "error": "Candidate version did not improve selected weak areas without regression; restored best version.",
                })
                break

        # Ensure final export uses the best preserved version.
        if best_version.get("slides"):
            slide_dicts = list(best_version.get("slides") or slide_dicts)
            quality_dashboard = best_version.get("quality_dashboard") or quality_dashboard
            completeness = best_version.get("completeness") or completeness
            benchmark_gap_analysis = best_version.get("benchmark_gap_analysis") or benchmark_gap_analysis
            quality_distribution = best_version.get("quality_distribution") or quality_distribution
            quality_review = best_version.get("quality_review") or quality_review

        director_remaining_assignments = _director_assignments(
            dashboard=quality_dashboard,
            completeness=completeness,
            quality_distribution=quality_distribution,
            quality_review=quality_review,
            benchmark_gaps=benchmark_gap_analysis,
        )
        director_dashboard = _build_training_director_dashboard(
            director_blueprint=director_blueprint,
            quality_dashboard=quality_dashboard,
            quality_distribution=quality_distribution,
            completeness=completeness,
            remaining_tasks=director_remaining_assignments,
            benchmark_gaps=benchmark_gap_analysis,
        )

        quality_combined = {
            "distribution": quality_distribution,
            "review": quality_review,
            "completeness": completeness,
            "quality_dashboard": quality_dashboard,
            "human_course_benchmark": human_course_benchmark,
            "benchmark_gap_analysis": benchmark_gap_analysis,
            "training_director_blueprint": director_blueprint,
            "training_director_dashboard": director_dashboard,
            "training_director_assignments": director_remaining_assignments,
            "auto_expansion_rounds": auto_expansion_rounds,
            "quality_improvement_attempts": quality_improvement_attempts,
            "version_history": version_history,
            "best_version": {
                "label": best_version.get("label") or "Version 1",
                "slides": len(best_version.get("slides") or []),
                "overall_score": int((best_version.get("quality_dashboard") or {}).get("overall_score") or 0),
            },
        }
        _save_debug("quality_gate.json", quality_combined)
        cache["quality_gate"] = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            **quality_combined,
        }
        project.settings = project.settings
        db.commit()

        # Deterministic module-numbering fixup, after every rescue/expansion
        # pass has finished contributing slides — see _renumber_section_slides.
        _renumber_section_slides(slide_dicts)
        _validate_and_fix_quiz_slides(slide_dicts)
        _ensure_section_objectives_slides(slide_dicts)
        _insert_agenda_slide(slide_dicts)
        _ensure_course_info_slide(slide_dicts, project_dict)

        source_map = _build_source_map(slide_dicts, manual_index, knowledge_map)
        ppt_reference_trace = _build_ppt_reference_trace(slide_dicts, ppt_refs)
        # One entry per slide in the deck — silently capping at a fixed
        # number (previously [:12]) meant any course with more than 12
        # slides shipped a references slide that just stopped listing
        # sources partway through, with no indication anything was cut.
        # Paginate instead: several slides of ~15 rows each, same as a
        # human designer would split a long reference list.
        REFS_PER_SLIDE = 15
        ref_rows = [
            f"{row['module_or_slide']} - Source: Manual page {row['page_number']}, section {row['manual_section']}"
            for row in source_map
        ] or ["Source map generated from manual traceability index."]
        ref_pages = [ref_rows[i:i + REFS_PER_SLIDE] for i in range(0, len(ref_rows), REFS_PER_SLIDE)] or [ref_rows]
        for page_idx, page_bullets in enumerate(ref_pages, start=1):
            title = "References and Source Map"
            if len(ref_pages) > 1:
                title += f" ({page_idx}/{len(ref_pages)})"
            slide_dicts.append({
                "type": "references",
                "title": title,
                "bullets": page_bullets,
                "speaker_notes": "Use this slide to verify source traceability and prevent unsupported claims.",
                "source_pages": [r.get("page_number", 0) for r in source_map[:6] if int(r.get("page_number") or 0) > 0],
            })

        _save_debug("slides.json", slide_dicts)
        db.query(TrainingSlide).filter_by(project_id=project.id).delete()
        db.commit()

        for idx, sd in enumerate(slide_dicts):
            slide = TrainingSlide(
                project_id=project.id,
                slide_index=idx,
                slide_type=sd.get("type", "content"),
                title=sd.get("title", "")[:512],
                content=sd.get("bullets", []),
                speaker_notes=sd.get("speaker_notes", ""),
                source_pages=sd.get("source_pages", []),
                is_visible=True,
            )
            db.add(slide)
            db.flush()
            yield _sse({
                "type": "slide",
                "index": idx,
                "slide": {
                    "id": slide.id,
                    "slide_index": idx,
                    "type": slide.slide_type,
                    "title": slide.title,
                    "bullets": slide.content,
                    "speaker_notes": slide.speaker_notes,
                    "source_pages": slide.source_pages,
                    "is_visible": True,
                },
            })
        db.commit()

        all_citations = _extract_all_citations(slide_dicts)
        unique_pages = sorted(set(all_citations))
        citation_summary = {
            "total_citations": len(all_citations),
            "pages_cited_count": len(unique_pages),
            "coverage": f"{len(unique_pages)}/{structure.get('page_count', 0)} pages",
        }
        _save_debug("citations.json", citation_summary)
        yield stage_done(10, {
            "slides_saved": len(slide_dicts),
            "citation_summary": citation_summary,
            "auto_added_slides": sum(int(x.get("added_slides") or 0) for x in auto_expansion_rounds),
        })

        step11_status = "done"
        if (
            not quality_distribution.get("passed", True)
            or not quality_review.get("passed", True)
            or not quality_dashboard.get("passes_threshold", False)
        ):
            step11_status = "warning"
        yield stage_done(11, {
            "quality_gate": quality_distribution,
            "quality_review": quality_review,
            "educational_completeness": completeness,
            "quality_dashboard": quality_dashboard,
            "ai_training_director": {
                "pipeline": _AI_TRAINING_DIRECTOR_PIPELINE,
                "supervised_engines": _AI_TRAINING_DIRECTOR_ENGINES,
                "overall_score": quality_dashboard.get("overall_score"),
                "grade": quality_dashboard.get("grade"),
                "weak_categories": quality_dashboard.get("weak_categories") or [],
                "human_course_benchmark": human_course_benchmark,
                "benchmark_gap_analysis": benchmark_gap_analysis,
                "blueprint": director_blueprint,
                "dashboard": director_dashboard,
                "remaining_assignments": director_remaining_assignments,
            },
            "auto_expansion_rounds": auto_expansion_rounds,
            "quality_improvement_attempts": quality_improvement_attempts,
        }, status=step11_status)

        if quality_distribution.get("errors") or (completeness.get("reasons") or []) or not quality_dashboard.get("passes_threshold", False):
            yield _sse({
                "type": "quality_warning",
                "errors": (
                    quality_distribution.get("errors", [])
                    + (completeness.get("reasons") or [])
                    + ([f"Weak quality categories: {', '.join(quality_dashboard.get('weak_categories') or [])}"] if quality_dashboard.get("weak_categories") else [])
                ),
                "warnings": quality_distribution.get("warnings", []) + quality_review.get("warnings", []),
                "safety_pct": quality_distribution.get("safety_pct", 0),
                "maintenance_slides": quality_distribution.get("maintenance_slides", 0),
                "total_slides": quality_distribution.get("total_slides", 0),
                "benchmark_gap_analysis": benchmark_gap_analysis,
                "training_director_dashboard": director_dashboard,
            })

        export_blockers = _critical_export_blockers(
            ppt_conflicts=ppt_conflicts,
            quality_review=quality_review,
            slide_dicts=slide_dicts,
        )
        if not quality_dashboard.get("passes_threshold", False) or not benchmark_gap_analysis.get("passes", True):
            missing = quality_dashboard.get("weak_categories") or []
            attempts = quality_improvement_attempts or []
            suggested_plan = [
                "Increase module depth and add lesson packages per weak module.",
                "Increase practical labs with tools, observations, and completion checklists.",
                "Increase troubleshooting scenarios with decision/fault trees and measurement logic.",
                "Expand instructor coaching notes with questioning and debrief patterns.",
                "Match or exceed human benchmark metrics without copying benchmark course content.",
            ]
            if export_blockers.get("is_critical"):
                project.status = "error"
                db.commit()
                yield _sse({
                    "type": "error",
                    "step": 11,
                    "error": "Export blocked due to critical technical/safety blockers (not quality score).",
                    "debug": {
                        "missing_quality_categories": missing,
                        "improvement_attempts": attempts,
                        "training_director_assignments": director_remaining_assignments,
                        "training_director_dashboard": director_dashboard,
                        "suggested_action_plan": suggested_plan,
                        "overall_grade": quality_dashboard.get("grade"),
                        "overall_score": quality_dashboard.get("overall_score"),
                        "export_blockers": export_blockers.get("blockers") or [],
                        "human_course_benchmark": human_course_benchmark,
                        "benchmark_gap_analysis": benchmark_gap_analysis,
                        "completeness": completeness,
                        "quality_gate": quality_distribution,
                        "quality_review": quality_review,
                        "quality_dashboard": quality_dashboard,
                    },
                })
                return

            yield _sse({
                "type": "warning",
                "message": "Course exported as draft. Quality improvements are recommended.",
                "failed_stages": ["ai-instructor-review-threshold"],
                "debug": {
                    "missing_quality_categories": missing,
                    "improvement_attempts": attempts,
                    "training_director_assignments": director_remaining_assignments,
                    "training_director_dashboard": director_dashboard,
                    "suggested_action_plan": suggested_plan,
                    "overall_grade": quality_dashboard.get("grade"),
                    "overall_score": quality_dashboard.get("overall_score"),
                    "human_course_benchmark": human_course_benchmark,
                    "benchmark_gap_analysis": benchmark_gap_analysis,
                },
            })

        yield stage_running(12)
        pptx_size_kb = 0
        export_artifacts: dict[str, dict] = {}
        try:
            from api.utils.pptx_gen import build_pptx
            from api.utils.docgen import build_docx

            _apply_image_tags(slide_dicts)
            deck_images = _build_images_for_slides(project.id, slide_dicts)

            log.info("EXPORT_STARTED | type=pptx project_id=%s version=instructor", project.id)
            pptx_bytes = build_pptx(project_dict, slide_dicts, version="instructor", images=deck_images)
            if not pptx_bytes:
                raise RuntimeError("PPTX output is empty")
            pptx_size_kb = round(len(pptx_bytes) / 1024, 1)
            safe_title = _safe_course_slug(project.course_title, 60)
            pptx_filename = f"{safe_title}_instructor.pptx"
            pptx_path = _artifact_path(project.id, pptx_filename)
            _write_artifact(pptx_path, pptx_bytes)
            pptx_ok, pptx_size = _verify_artifact(pptx_path)
            if not pptx_ok:
                raise RuntimeError("PPTX artifact verification failed")
            export_artifacts["pptx"] = {
                "filename": pptx_filename,
                "path": pptx_path,
                "size": pptx_size,
                "download_url": _download_url_for("/training/export/pptx/{project_id}", project.id, "version=instructor"),
            }
            log.info(
                "EXPORT_COMPLETED | type=pptx project_id=%s filename=%s path=%s size=%d download_url=%s",
                project.id,
                pptx_filename,
                pptx_path,
                pptx_size,
                export_artifacts["pptx"]["download_url"],
            )

            log.info("EXPORT_STARTED | type=docx project_id=%s doc_type=instructor_guide", project.id)
            docx_md = _build_docx_content_from_slide_dicts(project_dict, slide_dicts, "instructor_guide")

            class _StageDocxRecord:
                id = project.id
                mode = "training"
                topic = project.course_title
                domain_label = f"{project.manufacturer} {project.equipment_model}".strip()
                word_count = len(docx_md.split())
                kb_chunks_used = 0

            docx_bytes = build_docx(_StageDocxRecord(), docx_md, lang="en")
            if not docx_bytes:
                raise RuntimeError("DOCX output is empty")
            docx_filename = f"{safe_title}_Instructor_Guide.docx"
            docx_path = _artifact_path(project.id, docx_filename)
            _write_artifact(docx_path, docx_bytes)
            docx_ok, docx_size = _verify_artifact(docx_path)
            if not docx_ok:
                raise RuntimeError("DOCX artifact verification failed")
            export_artifacts["docx"] = {
                "filename": docx_filename,
                "path": docx_path,
                "size": docx_size,
                "download_url": _download_url_for("/training/export/docx/{project_id}", project.id, "doc_type=instructor_guide"),
            }
            log.info(
                "EXPORT_COMPLETED | type=docx project_id=%s filename=%s path=%s size=%d download_url=%s",
                project.id,
                docx_filename,
                docx_path,
                docx_size,
                export_artifacts["docx"]["download_url"],
            )

            log.info("EXPORT_STARTED | type=zip project_id=%s", project.id)
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(f"{safe_title}_Instructor.pptx", build_pptx(project_dict, slide_dicts, version="instructor", images=deck_images))
                zf.writestr(f"{safe_title}_Student.pptx", build_pptx(project_dict, slide_dicts, version="student", images=deck_images))
                zf.writestr(f"{safe_title}_Instructor_Guide.docx", docx_bytes)

                student_md = _build_docx_content_from_slide_dicts(project_dict, slide_dicts, "student_handbook")

                class _StageDocxStudentRecord:
                    id = project.id
                    mode = "training"
                    topic = project.course_title
                    domain_label = f"{project.manufacturer} {project.equipment_model}".strip()
                    word_count = len(student_md.split())
                    kb_chunks_used = 0

                student_docx = build_docx(_StageDocxStudentRecord(), student_md, lang="en")
                zf.writestr(f"{safe_title}_Student_Handbook.docx", student_docx)
                zf.writestr("README.txt", (
                    f"Training Package: {project.course_title}\n"
                    f"Equipment: {project.manufacturer} {project.equipment_model}\n"
                    f"Generated: {datetime.now(timezone.utc).strftime('%d %B %Y')}\n"
                ))

            zip_bytes = zip_buf.getvalue()
            if not zip_bytes:
                raise RuntimeError("ZIP output is empty")
            zip_filename = f"{safe_title}_Training_Package.zip"
            zip_path = _artifact_path(project.id, zip_filename)
            _write_artifact(zip_path, zip_bytes)
            zip_ok, zip_size = _verify_artifact(zip_path)
            if not zip_ok:
                raise RuntimeError("ZIP artifact verification failed")
            export_artifacts["zip"] = {
                "filename": zip_filename,
                "path": zip_path,
                "size": zip_size,
                "download_url": _download_url_for("/training/export/zip/{project_id}", project.id),
            }
            log.info(
                "EXPORT_COMPLETED | type=zip project_id=%s filename=%s path=%s size=%d download_url=%s",
                project.id,
                zip_filename,
                zip_path,
                zip_size,
                export_artifacts["zip"]["download_url"],
            )

            _save_debug("ppt-data.json", {
                "slide_count": len(slide_dicts),
                "pptx_size_bytes": len(pptx_bytes),
                "pptx_size_kb": pptx_size_kb,
                "export_artifacts": export_artifacts,
            })
        except Exception as pptx_err:
            log.exception("EXPORT_FAILED | project_id=%s error=%s", project.id, pptx_err)
            _save_debug("pptx_error.json", {"error": str(pptx_err)})
            project.status = "error"
            db.commit()
            yield _sse({
                "type": "error",
                "step": 12,
                "error": f"Export verification failed before completion: {pptx_err}",
            })
            return

        generation_summary = {
            "generation_status": "draft",
            "draft_status": "Draft — Instructor Review Recommended",
            "instructor_review_recommended": bool(
                not quality_dashboard.get("passes_threshold", False)
                or not benchmark_gap_analysis.get("passes", True)
                or bool(quality_distribution.get("errors") or quality_review.get("issues") or completeness.get("reasons"))
            ),
            "manual_pages_analyzed": structure.get("page_count", 0),
            "sections_extracted": len(manual_index.get("sections") or []),
            "figures_detected": len(manual_index.get("figures") or []),
            "tables_detected": len(manual_index.get("tables") or []),
            "modules_generated": len(outline.get("sections") or []),
            "visuals_generated": len(visuals),
            "exercises_generated": len([s for s in slide_dicts if s.get("type") == "practical"]),
            "questions_generated": len(assessments.get("instructor_answer_key") or []),
            "warnings_retained": len(manual_index.get("warnings") or []),
            "content_requiring_instructor_review": quality_review.get("issues", []) + quality_distribution.get("errors", []),
            "failed_optional_stages": failed_optional_stages,
            "source_map_entries": len(source_map),
            "powerpoint_files_searched": int(ppt_refs.get("searched_files") or 0),
            "powerpoint_candidate_slides_found": int(ppt_refs.get("candidate_slides_found") or 0),
            "powerpoint_reference_slides_used": len(ppt_refs.get("selected_references") or []),
            "manufacturer_approved_powerpoint_slides_used": int(ppt_refs.get("manufacturer_approved_used") or 0),
            "powerpoint_conflicts_detected": len(ppt_conflicts),
            "powerpoint_duplicates_removed": max(0, int(ppt_refs.get("candidate_slides_found") or 0) - len(ppt_refs.get("selected_references") or [])),
            "visual_references_applied": len([r for r in (ppt_refs.get("selected_references") or []) if r.get("reference_category") == "visual"]),
            "arabic_formatting_references_applied": len([r for r in (ppt_refs.get("selected_references") or []) if r.get("reference_category") == "arabic_formatting"]),
            "ppt_reference_trace_count": len(ppt_reference_trace),
            "ppt_reference_message": ppt_refs.get("message") or "",
            "educational_completeness_passed": bool(completeness.get("complete", True)),
            "educational_completeness_reasons": completeness.get("reasons", []),
            "auto_expansion_rounds": auto_expansion_rounds,
            "quality_improvement_attempts": quality_improvement_attempts,
            "version_history": version_history,
            "quality_dashboard": quality_dashboard,
            "overall_instructor_grade": quality_dashboard.get("grade"),
            "overall_quality_score": quality_dashboard.get("overall_score"),
            "export_artifacts": export_artifacts,
        }

        cache["last_generation_summary"] = generation_summary
        cache["last_source_map"] = source_map
        cache["last_ppt_reference_trace"] = ppt_reference_trace
        cache["last_ppt_conflicts"] = ppt_conflicts
        project.settings = project.settings
        project.status = "complete"
        db.commit()

        yield stage_done(12, {
            "pptx_size_kb": pptx_size_kb,
            "slides_saved": len(slide_dicts),
            "generation_status": "draft",
            "draft_status": "Draft — Instructor Review Recommended",
            "instructor_review_recommended": generation_summary.get("instructor_review_recommended", True),
            "generation_summary": generation_summary,
        }, status="warning" if failed_optional_stages else "done")

        if failed_optional_stages:
            yield _sse({
                "type": "warning",
                "message": "Some optional enhancement stages failed. Core manual-based generation completed successfully.",
                "failed_stages": failed_optional_stages,
                "retry_hint": "Re-run generation with the same configuration to retry failed optional stages only (cached stages are reused).",
            })

        yield _sse({
            "type": "done",
            "project_id": project.id,
            "slide_count": len(slide_dicts),
            "generation_status": "draft",
            "draft_status": "Draft — Instructor Review Recommended",
            "instructor_review_recommended": generation_summary.get("instructor_review_recommended", True),
            "generation_summary": generation_summary,
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/training/projects")
def list_projects(
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
    limit: int = 50,
):
    from api.db.models import TrainingProject
    q = db.query(TrainingProject).order_by(TrainingProject.updated_at.desc())
    if user:
        q = q.filter(TrainingProject.user_id == user["id"])
    return [_project_to_dict(p) for p in q.limit(limit).all()]


@router.get("/training/project/{project_id}")
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import TrainingProject
    p = db.query(TrainingProject).filter_by(id=project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found.")
    result = _project_to_dict(p)
    result["slides"] = [_slide_to_dict(s) for s in p.slides if s.is_visible]
    return result


@router.delete("/training/project/{project_id}", status_code=204)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import TrainingProject
    p = db.query(TrainingProject).filter_by(id=project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found.")
    db.delete(p)
    db.commit()


class SlideUpdateRequest(BaseModel):
    title: Optional[str] = None
    bullets: Optional[list[str]] = None
    speaker_notes: Optional[str] = None
    is_visible: Optional[bool] = None


@router.patch("/training/project/{project_id}/slide/{slide_idx}")
def update_slide(
    project_id: str,
    slide_idx: int,
    body: SlideUpdateRequest,
    db: Session = Depends(get_db),
):
    from api.db.models import TrainingSlide
    slide = db.query(TrainingSlide).filter_by(
        project_id=project_id, slide_index=slide_idx
    ).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found.")
    if body.title is not None:
        slide.title = body.title
    if body.bullets is not None:
        slide.content = body.bullets
    if body.speaker_notes is not None:
        slide.speaker_notes = body.speaker_notes
    if body.is_visible is not None:
        slide.is_visible = body.is_visible
    db.commit()
    return _slide_to_dict(slide)


# ── Export endpoints ───────────────────────────────────────────────────────────

@router.get("/training/export/pptx/{project_id}")
def export_pptx(
    project_id: str,
    version: str = "combined",
    db: Session = Depends(get_db),
):
    """Export the training project as a .pptx file.
    version: combined | operator | engineer | instructor | student"""
    from api.db.models import TrainingProject
    from api.utils.pptx_gen import build_pptx

    log.info("EXPORT_STARTED | type=pptx project_id=%s version=%s", project_id, version)
    log.info("DOWNLOAD_REQUEST | type=pptx project_id=%s", project_id)

    p = db.query(TrainingProject).filter_by(id=project_id).first()
    if not p:
        log.warning("DOWNLOAD_RESPONSE | type=pptx project_id=%s status=404 reason=project_not_found", project_id)
        raise HTTPException(status_code=404, detail="Project not found.")
    if not p.slides:
        log.warning("DOWNLOAD_RESPONSE | type=pptx project_id=%s status=400 reason=no_slides", project_id)
        raise HTTPException(status_code=400, detail="No slides generated yet. Run generation first.")

    project_dict = _project_to_dict(p)
    slides = [_slide_to_dict(s) for s in p.slides if s.is_visible]
    _apply_image_tags(slides)
    deck_images = _build_images_for_slides(project_id, slides)

    try:
        pptx_bytes = build_pptx(project_dict, slides, version=version, images=deck_images)
    except Exception as exc:
        log.exception("EXPORT_FAILED | type=pptx project_id=%s version=%s error=%s", project_id, version, exc)
        raise HTTPException(status_code=500, detail="Failed to build PPTX export") from exc

    if not pptx_bytes:
        log.error("EXPORT_FAILED | type=pptx project_id=%s reason=empty_output", project_id)
        raise HTTPException(status_code=500, detail="Generated PPTX is empty")

    safe_title = _safe_course_slug(p.course_title, 60)
    filename = f"{safe_title}_{version}.pptx"
    output_path = _artifact_path(project_id, filename)
    size = _write_artifact(output_path, pptx_bytes)
    ok, verified_size = _verify_artifact(output_path)
    if not ok:
        log.error("EXPORT_FAILED | type=pptx project_id=%s filename=%s path=%s reason=verification_failed", project_id, filename, output_path)
        raise HTTPException(status_code=500, detail="PPTX export verification failed")

    download_url = _download_url_for("/training/export/pptx/{project_id}", project_id, f"version={version}")
    log.info(
        "EXPORT_COMPLETED | type=pptx project_id=%s filename=%s path=%s size=%d download_url=%s",
        project_id,
        filename,
        output_path,
        verified_size,
        download_url,
    )
    log.info("DOWNLOAD_RESPONSE | type=pptx project_id=%s status=200", project_id)
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        filename=filename,
    )


def _build_docx_content(project, slides, doc_type: str) -> str:
    """Render a Markdown string from slides for DOCX conversion."""
    is_instructor = doc_type == "instructor_guide"
    lines = [
        f"# {project.course_title}",
        f"**Equipment:** {project.manufacturer} {project.equipment_model}",
        f"**Audience:** {project.audience}",
        f"**Training Type:** {project.training_type}",
        f"**Date:** {datetime.now(timezone.utc).strftime('%d %B %Y')}",
        "", "---", "",
    ]
    for s in slides:
        if not s.is_visible:
            continue
        lines.append(f"## {s.title}")
        for b in (s.content or []):
            lines.append(f"- {b}")
        if is_instructor and s.speaker_notes:
            lines.append(f"\n> **Instructor Notes:** {s.speaker_notes}")
        if s.source_pages:
            pages_str = ", ".join(str(pg) for pg in s.source_pages)
            lines.append(f"\n*Source: Manual pp. {pages_str}*")
        lines.append("")
    return "\n".join(lines)


def _build_docx_content_from_slide_dicts(project_dict: dict, slide_dicts: list[dict], doc_type: str) -> str:
    """Render a Markdown string from generated slide dictionaries for DOCX conversion."""
    is_instructor = doc_type == "instructor_guide"
    lines = [
        f"# {project_dict.get('course_title', 'Training Course')}",
        f"**Equipment:** {project_dict.get('manufacturer', '')} {project_dict.get('equipment_model', '')}".strip(),
        f"**Audience:** {project_dict.get('audience', '')}",
        f"**Training Type:** {project_dict.get('training_type', '')}",
        f"**Date:** {datetime.now(timezone.utc).strftime('%d %B %Y')}",
        "",
        "---",
        "",
    ]
    for s in slide_dicts:
        lines.append(f"## {_normalized_text(s.get('title'))}")
        for b in (s.get("bullets") or []):
            lines.append(f"- {b}")
        if is_instructor and s.get("speaker_notes"):
            lines.append(f"\n> **Instructor Notes:** {s.get('speaker_notes')}")
        if s.get("source_pages"):
            pages_str = ", ".join(str(pg) for pg in s.get("source_pages") if isinstance(pg, int) or str(pg).isdigit())
            if pages_str:
                lines.append(f"\n*Source: Manual pp. {pages_str}*")
        lines.append("")
    return "\n".join(lines)


@router.get("/training/export/docx/{project_id}")
def export_docx(
    project_id: str,
    doc_type: str = "instructor_guide",
    db: Session = Depends(get_db),
):
    """Export as DOCX. doc_type: instructor_guide | student_handbook"""
    from api.db.models import TrainingProject

    log.info("EXPORT_STARTED | type=docx project_id=%s doc_type=%s", project_id, doc_type)
    log.info("DOWNLOAD_REQUEST | type=docx project_id=%s", project_id)

    p = db.query(TrainingProject).filter_by(id=project_id).first()
    if not p:
        log.warning("DOWNLOAD_RESPONSE | type=docx project_id=%s status=404 reason=project_not_found", project_id)
        raise HTTPException(status_code=404, detail="Project not found.")
    if not p.slides:
        log.warning("DOWNLOAD_RESPONSE | type=docx project_id=%s status=400 reason=no_slides", project_id)
        raise HTTPException(status_code=400, detail="No slides generated yet.")

    content_md = _build_docx_content(p, p.slides, doc_type)

    from api.utils.docgen import build_docx

    class FakeRecord:
        id = p.id
        mode = "training"
        topic = p.course_title
        domain_label = f"{p.manufacturer} {p.equipment_model}".strip()
        word_count = len(content_md.split())
        kb_chunks_used = 0

    try:
        docx_bytes = build_docx(FakeRecord(), content_md, lang="en")
    except Exception as exc:
        log.exception("EXPORT_FAILED | type=docx project_id=%s doc_type=%s error=%s", project_id, doc_type, exc)
        raise HTTPException(status_code=500, detail="Failed to build DOCX export") from exc

    if not docx_bytes:
        log.error("EXPORT_FAILED | type=docx project_id=%s reason=empty_output", project_id)
        raise HTTPException(status_code=500, detail="Generated DOCX is empty")

    label = "Instructor_Guide" if doc_type == "instructor_guide" else "Student_Handbook"
    safe_title = _safe_course_slug(p.course_title, 60)
    filename = f"{safe_title}_{label}.docx"
    output_path = _artifact_path(project_id, filename)
    _write_artifact(output_path, docx_bytes)
    ok, verified_size = _verify_artifact(output_path)
    if not ok:
        log.error("EXPORT_FAILED | type=docx project_id=%s filename=%s path=%s reason=verification_failed", project_id, filename, output_path)
        raise HTTPException(status_code=500, detail="DOCX export verification failed")

    download_url = _download_url_for("/training/export/docx/{project_id}", project_id, f"doc_type={doc_type}")
    log.info(
        "EXPORT_COMPLETED | type=docx project_id=%s filename=%s path=%s size=%d download_url=%s",
        project_id,
        filename,
        output_path,
        verified_size,
        download_url,
    )
    log.info("DOWNLOAD_RESPONSE | type=docx project_id=%s status=200", project_id)
    return FileResponse(
        output_path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=filename,
    )


@router.get("/training/export/zip/{project_id}")
def export_zip(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Export a complete training package as ZIP (PPTX × 2 + DOCX × 2 + README)."""
    from api.db.models import TrainingProject
    from api.utils.pptx_gen import build_pptx
    from api.utils.docgen import build_docx

    log.info("EXPORT_STARTED | type=zip project_id=%s", project_id)
    log.info("DOWNLOAD_REQUEST | type=zip project_id=%s", project_id)

    p = db.query(TrainingProject).filter_by(id=project_id).first()
    if not p:
        log.warning("DOWNLOAD_RESPONSE | type=zip project_id=%s status=404 reason=project_not_found", project_id)
        raise HTTPException(status_code=404, detail="Project not found.")
    if not p.slides:
        log.warning("DOWNLOAD_RESPONSE | type=zip project_id=%s status=400 reason=no_slides", project_id)
        raise HTTPException(status_code=400, detail="No slides generated yet.")

    project_dict = _project_to_dict(p)
    slides = [_slide_to_dict(s) for s in p.slides if s.is_visible]
    _apply_image_tags(slides)
    deck_images = _build_images_for_slides(project_id, slides)
    safe_title = _safe_course_slug(p.course_title, 50)

    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{safe_title}_Instructor.pptx",
                        build_pptx(project_dict, slides, version="instructor", images=deck_images))
            zf.writestr(f"{safe_title}_Student.pptx",
                        build_pptx(project_dict, slides, version="student", images=deck_images))

            class FakeRec:
                id = p.id; mode = "training"; topic = p.course_title
                domain_label = f"{p.manufacturer} {p.equipment_model}".strip()
                word_count = 1000; kb_chunks_used = 0

            zf.writestr(f"{safe_title}_Instructor_Guide.docx",
                        build_docx(FakeRec(), _build_docx_content(p, p.slides, "instructor_guide"), lang="en"))
            zf.writestr(f"{safe_title}_Student_Handbook.docx",
                        build_docx(FakeRec(), _build_docx_content(p, p.slides, "student_handbook"), lang="en"))

            zf.writestr("README.txt", (
                f"Training Package: {p.course_title}\n"
                f"Equipment: {p.manufacturer} {p.equipment_model}\n"
                f"Generated: {datetime.now(timezone.utc).strftime('%d %B %Y')}\n\n"
                f"Files:\n"
                f"  {safe_title}_Instructor.pptx  — Instructor version with answers and notes\n"
                f"  {safe_title}_Student.pptx     — Student version without answers\n"
                f"  {safe_title}_Instructor_Guide.docx\n"
                f"  {safe_title}_Student_Handbook.docx\n"
            ))
    except Exception as exc:
        log.exception("EXPORT_FAILED | type=zip project_id=%s error=%s", project_id, exc)
        raise HTTPException(status_code=500, detail="Failed to build ZIP export") from exc

    zip_bytes = buf.getvalue()
    if not zip_bytes:
        log.error("EXPORT_FAILED | type=zip project_id=%s reason=empty_output", project_id)
        raise HTTPException(status_code=500, detail="Generated ZIP is empty")

    filename = f"{safe_title}_Training_Package.zip"
    output_path = _artifact_path(project_id, filename)
    _write_artifact(output_path, zip_bytes)
    ok, verified_size = _verify_artifact(output_path)
    if not ok:
        log.error("EXPORT_FAILED | type=zip project_id=%s filename=%s path=%s reason=verification_failed", project_id, filename, output_path)
        raise HTTPException(status_code=500, detail="ZIP export verification failed")

    download_url = _download_url_for("/training/export/zip/{project_id}", project_id)
    log.info(
        "EXPORT_COMPLETED | type=zip project_id=%s filename=%s path=%s size=%d download_url=%s",
        project_id,
        filename,
        output_path,
        verified_size,
        download_url,
    )
    log.info("DOWNLOAD_RESPONSE | type=zip project_id=%s status=200", project_id)
    return FileResponse(
        output_path,
        media_type="application/zip",
        filename=filename,
    )


@router.get("/training/export/verify/{project_id}")
def verify_export_readiness(
    project_id: str,
    db: Session = Depends(get_db),
):
    """Verify export artifacts exist and are downloadable before showing success."""
    from api.db.models import TrainingProject
    from api.utils.pptx_gen import build_pptx
    from api.utils.docgen import build_docx

    log.info("EXPORT_VERIFY_STARTED | project_id=%s", project_id)
    p = db.query(TrainingProject).filter_by(id=project_id).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found.")
    if not p.slides:
        raise HTTPException(status_code=400, detail="No slides generated yet.")

    project_dict = _project_to_dict(p)
    slides = [_slide_to_dict(s) for s in p.slides if s.is_visible]
    _apply_image_tags(slides)
    deck_images = _build_images_for_slides(project_id, slides)
    safe_title = _safe_course_slug(p.course_title, 60)
    errors: list[str] = []
    artifacts: dict[str, dict] = {}

    def _check(kind: str, filename: str, data: bytes, url: str) -> None:
        path = _artifact_path(project_id, filename)
        _write_artifact(path, data)
        ok, size = _verify_artifact(path)
        artifacts[kind] = {
            "ok": ok,
            "filename": filename,
            "path": path,
            "size": size,
            "download_url": url,
        }
        if not ok:
            errors.append(f"{kind} artifact verification failed")

    try:
        pptx_data = build_pptx(project_dict, slides, version="instructor", images=deck_images)
        _check(
            "pptx",
            f"{safe_title}_instructor.pptx",
            pptx_data,
            _download_url_for("/training/export/pptx/{project_id}", project_id, "version=instructor"),
        )

        content_md = _build_docx_content(p, p.slides, "instructor_guide")

        class FakeRecord:
            id = p.id
            mode = "training"
            topic = p.course_title
            domain_label = f"{p.manufacturer} {p.equipment_model}".strip()
            word_count = len(content_md.split())
            kb_chunks_used = 0

        docx_data = build_docx(FakeRecord(), content_md, lang="en")
        _check(
            "docx",
            f"{safe_title}_Instructor_Guide.docx",
            docx_data,
            _download_url_for("/training/export/docx/{project_id}", project_id, "doc_type=instructor_guide"),
        )

        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.writestr(f"{safe_title}_Instructor.pptx", build_pptx(project_dict, slides, version="instructor", images=deck_images))
            zf.writestr(f"{safe_title}_Student.pptx", build_pptx(project_dict, slides, version="student", images=deck_images))
            zf.writestr(f"{safe_title}_Instructor_Guide.docx", docx_data)

            student_md = _build_docx_content(p, p.slides, "student_handbook")

            class FakeStudentRecord:
                id = p.id
                mode = "training"
                topic = p.course_title
                domain_label = f"{p.manufacturer} {p.equipment_model}".strip()
                word_count = len(student_md.split())
                kb_chunks_used = 0

            student_docx = build_docx(FakeStudentRecord(), student_md, lang="en")
            zf.writestr(f"{safe_title}_Student_Handbook.docx", student_docx)
            zf.writestr("README.txt", "Training package verification artifact")
        _check(
            "zip",
            f"{safe_title}_Training_Package.zip",
            zip_buf.getvalue(),
            _download_url_for("/training/export/zip/{project_id}", project_id),
        )
    except Exception as exc:
        log.exception("EXPORT_VERIFY_FAILED | project_id=%s error=%s", project_id, exc)
        errors.append(str(exc))

    ready = len(errors) == 0 and all(v.get("ok") for v in artifacts.values())
    log.info("EXPORT_VERIFY_COMPLETED | project_id=%s ready=%s details=%s", project_id, ready, artifacts)
    return {
        "ready": ready,
        "project_id": project_id,
        "artifacts": artifacts,
        "errors": errors,
    }


# ── Slide approval & correction endpoints ──────────────────────────────────────

class _SlideApproveBody(BaseModel):
    approved: bool = True


class _SlideCorrectionBody(BaseModel):
    original_content: dict = {}
    corrected_content: dict
    correction_reason: str = ""
    corrected_by: str = ""


@router.post("/training/projects/{project_id}/slides/{slide_idx}/approve")
def approve_training_slide(
    project_id: str,
    slide_idx: int,
    body: _SlideApproveBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Approve or reject a training slide (authenticated users only)."""
    from api.db.models import TrainingProject, TrainingSlide
    from datetime import datetime, timezone

    proj = db.query(TrainingProject).filter(TrainingProject.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # Ownership check: only project owner or users with no user_id restriction
    user_id = str(user.get("id") or "")
    if proj.user_id and proj.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorised to modify this project")

    slide = db.query(TrainingSlide).filter(
        TrainingSlide.project_id == project_id,
        TrainingSlide.slide_index == slide_idx,
    ).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    slide.approval_status = "approved" if body.approved else "rejected"
    slide.approved_at = datetime.now(timezone.utc) if body.approved else None
    db.commit()
    return {"ok": True, "slide_idx": slide_idx, "status": slide.approval_status}


@router.post("/training/projects/{project_id}/slides/{slide_idx}/correct")
def correct_training_slide(
    project_id: str,
    slide_idx: int,
    body: _SlideCorrectionBody,
    db: Session = Depends(get_db),
    user: dict = Depends(require_auth),
):
    """Record an instructor correction for a training slide (authenticated users only)."""
    from api.db.models import TrainingProject, TrainingSlide, SlideCorrection

    proj = db.query(TrainingProject).filter(TrainingProject.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")

    # Ownership check
    user_id = str(user.get("id") or "")
    if proj.user_id and proj.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorised to modify this project")

    slide = db.query(TrainingSlide).filter(
        TrainingSlide.project_id == project_id,
        TrainingSlide.slide_index == slide_idx,
    ).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    # Capture original before any mutation
    original = body.original_content or {
        "title": slide.title,
        "content": slide.content,
        "speaker_notes": slide.speaker_notes,
    }

    correction = SlideCorrection(
        slide_id=slide.id,
        slide_type="training",
        original_content=original,
        corrected_content=body.corrected_content,
        correction_reason=body.correction_reason,
        corrected_by=body.corrected_by or user.get("name") or user.get("email") or "instructor",
    )
    db.add(correction)

    # Apply corrections using the actual TrainingSlide fields
    cc = body.corrected_content
    if "title" in cc:
        slide.title = cc["title"]
    # "content" or "bullets" both map to slide.content (JSON list of bullet strings)
    if "content" in cc:
        slide.content = cc["content"]
    elif "bullets" in cc:
        slide.content = cc["bullets"]
    # "speaker_notes" or "notes" map to slide.speaker_notes
    if "speaker_notes" in cc:
        slide.speaker_notes = cc["speaker_notes"]
    elif "notes" in cc:
        slide.speaker_notes = cc["notes"]

    db.commit()
    return {"ok": True, "correction_id": correction.id}


class _SlideRefineBody(BaseModel):
    instruction: str


@router.post("/training/projects/{project_id}/slides/{slide_idx}/refine")
async def refine_training_slide(
    project_id: str,
    slide_idx: int,
    body: _SlideRefineBody,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """AI-assisted single-slide refinement from a natural-language instruction
    (e.g. "make this shorter", "add a worked example", "simplify the wording").

    Modeled on Gamma.app's post-generation "chat with your deck" agent: rather
    than only supporting manual field-by-field correction (see
    correct_training_slide above), let the instructor describe the change in
    plain language and have the model apply it — while staying grounded in
    the same source manual excerpt the slide was originally built from, so
    citations stay accurate instead of drifting into invented content.
    """
    from api.db.models import TrainingProject, TrainingSlide, SlideCorrection
    from api.services.ai_providers.registry import provider_registry

    instruction = _normalized_text(body.instruction)
    if not instruction:
        raise HTTPException(status_code=400, detail="instruction is required.")

    proj = db.query(TrainingProject).filter(TrainingProject.id == project_id).first()
    if not proj:
        raise HTTPException(status_code=404, detail="Project not found")
    user_id = str((user or {}).get("id") or "")
    if proj.user_id and user_id and proj.user_id != user_id:
        raise HTTPException(status_code=403, detail="Not authorised to modify this project")

    slide = db.query(TrainingSlide).filter(
        TrainingSlide.project_id == project_id,
        TrainingSlide.slide_index == slide_idx,
    ).first()
    if not slide:
        raise HTTPException(status_code=404, detail="Slide not found")

    active = provider_registry.get_active()
    gemini = provider_registry.get("gemini")
    provider = gemini if gemini and gemini.is_configured else active
    if not provider:
        raise HTTPException(status_code=503, detail="No AI provider is configured.")

    extracted_pages = proj.extracted_pages or []
    source_pages = set(int(p) for p in (slide.source_pages or []) if str(p).isdigit())
    manual_excerpt = "\n\n".join(
        f"[Manual page {p.get('page_num')}]\n{p.get('text', '')}"
        for p in extracted_pages
        if int(p.get("page_num") or 0) in source_pages
    )[:8000] or _build_manual_context(extracted_pages, max_chars=6000)

    original = {
        "title": slide.title,
        "bullets": slide.content or [],
        "speaker_notes": slide.speaker_notes or "",
    }

    prompt = f"""You are refining ONE slide of an existing technical training deck based on an
instructor's plain-language request. Keep every technical fact grounded in the manual excerpt
below — never invent specifications, values, or procedures that aren't in it.

CURRENT SLIDE (type={slide.slide_type}):
{json.dumps(original, ensure_ascii=False, indent=2)}

INSTRUCTOR'S REQUEST:
{instruction}

RELEVANT MANUAL EXCERPT (authoritative source — do not contradict it):
{manual_excerpt}

Return JSON only, in this exact shape:
{{"title": "string", "bullets": ["string", ...], "speaker_notes": "string"}}

Rules:
- Apply the instructor's request precisely; do not change anything they didn't ask about.
- Keep (p.N) citations in bullets where the original had them, adjusted only if content moved.
- Do not add markdown formatting, headings, or text outside the JSON object."""

    raw = await provider.chat(
        [{"role": "user", "content": prompt}],
        max_tokens=16384,
        system_prompt="You are a precise instructional editor. Return strict JSON only.",
    )
    raw = _repair_page_range_json_arrays(raw)
    parsed = _safe_parse_json_object(raw)
    if not parsed or "bullets" not in parsed:
        raise HTTPException(status_code=502, detail="AI refinement did not return a usable slide.")

    updated = {
        "title": _normalized_text(parsed.get("title")) or slide.title,
        "bullets": [str(b) for b in (parsed.get("bullets") or [])] or slide.content,
        "speaker_notes": _normalized_text(parsed.get("speaker_notes")) or slide.speaker_notes,
    }

    db.add(SlideCorrection(
        slide_id=slide.id,
        slide_type="training",
        original_content=original,
        corrected_content=updated,
        correction_reason=f"AI refinement: {instruction}",
        corrected_by="AI Refinement Agent",
    ))
    slide.title = updated["title"][:512]
    slide.content = updated["bullets"]
    slide.speaker_notes = updated["speaker_notes"]
    db.commit()

    return {"ok": True, "slide_idx": slide_idx, "slide": updated}
