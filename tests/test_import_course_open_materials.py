"""Registered imports must not duplicate a document after its display title changes."""

from uuid import NAMESPACE_URL, uuid5

from scripts.import_course_open_materials import find_registered_document


def test_existing_document_is_found_by_stable_id_after_title_correction() -> None:
    source = {"id": "tsinghua-dsa-greedy-dp", "title": "数据结构与算法：基础算法"}
    stable_id = str(uuid5(NAMESPACE_URL, "computer-course-rag/document/tsinghua-dsa-greedy-dp"))
    existing = {"id": stable_id, "name": "数据结构与算法：贪心与动态规划", "status": "ready"}
    assert find_registered_document([existing], source) is existing


def test_legacy_document_is_found_by_title_as_fallback() -> None:
    source = {"id": "sample", "title": "课程讲义"}
    existing = {"id": "legacy-id", "name": "课程讲义", "status": "ready"}
    assert find_registered_document([existing], source) is existing
