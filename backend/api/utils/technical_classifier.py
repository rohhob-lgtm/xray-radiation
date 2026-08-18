"""
Technical content classifier for the translation pipeline.

Determines whether a segment requires OpenAI expert review (Stage 5).
Entirely local — no AI calls, no network, no external imports.
Scores segments based on keyword presence and structural patterns.

Conservative by design: any single match → classify as technical.
When uncertain, always review rather than skip.
"""
from __future__ import annotations

import re

# ── Domain keyword set ────────────────────────────────────────────────────────
# Six engineering domains from the review system prompt, plus Rapiscan vocab.

_TECHNICAL_KEYWORDS: frozenset[str] = frozenset({
    # X-ray & imaging
    "x-ray", "xray", "detector", "collimator", "attenuate", "attenuation",
    "penetration", "scintillator", "photodiode", "pixel", "voxel",
    "reconstruction", "tomography", "ct scan", "dual energy", "focal spot",
    "anode", "cathode", "filament",
    # Radiation physics
    "radiation", "dose", "dosimeter", "dosimetry", "alara", "becquerel",
    "curie", "radioactive", "radionuclide", "isotope", "shielding",
    "irradiation", "contamination",
    # Screening / security
    "rapiscan", "smuggling", "contraband", "threat detection", "screening",
    "baggage", "cargo scanner", "linac", "accelerator", "body scanner",
    "explosive", "illicit", "narcotics",
    # HV electronics
    "high voltage", "hv generator", "rectifier", "inverter", "pwm",
    # Mechanical
    "conveyor", "gantry", "aperture", "interlock", "solenoid", "pneumatic",
    "hydraulic", "encoder", "resolver", "actuator", "torque",
    # Maintenance / field service
    "maintenance", "calibration", "preventive maintenance", "corrective",
    "overhaul", "troubleshoot", "diagnostic", "field service",
    # Safety
    "lockout", "tagout", "loto", "hazard", "danger", "emergency shutdown",
    "watchdog", "failsafe", "radiation safety", "electrical safety",
    # PCB / electronics
    "pcb", "firmware", "fpga", "microcontroller", "fuse", "relay",
    # Technical manuals / procedures
    "procedure", "specification", "tolerance", "operating procedure",
    "technical manual", "service manual",
    # Standards
    "IEC", "IEEE", "ASTM", "ANSI", "IAEA", "NCRP",
})

# Single compiled regex — longest keywords first to avoid substring collisions.
_KW_RE = re.compile(
    r"\b(?:" + "|".join(
        re.escape(k) for k in sorted(_TECHNICAL_KEYWORDS, key=len, reverse=True)
    ) + r")\b",
    re.IGNORECASE,
)

# Fault codes and model/part identifiers that signal engineering content
# even without explicit keywords.
_PATTERN_RE = re.compile(
    r"\b(?:ERR|FAULT|ALARM|F\d{2,6}|E\d{3,6})\b"   # fault / error codes
    r"|[A-Z]{2,5}-\d{3,}",                           # model / part code format
)


def is_technical_segment(text: str) -> bool:
    """Return True if this segment needs OpenAI expert review.

    Pure local check — no network, no AI. Conservative: any keyword or
    structural pattern match returns True.

    Args:
        text: source text of the segment (before translation).
    """
    if not text or len(text.strip()) < 4:
        return False
    return bool(_KW_RE.search(text)) or bool(_PATTERN_RE.search(text))


def classify_segments(
    segments: list[dict],
    source_key: str = "source",
) -> tuple[list[dict], list[dict]]:
    """Partition segments into (technical, general).

    Technical → expert review (Stage 5).
    General   → skip review; provider translation is sufficient.

    Both lists contain references to the same dicts (not copies).
    """
    technical: list[dict] = []
    general: list[dict] = []
    for seg in segments:
        (technical if is_technical_segment(seg.get(source_key, "")) else general).append(seg)
    return technical, general
