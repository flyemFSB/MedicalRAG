"""结构优先分块检查（ADR 0034：保留标题路径与来源）。"""

from medicalrag_core.chunking.chunking import Section, chunk_document, embedding_text


def _sections():
    return (
        Section(level=1, heading="高血压", text="定义与分类。"),
        Section(level=2, heading="病因", text="主要病因包括…"),
        Section(level=2, heading="治疗", text="常规管理包括…"),
        Section(level=1, heading="糖尿病", text="另一类疾病。"),
    )


def test_each_section_becomes_one_chunk_with_provenance():
    chunks = chunk_document("doc-1", _sections())
    assert len(chunks) == 4
    assert all(c.document_id == "doc-1" for c in chunks)
    assert [c.index for c in chunks] == [0, 1, 2, 3]
    assert [c.text for c in chunks] == [
        "定义与分类。",
        "主要病因包括…",
        "常规管理包括…",
        "另一类疾病。",
    ]


def test_heading_path_tracks_nesting_and_resets():
    chunks = chunk_document("doc-1", _sections())
    assert chunks[0].heading_path == ("高血压",)
    assert chunks[1].heading_path == ("高血压", "病因")
    assert chunks[2].heading_path == ("高血压", "治疗")
    # 新一级标题重置路径
    assert chunks[3].heading_path == ("糖尿病",)


def test_embedding_text_includes_heading_path():
    chunks = chunk_document("doc-1", _sections())
    assert embedding_text(chunks[0]) == "高血压\n定义与分类。"
    assert embedding_text(chunks[1]) == "高血压 > 病因\n主要病因包括…"


def _counter(text: str) -> int:
    """测试用计数：1 字符 = 1 token（加性，模拟理想 tokenizer 的可累加性）。"""
    return len(text)


def test_long_section_splits_at_sentence_boundaries_with_overlap():
    body = "".join(f"第{i}句内容关于血压测量。" for i in range(60))
    sections = (Section(level=1, heading="监测", text=body),)
    chunks = chunk_document(
        "doc-1", sections, count_tokens=_counter, max_tokens=100, overlap_tokens=16
    )
    assert len(chunks) > 1
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(c.heading_path == ("监测",) for c in chunks)
    assert all(_counter(c.text) <= 100 for c in chunks)
    # 相邻块共享尾部句子（ADR 0077 overlap；预算 16 token ≈ 一句）
    assert any(chunks[0].text.endswith(chunks[1].text[:k]) for k in range(4, 17)), (
        "第 2 块开头应复现第 1 块的结尾句子"
    )


def test_table_section_stays_atomic_even_when_oversized():
    rows = "\n".join(f"| 药物{i} | 剂量{i}mg | 注意事项{i} |" for i in range(80))
    sections = (Section(level=1, heading="剂量对照表", text=rows),)
    chunks = chunk_document("doc-1", sections, count_tokens=_counter, max_tokens=50)
    assert len(chunks) == 1
    assert chunks[0].text == rows
