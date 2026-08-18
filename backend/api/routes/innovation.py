"""
Innovation Engine
Generates patent-ready invention disclosures and research proposals grounded in the
platform's knowledge base. Produces structured, multi-section outputs via SSE streaming.
"""
from __future__ import annotations
import asyncio
import json
import logging
import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.middleware.auth import optional_auth

log = logging.getLogger(__name__)
router = APIRouter(tags=["innovation"])

# ── Domain catalogue ─────────────────────────────────────────────────────────

DOMAINS = [
    {"id": "cargo_scanner",          "label": "Cargo Scanners",             "icon": "📦", "desc": "Large-object pallet & freight inspection systems"},
    {"id": "vehicle_scanner",        "label": "Vehicle Scanners",           "icon": "🚗", "desc": "Drive-through and portal vehicle X-ray systems"},
    {"id": "container_scanner",      "label": "Container Scanners",         "icon": "🏗️", "desc": "ISO shipping container & rail car inspection"},
    {"id": "baggage_scanner",        "label": "Baggage Scanners",           "icon": "🧳", "desc": "Airport cabin & hold baggage screening"},
    {"id": "ct_xray",                "label": "CT X-Ray Systems",           "icon": "🔬", "desc": "Computed tomography for security & industrial"},
    {"id": "backscatter",            "label": "Backscatter Systems",        "icon": "🌊", "desc": "Compton backscatter imaging technology"},
    {"id": "dual_energy",            "label": "Dual-Energy Systems",        "icon": "⚡", "desc": "Two-beam material discrimination imaging"},
    {"id": "multi_energy",           "label": "Multi-Energy Systems",       "icon": "🌈", "desc": "Spectral / multi-energy photon discrimination"},
    {"id": "photon_counting",        "label": "Photon-Counting Detectors",  "icon": "🔵", "desc": "Direct-conversion energy-resolving detectors"},
    {"id": "ai_reconstruction",      "label": "AI Image Reconstruction",    "icon": "🤖", "desc": "Deep learning for image quality & reconstruction"},
    {"id": "detector_electronics",   "label": "Detector Electronics",       "icon": "💻", "desc": "ASIC readout, signal chain, digitisation"},
    {"id": "dose_optimization",      "label": "Dose Optimization",          "icon": "🛡️", "desc": "ALARA dose reduction techniques & algorithms"},
    {"id": "auto_calibration",       "label": "Automatic Calibration",      "icon": "🎯", "desc": "Self-calibrating detector and system methods"},
    {"id": "image_enhancement",      "label": "Image Enhancement",          "icon": "🖼️", "desc": "Noise reduction, sharpening, contrast optimisation"},
    {"id": "threat_detection",       "label": "Threat Detection",           "icon": "🚨", "desc": "Explosive, weapon & contraband recognition"},
    {"id": "material_discrimination", "label": "Material Discrimination",   "icon": "🔍", "desc": "Atomic number & density-based material ID"},
    {"id": "scatter_correction",     "label": "Scatter Correction",         "icon": "🌀", "desc": "Anti-scatter grids, algorithms & measurements"},
    {"id": "detector_cooling",       "label": "Detector Cooling",           "icon": "❄️", "desc": "Thermal management for detector arrays"},
    {"id": "generator_technology",   "label": "Generator Technology",       "icon": "⚙️", "desc": "X-ray tube, anode & high-frequency generators"},
    {"id": "high_voltage",           "label": "High-Voltage Engineering",   "icon": "🔋", "desc": "HV power supplies, switching & conditioning"},
    {"id": "mechanical_design",      "label": "Mechanical Scanner Design",  "icon": "🔧", "desc": "Gantry, conveyor, shielding & motion systems"},
]

DOMAIN_MAP = {d["id"]: d for d in DOMAINS}

# ── System prompts ────────────────────────────────────────────────────────────

_PERSONA = """You are Innovation Engine.
Research by Mohamed Noaman.
International Instructor & Researcher.
X-Ray and Security Inspection Systems.

Your mission: invent novel, technically credible engineering concepts that could become scientific publications or patent applications.

SCIENTIFIC RIGOUR PROTOCOL:
You must clearly label every claim with one of:
  [ESTABLISHED] — proven physics / engineering supported by literature
  [HYPOTHESIS]  — plausible engineering idea requiring experimental validation
  [SPECULATIVE] — novel concept requiring significant research before validation

Never present speculative ideas as established facts. When citing principles, reference physical laws, detector physics, or established techniques by name.

KNOWLEDGE BASE CONTEXT (retrieved from uploaded documents):
{kb_context}

VERIFIED EXTERNAL RESEARCH CONTEXT (live internet retrieval):
{external_context}

INVENTION TOPIC: {topic}
TECHNOLOGY DOMAIN: {domain_label}
"""

_INLINE_CITATION_PROTOCOL = """
═══════════════════════════════════════════════════════
INLINE CITATION PROTOCOL — MANDATORY
═══════════════════════════════════════════════════════
• Every factual claim, prior-art reference, or KB-sourced statement MUST carry an
  inline citation: [1], [2], [3] … in order of first appearance.
• Cite KB documents using the filenames shown in the KNOWLEDGE BASE CONTEXT block.
  Example: "Multi-energy detectors achieve Z-discrimination [1]"
• Patents inline: "(US 10,123,456 B2)" then [N].
• Papers inline: "(Author et al., Year)" then [N].
• Standards inline: "(IEC 62220-1:2003)" then [N].

⚠ DO NOT write sections 13, 14, 15, 16, or 17.
  The system pipeline automatically appends after your output:
    §13 References  §14 Related Patents  §15 Standards
    §16 Knowledge Base Sources  §17 Commercialisation
  End your output at section 12. Writing these yourself causes duplicates.
═══════════════════════════════════════════════════════
"""

_REASONING_WORKFLOW = """
═══════════════════════════════════════════════════════
INNOVATION ENGINE REASONING WORKFLOW — MANDATORY
═══════════════════════════════════════════════════════
You are not allowed to behave as a generic text generator.
You must reason like a senior research scientist and R&D engineer.

Follow these stages in order before writing the final report:

Stage 1 — Problem Definition
- Define the engineering problem precisely.
- State scope, constraints, assumptions, and measurable success criteria.

Stage 2 — Evidence Collection
- Use only verified evidence from academic papers, patents, standards/regulators,
  manufacturer documentation, official organisations, and local knowledge-base documents.
- Reject weak, generic, irrelevant, or unverified sources.

Stage 3 — Critical Literature Review
- Compare papers against each other.
- Compare patents against each other.
- Identify contradictions, limitations, consensus, and unresolved problems.
- Do not merely summarize sources.

Stage 4 — Research Gap Detection
- Determine what technical problem remains unsolved after the verified review.
- If no genuine gap is supported by evidence, stop and state that no meaningful novelty was found.
- Do not invent a gap.

Stage 5 — Engineering Reasoning
- Evaluate physics, detector technology, electronics, AI feasibility, manufacturing,
  calibration, radiation safety, maintenance, deployment, cost, and validation.
- Reject concepts that violate known science or depend on unrealistic assumptions.

Stage 6 — Prior-Art Validation
- Compare every accepted proposal against verified patents, literature, and standards.
- Never claim novelty before this comparison.

Stage 7 — Scientific Self-Criticism
- Attempt to reject your own proposal before writing the report.
- State why it could fail, what evidence is missing, which assumptions are weak,
  and which experiment could disprove it.

Stage 8 — Report Generation
- Only after completing stages 1-7, generate the final report.
- The final report must reflect the prior reasoning, not bypass it.

Claim discipline:
- Every conclusion must be marked as one of:
  [FACT] factual statement directly supported by verified evidence
  [INFERENCE] engineering inference derived from verified evidence
  [PROPOSAL] new technical contribution being proposed
  [HYPOTHESIS] unverified claim requiring experimental validation
- Never use invented experiments, measurements, percentages, datasets, references,
  patents, standards, or impossible technologies.
- If evidence or prior-art verification is incomplete, treat the output as draft quality.
═══════════════════════════════════════════════════════
"""

