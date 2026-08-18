"""
Exam pattern learner — extracts question/answer patterns from documents locally.

Detects multiple-choice and short-answer questions using regex, then:
  - Classifies Bloom's Taxonomy level by keyword matching
  - Scores distractor quality (length variance, plausibility of wrong answers)
  - Stores each pattern in ExamPattern for use as few-shot examples

No API calls — everything runs locally.
"""
from __future__ import annotations
import logging
import re
from typing import Optional

from sqlalchemy.orm import Session

log = logging.getLogger(__name__)

# ── Regex patterns ─────────────────────────────────────────────────────────────

# Numbered questions: "1." / "1)" / "Q1." etc.
_RE_QUESTION = re.compile(
    r'(?:^|\n)\s*(?:[Qq]?[\d]+[\.\)]\s+)([A-Z][^\n]{20,300}[?.])',
    re.MULTILINE,
)

# MCQ options: "A." / "A)" / "a." / "(A)" followed by text
_RE_OPTION = re.compile(
    r'(?:^|\n)\s*(?:\(?[A-Da-d][\.\)]\s*)([^\n]{5,200})',
    re.MULTILINE,
)

# "Answer:" / "Correct:" lines
_RE_ANSWER = re.compile(
    r'(?:^|\n)\s*(?:Answer|Correct\s+Answer|Key)[:\s]+([A-Da-d]\.?\s*[^\n]{0,200})',
    re.MULTILINE | re.IGNORECASE,
)

# Topic heading before questions: "Section:", "Topic:", chapter headings
_RE_TOPIC = re.compile(
    r'(?:^|\n)\s*(?:Section|Topic|Chapter|Module|Unit)[:\s]+([A-Z][^\n]{5,80})',
    re.MULTILINE,
)

from api.services.terminology_service import classify_bloom, BLOOM_KEYWORDS


def _score_distractor_quality(options: list[str]) -> float:
    """
    Score distractor (wrong answer) quality 0.0–1.0.
    Heuristics:
      - Good: similar length across options (±30% variance)
      - Good: all options are non-trivial (>5 chars)
      - Poor: one option is obviously "All of the above" / "None of the above"
    """
    if len(options) < 2:
        return 0.0

    lengths = [len(o) for o in options]
    avg_len = sum(lengths) / len(lengths)
    if avg_len == 0:
        return 0.0

    variance = sum((l - avg_len) ** 2 for l in lengths) / len(lengths)
    cv = (variance ** 0.5) / avg_len  # coefficient of variation

    score = max(0.0, 1.0 - cv)  # lower variance = better distractors

    # Penalty for trivial options
    trivial = {"all of the above", "none of the above", "all the above", "both a and b"}
    penalised = sum(1 for o in options if o.lower().strip() in trivial)
    score -= penalised * 0.25

    return round(max(0.0, min(1.0, score)), 2)


def _classify_difficulty(question: str, options: list[str]) -> str:
    """Heuristic difficulty based on question length and vocabulary."""
    q = question.lower()

    hard_signals = ["calculate", "derive", "troubleshoot", "diagnose",
                    "why does", "what causes", "explain the mechanism",
                    "compare", "evaluate", "critically"]
    easy_signals = ["what is", "which of", "true or false", "identify",
                    "name the", "list", "where is"]

    if any(sig in q for sig in hard_signals):
        return "hard"
    if any(sig in q for sig in easy_signals):
        return "easy"
    if len(question) > 150:
        return "hard"
    return "medium"


def _extract_questions(text: str) -> list[dict]:
    """
    Parse a document for MCQ patterns and return structured question dicts.
    """
    questions = []
    current_topic = "General"

    # Track topic sections
    topic_positions: list[tuple[int, str]] = []
    for m in _RE_TOPIC.finditer(text):
        topic_positions.append((m.start(), m.group(1).strip()))

    def _get_topic(pos: int) -> str:
        topic = "General"
        for tp_pos, tp_name in topic_positions:
            if tp_pos <= pos:
                topic = tp_name
        return topic

    # Find questions
    question_positions: list[tuple[int, str]] = []
    for m in _RE_QUESTION.finditer(text):
        question_positions.append((m.start(), m.group(1).strip()))

    for i, (q_pos, q_text) in enumerate(question_positions):
        # Find options between this question and the next
        next_pos = question_positions[i + 1][0] if i + 1 < len(question_positions) else q_pos + 1000
        segment = text[q_pos:next_pos]

        options = []
        for om in _RE_OPTION.finditer(segment):
            opt = om.group(1).strip()
            if opt and len(opt) > 3:
                options.append(opt)

        # Look for answer line
        answer_text = None
        for am in _RE_ANSWER.finditer(segment):
            answer_text = am.group(1).strip()
            break

        if not options and not answer_text:
            continue  # Skip non-Q&A content

        bloom = classify_bloom(q_text)
        difficulty = _classify_difficulty(q_text, options)
        distractor_q = _score_distractor_quality(options)
        topic = _get_topic(q_pos)

        questions.append({
            "question_text": q_text,
            "options": options[:4],
            "answer_text": answer_text,
            "bloom_level": bloom,
            "difficulty": difficulty,
            "distractor_quality": distractor_q,
            "topic": topic[:100] if topic else None,
        })

    return questions


def extract_and_store(db: Session, doc_id: str, filename: str, text: str) -> int:
    """
    Extract exam patterns from document text and store them.
    Returns count of new patterns stored.
    Idempotent per document.
    """
    from api.db.models import ExamPattern

    # Idempotency
    existing = db.query(ExamPattern).filter(
        ExamPattern.source_doc_id == doc_id
    ).first()
    if existing:
        log.debug("Exam patterns already extracted for %s — skipping", doc_id)
        return 0

    questions = _extract_questions(text[:100_000])
    if not questions:
        return 0

    count = 0
    for q in questions:
        db.add(ExamPattern(
            source_doc_id=doc_id,
            source_filename=filename,
            question_text=q["question_text"],
            answer_text=q["answer_text"],
            bloom_level=q["bloom_level"],
            difficulty=q["difficulty"],
            distractor_quality=q["distractor_quality"],
            topic=q["topic"],
            options=q["options"],
        ))
        count += 1

    try:
        db.commit()
        log.info("ExamLearner: stored %d patterns from %s", count, filename)
    except Exception as exc:
        db.rollback()
        log.warning("ExamPattern commit failed for %s: %s", doc_id, exc)
        return 0

    return count


def list_patterns(db: Session, topic: str = "", bloom: str = "",
                  difficulty: str = "", limit: int = 50, offset: int = 0) -> dict:
    """List exam patterns with optional filters."""
    from api.db.models import ExamPattern

    q = db.query(ExamPattern)
    if topic:
        q = q.filter(ExamPattern.topic.ilike(f"%{topic}%"))
    if bloom:
        q = q.filter(ExamPattern.bloom_level == bloom)
    if difficulty:
        q = q.filter(ExamPattern.difficulty == difficulty)

    total = q.count()
    rows = q.order_by(ExamPattern.created_at.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "patterns": [
            {
                "id": p.id,
                "source_doc_id": p.source_doc_id,
                "source_filename": p.source_filename,
                "question_text": p.question_text,
                "answer_text": p.answer_text,
                "bloom_level": p.bloom_level,
                "difficulty": p.difficulty,
                "distractor_quality": p.distractor_quality,
                "topic": p.topic,
                "options": p.options,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in rows
        ],
    }
