"""Education Studio — generate courses, quizzes, lesson plans, certificates."""
from __future__ import annotations
import json
from typing import Optional, AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from api.db import get_db
from api.middleware.auth import optional_auth
from api.services.ai_providers.registry import provider_registry
from api.services.rag_service import retrieve_chunks

router = APIRouter(tags=["education"])


class EducationRequest(BaseModel):
    content_type: str          # course_outline | quiz | lesson_plan | exam | certificate | instructor_notes | student_notes
    topic: str                 # e.g. "ZBV cargo scanner operation"
    level: str = "intermediate"  # beginner | intermediate | advanced | expert
    num_items: int = 5         # questions for quiz, modules for course, etc.
    audience: str = "operator" # operator | engineer | researcher | student | instructor


CONTENT_PROMPTS = {
    "course_outline": """
Create a comprehensive course outline for: {topic}

**Audience:** {audience} | **Level:** {level}
**Modules:** {num_items}

Structure:
# Course: {topic}

## Course Overview
- Duration, prerequisites, learning outcomes

## Module 1–{num_items}: [Title]
For each module:
- Learning objectives (3–5 bullet points)
- Key topics covered
- Practical exercises
- Assessment criteria

## Resources & References
- Reference standards, manuals, further reading

Use professional training format with clear hierarchy. Include X-ray physics, safety standards, and operational best practices where relevant.
""",
    "quiz": """
Create a professional {num_items}-question multiple-choice quiz on: {topic}

**Level:** {level} | **Audience:** {audience}

Format each question as:
**Q[N].** [Question text]

A) [Option]
B) [Option]
C) [Option]
D) [Option]

**Answer:** [Letter] — [Brief explanation of why this is correct and why others are wrong]

---

Cover key concepts: physics principles, operational procedures, safety protocols, threat detection techniques, and equipment specifications relevant to {topic}.
""",
    "lesson_plan": """
Write a detailed lesson plan for teaching: {topic}

**Duration:** {num_items} hours | **Level:** {level} | **Audience:** {audience}

Include:
# Lesson Plan: {topic}

## 1. Learning Objectives
Clear, measurable outcomes using action verbs.

## 2. Prerequisites
What students must know before this lesson.

## 3. Materials & Equipment
Equipment, handouts, software, reference documents.

## 4. Session Breakdown
For each hour block:
- Topic segment with time allocation
- Teaching method (lecture, demo, hands-on)
- Key talking points
- Interactive element

## 5. Practical Exercises
Step-by-step practical activities with expected outcomes.

## 6. Assessment
How to evaluate student understanding (quiz, practical test, discussion).

## 7. Instructor Notes
Common misconceptions, difficult concepts, tips for engagement.
""",
    "exam": """
Create a formal {num_items}-question examination on: {topic}

**Level:** {level} | **Audience:** {audience}
**Format:** Mix of multiple choice (60%), short answer (25%), practical scenario (15%)

Include:
# Official Examination: {topic}

**Instructions:** Time allowed — X minutes. All questions are compulsory.

## Section A: Multiple Choice (60 marks)
[Multiple choice questions with 4 options each]

## Section B: Short Answer (25 marks)
[Questions requiring 2–5 sentence responses]

## Section C: Scenario Analysis (15 marks)
[1–2 real-world operational scenarios requiring analysis]

## Answer Key (Instructor Copy)
[Complete answers and marking scheme]
""",
    "certificate": """
Draft a professional training certificate template for: {topic}

**Level:** {level} | **Audience:** {audience}

Format:
# CERTIFICATE OF COMPETENCY

**This certifies that:** [PARTICIPANT NAME]

**Has successfully completed:** {topic}

**Training Level:** {level}
**Duration:** [Hours]
**Date of Completion:** [DATE]

**Competencies Achieved:**
[List of {num_items} specific competencies demonstrated]

**Assessment Method:** [Written exam + practical assessment]

**Valid Until:** [DATE + 2 years]

**Issuing Authority:** X-Ray Research Innovation Platform
**Certificate Number:** [AUTO-GENERATED]

---
Also include guidelines for issuing this certificate: required pass mark, re-assessment policy, recognition bodies.
""",
    "instructor_notes": """
Prepare detailed instructor notes for teaching: {topic}

**Level:** {level} | **Number of sessions:** {num_items}

Include:
# Instructor Notes: {topic}

## Pedagogical Approach
Best methods for teaching this technical content.

## Session-by-Session Notes
For each of {num_items} sessions:
- Key concepts to emphasize
- Common student questions and ideal answers
- Misconceptions to address proactively
- Demonstrations and analogies that work well
- Time management tips

## Difficult Concepts
The hardest ideas and proven ways to explain them.

## Practical Assessment Rubric
Detailed marking criteria for each competency.

## Frequently Asked Questions
Top 10 FAQs with expert answers.

## Additional Resources
Books, standards, online resources, manufacturers' materials.
""",
    "student_notes": """
Create structured student notes for: {topic}

**Level:** {level} | **Sections:** {num_items}

Format as comprehensive study notes:
# Study Notes: {topic}

## Key Concepts
Explained clearly with diagrams described in text.

## Important Formulas & Equations
With worked examples.

## Critical Safety Points
Highlighted safety-critical information.

## Summary Tables
Comparison tables for different systems, materials, techniques.

## Practice Questions
{num_items} self-assessment questions with answers.

## Glossary
Key technical terms defined.

## Quick Reference Card
One-page summary of the most important points.
""",
}


