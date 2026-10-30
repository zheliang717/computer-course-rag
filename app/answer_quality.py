"""Validate evidence anchors and render explicitly separated teaching claims.

Exact quote validation proves location only, not semantic entailment. Model
review and deterministic calculations are separate signals, never a teacher's
approval or a guarantee of overall answer correctness.
"""
import json
import re
import logging

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal


class EvidenceAnchor(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    source_index: int = Field(ge=1, le=20)
    quote: str | None = Field(default=None, min_length=8, max_length=220)
    quote_id: str | None = Field(default=None, pattern=r'^s[1-9][0-9]*q[1-9][0-9]*$')


class ReviewedSection(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    heading: str = Field(min_length=1, max_length=60)
    text: str = Field(min_length=1, max_length=2000)
    basis: Literal['course', 'supplement', 'inference']
    anchors: list[EvidenceAnchor] = Field(default_factory=list, max_length=5)


class ReviewedAnswer(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    sections: list[ReviewedSection] = Field(min_length=1, max_length=6)
    corrections: list[str] = Field(default_factory=list, max_length=8)


class AnswerQualityError(RuntimeError):
    pass


def anchor_catalog(hits):
    catalog = {}
    for source_index, hit in enumerate(hits, 1):
        # IDs bind to THIS retrieval, never a model-generated location or title.
        for index, start in enumerate(range(0, len(hit.chunk.text), 160), 1):
            quote = hit.chunk.text[start:start+200]
            if len(quote.strip()) >= 8:
                catalog[f's{source_index}q{index}'] = {'source_index': source_index, 'quote': quote}
    return catalog


def review_prompt(question, answer, receipts, hits=(), allow_supplement=True):
    return json.dumps({'question': question, 'draft_answer': answer, 'calculation_receipts': receipts,
        'known_issue_constraints': [
            'LRU链表与活动页面栈均可表达精确的最近访问顺序；不要把LRU近似OPT误读为活动栈只是近似LRU。栈实现同样有维护开销，不要宣称用栈结构就能优化性能。不要引入未提供证据的Clock算法。未问及栈时不必额外介绍。',
            'TLS证书解释限定在资料的网页/HTTPS常见证书认证场景，结论段也须写明范围；不要把证书说成所有TLS的必要前提，不得声称必须先完成身份认证才能密钥交换或加密握手。域名验证证书不等于证明组织所有权；资料未提供CA分类时勿扩展。未检索握手资料时删除这类时序断言。'
        ],
        'anchor_catalog': anchor_catalog(hits),
        'supplement_rule': '允许明确标注且切合问题的必要补充。' if allow_supplement else '当前是严格资料模式，不输出supplement段落；资料不足部分直接说明缺失，不补写资料外细节。',
        'task': '独立复核后重写，不是润色原答案。原答案可能有错误，不可先假定其正确。逐段检查题意、推演、例子、绝对化结论和引用。'
        '资料只说近似、假设或倾向时不可写成普遍最优保证。自己设计的数字/数组例子须复算；没有复算就删去该例子。'
        '用简短结论开头，之后2—4个重点即可，不重复总结，不额外扩展未询问的协议或算法。'
        '每段标basis：course仅描述实际资料支持的观点，至少选择一个anchor_catalog中的quote_id，不要自己抄写或改写quote；'
        'supplement为通用补充，不附资料引用；inference为基于资料的推导，说明假设，引用只作为前提。'
        '引文不足就缩小结论或说明边界，不得为了引用而挑无关句子。不要在text内写[证据N]，由系统按锚点渲染。'
        '必须只输出JSON：{"sections":[{"heading":"结论","text":"Markdown正文","basis":"course",'
        '"anchors":[{"source_index":1,"quote_id":"s1q1"}]}],"corrections":["修正点"]}。'
        '数学式保留LaTeX，不要使用未经提供的教材名称、页码或计算编号。'}, ensure_ascii=False)


def _find_quote(source, quote):
    # Match only a contiguous span, allowing line-wrap whitespace differences.
    compact, positions = '', []
    for index, char in enumerate(source):
        if not char.isspace():
            compact += char
            positions.append(index)
    needle = ''.join(quote.split())
    start = compact.find(needle)
    if start < 0:
        raise AnswerQualityError('引用不能定位到本轮片段中的连续原文。')
    return positions[start], positions[start + len(needle) - 1] + 1


def parse_review(raw, hits, *, allow_supplement=True):
    if len(raw) > 40000:
        raise AnswerQualityError('复核输出超出长度限制。')
    cleaned = raw.strip()
    fenced = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', cleaned, re.I)
    if fenced:
        cleaned = fenced[1]
    try:
        value = ReviewedAnswer.model_validate(json.loads(cleaned))
    except (ValueError, TypeError, ValidationError) as exc:
        detail = ', '.join('.'.join(map(str, e['loc'])) + ':' + e['type'] for e in exc.errors(include_input=False)[:3]) if isinstance(exc, ValidationError) else 'json'
        raise AnswerQualityError('回答复核格式不完整：' + detail) from exc
    paragraphs, anchor_rows = [], []
    catalog = anchor_catalog(hits)
    included = [s for s in value.sections if allow_supplement or s.basis != 'supplement']
    if not included: raise AnswerQualityError('没有得到由资料支撑的有效讲解。')
    for index, section in enumerate(included):
        # Only server-inserted anchors become clickable references. A model's
        # manually typed marker grants nothing and is removed, not trusted.
        section.text = re.sub(r'\[证据\d+\]', '', section.text)
        if section.basis == 'course' and not section.anchors:
            raise AnswerQualityError('资料观点缺少可定位引文。')
        if section.basis == 'supplement' and section.anchors:
            raise AnswerQualityError('通用补充不能借用资料编号背书。')
        refs = []
        for anchor in section.anchors:
            if anchor.source_index > len(hits):
                raise AnswerQualityError('引用编号不属于本轮证据。')
            hit = hits[anchor.source_index-1]
            quote = anchor.quote
            if anchor.quote_id:
                location = catalog.get(anchor.quote_id)
                if not location or location['source_index'] != anchor.source_index:
                    raise AnswerQualityError('引文标识不属于该证据。')
                quote = location['quote']
            if not quote: raise AnswerQualityError('缺少引文标识。')
            start, end = _find_quote(hit.chunk.text, quote)
            refs.append(anchor.source_index)
            anchor_rows.append({'section_index': index, 'source_index': anchor.source_index,
                'quote': hit.chunk.text[start:end], 'chunk_id': hit.chunk.chunk_id,
                'document_id': hit.chunk.document_id, 'page_number': hit.chunk.page_number})
        label = {'course': '', 'supplement': '**补充知识**\n\n', 'inference': '**补充推导**\n\n'}[section.basis]
        reference_text = ''.join(f'[证据{n}]' for n in dict.fromkeys(refs))
        if section.basis == 'inference' and reference_text:
            reference_text = '\n\n推导前提：' + reference_text
        paragraphs.append(f'### {section.heading}\n\n{label}{section.text}{reference_text}')
    return '\n\n'.join(paragraphs), {'status': 'ai_reviewed', 'teacher_approved': False,
        'anchor_location_checked': True, 'semantic_entailment_verified': False,
        'sections': [{'heading': s.heading, 'basis': s.basis} for s in included],
        'omitted_supplement_count': len(value.sections)-len(included),
        'anchors': anchor_rows, 'corrections': [v[:300] for v in value.corrections if not re.search(r'格式|anchor|quote_id|编号', v, re.I)],
        'notice': 'AI已复核并定位引用原文；不代表教师审定，仍可反馈有疑问的内容。'}


def validate_known_claims(answer, question):
    """Narrow regression vetoes, not a general semantic correctness proof.

    TLS boundary: RFC8446 section2 flow and section2.2 PSK mode.
    https://www.rfc-editor.org/rfc/rfc8446#section-2
    """
    text=re.sub(r'[*_#`]', '', answer)
    sentences=re.split(r'[。；\n]',text)
    if 'LRU' in (question+text).upper():
        for sentence in sentences:
            if '链表' in question and re.search(r'(?:这种实现方式|链表实现).{0,35}(?:对\s*LRU.{0,20}近似|近似\s*LRU)',sentence,re.I) and not re.search(r'不是|并非|不应|不能',sentence):
                raise AnswerQualityError('按每次访问移动节点的链表可以精确维护LRU，不需要时间戳才能称为精确LRU；不要误读为近似实现。')
            if '近似' in sentence and '活动页面栈' in sentence and not re.search(r'(?:不是|并非|并不|不应).{0,16}近似',sentence):
                raise AnswerQualityError('不能将活动页面栈误称为近似LRU实现；只说明题目所问的精确访问顺序。')
            if re.search(r'栈结构.{0,50}(?:优化性能|提高性能|降低开销)',sentence,re.I) and not re.search(r'不能|并非|不应',sentence):
                raise AnswerQualityError('删除无证据的Clock扩展与栈优化性能断言；资料明确栈实现也有维护开销。')
            if '历史最悠久' in sentence and not re.search(r'不是|并非|不应|不能',sentence):
                raise AnswerQualityError('LRU比较最后访问时间，不要把它说成驻留历史最悠久。')
    if 'TLS' in (question+text).upper():
        for sentence in sentences:
            if re.search(r'不能(?:认为|声称|说)|不应|并非|不是所有',sentence):
                continue
            if re.search(r'只有.{0,90}身份.{0,90}(?:密钥交换|加密通信)',sentence):
                raise AnswerQualityError('删除先身份认证后才能密钥交换/加密的普遍时序断言；资料未支持此结论。')
            if '数字证书是' in sentence and 'TLS' in sentence and not re.search(r'浏览器|网页|HTTPS|常见|证书认证',sentence,re.I):
                raise AnswerQualityError('数字证书的必要性应限定在网页/HTTPS常见证书认证场景，不能泛化到所有TLS。')
            if '服务器需要数字证书' in sentence and not re.search(r'浏览器|网页|HTTPS|常见|证书认证',sentence,re.I):
                raise AnswerQualityError('包括结论段在内，将服务器证书要求明确限定到常见网页/HTTPS证书认证场景。')
            if re.search(r'证明.{0,50}属于.{0,30}组织',sentence) and not re.search(r'OV|EV|企业验证|组织验证',sentence,re.I):
                raise AnswerQualityError('不能将一般数字证书等同于组织所有权证明；删除资料未支持的CA扩展。')


def review_answer(generator, session, question, draft, hits, *, on_response=None, allow_supplement=True):
    session.output_format = 'json'
    numeric_text = re.sub(r'\[(?:证据|计算)\d+\]|(?m:^\s*\d+[.、])', '', draft)
    session.require_calculation = bool(session.tools_enabled and re.search(r'\d\s*[,，+*/=]|=\s*\d|\[\s*\d', numeric_text)
        and not any(r['status'] == 'completed' for r in session.receipts))
    prompt = review_prompt(question, draft, session.receipts, hits, allow_supplement)
    for attempt in range(2):
        session.check()
        session.on_stage('正在复核推演与逐段资料依据…' if not attempt else '正在修正讲解与引用边界…')
        raw = ''.join(generator.stream_with_calculations(prompt, hits, session=session, grounded=True,
            task='answer_review', on_response=on_response))
        try:
            answer, metadata = parse_review(raw, hits, allow_supplement=allow_supplement)
            validate_known_claims(answer, question)
            metadata['known_issue_vetoes_checked'] = True
            metadata['attempts'] = attempt + 1
            return answer, metadata
        except AnswerQualityError as exc:
            logging.getLogger(__name__).warning('Teaching review schema/anchor check failed: %s', exc)
            if attempt:
                raise
            prompt = review_prompt(question, draft, session.receipts, hits, allow_supplement) + '\n上次复核未通过：' + str(exc) + '。请完整重新输出，仅选择本轮anchor_catalog中的quote_id。'
