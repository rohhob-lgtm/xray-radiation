"""Gemini function-calling agent loop for the AI Chat Workspace.

Runs entirely inside the existing ``/api/chat/stream`` SSE request — no
separate job queue (see plan's Scope decision #1). Emits a stream of typed
event dicts that ``api.routes.chat`` forwards as SSE messages, while also
persisting a ``WorkspaceTask``/``TaskEvent`` audit trail so the Workspace
panel can show history even if the SSE connection drops.

No hidden chain-of-thought is ever emitted — only short stage/tool labels.
"""
from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from sqlalchemy.orm import Session

from api.config import settings
from api.db import crud
from api.db.models import Conversation, Workspace

from .tools import ALL_TOOL_NAMES, TOOL_SCHEMAS, WorkspaceToolContext, execute_tool

log = logging.getLogger(__name__)

_GENERATOR_TOOLS = {
    "create_excel_workbook", "create_csv", "create_word_document",
    "create_powerpoint", "create_pdf_report", "create_markdown_report",
    "write_generated_file", "translate_document",
}

_SYSTEM_PROMPT_TEMPLATE = """You are the X-Ray Research Innovation Platform's workspace agent — similar to \
Claude Code, but for a folder of documents the user uploaded. Use the provided tools to inspect files, \
search the workspace, translate content, and generate downloadable deliverables (Excel, Word, \
PowerPoint, PDF, CSV, JSON, Markdown, TXT).

Rules:
- Never invent facts about files you have not read — use the tools to inspect content first.
- Prefer search_workspace to locate relevant material before reading every file.
- When asked to produce a deliverable, actually call the matching create_*/write_generated_file/\
translate_document tool — do not just describe what the file would contain.
- A failed or unsupported file should be reported as a warning, not treated as a reason to stop.
- Keep your final answer concise: what was analyzed, key findings, actions completed, warnings or \
failed files, and the generated files (reference them by filename — the UI renders download buttons \
separately, so do not include raw links).
- Never reveal step-by-step internal reasoning or chain-of-thought — only results and short status.

Workspace: {workspace_name} ({file_count} files)
Files (top-level; use list_workspace_files/get_workspace_tree/search_workspace for the rest):
{tree_summary}
"""


def _summarize_tree(files: list) -> str:
    lines = [f"- {f.relative_path} ({f.parse_status}, {f.size_bytes} bytes)" for f in files[:60]]
    if len(files) > 60:
        lines.append(f"... and {len(files) - 60} more files (use list_workspace_files/search_workspace)")
    return "\n".join(lines) or "(empty workspace)"


def _summarize_json(obj: Any, limit: int) -> str:
    try:
        s = json.dumps(obj, default=str)
    except Exception:
        s = str(obj)
    return s[:limit]


async def _record_task_timeline_event(
    db: Session, workspace: Workspace, conversation: Conversation, task, status: str, user_message: str,
) -> None:
    """
    Cognitive Layer (Phase 2): Project Timeline real wiring — a workspace
    agent run reaching a terminal state is exactly the kind of "important
    event" the timeline is for. No-op for anonymous scopes (workspace
    actions already require auth, so this is always a real user).
    """
    if not workspace.user_id:
        return
    from api.services import timeline_service
    from api.services.identity import MemoryScope
    scope = MemoryScope(user_id=workspace.user_id, anon_session_id=None, is_persistent=True)
    try:
        await timeline_service.record_event(
            db, scope, module="workspace", event_type=status,
            title=f"Workspace task {status}: {user_message[:80]}",
            description=task.result_summary or user_message,
            source_ref=task.id,
            related_entity=("project", workspace.id),
        )
    except Exception:
        log.exception("Timeline event recording failed for workspace task %s", task.id)


