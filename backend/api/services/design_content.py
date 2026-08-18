"""
Deterministic design-intent detection + LLM structured-content generation
for the AI Tool Router's visual-design pipeline (see design_orchestrator.py).

Intent detection is deliberately keyword-based, not an LLM/tool-router
decision — same reasoning as canva_chat_intent.py's detect_canva_intent:
a design request must never silently fall through to a text-only reply
just because the model chose not to call a tool.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

log = logging.getLogger(__name__)

# Ordered so more-specific phrases (e.g. "course cover") are checked before
# a shorter substring (e.g. "cover") could ever be added — avoids surprises
# if this table grows later.
_DESIGN_TYPE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("certificate", ("certificate", "certification")),
    ("infographic", ("infographic",)),
    ("brochure", ("brochure",)),
    ("course_cover", ("course cover",)),
    ("presentation_cover", ("presentation cover",)),
    ("training_visual", ("training visual", "training material")),
    ("social_media", ("social media", "instagram post", "linkedin post", "social post")),
    ("banner", ("banner",)),
    ("flyer", ("flyer",)),
    ("poster", ("poster",)),
]

_EDIT_VERBS = re.compile(r"\b(change|shorten|switch|make it|use another|regenerate|try again|"
                          r"generate another|redo|different|edit)\b", re.IGNORECASE)


def detect_design_intent(message: str) -> Optional[str]:
    """Returns a design_type key (matching design_specs.DIMENSIONS) if the
    message expresses a new visual-design request, else None."""
    if not message:
        return None
    lowered = message.lower()
    for design_type, phrases in _DESIGN_TYPE_KEYWORDS:
        if any(phrase in lowered for phrase in phrases):
            return design_type
    return None


def detect_design_edit_intent(message: str, has_prior_workflow: bool) -> Optional[dict[str, Any]]:
    """Returns a dict of edits to merge into the prior DesignWorkflow's
    structured_spec (plus optional control flags like "regenerate"/
    "new_template"), or None if this message isn't an edit request — only
    meaningful when a prior workflow exists for this conversation."""
    if not has_prior_workflow or not message:
        return None
    lowered = message.lower()
    if not _EDIT_VERBS.search(lowered):
        return None

    edits: dict[str, Any] = {}

    title_match = re.search(r"(?:change|set|update)\s+the\s+title\s+to\s+(.+)", message, re.IGNORECASE)
    if title_match:
        edits["title"] = title_match.group(1).strip(" .\"'")

    if re.search(r"\bshorten\b|\bmake it shorter\b|\bmore concise\b", lowered):
        edits["shorten"] = True

    if re.search(r"\b(arabic|عرب)\b", lowered) and re.search(r"switch|change|make it|use", lowered):
        edits["language"] = "ar"
        edits["direction"] = "rtl"
    elif re.search(r"\benglish\b", lowered) and re.search(r"switch|change|make it|use", lowered):
        edits["language"] = "en"
        edits["direction"] = "ltr"

    if re.search(r"\brtl\b|\bright.to.left\b", lowered):
        edits["direction"] = "rtl"
    elif re.search(r"\bltr\b|\bleft.to.right\b", lowered):
        edits["direction"] = "ltr"

    if re.search(r"\banother template\b|\bdifferent template\b|\bchange the template\b|\bswitch template\b", lowered):
        edits["new_template"] = True

    if re.search(r"\bregenerate\b|\btry again\b|\bgenerate another\b|\bredo\b|\bregenerate the image\b", lowered):
        edits["regenerate"] = True

    size_match = re.search(r"\b(\d{2,5})\s*[x×]\s*(\d{2,5})\b", lowered)
    if size_match:
        edits["width"] = int(size_match.group(1))
        edits["height"] = int(size_match.group(2))

    if re.search(r"\bchange the layout\b|\bdifferent layout\b", lowered):
        edits["change_layout"] = True

    return edits or None


_SPEC_SYSTEM_PROMPT = (
    "You write structured content briefs for visual designs (posters, infographics, "
    "certificates, brochures, flyers, banners, social media visuals, presentation covers, "
    "training materials). Given the user's request, reply with ONLY a single JSON object "
    "(no markdown fencing, no commentary) with exactly these keys:\n"
    '{"title": "short headline, <=60 chars", '
    '"subtitle": "one supporting line, <=100 chars, or empty string", '
    '"bullets": ["up to 5 short supporting points, or empty list"], '
    '"palette": "one of: blue, red, amber, green, purple, teal", '
    '"language": "ISO 639-1 code of the language to write the content in, inferred from the request", '
    '"direction": "rtl if language is Arabic/Hebrew/Persian/Urdu, else ltr"}\n'
    "Write the title/subtitle/bullets themselves in the inferred language."
)

_FALLBACK_PALETTES = ("blue", "red", "amber", "green", "purple", "teal")


def _extract_json_object(text: str) -> Optional[dict]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.IGNORECASE)
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def _fallback_spec(message: str) -> dict[str, Any]:
    """Never raises — degrades to a trivial spec derived straight from the
    message text when the LLM call fails or returns unparseable JSON."""
    title = message.strip()[:60] or "Untitled Design"
    return {
        "title": title, "subtitle": "", "bullets": [],
        "palette": "blue", "language": "en", "direction": "ltr",
    }


async def generate_design_spec(
    provider: Any, message: str, design_type: str, prior_spec: Optional[dict] = None,
) -> dict[str, Any]:
    """One strict-JSON LLM call producing {title, subtitle, bullets, palette,
    language, direction}. Never raises — malformed/missing output degrades
    to a trivial spec derived from the message text."""
    user_prompt = f"Design type: {design_type}\nRequest: {message}"
    if prior_spec:
        user_prompt += f"\nExisting content to revise (keep consistent unless asked to change): {json.dumps(prior_spec)}"

    try:
        reply = await provider.chat([{"role": "user", "content": user_prompt}], system_prompt=_SPEC_SYSTEM_PROMPT)
    except Exception:
        log.exception("generate_design_spec: provider.chat failed, using fallback spec")
        return _fallback_spec(message)

    parsed = _extract_json_object(reply or "")
    if not parsed:
        log.warning("generate_design_spec: unparseable LLM output, using fallback spec")
        return _fallback_spec(message)

    palette = str(parsed.get("palette") or "blue").lower()
    if palette not in _FALLBACK_PALETTES:
        palette = "blue"
    bullets = parsed.get("bullets")
    bullets = [str(b) for b in bullets][:5] if isinstance(bullets, list) else []
    direction = str(parsed.get("direction") or "ltr").lower()
    if direction not in ("rtl", "ltr"):
        direction = "ltr"

    return {
        "title": str(parsed.get("title") or message.strip()[:60] or "Untitled Design")[:120],
        "subtitle": str(parsed.get("subtitle") or "")[:200],
        "bullets": bullets,
        "palette": palette,
        "language": str(parsed.get("language") or "en")[:10],
        "direction": direction,
    }
