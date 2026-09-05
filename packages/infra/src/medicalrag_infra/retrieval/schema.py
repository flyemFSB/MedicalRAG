"""Qdrant 向量集合模式（Schema）定义与初始化（迁移至 Qdrant）。

定义集合的向量结构（包含基于 HNSW 索引的 dense_vec 稠密向量、基于 BM25 模型的 sparse_vec 稀疏向量、以及 payload 标量过滤索引），
并提供具有幂等性的 ensure_collection 初始化构建方法。
"""

from __future__ import annotations

from qdrant_client import QdrantClient, models

DEFAULT_EMBEDDING_DIM = 1536
DEFAULT_COLLECTION = "medical_chunks_v1"
# 稀疏向量模型（索引端与检索端共享同一静态 BM25 模型：无语料库状态依赖，保证对称一致性）
DEFAULT_SPARSE_MODEL = "Qdrant/bm25"


def ensure_collection(
    client: QdrantClient,
    collection: str = DEFAULT_COLLECTION,
    *,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
) -> None:
    """幂等创建 Qdrant 向量集合并建立标量载荷索引；若集合已存在则自动跳过。"""
    collections = [c.name for c in client.get_collections().collections]
    if collection in collections:
        return

    client.create_collection(
        collection_name=collection,
        vectors_config={
            "dense_vec": models.VectorParams(
                size=embedding_dim,
                distance=models.Distance.COSINE,
                on_disk=False,
                quantization_config=models.TurboQuantization(
                    turbo=models.TurboQuantQuantizationConfig(
                        bits=models.TurboQuantBitSize.BITS4,
                        always_ram=True,
                    ),
                ),
                hnsw_config=models.HnswConfigDiff(
                    m=16,
                    ef_construct=200,
                ),
            ),
        },
        sparse_vectors_config={
            "sparse_vec": models.SparseVectorParams(
                modifier=models.Modifier.IDF,
            ),
        },
        optimizers_config=models.OptimizersConfigDiff(
            indexing_threshold=20000,
        ),
    )

    # 标量载荷索引：workspace_id 精确过滤采用 KEYWORD 类型（官方推荐实践：不分词），is_eligible 采用 BOOL 类型
    client.create_payload_index(
        collection_name=collection,
        field_name="workspace_id",
        field_schema=models.PayloadSchemaType.KEYWORD,
    )
    client.create_payload_index(
        collection_name=collection,
        field_name="is_eligible",
        field_schema=models.PayloadSchemaType.BOOL,
    )