_RESEARCH_NOTE = (
    "Prepared under the direction of Mohamed Noaman and subject to expert technical review "
    "and validation before publication or implementation."
)


def _format_reasoning_source(i: int, source) -> str:
    parts = [f"[{i}] {getattr(source, 'title', 'Untitled source')}"]
    meta = []
    stype = getattr(source, "source_type", "external")
    year = getattr(source, "year", "")
    publisher = getattr(source, "publisher", "")
    doi = getattr(source, "doi", "")
    patent_number = getattr(source, "patent_number", "")
    standard_number = getattr(source, "standard_number", "")
    verified_by = getattr(source, "verified_by", "")
    url = getattr(source, "url", "")
    relevance_score = getattr(source, "relevance_score", 0.0)
    if stype:
        meta.append(f"type={stype}")
    if year:
        meta.append(f"year={year}")
    if publisher:
        meta.append(f"publisher={publisher}")
    if doi:
        meta.append(f"doi={doi}")
    if patent_number:
        meta.append(f"patent={patent_number}")
    if standard_number:
        meta.append(f"standard={standard_number}")
    if verified_by:
        meta.append(f"verified={verified_by}")
    if url:
        meta.append(f"url={url}")
    meta.append(f"relevance={relevance_score:.1f}")
    parts.append("; ".join(meta))
    abstract = (getattr(source, "abstract", "") or "").strip()
    if abstract:
        parts.append(f"abstract: {abstract[:500]}")
    return "\n".join(parts)


def _build_reasoning_context(
    topic: str,
    domain_label: str,
    mode: str,
    kb_chunks: list,
    external_sources: list,
    external_warnings: list[str],
    external_search_targets: list[str],
) -> str:
    lines = [
        "VERIFIED EVIDENCE DOSSIER",
        f"Topic: {topic}",
        f"Domain: {domain_label}",
        f"Mode: {mode}",
        "",
        "External search targets executed:",
    ]
    for target in external_search_targets:
        lines.append(f"- {target}")
    if external_warnings:
        lines.append("")
        lines.append("Verification warnings:")
        for warning in external_warnings:
            lines.append(f"- {warning}")

    lines.append("")
    lines.append("Verified external sources:")
    if external_sources:
        for i, source in enumerate(external_sources, 1):
            lines.append(_format_reasoning_source(i, source))
            lines.append("")
    else:
        lines.append("- None")

    lines.append("Local knowledge-base evidence:")
    if kb_chunks:
        seen: set[str] = set()
        idx = 1
        for chunk in kb_chunks:
            fname = getattr(chunk, "filename", None) or "Unknown document"
            if fname in seen:
                continue
            seen.add(fname)
            snippet = " ".join((getattr(chunk, "content", "") or "")[:500].split())
            lines.append(f"[KB{idx}] {fname}")
            if snippet:
                lines.append(f"snippet: {snippet}")
            lines.append("")
            idx += 1
    else:
        lines.append("- None")

    return "\n".join(lines).strip()


def _build_stage_prompt(mode: str, topic: str, domain_label: str, evidence_dossier: str) -> str:
    report_target = "research paper"
    if mode == "patent":
        report_target = "invention report"
    elif mode == "full":
        report_target = "combined research and invention report"

    return f"""Use the verified evidence dossier below to complete stages 1-7 of the reasoning workflow before drafting the final {report_target}.

Return your analysis in the following exact headings:

## Stage 1. Problem Definition
## Stage 2. Evidence Collection Review
## Stage 3. Critical Literature and Prior-Art Review
## Stage 4. Research Gap Detection
## Stage 5. Engineering Reasoning
## Stage 6. Prior-Art Validation
## Stage 7. Scientific Self-Criticism

Rules:
- Quote only evidence present in the dossier.
- If evidence is insufficient for a meaningful new contribution, say so explicitly.
- Do not invent missing source details.
- Use [FACT], [INFERENCE], [PROPOSAL], and [HYPOTHESIS] labels throughout.
- In Stage 4, answer exactly whether a genuine unresolved technical problem remains.
- In Stage 6, include the sentence: "This concept appears technically distinct based on the currently verified prior-art search. Formal patentability must be determined through a professional patent examination." only if the evidence supports that cautious conclusion.
- In Stage 7, include at least one concrete falsification experiment.

Topic: {topic}
Domain: {domain_label}

{evidence_dossier}
"""


