"""QdrantRetriever 检查（注入 fake QdrantClient + EmbeddingProvider）。

Qdrant API：query_points(prefetch=[dense, sparse], query=RrfQuery(k=60))。
检索器做 dense + sparse 双路 prefetch，Qdrant 内部 RRF 融合。
sparse 查询向量由 fastembed 静态 BM25 模型（此处注入 fake）生成。
"""

from medicalrag_core.chat.model import ChatRequest, IntentQuery
from medicalrag_core.intent.node import IntentKind, IntentLevel, IntentNode
from medicalrag_infra.retrieval.qdrant import QdrantRetriever


def _query(node_id: str = "disease-info") -> IntentQuery:
    node = IntentNode(
        node_id,
        level=IntentLevel.TOPIC,
        kind=IntentKind.KNOWLEDGE,
        name="疾病信息",
        description="疾病基本信息",
    )
    return IntentQuery(node)


def _request() -> ChatRequest:
    return ChatRequest(question="q", conversation_id="c", user_id="u", workspace_id="ws-1")


class FakeEmbeddings:
    def __init__(self, vectors=None) -> None:
        self.vectors = vectors or [[0.1, 0.2]]
        self.calls: list[list[str]] = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return self.vectors


class FakeSparse:
    """Duck-typed fastembed SparseEmbedding."""

    def __init__(self, indices, values) -> None:
        self.indices = indices
        self.values = values


class FakeSparseModel:
    def embed(self, texts):
        return iter([FakeSparse([3, 7], [0.9, 0.4]) for _ in texts])


class FakeQueryResult:
    """Fake query_points result with points list."""

    def __init__(self, points) -> None:
        self.points = points


class FakePoint:
    """Fake point with id, score, payload."""

    def __init__(self, chunk_id: str, score: float = 0.9) -> None:
        self.id = chunk_id
        self.score = score
        self.payload = {
            "chunk_id": chunk_id,
            "document_id": "d1",
            "source_id": "s1",
            "title": "t",
            "snippet": "s",
        }


class FakeQdrantClient:
    """Fake QdrantClient: tracks query_points calls, returns fake results."""

    def __init__(self, points=None) -> None:
        self._points = points or [FakePoint("c1"), FakePoint("c2", 0.7)]
        self.calls: list[dict] = []

    def query_points(self, **kwargs):
        self.calls.append(kwargs)
        return FakeQueryResult(self._points)


async def test_retrieve_maps_points_to_candidates():
    embeddings = FakeEmbeddings()
    client = FakeQdrantClient([FakePoint("c1"), FakePoint("c2", 0.7)])
    result = await QdrantRetriever(
        client, embeddings, collection="med_v1", sparse_model=FakeSparseModel()
    ).retrieve(_request(), (_query(),))
    assert [c.chunk_id for c in result] == ["c1", "c2"]
    assert result[0].intent == "disease-info"
    assert result[0].channel == "hybrid"
    assert result[0].is_eligible


async def test_retrieve_uses_prefetch_and_rrf():
    embeddings = FakeEmbeddings()
    client = FakeQdrantClient()
    await QdrantRetriever(
        client, embeddings, collection="med_v1", sparse_model=FakeSparseModel()
    ).retrieve(_request(), (_query(),))
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["collection_name"] == "med_v1"
    # dense + sparse 双路 prefetch
    assert len(call["prefetch"]) == 2
    assert call["prefetch"][0].using == "dense_vec"
    assert call["prefetch"][1].using == "sparse_vec"
    assert call["prefetch"][1].query.indices == [3, 7]
    assert call["prefetch"][1].query.values == [0.9, 0.4]
    # RRF query
    assert call["query"].rrf.k == 60
    # Filter
    query_filter = call["query_filter"]
    assert len(query_filter.must) == 2
    # 无重写问题时兜底为意图名+描述（ADR 0036 缺省路径）
    assert embeddings.calls == [["疾病信息 疾病基本信息"]]


async def test_retrieve_prefers_rewritten_question_and_slots():
    # ADR 0036：查询主体是重写后的问题，槽位 Medical Entity 附加。
    node = _query().node
    query = IntentQuery(node, {"drug": "阿司匹林"}, rewritten_question="阿司匹林的用法用量")
    embeddings = FakeEmbeddings()
    await QdrantRetriever(
        FakeQdrantClient(), embeddings, collection="med_v1", sparse_model=FakeSparseModel()
    ).retrieve(_request(), (query,))
    assert embeddings.calls == [["阿司匹林的用法用量 阿司匹林"]]


async def test_retrieve_dedupes_identical_query_texts():
    node = _query().node
    queries = (
        IntentQuery(node, rewritten_question="同一个问题"),
        IntentQuery(node, rewritten_question="同一个问题"),
    )
    embeddings = FakeEmbeddings()
    await QdrantRetriever(
        FakeQdrantClient(), embeddings, collection="med_v1", sparse_model=FakeSparseModel()
    ).retrieve(_request(), queries)
    assert len(embeddings.calls) == 1
