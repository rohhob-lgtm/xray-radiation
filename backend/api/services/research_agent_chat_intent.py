"""Natural-language chat commands for the Autonomous Research Agent.

Maps phrases like "ابحث في الإنترنت وتعلّم..." / "research and learn about X"
to Research Agent mission actions, reusing the exact same
api.services.research_agent.job_runner functions the Learning Hub UI calls —
chat is a convenience entry point into the same missions, not a separate
research system.
"""
from __future__ import annotations

import re
from typing import Optional

from sqlalchemy.orm import Session

from api.db import crud
from api.services.research_agent.job_runner import (
    start_mission, pause_mission, resume_mission, stop_mission,
)
from api.services.source_trust.source_trust_service import submit_user_review, reset_user_review

_START_RE = re.compile(
    r"(?:ابحث\s+(?:في\s+الإنترنت\s+)?وتعلّم|ابحث\s+وتعلم|تعلّم\s+كل\s+ما\s+يتعلق\s+ب|"
    r"حدّث\s+معرفتك\s+(?:حول|عن)|ابحث\s+عن\s+ملفات.*?خاصة\s+ب|"
    r"research\s+and\s+learn(?:\s+everything)?(?:\s+about)?|"
    r"search\s+(?:the\s+)?(?:internet|web)\s+and\s+learn(?:\s+about)?|"
    r"update\s+your\s+knowledge\s*(?:about|on)?|learn\s+everything\s+about)"
    r"\s*[:\-]?\s*(.*)",
    re.IGNORECASE,
)
# LEARN_TOPIC — deliberately distinct from _START_RE above. A plain "start
# research" command launches a small, bounded quick_scan mission (see
# _CHAT_MISSION_LIMITS below) and answers immediately once it's done; a
# LEARN_TOPIC command must NOT answer immediately — it launches a broader
# deep_research mission (bigger coverage_target/max_coverage_rounds, see
# _LEARN_TOPIC_MISSION_LIMITS) that sweeps manufacturers, manuals, academic
# papers, patents, standards, and conference/technical reports before the
# user's *next* question about the topic gets answered from the richer
# stored knowledge — reusing the exact same discovery/extraction/trust/
# governance/memory pipeline every other mission already uses, just with a
# bigger bounded budget. Checked BEFORE _START_RE below so "learn everything
# about X" (which _START_RE would also match) resolves to the deeper
# mission, not the quick one.
_LEARN_TOPIC_HEAD_RE = re.compile(
    r"^(?:learn\s+everything\s+about|study|research)\s+(.+?)[.?!]*$",
    re.IGNORECASE,
)
_LEARN_TOPIC_AR_RE = re.compile(r"^(?:تعلّم|تعلم)\s+كل\s+شيء\s+عن\s+(.+?)[.؟!]*$")
# "Study X"/"Research X" are common in ordinary sentences too ("Research
# shows that...", "Study found no correlation...") — a bare command-shaped
# regex alone can't tell those apart from an imperative command. Reject when
# the word right after the verb is one of these common non-topic openers.
_LEARN_TOPIC_FALSE_POSITIVE_HEADS = {
    "shows", "show", "showed", "indicates", "indicate", "indicated",
    "suggests", "suggest", "suggested", "found", "finds", "reveals",
    "reveal", "revealed", "is", "was", "has", "have", "on", "into", "in",
    "the", "a", "an", "and", "papers", "paper", "results", "conducted",
}


def _detect_learn_topic(text: str) -> Optional[str]:
    m = _LEARN_TOPIC_AR_RE.match(text)
    if m:
        topic = m.group(1).strip()
        return topic or None
    m = _LEARN_TOPIC_HEAD_RE.match(text)
    if not m:
        return None
    topic = m.group(1).strip()
    if not topic:
        return None
    if topic.split()[0].lower() in _LEARN_TOPIC_FALSE_POSITIVE_HEADS:
        return None
    return topic


