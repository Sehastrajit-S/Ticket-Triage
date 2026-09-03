import json
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.integrations import slack_stub
from app.tools import classify, draft_response, escalate, policy_check, route


@pytest.mark.asyncio
async def test_route_billing_default_no_escalation():
    result = await route.run(None, {"category": "billing", "severity": "P3-medium"})
    assert result["team"] == "billing_support"
    assert result["escalated"] is False


@pytest.mark.asyncio
async def test_route_p1_forces_escalation_suffix():
    result = await route.run(None, {"category": "technical_bug", "severity": "P1-critical"})
    assert result["escalated"] is True
    assert result["team"] == "engineering_support_escalation"


@pytest.mark.asyncio
async def test_route_security_always_escalates_without_suffix():
    result = await route.run(None, {"category": "security", "severity": "P4-low"})
    assert result["escalated"] is True
    assert result["team"] == "security_team"


@pytest.mark.asyncio
async def test_classify_parses_model_json(monkeypatch):
    fake_response = SimpleNamespace(
        message=SimpleNamespace(
            content=[
                SimpleNamespace(
                    text=json.dumps(
                        {
                            "severity": "P2-high",
                            "category": "billing",
                            "confidence": 0.8,
                            "rationale": "billing issue",
                        }
                    )
                )
            ]
        )
    )

    async def fake_chat(**kwargs):
        return fake_response

    monkeypatch.setattr(classify, "chat", fake_chat)

    result = await classify.run(None, {"subject": "Charged twice", "body": "please help"})
    assert result["severity"] == "P2-high"
    assert result["category"] == "billing"
    assert result["confidence"] == 0.8


@pytest.mark.asyncio
async def test_policy_check_uses_retrieval_and_sla_table(monkeypatch):
    from app.retrieval.search import RetrievedChunk

    async def fake_search(session, query, source_types=None, top_k=None, top_n=None):
        return [RetrievedChunk("doc-1", "policy", "SLA Policy", "P1 gets 1 hour", 0.9, {})]

    monkeypatch.setattr(policy_check, "search", fake_search)

    result = await policy_check.run(None, {"category": "security", "severity": "P1-critical"})
    assert result["sla_hours"] == 1
    assert "doc-1" in result["matched_doc_ids"]


@pytest.mark.asyncio
async def test_escalate_notifies_via_notifier(monkeypatch):
    notifier = slack_stub.LoggingNotifier()
    monkeypatch.setattr(escalate, "get_notifier", lambda: notifier)

    result = await escalate.run(
        None,
        {"ticket_id": "t-1", "severity": "P1-critical", "category": "security", "reason": "breach"},
    )
    assert result["notified"] is True
    assert len(notifier.sent_messages) == 1
    assert "t-1" in notifier.sent_messages[0]["text"]


@pytest.mark.asyncio
async def test_draft_response_grounds_reply_in_fetched_documents(monkeypatch):
    doc_id = uuid.uuid4()
    fake_doc = MagicMock()
    fake_doc.id = doc_id
    fake_doc.title = "Runbook"
    fake_doc.content = "Do X then Y"

    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = [fake_doc]

    session = AsyncMock()
    session.execute.return_value = fake_result

    fake_response = SimpleNamespace(message=SimpleNamespace(content=[SimpleNamespace(text="Please do X then Y.")]))

    async def fake_chat(**kwargs):
        return fake_response

    monkeypatch.setattr(draft_response, "chat", fake_chat)

    result = await draft_response.run(
        session,
        {"subject": "help", "body": "issue", "category": "technical_bug", "doc_ids": [str(doc_id)]},
    )
    assert result["draft"] == "Please do X then Y."
    assert str(doc_id) in result["cited_doc_ids"]


@pytest.mark.asyncio
async def test_draft_response_handles_no_context(monkeypatch):
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = []
    session = AsyncMock()
    session.execute.return_value = fake_result

    fake_response = SimpleNamespace(
        message=SimpleNamespace(content=[SimpleNamespace(text="A human agent will follow up shortly.")])
    )

    async def fake_chat(**kwargs):
        return fake_response

    monkeypatch.setattr(draft_response, "chat", fake_chat)

    result = await draft_response.run(
        session, {"subject": "help", "body": "issue", "category": "other", "doc_ids": []}
    )
    assert result["cited_doc_ids"] == []
    assert "follow up" in result["draft"]
