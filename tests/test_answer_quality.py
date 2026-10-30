import json

import pytest

from app.answer_quality import AnswerQualityError, parse_review, review_answer, validate_known_claims


@pytest.mark.parametrize('answer,question',[
    ('另一种近似 LRU 的实现——活动页面栈。','LRU如何维护链表？'),
    ('只有在身份确认后，才能进行后续的密钥交换和加密通信。','TLS为何用证书？'),
    ('数字证书是 TLS 建立安全连接的基础。','TLS证书'),
    ('因此，实际系统中常采用栈结构或其他近似算法（如Clock算法）来优化性能。','LRU'),
    ('尾节点代表当前内存中历史最悠久的页面。','LRU'),
    ('这种实现方式是对 LRU 算法的一种近似。','LRU链表如何维护？'),
    ('服务器需要数字证书是为了证明身份。','TLS证书'),
    ('CA证明了该服务器确实属于它所声称的组织。','TLS证书'),
])
def test_observed_teaching_errors_cannot_pass_known_issue_veto(answer,question):
    with pytest.raises(AnswerQualityError):validate_known_claims(answer,question)


def test_scoped_tls_and_exact_lru_are_not_vetoed():
    validate_known_claims('在常见网页HTTPS证书认证场景中，证书用于验证服务器身份。','TLS')
    validate_known_claims('活动页面栈不是近似LRU；它也可维护准确的最近访问顺序。','LRU')
    validate_known_claims('并非所有服务器需要数字证书，TLS也支持PSK。','TLS')
    validate_known_claims('不能说只有身份确认后才能进行密钥交换。','TLS')
from app.calculations import calculate
from app.domain import SearchHit, TextChunk


HITS = [SearchHit(TextChunk('chunk', 'doc', '教材', 1, 'LRU是最优置换算法的一种近似。\n链表尾节点是最久未使用的页面。'), .8)]


def payload(**changes):
    section = {'heading': '结论', 'text': '应淘汰最久未使用页。', 'basis': 'course',
               'anchors': [{'source_index': 1, 'quote': '链表尾节点是最久未使用的页面。'}]}
    section.update(changes)
    return json.dumps({'sections': [section], 'corrections': []}, ensure_ascii=False)


def test_review_anchors_are_exact_and_supplement_is_explicit():
    answer, meta = parse_review(payload(), HITS)
    assert '[证据1]' in answer and meta['anchors'][0]['quote'] in HITS[0].chunk.text
    assert meta['anchor_location_checked'] and not meta['semantic_entailment_verified'] and not meta['teacher_approved']
    answer, _ = parse_review(payload(basis='supplement', anchors=[]), HITS)
    assert '补充知识' in answer and '证据' not in answer


@pytest.mark.parametrize('changes', [
    {'anchors': []}, {'anchors': [{'source_index': 2, 'quote': '链表尾节点是最久未使用的页面。'}]},
    {'anchors': [{'source_index': 1, 'quote': '不存在于原文中的完整引文。'}]},
    {'basis': 'supplement'},
])
def test_bad_anchor_or_unclassified_citation_is_rejected(changes):
    with pytest.raises(AnswerQualityError):
        parse_review(payload(**changes), HITS)


def test_review_does_not_claim_location_implies_logical_support():
    _, meta = parse_review(payload(text='错误结论。'), HITS)
    assert meta['semantic_entailment_verified'] is False


def test_only_catalog_anchors_render_citations_and_strict_mode_omits_supplement():
    answer, meta = parse_review(payload(text='淘汰最旧页[证据99]', anchors=[{'source_index':1,'quote_id':'s1q1'}]), HITS)
    assert '[证据99]' not in answer and '[证据1]' in answer
    assert meta['anchors'][0]['quote'] == HITS[0].chunk.text
    with pytest.raises(AnswerQualityError): parse_review(payload(basis='supplement', anchors=[]),HITS,allow_supplement=False)


def test_binary_search_trace_prevents_the_observed_midpoint_error():
    result = calculate('trace_binary_search', {'values': [1, 3, 5, 7, 9], 'target': 7}, origin='manual')
    assert result.status == 'completed' and result.result == '3'
    assert 'm=0+(4-0)//2=2' in result.steps[0].expression
    assert 'm=3+(4-3)//2=3' in result.steps[1].expression
    assert calculate('trace_binary_search', {'values': [5, 1], 'target': 1}, origin='manual').status == 'error'
    assert calculate('trace_binary_search', {'values': [], 'target': 1}, origin='manual').result == '-1'
    assert calculate('trace_binary_search', {'values': [True], 'target': 1}, origin='manual').status == 'error'


def test_page_replacement_is_not_a_universal_lru_optimality_claim():
    inputs = {'frames': 3, 'references': [1, 2, 3, 4, 1, 2, 5, 1, 2, 3, 4, 5]}
    lru = calculate('simulate_page_replacement', {**inputs, 'algorithm': 'LRU'}, origin='manual')
    optimal = calculate('simulate_page_replacement', {**inputs, 'algorithm': 'OPT'}, origin='manual')
    assert int(lru.result) > int(optimal.result)
    assert len(lru.steps) == len(inputs['references']) and '不证明' in lru.boundary
    assert calculate('simulate_page_replacement', {**inputs, 'algorithm': 'LRU', 'frames': 0}, origin='manual').status == 'error'


def test_review_retries_once_with_bounded_session():
    class Session:
        output_format = 'text'
        tools_enabled = True
        receipts = []
        require_calculation = False
        def check(self): pass
        def on_stage(self, label): pass
    class Generator:
        calls = 0
        def stream_with_calculations(self, *args, **kwargs):
            self.calls += 1
            yield 'bad' if self.calls == 1 else payload()
    generator = Generator()
    answer, meta = review_answer(generator, Session(), '问题', '不带数字的讲解', HITS)
    assert meta['attempts'] == generator.calls == 2 and '证据1' in answer
