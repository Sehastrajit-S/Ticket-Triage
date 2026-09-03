from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import EscalateInput, EscalateResult
from app.config import get_settings
from app.integrations.slack_stub import get_notifier

settings = get_settings()


async def run(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    parsed = EscalateInput.model_validate(args)
    notifier = get_notifier()
    text = (
        f":rotating_light: Escalation — ticket {parsed.ticket_id}\n"
        f"Severity: {parsed.severity.value} | Category: {parsed.category.value}\n"
        f"Reason: {parsed.reason}"
    )
    delivered = await notifier.notify(
        settings.slack_escalation_channel, text, metadata={"ticket_id": parsed.ticket_id}
    )
    result = EscalateResult(notified=delivered, channel=settings.slack_escalation_channel)
    return result.model_dump(mode="json")
