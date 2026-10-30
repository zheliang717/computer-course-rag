"""Page-scoped gold labels must not be satisfied by a different page in the same book."""

from app.domain import SearchHit, TextChunk
from app.rag import RetrievalResult
from scripts.evaluate_retrieval import evaluate, quality_gate, source_coverage


class FixedRetrieval:
    def retrieve(self, question, knowledge_base_id=None):
        del knowledge_base_id
        if question == "unrelated":
            return RetrievalResult(accepted=False, message="", hits=[])
        hits = [
            SearchHit(TextChunk(str(page), "doc-1", "Course notes", page, "MMU maps addresses"), 0.9)
            for page in (1, 2)
        ]
        return RetrievalResult(accepted=True, message="", hits=hits)


def test_page_scoped_metrics_keep_document_and_page_matches_separate():
    cases = [
        {"id": "page-2", "kind": "positive", "question": "mapping", "expected_documents": ["Course notes"],
         "expected_pages": [2], "expected_terms_any": ["MMU"]},
        {"id": "negative", "kind": "negative", "question": "unrelated", "expected_documents": [],
         "expected_terms_any": []},
    ]
    metrics, details = evaluate(FixedRetrieval(), cases, keep_details=True)
    assert metrics["recall_at_5"] == 1.0
    assert metrics["mrr"] == 1.0
    assert metrics["citation_accuracy"] == 1.0
    assert metrics["page_recall_at_5"] == 1.0
    assert metrics["page_mrr"] == 0.5
    assert metrics["page_citation_accuracy"] == 0.5
    assert metrics["refusal_accuracy"] == 1.0
    assert details[0]["expected_page_rank"] == 2
    assert details[0]["retrieved_pages"] == [1, 2]


def test_legacy_cases_do_not_gain_page_metrics():
    cases = [
        {"id": "legacy", "kind": "positive", "question": "mapping", "expected_documents": ["Course notes"],
         "expected_terms_any": ["MMU"]},
        {"id": "negative", "kind": "negative", "question": "unrelated", "expected_documents": [],
         "expected_terms_any": []},
    ]
    metrics, details = evaluate(FixedRetrieval(), cases, keep_details=True)
    assert "page_recall_at_5" not in metrics
    assert details[0]["expected_page_rank"] is None


def test_source_coverage_flags_missing_targets_per_course_without_counting_alternatives():
    cases = [
        {"id": "present", "kind": "positive", "expected_documents": ["Existing notes"]},
        {"id": "alternative", "kind": "positive", "expected_documents": ["Missing edition", "Existing notes"]},
        {"id": "missing", "kind": "positive", "expected_documents": ["Absent book"]},
        {"id": "wrong-course", "kind": "positive", "knowledge_base_id": "other",
         "expected_documents": ["Existing notes"]},
        {"id": "negative", "kind": "negative", "expected_documents": []},
    ]
    coverage = source_coverage(cases, {"course": {"Existing notes"}, "other": set()}, "course")
    assert coverage == {
        "positive_cases": 4, "covered_cases": 2, "missing_cases": 2,
        "missing_case_ids": ["missing", "wrong-course"],
        "missing_documents": ["Absent book", "Existing notes"],
    }


def test_stable_document_id_keeps_renamed_source_counted_and_retrieved():
    case = {"id": "renamed", "kind": "positive", "question": "mapping",
            "expected_documents": ["Old display name"], "expected_document_ids": ["doc-1"],
            "expected_terms_any": ["MMU"]}
    coverage = source_coverage([case], {"course": {"doc-1", "Course notes"}}, "course")
    assert coverage["missing_cases"] == 0
    metrics, details = evaluate(FixedRetrieval(), [case, {
        "id": "negative", "kind": "negative", "question": "unrelated",
        "expected_documents": [], "expected_terms_any": []}], keep_details=True)
    assert metrics["recall_at_5"] == 1.0
    assert metrics["citation_accuracy"] == 1.0
    assert details[0]["retrieved_documents"] == ["Course notes", "Course notes"]
    assert details[0]["retrieved_document_ids"] == ["doc-1", "doc-1"]


def test_quality_gate_requires_source_coverage_as_well_as_retrieval_metrics():
    metrics = {"recall_at_5": 1.0, "mrr": 0.95, "refusal_accuracy": 1.0,
               "latency_p95_ms": 100.0,"citation_accuracy":.95}
    assert quality_gate(metrics, {"missing_cases": 0})
    assert not quality_gate(metrics, {"missing_cases": 1})
    assert not quality_gate({**metrics, "recall_at_5": 0.7}, {"missing_cases": 0})
    assert not quality_gate({**metrics,'citation_accuracy':.2909},{'missing_cases':0})
    assert not quality_gate({**metrics,'page_scoped_cases':10,'page_recall_at_5':1,'page_citation_accuracy':.5},{'missing_cases':0})
