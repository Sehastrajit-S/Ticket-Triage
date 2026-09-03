from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Feedback, TriageDecision
from app.db.session import get_session

router = APIRouter(prefix="/feedback", tags=["feedback"])


class FeedbackInput(BaseModel):
    triage_decision_id: uuid.UUID
    corrected_severity: str | None = None
    corrected_category: str | None = None
    corrected_team: str | None = None
    human_notes: str = ""


@router.post("", status_code=201)
async def submit_feedback(payload: FeedbackInput, session: AsyncSession = Depends(get_session)) -> dict:
    decision = await session.get(TriageDecision, payload.triage_decision_id)
    if decision is None:
        raise HTTPException(status_code=404, detail="triage decision not found")

    feedback = Feedback(
        triage_decision_id=payload.triage_decision_id,
        corrected_severity=payload.corrected_severity,
        corrected_category=payload.corrected_category,
        corrected_team=payload.corrected_team,
        human_notes=payload.human_notes,
    )
    session.add(feedback)
    await session.commit()
    await session.refresh(feedback)
    return {"id": str(feedback.id), "created_at": feedback.created_at.isoformat()}
