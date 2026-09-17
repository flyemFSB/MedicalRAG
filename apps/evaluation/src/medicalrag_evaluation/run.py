"""评测执行器（质量门禁：PR 门禁跑 eval-retrieval 检索评测；RC 门禁跑 eval-answer 综合评测，ADR 0080）。

- ``eval-retrieval``：评估确定性检索指标（Recall@k、MRR、nDCG@k、Top-1 命中率 chunk_hit_at_1、空召回率、P95 延迟），无需外部模型服务。
  **判决语义**：指标低于 ``_MIN_METRICS`` 下限或空召回率高于上限即以非零状态码退出——无阈值的评测步骤永远是绿的，等于没门禁。
  **覆盖边界**（不得误读）：候选集与分数来自数据集文件，本步**不执行真实检索器**（Qdrant dense+sparse 与融合），
  度量的是指标实现与 fixtures 本身的回归；真实检索路径的集成验证见 docs/testing-seams.md 的「明确不覆盖」登记。
- ``eval-answer``：基于 RAGAS 评估生成答案质量（真实性 faithfulness、回答相关性 answer_relevancy 等），RAGAS 为可选依赖组——未安装时显式拦截报错，严禁静默跳过。

数据集 JSONL 格式定义（每行）：
  {"question": str, "relevant_chunk_ids": [str], "intent_id": str,
   "candidate_chunk_ids": [str], "scores": [float], "latency_ms": float,
   "answer": str | null, "ground_truth": str | null}

命令行调用示例：
  uv run --package medicalrag-evaluation python -m medicalrag_evaluation.run \\
      eval-retrieval fixtures/retrieval.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import cast


def _load(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _reciprocal_rank(rank: int) -> float:
    return 1.0 / rank if rank >= 1 else 0.0


def _dcg(ranks: list[int], k: int) -> float:
    value = 0.0
    for i, rank in enumerate(ranks[:k]):
        if rank == 0:
            continue
        value += 1.0 / math.log2(i + 2)  # 命中位置的对数折损
    return value


def _idcg(k: int, relevant_count: int) -> float:
    """理想 DCG：全部相关块按最优先排列（位置数上限为 min(k, 相关块数)）。

    必须与 ``relevant_count`` 挂钩而非写死常数：否则 relevant > 上限时
    DCG 分子可超过 IDCG 分母，nDCG > 1（指标越界）。
    """
    return sum(1.0 / math.log2(i + 2) for i in range(min(k, relevant_count)))


def eval_retrieval(rows: list[dict[str, object]]) -> dict[str, float]:
    """计算确定性检索质量指标（Recall@k、MRR、nDCG@k、chunk_hit_at_1、空召回率、P95 检索延迟）。

    ``intent_id`` 字段在预计算候选数据面中无法用于意图准确率评估（候选行未携带意图命中信息）；
    指标更名为 ``chunk_hit_at_1`` 以名实相符：度量 Top-1 检索块是否相关。
    意图分类准确率需管线回放（真实调用分类器）后另行评测，见 docs/spec.md 评测章节。
    """
    k = 10
    recall_sum = 0.0
    mrr_sum = 0.0
    ndcg_sum = 0.0
    chunk_hit_at_1 = 0
    empty_recall = 0
    latencies: list[float] = []

    for row in rows:
        relevant = set(cast(list[str], row["relevant_chunk_ids"]))
        candidates = list(cast(list[str], row["candidate_chunk_ids"]))
        scores = list(cast(list[float], row["scores"]))
        latency = float(cast("int | float | str", row.get("latency_ms", 0.0)))
        latencies.append(latency)
        if not relevant:
            empty_recall += 1
            continue

        # 按综合匹配得分降序截取 Top-k 检索候选集
        ordered = [
            cid for cid, _ in sorted(zip(candidates, scores, strict=True), key=lambda p: -p[1])
        ][:k]
        ranks = [i + 1 for i, cid in enumerate(ordered) if cid in relevant]
        recall = len(ranks) / len(relevant)
        recall_sum += recall
        if ranks:
            mrr_sum += _reciprocal_rank(ranks[0])
            ndcg_sum += _dcg(
                [1 if i in ranks else 0 for i in range(1, len(ordered) + 1)], k
            ) / _idcg(k, len(relevant))
        if ordered and ordered[0] in relevant:
            chunk_hit_at_1 += 1

    n = len(rows)
    latencies_sorted = sorted(latencies)
    p95 = latencies_sorted[math.ceil(0.95 * len(latencies_sorted)) - 1] if latencies_sorted else 0.0
    return {
        "recall_at_k": round(recall_sum / n, 4) if n else 0.0,
        "mrr": round(mrr_sum / n, 4) if n else 0.0,
        "ndcg_at_k": round(ndcg_sum / n, 4) if n else 0.0,
        "chunk_hit_at_1": round(chunk_hit_at_1 / n, 4) if n else 0.0,
        "empty_recall_rate": round(empty_recall / n, 4) if n else 0.0,
        "p95_latency_ms": round(p95, 1),
    }


# 检索指标的判决下限：门禁必须能失败（无阈值的评测步骤永远是绿的）。
# 取值 = 2026-09-14 对 fixtures/retrieval.jsonl 实测值（recall/mrr/chunk_hit_at_1 = 0.9333，
# empty_recall_rate = 0.0667）向下留一档余量。改这些数字等于改门禁松紧，属评审对象。
_MIN_METRICS = {"recall_at_k": 0.90, "chunk_hit_at_1": 0.90, "mrr": 0.90}
_MAX_EMPTY_RECALL_RATE = 0.10


def gate_failures(metrics: dict[str, float]) -> list[str]:
    """按 ``_MIN_METRICS`` / ``_MAX_EMPTY_RECALL_RATE`` 判定检索指标；返回未达标描述（空 = 通过）。"""
    failures = [
        f"{name}={metrics[name]:.4f} 低于下限 {floor}"
        for name, floor in _MIN_METRICS.items()
        if metrics[name] < floor
    ]
    if metrics["empty_recall_rate"] > _MAX_EMPTY_RECALL_RATE:
        failures.append(
            f"empty_recall_rate={metrics['empty_recall_rate']:.4f} 高于上限 {_MAX_EMPTY_RECALL_RATE}"
        )
    return failures


def eval_answer(rows: list[dict[str, object]]) -> dict[str, float] | None:
    """计算 RAGAS 答案生成质量指标（真实性 faithfulness、回答相关性 answer_relevancy）；返回 None 表示质量门禁未通过。

    RAGAS 为可选依赖包，但 eval-answer 属于发布候选（RC）阶段的强制门禁：
    若缺少依赖或评测集无有效答案样本，必须显式抛出错误并以非零状态码退出，严禁静默假通过。
    """
    try:
        from ragas import evaluate  # type: ignore[reportMissingImports]  # 隔离环境注入的可选依赖
        from ragas.dataset_schema import (  # type: ignore[reportMissingImport]
            EvaluationDataset,
            SingleTurnSample,
        )
        from ragas.metrics import (  # type: ignore[reportMissingImport]
            answer_relevancy,
            faithfulness,
        )
    except ImportError:
        print(
            "门禁失败：eval-answer 需在隔离解释器环境运行（ragas→instructor 与项目 openai>=3.11 冲突，"
            "不入主 lock）：`uv run --no-project -p 3.12 --with ragas==0.4.3 "
            "python apps/evaluation/src/medicalrag_evaluation/run.py eval-answer <dataset>`。",
            file=sys.stderr,
        )
        return None

    samples = [
        SingleTurnSample(
            user_input=str(row["question"]),
            response=str(row.get("answer") or ""),
            reference=str(row.get("ground_truth") or ""),
        )
        for row in rows
        if row.get("answer")
    ]
    if not samples:
        print("门禁失败：eval-answer 数据集中没有带 answer 的样本。", file=sys.stderr)
        return None
    result = evaluate(
        dataset=EvaluationDataset(samples=samples), metrics=[faithfulness, answer_relevancy]
    )
    return {"faithfulness": result[faithfulness], "answer_relevancy": result[answer_relevancy]}


def main() -> int:
    parser = argparse.ArgumentParser(description="MedicalRAG 评测 runner")
    parser.add_argument("task", choices=["eval-retrieval", "eval-answer"], help="评测任务")
    parser.add_argument("dataset", type=Path, help="JSONL 数据集路径")
    args = parser.parse_args()

    rows = _load(args.dataset)
    if not rows:
        print("数据集为空。", file=sys.stderr)
        return 1
    if args.task == "eval-retrieval":
        metrics = eval_retrieval(rows)
        failures = gate_failures(metrics)
        print(
            json.dumps(
                {
                    "task": args.task,
                    "samples": len(rows),
                    "metrics": metrics,
                    "thresholds": {**_MIN_METRICS, "empty_recall_rate_max": _MAX_EMPTY_RECALL_RATE},
                    "failures": failures,
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        if failures:
            print("检索指标未达下限：" + "；".join(failures), file=sys.stderr)
            return 1
        return 0
    answer_metrics = eval_answer(rows)
    if answer_metrics is None:
        return 2  # eval-answer 是 RC 门禁：缺依赖/缺样本显式失败
    metrics = answer_metrics
    print(
        json.dumps(
            {"task": args.task, "samples": len(rows), "metrics": metrics},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
