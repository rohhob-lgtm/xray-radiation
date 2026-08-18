"""
Do-Not-Translate (DNT) Filter for the Translation Studio.

Protects technical tokens from being altered by translation providers:
  - URLs and email addresses
  - Dates (ISO, abbreviated, ordinal)
  - Version / revision numbers (v1.2, Rev. 3)
  - Company / brand names (Rapiscan, Smiths Detection, …)
  - Part numbers / model numbers / serial numbers
  - Connector IDs (J12, P4, CN-3)
  - PCB IDs (PCB-001, PCB2)
  - Voltage / current / power values (120V, 5mA, 100W)
  - Measurements (500mm, 2.4GHz, 50kHz)
  - Error codes (E001, ERR-42, Fault:F05)
  - Calibration values (CAL-123, Cal.offset)

Workflow:
  1. protect(text) → (protected_text, token_map)
     Replaces each matched token with a UUID placeholder.
  2. Provider translates protected_text.
  3. restore(translated_text, token_map) → final_text
     Puts the original tokens back.

Placeholders survive translation because they look like opaque XML tags
to most providers, e.g. ⟪DNT_0⟫.
"""
from __future__ import annotations

import re
import uuid

# ── Pattern library ────────────────────────────────────────────────────────────

# Each pattern is a tuple: (name, compiled_regex)
# Order matters — more specific patterns must come before general ones.
_PATTERNS = [
    # URLs: http(s) and bare www — match before any alphanumeric patterns
    ("url", re.compile(
        r"https?://[^\s\"'<>\]\[)(\u27ea\u27eb]+"
        r"|www\.[a-zA-Z0-9][-a-zA-Z0-9.]+\.[a-zA-Z]{2,}(?:/[^\s]*)?",
        re.IGNORECASE,
    )),
    # Email addresses
    ("email", re.compile(
        r"\b[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}\b",
    )),
    # Dates: ISO (2024-08-09), slash-separated (08/09/24), abbreviated month
    # (24AUG09, 9 Aug 2024, Aug 2024), and ordinal-style dates
    ("date", re.compile(
        r"\b\d{4}[-/]\d{2}[-/]\d{2}\b"                              # 2024-08-09
        r"|\b\d{1,2}[-/]\d{1,2}[-/]\d{2,4}\b"                      # 08/09/2024
        r"|\b\d{1,2}\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s*\d{2,4}\b"
        r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s*\d{1,2}[,\s]+\d{4}\b"
        r"|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{4}\b"
        r"|\b\d{1,2}(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\d{2,4}\b",
        re.IGNORECASE,
    )),
    # Version / revision numbers: v1.0, v2.1.3, Version 1.2, Rev. 3, R3
    ("version", re.compile(
        r"\b[Vv](?:er(?:sion)?\.?\s*)?\d+(?:[._]\d+){0,3}\b"
        r"|\bRev(?:ision)?\.?\s*\d+(?:[._]\d+)?\b",
        re.IGNORECASE,
    )),
    # Company / brand names — exact list; never translate these
    ("company_name", re.compile(
        r"\b(?:Rapiscan|Smiths\s+Detection|L3(?:\s*Harris)?|OSI\s+Systems|"
        r"Analogic|Nuctech|Leidos|Astrophysics|ADANI|Autoclear|"
        r"InVision|Morpho|Sagem|Safran|Heimann|Scantech|CEIA|Garrett)\b",
        re.IGNORECASE,
    )),
    # Error codes: E001, ERR-42, Fault:F05, Error_Code_007
    ("error_code", re.compile(
        r"\b(?:ERR|ERROR|FAULT|FAIL|ALARM|CODE|E)[-_:]?\d{2,6}\b",
        re.IGNORECASE,
    )),
    # Calibration values: CAL-001, Cal.offset, CALIB_3
    # Separator is mandatory (not optional) so plain English words that start
    # with "cal" — calendar, calculate, calibration, california, calling —
    # aren't swallowed whole as false-positive DNT tokens.
    ("calibration", re.compile(
        r"\b(?:CAL|CALIB|CALIBR)[-_.]\w{1,10}\b",
        re.IGNORECASE,
    )),
    # PCB IDs: PCB-001, PCB3, PCB_A1
    ("pcb_id", re.compile(
        r"\bPCB[-_]?[A-Z0-9]{1,6}\b",
        re.IGNORECASE,
    )),
    # Connector IDs: J12, P4, CN-3, CON-12, SW1, TP5
    ("connector_id", re.compile(
        r"\b(?:J|P|CN|CON|SW|TP|TB|XP|XS|X)[-_]?\d{1,4}\b",
        re.IGNORECASE,
    )),
    # Measurements with units (must match number+unit as a unit)
    ("measurement", re.compile(
        r"\b\d+(?:[.,]\d+)?\s*"
        r"(?:mm|cm|m|km|in|ft|"
        r"kV|mV|V|mA|μA|A|W|kW|MW|"
        r"MHz|GHz|kHz|Hz|"
        r"ms|μs|ns|s|"
        r"kg|g|mg|lb|"
        r"°C|°F|K|"
        r"bar|psi|Pa|kPa|MPa|"
        r"rpm|dB|dBm|"
        r"mSv|μSv|mGy|Gy|Bq|Ci|R|mR|"
        r"mAs|kVp|lp/mm)\b",
        re.IGNORECASE,
    )),
    # Part / model / serial numbers: must have letters + digits mixed
    # e.g. ABC-1234, XR-6000, SN:123456, P/N:ABC123
    # The lookahead requires a digit somewhere in the suffix so plain English
    # words that happen to start with a prefix keyword — modules, modern,
    # partner, reference, parties, referee — aren't falsely protected as
    # part numbers (they were previously swallowed whole by the bare
    # [A-Z0-9][-A-Z0-9_/]{2,15} alphanumeric run).
    ("part_number", re.compile(
        r"\b(?:P/N|PN|S/N|SN|MODEL|MOD|PART|REF|ITEM)[:.\s]?(?=[A-Z0-9_/-]*\d)[A-Z0-9][-A-Z0-9_/]{2,15}\b"
        r"|"
        r"\b[A-Z]{1,4}[-_]?\d{3,8}(?:[-_][A-Z0-9]{1,6})?\b",
        re.IGNORECASE,
    )),
]


