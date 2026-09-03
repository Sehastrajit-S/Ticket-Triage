from __future__ import annotations

from typing import Any

from cohere.types.document import Document as CohereDocument
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import DraftResponseInput, DraftResponseResult
from app.cohere_client.client import chat, extract_text
from app.db.models import Document

_SYSTEM = (
    "You are a precise, professional support agent. Draft a FIRST reply to this customer's new, "
    "unresolved ticket, grounded ONLY in the attached documents.\n\n"
    "The documents include past resolved tickets and runbooks. These describe what happened in "
    "OTHER, separate cases, or the steps a runbook prescribes — they are precedent to guide your "
    "reply, never a record of what has already been done for THIS customer or THIS ticket. Never "
    "state or imply that an investigation is complete, that an action (refund, password reset, "
    "2FA enablement, account verification, etc.) has already been taken, or that the issue is "
    "resolved, unless the current ticket explicitly says so. Describe such actions as what you "
    "(support) will do next, or what the customer should do next — not as already-completed "
    "facts.\n\n"
    "Do not include internal fields from the documents in the reply — no severity/category/"
    "priority labels, internal titles, or other internal metadata. Write only the customer-facing "
    "reply text.\n\n"
    "If the documents are insufficient to fully resolve the issue, say so plainly and note that a "
    "human agent will follow up. Keep the reply concise."
)


async def run(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    parsed = DraftResponseInput.model_validate(args)

    docs: list[Document] = []
    if parsed.doc_ids:
        result = await session.execute(select(Document).where(Document.id.in_(parsed.doc_ids)))
        docs = list(result.scalars().all())

    # Pass documents natively via Cohere's grounded-generation `documents` parameter instead of
    # stuffing them into the prompt text — this is what makes Command A emit real `citations`
    # (span-level, tied back to a document id) rather than us guessing which docs it used.
    cohere_documents = [
        CohereDocument(id=str(doc.id), data={"title": doc.title, "text": doc.content}) for doc in docs
    ]

    messages = [
        {"role": "system", "content": _SYSTEM},
        {
            "role": "user",
            "content": (
                f"Ticket subject: {parsed.subject}\n"
                f"Ticket body: {parsed.body}\n"
                f"Category: {parsed.category.value}"
            ),
        },
    ]
    response = await chat(
        messages=messages,
        documents=cohere_documents or None,
        temperature=0.3,
    )

    citations = [
        {
            "text": c.text,
            "start": c.start,
            "end": c.end,
            "document_ids": [s.id for s in (c.sources or []) if getattr(s, "type", None) == "document"],
        }
        for c in (getattr(response.message, "citations", None) or [])
    ]
    cited_doc_ids = sorted({doc_id for c in citations for doc_id in c["document_ids"]})

    result = DraftResponseResult(
        draft=extract_text(response),
        cited_doc_ids=cited_doc_ids or [str(d.id) for d in docs],
        citations=citations,
    )
    return result.model_dump(mode="json")