@router.post("/education/generate")
async def generate_education_content(
    body: EducationRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[dict] = Depends(optional_auth),
):
    """Generate educational content using RAG knowledge + GPT-5.4. Returns SSE stream."""
    provider = provider_registry.get_active()
    if not provider:
        raise HTTPException(status_code=503, detail="No AI provider available")

    template = CONTENT_PROMPTS.get(body.content_type, CONTENT_PROMPTS["lesson_plan"])
    user_prompt = template.format(
        topic=body.topic,
        level=body.level,
        num_items=body.num_items,
        audience=body.audience,
    )

    # Retrieve relevant knowledge from the RAG system
    chunks = await retrieve_chunks(body.topic, db, top_k=4)
    rag_context = ""
    if chunks:
        rag_context = "\n\n## Reference Knowledge from Uploaded Documents\n"
        for chunk in chunks[:3]:
            rag_context += f"\n**From {chunk.filename} p.{chunk.page_num}:**\n"
            rag_context += chunk.content[:400] + "\n"

    system_prompt = f"""You are a world-class X-ray technology training expert and instructional designer with 20+ years of experience in security screening, baggage inspection, cargo scanning, and radiation physics education.

You create professional, technically accurate educational content for:
- Security operators and screeners
- X-ray engineers and physicists
- Maintenance technicians
- Researchers and scientists
- Training instructors

Always:
- Use precise technical terminology
- Reference relevant standards (IAEA, TSA, EU, ASTM, IEEE)
- Include safety considerations and radiation protection principles
- Make content practical and applicable
- Format with clear headers, bullet points, and tables where appropriate
- Cite relevant X-ray physics: Beer-Lambert law, HVL/TVL, dual-energy discrimination, etc.
{rag_context}"""

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            yield f"data: {json.dumps({'type': 'start'})}\n\n"
            full_content = ""
            async for chunk in provider.stream_chat(
                [{"role": "user", "content": user_prompt}],
                system_prompt=system_prompt,
            ):
                full_content += chunk
                yield f"data: {json.dumps({'type': 'chunk', 'chunk': chunk})}\n\n"
            yield f"data: {json.dumps({'type': 'done', 'content': full_content})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)})}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/education/content-types")
def list_content_types():
    return [
        {"id": "course_outline", "label": "Course Outline", "icon": "GraduationCap", "desc": "Full modular course structure with objectives"},
        {"id": "lesson_plan", "label": "Lesson Plan", "icon": "BookOpen", "desc": "Hour-by-hour teaching session plan"},
        {"id": "quiz", "label": "Quiz / Assessment", "icon": "CheckSquare", "desc": "Multiple-choice quiz with answer key"},
        {"id": "exam", "label": "Formal Examination", "icon": "FileText", "desc": "Graded exam with marking scheme"},
        {"id": "instructor_notes", "label": "Instructor Notes", "icon": "PenTool", "desc": "Pedagogical guidance and session notes"},
        {"id": "student_notes", "label": "Student Notes", "icon": "BookMarked", "desc": "Structured study notes and glossary"},
        {"id": "certificate", "label": "Certificate Template", "icon": "Award", "desc": "Training completion certificate"},
    ]
