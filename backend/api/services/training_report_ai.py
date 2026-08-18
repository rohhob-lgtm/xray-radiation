"""
Training Course Report — narrative generation.

Drafts the ten narrative sections of a Training Course Report strictly from
the structured facts the operator entered — never inventing project codes,
serial numbers, dates, attendee names, exam results or customer details.

Every section has a deterministic fallback composer (a direct fill-in of the
original template sentence with the supplied values) so the feature keeps
working with no facts lost even when no real LLM is configured, or a live
provider call fails. When a real provider *is* active, its answer is used
instead — it is asked to write in the same tone as the completed reference
report, still bounded to the same fact set.
"""
from __future__ import annotations
import logging
from typing import Any, Optional

from api.utils.training_report_docx import fmt_num

log = logging.getLogger(__name__)

_STYLE_REFERENCE = (
    "The Contract exits to provide 1 week of P60 ZBX OP Training - on Rapiscan Systems| "
    "AS&E Cargo Inspection Systems at Aqaba- Sea port -Jordan. The course was delivered by "
    "Mohamed Noaman of the Rapiscan Systems| AS&E Training department. Training delivered in "
    "Arabic Language. A total of 13 students of GID attended the training. Certificates were "
    "awarded to 13 students."
)


def _plural(n: Any, word: str) -> str:
    try:
        return word if int(n) == 1 else word + "s"
    except (TypeError, ValueError):
        return word + "s"


# ── Deterministic fallback composers (facts -> sentence, "" if nothing to say) ─

def _fb_reference_documents(f: dict) -> str:
    refs = f.get("doc_refs") or []
    parts = [
        f"{(r.get('reference_number') or '').strip()} - {(r.get('title') or '').strip()}".strip(" -")
        for r in refs if (r.get("reference_number") or "").strip() or (r.get("title") or "").strip()
    ]
    if not parts:
        return ""
    joined = "; ".join(parts)
    return (
        "This document should be read in conjunction with any Contract, Sub-Contract, "
        "Proposal or Tender related documentation for this Project. This document references "
        f"the following referenced document{'s' if len(parts) > 1 else ''}: {joined}."
    )


def _fb_background(f: dict) -> str:
    training_level = f.get("training_level") or ""
    system_type = f.get("system_type") or ""
    site = f.get("site_of_operation") or ""
    if not (training_level and system_type and site):
        return ""
    days = f.get("total_training_days")
    days_phrase = f"{fmt_num(days)} {_plural(days, 'day')} of " if days else ""
    purpose = f.get("training_purpose") or ""
    s = f"The Contract exists to provide {days_phrase}{training_level} training on Rapiscan {system_type} Inspection Systems at {site}."
    if purpose:
        s += f" {purpose}"
    return s


def _fb_instructor(f: dict) -> str:
    names = (f.get("instructor") or "").strip()
    if not names:
        return ""
    is_plural = "," in names or " and " in names or "&" in names
    verb = "were" if is_plural else "was"
    s = f"The course {verb} delivered by {names} of the Rapiscan Training Department."
    bio = f.get("instructor_bio") or ""
    if bio:
        s += f" {bio}"
    return s


def _fb_delivery_language(f: dict) -> str:
    delivery = (f.get("delivery_language") or "").strip()
    if not delivery:
        return ""
    doc_lang = (f.get("documentation_language") or delivery).strip()
    s = f"Training was delivered in {delivery}."
    if doc_lang:
        s += (
            " Documentation to support training, including System Manuals, Student Guides, "
            f"Job Aids and Students' course notes as appropriate, were provided as electronic copy in {doc_lang}."
        )
    return s


def _fb_training_location(f: dict) -> str:
    classroom = (f.get("classroom_location") or "").strip()
    practical = (f.get("practical_location") or "").strip()
    if not (classroom or practical):
        return ""
    parts = []
    if classroom:
        parts.append(f"Classroom training was presented at {classroom}.")
    if practical:
        parts.append(f"Practical Training was given at {practical}.")
    return " ".join(parts)


def _fb_students(f: dict) -> str:
    total = f.get("attendees_total")
    if not total:
        return ""
    s = (
        f"A total of {total} {_plural(total, 'student')} attended the training sessions and "
        "completed the reinforcement hours required to complete the course."
    )
    extra = []
    if f.get("previous_experience"):
        extra.append(f"Trainees had {f['previous_experience']} previous experience")
    if f.get("computer_skills"):
        extra.append(f"{f['computer_skills']} computer skills")
    if f.get("language_ability"):
        extra.append(f"{f['language_ability']} language ability")
    if f.get("trainee_background"):
        extra.append(str(f["trainee_background"]))
    if extra:
        s += " " + ". ".join(extra) + "."
    return s


def _fb_schedule(f: dict) -> str:
    days = f.get("total_training_days")
    start = (f.get("start_date") or "").strip()
    end = (f.get("end_date") or "").strip()
    if not (days and start and end):
        return ""
    s = (
        f"Training was delivered according to the schedule over a period of {fmt_num(days)} training "
        f"{_plural(days, 'day')} commencing on {start} and finishing on {end}."
    )
    if f.get("schedule_summary"):
        s += f" {f['schedule_summary']}"
    if f.get("subjects_covered"):
        s += f" Subjects covered included: {f['subjects_covered']}."
    if f.get("practical_activities"):
        s += f" Practical activities performed included: {f['practical_activities']}."
    return s


