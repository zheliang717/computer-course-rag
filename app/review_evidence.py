"""Resolve model-proposed anchors against exact inputs; never certify reasoning.

An existing quote or receipt proves provenance only. Unsupported conclusions
remain visible as questions, and teacher judgments are a separate human action.
"""
from copy import deepcopy
import re
from uuid import UUID, uuid5

from app.schemas import DraftReviewAnchor

FIELDS = {'stem': '题干', 'options': '选项', 'correct_answer': '参考答案', 'explanation': '解析', 'knowledge_point': '知识点'}
HARDWARE = re.compile(r'位宽|地址总线|总线宽度|\b(?:32|48|64)\s*位|基址寄存器|从.?0.?开始连续|连续分配|地址截断|硬件架构')
ASKS_HARDWARE = re.compile(r'位宽|总线|\b(?:32|48|64)\s*位|地址长度|溢出|截断|基址|硬件')


def finding_id(review_id, position):
    return uuid5(UUID(str(review_id)), str(position + 1)).hex


def _anchor(raw, question, hits, receipts):
    value = DraftReviewAnchor.model_validate(raw).model_dump(mode='json')
    result = {**value, 'matched': False, 'label': '未匹配的拟引用', 'excerpt': '',
              'reason': '未找到该拟引用对应的原文或实际回执。', 'document_id': None, 'page_number': None}
    quote = (value.get('quote') or '').strip()
    if value['kind'] == 'question':
        field = value.get('field')
        text = question.get(field) if field else None
        text = '\n'.join(text) if isinstance(text, list) else str(text or '')
        result['label'] = '原题 · ' + FIELDS.get(field, '未指定字段')
        if quote and quote in text and (len(quote) >= 8 or quote == text):
            result.update(matched=True, excerpt=quote, reason='所引文字可在保存的原题字段中定位；不证明推论正确。')
    elif value['kind'] == 'source':
        index = value.get('source_index')
        if index and index <= len(hits):
            hit = hits[index - 1]
            result['label'] = f'证据{index} · {hit.chunk.document_name} · 第{hit.chunk.page_number}页'
            if quote and quote in hit.chunk.text and len(quote) >= 6:
                result.update(matched=True, excerpt=quote, document_id=hit.chunk.document_id,
                    page_number=hit.chunk.page_number, reason='拟引用文字存在于本次获准片段；仍需核对其是否支持此观点。')
    else:
        receipt = next((item for item in receipts if item.get('reference') == value.get('reference')
                        and item.get('status') == 'completed'), None)
        if receipt:
            step = value.get('step_index')
            if step:
                steps = receipt.get('steps', [])
                if step <= len(steps):
                    entry = steps[step - 1]
                    text = f"{entry['expression']} = {entry['result']}"
                    if not quote or quote in (entry['result'], text):
                        result.update(matched=True, excerpt=text, label=f"{receipt['reference']} · {entry['label']}")
            elif not quote or quote in (receipt.get('result'), receipt.get('exact_result')):
                result.update(matched=True, excerpt=str(receipt.get('result')), label=f"{receipt['reference']} · {receipt['title']}")
            if result['matched']:
                result['reason'] = '该回执与结果确实存在；未核实参数是否符合题意、单位及完整推理。'
    return result


def resolve_review_evidence(parsed, *, review_id, question, hits, receipts):
    result = deepcopy(parsed)
    findings = []
    for position, authored in enumerate(parsed['findings']):
        anchors = [_anchor(value, question, hits, receipts) for value in authored.get('anchors', [])]
        matched = [value for value in anchors if value['matched']]
        kinds = {value['kind'] for value in matched}
        fields = {value['field'] for value in matched if value['kind'] == 'question'}
        claim = authored.get('claim_type', 'open_question')
        assessment = authored.get('assessment', 'uncertain')
        complete = bool(anchors) and all(value['matched'] for value in anchors)
        basis = ('linked' if complete else 'invalid' if anchors else 'missing')
        sufficient = complete and (
            claim == 'numeric' and {'question', 'calculation'} <= kinds or
            claim == 'source_conflict' and {'question', 'source'} <= kinds or
            claim == 'internal_consistency' and len(fields) >= 2 or
            claim == 'teaching_improvement' and 'question' in kinds)
        note = '原文/回执定位检查不是学科正确性或推理验证。'
        if not sufficient:
            assessment = 'uncertain'
            note = '依据未形成对应链，只作待核实设想，不作为已发现缺陷。'
        elif claim == 'teaching_improvement':
            assessment = 'improvement'
            note = '基于原题的教学完善建议，不等于题目有错误；仍需教师判断。'
        paging = any(item.get('tool') == 'translate_page_address' and item.get('status') == 'completed' for item in receipts)
        material_mentions_hardware = any(value['kind'] == 'source' and HARDWARE.search(value['excerpt']) for value in matched)
        if (paging and HARDWARE.search(authored['detail'] + authored['suggestion'])
                and not ASKS_HARDWARE.search(question['stem']) and not material_mentions_hardware):
            assessment = 'uncertain'
            note = '这是题目未要求且无对应教材片段支撑的额外硬件设想，不按本题缺陷呈现；该保守归类仍可由教师复核。'
        findings.append({**authored, 'id': finding_id(review_id, position), 'anchors': anchors,
            'original_assessment': authored.get('assessment', 'uncertain'), 'assessment': assessment,
            'basis_status': basis, 'basis_note': note})
    result.update(findings=findings, analysis_version=2,
        basis_summary=f"{len(findings)}条审阅意见：{sum(item['assessment'] != 'uncertain' for item in findings)}条有对应定位的建议，"
            f"{sum(item['assessment'] == 'uncertain' for item in findings)}条待核实设想。定位不等于结论正确。")
    resolved_basis, notes = {}, {}
    for key in ('suggested_stem', 'suggested_correct_answer', 'suggested_explanation'):
        indices = parsed.get('suggestion_basis', {}).get(key, [])
        eligible = [findings[index - 1]['id'] for index in indices if index <= len(findings)
            and findings[index - 1]['assessment'] != 'uncertain' and findings[index - 1]['basis_status'] == 'linked']
        resolved_basis[key] = eligible if len(eligible) == len(indices) and indices else []
        notes[key] = ('有关联定位，但修改内容和语义仍需教师核对。' if resolved_basis[key]
            else '未关联到有对应依据的建议，不提供直接填入；仍可自行编辑。')
    result.update(suggestion_basis=resolved_basis, suggestion_notes=notes)
    return result


def saved_review_view(value, review_id):
    result = deepcopy(value)
    if result.get('analysis_version', 1) >= 2:
        return result
    result.update(analysis_version=1, basis_summary='旧版未记录逐条依据；原意见只作待核实记录，不能据此确认缺陷。',
        suggestion_basis={}, suggestion_notes={})
    result['findings'] = [{**item, 'id': finding_id(review_id, index), 'assessment': 'uncertain',
        'original_assessment': None, 'claim_type': 'open_question', 'basis_status': 'legacy',
        'basis_note': '旧版缺少逐条依据；未回填或猜配证据。', 'anchors': []}
        for index, item in enumerate(result.get('findings', []))]
    return result
