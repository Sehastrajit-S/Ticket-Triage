"""Stub Slack Events API receiver. Signature verification is real (HMAC over
the signing secret) but becomes a no-op until SLACK_SIGNING_SECRET is set, so
this endpoint is safe to leave mounted before a real Slack app exists.
"""

from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db.models import Ticket
from app.db.session import get_session
from app.integrations.north_automation import get_orchestrator
from app.integrations.slack_stub import parse_slack_event

router = APIRouter(prefix="/integrations/slack", tags=["slack"])
settings = get_settings()


def _verify_signature(body: bytes, timestamp: str, signature: str) -> bool:
    if not settings.slack_signing_secret:
        return True
    try:
        if abs(time.time() - float(timestamp)) > 60 * 5:
            return False
    except ValueError:
        return False
    basestring = f"v0:{timestamp}:{body.decode()}".encode()
    digest = hmac.new(settings.slack_signing_secret.encode(), basestring, hashlib.sha256).hexdigest()
    return hmac.compare_digest(f"v0={digest}", signature)


@router.post("/events")
async def slack_events(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    body = await request.body()
    payload = await request.json()

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}

    signature = request.headers.get("X-Slack-Signature", "")
    timestamp = request.headers.get("X-Slack-Request-Timestamp", "0")
    if not _verify_signature(body, timestamp, signature):
        raise HTTPException(status_code=401, detail="invalid Slack signature")

    ticket_input = parse_slack_event(payload)
    if ticket_input is None:
        return {"ok": True, "skipped": True}

    ticket = Ticket(
        subject=ticket_input.subject,
        body=ticket_input.body,
        customer_id=ticket_input.customer_id,
        channel=ticket_input.channel,
    )
    session.add(ticket)
    await session.commit()
    await session.refresh(ticket)

    orchestrator = get_orchestrator()
    await orchestrator.handle_new_ticket(session, ticket)
    return {"ok": True, "ticket_id": str(ticket.id)}