def _fb_completion_certification(f: dict) -> str:
    system_type = (f.get("system_type") or "").strip()
    if not system_type:
        return ""
    s = (
        "Certified students attended all sessions of training, or sufficient sessions, and have "
        "demonstrated to the instructors that satisfactory levels of learning have been achieved "
        f"to be knowledgeable, competent and confident in operating/maintaining the {system_type} system. "
        "Students assessments by observation and verbal questioning were carried out by the instructors "
        "continuously during the training."
    )
    if f.get("written_exam_completed"):
        s += " A written examination was completed."
    if f.get("practical_exam_completed"):
        s += " A practical examination was completed on the final day of the course."
    if f.get("pass_percentage"):
        s += f" The minimum pass percentage required for certification was {fmt_num(f['pass_percentage'])}%."
    certified = f.get("attendees_certified")
    if certified is not None and certified != "":
        s += (
            f" Certification was awarded to {certified} {_plural(certified, 'student')}. A list of all "
            "attendees and the serial number of the certificate, if awarded, and observations as noted "
            "by the instructor are shown in the table below."
        )
    if f.get("certification_requirements"):
        s += f" {f['certification_requirements']}"
    if f.get("instructor_evaluation"):
        s += f" {f['instructor_evaluation']}"
    return s


def _fb_additional_notes(f: dict) -> str:
    parts = []
    if f.get("additional_notes"):
        parts.append(f"Notes: {f['additional_notes']}")
    if f.get("qa_issues"):
        parts.append(f"QA Issues: {f['qa_issues']}")
    if f.get("technical_issues"):
        parts.append(f"Technical Issues Discovered: {f['technical_issues']}")
    if f.get("action_taken"):
        resp = f" ({f['responsible_party']})" if f.get("responsible_party") else ""
        parts.append(f"Action Taken: {f['action_taken']}{resp}")
    return " ".join(parts)


def _fb_follow_up_plan(f: dict) -> str:
    plan = (f.get("follow_up_plan") or "").strip()
    if plan:
        return plan
    return (
        "Operators should start working on the system as soon as possible after training to "
        "reinforce and improve their knowledge and experience."
    )


_FALLBACKS = {
    "reference_documents": _fb_reference_documents,
    "background": _fb_background,
    "instructor": _fb_instructor,
    "delivery_language": _fb_delivery_language,
    "training_location": _fb_training_location,
    "students": _fb_students,
    "schedule": _fb_schedule,
    "completion_certification": _fb_completion_certification,
    "additional_notes": _fb_additional_notes,
    "follow_up_plan": _fb_follow_up_plan,
}

_SECTION_ROLE = {
    "reference_documents": "lists the reference manuals/documents this report should be read alongside",
    "background": "explains the contractual purpose of the training and the system it covers",
    "instructor": "names the instructor(s) who delivered the course",
    "delivery_language": "states the language training and documentation were delivered in",
    "training_location": "states where classroom and practical training took place",
    "students": "describes the attendees and their background",
    "schedule": "describes the training schedule and days",
    "completion_certification": "describes assessment method and certification outcome",
    "additional_notes": "notes any QA or technical issues raised during the course",
    "follow_up_plan": "states the after-training follow-up plan",
}


async def generate_section(
    section_key: str,
    facts: dict,
    output_language: str = "en",
    provider=None,
) -> str:
    """Return the narrative text for one section, or "" if there is nothing
    to say (all relevant facts were left blank — omitted cleanly, no filler)."""
    fallback_fn = _FALLBACKS.get(section_key)
    if fallback_fn is None:
        raise ValueError(f"Unknown training report section: {section_key}")

    fallback_text = fallback_fn(facts)
    if not fallback_text:
        return ""

    if provider is None or getattr(provider, "provider_id", "mock") == "mock":
        return fallback_text

    try:
        ai_text = await _call_ai(provider, section_key, facts, fallback_text, output_language)
    except Exception:
        log.warning("Training report AI section '%s' failed — using deterministic fallback", section_key, exc_info=True)
        return fallback_text

    return ai_text or fallback_text


async def _call_ai(provider, section_key: str, facts: dict, fallback_text: str, output_language: str) -> Optional[str]:
    role = _SECTION_ROLE.get(section_key, "")
    lang_instruction = (
        "Write in formal Modern Standard Arabic. Keep system names, model numbers, project "
        "codes and dates exactly as given, in Latin characters, inside the Arabic sentence."
        if output_language == "ar"
        else "Write in formal British/International English."
    )
    system_prompt = (
        "You are drafting one section of an official Training Course Report for X-Ray "
        "cargo/baggage screening equipment, in the terminology and tone of this completed "
        f"reference report: \"{_STYLE_REFERENCE}\"\n\n"
        f"This section {role}.\n\n"
        "STRICT RULES:\n"
        "1. Use ONLY the facts given below. Never invent project codes, serial numbers, dates, "
        "attendee names, exam results, customer details or technical issues that are not given.\n"
        "2. If information needed for a natural sentence is missing, omit that clause instead of "
        "writing \"N/A\" or leaving a blank.\n"
        "3. Use correct singular/plural grammar.\n"
        "4. Output 1-3 sentences of plain prose only — no heading, no markdown, no bullet points, "
        "no preamble such as \"Here is...\".\n"
        f"5. {lang_instruction}\n\n"
        f"A deterministic version of this sentence (for reference; you may improve its phrasing "
        f"but must not add new facts) is:\n\"{fallback_text}\""
    )
    facts_lines = "\n".join(
        f"- {k}: {fmt_num(v) if isinstance(v, float) else v}"
        for k, v in facts.items() if v not in (None, "", [], {})
    )
    user_prompt = f"Facts for this section:\n{facts_lines}"

    raw = await provider.chat([{"role": "user", "content": user_prompt}], system_prompt=system_prompt)
    text = (raw or "").strip()
    if not text or len(text) > 1500:
        return None
    return text
