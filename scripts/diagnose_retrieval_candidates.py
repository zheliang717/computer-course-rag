"""Read-only comparison of vector candidates and lexical rescue on four fixed datasets.

Run with the same PostgreSQL and embedding environment as the API. Nothing is
written to the application database or the evaluation history.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

from app.database import get_session_factory
from app.hybrid_store import keyword_overlap
from app.main import embedder, settings
from app.models import Chunk, Document
from app.pgvector_store import PgVectorStore


DATASETS = (
    Path("materials/eval/learningos-address-space-zh-13.json"),
    Path("materials/eval/os-net-zh-20.json"),
    Path("materials/eval/mdn-http-zh-10.json"),
    Path("materials/eval/questions-150-v2.json"),
)


def score_rows(case: dict, knowledge_base_id: str) -> list[dict]:
    vector = embedder.embed([case["question"]])[0]
    distance = Chunk.embedding.cosine_distance(vector)
    statement = (
        select(Chunk.id, Document.id.label("document_id"), Document.filename,
               Chunk.page_number, Chunk.content, distance.label("distance"))
        .join(Document, Document.id == Chunk.document_id)
        .where(Document.knowledge_base_id == UUID(knowledge_base_id),
               Document.publication_status == "published", Chunk.embedding.is_not(None))
    )
    with get_session_factory()() as session:
        rows = session.execute(statement).all()
    return [
        {"id": str(row.id), "document_id": str(row.document_id),
         "document": row.filename, "page": row.page_number,
         "vector": max(0.0, 1.0 - float(row.distance)),
         "keyword": keyword_overlap(case["question"], row.content)}
        for row in rows
    ]


def rank(scored: list[dict], bonus: float, threshold: float, *, query: str,
         vector_limit: int = 40, lexical_limit: int = 0) -> list[dict]:
    vector_order = sorted(scored, key=lambda item: item["vector"], reverse=True)
    lexical_order = sorted(scored, key=lambda item: item["keyword"], reverse=True)
    baseline_ids = {item["id"] for item in vector_order[: settings.retrieval_top_k * 8]}
    candidate_ids = {item["id"] for item in vector_order[:vector_limit]}
    if lexical_limit:
        candidate_ids.update(item["id"] for item in lexical_order[:lexical_limit]
                             if item["keyword"] >= threshold)
    candidates = [item.copy() for item in scored if item["id"] in candidate_ids]
    effective_bonus = bonus if PgVectorStore._supports_lexical_rescue(query) else 0.0
    for item in candidates:
        item["score"] = min(1.0, settings.retrieval_vector_weight * item["vector"]
                            + (1.0 - settings.retrieval_vector_weight) * item["keyword"]
                            + min(PgVectorStore._lexical_rescue_cap,
                                  effective_bonus * max(0.0, item["keyword"] - threshold))
                            * int(item["vector"] < PgVectorStore._lexical_rescue_max_vector_score
                                  and item["id"] not in baseline_ids))
    return sorted(candidates, key=lambda item: item["score"], reverse=True)[: settings.retrieval_top_k]


def main() -> None:
    if settings.storage_backend.lower() not in {"postgres", "pgvector"}:
        raise SystemExit("Only run against the configured PostgreSQL retrieval database")
    datasets = [json.loads(path.read_text(encoding="utf-8")) for path in DATASETS]
    cached = {
        (dataset["dataset_version"], case["id"]): score_rows(
            case, case.get("knowledge_base_id", dataset.get("knowledge_base_id")))
        for dataset in datasets for case in dataset["cases"]
    }
    failure_rows = cached[("learningos-address-space-zh-13-v1", "addr-generation")]
    target_rows = [item for item in failure_rows if item["document_id"] == "06c8196e-22a8-5368-9f49-3290c5a5bc8a"]
    vector_order = sorted(failure_rows, key=lambda item: item["vector"], reverse=True)
    lexical_order = sorted(failure_rows, key=lambda item: item["keyword"], reverse=True)
    print(json.dumps({"case": "addr-generation", "target_chunks": [
        {"page": item["page"], "vector_rank": vector_order.index(item) + 1,
         "keyword_rank": lexical_order.index(item) + 1,
         "vector": round(item["vector"], 4), "keyword": round(item["keyword"], 4)}
        for item in target_rows]}, ensure_ascii=False))
    for vector_limit, lexical_limit, bonus, threshold in (
        (40, 0, 0.0, 0.0),
        (80, 0, 1.0, 0.5),
        (40, 20, 1.0, 0.5),
        (80, 20, 1.0, 0.5),
    ):
        results = []
        for dataset in datasets:
            hits = missed = page_hits = page_missed = refused = 0
            details = {}
            for case in dataset["cases"]:
                ranked = rank(cached[(dataset["dataset_version"], case["id"])], bonus, threshold,
                              query=case["question"], vector_limit=vector_limit,
                              lexical_limit=lexical_limit)
                accepted = [item for item in ranked if item["score"] >= settings.retrieval_min_score]
                if case["kind"] == "negative":
                    refused += int(not accepted)
                    continue
                expected_ids = case.get("expected_document_ids")
                matches = [(item["document_id"] in expected_ids if expected_ids
                            else item["document"] in case["expected_documents"])
                           for item in accepted]
                rank_document = next((index + 1 for index, matched in enumerate(matches)
                                      if matched), None)
                rank_page = next((index + 1 for index, (item, matched) in enumerate(zip(accepted, matches))
                                  if matched and item["page"] in case.get("expected_pages", [])), None)
                hits += int(rank_document is not None)
                missed += int(rank_document is None)
                if case.get("expected_pages"):
                    page_hits += int(rank_page is not None)
                    page_missed += int(rank_page is None)
                if rank_document is None or case.get("expected_pages") and rank_page is None:
                    details[case["id"]] = {
                        "document_rank": rank_document, "page_rank": rank_page,
                        "top": [(item["document"], item["page"], round(item["score"], 3),
                                 round(item["keyword"], 3)) for item in accepted],
                    }
            results.append({
                "dataset": dataset["dataset_version"], "document_hits": hits, "document_misses": missed,
                "page_hits": page_hits, "page_misses": page_missed, "negative_refusals": refused,
                "missed_cases": details,
            })
        print(json.dumps({"vector_limit": vector_limit, "lexical_limit": lexical_limit,
                          "bonus": bonus, "threshold": threshold, "results": results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
