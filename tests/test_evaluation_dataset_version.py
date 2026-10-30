"""Keep the corrected benchmark traceable to the registered source PDF."""

import hashlib
import json
from pathlib import Path
import pytest

from app.catalog import stable_document_uuid


ROOT = Path(__file__).resolve().parents[1]


def test_v2_corrects_only_the_source_identity_and_preserves_v1():
    old = json.loads((ROOT / "materials/eval/questions-150.json").read_text(encoding="utf-8"))
    new = json.loads((ROOT / "materials/eval/questions-150-v2.json").read_text(encoding="utf-8"))
    registry = {source["id"]: source for source in json.loads(
        (ROOT / "materials/sources.json").read_text(encoding="utf-8"))["sources"]}
    source = registry["tsinghua-dsa-greedy-dp"]

    assert old["dataset_version"] == "dsa-zh-150-v1"
    assert new["dataset_version"] == "dsa-zh-150-v2"
    assert len(old["cases"]) == len(new["cases"]) == 150
    assert [(case["id"], case["kind"], case["question"], case["expected_terms_any"])
            for case in old["cases"]] == [
                (case["id"], case["kind"], case["question"], case["expected_terms_any"])
                for case in new["cases"]]

    changed = [(before, after) for before, after in zip(old["cases"], new["cases"])
               if before["expected_documents"] != after["expected_documents"]]
    assert len(changed) == 36
    assert {before["expected_documents"][0] for before, _ in changed} == {"数据结构与算法：贪心与动态规划"}
    assert {after["expected_documents"][0] for _, after in changed} == {source["title"]}
    assert {tuple(after["expected_document_ids"]) for _, after in changed} == {
        (str(stable_document_uuid(source["id"])),)}
    assert all(case.get("expected_document_ids") for case in new["cases"] if case["kind"] == "positive")

    assert new["source_correction"]["sha256"] == source["sha256"]


def test_registered_external_pdf_matches_when_supplied_by_operator():
    registry = json.loads((ROOT / 'materials/sources.json').read_text(encoding='utf-8'))['sources']
    source = next(item for item in registry if item['id'] == 'tsinghua-dsa-greedy-dp')
    path = ROOT / source['local_file']
    if not path.is_file():
        pytest.skip('Third-party PDF is not bundled; operator may supply a permitted local copy.')
    assert hashlib.sha256(path.read_bytes()).hexdigest().upper() == source['sha256']