def _build_final_report_prompt(mode: str, reasoning_output: str) -> str:
    if mode == "research":
        structure = """Use this exact structure and numbering in order:
## 1. Title
## 2. Author Information
## 3. Abstract
## 4. Keywords
## 5. Introduction, Scope, and Constraints
## 6. Scientific and Technical Background
## 7. Critical Literature Review and Existing Technologies
## 8. Research Gap, Questions, and Proposed Contribution
## 9. Materials, Methods, and Experimental Design
## 10. Safety, Regulatory, Validation, and Expected Results Targets
## 11. Discussion and Limitations
## 12. Conclusion and Future Work

Additional rules:
- Section 2 must contain exactly this authorship block:
  Innovation Engine
  Research developed under the direction of:
  Mohamed Noaman
  Founder, X-Ray Academy
  International Instructor & Technical Trainer
  X-Ray and Security Inspection Systems
- Include this professional note once in Section 2 or the conclusion: """ + _RESEARCH_NOTE + """
- Do not claim that experiments have already been performed unless the evidence dossier explicitly proves that.
- Use the heading "Expected Results and Validation Targets", not a fabricated results section.
- Keep all conclusions aligned with the stage analysis below.
- If the stage analysis concludes that no genuine research gap exists, state that clearly and do not invent a new proposal.
- End at section 12 only. Do not append references, patents, standards, KB sources, or commercialisation.
"""
    else:
        structure = """Use this exact structure and numbering in order:
## 1. Title
## 2. Author Information
## 3. Technical Field
## 4. Background and Verified Prior Art
## 5. Unresolved Technical Problem
## 6. Proposed Invention
## 7. Novel Technical Contribution
## 8. System Architecture and Components
## 9. Operating Method and Data Flow
## 10. Prototype Design, Required Equipment, and Alternative Embodiments
## 11. Validation Plan, Safety Requirements, and Failure Modes
## 12. Industrial Applicability, Prior-Art Position, and Conclusion

Additional rules:
- Section 2 must contain exactly this authorship block:
  Innovation Engine
  Research developed under the direction of:
  Mohamed Noaman
  Founder, X-Ray Academy
  International Instructor & Technical Trainer
  X-Ray and Security Inspection Systems
- Include this professional note once in Section 2 or the conclusion: """ + _RESEARCH_NOTE + """
- Never state that the invention is patentable.
- If supported by the verified stage analysis, you may use only this cautious sentence in Section 16:
  "This concept appears technically distinct based on the currently verified prior-art search. Formal patentability must be determined through a professional patent examination."
- Do not invent measured performance data.
- If the stage analysis concludes that no genuine unresolved technical problem remains, state that clearly and do not force a new invention.
- End at section 12 only. Do not append references, patents, standards, KB sources, or commercialisation.
"""

    return f"""Using the validated stage analysis below, write the final report in natural professional language.

{structure}

Mandatory writing rules:
- Avoid repetitive AI wording, filler, promotional language, and unsupported certainty.
- Every substantive conclusion must be clearly supported by the stage analysis or marked as [HYPOTHESIS].
- Preserve honest uncertainty.
- Do not expose the internal stage workflow in the final report.

Stage analysis:

{reasoning_output}
"""


def _is_relevance_accepted(source) -> bool:
    """Keep only references that passed relevance filtering."""
    if getattr(source, "rejected", False):
        return False
    if getattr(source, "is_relevant", True) is False:
        return False
    score = getattr(source, "relevance_score", None)
    if isinstance(score, (int, float)):
        return score >= 6.0
    return True

_PATENT_DYNAMIC = """
=== PATENT MODE: COMPLETE INVENTION PACKAGE ===

Generate a professional patent filing document suitable for submission to
USPTO, WIPO, EPO, UKIPO, and GCC Patent Office.

No placeholder text. No empty sections. Professional formatting only.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 0 — PATENT COVER PAGE  (generate this first, before §1)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Output a section headed exactly:

## PATENT COVER PAGE

Then output this exact branding block, preserving line breaks:

Innovation Engine
Research by
Mohamed Noaman

International Instructor & Researcher
X-Ray and Security Inspection Systems

Containing the following fields, each on its own line:

**Patent Title:** [Precise patent-style title, ≤20 words]
**Date:** {today}
**Version:** 1.0 — Draft
**Technology Domain:** {domain_label}
**Confidentiality Level:** CONFIDENTIAL — For Internal Use Only
**Patent Status:** Draft — Pending Internal Review

**Executive Summary:**
[3–5 sentences: what the invention does, its core technical novelty,
and its primary commercial value. Written for a C-suite or patent attorney.]

**Technology Readiness Level (TRL):** TRL [1–4] — [one-sentence TRL description]
**Innovation Score:** [55–95] / 100 — [one-sentence justification]
**Commercial Potential:** [Medium / High / Very High] — [one-sentence justification]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
PART 1 — PATENT BODY SECTIONS §1–§12
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 1. ABSTRACT
Professional patent abstract, 150–250 words.
Cover: field of invention, technical problem solved, core technical solution, key advantages.
Write in formal patent language.

## 2. BACKGROUND
### Current Technology
State of the art in {domain_label} — specific named systems, architectures, performance figures.

### Existing Limitations
4–6 concrete technical, operational, and commercial limitations. [ESTABLISHED] every one.

### Market Gap
The unmet need — quantified where possible (market size, failure rate, cost of unsolved problem).

### Technical Challenges
Engineering challenges that make the problem difficult: physics constraints, manufacturing
limits, signal-to-noise barriers, regulatory requirements.

## 3. PRIOR ART REVIEW
### Related Technologies
Adjacent-field technologies with [N] citations.

### Existing Commercial Systems
Named systems (manufacturer, model where known) with technical specs and cited [N].

### Academic Work
Relevant published research — cite every paper as [N].

### Existing Patents
2–4 specific prior patents with patent numbers, cited as [N].

### Comparison Table
Markdown table: this invention vs. 3–4 prior art approaches across 6–8 performance dimensions.

### Novelty Analysis
Explicit statement of what makes this invention new over every listed prior art item.

## 4. PROBLEM STATEMENT
### Technical Problem
Precise engineering problem statement — measurable gap between required and achieved performance.

### Operational Problem
How the unsolved technical problem affects operators, throughput, safety, or decision quality.

### Commercial Problem
Market impact: cost of the problem, competitive disadvantage, regulatory exposure.

## 5. INVENTION SUMMARY
### Core Innovation
The single inventive step in 2–3 sentences — this is the heart of the patent.

### System Overview
High-level description of the complete invention — subsystems, interfaces, data flows.

### Advantages
7–9 specific, quantifiable advantages over prior art, each tagged [ESTABLISHED],
[HYPOTHESIS], or [SPECULATIVE], with estimated figures and physical justification.

### Expected Performance
Quantitative performance targets with units: resolution, throughput, dose, accuracy,
false-alarm rate, cost — compared to the best prior art on each dimension.

## 6. DETAILED DESCRIPTION
### Architecture
System-level block diagram description — modules, connections, data flows.

### Subsystems
Detailed description of each major subsystem with specifications.

### Hardware
Hardware components: sensors, detectors, electronics, mechanical assemblies —
with part types, key parameters, and integration approach.

### Software
Software modules: data acquisition, processing pipeline, control software, UI —
with APIs, data formats, and latency requirements.

### Algorithms
Core algorithms with mathematical formulations, key equations, and pseudo-code
for the most novel algorithmic steps.

### Workflow
Step-by-step operational workflow from power-on to output — numbered list.

### Control Logic
Control system design: feedback loops, state machines, safety interlocks,
emergency stop logic, automated calibration triggers.

### AI Components
If AI/ML is used: model architecture, training data requirements, inference pipeline,
model size, latency budget, update/retraining strategy, explainability.

### Safety
Radiation safety (dose limits, shielding), electrical safety (HV isolation,
interlock chains), mechanical safety (crush/pinch guards), fail-safe logic,
regulatory compliance pathway.

## 7. FIGURE DESCRIPTIONS
Describe the 6 engineering drawings that would accompany this patent filing.
Each description must be specific enough for a draughtsman to create the figure.

**Figure 1 — Overall System Architecture**
[Block diagram: all major modules, interconnections, power and data buses]

**Figure 2 — Signal Flow Diagram**
[Signal processing chain from detector to output: ADC, filtering, reconstruction, display]

**Figure 3 — AI / Algorithm Workflow**
[AI or algorithmic processing flowchart: input → pre-processing → inference → post-processing → output]

**Figure 4 — Mechanical Design**
[Cross-section or assembly drawing: key dimensions, materials, mounting, shielding]

**Figure 5 — Electronics / Detector Electronics**
[Circuit block diagram: detector bias, readout ASIC, digitiser, control FPGA, power supply]

**Figure 6 — Deployment Scenario**
[Installation diagram: the invention in its operational environment with operator interface]

## 8. CLAIMS
Draft patent claims in formal USPTO claim language.

### Independent Claims

**Claim 1 (Apparatus):**
An apparatus for {topic_short}, comprising: ...

**Claim 2 (Method):**
A method for {topic_short}, comprising: ...

**Claim 3 (System):**
A system for {topic_short}, comprising: ...

### Dependent Claims
**Claim 4:** The apparatus of claim 1, wherein ...
**Claim 5:** The apparatus of claim 1, further comprising ...
**Claim 6:** The method of claim 2, wherein ...
**Claim 7:** The method of claim 2, further comprising ...
**Claim 8:** The system of claim 3, wherein ...

### Method Claims
**Claim 9:** A computer-implemented method comprising ...
**Claim 10:** The method of claim 9, wherein ...

### Software Claims
**Claim 11:** A non-transitory computer-readable medium storing instructions that, when executed, cause a processor to ...

### AI Claims (if AI is a novel element)
**Claim 12:** A machine learning system for ..., comprising: a trained model configured to ...

## 9. NOVELTY ANALYSIS
Explain precisely why this invention is new and non-obvious.

### vs. Commercial Products
Named comparison with 3–4 commercial systems — specific technical differences that
prevent each from solving the problem this invention solves.

### vs. Published Papers
Comparison with 3–5 academic works [N] — what each paper does and does not teach.

### vs. Known Patents
Comparison with 3–5 prior patents [N] — explicit claim-by-claim novelty distinction.

## 10. INDUSTRIAL APPLICATIONS
Real deployment scenarios with expected ROI, deployment timeline, and market size:

- **Government / National Security:** ...
- **Military / Defence:** ...
- **Customs & Border Protection:** ...
- **Port & Maritime Security:** ...
- **Airport Security (Checked Baggage & Cabin Baggage):** ...
- **Land Border Security:** ...
- **Cargo & Freight Inspection:** ...
- **Vehicle Inspection (Drive-Through):** ...
- **Rail & Metro Security:** ...
- **Nuclear / Industrial NDT:** ...

## 11. RISK ANALYSIS

### Technical Risks
4–6 risks — each with: description, probability (Low/Med/High), impact (Low/Med/High), mitigation.

### Manufacturing Risks
2–3 risks — supply chain, fabrication tolerance, yield.

### Regulatory Risks
Approval pathway complexity in the USA (FDA/TSA), EU (CE/ECAC), GCC, and other key markets.

### Safety Risks
Radiation, electrical (HV), mechanical, and operational hazards — with specific mitigations
and reference to applicable standards.

### Cybersecurity Risks
Data exfiltration, adversarial attacks on AI, network intrusion, supply-chain firmware tampering —
with specific countermeasures.

## 12. FUTURE DEVELOPMENT

### Phase 1 — Proof of Concept (Months 1–12)
Milestones, deliverables, resources, budget estimate, TRL target.

### Phase 2 — Prototype Development (Months 13–24)
Milestones, deliverables, resources, budget estimate, TRL target.

### Phase 3 — Validation & Commercialisation (Months 25–36)
Milestones, deliverables, resources, budget estimate, TRL target.

### TRL Progression Roadmap
| Phase | Start TRL | End TRL | Key Gate |
|-------|-----------|---------|----------|
| Phase 1 | ... | ... | ... |
| Phase 2 | ... | ... | ... |
| Phase 3 | ... | ... | ... |

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
END OF YOUR OUTPUT — Stop at section 12.
The pipeline appends §13 References, §14 Related Patents,
§15 Standards, §16 Knowledge Base Sources, §17 Commercialisation.
DO NOT write these sections yourself.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

_RESEARCH_DYNAMIC = """
=== RESEARCH MODE: ACADEMIC RESEARCH PROPOSAL ===

