"""Evaluate retrieval quality, refusal behavior, latency and retrieval ablations."""

import argparse
import json
import math
import time
from pathlib import Path

from sqlalchemy import select

from app.database import get_session_factory
from app.evaluation import EvaluationService
from app.main import embedder, retrieval, settings
from app.models import Document
from app.pgvector_store import PgVectorStore
from app.rag import RetrievalService
from app.retrieval_quality import quality_gate, gate_details


from app.evaluation_runner import percentile, source_coverage, published_source_coverage, evaluate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="materials/eval/questions-150-v2.json")
    parser.add_argument("--output", default="reports/rag-evaluation-dsa-v2-latest.json")
    parser.add_argument("--warmup", action="store_true",
                        help="先执行一次只读查询，并单独记录首次查询耗时；正式指标只计算预热后请求")
    parser.add_argument("--vector-weight", type=float, default=None,
                        help="仅本次评测使用的向量权重；不修改线上管理员设置")
    parser.add_argument("--no-persist", action="store_true",
                        help="仅生成本地 JSON 报告，不写入管理员质量评测历史（适用于参数试验）")
    args = parser.parse_args()
    if args.vector_weight is not None and not 0 <= args.vector_weight <= 1:
        parser.error("--vector-weight 必须在 0 到 1 之间")
    dataset = json.loads(Path(args.cases).read_text(encoding="utf-8"))
    cases = dataset["cases"]
    knowledge_base_id = dataset.get("knowledge_base_id")
    coverage = (published_source_coverage(cases, knowledge_base_id)
                if settings.storage_backend.lower() in {"postgres", "pgvector"} else None)
    primary_service = retrieval
    if args.vector_weight is not None:
        if settings.storage_backend.lower() not in {"postgres", "pgvector"}:
            parser.error("--vector-weight 仅支持 PostgreSQL/pgvector 评测")
        primary_service = RetrievalService(
            PgVectorStore(get_session_factory(), embedder, vector_weight=args.vector_weight),
            min_score=settings.retrieval_min_score, top_k=settings.retrieval_top_k,
        )
    warmup_latency_ms = None
    if args.warmup:
        warmup_started = time.perf_counter()
        primary_service.retrieve("课程资料检索预热", knowledge_base_id)
        warmup_latency_ms = round((time.perf_counter() - warmup_started) * 1000, 2)
    primary_metrics, details = evaluate(
        primary_service, cases, keep_details=True, knowledge_base_id=knowledge_base_id)
    ablations = {}
    if settings.storage_backend.lower() in {"postgres", "pgvector"}:
        for label, weight in (("vector_only", 1.0), ("keyword_only", 0.0)):
            candidate_store = PgVectorStore(get_session_factory(), embedder, vector_weight=weight)
            candidate_service = RetrievalService(candidate_store, min_score=settings.retrieval_min_score, top_k=settings.retrieval_top_k)
            ablations[label], _ = evaluate(
                candidate_service, cases, keep_details=False, knowledge_base_id=knowledge_base_id)
    run_name = f"计算机课程 RAG 检索评测 · {dataset['dataset_version']}"
    if args.vector_weight is not None:
        run_name += f" · 试验权重 {args.vector_weight:g}"
    gates = quality_gate(primary_metrics, coverage)
    report = {"name": run_name, "dataset_version": dataset["dataset_version"],
              "knowledge_base_id": knowledge_base_id,
              "case_count": len(cases), "metrics": primary_metrics, "quality_gate": gates,
              "ablations": ablations, "details": details,"gate_details":gate_details(primary_metrics,coverage)}
    if coverage is not None:
        report["source_coverage"] = coverage
    if warmup_latency_ms is not None:
        report["warmup_query_ms"] = warmup_latency_ms
    if args.vector_weight is not None:
        report["evaluation_vector_weight"] = args.vector_weight
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.no_persist:
        EvaluationService(get_session_factory()).create(
            name=report["name"], dataset_version=dataset["dataset_version"], case_count=len(cases),
            metrics={**primary_metrics, "quality_gate": gates, "gate_details":report['gate_details'], "ablations": ablations,
                     **({"source_coverage": coverage} if coverage is not None else {}),
                     "evaluation_vector_weight": args.vector_weight if args.vector_weight is not None
                     else settings.retrieval_vector_weight,
                     "warmup_query_ms": warmup_latency_ms},
            details=details, created_by="evaluation-cli")
    print(json.dumps({"dataset_version": dataset["dataset_version"], "case_count": len(cases),
                      **({"source_coverage": coverage} if coverage is not None else {}),
                      **({"warmup_query_ms": warmup_latency_ms} if warmup_latency_ms is not None else {}),
                      **({"evaluation_vector_weight": args.vector_weight} if args.vector_weight is not None else {}),
                      **primary_metrics}, ensure_ascii=False, indent=2))
    print("QUALITY_GATE=" + ("PASS" if gates else "FAIL"))
    return 0 if gates else 1


if __name__ == "__main__":
    raise SystemExit(main())
