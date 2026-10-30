"""Answer modes are request facts, never inferred from retrieved citations."""

ANSWER_MODES = frozenset({'rag', 'hybrid', 'general'})


def recorded_answer_mode(value):
    return value if isinstance(value, str) and value in ANSWER_MODES else None


def answer_mode_label(value):
    return {'rag': '严格课程 RAG', 'hybrid': '课程优先', 'general': '通用助手'}.get(
        recorded_answer_mode(value), '原回答模式未记录')
