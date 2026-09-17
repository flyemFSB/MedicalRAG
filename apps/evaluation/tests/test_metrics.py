"""eval-retrieval 确定性指标检查。"""

from medicalrag_evaluation.run import _MIN_METRICS as _MIN_METRICS_TEST
from medicalrag_evaluation.run import eval_retrieval, gate_failures


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
    assert metrics["chunk_hit_at_1"] == round(2 / 3, 4)  # 两行有相关且 top1 均命中
    assert metrics["empty_recall_rate"] == round(1 / 3, 4)
    assert metrics["p95_latency_ms"] == 10.0


def test_top1_hit_counts():
    rows = [
        _row(["c1"], ["c1", "c9"], [0.9, 0.1]),
        _row(["c9"], ["c1", "c9"], [0.9, 0.1]),
    ]
    metrics = eval_retrieval(rows)
    assert metrics["chunk_hit_at_1"] == 0.5


def test_gate_fails_when_metrics_drop_below_floor():
    """门禁必须能失败：检索指标跌破下限时 eval-retrieval 要以非零码退出。"""
    # top-1 未命中且相关块未进候选集：recall/mrr/hit@1 均为 0
    metrics = eval_retrieval([_row(["c9"], ["c1", "c2"], [0.9, 0.5])])
    failures = gate_failures(metrics)

    assert {"recall_at_k", "mrr", "chunk_hit_at_1"} <= {
        message.split("=")[0] for message in failures
    }
    assert gate_failures(dict.fromkeys(_MIN_METRICS_TEST, 1.0) | {"empty_recall_rate": 0.0}) == []
