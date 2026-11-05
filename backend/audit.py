"""Append-only audit trail: one JSON object per line in output/audit_trail.json.

Every agent-loop step (model request, model response with tool calls, final output) and every
delegation is appended. The file is never truncated or rewritten.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)

from backend.config import AUDIT_TEXT_LIMIT, AUDIT_TRAIL_PATH, MODEL_NAME


def _clip(value: Any) -> Any:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text if len(text) <= AUDIT_TEXT_LIMIT else text[:AUDIT_TEXT_LIMIT] + f"... [{len(text)} chars]"


def message_parts(message: ModelRequest | ModelResponse) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for part in message.parts:
        if isinstance(part, UserPromptPart):
            out.append({"kind": "user_prompt", "content": _clip(part.content)})
        elif isinstance(part, ToolCallPart):
            out.append({"kind": "tool_call", "tool": part.tool_name, "args": part.args_as_dict(),
                        "tool_call_id": part.tool_call_id})
        elif isinstance(part, ToolReturnPart):
            out.append({"kind": "tool_return", "tool": part.tool_name, "content": _clip(part.content),
                        "tool_call_id": part.tool_call_id})
        elif isinstance(part, RetryPromptPart):
            out.append({"kind": "retry", "tool": part.tool_name, "content": _clip(part.content)})
        elif isinstance(part, TextPart):
            out.append({"kind": "text", "content": _clip(part.content)})
        elif isinstance(part, ThinkingPart):
            out.append({"kind": "thinking", "chars": len(part.content or "")})
    return out


def record(event: str, *, run_id: str, ticket_id: int | None, agent: str, depth: int, **data: Any) -> None:
    """Append one event line. Never raises: a failed audit write must not crash a run silently,
    so the error is printed instead."""
    line = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "run_id": run_id,
        "ticket_id": ticket_id,
        "agent": agent,
        "depth": depth,
        "model": MODEL_NAME,
        "event": event,
        **data,
    }
    try:
        AUDIT_TRAIL_PATH.parent.mkdir(parents=True, exist_ok=True)
        with AUDIT_TRAIL_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")
    except OSError as exc:
        print(f"[audit] could not write {AUDIT_TRAIL_PATH}: {exc}")

