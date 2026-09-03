from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.retrieval.ingest import DocumentInput, ingest_documents

router = APIRouter(prefix="/admin", tags=["admin"])


class DocumentPayload(BaseModel):
    source_type: str  # ticket|kb|runbook|policy
    title: str
    content: str
    metadata: dict = {}


@router.post("/documents", status_code=201)
async def add_documents(payload: list[DocumentPayload], session: AsyncSession = Depends(get_session)) -> dict:
    """Re-index / add KB articles, runbooks, policy docs, or historical tickets."""
    docs = [
        DocumentInput(source_type=d.source_type, title=d.title, content=d.content, metadata=d.metadata)
        for d in payload
    ]
    rows = await ingest_documents(session, docs)
    return {"ingested": len(rows), "ids": [str(r.id) for r in rows]}
