"""结构优先分块检查（ADR 0034/0087：标题路径溯源 + tolerance 原子性 + 表格 KV 特殊化）。"""

import pytest

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
        "doc-1",
        sections,
        count_tokens=_counter,
        max_tokens=100,
        overlap_tokens=16,
        tolerance_tokens=100,  # 测试显式关掉 tolerance 原子性，聚焦句子切分行为
    )
    assert len(chunks) > 1
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert all(c.heading_path == ("监测",) for c in chunks)
    assert all(_counter(c.text) <= 100 for c in chunks)
    # 相邻块共享尾部句子（ADR 0077 overlap；预算 16 token ≈ 一句）
    assert any(chunks[0].text.endswith(chunks[1].text[:k]) for k in range(4, 17)), (
        "第 2 块开头应复现第 1 块的结尾句子"
    )


def test_section_within_tolerance_stays_atomic():
    """ADR 0087 tolerance 双阶段预算：超出 max_tokens 但在 tolerance 内的章节保持原子单块。"""
    body = "".join(f"第{i}句内容关于血压测量。" for i in range(30))  # ≈ 420 token > 100
    sections = (Section(level=1, heading="监测", text=body),)
    chunks = chunk_document(
        "doc-1", sections, count_tokens=_counter, max_tokens=100, tolerance_tokens=500
    )
    assert len(chunks) == 1
    assert chunks[0].text == body


def test_pipe_table_splits_by_rows_and_header_stays_out_of_embedding_text():
    """ADR 0087 表格特殊化：行级切分（行内原子）、每块重带表头展示、向量文本只取 KV 正文。"""
    header = "| 药物 | 剂量 | 注意事项 |"
    separator = "| --- | --- | --- |"
    body_rows = [f"| 药物{i} | 剂量{i}mg | 注意事项{i} |" for i in range(8)]
    sections = (
        Section(level=1, heading="剂量对照表", text="\n".join([header, separator, *body_rows])),
    )
    chunks = chunk_document(
        "doc-1", sections, count_tokens=_counter, max_tokens=120, table_rows_per_chunk=3
    )
    # 8 行 ÷ 每块 3 行 → 3 块（行数硬上限）
    assert len(chunks) == 3
    for chunk in chunks:
        # 展示正文携带表头（markdown 完整表格）
        assert chunk.text.startswith("| 药物 | 剂量 | 注意事项 |")
        # 向量文本为 KV 正文：不含表头行，但保留标题路径前缀
        embedded = embedding_text(chunk)
        assert embedded.startswith("剂量对照表\n")
        assert "药物: " in embedded
        assert "| 药物 |" not in embedded.split("\n", 1)[1]
    # 行不重不漏且行内原子
    kv_rows = [line for chunk in chunks for line in embedding_text(chunk).splitlines()[1:]]
    assert len(kv_rows) == 8
    assert kv_rows[0] == "药物: 药物0; 剂量: 剂量0mg; 注意事项: 注意事项0"


def test_html_table_splits_with_header_repeat_and_kv_embedding():
    """MinerU HTML 表：剥 colspan/rowspan=1，按 <tr> 切分，每块包回 <table> 外壳。"""
    rows = "".join(
        f'<tr><td colspan="1">药物{i}</td><td rowspan="1">剂量{i}mg</td></tr>' for i in range(5)
    )
    text = f"<table><tr><th>药物</th><th>剂量</th></tr>{rows}</table>"
    sections = (Section(level=1, heading="用药表", text=text),)
    chunks = chunk_document(
        "doc-1", sections, count_tokens=_counter, max_tokens=120, table_rows_per_chunk=2
    )
    assert len(chunks) == 3  # 5 行 ÷ 每块 2 行
    for chunk in chunks:
        assert chunk.text.startswith("<table>")
        assert chunk.text.count("<tr>") >= 2  # 表头 + 数据行
        assert 'colspan="1"' not in chunk.text
        embedded = embedding_text(chunk)
        assert "药物: 药物" in embedded
        assert "<table>" not in embedded


def test_table_single_oversized_row_stays_atomic():
    """行内原子：单行超预算也整行独立成块，绝不切断一行。"""
    header = "| 药物 | 说明 |"
    long_row = f"| 长药名 | {'长' * 300} |"
    sections = (Section(level=1, heading="表", text=f"{header}\n| --- | --- |\n{long_row}"),)
    chunks = chunk_document("doc-1", sections, count_tokens=_counter, max_tokens=50)
    assert len(chunks) == 1
    assert "长" * 300 in chunks[0].text
    assert "长" * 300 in embedding_text(chunks[0])


def test_empty_section_produces_no_chunk():
    """空章节/空切片不进入嵌入与索引（避免低质召回源）。"""
    assert chunk_document("doc-1", (Section(level=1, heading="空", text="   "),)) == ()


def test_section_level_must_start_at_one():
    """层级非法会让 heading_path 静默吞掉上一级标题（溯源失真）——fail-fast 而非静默走样。"""
    with pytest.raises(ValueError, match="层级必须从 1 起始"):
        chunk_document("doc-1", (Section(level=0, heading="错位", text="正文"),))


def test_table_shaped_text_without_parsable_rows_stays_plain():
    """多数行以 | 开头但无完整表格行（缺首尾竖线）：整段按普通正文处理，不吞内容。"""
    text = "|只有开头竖线没有收尾"
    chunks = chunk_document(
        "doc-1", (Section(level=1, heading="表", text=text),), count_tokens=_counter, max_tokens=50
    )
    assert [c.text for c in chunks] == [text]


def test_table_header_without_body_rows_stays_plain():
    """只有表头与分隔行、无数据行：无切分价值，整段保留（不得丢表头）。"""
    text = "| 药物 | 剂量 |\n| --- | --- |"
    chunks = chunk_document(
        "doc-1", (Section(level=1, heading="表", text=text),), count_tokens=_counter, max_tokens=50
    )
    assert [c.text for c in chunks] == [text]


def test_html_table_with_one_cell_row_stays_plain():
    """HTML 表行数不足（<tr> 多但仅一行有单元格）：不切分，整段保留。"""
    text = "<table><tr><td>只有一行有单元格</td></tr><tr>无单元格</tr></table>"
    chunks = chunk_document(
        "doc-1", (Section(level=1, heading="表", text=text),), count_tokens=_counter, max_tokens=50
    )
    assert [c.text for c in chunks] == [text]


def test_single_oversized_sentence_splits_by_character_ratio():
    """单句超预算（无句末标点）时的兜底保护：按字符比例切分，不丢字符。"""
    body = "血" * 300
    chunks = chunk_document(
        "doc-1",
        (Section(level=1, heading="长句", text=body),),
        count_tokens=_counter,
        max_tokens=50,
        tolerance_tokens=50,
    )
    assert len(chunks) > 1
    assert all(_counter(c.text) <= 50 for c in chunks)
    assert "".join(c.text for c in chunks) == body


def test_overlap_tail_is_trimmed_to_stay_within_budget():
    """重叠预算大于单句时，尾部累积句与当前句一起超预算：从最早的尾句依次丢弃，块不得超限。"""
    sentences = "".join(f"{i:02d}" + "字" * 27 + "。" for i in range(1, 13))  # 每句 30 token
    chunks = chunk_document(
        "doc-1",
        (Section(level=1, heading="监测", text=sentences),),
        count_tokens=_counter,
        max_tokens=100,
        overlap_tokens=90,
        tolerance_tokens=100,
    )
    assert len(chunks) > 1
    assert all(_counter(c.text) <= 100 for c in chunks)
