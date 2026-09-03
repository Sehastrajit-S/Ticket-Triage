from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import Category, ClassifyInput, ClassifyResult, Severity
from app.cohere_client.client import chat, extract_text

_SYSTEM = f"""You are a support-ticket classifier for a SaaS product.

Classify the ticket into exactly one severity and one category:
- severity: one of {[s.value for s in Severity]}
  P1-critical = full outage / data loss / security breach / production down for many customers.
  P2-high = major feature broken, no workaround, affects one customer badly.
  P3-medium = partial functionality issue, workaround exists.
  P4-low = cosmetic, question, or minor inconvenience.
- category: one of {[c.value for c in Category]}

Respond with ONLY a JSON object of the form:
{{"severity": "<severity>", "category": "<category>", "confidence": <0-1 float>, "rationale": "<one sentence>"}}"""


async def run(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    parsed = ClassifyInput.model_validate(args)
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"Subject: {parsed.subject}\n\nBody: {parsed.body}"},
    ]
    response = await chat(messages=messages, response_format={"type": "json_object"}, temperature=0)
    data = json.loads(extract_text(response))
    result = ClassifyResult(
        severity=Severity(data["severity"]),
        category=Category(data["category"]),
        confidence=float(data.get("confidence", 0.5)),
        rationale=data.get("rationale", ""),
    )
    return result.model_dump(mode="json")
