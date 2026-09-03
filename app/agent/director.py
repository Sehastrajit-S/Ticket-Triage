"""The Director agent: a Command A multi-step tool-use loop over the triage toolset.

This is the top of the tool-wise hierarchy — it doesn't implement any triage logic
itself, it only reasons about *which* tool to call next and interprets results,
delegating everything (retrieval, classification, routing, drafting, escalation)
to the tools in app/tools/.
"""

from __future__ import annotations

import json
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.prompts import SYSTEM_PROMPT
from app.agent.schemas import Category, Severity, TriageResult
from app.cohere_client.client import chat, extract_text
from app.db.models import Ticket, TriageDecision
from app.observability.tracing import traced
from app.tools.registry import ToolExecutionError, call_tool
from app.tools.schemas import TOOL_DEFINITIONS

_MAX_STEPS = 8
_REQUIRED_TOOLS = ("classify_ticket", "route_ticket", "draft_response")


@traced("director.run_triage")
async def run_triage(session: AsyncSession, ticket: Ticket) -> TriageResult:
    """Runs the full tool-use loop for one ticket and persists the resulting TriageDecision."""
    start = time.perf_counter()
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": f"New ticket (id={ticket.id}).\nSubject: {ticket.subject}\nBody: {ticket.body}",
        },
    ]

    tool_trace: list[dict[str, Any]] = []
    retrieved_doc_ids: set[str] = set()
    final_text = ""

    called_tools: set[str] = set()

    for _ in range(_MAX_STEPS):
        response = await chat(messages=messages, tools=TOOL_DEFINITIONS, temperature=0)
        tool_calls = getattr(response.message, "tool_calls", None) or []

        if not tool_calls:
            missing = [t for t in _REQUIRED_TOOLS if t not in called_tools]
            if missing:
                # The model stopped early. Nudge it to finish the required steps instead of
                # silently accepting a partial/empty result.
                messages.append({"role": "assistant", "content": extract_text(response)})
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "You have not finished the procedure yet. You still need to call: "
                            f"{', '.join(missing)}. Continue calling tools until all required "
                            "steps are done, then respond with the final JSON object only."
                        ),
                    }
                )
                continue
            final_text = extract_text(response)
            break

        messages.append(
            {
                "role": "assistant",
                "tool_calls": tool_calls,
                "tool_plan": getattr(response.message, "tool_plan", None),
            }
        )

        for tool_call in tool_calls:
            args = json.loads(tool_call.function.arguments or "{}")
            try:
                result = await call_tool(session, tool_call.function.name, args, ticket_id=ticket.id)
            except ToolExecutionError as exc:
                result = {"error": str(exc)}

            tool_trace.append({"tool": tool_call.function.name, "args": args, "result": result})
            called_tools.add(tool_call.function.name)
            if tool_call.function.name == "search_knowledge_base":
                retrieved_doc_ids.update(r["document_id"] for r in result.get("results", []))

            messages.append({"role": "tool", "tool_call_id": tool_call.id, "content": json.dumps(result)})
    else:
        # Exhausted the step budget without a bare-text final answer; force one.
        response = await chat(messages=messages, temperature=0)
        final_text = extract_text(response)

    triage = _finalize(final_text, ticket, tool_trace, retrieved_doc_ids)
    triage.latency_ms = int((time.perf_counter() - start) * 1000)

    decision = TriageDecision(
        ticket_id=ticket.id,
        severity=triage.severity.value,
        category=triage.category.value,
        routed_team=triage.routed_team,
        confidence=triage.confidence,
        rationale=triage.rationale,
        draft_response=triage.draft_response,
        retrieved_doc_ids=triage.retrieved_doc_ids,
        tool_trace=triage.tool_trace,
        escalated=triage.escalated,
        latency_ms=triage.latency_ms,
    )
    session.add(decision)
    await session.commit()

    return triage


def _finalize(
    final_text: str,
    ticket: Ticket,
    tool_trace: list[dict[str, Any]],
    retrieved_doc_ids: set[str],
) -> TriageResult:
    data = _try_parse_json(final_text) or _fallback_from_tool_trace(tool_trace)

    severity = Severity(data.get("severity") or Severity.P3_MEDIUM.value)
    category = Category(data.get("category") or Category.OTHER.value)
    doc_ids = data.get("retrieved_doc_ids") or list(retrieved_doc_ids)

    return TriageResult(
        ticket_id=str(ticket.id),
        severity=severity,
        category=category,
        routed_team=data.get("routed_team") or "general_support",
        confidence=float(data.get("confidence") or 0.5),
        rationale=data.get("rationale") or "",
        draft_response=data.get("draft_response") or "",
        retrieved_doc_ids=doc_ids,
        tool_trace=tool_trace,
        escalated=bool(data.get("escalated") or False),
    )


def _try_parse_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return None


def _fallback_from_tool_trace(tool_trace: list[dict[str, Any]]) -> dict[str, Any]:
    """If the model never emitted valid final JSON, reconstruct the result from raw tool outputs."""
    merged: dict[str, Any] = {}
    for entry in tool_trace:
        result = entry.get("result") or {}
        if entry["tool"] == "classify_ticket":
            merged.update(
                severity=result.get("severity"),
                category=result.get("category"),
                confidence=result.get("confidence"),
                rationale=result.get("rationale"),
            )
        elif entry["tool"] == "route_ticket":
            merged["routed_team"] = result.get("team")
            merged["escalated"] = result.get("escalated")
        elif entry["tool"] == "draft_response":
            merged["draft_response"] = result.get("draft")
            merged["retrieved_doc_ids"] = result.get("cited_doc_ids")
    return merged