Generate a COMPLETE research paper style document, not short notes.
Each section must contain substantial technical depth (multiple paragraphs, equations
or quantitative targets where relevant, and explicit engineering assumptions).

Begin the document with this exact branding block, preserving line breaks:

Innovation Engine
Research by
Mohamed Noaman

International Instructor & Researcher
X-Ray and Security Inspection Systems

Use this exact structure and numbering in order:
## 1. Abstract
## 2. Keywords
## 3. Introduction
## 4. Literature Review and Prior Art
## 5. Problem Statement
## 6. Methodology
## 7. Experimental Design and Validation Plan
## 8. Results and Discussion (Predicted / Hypothesized)
## 9. Limitations and Risk Analysis
## 10. Industrial and Operational Impact
## 11. Future Work and 3-Year Research Roadmap
## 12. Conclusion

Research quality requirements:
    • No one-line sections. Each section should be meaningfully developed.
    • Include cargo/security radiation-detector context when the topic requests it.
    • Literature review must prioritize detector, scanning, security-inspection relevance.
    • Avoid unrelated medical CT/cardiac content unless explicitly requested.
    • Use inline citations [N] for factual claims and comparisons.
    • Do not output sections 13+ (pipeline appends mandatory sections).
"""

# ── Request schema ────────────────────────────────────────────────────────────

class InnovationRequest(BaseModel):
    domain: str
    topic: str
    mode: str = "patent"          # patent | research | full
    context: Optional[str] = None
    kb_top_k: int = 8


# ── Route: list domains ───────────────────────────────────────────────────────

@router.get("/innovation/domains")
def list_domains():
    return DOMAINS


# ── Route: history ────────────────────────────────────────────────────────────

@router.get("/innovation/history")
def list_innovation_history(
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
    limit: int = 50,
):
    from api.db.models import InnovationOutput
    q = db.query(InnovationOutput).order_by(InnovationOutput.created_at.desc())
    if user:
        q = q.filter(InnovationOutput.user_id == user["id"])
    return [
        {
            "id":           o.id,
            "domain":       o.domain,
            "domain_label": o.domain_label,
            "mode":         o.mode,
            "topic":        o.topic,
            "word_count":   o.word_count,
            "kb_chunks":    o.kb_chunks_used,
            "created_at":   o.created_at.isoformat(),
            "preview":      o.content[:300],
        }
        for o in q.limit(limit).all()
    ]


@router.delete("/innovation/history/{innovation_id}", status_code=204)
def delete_innovation(
    innovation_id: str,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import InnovationOutput
    obj = db.query(InnovationOutput).filter(InnovationOutput.id == innovation_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Innovation not found")
    db.delete(obj)
    db.commit()


# ── Route: generate (SSE streaming) ─────────────────────────────────────────

@router.post("/innovation/generate")
async def generate_innovation(
    body: InnovationRequest,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    if body.domain not in DOMAIN_MAP:
        raise HTTPException(status_code=400, detail=f"Unknown domain '{body.domain}'")
    if body.mode not in ("patent", "research", "full"):
        raise HTTPException(status_code=400, detail="mode must be patent | research | full")

    domain_label = DOMAIN_MAP[body.domain]["label"]

    # ── Retrieve KB context ──────────────────────────────────────────────────
    from api.services.rag_service import retrieve_chunks
    kb_query = f"{domain_label} {body.topic}"
    chunks = await retrieve_chunks(kb_query, db, top_k=body.kb_top_k)
    if not chunks and body.domain == "cargo_scanner":
        # Retry with cargo-focused alternatives to avoid empty local KB context.
        kb_retry_queries = [
            f"cargo scanner radiation detector {body.topic}",
            f"container inspection x-ray detector security",
            f"customs cargo screening dual energy detector",
            f"cargo inspection detector electronics photon counting",
            f"x-ray cargo scanner material discrimination threat detection",
            f"border security container scanner high energy x ray",
        ]
        for q in kb_retry_queries:
            chunks = await retrieve_chunks(q, db, top_k=max(body.kb_top_k, 16))
            if chunks:
                break
    kb_context_parts = []
    for c in chunks:
        snippet = c.content[:400].strip()
        kb_context_parts.append(f"[Source: {c.filename}]\n{snippet}")
    kb_context = "\n\n---\n\n".join(kb_context_parts) if kb_context_parts else "No relevant documents found in the knowledge base."

    # ── Build static prompt parts ────────────────────────────────────────────
    from datetime import datetime as _dt, timezone as _tz
    today_str = _dt.now(_tz.utc).strftime("%d %B %Y")
    topic_short = " ".join(body.topic.split()[:6])

    if body.mode == "patent":
        generation_instructions = _PATENT_DYNAMIC.format(
            today=today_str,
            domain_label=domain_label,
            topic_short=topic_short,
        )
    elif body.mode == "research":
        generation_instructions = _RESEARCH_DYNAMIC
    else:  # full
        generation_instructions = _PATENT_DYNAMIC.format(
            today=today_str,
            domain_label=domain_label,
            topic_short=topic_short,
        ) + "\n\n" + _RESEARCH_DYNAMIC

    # ── Stream from AI ───────────────────────────────────────────────────────
    from openai import AsyncOpenAI
    from api.services.ai_providers.registry import provider_registry

    openai_api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    openai_client = AsyncOpenAI(api_key=openai_api_key) if openai_api_key else None
    active_provider = provider_registry.get_active()
    use_ollama_stream = (
        openai_client is None
        and active_provider is not None
        and getattr(active_provider, "provider_id", "") == "ollama"
    )

    if openai_client is None and not use_ollama_stream:
        raise HTTPException(
            status_code=500,
            detail=(
                "Innovation Engine requires OPENAI_API_KEY or an active Ollama provider "
                "for report generation."
            ),
        )

    output_id = str(uuid.uuid4())

    async def event_stream():
        full_content = ""
        try:
            yield f"data: {json.dumps({'type': 'start', 'output_id': output_id, 'kb_chunks': len(chunks)})}\n\n"

            def _emergency_draft(mode_value: str, topic_value: str, domain_value: str) -> str:
                if mode_value == "research":
                    return (
                        "## 1. Abstract\n"
                        f"This research investigates {topic_value} in {domain_value}, focusing on how AI can improve radiation-detector sensitivity, material discrimination, and operator decision support [HYPOTHESIS]. "
                        "The programme targets realistic cargo-screening constraints including throughput, shielding geometry, cluttered loads, and low-contrast contraband signatures [ESTABLISHED]. "
                        "A phased methodology is proposed to combine detector-physics-informed features with AI inference pipelines and validation against operational KPIs [HYPOTHESIS].\n\n"
                        "## 2. Keywords\n"
                        "X-ray security screening; cargo scanner; radiation detectors; dual-energy imaging; AI-assisted threat detection; throughput optimization.\n\n"
                        "## 3. Introduction\n"
                        "Cargo-screening systems operate under competing constraints: high conveyor throughput, limited acquisition time, variable object orientation, and strict false-alarm budgets [ESTABLISHED]. "
                        "Detector subsystems often encounter dynamic range limitations and spectrum-dependent attenuation ambiguities, which reduce confidence for dense or mixed materials [ESTABLISHED]. "
                        "AI is therefore positioned as a post-acquisition decision amplifier, not a replacement for detector physics, by learning feature interactions that are difficult to encode as static rules [HYPOTHESIS].\n\n"
                        "## 4. Literature Review and Prior Art\n"
                        "Prior art in cargo scanning demonstrates dual-energy and high-energy transmission approaches for material class separation, but many deployments remain threshold-heavy and operator-dependent [ESTABLISHED]. "
                        "Detector-centric studies emphasize calibration drift, spectral cross-talk, and pile-up effects as core bottlenecks that propagate into downstream classification error [ESTABLISHED]. "
                        "AI-focused publications report gains in anomaly ranking and clutter suppression; however, transferability to real cargo manifests is frequently under-validated [HYPOTHESIS].\n\n"
                        "## 5. Problem Statement\n"
                        "The central problem is to increase detection reliability for difficult cargo compositions without sacrificing line speed. "
                        "Specifically, the system must improve probability of detection for low-contrast threats while maintaining bounded false positives and explainable operator cues [HYPOTHESIS].\n\n"
                        "## 6. Methodology\n"
                        "The proposed method combines detector-domain corrections (gain normalization, energy-window compensation, scatter-aware pre-processing) with an AI inference stack using multi-branch feature fusion [HYPOTHESIS]. "
                        "Inputs include transmission intensity maps, dual-energy decomposition features, uncertainty estimates, and region proposals derived from detector confidence masks [ESTABLISHED]. "
                        "Model outputs include threat likelihood, material-class confidence, and explanation overlays for operator review [HYPOTHESIS].\n\n"
                        "## 7. Experimental Design and Validation Plan\n"
                        "Validation proceeds in three tiers: simulation, controlled test articles, and shadow-mode field operation. "
                        "Simulation includes perturbations for noise, source fluctuation, detector dead channels, and load-density distributions [ESTABLISHED]. "
                        "Bench testing uses standardized surrogate objects with known attenuation and hidden threat inserts. Field shadow mode compares AI recommendations against expert adjudication and baseline rule-based alarms [HYPOTHESIS].\n\n"
                        "## 8. Results and Discussion (Predicted / Hypothesized)\n"
                        "Predicted outcomes include improved detection sensitivity and reduced false alarms via physics-aware feature fusion [HYPOTHESIS]. "
                        "Expected gains are strongest in cluttered loads where conventional single-threshold logic saturates [HYPOTHESIS]. "
                        "Potential regressions include domain shift for unseen cargo categories and performance drift under seasonal calibration changes [SPECULATIVE].\n\n"
                        "## 9. Limitations and Risk Analysis\n"
                        "Key risks include data representativeness, annotation bias, detector aging effects, and adversarial concealment strategies [ESTABLISHED]. "
                        "Mitigation includes periodic recalibration, uncertainty-gated alerts, drift monitoring, and fail-safe fallback to deterministic rules when confidence drops below thresholds [HYPOTHESIS].\n\n"
                        "## 10. Industrial and Operational Impact\n"
                        "Operationally, improved detector-AI integration can reduce secondary inspections, shorten queue time, and stabilize decisions across operator experience levels [HYPOTHESIS]. "
                        "Industrial impact includes stronger compliance posture, lower reinspection cost, and improved scanner utilization under high-traffic border and port scenarios [HYPOTHESIS].\n\n"
                        "## 11. Future Work and 3-Year Research Roadmap\n"
                        "Year 1: build calibrated dataset pipeline, baseline models, and detector-aware pre-processing stack. "
                        "Year 2: integrate multi-energy feature learning, uncertainty calibration, and operator explanation layer. "
                        "Year 3: execute multi-site validation, formal safety case documentation, and commercialization readiness assessment [HYPOTHESIS].\n\n"
                        "## 12. Conclusion\n"
                        "AI can materially improve cargo-scanner radiation-detector effectiveness when tightly coupled with detector physics, calibration governance, and operational validation discipline [HYPOTHESIS]. "
                        "The proposed programme defines a practical path from feasibility to deployable, auditable screening performance improvements [ESTABLISHED]."
                    )
                return (
                    f"## 1. Title\n"
                    f"{topic_value} for {domain_value}\n\n"
                    "## 2. Technical Field\n"
                    "X-ray security imaging and computational threat analysis [ESTABLISHED].\n\n"
                    "## 3. Background\n"
                    "Conventional workflows trade off speed, sensitivity, and operator consistency [ESTABLISHED].\n\n"
                    "## 4. Problem to Solve\n"
                    "Reduce missed detections while maintaining inspection throughput [HYPOTHESIS].\n\n"
                    "## 5. Core Invention Concept\n"
                    "A compact dual-energy and AI fusion pipeline for robust anomaly prioritization [HYPOTHESIS].\n\n"
                    "## 6. System Architecture\n"
                    "Detector acquisition, feature extraction, model scoring, and operator decision support [ESTABLISHED].\n\n"
                    "## 7. Novelty and Advantages\n"
                    "Lower decision latency and improved consistency over baseline rule-only systems [HYPOTHESIS].\n\n"
                    "## 8. Embodiments\n"
                    "Standalone scanner module, edge-assisted deployment, and centralized model governance [SPECULATIVE].\n\n"
                    "## 9. Method Claims Draft\n"
                    "Acquire, decompose, score, rank, and present prioritized alerts with confidence bounds [HYPOTHESIS].\n\n"
                    "## 10. Apparatus Claims Draft\n"
                    "Integrated detector-processing interface with low-latency inference path [HYPOTHESIS].\n\n"
                    "## 11. Validation Plan\n"
                    "Controlled benchmark against false alarm and missed detection targets [ESTABLISHED].\n\n"
                    "## 12. Industrial Applicability\n"
                    "Applicable to airport, vehicle, and cargo inspection environments [ESTABLISHED]."
                )

            # Run external research first so the reasoning stages are based on verified evidence.
            from api.services.innovation_external_research import (
                ExternalResearchResult,
                perform_hybrid_external_research,
            )
            yield f"data: {json.dumps({'type': 'building_sections', 'message': 'Collecting verified evidence and prior art…'})}\n\n"
            try:
                ext_result = await asyncio.wait_for(
                    perform_hybrid_external_research([body.topic], domain_label),
                    timeout=45,
                )
            except Exception:
                ext_result = ExternalResearchResult(
                    sources=[],
                    searched_at_utc=_dt.now(_tz.utc).strftime("%Y-%m-%d"),
                    searched_sources=[
                        "Crossref",
                        "PubMed",
                        "IEEE Xplore",
                        "ScienceDirect",
                        "SpringerLink",
                        "arXiv",
                        "PatentsView/Google Patents/WIPO/Espacenet/USPTO",
                        "ISO/IEC/NIST/IAEA/TSA/ECAC authoritative pages",
                        "Manufacturer and university pages",
                    ],
                    warnings=[
                        "External research did not finish within runtime budget. Output must be treated as DRAFT — EXTERNAL VERIFICATION INCOMPLETE."
                    ],
                )

            yield f"data: {json.dumps({'type': 'external_research', 'external_sources': len(ext_result.sources), 'warnings': ext_result.warnings})}\n\n"

            evidence_dossier = _build_reasoning_context(
                body.topic,
                domain_label,
                body.mode,
                chunks,
                ext_result.sources,
                ext_result.warnings,
                ext_result.searched_sources,
            )

            external_context = evidence_dossier

            system_prompt = _PERSONA.format(
                kb_context=kb_context,
                external_context=external_context,
                topic=body.topic,
                domain_label=domain_label,
            ) + _INLINE_CITATION_PROTOCOL + "\n\n" + _REASONING_WORKFLOW

            if use_ollama_stream:
                # Compact local prompt to reduce first-token latency on Ollama models.
                compact_kb = kb_context[:2400]
                system_prompt = (
                    "You are Innovation Engine. Research by Mohamed Noaman. International Instructor & Researcher, X-Ray and Security Inspection Systems. "
                    "Behave like a senior research scientist and R&D engineer.\n\n"
                    "Rules: complete staged reasoning before drafting; use only verified evidence; "
                    "label claims as [FACT], [INFERENCE], [PROPOSAL], or [HYPOTHESIS]; avoid repetition.\n\n"
                    f"Domain: {domain_label}\n"
                    f"Topic: {body.topic}\n\n"
                    "Knowledge Base Context:\n"
                    f"{compact_kb}\n\n"
                    "Verified evidence dossier:\n"
                    f"{evidence_dossier[:5000]}"
                )

            _stream_usage = None

            if use_ollama_stream:
                # Keep local generation responsive on smaller Ollama models.
                stage_prompt = _build_stage_prompt(body.mode, body.topic, domain_label, evidence_dossier)
                final_prompt = _build_final_report_prompt(body.mode, "<reasoning will follow>")
                ollama_user_message = (
                    f"{stage_prompt}\n\n"
                    "After finishing the stage analysis, write the final report aligned with that analysis.\n\n"
                    f"{final_prompt}"
                )
                stream_messages = [{"role": "user", "content": ollama_user_message}]
                streamed_any_chunk = False
                try:
                    async for chunk_text in active_provider.stream_chat(stream_messages, system_prompt=system_prompt):
                        if chunk_text:
                            streamed_any_chunk = True
                            full_content += chunk_text
                            yield f"data: {json.dumps({'type': 'chunk', 'chunk': chunk_text})}\\n\\n"
                except Exception as stream_err:
                    # If local streaming fails before first token, retry once via non-stream path.
                    if not streamed_any_chunk:
                        yield f"data: {json.dumps({'type': 'building_sections', 'message': 'Local stream stalled; retrying with direct Ollama call…'})}\n\n"
                        try:
                            fallback_text = await asyncio.wait_for(
                                active_provider.chat(stream_messages, system_prompt=system_prompt),
                                timeout=30,
                            )
                            if fallback_text:
                                full_content += fallback_text
                                yield f"data: {json.dumps({'type': 'chunk', 'chunk': fallback_text})}\\n\\n"
                        except Exception:
                            raise RuntimeError(
                                "Innovation generation failed before final staged report output. "
                                "Legacy fallback draft is disabled to protect document quality."
                            )
                    else:
                        raise
            else:
                reasoning_user_message = _build_stage_prompt(body.mode, body.topic, domain_label, evidence_dossier)
                reasoning_resp = await openai_client.chat.completions.create(
                    model="gpt-5.4",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": reasoning_user_message},
                    ],
                    max_completion_tokens=8000,
                )
                reasoning_output = (reasoning_resp.choices[0].message.content or "").strip()
                try:
                    from api.utils.usage_recorder import record_usage_from_response
                    record_usage_from_response(
                        "Innovation Engine", reasoning_resp,
                        sub_feature="reasoning_workflow",
                        meta={"topic": body.topic, "domain": body.domain, "mode": body.mode},
                    )
                except Exception:
                    pass

                final_user_message = _build_final_report_prompt(body.mode, reasoning_output)
                stream = await openai_client.chat.completions.create(
                    model="gpt-5.4",
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user",   "content": final_user_message},
                    ],
                    max_completion_tokens=16000,
                    stream=True,
                    stream_options={"include_usage": True},
                )
                async for delta in stream:
                    if not delta.choices:
                        # Final usage-only chunk from stream_options
                        _stream_usage = delta.usage
                        continue
                    chunk_text = delta.choices[0].delta.content or ""
                    if chunk_text:
                        full_content += chunk_text
                        yield f"data: {json.dumps({'type': 'chunk', 'chunk': chunk_text})}\\n\\n"

            # Record main report cost
            try:
                from api.utils.usage_recorder import record_usage
                if _stream_usage:
                    record_usage(
                        "Innovation Engine", "gpt-5.4",
                        _stream_usage.prompt_tokens or 0,
                        _stream_usage.completion_tokens or 0,
                        cached_tokens=getattr(
                            getattr(_stream_usage, "prompt_tokens_details", None),
                            "cached_tokens", 0
                        ) or 0,
                        sub_feature="report_stream",
                        meta={"topic": body.topic, "domain": body.domain, "mode": body.mode,
                              "kb_chunks": len(chunks)},
                    )
            except Exception:
                pass

            # ── Mandatory sections pipeline ──────────────────────────────────
            # Sections 13-17 are ALWAYS built by the pipeline, never by the LLM.
            # This runs after streaming so the DB never stores an incomplete report.
            yield f"data: {json.dumps({'type': 'building_sections', 'message': 'Building References, Patents, Standards…'})}\n\n"

            from api.utils.mandatory_sections import build_mandatory_sections
            filtered_external_sources = [s for s in ext_result.sources if _is_relevance_accepted(s)]
            try:
                final_content, tail = await build_mandatory_sections(
                    body=full_content,
                    topic=body.topic,
                    domain_label=domain_label,
                    mode=body.mode,
                    kb_chunks=chunks,
                    external_sources=filtered_external_sources,
                    external_warnings=ext_result.warnings,
                    external_search_date=ext_result.searched_at_utc,
                    external_search_targets=ext_result.searched_sources,
                    output_id=output_id,
                    client=openai_client,
                )
            except Exception as ms_err:
                log.error("Mandatory sections pipeline failed: %s", ms_err)
                yield f"data: {json.dumps({'type': 'error', 'error': f'Failed to build mandatory report sections: {ms_err}'})}\n\n"
                return

            # Stream the appended tail so the frontend updates immediately
            yield f"data: {json.dumps({'type': 'sections_appended', 'tail': tail})}\n\n"

            # Persist to DB — always the fully assembled report
            from api.db.models import InnovationOutput
            wc = len(final_content.split())
            record = InnovationOutput(
                id=output_id,
                user_id=user["id"] if user else None,
                domain=body.domain,
                domain_label=domain_label,
                mode=body.mode,
                topic=body.topic,
                content=final_content,
                kb_chunks_used=len(chunks),
                word_count=wc,
            )
            db.add(record)
            db.commit()

            yield f"data: {json.dumps({'type': 'done', 'output_id': output_id, 'word_count': wc, 'kb_chunks': len(chunks)})}\n\n"

        except Exception as exc:
            log.exception("Innovation generation error: %s", exc)
            msg = (str(exc) or "").strip()
            if not msg:
                msg = exc.__class__.__name__
            if msg == "ReadTimeout":
                msg = (
                    "Local Ollama generation timed out before first token. "
                    "Please retry, use a shorter topic, or confirm the Ollama model is warmed up."
                )
            yield f"data: {json.dumps({'type': 'error', 'error': msg})}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Route: export HTML report ─────────────────────────────────────────────────

@router.get("/innovation/export/{innovation_id}")
def export_innovation_report(
    innovation_id: str,
    db: Session = Depends(get_db),
):
    from fastapi.responses import HTMLResponse
    from api.routes.export import _html_page, _md_to_html, _now_str, REPORT_CSS
    from api.db.models import InnovationOutput

    obj = db.query(InnovationOutput).filter(InnovationOutput.id == innovation_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Innovation not found")

    from api.utils.docgen import _strip_offer_footer
    mode_label = {"patent": "Patent Mode", "research": "Research Mode", "full": "Full Innovation Disclosure"}.get(obj.mode, obj.mode)
    content_html = _md_to_html(_strip_offer_footer(obj.content or ""))

    body = f"""
    <div class="header">
      <div>
                <div class="logo">X-Ray Academy · Innovation Engine</div>
        <div class="title">{obj.topic}</div>
        <div class="subtitle">{obj.domain_label} · {mode_label}</div>
      </div>
      <div class="meta">
        <strong>{_now_str()}</strong>
        <span class="badge badge-primary">{mode_label}</span><br>
        KB Chunks: {obj.kb_chunks_used} · Words: {obj.word_count:,}<br>
        ID: {obj.id[:8].upper()}
      </div>
    </div>
    <div>{content_html}</div>
    """
    from fastapi.responses import HTMLResponse as HR
    return HR(_html_page(obj.topic, body))


# ── Schemas for new endpoints ─────────────────────────────────────────────────

class TranslateRequest(BaseModel):
    target: str = "ar"             # ar | bilingual
    bilingual_layout: str = "sequential"   # sequential | sidebyside

class SaveRequest(BaseModel):
    content: str

class SaveVersionRequest(BaseModel):
    content: str
    language: str = "en"
    note: Optional[str] = None

class ExportRequest(BaseModel):
    lang: str = "en"             # en | ar | bilingual
    layout: str = "sequential"  # sequential | sidebyside
    ar_content: Optional[str] = None   # pre-translated Arabic markdown


# ── Route: translate ──────────────────────────────────────────────────────────

@router.post("/innovation/{innovation_id}/translate")
async def translate_innovation(
    innovation_id: str,
    body: TranslateRequest,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import InnovationOutput
    from openai import AsyncOpenAI

    obj = db.query(InnovationOutput).filter(InnovationOutput.id == innovation_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Innovation not found")

    client = AsyncOpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

    if body.target == "ar":
        system_prompt = """You are a professional scientific and patent translator specialising in X-ray technology,
