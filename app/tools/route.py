from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import (
    DEFAULT_CATEGORY_TEAM_MAP,
    ESCALATION_CATEGORIES,
    ESCALATION_SEVERITIES,
    RouteInput,
    RouteResult,
)


async def run(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    parsed = RouteInput.model_validate(args)
    team = DEFAULT_CATEGORY_TEAM_MAP[parsed.category]
    must_escalate = parsed.severity in ESCALATION_SEVERITIES or parsed.category in ESCALATION_CATEGORIES

    if must_escalate:
        reason = (
            f"{parsed.severity.value} severity requires immediate escalation"
            if parsed.severity in ESCALATION_SEVERITIES
            else f"{parsed.category.value} tickets are always escalated regardless of severity"
        )
        if parsed.category not in ESCALATION_CATEGORIES:
            team = f"{team}_escalation"
    else:
        reason = f"Routed by default category mapping for {parsed.category.value}"

    result = RouteResult(team=team, escalated=must_escalate, reason=reason)
    return result.model_dump(mode="json")
