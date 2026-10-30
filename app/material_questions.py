"""Faithful text-PDF question segmentation; never invent missing answers.

Source spans are computed before formatting, and can cross actual PDF pages.
Unnumbered scans/images require another workflow; no OCR claim is made here.
"""
import re
from uuid import uuid4
from app.question_quality import _normalized

START = re.compile(r'(?m)^\s*(?:(?:第\s*\d+\s*题\s*[:：.、]?)|(?:\d{1,3}\s*[.、．)）]))\s*')
ANSWER = re.compile(r'(?:参考答案|正确答案|答案)\s*[:：]\s*([^\n]+)')
EXPLANATION = re.compile(r'(?:解析|解答|分析)\s*[:：]\s*([\s\S]*)')
OPTION = re.compile(r'(?:^|\n|\s+)([A-H])[.、．)）]\s*')


def extract_questions(pages, source, *, excerpt='', existing=()):
    text, boundaries = '', []
    for page in pages:
        offset = len(text); text += page['content'] + '\n'
        boundaries.append((offset, len(text) - 1, page['page_number']))
    if excerpt:
        start = text.find(excerpt)
        if start < 0: raise ValueError('选段必须逐字来自所选资料页，不能改写后作为原文。')
        ranges = [(start, start + len(excerpt))]
    else:
        marks = list(START.finditer(text))
        ranges = [(mark.start(), marks[i + 1].start() if i + 1 < len(marks) else len(text)) for i, mark in enumerate(marks)]
    output = []
    seen = set()
    bank = {_normalized(str(x['stem'])) for x in existing}
    for start, stop in ranges:
        raw = text[start:stop].strip()
        body = START.sub('', raw, count=1).strip()
        if len(body) < 5 or len(body) > 12000: continue
        answer = ANSWER.search(body); explanation = EXPLANATION.search(body)
        cut = min([m.start() for m in (answer, explanation) if m] or [len(body)])
        question = body[:cut].strip()
        matches = list(OPTION.finditer(question))
        options = []
        if len(matches) >= 2:
            stem = question[:matches[0].start()].strip()
            for i, match in enumerate(matches):
                value = question[match.end():matches[i + 1].start() if i + 1 < len(matches) else len(question)].strip()
                options.append(match.group(1) + '. ' + value)
            kind = 'multiple_choice' if '多选' in stem else 'single_choice'
        else:
            stem = question
            kind = 'true_false' if '判断' in stem else 'fill_blank' if '填空' in stem or re.search(r'_{2,}', stem) else 'short_answer'
        correct = answer.group(1).strip() if answer else ''
        if kind == 'true_false':
            options = ['A. 正确', 'B. 错误']
            if correct in {'正确', '对', '√', 'True', 'true'}: correct = 'A'
            elif correct in {'错误', '错', '×', 'False', 'false'}: correct = 'B'
        if len(stem) < 2 or len(stem) > 5000: continue
        key = _normalized(stem)
        duplicate = key in bank or key in seen
        seen.add(key)
        spans = []
        for lo, hi, page in boundaries:
            left, right = max(start, lo), min(stop, hi)
            if left < right and text[left:right].strip():
                spans.append(dict(page_number=page, quote=text[left:right], start_offset=left-lo, end_offset=right-lo))
        output.append(dict(candidate_id=str(uuid4()), question_type=kind, stem=stem, options=options,
            correct_answer=correct[:2000], explanation=explanation.group(1).strip()[:5000] if explanation else '',
            difficulty=2, knowledge_point='', duplicate=duplicate, needs_answer=not bool(correct),
            source={**source, 'spans':spans, 'original_text':raw, 'answer_origin':'source' if answer else 'missing',
                'origin':'teacher_excerpt' if excerpt else 'material_extracted'}))
        if len(output) >= 50: break
    return output
