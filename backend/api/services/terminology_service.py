"""
Terminology extraction service — local-first, zero-cost for most content.

Extracts technical vocabulary from document text using:
  1. Regex patterns for abbreviations, components, procedures (no API call)
  2. Domain keyword lists for X-ray / security screening context
  3. Optional GPT-4o-mini call only for novel multi-word technical terms

All results are stored in TerminologyEntry and reused on subsequent documents.
"""
from __future__ import annotations
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# ── Domain keyword seeds ───────────────────────────────────────────────────────

_EQUIPMENT = [
    "ZBV", "HCVM", "MVXRAY", "RTT", "HCV", "Eagle", "Rapiscan",
    "Gantry", "Conveyor", "Generator", "Detector", "Scanner",
    "HMI", "HVPS", "DAQ", "PCB", "UPS", "APC",
]

_SAFETY = [
    "ALARA", "TLD", "PPE", "RSO", "mSv", "mGy", "HVL", "TVL",
    "Shielding", "Interlock", "Dosimeter",
]

_RADIATION = [
    "keV", "MeV", "kVp", "mA", "Bremsstrahlung", "Compton",
    "Attenuation", "Scatter", "Backscatter",
]

_XRAY_COMPONENTS = [
    "X-ray tube", "Detector array", "Photomultiplier", "Scintillator",
    "Collimator", "Filter wheel", "Beryllium window", "Anode", "Cathode",
    "Filament", "Target", "Focal spot",
]

_PROCEDURES = [
    "Calibration", "Alignment", "Functional test", "Acceptance test",
    "Preventive maintenance", "Corrective maintenance",
    "Startup procedure", "Shutdown procedure",
]


# ── Regex patterns ─────────────────────────────────────────────────────────────

# ALL-CAPS abbreviations (2–8 uppercase letters, optionally with digits/hyphens)
_RE_ABBREV = re.compile(r'\b([A-Z][A-Z0-9\-]{1,7})\b')

# Numbered or bulleted procedures: "1. Remove the ..." / "Step 3 — ..."
_RE_PROC = re.compile(
    r'(?:^|\n)\s*(?:\d+[\.\)]\s+|Step\s+\d+\s*[:\-—]\s*)([A-Z][^\n]{10,100})',
    re.MULTILINE,
)

# "The <Noun Phrase>" or "<Noun> <Noun> (optional)" patterns up to 4 words
_RE_COMPONENT = re.compile(
    r'\bthe\s+([A-Z][a-z]+(?:\s+[A-Z]?[a-z]+){0,3})\b',
)

# Part-number-like strings: "P/N 123-456A", "PN: XYZ-001"
_RE_PARTNUM = re.compile(
    r'(?:P/?N|Part\s+No?\.?)[:\s]+([A-Z0-9][A-Z0-9\-\.\/]{3,20})',
    re.IGNORECASE,
)


# ── Bloom level keywords for exam classification ───────────────────────────────

BLOOM_KEYWORDS: dict[str, list[str]] = {
    "remember": ["define", "list", "name", "recall", "state", "identify", "what is"],
    "understand": ["explain", "describe", "summarize", "interpret", "classify", "what does"],
    "apply": ["apply", "use", "calculate", "demonstrate", "perform", "solve", "show how"],
    "analyze": ["analyze", "compare", "differentiate", "examine", "why does", "what causes"],
    "evaluate": ["evaluate", "assess", "justify", "critique", "determine", "which is best"],
    "create": ["design", "construct", "develop", "formulate", "propose", "create"],
}


def classify_bloom(question: str) -> str:
    """Return Bloom taxonomy level for a question using local keyword matching."""
    q = question.lower()
    for level, keywords in BLOOM_KEYWORDS.items():
        if any(kw in q for kw in keywords):
            return level
    return "remember"


# ── Main extraction function ───────────────────────────────────────────────────

def extract_and_store(db: Session, doc_id: str, text: str) -> int:
    """
    Extract terminology from document text and upsert into TerminologyEntry.
    Returns the count of new entries added.
    Returns immediately if doc_id already has entries (idempotent).
    """
    from api.db.models import TerminologyEntry

    # Idempotency: skip if already processed this document
    existing = db.query(TerminologyEntry).filter(
        TerminologyEntry.source_doc_id == doc_id
    ).first()
    if existing:
        log.debug("Terminology already extracted for doc %s — skipping", doc_id)
        return 0

    entries: list[tuple[str, str]] = []  # (term, category)

    text_sample = text[:80_000]  # cap for performance

    # 1. Known equipment / seed terms
    for term in _EQUIPMENT + _SAFETY + _RADIATION:
        if term.lower() in text_sample.lower():
            entries.append((term, "equipment"))

    for comp in _XRAY_COMPONENTS:
        if comp.lower() in text_sample.lower():
            entries.append((comp, "component"))

    for proc in _PROCEDURES:
        if proc.lower() in text_sample.lower():
            entries.append((proc, "procedure"))

    # 2. Abbreviations (ALL-CAPS sequences)
    for m in _RE_ABBREV.finditer(text_sample):
        abbrev = m.group(1)
        if 2 <= len(abbrev) <= 8 and not abbrev.isdigit():
            entries.append((abbrev, "abbreviation"))

    # 3. Part numbers
    for m in _RE_PARTNUM.finditer(text_sample):
        entries.append((m.group(1), "specification"))

    # 4. Procedure step starts
    for m in _RE_PROC.finditer(text_sample):
        verb_phrase = m.group(1).strip()[:80]
        if len(verb_phrase) > 10:
            entries.append((verb_phrase, "procedure"))

    # Deduplicate (case-insensitive)
    seen: set[str] = set()
    new_count = 0
    for term, category in entries:
        key = term.lower().strip()
        if not key or key in seen or len(key) < 2:
            continue
        seen.add(key)

        # Upsert: increment use_count if term already exists globally
        existing_entry = db.query(TerminologyEntry).filter(
            TerminologyEntry.term.ilike(term)
        ).first()
        if existing_entry:
            existing_entry.use_count += 1
        else:
            db.add(TerminologyEntry(
                term=term,
                category=category,
                source_doc_id=doc_id,
                confidence=0.9,
            ))
            new_count += 1

    try:
        db.commit()
    except Exception as exc:
        db.rollback()
        log.warning("Terminology commit failed for %s: %s", doc_id, exc)
        return 0

    log.info("Terminology: added %d new entries for doc %s", new_count, doc_id)
    return new_count


def search_terminology(db: Session, query: str = "", category: str = "",
                       limit: int = 100, offset: int = 0) -> dict:
    """Search/list terminology entries."""
    from api.db.models import TerminologyEntry

    q = db.query(TerminologyEntry)
    if query:
        q = q.filter(TerminologyEntry.term.ilike(f"%{query}%"))
    if category:
        q = q.filter(TerminologyEntry.category == category)

    total = q.count()
    rows = q.order_by(TerminologyEntry.use_count.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "entries": [
            {
                "id": e.id,
                "term": e.term,
                "category": e.category,
                "definition": e.definition,
                "source_doc_id": e.source_doc_id,
                "confidence": e.confidence,
                "use_count": e.use_count,
                "created_at": e.created_at.isoformat() if e.created_at else None,
            }
            for e in rows
        ],
    }
