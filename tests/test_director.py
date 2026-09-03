import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent import director
from app.db.models import Ticket


def _tool_call(name: str, args: dict, call_id: str = "call_1"):
    return SimpleNamespace(id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args)))


@pytest.mark.asyncio
async def test_run_triage_happy_path_parses_final_json(monkeypatch):
    ticket = Ticket(subject="API down", body="everything is 503")
    ticket.id = uuid.uuid4()

    final_json = {
        "severity": "P1-critical",
        "category": "technical_bug",
        "routed_team": "engineering_support_escalation",
        "confidence": 0.9,
        "rationale": "outage",
        "draft_response": "We're on it.",
        "retrieved_doc_ids": ["doc-1"],
        "escalated": True,
    }

    # The director now refuses to accept a final answer until classify_ticket, route_ticket,
    # and draft_response have all actually been called — so the mocked sequence has to include
    # them, not just search_knowledge_base, to reach the final JSON step.
    responses = [
        SimpleNamespace(
            message=SimpleNamespace(
                tool_calls=[_tool_call("search_knowledge_base", {"query": "API down"})],
                tool_plan="searching",
            )
        ),
        SimpleNamespace(
            message=SimpleNamespace(
                tool_calls=[_tool_call("classify_ticket", {"subject": "API down", "body": "everything is 503"})],
                tool_plan=None,
            )
        ),
        SimpleNamespace(
            message=SimpleNamespace(
                tool_calls=[_tool_call("route_ticket", {"category": "technical_bug", "severity": "P1-critical"})],
                tool_plan=None,
            )
        ),
        SimpleNamespace(
            message=SimpleNamespace(
                tool_calls=[_tool_call("draft_response", {"subject": "API down", "body": "everything is 503"})],
                tool_plan=None,
            )
        ),
        SimpleNamespace(
            message=SimpleNamespace(tool_calls=None, content=[SimpleNamespace(text=json.dumps(final_json))])
        ),
    ]

    async def fake_chat(messages, tools=None, **kwargs):
        return responses.pop(0)

    async def fake_call_tool(session, tool_name, args, ticket_id=None):
        if tool_name == "search_knowledge_base":
            return {
                "results": [
                    {
                        "document_id": "doc-1",
                        "source_type": "runbook",
                        "title": "t",
                        "content": "c",
                        "relevance_score": 0.9,
                    }
                ]
            }
        return {"ok": True}

    session = AsyncMock()
    session.add = MagicMock()  # real AsyncSession.add() is synchronous

    monkeypatch.setattr(director, "chat", fake_chat)
    monkeypatch.setattr(director, "call_tool", fake_call_tool)

    result = await director.run_triage(session, ticket)

    assert result.severity.value == "P1-critical"
    assert result.category.value == "technical_bug"
    assert result.escalated is True
    assert "doc-1" in result.retrieved_doc_ids
    session.add.assert_called()  # TriageDecision persisted
    session.commit.assert_called()


@pytest.mark.asyncio
async def test_run_triage_falls_back_to_tool_trace_when_final_text_is_prose(monkeypatch):
    ticket = Ticket(subject="Question", body="how do I export data")
    ticket.id = uuid.uuid4()

    # Required tools (classify/route/draft) all run before the model's final response, which
    # this time is prose rather than JSON — exercising _fallback_from_tool_trace, which
    # reconstructs the result from the tools' own outputs instead of parsing the final text.
    responses = [
        SimpleNamespace(
            message=SimpleNamespace(
                tool_calls=[_tool_call("classify_ticket", {"subject": ticket.subject, "body": ticket.body})],
                tool_plan=None,
            )
        ),
        SimpleNamespace(
            message=SimpleNamespace(
                tool_calls=[_tool_call("route_ticket", {"category": "how_to", "severity": "P4-low"})],
                tool_plan=None,
            )
        ),
        SimpleNamespace(
            message=SimpleNamespace(
                tool_calls=[_tool_call("draft_response", {"subject": ticket.subject, "body": ticket.body})],
                tool_plan=None,
            )
        ),
        SimpleNamespace(
            message=SimpleNamespace(
                tool_calls=None,
                content=[SimpleNamespace(text="Sure, here's a plain-language summary, not JSON.")],
            )
        ),
    ]

    async def fake_chat(messages, tools=None, **kwargs):
        return responses.pop(0)

    async def fake_call_tool(session, tool_name, args, ticket_id=None):
        if tool_name == "classify_ticket":
            return {"severity": "P4-low", "category": "how_to", "confidence": 0.7, "rationale": "how-to question"}
        if tool_name == "route_ticket":
            return {"team": "general_support", "escalated": False, "reason": "default mapping"}
        if tool_name == "draft_response":
            return {"draft": "Here's how to export your data.", "cited_doc_ids": []}
        return {"ok": True}

    session = AsyncMock()
    session.add = MagicMock()  # real AsyncSession.add() is synchronous

    monkeypatch.setattr(director, "chat", fake_chat)
    monkeypatch.setattr(director, "call_tool", fake_call_tool)

    result = await director.run_triage(session, ticket)

    assert result.severity.value == "P4-low"
    assert result.category.value == "how_to"
    assert result.routed_team == "general_support"  # reconstructed from route_ticket's own output


@pytest.mark.asyncio
async def test_run_triage_stops_after_max_steps_without_infinite_loop(monkeypatch):
    ticket = Ticket(subject="loop test", body="always calls a tool")
    ticket.id = uuid.uuid4()

    async def fake_chat(messages, tools=None, **kwargs):
        if tools is not None:
            return SimpleNamespace(
                message=SimpleNamespace(
                    tool_calls=[_tool_call("search_knowledge_base", {"query": "x"})], tool_plan=None
                )
            )
        return SimpleNamespace(message=SimpleNamespace(tool_calls=None, content=[SimpleNamespace(text="{}")]))

    async def fake_call_tool(session, tool_name, args, ticket_id=None):
        return {"results": []}

    session = AsyncMock()
    session.add = MagicMock()  # real AsyncSession.add() is synchronous

    monkeypatch.setattr(director, "chat", fake_chat)
    monkeypatch.setattr(director, "call_tool", fake_call_tool)

    result = await director.run_triage(session, ticket)

    # Never got a final answer from the tool-enabled calls; the forced no-tools call closes it out.
    assert result.severity.value == "P3-medium"  # schema default when nothing was parsed
