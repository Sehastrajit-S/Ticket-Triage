from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import PolicyCheckInput, PolicyCheckResult, Severity
from app.retrieval.search import search

_SLA_HOURS: dict[Severity, int] = {
    Severity.P1_CRITICAL: 1,
    Severity.P2_HIGH: 4,
    Severity.P3_MEDIUM: 24,
    Severity.P4_LOW: 72,
}


async def run(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    parsed = PolicyCheckInput.model_validate(args)
    query = f"SLA and escalation policy for {parsed.category.value} tickets at {parsed.severity.value} severity"
    chunks = await search(session, query, source_types=["policy", "runbook"], top_n=3)
    notes = "\n".join(f"- {c.title}: {c.content[:280]}" for c in chunks)
    result = PolicyCheckResult(
        sla_hours=_SLA_HOURS[parsed.severity],
        policy_notes=notes or "No specific policy document found; default SLA applies.",
        matched_doc_ids=[c.document_id for c in chunks],
    )
    return result.model_dump(mode="json")
