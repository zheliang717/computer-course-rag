from app.domain import SearchHit, TextChunk
from app.rag import RetrievalService


def hit(id, score):
    return SearchHit(TextChunk(id, 'allowed-doc', '课程资料', 1, '相关原文'), score)


class Store:
    def __init__(self):
        self.calls = []

    def search(self, question, top_k, **filters):
        self.calls.append((question, top_k, filters))
        return [hit('same', .39)] if question.count('？') > 1 else [hit('same', .51), hit('other', .35)]


def test_explicit_subquestions_reuse_scope_dedupe_and_threshold():
    store = Store()
    result = RetrievalService(store, min_score=.43, top_k=5).retrieve(
        '栈为什么后进先出？push和pop分别做什么？', 'base', document_id='allowed-doc')
    assert result.accepted and len(result.hits) == 1 and result.hits[0].score == .51
    assert len(store.calls) == 3
    assert store.calls[1][0] == '栈为什么后进先出？'
    assert store.calls[2][0] == 'push和pop分别做什么？'
    assert all(call[2] == {'knowledge_base_id': 'base', 'document_id': 'allowed-doc'} for call in store.calls)


def test_single_question_and_fenced_code_keep_original_search():
    for question in ['什么是二分查找？', '比较TCP与UDP', '```x ? y : z```\n请解释？为什么？']:
        store = Store()
        RetrievalService(store, min_score=.43, top_k=5).retrieve(question)
        assert len(store.calls) == 1


def test_expansion_is_bounded_and_does_not_enable_long_input_fanout():
    assert len(RetrievalService._question_parts('问题一是什么？问题二是什么？问题三是什么？问题四是什么？')) == 3
    assert not RetrievalService._question_parts('长文本' * 500 + '？问题二是什么？')
