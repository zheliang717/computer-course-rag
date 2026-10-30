import math
import time
from sqlalchemy import select
from app.database import get_session_factory
from app.models import Document
from app.rag import RetrievalService

def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(len(ordered) * fraction) - 1))
    return ordered[index]


def source_coverage(cases: list[dict], available: dict[str | None, set[str]],
                    knowledge_base_id: str | None = None) -> dict:
    """Check that each positive case has at least one published target source."""
    missing_cases: list[str] = []
    missing_documents: set[str] = set()
    positive_count = 0
    for case in cases:
        if case["kind"] != "positive":
            continue
        positive_count += 1
        scope = case.get("knowledge_base_id", knowledge_base_id)
        expected = set(case.get("expected_document_ids") or case["expected_documents"])
        if not expected.intersection(available.get(scope, set())):
            missing_cases.append(case["id"])
            missing_documents.update(expected)
    return {"positive_cases": positive_count, "covered_cases": positive_count - len(missing_cases),
            "missing_cases": len(missing_cases), "missing_case_ids": missing_cases,
            "missing_documents": sorted(missing_documents)}


def published_source_coverage(cases: list[dict], knowledge_base_id: str | None) -> dict:
    with get_session_factory()() as session:
        rows = session.execute(select(Document.knowledge_base_id, Document.id, Document.filename).where(
            Document.status == "ready", Document.publication_status == "published")).all()
    available: dict[str | None, set[str]] = {None: set()}
    for scope, document_id, filename in rows:
        available.setdefault(str(scope), set()).update((str(document_id), filename))
        available[None].update((str(document_id), filename))
    return source_coverage(cases, available, knowledge_base_id)


def evaluate(
    service: RetrievalService, cases: list[dict], *, keep_details: bool,
    knowledge_base_id: str | None = None, checkpoint=None,
) -> tuple[dict, list[dict]]:
    positive = [case for case in cases if case["kind"] == "positive"]
    negative = [case for case in cases if case["kind"] == "negative"]
    page_cases = [case for case in positive if case.get("expected_pages")]
    recalled = reciprocal_sum = correct_citations = citation_count = term_hits = refused = 0
    page_recalled = page_reciprocal_sum = correct_page_citations = page_citation_count = 0
    latencies: list[float] = []
    details = []
    started_all = time.perf_counter()
    for index, case in enumerate(cases):
        if checkpoint: checkpoint(index, len(cases))
        started = time.perf_counter()
        result = service.retrieve(case["question"], case.get("knowledge_base_id", knowledge_base_id))
        latency_ms = (time.perf_counter() - started) * 1000
        latencies.append(latency_ms)
        documents = [hit.chunk.document_name for hit in result.hits]
        document_ids = [hit.chunk.document_id for hit in result.hits]
        pages = [hit.chunk.page_number for hit in result.hits]
        evidence = "\n".join(hit.chunk.text for hit in result.hits)
        expected = case["expected_documents"]
        expected_ids = set(case.get("expected_document_ids") or [])
        matches = [document_id in expected_ids if expected_ids else name in expected
                   for document_id, name in zip(document_ids, documents)]
        rank = next((index + 1 for index, matched in enumerate(matches) if matched), None)
        expected_pages = case.get("expected_pages", [])
        page_rank = next((index + 1 for index, (matched, page) in enumerate(zip(matches, pages))
                          if matched and page in expected_pages), None) if expected_pages else None
        if case["kind"] == "positive":
            recalled += int(rank is not None and rank <= 5)
            reciprocal_sum += 1.0 / rank if rank else 0.0
            correct_citations += sum(matches)
            citation_count += len(documents)
            term_hits += int(any(term in evidence for term in case["expected_terms_any"]))
            if expected_pages:
                page_recalled += int(page_rank is not None and page_rank <= 5)
                page_reciprocal_sum += 1.0 / page_rank if page_rank else 0.0
                correct_page_citations += sum(matched and page in expected_pages
                                              for matched, page in zip(matches, pages))
                page_citation_count += len(documents)
        else:
            refused += int(not result.accepted)
        if keep_details:
            details.append({"id": case["id"], "kind": case["kind"], "question": case["question"],
                            "accepted": result.accepted, "expected_documents": expected,
                            "expected_document_ids": sorted(expected_ids),
                            "retrieved_documents": documents, "retrieved_document_ids": document_ids,
                            "expected_rank": rank,
                            "expected_pages": expected_pages, "retrieved_pages": pages,
                            "expected_page_rank": page_rank,
                            "latency_ms": round(latency_ms, 2)})
    elapsed = time.perf_counter() - started_all
    metrics = {
        "positive_cases": len(positive), "negative_cases": len(negative),
        "recall_at_5": round(recalled / len(positive), 4), "mrr": round(reciprocal_sum / len(positive), 4),
        "citation_accuracy": round(correct_citations / citation_count, 4) if citation_count else 0.0,
        "evidence_term_coverage": round(term_hits / len(positive), 4),
        "refusal_accuracy": round(refused / len(negative), 4),
        "latency_p50_ms": round(percentile(latencies, 0.50), 2), "latency_p95_ms": round(percentile(latencies, 0.95), 2),
        "throughput_qps": round(len(cases) / elapsed, 2) if elapsed else 0.0,
    }
    if page_cases:
        metrics.update({
            "page_scoped_cases": len(page_cases),
            "page_recall_at_5": round(page_recalled / len(page_cases), 4),
            "page_mrr": round(page_reciprocal_sum / len(page_cases), 4),
            "page_citation_accuracy": round(correct_page_citations / page_citation_count, 4)
            if page_citation_count else 0.0,
        })
    return metrics, details