_STOP_RE = re.compile(r"أوقف\s+مهمة\s+البحث|stop\s+the\s+(?:current\s+)?research", re.IGNORECASE)
_PAUSE_RE = re.compile(r"أوقف\s+مؤقتا|pause\s+(?:the\s+)?research", re.IGNORECASE)
_RESUME_RE = re.compile(r"استأنف\s+التعلّم|استئناف\s+البحث|resume\s+(?:the\s+)?(?:research|learning)", re.IGNORECASE)
_SOURCES_RE = re.compile(r"اعرض\s+المصادر|ما\s+هي\s+المصادر|what\s+sources|show\s+(?:me\s+)?(?:the\s+)?sources", re.IGNORECASE)
# Phase 2B.1 — Curiosity Engine.
_CURIOSITY_RE = re.compile(
    r"اعرض\s+الأسئلة\s+التي\s+اكتشفتها|الأسئلة\s+التي\s+اكتشفتها\s+بنفسك|"
    r"questions\s+you\s+discovered|questions\s+you\s+found\s+(?:by\s+)?yourself|"
    r"show\s+(?:me\s+)?(?:the\s+)?(?:curiosity\s+)?questions",
    re.IGNORECASE,
)
# Phase 2B.2 — Knowledge Governance conflicts.
_CONFLICTS_RE = re.compile(
    r"اعرض\s+التعارضات|ما\s+هي\s+التعارضات|"
    r"show\s+(?:me\s+)?(?:the\s+)?conflicts|what\s+(?:are\s+the\s+)?conflicts",
    re.IGNORECASE,
)
# Phase 2B.3 — Dynamic Source Trust. "This source"/"this info" have no
# entity-pointing mechanism in this chat system today (same limitation the
# existing commands above already have — "show me the conflicts" shows every
# open conflict for the latest mission, not one specific claim) — resolved
# consistently here as the latest mission's top-ranked source, disclosed in
# each handler below, not silently guessed.
_TRUST_WHY_RE = re.compile(
    r"لماذا\s+تثق(?:\s+أو\s+لا\s+تثق)?\s+في\s+هذا\s+المصدر|لماذا\s+ثقتك\s+في\s+هذا\s+المصدر\s+منخفضة|"
    r"why\s+(?:do\s+you\s+)?trust\s+this\s+source|why\s+(?:is\s+your\s+)?trust\s+in\s+this\s+source\s+low",
    re.IGNORECASE,
)
_TRUST_HISTORY_RE = re.compile(
    r"اعرض\s+تاريخ\s+تغير\s+الثقة|show\s+(?:me\s+)?(?:the\s+)?trust\s+history",
    re.IGNORECASE,
)
_STRONGEST_SOURCES_RE = re.compile(
    r"ما\s+أقوى\s+المصادر\s+عن\s+(.+)|strongest\s+sources\s+(?:about|on)\s+(.+)",
    re.IGNORECASE,
)
_NEEDING_VERIFICATION_RE = re.compile(
    r"اعرض\s+المصادر\s+التي\s+تحتاج\s+تحقق(?:ًا)?\s+مستقل|"
    r"show\s+(?:me\s+)?sources\s+(?:that\s+)?need(?:ing)?\s+independent\s+verification",
    re.IGNORECASE,
)
_SINGLE_SOURCE_DEPENDENCY_RE = re.compile(
    r"هل\s+تعتمد\s+هذه\s+المعلومة\s+على\s+مصدر\s+واحد|"
    r"(?:does|is)\s+this\s+(?:information|info)\s+(?:depend|based)\s+on\s+(?:a\s+)?(?:single|one)\s+source",
    re.IGNORECASE,
)
_REJECTED_SOURCES_RE = re.compile(
    r"اعرض\s+المصادر\s+المرفوضة|show\s+(?:me\s+)?(?:the\s+)?rejected\s+sources",
    re.IGNORECASE,
)
_RATE_SOURCE_RE = re.compile(
    r"قيّم\s+هذا\s+المصدر\s+(?:على\s+أنه\s+)?(trusted|useful|questionable|rejected|موثوق|مفيد|مشكوك\s+فيه|مرفوض)|"
    r"rate\s+this\s+source\s+as\s+(trusted|useful|questionable|rejected)",
    re.IGNORECASE,
)
_RESET_RATING_RE = re.compile(
    r"ألغِ\s+تقييمي\s+(?:السابق\s+)?لهذا\s+المصدر|cancel\s+my\s+(?:previous\s+)?rating\s+for\s+this\s+source|"
    r"reset\s+my\s+review\s+(?:for\s+)?this\s+source",
    re.IGNORECASE,
)
_FIND_INDEPENDENT_SOURCE_RE = re.compile(
    r"ابحث\s+عن\s+مصدر\s+مستقل\s+يؤكد\s+هذه\s+المعلومة|"
    r"find\s+an?\s+independent\s+source\s+to\s+(?:verify|confirm)\s+this",
    re.IGNORECASE,
)
_ARABIC_TO_REVIEW_STATUS = {"موثوق": "Trusted", "مفيد": "Useful", "مشكوك فيه": "Questionable", "مرفوض": "Rejected"}

