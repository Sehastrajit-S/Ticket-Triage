"""Retrieval pipeline: pgvector cosine search (recall) -> Rerank 4 (precision)."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cohere_client.client import embed, rerank
from app.config import get_settings
from app.db.models import Document
from app.observability.tracing import traced

settings = get_settings()


@dataclass
class RetrievedChunk:
    document_id: str
    source_type: str
    title: str
    content: str
    relevance_score: float
    metadata: dict


@traced("retrieval.search")
async def search(
    session: AsyncSession,
    query: str,
    source_types: list[str] | None = None,
    top_k: int | None = None,
    top_n: int | None = None,
) -> list[RetrievedChunk]:
    """Vector search for the top_k nearest documents, reranked down to top_n."""
    top_k = top_k or settings.retrieval_top_k
    top_n = top_n or settings.rerank_top_n

    [query_vector] = await embed([query], input_type="search_query")

    stmt = select(Document).order_by(Document.embedding.cosine_distance(query_vector)).limit(top_k)
    if source_types:
        stmt = stmt.where(Document.source_type.in_(source_types))

    candidates = (await session.execute(stmt)).scalars().all()
    if not candidates:
        return []

    reranked = await rerank(query, [c.content for c in candidates], top_n=min(top_n, len(candidates)))

    results: list[RetrievedChunk] = []
    for item in reranked:
        doc = candidates[item["index"]]
        results.append(
            RetrievedChunk(
                document_id=str(doc.id),
                source_type=doc.source_type,
                title=doc.title,
                content=doc.content,
                relevance_score=item["relevance_score"],
                metadata=doc.doc_metadata,
            )
        )
    return results
