"""Saved teaching-analysis inputs, separate from model conclusions.

No legacy backfill: current records can check freshness, not reconstruct the
exact text an older model saw. Payload digests prove storage identity only.
"""
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
from uuid import UUID

from app.assessment import AssessmentService
from app.models import Assignment, AssignmentSubmission, TeachingDraft, User
from app.teaching_drafts import TeachingDraftService


class AnalysisInputChanged(ValueError):
    """The input changed before the explicitly requested external operation."""


def input_digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def saved_analysis_input(kind, data, *, online, captured_at=None):
    return {'version': 1, 'kind': kind, 'input_kind': 'online' if online else 'local_outline',
        'captured_at': captured_at or datetime.now(timezone.utc).isoformat(),
        'input': deepcopy(data), 'input_sha256': input_digest(data)}


def content_notes(content, data):
    """Bounded wording reminders, not semantic verification or a verdict."""
    notes = []
    def affirmative(pattern, line):
        return any(not re.search(r'不代表|不能|不得|不要|不等于|不意味着',
            line[max(0, match.start()-18):match.start()]) for match in re.finditer(pattern, line))
    if data.get('pending_review_count') == 0 and data.get('graded_count', 0) > 0:
        for line in content.splitlines():
            if affirmative(r'需(?:要)?人工.{0,12}(?:批阅|批改)|尚未(?:完成)?(?:批改|评分)|还[需要].{0,8}批[改阅]', line):
                notes.append({'code': 'grading_wording', 'excerpt': line[:350],
                    'message': f"生成时已批改{data['graded_count']}份、待批改0份。请核对这句话是否把主观题无逐题客观判定误写成尚未批改；这里只是措辞提醒，不是自动判错。"})
                break
    if data.get('student_name') and any(question.get('question_type') == 'short_answer' for question in data.get('questions', [])):
        for line in content.splitlines():
            if affirmative(r'(?:主观题|简答题|案例题).{0,24}(?:未得分|零分|0\s*分|得了?满分)', line):
                notes.append({'code': 'individual_question_score', 'excerpt': line[:350],
                    'message': '本次输入只有整份成绩与教师评语，没有主观题逐题分数。请核对这句话是否推断了未提供的得分；不是平台的评分结论。'})
                break
    return notes


class AnalysisBasisService:
    def __init__(self, session_factory):
        self._session_factory = session_factory

    def get(self, draft_id, *, actor_id, role, question_page=1, work_page=1, page_size=5):
        # Imports are lazy so generators can use the pure saved-input helper.
        from app.assignment_reviews import AssignmentReviewService
        from app.student_answer_analysis import StudentAnswerAnalysisService
        with self._session_factory() as session:
            actor = session.get(User, actor_id)
            draft = session.get(TeachingDraft, draft_id)
            if (not actor or not actor.active or actor.role != role or
                    not TeachingDraftService._accessible(session, draft, actor_id, role)):
                raise PermissionError('草稿不存在或当前用户无权查看。')
            if draft.draft_type not in {'review', 'student_analysis'}:
                raise ValueError('本入口用于作业讲评和个人作答分析。')
            context = draft.source_context
            try:
                assignment_id = UUID(context['assignment_id'])
                assignment = session.get(Assignment, assignment_id)
                if (not assignment or assignment.course_id != draft.course_id or
                        not AssessmentService._can_access_assignment(session, assignment, actor_id, role)):
                    raise PermissionError('关联作业不存在或当前不可访问。')
                if draft.draft_type == 'student_analysis':
                    submission = session.get(AssignmentSubmission, UUID(context['submission_id']))
                    if not submission or submission.assignment_id != assignment.id:
                        raise PermissionError('原提交记录不存在或已不属于本作业。')
                    current = StudentAnswerAnalysisService._snapshot(session, submission, assignment)
                else:
                    current = AssignmentReviewService._snapshot(session, assignment,
                        include_student_answers=bool(context.get('work_signature')))
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError('旧草稿没有完整的作业关联，不能猜配分析依据。') from exc
            stale = (current['signature'] != context['snapshot_signature'] or bool(
                context.get('work_signature') and current.get('work_signature') != context['work_signature'])) if context.get('snapshot_signature') else None
            saved = context.get('analysis_basis')
            valid = bool(isinstance(saved, dict) and saved.get('version') == 1 and
                saved.get('kind') == draft.draft_type and isinstance(saved.get('input'), dict) and
                saved.get('input_sha256') == input_digest(saved['input']))
            data = saved['input'] if valid else {}
            questions = sorted(data.get('questions', []), key=lambda item: item.get('position', 0))
            work = data.get('student_work', [])
            facts = {key: data.get(key) for key in ('course_title', 'assignment_title', 'submission_count',
                'graded_count', 'pending_review_count', 'average_percent', 'question_count_total',
                'question_count_analyzed', 'student_work_included', 'student_work_total', 'student_name',
                'grading_status', 'recorded_score', 'max_score', 'teacher_feedback', 'teacher_feedback_truncated') if key in data}
            if not valid:
                # These values were actually saved, unlike absent question/work text.
                facts = {key: context[key] for key in ('submission_count', 'graded_count', 'pending_review_count',
                    'average_percent', 'student_work_included', 'student_work_total', 'student_name',
                    'question_count_total', 'question_count_analyzed') if key in context}
            by_id = {question['question_id']: question for question in questions}
            def work_view(item):
                return {**item, 'answers': [{'question_id': key,
                    'position': by_id[key].get('position', list(by_id).index(key) + 1),
                    'stem': by_id[key]['stem'][:80], 'answer': value,
                    'truncated': key in item.get('truncated_answer_ids', [])}
                    for key, value in sorted(item.get('answers', {}).items(),
                        key=lambda entry: by_id.get(entry[0], {}).get('position', 0)) if key in by_id]}
            def page(items, number, mapper=lambda item: item):
                return {'items': [mapper(item) for item in items[(number-1)*page_size:number*page_size]],
                    'total': len(items), 'page': number, 'page_size': page_size}
            return {'draft_id': str(draft.id), 'kind': draft.draft_type, 'assignment_id': str(assignment.id),
                'status': 'saved' if valid else 'unavailable' if saved is not None else 'legacy',
                'captured_at': saved.get('captured_at') if valid else None,
                'input_kind': saved.get('input_kind') if valid else None, 'stale': stale,
                'facts': facts, 'questions': page(questions, question_page), 'work': page(work, work_page, work_view),
                'content_edited': hashlib.sha256(draft.content.encode()).hexdigest() != context['analysis_content_sha256']
                    if context.get('analysis_content_sha256') else None,
                'original_content': context.get('analysis_initial_content') if valid else None,
                'content_notes': content_notes(draft.content, data) if valid else [],
                'notice': ('以下是生成时保存的实际输入；不包含AI新增判断，也不证明建议正确。' if valid
                    else '旧版未保存完整输入，不能用当前作答补成生成时依据。这里只显示原有摘要，可打开当前作业核对。'),
                'scope_note': '讲评按该作业全部提交统计，包含历史提交；具体作答最多30份、题目最多12题。主观题没有逐题客观正误判定，不等于尚未批改。' if draft.draft_type == 'review'
                    else '仅该学生本次提交；最多12题。未批改时记录分数不是最终成绩，节选不代表完整回答。'}
