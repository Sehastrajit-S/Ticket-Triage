from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import TicketInput
from app.db.models import Ticket
from app.db.session import get_session

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.post("", status_code=201)
async def create_ticket(payload: TicketInput, session: AsyncSession = Depends(get_session)) -> dict:
    ticket = Ticket(
        subject=payload.subject,
        body=payload.body,
        customer_id=payload.customer_id,
        channel=payload.channel,
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)
    return {"id": str(ticket.id), "status": ticket.status, "created_at": ticket.created_at.isoformat()}


@router.get("/{ticket_id}")
async def get_ticket(ticket_id: uuid.UUID, session: AsyncSession = Depends(get_session)) -> dict:
    ticket = await session.get(Ticket, ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="ticket not found")
    return {
        "id": str(ticket.id),
        "subject": ticket.subject,
        "body": ticket.body,
        "customer_id": ticket.customer_id,
        "channel": ticket.channel,
        "status": ticket.status,
        "created_at": ticket.created_at.isoformat(),
    }
