"""Parse AI question output without treating unvalidated text as publishable questions."""
import json

from pydantic import ValidationError

from app.schemas import QuestionDraftItem


def parse_question_draft(text: str) -> list[dict]:
    value = text.strip()
    fence = chr(96) * 3
    if value.startswith(fence):
        value = value[3:]
        if value.lower().startswith("json"):
            value = value[4:]
        value = value.rsplit(fence, 1)[0].strip()
    try:
        payload = json.loads(value)
    except (ValueError, TypeError):
        return []
    raw = payload.get("questions") if isinstance(payload, dict) else payload
    if not isinstance(raw, list) or not 1 <= len(raw) <= 50:
        return []
    try:
        return [QuestionDraftItem.model_validate(item).model_dump() for item in raw]
    except ValidationError:
        return []
