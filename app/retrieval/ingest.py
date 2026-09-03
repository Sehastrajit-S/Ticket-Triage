"""Embed and upsert documents (historical tickets, KB articles, runbooks, policies) into pgvector."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.cohere_client.client import embed
from app.db.models import Document
from app.observability.tracing import traced

_EMBED_BATCH_SIZE = 96  # Cohere embed endpoint batch limit headroom


@dataclass
class DocumentInput:
    source_type: str  # ticket|kb|runbook|policy
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@traced("ingest.documents")
async def ingest_documents(session: AsyncSession, docs: list[DocumentInput]) -> list[Document]:
    """Embeds each doc's content and persists it as a Document row. Commits once at the end."""
    if not docs:
        return []

    rows: list[Document] = []
    for start in range(0, len(docs), _EMBED_BATCH_SIZE):
        batch = docs[start : start + _EMBED_BATCH_SIZE]
        embeddings = await embed([d.content for d in batch], input_type="search_document")
        for doc, vector in zip(batch, embeddings, strict=True):
            rows.append(
                Document(
                    source_type=doc.source_type,
                    title=doc.title,
                    content=doc.content,
                    doc_metadata=doc.metadata,
                    embedding=vector,
                )
            )

    session.add_all(rows)
    await session.commit()
    for row in rows:
        await session.refresh(row)
    return rows
