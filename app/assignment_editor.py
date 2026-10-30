from datetime import datetime, timezone
import hashlib
import json
from uuid import UUID
from sqlalchemy import select, delete
from app.accounts import AccountService
from app.assessment import AssessmentService
from app.models import (Assignment, AssignmentQuestion, AssignmentRevisionSnapshot, AssignmentSubmission,
    QuestionBankItem, CourseSection, QuestionSource)
from app.pagination import sql_page
from app.question_quality import review_question_set


class AssignmentEditorService:
    def __init__(self, sessions): self.sessions = sessions

    @staticmethod
    def owned(s, principal, identifier):
        actor = AccountService.actor(s, principal, {'teacher', 'admin'})
        item = s.scalar(select(Assignment).where(Assignment.id == identifier).with_for_update())
        if not item: raise PermissionError('作业不存在。')
        course = AccountService.manager(s, actor, item.course_id)
        if course.status == 'archived': raise ValueError('课程已归档，不能修改作业。')
        return actor, item

    @staticmethod
    def state(s, item):
        rows = s.execute(select(AssignmentQuestion, QuestionBankItem).join(QuestionBankItem).where(
            AssignmentQuestion.assignment_id == item.id).order_by(AssignmentQuestion.position)).all()
        return {'id': str(item.id), 'course_id': str(item.course_id), 'title': item.title,
            'description': item.description, 'due_at': item.due_at.isoformat() if item.due_at else None,
            'status': item.status, 'revision': item.revision, 'ai_policy': item.ai_policy,
            'previous_version_id': str(item.previous_version_id) if item.previous_version_id else None,
            'questions': [{'question_id': str(q.id), 'points': aq.points,
                'question': AssessmentService.question_dict(q, reveal_answer=True)} for aq, q in rows]}

    @classmethod
    def snapshot(cls, s, actor, item, reason):
        existing = s.scalar(select(AssignmentRevisionSnapshot.id).where(AssignmentRevisionSnapshot.assignment_id == item.id,
            AssignmentRevisionSnapshot.revision == item.revision))
        if not existing:
            s.add(AssignmentRevisionSnapshot(assignment_id=item.id, revision=item.revision, actor_id=actor,
                reason=reason, content=cls.state(s, item)))

    def get(self, principal, identifier):
        with self.sessions() as s:
            _, item = self.owned(s, principal, identifier)
            return self.state(s, item)

    def save(self, principal, identifier, data):
        with self.sessions.begin() as s:
            actor, item = self.owned(s, principal, identifier)
            if item.status != 'draft' or s.scalar(select(AssignmentSubmission.id).where(AssignmentSubmission.assignment_id == item.id).limit(1)):
                raise ValueError('已发布或已提交的作业不能覆盖，请创建修订草稿。')
            if item.revision != data.revision: raise ValueError('草稿已被更新，请刷新后再修改。')
            self.snapshot(s, actor.id, item, '编辑前版本')
            ids, questions = set(), []
            for entry in data.questions:
                q = s.scalar(select(QuestionBankItem).where(QuestionBankItem.id == entry.question_id).with_for_update()) if entry.question_id else None
                if entry.question_id and (not q or q.course_id != item.course_id): raise ValueError('题目不存在或不属于该课程。')
                if q and q.id in ids: raise ValueError('一份作业不能重复使用同一题目。')
                if entry.content:
                    old_source = s.get(QuestionSource,q.id) if q else None
                    old_question_id = str(q.id) if q else None
                    content = entry.content.model_dump(exclude={'source_id'})
                    findings = review_question_set([content], [])
                    errors = [r for r in findings if r['severity'] == 'error']
                    if errors: raise ValueError(errors[0]['message'])
                    # Content editing creates an independent question, never rewrites the bank/history.
                    q = QuestionBankItem(course_id=item.course_id, creator_id=actor.id,
                        section_id=q.section_id if q else None, **content)
                    s.add(q); s.flush()
                    if old_source:
                        s.add(QuestionSource(question_id=q.id,source={**old_source.source,'revision_of_question_id':old_question_id}))
                if not q: raise ValueError('请选择题库题目或填写完整新题。')
                ids.add(q.id); questions.append((q, entry.points))
            s.execute(delete(AssignmentQuestion).where(AssignmentQuestion.assignment_id == item.id))
            s.flush()
            for index, (q, points) in enumerate(questions, 1):
                s.add(AssignmentQuestion(assignment_id=item.id, question_id=q.id, position=index, points=points))
            item.title, item.description, item.due_at, item.ai_policy = data.title.strip(), data.description, data.due_at, data.ai_policy
            item.revision += 1
            s.flush(); self.snapshot(s, actor.id, item, data.reason.strip())
            AccountService.audit(s, actor, 'assignment_draft_saved', item.id, revision=item.revision)
            return self.state(s, item)

    def preview(self, principal, identifier):
        with self.sessions() as s:
            _, item = self.owned(s, principal, identifier)
            value = self.state(s, item)
            value['max_score'] = round(sum(q['points'] for q in value['questions']), 2)
            value['signature'] = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            return value

    def publish(self, principal, identifier, data):
        with self.sessions.begin() as s:
            actor, item = self.owned(s, principal, identifier)
            if item.status != 'draft': raise ValueError('仅草稿可发布，当前作业已发布或关闭。')
            value = self.state(s, item)
            value['max_score'] = round(sum(q['points'] for q in value['questions']), 2)
            signature = hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            if data.signature != signature or not data.confirmed: raise ValueError('预览内容已变化，请重新核对后确认发布。')
            if not value['questions']: raise ValueError('请至少加入一道题目。')
            self.snapshot(s, actor.id, item, '发布前草稿')
            item.revision += 1; item.status = 'published'
            s.flush(); self.snapshot(s, actor.id, item, '教师确认发布')
            AccountService.audit(s, actor, 'publish_assignment', item.id, revision=item.revision, max_score=value['max_score'])
            return self.state(s, item)

    def fork(self, principal, identifier, data):
        with self.sessions.begin() as s:
            actor, original = self.owned(s, principal, identifier)
            existing = s.scalar(select(Assignment).where(Assignment.workflow_request_id == data.request_id))
            if existing:
                if existing.previous_version_id != original.id or existing.creator_id != actor.id:
                    raise ValueError('确认编号已用于其他操作。')
                return self.state(s, existing)
            self.snapshot(s, actor.id, original, '保留修订前原版')
            item = Assignment(course_id=original.course_id, creator_id=actor.id, title=(original.title + ' · 修订')[:200],
                description=original.description, status='draft', due_at=original.due_at, ai_policy=original.ai_policy,
                previous_version_id=original.id, revision=1, workflow_request_id=data.request_id)
            s.add(item); s.flush()
            for row in s.scalars(select(AssignmentQuestion).where(AssignmentQuestion.assignment_id == original.id)):
                s.add(AssignmentQuestion(assignment_id=item.id, question_id=row.question_id, position=row.position, points=row.points))
            s.flush(); self.snapshot(s, actor.id, item, '从原版创建独立修订草稿')
            AccountService.audit(s, actor, 'assignment_revision_created', item.id, original_id=str(original.id))
            return self.state(s, item)

    def history(self, principal, identifier, page, page_size):
        with self.sessions() as s:
            self.owned(s, principal, identifier)
            return sql_page(s, select(AssignmentRevisionSnapshot).where(AssignmentRevisionSnapshot.assignment_id == identifier).order_by(
                AssignmentRevisionSnapshot.revision.desc()), page=page, page_size=page_size, mapper=lambda row: {
                    'revision': row.revision, 'reason': row.reason, 'created_at': row.created_at, 'content': row.content})

    def assistant_context(self, principal, assignment_id, question_id):
        from app.learning_assistance import LearningAssistanceService
        with self.sessions() as s:
            actor = AccountService.actor(s, principal, {'student'})
            item = s.get(Assignment, assignment_id)
            if not item or item.status not in ('published', 'closed'): raise PermissionError('作业当前不可访问。')
            LearningAssistanceService.course(s, actor, item.course_id)
            q = s.scalar(select(QuestionBankItem).join(AssignmentQuestion).where(AssignmentQuestion.assignment_id == item.id,
                AssignmentQuestion.question_id == question_id))
            if not q: raise ValueError('题目不属于当前作业。')
            instruction = {'disabled': '教师未开启本作业的AI辅助。',
                'hints': '教师仅允许思路提示：只点明相关概念、解题入口或给一个引导性问题；不要给选项、最终答案或可直接提交的完整解法。',
                'guided': '教师允许分步辅导：结合题目解释思路与步骤；请让学生自己组织作答，不宣称替学生完成提交。'}[item.ai_policy]
            return {'assignment_id': str(item.id), 'question_id': str(q.id), 'course_id': str(item.course_id),
                'title': item.title, 'revision': item.revision, 'policy': item.ai_policy, 'instruction': instruction,
                'question': {'stem': q.stem, 'options': q.options, 'knowledge_point': q.knowledge_point}}
