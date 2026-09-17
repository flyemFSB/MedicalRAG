"""QdrantIndexer 检查（注入 fake QdrantClient + embedding；ADR 0011/0035 迁移至 Qdrant）。"""

from medicalrag_core.chunking.chunking import Section, chunk_document
from medicalrag_infra.retrieval.indexer import QdrantIndexer


class FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return [[float(i)] for i in range(len(texts))]


class FakeSparse:
    """Duck-typed fastembed SparseEmbedding."""

    def __init__(self, indices, values) -> None:
        self.indices = indices
        self.values = values


class FakeSparseModel:
    def embed(self, texts):
        return iter([FakeSparse([0, 2], [1.0, 0.5]) for _ in texts])


class FakeQdrantClient:
    def __init__(self) -> None:
        self.upserts: list[dict] = []

    def upsert(self, **kwargs):
        self.upserts.append(kwargs)

    def get_collections(self):
        class Collections:
            def __init__(self) -> None:
                self.collections: list = []

        return Collections()

    def create_collection(self, **kwargs):
        pass

    def create_payload_index(self, **kwargs):
        pass


async def test_index_embeds_with_structure_and_upserts_points():
    embeddings = FakeEmbeddings()
    client = FakeQdrantClient()
    chunks = chunk_document(
        "doc-1",
        (
            Section(level=1, heading="高血压", text="定义。"),
            Section(level=2, heading="病因", text="病因内容。"),
        ),
    )
    indexer = QdrantIndexer(client, embeddings, collection="med_v1", sparse_model=FakeSparseModel())
    await indexer.index("doc-1", "ws-1", chunks, title="高血压指南", source_id="src-1")

    assert embeddings.calls == [["高血压\n定义。", "高血压 > 病因\n病因内容。"]]
    assert len(client.upserts) == 1
    upsert = client.upserts[0]
    assert upsert["collection_name"] == "med_v1"
    points = upsert["points"]
    assert len(points) == 2
    import uuid

    assert points[0].id == str(uuid.uuid5(uuid.NAMESPACE_URL, "doc-1:0"))
    assert points[1].id == str(uuid.uuid5(uuid.NAMESPACE_URL, "doc-1:1"))
    assert points[0].payload["chunk_id"] == "doc-1:0"
    assert points[0].payload["title"] == "高血压指南"
    assert points[0].payload["source_id"] == "src-1"
    assert points[0].payload["workspace_id"] == "ws-1"
    # ADR 0079/0013：索引时点先落为不合格，published 阶段才翻转资格
    assert points[0].payload["is_eligible"] is False
    # 模拟嵌入模型生成的稠密向量
    assert points[0].vector["dense_vec"] == [0.0]
    assert points[1].vector["dense_vec"] == [1.0]
    # fastembed 静态 BM25 模型生成的稀疏向量
    assert points[0].vector["sparse_vec"].indices == [0, 2]
    assert points[0].vector["sparse_vec"].values == [1.0, 0.5]
    # 存储于 payload 中的文本
    assert points[0].payload["text"] == "高血压\n定义。"
