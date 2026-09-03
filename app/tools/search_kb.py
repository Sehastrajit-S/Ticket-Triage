from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.schemas import SearchKBInput, SearchKBResult
from app.retrieval.search import search


async def run(session: AsyncSession, args: dict[str, Any]) -> dict[str, Any]:
    parsed = SearchKBInput.model_validate(args)
    chunks = await search(session, parsed.query, source_types=parsed.source_types, top_n=parsed.top_n)
    results = [
        SearchKBResult(
            document_id=c.document_id,
            source_type=c.source_type,
            title=c.title,
            content=c.content,
            relevance_score=c.relevance_score,
        )
        for c in chunks
    ]
    return {"results": [r.model_dump(mode="json") for r in results]}
