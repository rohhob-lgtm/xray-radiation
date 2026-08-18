"""
Tool Router between the AI Chat and the Enterprise Connector Framework.

Every enabled connector's implemented (and declared-but-not-yet-implemented,
so intent is still recognized honestly) capabilities are offered to the LLM
as OpenAI-style function tools on each chat turn. The model itself decides
whether the user's message needs a tool call — this is genuine LLM-driven
routing, not keyword matching. Requires the active AI provider to support
`chat_with_tools` (currently Gemini via its OpenAI-compatibility endpoint);
callers should fall back to a simpler heuristic when it doesn't.

Reuses the exact SSE progress-event shapes (`stage`/`tool_call`/`tool_result`)
the AI Chat Workspace agent already emits, and the exact result-payload
shapes (`canva_designs`/`canva_connect_required`/`canva_error`) the frontend
already renders — no new frontend work needed for either.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional

from sqlalchemy.orm import Session

from api.db import crud
from api.services.connectors.base import ConnectorActionResult
from api.services.connectors.registry import connector_registry
from api.services.connectors.service import connector_service

log = logging.getLogger(__name__)

_MAX_TOOL_CALLS_PER_TURN = 3

_SYSTEM_PROMPT = (
    "You can access the user's connected external platforms (such as Canva) "
    "through tools. Call the matching tool whenever the user's request concerns "
    "one of those platforms — listing, searching, opening, or creating something "
    "there — even if they don't name the tool explicitly. For anything else, do "
    "not call a tool; just answer normally."
)

# Regression fix — a plain research question ("what's the newest baggage
# X-ray scanning technology?") was reaching the LLM tool-decision call above
# and getting misrouted to the Google Drive connector, because the prompt
# above deliberately tells the model to call a tool "even if they don't name
# the tool explicitly" (a reasonable instruction for genuinely ambiguous
# platform requests, wrong for a request that has nothing to do with any
# connected platform at all). detect_connector_tool_intent() is a
# deterministic pre-gate — run_connector_tool_loop (and its real LLM call)
# is now only invoked when the message plausibly references a connected
# platform by name or a generic file-storage/sync action, so an unrelated
# research question never reaches the tool-decision call in the first place.
_GENERIC_CONNECTOR_ACTION_RE = re.compile(
    r"\b(upload|download|sync|synchroniz\w*)\b|"
    r"\bconnect(?:ed)?\s+(?:my\s+)?account\b|"
    # "drive" as its own word (not e.g. "hard drive"/"drive a car") — in
    # this platform's chat context it means Google Drive specifically. The
    # target must be drive/cloud-storage-shaped, never an arbitrary word
    # (that would also match "the document in my workspace", which belongs
    # to the Workspace Agent's own file-reference detection, not this gate).
    r"\bdrive\s+(?:files?|documents?)\b|\b(?:files?|documents?)\s+(?:stored\s+)?(?:in|on|from)\s+(?:my\s+)?drive\b|\bmy\s+drive\b|"
    r"رفع|تحميل|مزامنة|زامن|اربط\s+حسابي|درايف|قوقل\s+درايف|جوجل\s+درايف",
    re.IGNORECASE,
)


def detect_connector_tool_intent(message: str) -> bool:
    """True only when `message` plausibly concerns a connected external
    platform (mentioned by name) or a generic upload/download/sync/file-
    storage action — the deterministic gate that decides whether
    run_connector_tool_loop's real LLM tool-decision call is even worth
    making this turn. False for everything else, including ordinary
    research/knowledge questions, so they fall through to the plain-text
    chat path (Knowledge Router / Expert Reasoning) instead.

    Matches against every REGISTERED connector's display name/provider slug
    (connector_registry.list_registered_providers() — the platform's full
    catalog, e.g. "Google Drive", "Canva", "Dropbox", "OneDrive", "Slack"),
    not just ones a given user has already enabled/connected — a user
    saying "connect my Google Drive" for the first time must still be
    recognized, not silently answered as a plain chat message. Per-user
    connection status is checked downstream inside run_connector_tool_loop
    itself (returning a connect_required payload when not yet connected),
    which this gate does not need to duplicate."""
    if not message:
        return False
    if _GENERIC_CONNECTOR_ACTION_RE.search(message):
        return True
    lowered = message.lower()
    for provider in connector_registry.list_registered_providers():
        connector = connector_registry.get(provider)
        display_name = connector.manifest.display_name.lower()
        provider_as_words = provider.replace("_", " ")
        if display_name in lowered or provider_as_words in lowered:
            return True
    return False


def _to_tool_name(action: str) -> str:
    """'canva.list_designs' -> 'canva_list_designs' (OpenAI tool names disallow '.')."""
    return action.replace(".", "_").replace("-", "_")


def _json_schema_for(parameters_schema: dict) -> dict:
    properties: dict[str, Any] = {}
    required: list[str] = []
    for field_name, spec in (parameters_schema or {}).items():
        prop: dict[str, Any] = {
            "type": spec.get("type", "string"),
            "description": spec.get("description", ""),
        }
        if spec.get("enum"):
            prop["enum"] = spec["enum"]
        properties[field_name] = prop
        if spec.get("required"):
            required.append(field_name)
    return {"type": "object", "properties": properties, "required": required}


def build_tool_schemas(db: Session) -> tuple[list[dict], dict[str, tuple[str, str]]]:
    """
    Returns (openai_tool_schemas, tool_name -> (provider, action)) for every
    enabled + registered connector's declared capabilities.
    """
    schemas: list[dict] = []
    tool_map: dict[str, tuple[str, str]] = {}
    for row in crud.list_connectors(db):
        if not row.enabled or not connector_registry.is_registered(row.provider):
            continue
        connector = connector_registry.get(row.provider)
        for cap in connector.manifest.capabilities:
            tool_name = _to_tool_name(cap.action)
            description = cap.description
            if not cap.is_implemented:
                description += " (not implemented yet — calling this will report that honestly)"
            schemas.append({
                "type": "function",
                "function": {
                    "name": tool_name,
                    "description": description,
                    "parameters": _json_schema_for(cap.parameters_schema),
                },
            })
            tool_map[tool_name] = (row.provider, cap.action)
    return schemas, tool_map


def _loading_message(action: str) -> str:
    verb = action.split(".", 1)[1] if "." in action else action
    return {
        "list_designs": "Loading designs...",
        "get_design": "Loading design...",
        "open_design": "Loading design...",
        "get_profile": "Loading profile...",
        "create_design": "Creating design...",
    }.get(verb, f"Running {verb}...")


def _build_result_payload(provider: str, action: str, result: ConnectorActionResult) -> Optional[dict]:
    """Maps a connector action result onto the existing __CANVA__ SSE payload
    shapes the frontend already knows how to render (CanvaResultsCard)."""
    if not result.success:
        return {"type": f"{provider}_error", "error_code": result.error_code, "error_message": result.error_message}

    data = result.data or {}
    if action.endswith(".list_designs"):
        return {"type": "canva_designs", "items": data.get("items", [])}
    if action.endswith(".get_design") or action.endswith(".open_design"):
        design = data.get("design") or data
        return {"type": "canva_designs", "items": [design] if design else []}
    return None  # e.g. get_profile — no dedicated card; caller falls back to a text summary


def _summarize_for_model(result: ConnectorActionResult) -> dict:
    """Trimmed tool-result content fed back to the LLM (not the chat UI)."""
    if not result.success:
        return {"error_code": result.error_code, "error_message": result.error_message}
    data = result.data or {}
    if isinstance(data, dict) and "items" in data and isinstance(data["items"], list):
        # Drop long thumbnail/edit-url payloads from what the model re-reads —
        # it only needs enough to reason about titles/ids, not full URLs.
        trimmed = [
            {"id": item.get("id"), "title": item.get("title"), "updated_at": item.get("updated_at")}
            for item in data["items"][:25] if isinstance(item, dict)
        ]
        return {"items": trimmed, "count": len(data["items"])}
    return data


async def run_connector_tool_loop(
    db: Session, user_id: str, messages: list[dict], provider: Any,
) -> tuple[Optional[dict], list[dict]]:
    """
    Runs the LLM tool-decision loop for one chat turn.

    Returns (result_payload, progress_events):
      - (None, []) means no tool was needed this turn — caller should fall
        through to a normal text-chat reply.
      - Otherwise result_payload is one of the existing __CANVA__ SSE payload
        shapes (or None if the tool used has no dedicated card, e.g.
        get_profile) and progress_events is the ordered list of
        stage/tool_call/tool_result events to yield before it.
    """
    if not hasattr(provider, "chat_with_tools"):
        return None, []

    tool_schemas, tool_map = build_tool_schemas(db)
    if not tool_schemas:
        return None, []

    working_messages = list(messages)
    progress: list[dict] = []
    call_count = 0
    final_payload: Optional[dict] = None
    used_any_tool = False

    while call_count < _MAX_TOOL_CALLS_PER_TURN:
        try:
            msg = await provider.chat_with_tools(working_messages, tool_schemas, system_prompt=_SYSTEM_PROMPT)
        except Exception:
            log.exception("Connector tool-routing decision call failed")
            break

        tool_calls = getattr(msg, "tool_calls", None) or []
        if not tool_calls:
            break

        used_any_tool = True
        working_messages.append({
            "role": "assistant",
            "content": msg.content or "",
            "tool_calls": [
                {
                    "id": tc.id, "type": "function",
                    "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    **({"extra_content": tc.extra_content} if getattr(tc, "extra_content", None) else {}),
                }
                for tc in tool_calls
            ],
        })

        stop_loop = False
        for tc in tool_calls:
            if call_count >= _MAX_TOOL_CALLS_PER_TURN:
                break
            call_count += 1
            tool_name = tc.function.name
            provider_action = tool_map.get(tool_name)
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}

            if not provider_action:
                working_messages.append({
                    "role": "tool", "tool_call_id": tc.id,
                    "content": json.dumps({"error": f"Unknown tool '{tool_name}'"}),
                })
                continue

            conn_provider, action = provider_action
            display_name = conn_provider.replace("_", " ").title()
            progress.append({"type": "stage", "stage": "using_connector", "message": f"Using {display_name} Connector..."})
            progress.append({"type": "tool_call", "tool": tool_name, "args_summary": json.dumps(args)[:200]})

            connector = connector_registry.get(conn_provider)
            status = await connector.get_connection_status(db, user_id)
            if status.connection_status != "connected":
                progress.append({"type": "tool_result", "tool": tool_name, "ok": False})
                final_payload = {
                    "type": f"{conn_provider}_connect_required",
                    "connect_url": f"/api/connectors/{conn_provider}/connect",
                }
                stop_loop = True
                break

            progress.append({"type": "stage", "stage": "loading", "message": _loading_message(action)})
            result = await connector_service.execute_action(db, user_id, conn_provider, action, args)
            progress.append({"type": "tool_result", "tool": tool_name, "ok": result.success})

            final_payload = _build_result_payload(conn_provider, action, result)
            working_messages.append({
                "role": "tool", "tool_call_id": tc.id,
                "content": json.dumps(_summarize_for_model(result))[:4000],
            })

        if stop_loop:
            break

    if not used_any_tool:
        return None, []

    progress.append({"type": "stage", "stage": "completed", "message": "Completed."})
    return final_payload, progress