# Phase 2B.4 — Research Memory & Knowledge Freshness. "This topic" has no
# entity-pointing mechanism in this chat system today, same limitation as
# "this source" above — resolved consistently in _resolve_focus_topic_memory()
# below, disclosed in each handler's response, not silently guessed.
_TOPIC_LAST_UPDATED_RE = re.compile(
    r"متى\s+(?:كان\s+)?آخر\s+تحديث\s+لهذا\s+الموضوع|"
    r"when\s+was\s+this\s+topic\s+last\s+updated",
    re.IGNORECASE,
)
_TOPIC_IS_OUTDATED_RE = re.compile(
    r"هل\s+هذه\s+المعرفة\s+قديمة|"
    r"is\s+this\s+knowledge\s+outdated",
    re.IGNORECASE,
)
_TOPIC_REFRESH_RE = re.compile(
    r"حدّث\s+هذا\s+الموضوع|حدث\s+هذا\s+الموضوع|"
    r"update\s+this\s+topic",
    re.IGNORECASE,
)
_TOPIC_WHATS_CHANGED_RE = re.compile(
    r"ما\s+الذي\s+تغير\s+منذ\s+آخر\s+بحث|"
    r"what\s+has\s+changed\s+since\s+the\s+last\s+research",
    re.IGNORECASE,
)
_OUTDATED_TOPICS_RE = re.compile(
    r"اعرض\s+المواضيع\s+القديمة|"
    r"show\s+(?:me\s+)?outdated\s+topics",
    re.IGNORECASE,
)

# Phase 2B.5 — Autonomous Internet Learning. "تعلم عن..."/"حدّث معرفتك عن..."
# already work via _START_RE above; "اعرض مصادر تعلمك" already works via
# _SOURCES_RE below — only these 2 are genuinely new.
_WHAT_LEARNED_RE = re.compile(r"ماذا\s+تعلمت|what\s+have\s+you\s+learned", re.IGNORECASE)
_WHAT_UNKNOWN_RE = re.compile(
    r"ما\s+الذي\s+ما\s+زلت\s+لا\s+تعرفه|ماذا\s+لا\s+تعرف\s+بعد|"
    r"what\s+do\s+you\s+still\s+not\s+know|what\s+don.?t\s+you\s+know\s+yet",
    re.IGNORECASE,
)

# Phase 2B.8 — Proactive AI Scientist chat commands. Checked before the
# broader _SOURCES_RE/_CURIOSITY_RE below, same convention as every prior
# phase's additions to this dispatcher.
_RECENT_DISCOVERIES_RE = re.compile(
    r"ماذا\s+اكتشفت\s+مؤخر[اً]|what\s+have\s+you\s+discovered\s+recently",
    re.IGNORECASE,
)
_IMPORTANT_RESEARCH_RE = re.compile(
    r"ما\s+أهم\s+الأبحاث\s+الجديدة|most\s+important\s+new\s+research",
    re.IGNORECASE,
)
_WHATS_NEW_IN_RE = re.compile(
    r"ما\s+الجديد\s+في\s+(.+)|what.?s\s+new\s+(?:in|with)\s+(.+)",
    re.IGNORECASE,
)
_TRAINING_WORTHY_RE = re.compile(
    r"ما\s+الذي\s+يستحق\s+إضافته\s+إلى\s+التدريب|"
    r"what.?s\s+worth\s+adding\s+to\s+training",
    re.IGNORECASE,
)
_SCIENTIFIC_ALERTS_RE = re.compile(
    r"اعرض\s+التنبيهات\s+العلمية|show\s+(?:me\s+)?(?:the\s+)?scientific\s+alerts",
    re.IGNORECASE,
)

# Phase 2B.9 — Knowledge Health chat commands.
_KNOWLEDGE_HEALTH_RE = re.compile(
    r"ما\s+حالة\s+معرفتك|how\s+(?:is\s+|healthy\s+is\s+)?your\s+knowledge",
    re.IGNORECASE,
)
_WEAKEST_TOPICS_RE = re.compile(
    r"ما\s+أضعف\s+المواضيع|what\s+are\s+the\s+weakest\s+topics",
    re.IGNORECASE,
)
_OLD_TOPICS_HEALTH_RE = re.compile(
    r"ما\s+الموضوعات\s+القديمة|what\s+are\s+the\s+outdated\s+topics",
    re.IGNORECASE,
)
_DANGEROUS_CONFLICTS_RE = re.compile(
    r"أين\s+توجد\s+تعارضات\s+خطيرة|where\s+are\s+(?:there\s+)?(?:dangerous|critical)\s+conflicts",
    re.IGNORECASE,
)
_LEARN_NEXT_RE = re.compile(
    r"ماذا\s+يجب\s+أن\s+تتعلم\s+بعد|what\s+should\s+you\s+learn\s+next",
    re.IGNORECASE,
)