def protect(text: str) -> tuple[str, dict[str, str]]:
    """
    Replace DNT tokens in text with opaque placeholders.

    Returns:
        (protected_text, token_map)
        where token_map maps placeholder → original_token.
    """
    token_map: dict[str, str] = {}
    protected = text

    for _name, pattern in _PATTERNS:
        def _replace(m: re.Match) -> str:
            token = m.group(0)
            ph = f"\u27ea DNT_{len(token_map)} \u27eb"  # ⟪ DNT_N ⟫
            token_map[ph] = token
            return ph

        protected = pattern.sub(_replace, protected)

    return protected, token_map


def restore(translated: str, token_map: dict[str, str]) -> tuple[str, list[str]]:
    """
    Restore original tokens from placeholders.

    Returns:
        (restored_text, garbled_list)
        where garbled_list contains tokens whose placeholders survived but
        are surrounded by unexpected characters (possible mis-translation).
    """
    garbled: list[str] = []
    result = translated

    for ph, original in token_map.items():
        if ph in result:
            result = result.replace(ph, original)
        else:
            # Placeholder is gone — either translated or dropped.
            # Try fuzzy recovery: look for the original token already present.
            if original not in result:
                garbled.append(original)
                # Insert original at the end as a fallback
                result = result + f" [{original}]"

    return result, garbled


def extract_tokens(text: str) -> list[str]:
    """Return all DNT tokens found in text (for the Quality Report audit)."""
    found: list[str] = []
    for _name, pattern in _PATTERNS:
        found.extend(m.group(0) for m in pattern.finditer(text))
    return list(dict.fromkeys(found))  # deduplicate, preserve order
