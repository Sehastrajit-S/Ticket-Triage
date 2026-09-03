from unittest.mock import AsyncMock, MagicMock

import pytest

from app.retrieval import search as search_module


class _FakeDoc:
    def __init__(self, id, source_type, title, content):
        self.id = id
        self.source_type = source_type
        self.title = title
        self.content = content
        self.doc_metadata = {}


@pytest.mark.asyncio
async def test_search_orders_by_rerank_not_vector_order(monkeypatch):
    docs = [
        _FakeDoc("id-1", "kb", "Doc A", "content A"),
        _FakeDoc("id-2", "kb", "Doc B", "content B"),
    ]

    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = docs

    session = AsyncMock()
    session.execute.return_value = fake_result

    async def fake_embed(texts, input_type="search_document"):
        return [[0.1, 0.2, 0.3]]

    async def fake_rerank(query, documents, top_n=None):
        # Rerank flips the vector-search order to prove `search` respects rerank ordering.
        return [
            {"index": 1, "relevance_score": 0.9, "document": documents[1]},
            {"index": 0, "relevance_score": 0.4, "document": documents[0]},
        ]

    monkeypatch.setattr(search_module, "embed", fake_embed)
    monkeypatch.setattr(search_module, "rerank", fake_rerank)

    results = await search_module.search(session, "some query", top_k=10, top_n=2)

    assert [r.document_id for r in results] == ["id-2", "id-1"]
    assert results[0].relevance_score == 0.9


@pytest.mark.asyncio
async def test_search_returns_empty_when_no_candidates(monkeypatch):
    fake_result = MagicMock()
    fake_result.scalars.return_value.all.return_value = []

    session = AsyncMock()
    session.execute.return_value = fake_result

    async def fake_embed(texts, input_type="search_document"):
        return [[0.1, 0.2, 0.3]]

    monkeypatch.setattr(search_module, "embed", fake_embed)

    results = await search_module.search(session, "no matches expected")
    assert results == []