physics, and engineering. Translate the following technical invention document from English to professional Arabic.

TRANSLATION RULES:
- Use professional scientific, engineering, and patent Arabic terminology (not colloquial Arabic).
- Preserve section headings with their numbers exactly (## 1. TITLE → ## ١. العنوان or ## 1. العنوان).
- Keep technical English terms in parentheses after the Arabic term when helpful.
  Example: الكاشف الضوئي العادّ (Photon-Counting Detector)
- Preserve all markdown formatting: ##, ###, **, *, -, numbered lists, tables.
- Preserve [ESTABLISHED], [HYPOTHESIS], [SPECULATIVE] labels — translate them:
  [ESTABLISHED] → [محقق], [HYPOTHESIS] → [فرضية], [SPECULATIVE] → [تخميني]
- Mathematical formulas and abbreviations (MTF, lp/mm, kVp, mAs) stay in English.
- The translation must sound natural to a native Arabic-speaking engineer or patent attorney.
- Do NOT add any commentary or explanations — output only the translated document."""

        user_msg = f"Translate this invention document to Arabic:\n\n{obj.content}"

    else:  # bilingual — return Arabic version only; frontend combines
        system_prompt = """You are a professional scientific and patent translator. Translate the English invention
document below into professional Arabic, following all formatting and terminology rules for scientific patent documents.
Output only the Arabic translation in markdown format."""
        user_msg = f"Translate this invention document to Arabic:\n\n{obj.content}"

    response = await client.chat.completions.create(
        model="gpt-5.4",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_msg},
        ],
        max_completion_tokens=10000,
    )
    try:
        from api.utils.usage_recorder import record_usage_from_response
        record_usage_from_response(
            "Innovation Engine", response,
            sub_feature="report_translation",
            meta={"target_language": body.target},
        )
    except Exception:
        pass
    translated = response.choices[0].message.content or ""

    return {"content": translated, "language": body.target}


# ── Route: save (overwrite current content) ───────────────────────────────────

@router.post("/innovation/{innovation_id}/save")
def save_innovation_content(
    innovation_id: str,
    body: SaveRequest,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import InnovationOutput
    obj = db.query(InnovationOutput).filter(InnovationOutput.id == innovation_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Innovation not found")
    obj.content = body.content
    obj.word_count = len(body.content.split())
    db.commit()
    return {"ok": True, "word_count": obj.word_count}


# ── Route: save version ───────────────────────────────────────────────────────

@router.post("/innovation/{innovation_id}/save-version")
def save_innovation_version(
    innovation_id: str,
    body: SaveVersionRequest,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import InnovationOutput, InnovationVersion
    obj = db.query(InnovationOutput).filter(InnovationOutput.id == innovation_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Innovation not found")

    # next version number
    last = (
        db.query(InnovationVersion)
        .filter(InnovationVersion.innovation_id == innovation_id)
        .order_by(InnovationVersion.version_num.desc())
        .first()
    )
    next_num = (last.version_num + 1) if last else 1

    ver = InnovationVersion(
        innovation_id=innovation_id,
        version_num=next_num,
        content=body.content,
        language=body.language,
        note=body.note,
    )
    db.add(ver)
    db.commit()
    return {"ok": True, "version_num": next_num, "version_id": ver.id}


# ── Route: list versions ──────────────────────────────────────────────────────

@router.get("/innovation/{innovation_id}/versions")
def list_innovation_versions(
    innovation_id: str,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    from api.db.models import InnovationVersion
    versions = (
        db.query(InnovationVersion)
        .filter(InnovationVersion.innovation_id == innovation_id)
        .order_by(InnovationVersion.version_num.desc())
        .all()
    )
    return [
        {
            "id": v.id,
            "version_num": v.version_num,
            "language": v.language,
            "note": v.note,
            "word_count": len(v.content.split()),
            "created_at": v.created_at.isoformat(),
            "preview": v.content[:200],
        }
        for v in versions
    ]


# ── Route: export DOCX ────────────────────────────────────────────────────────

@router.post("/innovation/{innovation_id}/export/docx")
def export_docx(
    innovation_id: str,
    body: ExportRequest,
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response
    from api.db.models import InnovationOutput
    from api.utils.docgen import build_docx
    import urllib.parse

    obj = db.query(InnovationOutput).filter(InnovationOutput.id == innovation_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Innovation not found")

    doc_id = obj.id[:8].upper()
    slug = obj.topic[:40].replace(' ', '_').replace('/', '-')
    lang_suffix = {"en": "EN", "ar": "AR", "bilingual": "Bilingual"}.get(body.lang, "EN")
    prefix = "Research" if obj.mode == "research" else "Invention"
    filename = f"{prefix}_{slug}_{doc_id}_{lang_suffix}.docx"

    docx_bytes = build_docx(
        record=obj,
        content=obj.content,
        lang=body.lang,
        layout=body.layout,
        ar_content=body.ar_content or None,
    )

    encoded_name = urllib.parse.quote(filename)
    return Response(
        content=docx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "Content-Length": str(len(docx_bytes)),
        },
    )


# ── Route: export PDF ─────────────────────────────────────────────────────────

@router.post("/innovation/{innovation_id}/export/pdf")
def export_pdf(
    innovation_id: str,
    body: ExportRequest,
    db: Session = Depends(get_db),
):
    from fastapi.responses import Response
    from api.db.models import InnovationOutput
    from api.utils.docgen import build_pdf
    import urllib.parse

    obj = db.query(InnovationOutput).filter(InnovationOutput.id == innovation_id).first()
    if not obj:
        raise HTTPException(status_code=404, detail="Innovation not found")

    doc_id = obj.id[:8].upper()
    slug = obj.topic[:40].replace(' ', '_').replace('/', '-')
    lang_suffix = {"en": "EN", "ar": "AR", "bilingual": "Bilingual"}.get(body.lang, "EN")
    prefix = "Research" if obj.mode == "research" else "Invention"
    filename = f"{prefix}_{slug}_{doc_id}_{lang_suffix}.pdf"

    pdf_bytes = build_pdf(
        record=obj,
        content=obj.content,
        lang=body.lang,
        layout=body.layout,
        ar_content=body.ar_content or None,
    )

    encoded_name = urllib.parse.quote(filename)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
            "Content-Length": str(len(pdf_bytes)),
        },
    )
