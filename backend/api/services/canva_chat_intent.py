"""
Canva intent detection for AI Chat — mirrors gallery_service.detect_intent's
keyword-pattern approach (no extra LLM call) so "Connect my Canva account",
"Show my Canva designs", "Open my Canva presentation", "Import a Canva
design", and "Disconnect Canva" are all recognized without the user
invoking a slash command or explicit tool.
"""
from __future__ import annotations

import re
from typing import Literal, Optional

_CANVA_MENTION_RE = re.compile(r"\bcanva\b|كانفا|كانڤا|كانفه", re.IGNORECASE)
_DISCONNECT_RE = re.compile(
    r"\b(disconnect|revoke|remove|unlink|sign\s*out\s+of)\b|افصل|الغاء\s*الربط|إلغاء\s*الربط|قطع\s*الاتصال",
    re.IGNORECASE,
)

CanvaChatAction = Literal["disconnect", "list_designs"]


def detect_canva_intent(message: str) -> Optional[CanvaChatAction]:
    """
    Returns "disconnect" for an explicit disconnect/revoke request, or
    "list_designs" for anything else Canva-related (connect / show designs /
    open a presentation / import a design) — listing designs with their real
    edit URLs is the one honest response to all of these without guessing
    which specific design free text refers to.
    """
    if not message or not _CANVA_MENTION_RE.search(message):
        return None
    if _DISCONNECT_RE.search(message):
        return "disconnect"
    return "list_designs"
