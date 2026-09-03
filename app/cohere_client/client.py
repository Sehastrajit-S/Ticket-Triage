"""Thin async wrapper around the Cohere SDK: embed (v4), rerank (4), chat (Command A).

Every call is retried on transient failures and instrumented with an OTel span
so latency/errors show up in traces regardless of which layer calls in.

Provider switch: COHERE_PROVIDER selects where these calls actually go.
- "cohere" (default): api.cohere.com directly via AsyncClientV2, using cohere_api_key.
- "bedrock" / "sagemaker": Cohere's own AwsClientV2 subclasses (BedrockClientV2 /
  SagemakerClientV2), shipped in the same `cohere` SDK, using standard AWS
  credential resolution instead of an API key. These AWS client classes are
  sync-only (no async variant), so calls run in a thread via asyncio.to_thread
  to avoid blocking the event loop. Unverified against a live AWS account: no
  AWS credentials or Bedrock model access were available to test this path
  end-to-end, unlike the direct Cohere path above, which is exercised for real
  throughout this project.
"""

from __future__ import annotations

import asyncio
from typing import Any

import cohere
from tenacity import retry, stop_after_attempt, wait_exponential

from app.config import get_settings
from app.observability.tracing import traced

settings = get_settings()

_client: cohere.AsyncClientV2 | None = None
_aws_client: cohere.BedrockClientV2 | cohere.SagemakerClientV2 | None = None


def get_client() -> cohere.AsyncClientV2:
    global _client
    if _client is None:
        _client = cohere.AsyncClientV2(api_key=settings.cohere_api_key)
    return _client


def get_aws_client() -> cohere.BedrockClientV2 | cohere.SagemakerClientV2:
    """Returns the cached Bedrock or SageMaker client, selected by COHERE_PROVIDER.

    Both take AWS credentials via the standard boto3 resolution chain (env vars,
    ~/.aws/credentials profile, or an instance/task role) when aws_access_key /
    aws_secret_key aren't passed explicitly, so no separate AWS SDK setup is
    needed beyond `aws configure` or the equivalent env vars.
    """
    global _aws_client
    if _aws_client is None:
        region = settings.aws_region or None
        if settings.cohere_provider == "bedrock":
            _aws_client = cohere.BedrockClientV2(aws_region=region)
        elif settings.cohere_provider == "sagemaker":
            _aws_client = cohere.SagemakerClientV2(aws_region=region)
        else:
            raise ValueError(f"unknown cohere_provider: {settings.cohere_provider!r}")
    return _aws_client


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
    if settings.cohere_provider == "cohere":
        response = await get_client().embed(
            model=settings.cohere_embed_model,
            texts=texts,
            input_type=input_type,
            embedding_types=["float"],
        )
    else:
        model = (
            settings.cohere_bedrock_embed_model
            if settings.cohere_provider == "bedrock"
            else settings.cohere_sagemaker_embed_endpoint
        )
        response = await asyncio.to_thread(
            get_aws_client().embed,
            model=model,
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
    if settings.cohere_provider == "cohere":
        response = await get_client().rerank(
            model=settings.cohere_rerank_model,
            query=query,
            documents=documents,
            top_n=n,
        )
    else:
        model = (
            settings.cohere_bedrock_rerank_model
            if settings.cohere_provider == "bedrock"
            else settings.cohere_sagemaker_rerank_endpoint
        )
        response = await asyncio.to_thread(
            get_aws_client().rerank,
            model=model,
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
    if settings.cohere_provider == "cohere":
        return await get_client().chat(
            model=settings.cohere_chat_model,
            messages=messages,
            tools=tools,
            **kwargs,
        )
    model = (
        settings.cohere_bedrock_chat_model
        if settings.cohere_provider == "bedrock"
        else settings.cohere_sagemaker_chat_endpoint
    )
    return await asyncio.to_thread(
        get_aws_client().chat,
        model=model,
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
