"""Validate model-authored, advisory review of one teaching-draft question."""

from __future__ import annotations

import json
import re

from pydantic import ValidationError

from app.schemas import DraftAIReviewProposal


def parse_ai_question_review(raw: str) -> dict:
    value = raw.strip()
    fenced = re.fullmatch(r"```(?:json)?\s*([\s\S]*?)\s*```", value, flags=re.IGNORECASE)
    if fenced:
        value = fenced.group(1).strip()
    try:
        payload = json.loads(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("AI 复核结果不是可验证的 JSON。") from exc
    if not isinstance(payload, dict):
        raise ValueError("AI 复核结果应为 JSON 对象。")
    summary = payload.get("summary")
    findings = payload.get("findings")
    suggested_stem = payload.get("suggested_stem")
    if not isinstance(summary, str) or not 2 <= len(summary.strip()) <= 800:
        raise ValueError("AI 复核结果缺少简要结论。")
    if not isinstance(findings, list) or len(findings) > 8:
        raise ValueError("AI 复核问题列表格式不正确。")
    try:
        validated = [DraftAIReviewProposal.model_validate(item).model_dump() for item in findings]
    except ValidationError as exc:
        raise ValueError("AI 复核问题项格式不正确。") from exc
    if suggested_stem is not None:
        if not isinstance(suggested_stem, str) or len(suggested_stem.strip()) > 5000:
            raise ValueError("AI 建议题干格式不正确。")
        suggested_stem = suggested_stem.strip() or None
    suggestions = {'suggested_stem': suggested_stem}
    for key, limit in (('suggested_correct_answer', 2000), ('suggested_explanation', 5000)):
        item = payload.get(key)
        if item is not None and (not isinstance(item, str) or len(item.strip()) > limit):
            raise ValueError('AI 建议答案或解析格式不正确。')
        suggestions[key] = item.strip() or None if item is not None else None
    basis = payload.get('suggestion_basis') or {}
    if not isinstance(basis, dict):
        raise ValueError('AI 建议依据映射格式不正确。')
    safe_basis = {}
    for key in suggestions:
        values = basis.get(key, [])
        if not isinstance(values, list) or len(values) > 8 or any(type(value) is not int or not 1 <= value <= 8 for value in values):
            raise ValueError('AI 建议的依据序号不正确。')
        safe_basis[key] = values
    return {"summary": summary.strip(), "findings": validated, 'suggestion_basis': safe_basis, **suggestions}
