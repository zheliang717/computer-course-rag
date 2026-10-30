"""Deterministic preflight for teacher-reviewed question drafts.

This catches structural mistakes and repeated questions. It deliberately does
not claim to decide whether a model's explanation is academically correct.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from typing import Iterable


_LABEL = re.compile(r"^([A-J])\s*[.、:：)）]\s*(.+)$", re.IGNORECASE)
_PUNCTUATION = re.compile(r"[\W_]+", re.UNICODE)


def _normalized(value: str) -> str:
    return _PUNCTUATION.sub("", unicodedata.normalize("NFKC", value).casefold())


def _finding(index: int, severity: str, code: str, message: str, **extra: object) -> dict:
    return {"question_index": index, "severity": severity, "code": code, "message": message, **extra}


def _answer_tokens(answer: str) -> list[str]:
    return [value.strip() for value in re.split(r"[,，;；]", answer) if value.strip()]


def _similar(first: str, second: str) -> bool:
    if min(len(first), len(second)) < 12 or abs(len(first) - len(second)) > max(len(first), len(second)) * 0.15:
        return False
    return SequenceMatcher(None, first[:500], second[:500], autojunk=False).ratio() >= 0.88


def review_question_set(questions: list[dict], existing: Iterable[dict] = ()) -> list[dict]:
    """Return ordered, actionable findings; only `error` findings block import."""
    findings: list[dict] = []
    existing_stems = [
        (str(item.get("id", "")), _normalized(str(item.get("stem", ""))))
        for item in existing
    ]
    seen: dict[str, int] = {}
    for index, question in enumerate(questions, start=1):
        stem = str(question.get("stem", "")).strip()
        normalized_stem = _normalized(stem)
        question_type = str(question.get("question_type", ""))
        answer = str(question.get("correct_answer", "")).strip()
        options = [str(option).strip() for option in question.get("options", []) if str(option).strip()]

        if not normalized_stem:
            findings.append(_finding(index, "error", "empty_stem", "题干不能为空。"))
        elif normalized_stem in seen:
            findings.append(_finding(index, "error", "duplicate_in_draft", f"与本草稿第 {seen[normalized_stem]} 题重复。",
                                     related_question_index=seen[normalized_stem]))
        else:
            similar_index = next((old_index for old_stem, old_index in seen.items() if _similar(normalized_stem, old_stem)), None)
            if similar_index:
                findings.append(_finding(index, "warning", "similar_in_draft", f"与本草稿第 {similar_index} 题高度相似，请人工核对。",
                                         related_question_index=similar_index))
            seen[normalized_stem] = index

        for existing_id, old_stem in existing_stems:
            if not normalized_stem or not old_stem:
                continue
            if normalized_stem == old_stem:
                findings.append(_finding(index, "error", "duplicate_in_bank", "课程题库已有相同题干。",
                                         related_question_id=existing_id))
                break
            if _similar(normalized_stem, old_stem):
                findings.append(_finding(index, "warning", "similar_in_bank", "课程题库有高度相似题目，请人工核对。",
                                         related_question_id=existing_id))
                break

        if question_type in {"single_choice", "multiple_choice", "true_false"}:
            if len(options) < 2:
                findings.append(_finding(index, "error", "too_few_options", "该题型至少需要两个非空选项。"))
            parsed = [_LABEL.match(option) for option in options]
            labels = [match.group(1).upper() for match in parsed if match]
            contents = [match.group(2) if match else option for match, option in zip(parsed, options)]
            normalized_options = [_normalized(content) for content in contents]
            if len(set(normalized_options)) != len(normalized_options):
                findings.append(_finding(index, "error", "duplicate_options", "选项内容重复。"))
            if labels and len(labels) != len(options):
                findings.append(_finding(index, "warning", "mixed_option_labels", "部分选项有字母编号、部分没有，请统一格式。"))
            if len(set(labels)) != len(labels):
                findings.append(_finding(index, "error", "duplicate_labels", "选项字母编号重复。"))

            answer_tokens = _answer_tokens(answer)
            if question_type == "single_choice" and len(answer_tokens) != 1:
                findings.append(_finding(index, "error", "single_answer_count", "单选题必须只有一个正确答案。"))
            if question_type == "multiple_choice" and len(answer_tokens) < 2:
                findings.append(_finding(index, "error", "multiple_answer_count", "多选题至少需要两个正确答案。"))
            if question_type in {"single_choice", "multiple_choice"} and options and answer_tokens:
                positional_labels = {chr(ord("A") + option_index) for option_index, match in enumerate(parsed) if not match}
                allowed = set(labels) | positional_labels | set(normalized_options) | {_normalized(option) for option in options}
                invalid = [token for token in answer_tokens if token.upper() not in allowed and _normalized(token) not in allowed]
                if invalid:
                    findings.append(_finding(index, "error", "answer_not_in_options", "参考答案未对应现有选项。"))
                if len({_normalized(token) for token in answer_tokens}) != len(answer_tokens):
                    findings.append(_finding(index, "error", "repeated_answer", "参考答案重复列出了同一选项。"))
        elif options:
            findings.append(_finding(index, "warning", "unused_options", "非选择题设置了选项，请检查题型。"))

        if not answer:
            findings.append(_finding(index, "error", "empty_answer", "参考答案不能为空。"))
        if not str(question.get("explanation") or "").strip():
            findings.append(_finding(index, "warning", "missing_explanation", "尚无解析，建议补充评分或讲评依据。"))

    return findings
