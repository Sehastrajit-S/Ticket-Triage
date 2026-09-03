"""Thin async wrapper around the Cohere SDK: embed (v4), rerank (4), chat (Command A).

Every call is retried on transient failures and instrumented with an OTel span
so latency/errors show up in traces regardless of which layer calls in.
"""

from __future__ import annotations

from typing import Any

import cohere
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.observability.tracing import traced

settings = get_settings()

_client: cohere.AsyncClientV2 | None = None


def get_client() -> cohere.AsyncClientV2:
    global _client
    if _client is None:
        _client = cohere.AsyncClientV2(api_key=settings.cohere_api_key)
    return _client


_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=0.5, min=0.5, max=8),
    reraise=True,
)


@traced("cohere.embed")
@_retry
async def embed(texts: list[str], input_type: str = "search_document") -> list[list[float]]:
    """input_type: 'search_document' for corpus/ingestion, 'search_query' for queries."""
    if not texts:
        return []
    response = await get_client().embed(
        model=settings.cohere_embed_model,
        texts=texts,
        input_type=input_type,
        embedding_types=["float"],
    )
    return response.embeddings.float_


@traced("cohere.rerank")
@_retry
async def rerank(query: str, documents: list[str], top_n: int | None = None) -> list[dict[str, Any]]:
    """Returns documents reordered by relevance, each with its original text and score."""
    if not documents:
        return []
    n = top_n or min(settings.rerank_top_n, len(documents))
    response = await get_client().rerank(
        model=settings.cohere_rerank_model,
        query=query,
        documents=documents,
        top_n=n,
    )
    return [
        {"index": r.index, "relevance_score": r.relevance_score, "document": documents[r.index]}
        for r in response.results
    ]


@traced("cohere.chat")
@_retry
async def chat(
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> Any:
    """Raw passthrough to Command A chat, with model id defaulted from settings."""
    return await get_client().chat(
        model=settings.cohere_chat_model,
        messages=messages,
        tools=tools,
        **kwargs,
    )


def extract_text(response: Any) -> str:
    """Pulls the plain-text reply out of a Command A chat response's content blocks."""
    content = getattr(response.message, "content", None) or []
    for block in content:
        text = getattr(block, "text", None)
        if text:
            return text
    return ""
