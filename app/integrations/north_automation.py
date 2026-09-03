"""Stand-in for Cohere North Automations' 'intelligent workflow orchestration'.

In a real North deployment, a North Automation would be the thing wired to a
trigger (new Slack message, new email, webhook) that calls this triage agent,
then fans the result out to routing/escalation/response actions. Since North
itself is a hosted no-code product we can't provision here, `WorkflowOrchestrator`
reproduces that fan-out logic locally behind one interface — swap
`LocalWorkflowOrchestrator` for a thin webhook client once a real North
Automation exists, without touching the director or tools.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.director import run_triage
from app.agent.schemas import EscalateInput, TriageResult
from app.config import get_settings
from app.db.models import Ticket
from app.tools import escalate as escalate_tool

logger = logging.getLogger("integrations.north_automation")
settings = get_settings()


class WorkflowOrchestrator(ABC):
    """new ticket -> triage agent -> retrieve context -> route/escalate -> respond."""

    @abstractmethod
    async def handle_new_ticket(self, session: AsyncSession, ticket: Ticket) -> TriageResult: ...


class LocalWorkflowOrchestrator(WorkflowOrchestrator):
    async def handle_new_ticket(self, session: AsyncSession, ticket: Ticket) -> TriageResult:
        triage = await run_triage(session, ticket)

        # The director already calls escalate_ticket itself when routing says so; this is a
        # belt-and-suspenders notification in case the model's tool-use loop didn't get there,
        # matching what a North Automation's "on escalation" branch would guarantee. Only fire
        # it when the director's own tool trace shows escalate_ticket was never actually called,
        # otherwise this duplicates the notification on every single escalation.
        already_escalated = any(step.get("tool") == "escalate_ticket" for step in triage.tool_trace)
        if triage.escalated and not already_escalated:
            await escalate_tool.run(
                session,
                EscalateInput(
                    ticket_id=triage.ticket_id,
                    severity=triage.severity,
                    category=triage.category,
                    reason=f"Workflow orchestrator fallback escalation: {triage.rationale}",
                ).model_dump(mode="json"),
            )

        await self._notify_downstream(triage)
        return triage

    async def _notify_downstream(self, triage: TriageResult) -> None:
        """Best-effort fan-out to a real North Automations webhook, if one is configured."""
        if not settings.north_automations_webhook_url:
            logger.info(
                "north_automation.notify (stub, no webhook configured): %s",
                triage.model_dump(mode="json"),
            )
            return
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                await client.post(settings.north_automations_webhook_url, json=triage.model_dump(mode="json"))
        except httpx.HTTPError as exc:
            logger.warning("north_automation.notify webhook failed: %s", exc)


_orchestrator: WorkflowOrchestrator | None = None


def get_orchestrator() -> WorkflowOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = LocalWorkflowOrchestrator()
    return _orchestrator


__all__ = ["WorkflowOrchestrator", "LocalWorkflowOrchestrator", "get_orchestrator"]