def detect_research_agent_intent(message: str) -> Optional[dict]:
    """Return {"action": ..., ...} if the message is a research-agent command, else None."""
    text = (message or "").strip()
    if not text:
        return None

    # Checked before _START_RE — see _LEARN_TOPIC_HEAD_RE's docstring above
    # for why "learn everything about X" must resolve here, not to the
    # smaller quick-scan "start" action below.
    learn_topic = _detect_learn_topic(text)
    if learn_topic:
        return {"action": "learn_topic", "topic": learn_topic}

    m = _START_RE.search(text)
    if m:
        mission_text = (m.group(1) or "").strip() or text
        return {"action": "start", "mission_text": mission_text}
    if _STOP_RE.search(text):
        return {"action": "stop"}
    if _PAUSE_RE.search(text):
        return {"action": "pause"}
    if _RESUME_RE.search(text):
        return {"action": "resume"}
    # Trust commands are checked BEFORE the older, broader _SOURCES_RE/
    # _CURIOSITY_RE below — "show me sources needing independent
    # verification" contains "show me sources", which _SOURCES_RE's own
    # pattern would otherwise match first as a plain source-list request.
    rate_m = _RATE_SOURCE_RE.search(text)
    if rate_m:
        raw_status = (rate_m.group(1) or rate_m.group(2) or "").strip().lower()
        status = _ARABIC_TO_REVIEW_STATUS.get(raw_status, raw_status.capitalize())
        return {"action": "rate_source", "status": status}
    if _RESET_RATING_RE.search(text):
        return {"action": "reset_rating"}
    if _TRUST_WHY_RE.search(text):
        return {"action": "why_trust"}
    if _TRUST_HISTORY_RE.search(text):
        return {"action": "trust_history"}
    strongest_m = _STRONGEST_SOURCES_RE.search(text)
    if strongest_m:
        topic = (strongest_m.group(1) or strongest_m.group(2) or "").strip()
        return {"action": "strongest_sources", "topic": topic}
    if _NEEDING_VERIFICATION_RE.search(text):
        return {"action": "needing_verification"}
    if _SINGLE_SOURCE_DEPENDENCY_RE.search(text):
        return {"action": "single_source_check"}
    if _REJECTED_SOURCES_RE.search(text):
        return {"action": "rejected_sources"}
    if _FIND_INDEPENDENT_SOURCE_RE.search(text):
        return {"action": "find_independent_source"}

    # Phase 2B.4 — checked before the broader _SOURCES_RE/_CURIOSITY_RE
    # below, same reasoning as the trust commands above.
    if _TOPIC_LAST_UPDATED_RE.search(text):
        return {"action": "topic_last_updated"}
    if _TOPIC_IS_OUTDATED_RE.search(text):
        return {"action": "topic_is_outdated"}
    if _TOPIC_REFRESH_RE.search(text):
        return {"action": "topic_refresh"}
    if _TOPIC_WHATS_CHANGED_RE.search(text):
        return {"action": "topic_whats_changed"}
    if _OUTDATED_TOPICS_RE.search(text):
        return {"action": "list_outdated_topics"}

    # Phase 2B.5 — checked before the broader _SOURCES_RE/_CURIOSITY_RE too.
    if _WHAT_LEARNED_RE.search(text):
        return {"action": "what_learned"}
    if _WHAT_UNKNOWN_RE.search(text):
        return {"action": "what_unknown"}

    # Phase 2B.8 — Proactive AI Scientist, checked before the broader
    # _SOURCES_RE/_CURIOSITY_RE too, same reasoning as every block above.
    if _RECENT_DISCOVERIES_RE.search(text):
        return {"action": "recent_discoveries"}
    if _IMPORTANT_RESEARCH_RE.search(text):
        return {"action": "important_research"}
    whats_new_m = _WHATS_NEW_IN_RE.search(text)
    if whats_new_m:
        subject = (whats_new_m.group(1) or whats_new_m.group(2) or "").strip(" ?؟.")
        return {"action": "whats_new_in", "subject": subject}
    if _TRAINING_WORTHY_RE.search(text):
        return {"action": "training_worthy"}
    if _SCIENTIFIC_ALERTS_RE.search(text):
        return {"action": "list_scientific_alerts"}

    # Phase 2B.9 — Knowledge Health, checked before the broader
    # _SOURCES_RE/_CURIOSITY_RE too, same reasoning as every block above.
    if _KNOWLEDGE_HEALTH_RE.search(text):
        return {"action": "knowledge_health_overview"}
    if _WEAKEST_TOPICS_RE.search(text):
        return {"action": "weakest_topics"}
    if _OLD_TOPICS_HEALTH_RE.search(text):
        # Reuses the exact same 2B.4 "outdated topics" answer — no need for
        # a second, parallel notion of "outdated" alongside the existing one.
        return {"action": "list_outdated_topics"}
    if _DANGEROUS_CONFLICTS_RE.search(text):
        return {"action": "dangerous_conflicts"}
    if _LEARN_NEXT_RE.search(text):
        return {"action": "learn_next"}

    if _SOURCES_RE.search(text):
        return {"action": "list_sources"}
    if _CURIOSITY_RE.search(text):
        return {"action": "list_curiosity"}
    if _CONFLICTS_RE.search(text):
        return {"action": "list_conflicts"}
    return None


