"""North MCP tool server for the ticket-triage tools.

This exposes the exact same tools app/agent/director.py calls internally
(search_knowledge_base, classify_ticket, check_policy, route_ticket,
draft_response, escalate_ticket) as a standalone MCP server, built on
Cohere's own north-mcp-python-sdk (https://github.com/cohere-ai/north-mcp-python-sdk).

Why this file exists: director.py is OUR orchestrator, standing in for what a
real North Automation would do since we don't have North access to test
against. This file is the other half — instead of us deciding which tool to
call next, it lets North's own agent runtime be the orchestrator and call out
to these tools directly, which is the actual, supported extension point North
provides for custom capabilities. Register this server's URL with North and
director.py's tool-use loop becomes optional (a standalone/offline mode) —
North calls the same tools instead.

Run standalone:
    python mcp_server.py

Then point a North Automation (or the SDK's own examples/client.py, for local
testing without North) at http://<host>:<port>/mcp.
"""

from __future__ import annotations

from typing import Any

from north_mcp_python_sdk import NorthMCPServer

from app.config import get_settings
from app.db.session import AsyncSessionLocal
from app.tools import classify, escalate, policy_check, route, search_kb
from app.tools import draft_response as draft_response_tool

settings = get_settings()

_trusted_issuers = [i.strip() for i in settings.north_mcp_trusted_issuers.split(",") if i.strip()] or None

mcp = NorthMCPServer(
    "Ticket Triage",
    trusted_issuers=_trusted_issuers,
    debug=settings.app_env == "local",
)


@mcp.tool()
async def search_knowledge_base(
    query: str,
    source_types: list[str] | None = None,
    top_n: int | None = None,
) -> list[dict[str, Any]]:
    """Semantic search over past resolved tickets, KB articles, runbooks, and policy docs
    (Embed v4 + Rerank 4). Use before classifying or drafting a reply to ground the answer
    in real precedent. source_types filters to any of: ticket, kb, runbook, policy."""
    async with AsyncSessionLocal() as session:
        result = await search_kb.run(session, {"query": query, "source_types": source_types, "top_n": top_n})
    return [
        {
            "document_id": r["document_id"],
            "source_type": r["source_type"],
            "title": r["title"],
            "text": r["content"],
            "relevance_score": r["relevance_score"],
            # North's UI renders tool results carrying this field as citation cards.
            "_north_metadata": {
                "renderer": "document",
                "content": r["content"],
                "title": r["title"],
                "meta": {"source_type": r["source_type"], "document_id": r["document_id"]},
            },
        }
        for r in result["results"]
    ]


@mcp.tool()
async def classify_ticket(subject: str, body: str) -> dict[str, Any]:
    """Classify a ticket's severity (P1-critical, P2-high, P3-medium, or P4-low) and category
    using its subject and body."""
    async with AsyncSessionLocal() as session:
        return await classify.run(session, {"subject": subject, "body": body})


@mcp.tool()
async def check_policy(category: str, severity: str) -> dict[str, Any]:
    """Look up the SLA and escalation policy that applies to a given category+severity."""
    async with AsyncSessionLocal() as session:
        return await policy_check.run(session, {"category": category, "severity": severity})


@mcp.tool()
async def route_ticket(category: str, severity: str) -> dict[str, Any]:
    """Decide which team a ticket should be routed to, and whether it must be escalated."""
    async with AsyncSessionLocal() as session:
        return await route.run(session, {"category": category, "severity": severity})


@mcp.tool()
async def draft_response(
    subject: str,
    body: str,
    category: str,
    doc_ids: list[str] | None = None,
) -> dict[str, Any]:
    """Draft a customer-facing reply grounded ONLY in the documents named by doc_ids, using
    Cohere's native grounded generation (real span-level citations, not invented ones). Pass
    the doc_ids returned by search_knowledge_base — do not invent ids."""
    async with AsyncSessionLocal() as session:
        return await draft_response_tool.run(
            session,
            {"subject": subject, "body": body, "category": category, "doc_ids": doc_ids or []},
        )


@mcp.tool()
async def escalate_ticket(ticket_id: str, severity: str, category: str, reason: str) -> dict[str, Any]:
    """Notify the on-call channel about a ticket needing immediate human attention."""
    async with AsyncSessionLocal() as session:
        return await escalate.run(
            session,
            {"ticket_id": ticket_id, "severity": severity, "category": category, "reason": reason},
        )


if __name__ == "__main__":
    print(f"Starting Ticket Triage North MCP server on port {settings.north_mcp_port}...")
    if not _trusted_issuers:
        print("WARNING: NORTH_MCP_TRUSTED_ISSUERS is unset — tokens are decoded but not signature-")
        print("verified. Fine for local dev; set it before registering this server with real North.")
    mcp.run(transport="streamable-http", port=settings.north_mcp_port)
