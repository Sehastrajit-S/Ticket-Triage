"""Unit tests for the Bedrock/SageMaker provider switch in app/cohere_client/client.py.

These mock cohere.BedrockClientV2 / SagemakerClientV2 entirely, since no AWS
credentials or Bedrock model access are available to test against the real
services. What's verified here: the right client class gets constructed for
each provider, the right model/endpoint setting is used per call type, and
the sync AWS SDK methods are dispatched through asyncio.to_thread rather than
awaited directly (they have no async variant).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.cohere_client import client as cohere_client


@pytest.fixture(autouse=True)
def _reset_aws_client_cache():
    cohere_client._aws_client = None
    yield
    cohere_client._aws_client = None


@pytest.mark.asyncio
async def test_chat_uses_bedrock_client_and_model_when_provider_is_bedrock(monkeypatch):
    monkeypatch.setattr(cohere_client.settings, "cohere_provider", "bedrock")
    monkeypatch.setattr(cohere_client.settings, "cohere_bedrock_chat_model", "cohere.command-a-bedrock")
    monkeypatch.setattr(cohere_client.settings, "aws_region", "us-east-1")

    fake_response = SimpleNamespace(message=SimpleNamespace(content=[]))
    fake_bedrock_instance = MagicMock()
    fake_bedrock_instance.chat.return_value = fake_response

    with patch("cohere.BedrockClientV2", return_value=fake_bedrock_instance) as bedrock_cls:
        result = await cohere_client.chat(messages=[{"role": "user", "content": "hi"}])

    bedrock_cls.assert_called_once_with(aws_region="us-east-1")
    fake_bedrock_instance.chat.assert_called_once()
    assert fake_bedrock_instance.chat.call_args.kwargs["model"] == "cohere.command-a-bedrock"
    assert result is fake_response


@pytest.mark.asyncio
async def test_embed_uses_sagemaker_endpoint_when_provider_is_sagemaker(monkeypatch):
    monkeypatch.setattr(cohere_client.settings, "cohere_provider", "sagemaker")
    monkeypatch.setattr(cohere_client.settings, "cohere_sagemaker_embed_endpoint", "my-cohere-embed-endpoint")

    fake_response = SimpleNamespace(embeddings=SimpleNamespace(float_=[[0.1, 0.2]]))
    fake_sagemaker_instance = MagicMock()
    fake_sagemaker_instance.embed.return_value = fake_response

    with patch("cohere.SagemakerClientV2", return_value=fake_sagemaker_instance):
        result = await cohere_client.embed(["some text"])

    fake_sagemaker_instance.embed.assert_called_once()
    assert fake_sagemaker_instance.embed.call_args.kwargs["model"] == "my-cohere-embed-endpoint"
    assert result == [[0.1, 0.2]]


@pytest.mark.asyncio
async def test_rerank_uses_bedrock_and_returns_direct_api_shape(monkeypatch):
    monkeypatch.setattr(cohere_client.settings, "cohere_provider", "bedrock")
    monkeypatch.setattr(cohere_client.settings, "cohere_bedrock_rerank_model", "cohere.rerank-bedrock")

    fake_result = SimpleNamespace(index=0, relevance_score=0.9)
    fake_response = SimpleNamespace(results=[fake_result])
    fake_bedrock_instance = MagicMock()
    fake_bedrock_instance.rerank.return_value = fake_response

    with patch("cohere.BedrockClientV2", return_value=fake_bedrock_instance):
        result = await cohere_client.rerank("query", ["doc a"])

    assert result == [{"index": 0, "relevance_score": 0.9, "document": "doc a"}]
    assert fake_bedrock_instance.rerank.call_args.kwargs["model"] == "cohere.rerank-bedrock"


@pytest.mark.asyncio
async def test_default_provider_never_touches_aws_client(monkeypatch):
    monkeypatch.setattr(cohere_client.settings, "cohere_provider", "cohere")
    fake_response = SimpleNamespace(message=SimpleNamespace(content=[]))
    fake_async_client = MagicMock()
    fake_async_client.chat = AsyncMock(return_value=fake_response)
    monkeypatch.setattr(cohere_client, "get_client", lambda: fake_async_client)

    with patch("cohere.BedrockClientV2") as bedrock_cls, patch("cohere.SagemakerClientV2") as sagemaker_cls:
        result = await cohere_client.chat(messages=[{"role": "user", "content": "hi"}])

    assert result is fake_response
    bedrock_cls.assert_not_called()
    sagemaker_cls.assert_not_called()


def test_get_aws_client_raises_on_unknown_provider(monkeypatch):
    monkeypatch.setattr(cohere_client.settings, "cohere_provider", "not-a-real-provider")
    with pytest.raises(ValueError, match="unknown cohere_provider"):
        cohere_client.get_aws_client()