# Conservative default limits for chat-launched missions — Quick Scan, Free
# Mode always on (chat never opts a mission into paid APIs on the user's
# behalf). A user who wants a bigger sweep says "learn everything about X"
# instead (see _LEARN_TOPIC_MISSION_LIMITS below) or uses the full
# Autonomous Research panel in Learning Hub for Continuous Learning.
_CHAT_MISSION_LIMITS = {
    "max_pages": 20, "max_files": 20, "max_storage_mb": 100,
    "max_depth": 1, "min_relevance_score": 0.15, "min_quality_score": 45.0,
}

# LEARN_TOPIC missions are deliberately broader than the quick-scan limits
# above — the whole point is a comprehensive sweep across manufacturers,
# manuals, academic papers, patents, standards, and technical reports before
# the user's next question gets answered. Still bounded (not the unlimited
# Continuous Learning mode) and still Free Mode only — same discipline as
# every other chat-launched mission, just a bigger budget.
_LEARN_TOPIC_MISSION_LIMITS = {
    "max_pages": 60, "max_files": 60, "max_storage_mb": 300,
    "max_depth": 2, "min_relevance_score": 0.15, "min_quality_score": 40.0,
}


def _resolve_focus_source(db: Session, mission):
    """"This source"/"this info" have no entity-pointing mechanism in this
    chat system today — resolved consistently as the latest mission's
    top-ranked (by static quality) source, the same list "show me the
    sources" already surfaces first. A disclosed simplification, not a
    silent guess — every trust-command response says which source it means."""
    sources = crud.list_research_sources(db, mission.id)
    return sources[0] if sources else None


def _resolve_focus_topic_memory(db: Session, mission):
    """"This topic" resolved consistently as the latest mission's
    top-ranked topic's linked TopicResearchMemory — same disclosed-
    simplification convention as _resolve_focus_source() above."""
    topics = crud.list_research_topics(db, mission.id)  # already ordered by rank desc
    for topic in topics:
        if topic.topic_memory_id:
            return crud.get_topic_research_memory(db, topic.topic_memory_id)
    return None


