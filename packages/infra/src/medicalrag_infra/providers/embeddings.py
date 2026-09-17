"""文本向量嵌入适配器（基于 OpenAI SDK 实现，遵循 EmbeddingProvider 协议端口）。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Sequence
from typing import cast

import openai
from redis.exceptions import RedisError

from medicalrag_core.chat.ports import ProviderUnavailableError
from medicalrag_core.retrieval.ports import EmbeddingProvider

from .llm import _OpenAICompatClient


class OpenAICompatEmbeddingProvider(_OpenAICompatClient):
    """基于 OpenAI SDK /embeddings 接口的向量嵌入适配器。"""

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        try:
            response = await self._client.embeddings.create(
                model=self._config.model, input=list(texts)
            )
        except openai.APIError as exc:
            raise ProviderUnavailableError(type(exc).__name__) from exc
        embeddings = [item.embedding for item in response.data]
        if not embeddings or any(e is None for e in embeddings):
            raise ProviderUnavailableError("missing_embedding")
        return embeddings


class CachedEmbeddingProvider:
    """查询侧向量嵌入缓存（基于 Redis 实现；以模型名称 + 归一化查询文本的 SHA256 为缓存 Key，规范 Phase 3 优化）。

    本缓存专用于在线检索端（Agent）；文档切片摄取阶段为一次性批量计算，无需接入此缓存。
    当 Redis 服务异常或不可用时，系统自动执行 fail-open 策略，直接透传请求至底层 Inner Provider（将缓存视作加速优化，非硬性阻断依赖）。
    缓存 Key 显式包含模型名称，确保在切换嵌入模型后绝不会错误命中旧向量空间的陈旧向量。
    """

    def __init__(
        self,
        inner: EmbeddingProvider,
        redis_client,  # redis.asyncio.Redis 实例（采用鸭子类型解耦构造签名）
        *,
        namespace: str = "default",
    ) -> None:
        self._inner = inner
        self._redis = redis_client
        self._namespace = namespace
        self._ttl_s = 86_400

    def _key(self, text: str) -> str:
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        return f"emb:{self._namespace}:{digest}"

    async def embed(self, texts: Sequence[str]) -> Sequence[Sequence[float]]:
        if not texts:
            return []
        try:
            return await self._embed_cached(texts)
        except (RedisError, ValueError):
            # Redis 故障/缓存值损坏 fail-open：缓存是加速优化，不阻断嵌入链路
            # （历史格式或半写入的脏缓存值 json.loads 抛 JSONDecodeError，属 ValueError 子类）
            return [list(vector) for vector in await self._inner.embed(texts)]

    async def _embed_cached(self, texts: Sequence[str]) -> list[list[float]]:
        keys = [self._key(text) for text in texts]
        cached = await self._redis.mget(keys)
        results: list[list[float] | None] = [
            json.loads(value) if value is not None else None for value in cached
        ]
        misses = [index for index, result in enumerate(results) if result is None]
        if misses:
            fresh = await self._inner.embed([texts[index] for index in misses])
            vectors = [[float(x) for x in vector] for vector in fresh]
            if len(vectors) != len(misses):
                raise ProviderUnavailableError("embedding_count_mismatch")
            pipe = self._redis.pipeline()
            for index, vector in zip(misses, vectors, strict=True):
                results[index] = vector
                pipe.set(keys[index], json.dumps(vector), ex=self._ttl_s)
            await pipe.execute()
        return [cast("list[float]", result) for result in results]