async def run_workspace_turn(
    db: Session,
    workspace: Workspace,
    conversation: Conversation,
    user_message: str,
    history: list[dict],
    provider: Any,
    model_name: str,
) -> AsyncIterator[dict]:
    """Async generator of event dicts:

        {"type": "stage", "stage": ..., "message": ...}
        {"type": "tool_call", "tool": ..., "args_summary": ...}
        {"type": "tool_result", "tool": ..., "ok": bool}
        {"type": "chunk", "chunk": str}                       # visible answer text
        {"type": "error", "error": str}
        {"type": "done", "content": str, "task_id": str, "status": str, "generated_files": [...]}

    ``content`` on the "done" event is what the caller should persist as the
    saved assistant Message (includes a machine-readable generated-files
    trailer, parsed by the frontend the same way __GALLERY__: already is).
    """
    if not hasattr(provider, "chat_with_tools"):
        yield {
            "type": "error",
            "error": "The active AI provider does not support the workspace agent (tool calling). "
                     "Switch to Gemini in Settings to use file/folder workspaces.",
        }
        return

    files = crud.list_workspace_files(db, workspace.id)
    task = crud.create_task(db, workspace.id, user_message, conversation_id=conversation.id)
    crud.update_task_status(db, task.id, "analyzing")

    def log_event(event_type: str, message: str, payload: dict | None = None) -> None:
        crud.append_task_event(db, task.id, event_type, message, payload)

    yield {"type": "stage", "stage": "understanding", "message": "Understanding request"}
    log_event("stage", "Understanding request")

    yield {"type": "stage", "stage": "inspecting", "message": "Inspecting workspace"}
    log_event("stage", "Inspecting workspace", {"file_count": len(files)})

    system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
        workspace_name=workspace.name, file_count=len(files), tree_summary=_summarize_tree(files),
    )
    messages: list[dict] = list(history) + [{"role": "user", "content": user_message}]
    ctx = WorkspaceToolContext(db=db, workspace=workspace, provider=provider, model_name=model_name)

    generated_files: list[dict] = []
    any_tool_error = False
    max_calls = settings.max_agent_tool_calls_per_turn
    call_count = 0
    plan_emitted = False
    final_text = ""
    zero_call_retry_used = False

    yield {"type": "stage", "stage": "planning", "message": "Planning task"}
    log_event("stage", "Planning task")

    try:
        while call_count < max_calls:
            message = await provider.chat_with_tools(messages, TOOL_SCHEMAS, system_prompt=system_prompt)

            if not plan_emitted:
                plan_emitted = True
                yield {"type": "stage", "stage": "processing", "message": "Processing files"}
                log_event("stage", "Processing files")

            tool_calls = getattr(message, "tool_calls", None) or []
            if not tool_calls:
                # A turn that never calls a single tool is exactly how the
                # model has been observed to narrate a fabricated "success"
                # (invented filename, no real translate_document/create_*
                # call, no GeneratedFile row, no file on disk). Force one
                # corrective re-prompt before accepting a no-tool-call answer
                # as final, instead of trusting the model's own claim.
                if call_count == 0 and not zero_call_retry_used:
                    zero_call_retry_used = True
                    messages.append({"role": "assistant", "content": message.content or ""})
                    messages.append({
                        "role": "user",
                        "content": (
                            "You did not call a tool. If the user's request genuinely requires "
                            "a deliverable (a translated or generated file), call the matching "
                            "tool now. Otherwise, just answer the user's message directly and "
                            "naturally, the way a normal assistant would — do not mention "
                            "tools, files, or whether a tool was or was not called."
                        ),
                    })
                    log_event("stage", "No tool call detected — requesting corrective retry")
                    continue
                final_text = message.content or ""
                break

            messages.append({
                "role": "assistant",
                "content": message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id, "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                        # Gemini 3.x requires echoing back each function call's
                        # thought_signature on the next turn (400 INVALID_ARGUMENT
                        # otherwise) — surfaced via the OpenAI-compat endpoint as
                        # this vendor extension field on the tool call object.
                        **({"extra_content": tc.extra_content} if getattr(tc, "extra_content", None) else {}),
                    }
                    for tc in tool_calls
                ],
            })

            for tc in tool_calls:
                if call_count >= max_calls:
                    break
                call_count += 1
                tool_name = tc.function.name
                try:
                    args = json.loads(tc.function.arguments or "{}")
                except json.JSONDecodeError:
                    args = {}

                yield {"type": "tool_call", "tool": tool_name, "args_summary": _summarize_json(args, 200)}
                log_event("tool_call", f"Calling {tool_name}", {"args": args})

                if tool_name not in ALL_TOOL_NAMES:
                    result = {"error": f"Unknown tool '{tool_name}'"}
                else:
                    result = await execute_tool(ctx, tool_name, args)

                had_error = "error" in result
                any_tool_error = any_tool_error or had_error
                if tool_name in _GENERATOR_TOOLS and not had_error and "id" in result:
                    generated_files.append(result)

                yield {"type": "tool_result", "tool": tool_name, "ok": not had_error}
                log_event(
                    "tool_result",
                    f"{tool_name} {'failed' if had_error else 'completed'}",
                    {"result_summary": _summarize_json(result, 300)},
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": _summarize_json(result, 8000),
                })
        else:
            final_text = (
                "Reached the maximum number of tool calls allowed for a single turn "
                f"({max_calls}). Here is what was completed so far — ask a follow-up to continue."
            )
    except Exception as exc:
        log.exception("Workspace agent loop failed for task %s", task.id)
        crud.update_task_status(db, task.id, "failed", result_summary=str(exc))
        await _record_task_timeline_event(db, workspace, conversation, task, "failed", user_message)
        yield {"type": "error", "error": f"Workspace agent failed: {exc}"}
        return

    yield {"type": "stage", "stage": "validating", "message": "Validating output"}
    log_event("stage", "Validating output")

    status = "completed_with_warnings" if any_tool_error else "completed"
    crud.update_task_status(db, task.id, status, result_summary=final_text[:4000])
    await _record_task_timeline_event(db, workspace, conversation, task, status, user_message)

    yield {"type": "stage", "stage": "completed", "message": "Completed"}
    log_event("stage", "Completed")

    yield {"type": "chunk", "chunk": final_text}

    trailer = f"\n\n__GENERATED_FILES__:{json.dumps(generated_files, default=str)}" if generated_files else ""
    yield {
        "type": "done",
        "content": final_text + trailer,
        "task_id": task.id,
        "status": status,
        "generated_files": generated_files,
    }
