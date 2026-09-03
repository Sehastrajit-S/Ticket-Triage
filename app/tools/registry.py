"""Single dispatch point from tool name -> implementation, shared by the director loop and eval harness.

Every call is timed, span-wrapped, and written to AuditLog here so tool-success-rate and
latency metrics have one authoritative source regardless of which caller invoked the tool.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog
from app.observability.tracing import tracer
from app.tools import classify, draft_response, escalate, policy_check, route, search_kb

ToolFn = Callable[[AsyncSession, dict[str, Any]], Awaitable[dict[str, Any]]]

_TOOL_IMPLS: dict[str, ToolFn] = {
    "search_knowledge_base": search_kb.run,
    "classify_ticket": classify.run,
    "check_policy": policy_check.run,
    "route_ticket": route.run,
    "draft_response": draft_response.run,
    "escalate_ticket": escalate.run,
}

TOOL_NAMES: list[str] = list(_TOOL_IMPLS.keys())


class ToolExecutionError(Exception):
    def __init__(self, tool_name: str, original: Exception) -> None:
        super().__init__(f"tool '{tool_name}' failed: {original}")
        self.tool_name = tool_name
        self.original = original


async def call_tool(
    session: AsyncSession,
    tool_name: str,
    args: dict[str, Any],
    ticket_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    """Executes one tool by name, logging an AuditLog row regardless of outcome."""
    impl = _TOOL_IMPLS.get(tool_name)
    if impl is None:
        raise ToolExecutionError(tool_name, ValueError(f"unknown tool '{tool_name}'"))

    start = time.perf_counter()
    success = True
    error_message: str | None = None
    result: dict[str, Any] = {}

    with tracer.start_as_current_span(f"tool.{tool_name}"):
        try:
            result = await impl(session, args)
        except Exception as exc:  # noqa: BLE001 - captured for the audit trail, then re-raised
            success = False
            error_message = str(exc)
            raise ToolExecutionError(tool_name, exc) from exc
        finally:
            latency_ms = int((time.perf_counter() - start) * 1000)
            session.add(
                AuditLog(
                    ticket_id=ticket_id,
                    event_type="tool_call",
                    tool_name=tool_name,
                    payload={"args": args, "result": result, "error": error_message},
                    success=success,
                    latency_ms=latency_ms,
                )
            )
            await session.commit()

    return result
