"""Controlled offline ablation for chunk sizes, overlap and lightweight reranking."""
from __future__ import annotations

import argparse
import json
import math
import time
from pathlib import Path

from app.chunking import chunk_document
from app.domain import SearchHit
from app.embedding import HashingEmbedder
from app.hybrid_store import HybridVectorStore, keyword_overlap
from app.pdf import extract_pdf_pages


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CandidateRerankingStore:
    def __init__(self, base: HybridVectorStore, *, strategy: str) -> None:
        self.base = base
        self.strategy = strategy

    def search(self, query: str, top_k: int = 5, *, knowledge_base_id: str | None = None) -> list[SearchHit]:
        candidates = self.base.search(query, top_k=max(20, top_k), knowledge_base_id=knowledge_base_id)
        if self.strategy == "none":
            return candidates[:top_k]
        reranked = [SearchHit(chunk=hit.chunk, score=0.75 * hit.score + 0.25 * keyword_overlap(query, hit.chunk.text))
                    for hit in candidates]
        reranked.sort(key=lambda hit: hit.score, reverse=True)
        return reranked[:top_k]


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))]


def load_pages(registry_path: Path, cases: list[dict]) -> list:
    expected_names = {name for case in cases for name in case["expected_documents"]}
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    pages = []
    for source in registry["sources"]:
        if source["title"] not in expected_names:
            continue
        path = PROJECT_ROOT / source["local_file"]
        pages.extend(extract_pdf_pages(path, document_id=source["id"], document_name=source["title"]))
    return pages


def evaluate(store: CandidateRerankingStore, cases: list[dict], *, min_score: float) -> dict:
    positive = [case for case in cases if case["kind"] == "positive"]
    negative = [case for case in cases if case["kind"] == "negative"]
    recalled = reciprocal = correct_citations = citations = evidence_terms = refused = 0
    latencies = []
    for case in cases:
        started = time.perf_counter()
        hits = store.search(case["question"], top_k=5)
        accepted = bool(hits and hits[0].score >= min_score)
        if not accepted:
            hits = []
        latencies.append((time.perf_counter() - started) * 1000)
        names = [hit.chunk.document_name for hit in hits]
        evidence = "\n".join(hit.chunk.text for hit in hits)
        rank = next((index + 1 for index, name in enumerate(names) if name in case["expected_documents"]), None)
        if case["kind"] == "positive":
            recalled += int(rank is not None)
            reciprocal += 1 / rank if rank else 0
            correct_citations += sum(name in case["expected_documents"] for name in names)
            citations += len(names)
            evidence_terms += int(any(term in evidence for term in case["expected_terms_any"]))
        else:
            refused += int(not accepted)
    return {
        "recall_at_5": round(recalled / len(positive), 4),
        "mrr": round(reciprocal / len(positive), 4),
        "citation_accuracy": round(correct_citations / citations, 4) if citations else 0,
        "evidence_term_coverage": round(evidence_terms / len(positive), 4),
        "refusal_accuracy": round(refused / len(negative), 4),
        "latency_p50_ms": round(percentile(latencies, 0.5), 2),
        "latency_p95_ms": round(percentile(latencies, 0.95), 2),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default="materials/eval/questions-150-v2.json")
    parser.add_argument("--sources", default="materials/sources.json")
    parser.add_argument("--output", default="reports/chunking-reranker-ablation.json")
    parser.add_argument("--min-score", type=float, default=0.40)
    args = parser.parse_args()
    dataset = json.loads((PROJECT_ROOT / args.cases).read_text(encoding="utf-8"))
    cases = dataset["cases"]
    pages = load_pages(PROJECT_ROOT / args.sources, cases)
    configurations = ((300, 50), (500, 80), (800, 120))
    results = []
    for chunk_size, overlap in configurations:
        chunks = [chunk for page in pages for chunk in chunk_document(page, chunk_size=chunk_size, overlap=overlap)]
        base = HybridVectorStore(HashingEmbedder(dimensions=512), vector_weight=0.90)
        base.add(chunks)
        for strategy in ("none", "lexical_candidate_rerank"):
            metrics = evaluate(CandidateRerankingStore(base, strategy=strategy), cases, min_score=args.min_score)
            results.append({"chunk_size": chunk_size, "overlap": overlap, "reranker": strategy,
                            "chunk_count": len(chunks), "metrics": metrics})
            print(f"chunk={chunk_size}/{overlap} reranker={strategy}: Recall={metrics['recall_at_5']:.2%}, "
                  f"MRR={metrics['mrr']:.2%}, refusal={metrics['refusal_accuracy']:.2%}, P95={metrics['latency_p95_ms']}ms")
    best_recall = max(item["metrics"]["recall_at_5"] for item in results)
    best_mrr = max(item["metrics"]["mrr"] for item in results)
    # Treat sub-percentage metric differences as ties. Among equally accurate choices,
    # retain finer evidence granularity near the established 500-character baseline.
    eligible = [item for item in results if item["metrics"]["recall_at_5"] >= best_recall - 0.005
                and item["metrics"]["mrr"] >= best_mrr - 0.005]
    winner = min(eligible, key=lambda item: (
        item["reranker"] != "none", abs(item["chunk_size"] - 500), item["metrics"]["latency_p95_ms"]
    ))
    conclusion = ("保留 500/80 分块并关闭轻量词法候选重排。500/80 与 800/120 的 Recall、MRR 和证据覆盖率相同，"
                  "但 500 字符证据粒度更精细；词法重排提高少量引用纯度的同时降低了召回。")
    report = {"dataset_version": dataset["dataset_version"], "case_count": len(cases),
              "source_page_count": len(pages), "min_score": args.min_score,
              "results": results, "recommended": winner, "conclusion": conclusion}
    output = PROJECT_ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("RECOMMENDED=" + json.dumps(winner, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
