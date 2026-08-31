"""评测执行器（质量门禁：PR 门禁跑 eval-retrieval 检索评测；RC 门禁跑 eval-answer 与 eval-citation 综合评测）。

- ``eval-retrieval``：评估确定性检索指标（Recall@k、MRR、nDCG@k、意图分类 Top-1 准确率、空召回率、P95 延迟），无需外部模型服务；
- ``eval-answer``：基于 RAGAS 评估生成答案质量（真实性 faithfulness、回答相关性 answer_relevancy 等），RAGAS 为可选依赖组——未安装时显式拦截报错，严禁静默跳过；
- ``eval-citation``：评估生成答案中的证据引用标号准确率与证据覆盖率。

数据集 JSONL 格式定义（每行）：
  {"question": str, "relevant_chunk_ids": [str], "intent_id": str,
   "candidate_chunk_ids": [str], "scores": [float], "latency_ms": float,
   "answer": str | null, "ground_truth": str | null, "evidence_count": int | null}

命令行调用示例：
  uv run --package medicalrag-evaluation python -m medicalrag_evaluation.run \\
      eval-retrieval fixtures/retrieval.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import re
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


def _idcg(k: int) -> float:
    return sum(1.0 / math.log2(i + 2) for i in range(min(k, 5)))


def eval_retrieval(rows: list[dict[str, object]]) -> dict[str, float]:
    """计算确定性检索质量指标（Recall@k、MRR、nDCG@k、意图 Top-1 命中率、空召回率、P95 检索延迟）。"""
    k = 10
    recall_sum = 0.0
    mrr_sum = 0.0
    ndcg_sum = 0.0
    intent_top1_hits = 0
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
        ordered = [cid for cid, _ in sorted(zip(candidates, scores), key=lambda p: -p[1])][:k]
        ranks = [i + 1 for i, cid in enumerate(ordered) if cid in relevant]
        recall = len(ranks) / len(relevant)
        recall_sum += recall
        if ranks:
            mrr_sum += _reciprocal_rank(ranks[0])
            ndcg_sum += _dcg(
                [1 if i in ranks else 0 for i in range(1, len(ordered) + 1)], k
            ) / _idcg(k)
        if ordered and ordered[0] in relevant:
            intent_top1_hits += 1

    n = len(rows)
    latencies_sorted = sorted(latencies)
    p95 = latencies_sorted[math.ceil(0.95 * len(latencies_sorted)) - 1] if latencies_sorted else 0.0
    return {
        "recall_at_k": round(recall_sum / n, 4) if n else 0.0,
        "mrr": round(mrr_sum / n, 4) if n else 0.0,
        "ndcg_at_k": round(ndcg_sum / n, 4) if n else 0.0,
        "intent_top1": round(intent_top1_hits / n, 4) if n else 0.0,
        "empty_recall_rate": round(empty_recall / n, 4) if n else 0.0,
        "p95_latency_ms": round(p95, 1),
    }


def eval_answer(rows: list[dict[str, object]]) -> dict[str, float] | None:
    """计算 RAGAS 答案生成质量指标（真实性 faithfulness、回答相关性 answer_relevancy）；返回 None 表示质量门禁未通过。

    RAGAS 为可选依赖包，但 eval-answer 属于发布候选（RC）阶段的强制门禁：
    若缺少依赖或评测集无有效答案样本，必须显式抛出错误并以非零状态码退出，严禁静默假通过（ADR 0080）。
    """
    try:
        from ragas import evaluate  # type: ignore[reportMissingImports]  # 可选依赖（eval group）
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
            "门禁失败：eval-answer 需要安装可选依赖 `uv sync --group eval`（ragas）。",
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


_CITATION_RE = re.compile(r"\[(\d+)\]")


def eval_citation_accuracy(rows: list[dict[str, object]]) -> dict[str, float]:
    """计算证据引用标注文档准确率（引用标号是否严格落在提供证据集有效区间内）。

    数据集单行需携带 ``answer`` 与 ``evidence_count``（注入证据总条数）。
    citation_accuracy = 有效引用次数 / 全部引用次数；
    citation_coverage = 包含至少一条有效引用的回答占比；无任何引用时 accuracy 计为 0.0。
    """
    total_refs = 0
    valid_refs = 0
    answers_with_refs = 0
    answered = 0
    for row in rows:
        answer = row.get("answer")
        if not answer:
            continue
        answered += 1
        evidence_count = int(cast("int | float | str", row.get("evidence_count", 0) or 0))
        refs = [int(m) for m in _CITATION_RE.findall(str(answer))]
        if refs:
            answers_with_refs += 1
        total_refs += len(refs)
        valid_refs += sum(1 for r in refs if 1 <= r <= evidence_count)
    return {
        "citation_accuracy": round(valid_refs / total_refs, 4) if total_refs else 0.0,
        "citation_coverage": round(answers_with_refs / answered, 4) if answered else 0.0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="MedicalRAG 评测 runner")
    parser.add_argument(
        "task", choices=["eval-retrieval", "eval-answer", "eval-citation"], help="评测任务"
    )
    parser.add_argument("dataset", type=Path, help="JSONL 数据集路径")
    args = parser.parse_args()

    rows = _load(args.dataset)
    if not rows:
        print("数据集为空。", file=sys.stderr)
        return 1
    if args.task == "eval-retrieval":
        metrics = eval_retrieval(rows)
    elif args.task == "eval-citation":
        metrics = eval_citation_accuracy(rows)
    else:
        answer_metrics = eval_answer(rows)
        if answer_metrics is None:
            return 2  # eval-answer 是 RC 门禁：缺依赖/缺样本显式失败（ADR 0080）
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
