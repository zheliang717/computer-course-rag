import json

from app.draft_questions import parse_question_draft


def _question():
    return {
        "question_type": "single_choice",
        "stem": "中序遍历何时访问根结点？",
        "options": ["A. 左子树之后", "B. 左子树之前"],
        "correct_answer": "A",
        "explanation": "访问顺序为左、根、右。",
        "difficulty": 1,
        "knowledge_point": "二叉树遍历",
    }


def test_parse_question_draft_from_json_fence():
    body = json.dumps({"questions": [_question()]}, ensure_ascii=False)
    parsed = parse_question_draft(f"```json\n{body}\n```")
    assert len(parsed) == 1
    assert parsed[0]["correct_answer"] == "A"


def test_parse_question_draft_rejects_unstructured_or_invalid_output():
    assert parse_question_draft("这是一段解释，不是题目 JSON") == []
    assert parse_question_draft(json.dumps({"questions": []})) == []
    invalid = _question()
    invalid["difficulty"] = 9
    assert parse_question_draft(json.dumps({"questions": [invalid]}, ensure_ascii=False)) == []
