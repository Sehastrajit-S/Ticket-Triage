from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Ticket, TriageDecision
from app.db.session import get_session
from app.integrations.north_automation import get_orchestrator

router = APIRouter(prefix="/triage", tags=["triage"])


@router.post("/{ticket_id}/run")
async def run_triage_endpoint(ticket_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    orchestrator = get_orchestrator()
    result = await orchestrator.handle_new_ticket(session, ticket)
    return result.model_dump(mode="json")


@router.get("/{ticket_id}")
async def get_latest_triage(ticket_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    stmt = (
        select(TriageDecision)
        .where(TriageDecision.ticket_id == ticket_id)
        .order_by(TriageDecision.created_at.desc())
        .limit(1)
    )
    decision = (await session.execute(stmt)).scalar_one_or_none()
    if decision is None:
        raise HTTPException(status_code=404, detail="no triage decision for this ticket")
    return {
        "id": str(decision.id),
        "ticket_id": str(decision.ticket_id),
        "severity": decision.severity,
        "category": decision.category,
        "routed_team": decision.routed_team,
        "confidence": decision.confidence,
        "rationale": decision.rationale,
        "draft_response": decision.draft_response,
        "retrieved_doc_ids": decision.retrieved_doc_ids,
        "tool_trace": decision.tool_trace,
        "escalated": decision.escalated,
        "latency_ms": decision.latency_ms,
        "created_at": decision.created_at.isoformat(),
    }