async def handle_research_agent_intent(db: Session, user_id: str, intent: dict) -> dict:
    """Execute the detected intent and return a chat-ready result payload."""
    action = intent["action"]

    if action == "start":
        mission_text = intent["mission_text"]
        mission = crud.create_research_mission(
            db, user_id=user_id, mission_text=mission_text, mode="quick_scan",
            languages=["en"], content_types=["web_pages"], free_mode=True,
            limits=dict(_CHAT_MISSION_LIMITS),
        )
        start_mission(mission.id)
        return {"type": "research_mission_started", "mission": crud.research_mission_to_dict(mission)}

    if action == "learn_topic":
        topic = intent["topic"]
        mission = crud.create_research_mission(
            db, user_id=user_id, mission_text=f"Learn everything about {topic}",
            mode="deep_research", languages=["en"], content_types=["web_pages"],
            free_mode=True, limits=dict(_LEARN_TOPIC_MISSION_LIMITS),
            coverage_target=85.0, max_coverage_rounds=5, origin="chat_learn_topic",
        )
        start_mission(mission.id)
        return {"type": "research_mission_started", "mission": crud.research_mission_to_dict(mission)}

    # ── Proactive AI Scientist (Phase 2B.8) — global, not mission-scoped,
    # so handled before the "no missions yet" gate below (same as "start"). ──
    if action == "recent_discoveries":
        alerts = crud.list_scientific_alerts(db, limit=10)
        return {"type": "research_scientific_alerts", "query_label": "recent discoveries", "alerts": [crud.scientific_alert_to_dict(a) for a in alerts]}

    if action == "important_research":
        alerts = crud.list_scientific_alerts(db, alert_type="Scientific Alert", limit=10)
        alerts += crud.list_scientific_alerts(db, alert_type="Technology Update", limit=10)
        alerts.sort(key=lambda a: a.created_at, reverse=True)
        return {"type": "research_scientific_alerts", "query_label": "most important new research", "alerts": [crud.scientific_alert_to_dict(a) for a in alerts[:10]]}

    if action == "whats_new_in":
        from api.services.retrieval_utils import tokenize, keyword_score
        subject = intent.get("subject", "")
        query_tokens = tokenize(subject)
        candidates = crud.list_scientific_alerts(db, limit=100)
        if query_tokens:
            scored = [(keyword_score(query_tokens, f"{a.title} {a.summary} {a.topic_key}"), a) for a in candidates]
            matched = [a for score, a in sorted(scored, key=lambda p: p[0], reverse=True) if score > 0]
        else:
            matched = candidates
        return {"type": "research_scientific_alerts", "query_label": f"what's new in {subject}" if subject else "recent updates", "alerts": [crud.scientific_alert_to_dict(a) for a in matched[:10]]}

    if action == "training_worthy":
        alerts = crud.list_scientific_alerts(db, alert_type="Training Impact", limit=10)
        return {"type": "research_scientific_alerts", "query_label": "worth adding to training", "alerts": [crud.scientific_alert_to_dict(a) for a in alerts]}

    if action == "list_scientific_alerts":
        alerts = crud.list_scientific_alerts(db, alert_type="Scientific Alert", limit=10)
        return {"type": "research_scientific_alerts", "query_label": "scientific alerts", "alerts": [crud.scientific_alert_to_dict(a) for a in alerts]}

    # ── Knowledge Health (Phase 2B.9) — global, cache reads only (the audit
    # itself runs on the existing scheduler tick, never inline here). ──
    if action == "knowledge_health_overview":
        from api.services.research_brain import knowledge_health as kh
        overall = kh.get_overall_health(db)
        return {
            "type": "research_knowledge_health", "view": "overview",
            "overall": crud.knowledge_health_snapshot_to_dict(overall) if overall else None,
            "recommended_actions": kh.get_recommended_actions(db, limit=5),
        }

    if action == "weakest_topics":
        from api.services.research_brain import knowledge_health as kh
        weak = crud.list_knowledge_health_snapshots(db, scope_type="Topic", classification="Weak", limit=10)
        critical = crud.list_knowledge_health_snapshots(db, scope_type="Topic", classification="Critical", limit=10)
        snapshots = (critical + weak)[:10]
        return {"type": "research_knowledge_health", "view": "weakest_topics", "snapshots": [crud.knowledge_health_snapshot_to_dict(s) for s in snapshots]}

    if action == "dangerous_conflicts":
        from api.services.research_brain import knowledge_health as kh
        gaps = kh.get_safety_critical_gaps(db, limit=10)
        conflicts = [c for c in kh.get_unresolved_conflicts_summary(db, limit=50) if c.severity in ("high", "critical") or c.human_review_required]
        return {
            "type": "research_knowledge_health", "view": "dangerous_conflicts",
            "snapshots": [crud.knowledge_health_snapshot_to_dict(s) for s in gaps],
            "conflicts": [crud.knowledge_conflict_to_dict(c) for c in conflicts[:10]],
        }

    if action == "learn_next":
        from api.services.research_brain import knowledge_health as kh
        return {"type": "research_knowledge_health", "view": "learn_next", "recommended_actions": kh.get_recommended_actions(db, limit=10)}

    missions = crud.list_research_missions(db, user_id=user_id)
    if not missions:
        return {
            "type": "research_error",
            "message": 'You don\'t have any research missions yet. Try: "research and learn about <topic>".',
        }
    latest = missions[0]

    if action == "pause":
        mission = await pause_mission(latest.id)
        return {"type": "research_mission_paused", "mission": crud.research_mission_to_dict(mission)}
    if action == "resume":
        mission = await resume_mission(latest.id)
        return {"type": "research_mission_resumed", "mission": crud.research_mission_to_dict(mission)}
    if action == "stop":
        mission = await stop_mission(latest.id)
        return {"type": "research_mission_stopped", "mission": crud.research_mission_to_dict(mission)}
    if action == "list_sources":
        sources = crud.list_research_sources(db, latest.id)
        return {
            "type": "research_sources",
            "mission": crud.research_mission_to_dict(latest),
            "sources": [crud.research_source_to_dict(s) for s in sources[:20]],
        }
    if action == "list_curiosity":
        questions = crud.list_curiosity_questions(db, mission_id=latest.id)
        return {
            "type": "research_curiosity_questions",
            "mission": crud.research_mission_to_dict(latest),
            "questions": [crud.curiosity_question_to_dict(q) for q in questions[:20]],
        }
    if action == "list_conflicts":
        topics = crud.list_research_topics(db, latest.id)
        node_ids = {
            node.id
            for topic in topics
            for node in crud.list_knowledge_nodes_by_topic(db, topic.id, status=None)
        }
        conflicts = [
            c for c in crud.list_knowledge_conflicts(db, status="Open")
            if c.subject_node_id in node_ids
        ]
        return {
            "type": "research_conflicts",
            "mission": crud.research_mission_to_dict(latest),
            "conflicts": [crud.knowledge_conflict_to_dict(c) for c in conflicts[:20]],
        }

    # ── Dynamic Source Trust (Phase 2B.3) ────────────────────────────────
    if action in ("why_trust", "trust_history", "rate_source", "reset_rating"):
        source = _resolve_focus_source(db, latest)
        if not source:
            return {"type": "research_error", "message": "No sources discovered yet for the current mission."}

        if action == "why_trust":
            return {
                "type": "research_source_trust",
                "mission": crud.research_mission_to_dict(latest),
                "source": crud.research_source_to_dict(source),
            }
        if action == "trust_history":
            history = crud.list_source_trust_history(db, source.id, limit=20)
            return {
                "type": "research_source_trust_history",
                "mission": crud.research_mission_to_dict(latest),
                "source": crud.research_source_to_dict(source),
                "history": [crud.source_trust_history_to_dict(h) for h in history],
            }
        if action == "rate_source":
            try:
                updated = submit_user_review(db, source.id, user_id, intent["status"])
            except ValueError as exc:
                return {"type": "research_error", "message": str(exc)}
            return {
                "type": "research_source_reviewed",
                "mission": crud.research_mission_to_dict(latest),
                "source": crud.research_source_to_dict(updated),
            }
        if action == "reset_rating":
            updated = reset_user_review(db, source.id, user_id)
            return {
                "type": "research_source_review_reset",
                "mission": crud.research_mission_to_dict(latest),
                "source": crud.research_source_to_dict(updated),
            }

    if action == "strongest_sources":
        topic = (intent.get("topic") or "").strip().lower()
        sources = crud.list_research_sources(db, latest.id)
        if topic:
            sources = [s for s in sources if topic in (s.title or "").lower() or topic in (s.domain or "").lower()] or sources
        ranked = sorted(sources, key=lambda s: s.effective_trust_score, reverse=True)[:10]
        return {
            "type": "research_strongest_sources",
            "mission": crud.research_mission_to_dict(latest),
            "topic": intent.get("topic", ""),
            "sources": [crud.research_source_to_dict(s) for s in ranked],
        }

    if action == "needing_verification":
        sources = crud.list_research_sources(db, latest.id)
        unverified = []
        for source in sources:
            evidence = crud.list_knowledge_evidence_by_source(db, source.id)
            supporting = [e for e in evidence if e.supports and e.node_id]
            if not supporting:
                continue
            corroborated = any(
                len({(crud.get_research_source(db, ev2.research_source_id).source_family_id or ev2.research_source_id)
                     for ev2 in crud.list_knowledge_evidence(db, node_id=e.node_id)
                     if ev2.supports and crud.get_research_source(db, ev2.research_source_id)}) > 1
                for e in supporting
            )
            if not corroborated:
                unverified.append(source)
        return {
            "type": "research_sources_needing_verification",
            "mission": crud.research_mission_to_dict(latest),
            "sources": [crud.research_source_to_dict(s) for s in unverified[:20]],
        }

    if action == "single_source_check":
        topics = crud.list_research_topics(db, latest.id)
        total_nodes = 0
        single_source_nodes = 0
        for topic in topics:
            for node in crud.list_knowledge_nodes_by_topic(db, topic.id, status="current"):
                total_nodes += 1
                families = {
                    (crud.get_research_source(db, e.research_source_id).source_family_id or e.research_source_id)
                    for e in crud.list_knowledge_evidence(db, node_id=node.id)
                    if e.supports and crud.get_research_source(db, e.research_source_id)
                }
                if len(families) <= 1:
                    single_source_nodes += 1
        return {
            "type": "research_single_source_check",
            "mission": crud.research_mission_to_dict(latest),
            "total_facts": total_nodes,
            "single_source_facts": single_source_nodes,
        }

    if action == "rejected_sources":
        sources = crud.list_research_sources(db, latest.id)
        rejected = [s for s in sources if s.trust_status == "rejected"]
        return {
            "type": "research_rejected_sources",
            "mission": crud.research_mission_to_dict(latest),
            "sources": [crud.research_source_to_dict(s) for s in rejected],
        }

    if action == "find_independent_source":
        from api.services.research_brain.curiosity_engine import _generate_trust_driven_questions
        questions = _generate_trust_driven_questions(db, latest)
        return {
            "type": "research_independent_source_search",
            "mission": crud.research_mission_to_dict(latest),
            "questions": [crud.curiosity_question_to_dict(q) for q in questions[:5]],
        }

    # ── Research Memory & Knowledge Freshness (Phase 2B.4) ───────────────
    if action == "list_outdated_topics":
        memories = crud.list_outdated_topic_memories(db, limit=20)
        return {
            "type": "research_outdated_topics",
            "topics": [crud.topic_research_memory_to_dict(m) for m in memories],
        }

    if action in ("topic_last_updated", "topic_is_outdated", "topic_refresh", "topic_whats_changed"):
        memory = _resolve_focus_topic_memory(db, latest)
        if not memory:
            return {"type": "research_error", "message": "No topic memory found yet for the current mission."}

        if action == "topic_last_updated":
            return {
                "type": "research_topic_last_updated",
                "mission": crud.research_mission_to_dict(latest),
                "topic_memory": crud.topic_research_memory_to_dict(memory),
            }
        if action == "topic_is_outdated":
            from api.services.research_brain.research_memory import compute_freshness
            status = compute_freshness(db, memory.id)
            db.refresh(memory)
            return {
                "type": "research_topic_freshness",
                "mission": crud.research_mission_to_dict(latest),
                "topic_memory": crud.topic_research_memory_to_dict(memory),
                "freshness_status": status,
            }
        if action == "topic_refresh":
            from api.services.research_brain.research_memory import refresh_topic
            child = refresh_topic(db, memory.id)
            return {
                "type": "research_topic_refresh_started",
                "mission": crud.research_mission_to_dict(child),
                "topic_memory": crud.topic_research_memory_to_dict(memory),
            }
        if action == "topic_whats_changed":
            return {
                "type": "research_topic_whats_changed",
                "mission": crud.research_mission_to_dict(latest),
                "topic_memory": crud.topic_research_memory_to_dict(memory),
            }

    # ── Autonomous Internet Learning + Manufacturer/Scientific Intelligence (Phase 2B.5) ──
    if action == "what_learned":
        topics = crud.list_research_topics(db, latest.id)
        sources = crud.list_research_sources(db, latest.id)
        facts_count = sum(len(crud.list_knowledge_nodes_by_topic(db, t.id, status="current")) for t in topics)
        return {
            "type": "research_what_learned",
            "mission": crud.research_mission_to_dict(latest),
            "topics_covered": len([t for t in topics if t.status == "covered"]),
            "topics_total": len(topics),
            "sources_count": len(sources),
            "facts_count": facts_count,
        }

    if action == "what_unknown":
        from api.services.research_brain.gap_detector import list_low_coverage_topics
        low = list_low_coverage_topics(db, latest.id, threshold=latest.coverage_target)
        open_questions = [
            q for q in crud.list_curiosity_questions(db, mission_id=latest.id)
            if q.status in ("Suggested", "Approved")
        ]
        return {
            "type": "research_what_unknown",
            "mission": crud.research_mission_to_dict(latest),
            "low_coverage_topics": low,
            "open_questions": [crud.curiosity_question_to_dict(q) for q in open_questions[:10]],
        }

    return {"type": "research_error", "message": "Unrecognized research command."}
