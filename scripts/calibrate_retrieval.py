"""Compare acceptance thresholds on both course-scoped evaluation datasets."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

from app.config import get_settings
from app.main import store
from app.rag import RetrievalService


evaluate = runpy.run_path("scripts/evaluate_retrieval.py")["evaluate"]
datasets = [
    json.loads(Path(path).read_text(encoding="utf-8"))
    for path in ("materials/eval/questions-150-v2.json", "materials/eval/os-net-zh-20.json")
]
settings = get_settings()

for threshold in (0.40, 0.43, 0.45, 0.47, 0.50, 0.55, 0.60):
    service = RetrievalService(store, min_score=threshold, top_k=settings.retrieval_top_k)
    summary = {"threshold": threshold}
    for dataset in datasets:
        metrics, _ = evaluate(
            service, dataset["cases"], keep_details=False,
            knowledge_base_id=dataset.get("knowledge_base_id"),
        )
        summary[dataset["dataset_version"]] = {
            "recall_at_5": metrics["recall_at_5"],
            "refusal_accuracy": metrics["refusal_accuracy"],
            "citation_accuracy": metrics["citation_accuracy"],
        }
    print(json.dumps(summary, ensure_ascii=False), flush=True)
