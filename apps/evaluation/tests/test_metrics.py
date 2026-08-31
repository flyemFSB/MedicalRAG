"""eval-retrieval 确定性指标检查。"""

from medicalrag_evaluation.run import eval_retrieval


def _row(relevant, candidates, scores, latency=10.0):
    return {
        "question": "q",
        "relevant_chunk_ids": relevant,
        "candidate_chunk_ids": candidates,
        "scores": scores,
        "intent_id": "disease-info",
        "latency_ms": latency,
    }


def test_recall_mrr_ndcg_are_deterministic():
    rows = [
        _row(["c1"], ["c1", "c2", "c3"], [0.9, 0.5, 0.2]),
        _row(["c2"], ["c1", "c2"], [0.4, 0.8]),
        _row([], ["c1", "c2"], [0.3, 0.2]),  # 无相关 → 计入空召回率
    ]
    metrics = eval_retrieval(rows)
    assert metrics["recall_at_k"] > 0
    assert 0 <= metrics["mrr"] <= 1
    assert 0 <= metrics["ndcg_at_k"] <= 1
    assert metrics["intent_top1"] == round(2 / 3, 4)  # 两行有相关且 top1 均命中
    assert metrics["empty_recall_rate"] == round(1 / 3, 4)
    assert metrics["p95_latency_ms"] == 10.0


def test_top1_hit_counts():
    rows = [
        _row(["c1"], ["c1", "c9"], [0.9, 0.1]),
        _row(["c9"], ["c1", "c9"], [0.9, 0.1]),
    ]
    metrics = eval_retrieval(rows)
    assert metrics["intent_top1"] == 0.5


def test_citation_accuracy_counts_valid_refs():
    from medicalrag_evaluation.run import eval_citation_accuracy

    rows = [
        {"answer": "收缩压诊断界值为 140 mmHg [1]，需低盐饮食 [2]。", "evidence_count": 2},
        {"answer": "证据显示 [1] 有效；越界引用 [3]。", "evidence_count": 1},
        {"answer": "无引用的回答。", "evidence_count": 1},
    ]
    metrics = eval_citation_accuracy(rows)
    # 引用共 4 条，有效 3 条（[3] 越界）
    assert metrics["citation_accuracy"] == 0.75
    # 3 条答案中 2 条带引用
    assert metrics["citation_coverage"] == round(2 / 3, 4)


def test_citation_accuracy_empty_is_zero():
    from medicalrag_evaluation.run import eval_citation_accuracy

    assert (
        eval_citation_accuracy([{"answer": "没有引用", "evidence_count": 1}])["citation_accuracy"]
        == 0.0
    )
