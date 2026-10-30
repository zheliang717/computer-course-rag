import hashlib
import json

import pytest

from app.domain import SearchHit, TextChunk
from app.generation import OpenAICompatibleGenerator
from scripts.import_flagship_readings import MANIFEST, checked_text, selected_text, stable_id


def test_pinned_manifest_keeps_formal_titles_and_narrow_course_scope():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert len(manifest["packs"]) == 3
    assert len({stable_id(pack) for pack in manifest["packs"]}) == 3
    assert sum(len(pack["pages"]) for pack in manifest["packs"]) == 11
    for pack in manifest["packs"]:
        assert ".pdf" not in pack["title"].lower()
        assert len(pack["commit"]) == 40 and len(pack["license_sha256"]) == 64
        assert len(pack["course_codes"]) == 2
        for page in pack["pages"]:
            assert page["file"] in pack["files"] and page["related_sections"]
            assert page["keywords"]


def test_hash_and_utf8_are_verified_before_import():
    raw = "中文正文".encode()
    assert checked_text(raw, hashlib.sha256(raw).hexdigest()) == "中文正文"
    with pytest.raises(ValueError, match="哈希"):
        checked_text(b"different", hashlib.sha256(raw).hexdigest())
    with pytest.raises(UnicodeDecodeError):
        checked_text(b"\xff", hashlib.sha256(b"\xff").hexdigest())


def test_selection_preserves_formula_and_expands_only_mdn_label():
    text = '# 概念\n<u>栈</u> 与 {{Glossary("IP address", "IP 地址")}}\n$O(n)$；[资料](https://example.test)'
    result = selected_text(text, [[1, 3]])
    assert "栈 与 IP 地址" in result and "$O(n)$" in result and "资料" in result
    assert "example.test" not in result
    assert not result.startswith("#")
    assert selected_text("| 方法 | 时间 |\n| --- | --- |\n| `push()` | $O(1)$ |", [[1, 3]]) == "方法 · 时间\npush() · $O(1)$"


@pytest.mark.parametrize("source", ["![图](a.png)", "<!-- hidden -->", "```src\n[file]x", "<script>alert(1)</script>", "{{unknown()}}", "=== 'Python'"])
def test_unreviewed_content_is_rejected(source):
    with pytest.raises(ValueError):
        selected_text(source, [[1, len(source.splitlines())]])


@pytest.mark.parametrize("ranges", [[[0, 1]], [[2, 1]], [[1, 3]]])
def test_invalid_line_ranges_do_not_silently_truncate(ranges):
    with pytest.raises(ValueError):
        selected_text("a\nb", ranges)


def test_teacher_answer_contract_separates_claims_examples_and_current_citations():
    generator = OpenAICompatibleGenerator(api_base="https://example.invalid/v1", api_key="test", model="test")
    hit = SearchHit(TextChunk("c1", "d1", "教材", 4, "当前资料正文"), .9)
    payload = generator._request_payload("请解释", [hit], task="assistant_chat")
    system, user = [message["content"] for message in payload["messages"]]
    assert "本轮证据列表" in system and "待分析数据" in system
    assert "紧邻的观点" in system
    assert "自拟例子" in user and "适用前提" in user
    assert "[证据1: 教材, 第4页]" in user
    assert payload["max_tokens"] == 1200
    general = generator._request_payload("通用问题", [], grounded=False)
    assert "[证据1" not in general["messages"][1]["content"]
