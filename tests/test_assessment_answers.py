from app.assessment import AssessmentService
from app.models import QuestionBankItem


def question(kind: str, answer: str) -> QuestionBankItem:
    return QuestionBankItem(
        question_type=kind, correct_answer=answer, course_id=None,
        stem="test", options=[], difficulty=1,
    )


def test_multiple_choice_is_order_independent_and_exact() -> None:
    item = question("multiple_choice", "栈,队列")
    assert AssessmentService._answer_matches(item, '["队列","栈"]') is True
    assert AssessmentService._answer_matches(item, "栈，队列") is True
    assert AssessmentService._answer_matches(item, "栈") is False
    assert AssessmentService._answer_matches(item, "栈,队列,数组") is False


def test_fill_blank_supports_positions_and_alternatives() -> None:
    item = question("fill_blank", "根结点/根||左子树||右子树")
    assert AssessmentService._answer_matches(item, "根||左子树||右子树") is True
    assert AssessmentService._answer_matches(item, '["根结点","左子树","右子树"]') is True
    assert AssessmentService._answer_matches(item, "左子树||根||右子树") is False
    assert AssessmentService._answer_matches(item, "根||左子树") is False


def test_ai_letter_answers_match_submitted_option_text() -> None:
    single = question("single_choice", "A")
    single.options = ["A. 左子树", "B. 右子树"]
    assert AssessmentService._answer_matches(single, "A. 左子树") is True
    assert AssessmentService._answer_matches(single, "左子树") is True
    assert AssessmentService._answer_matches(single, "B. 右子树") is False

    multiple = question("multiple_choice", "A,C")
    multiple.options = ["A. 栈", "B. 数组", "C. 队列"]
    assert AssessmentService._answer_matches(multiple, '["C. 队列","A. 栈"]') is True
    assert AssessmentService._answer_matches(multiple, '["A. 栈","B. 数组"]') is False


def test_choice_text_answers_still_match_unlabeled_options() -> None:
    single = question("single_choice", "后进先出")
    single.options = ["先进先出", "后进先出"]
    assert AssessmentService._answer_matches(single, "后进先出") is True
    assert AssessmentService._answer_matches(single, "先进先出") is False
