"""OpenAI 兼容嵌入适配器检查（MockTransport）。"""

import httpx2 as httpx
import pytest

from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_infra.providers.embeddings import OpenAICompatEmbeddingProvider
from medicalrag_infra.providers.llm import LLMProviderConfig


def _provider(handler) -> OpenAICompatEmbeddingProvider:
    return OpenAICompatEmbeddingProvider(
        LLMProviderConfig(base_url="https://api.example.com", api_key="k", model="e"),
        transport=httpx.MockTransport(handler),
    )


async def test_embed_returns_vectors():
    def handler(request):
        return httpx.Response(
            200,
            json={"data": [{"embedding": [0.1, 0.2]}, {"embedding": [0.3, 0.4]}]},
        )

    vectors = await _provider(handler).embed(["a", "b"])
    assert vectors == [[0.1, 0.2], [0.3, 0.4]]


async def test_embed_raises_on_http_error():
    def handler(request):
        return httpx.Response(500, json={})

    with pytest.raises(ProviderUnavailableError):
        await _provider(handler).embed(["a"])


async def test_embed_raises_on_missing_embedding():
    def handler(request):
        return httpx.Response(200, json={"data": [{"index": 0}]})

    with pytest.raises(ProviderUnavailableError):
        await _provider(handler).embed(["a"])
