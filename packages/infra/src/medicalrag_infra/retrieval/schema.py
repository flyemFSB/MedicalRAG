"""Qdrant 向量集合模式（Schema）定义与初始化（迁移至 Qdrant）。

定义集合的向量结构（包含基于 HNSW 索引的 dense_vec 稠密向量、基于 BM25 模型的 sparse_vec 稀疏向量、以及 payload 标量过滤索引），
并提供具有幂等性的 ensure_collection 初始化构建方法。
"""

from __future__ import annotations

from qdrant_client import QdrantClient, models

DEFAULT_EMBEDDING_DIM = 1536
DEFAULT_COLLECTION = "medical_chunks_v1"
# 稀疏向量模型（索引端与检索端共享同一静态 BM25 模型：无外部语料拟合依赖，保证词项权重对称一致）
DEFAULT_SPARSE_MODEL = "Qdrant/bm25"


def ensure_collection(
    client: QdrantClient,
    collection: str = DEFAULT_COLLECTION,
    *,
    embedding_dim: int = DEFAULT_EMBEDDING_DIM,
) -> None:
    """幂等创建集合与标量载荷索引；集合已存在时只补建缺失的索引。

    载荷索引单独幂等执行（create_payload_index 重复调用安全），否则已存在的旧集合
    永远补不上后加索引字段（官方要求索引必须在写入数据前建立，否则 filterable HNSW 不会生成额外边）。
    """
    collections = [c.name for c in client.get_collections().collections]
    if collection not in collections:
        client.create_collection(
            collection_name=collection,
            vectors_config={
                "dense_vec": models.VectorParams(
                    size=embedding_dim,
                    distance=models.Distance.COSINE,
                    quantization_config=models.TurboQuantization(
                        turbo=models.TurboQuantQuantizationConfig(
                            bits=models.TurboQuantBitSize.BITS4,
                            # PINNED 是 always_ram 的非弃用等价写法（量化向量常驻内存）
                            memory=models.Memory.PINNED,
                        ),
                    ),
                    # 仅保留非默认值的 HNSW 参数（m=16 与 indexing_threshold=20000 已是官方默认）
                    hnsw_config=models.HnswConfigDiff(ef_construct=200),
                ),
            },
            sparse_vectors_config={
                "sparse_vec": models.SparseVectorParams(
                    modifier=models.Modifier.IDF,
                ),
            },
        )

    # 标量载荷索引：全部过滤路径（workspace_id / document_id / is_eligible）都必须有索引，
    # 否则过滤退化为全扫描（官方：未索引过滤不仅慢，还会消耗集群资源影响其它查询延迟）
    for field_name, field_schema in (
        ("workspace_id", models.PayloadSchemaType.KEYWORD),
        ("document_id", models.PayloadSchemaType.KEYWORD),
        ("is_eligible", models.PayloadSchemaType.BOOL),
    ):
        client.create_payload_index(
            collection_name=collection,
            field_name=field_name,
            field_schema=field_schema,
        )
