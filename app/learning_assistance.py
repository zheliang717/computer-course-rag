"""Explicit chapter reading assignments and immutable-answer annotations."""
from uuid import UUID
from sqlalchemy import select
from app.accounts import AccountService
from app.history_access import HistoryAccess
from app.models import (Course, CourseEnrollment, CourseKnowledgeBase, CourseSection,
    CourseSectionReading, Document, DocumentPage, QuestionRecord, AnswerFeedbackAnnotation, QuestionReview)
from app.pagination import sql_page


class LearningAssistanceService:
    def __init__(self, sessions):
        self.sessions = sessions

    @staticmethod
    def course(s, actor, course_id):
        course = s.get(Course, course_id)
        allowed = course and (actor.role == 'admin' or
            actor.role == 'teacher' and course.owner_id == actor.id or
            actor.role == 'student' and course.status == 'published' and s.scalar(select(CourseEnrollment.id).where(
                CourseEnrollment.course_id == course_id, CourseEnrollment.user_id == actor.id,
                CourseEnrollment.status == 'active')))
        if not allowed:
            raise PermissionError('课程不存在或已无权访问。')
        return course

    @staticmethod
    def document(s, actor, course_id, document_id):
        doc = s.get(Document, document_id)
        if not doc or not s.scalar(select(CourseKnowledgeBase.course_id).where(
                CourseKnowledgeBase.course_id == course_id, CourseKnowledgeBase.knowledge_base_id == doc.knowledge_base_id)):
            raise ValueError('资料必须属于该课程已关联的资料库。')
        if actor.role == 'student' and doc.publication_status != 'published':
            raise PermissionError('该资料尚未发布。')
        return doc

    @staticmethod
    def reading(s, item, doc):
        return {'id': str(item.id), 'section_id': str(item.section_id), 'document_id': str(doc.id),
            'document_name': doc.filename, 'first_page': item.first_page, 'last_page': item.last_page,
            'note': item.note, 'position': item.position, 'revision': item.revision}

    def readings(self, principal, section_id, page, page_size):
        with self.sessions() as s:
            actor = AccountService.actor(s, principal)
            section = s.get(CourseSection, section_id)
            if not section: raise PermissionError('章节不存在。')
            self.course(s, actor, section.course_id)
            query = select(CourseSectionReading, Document).join(Document, Document.id == CourseSectionReading.document_id).join(
                CourseKnowledgeBase, (CourseKnowledgeBase.knowledge_base_id == Document.knowledge_base_id) &
                (CourseKnowledgeBase.course_id == section.course_id)).where(CourseSectionReading.section_id == section_id)
            if actor.role == 'student': query = query.where(Document.publication_status == 'published')
            return sql_page(s, query.order_by(CourseSectionReading.position, CourseSectionReading.id), page=page,
                page_size=page_size, scalar=False, mapper=lambda pair: self.reading(s, *pair))

    def save_reading(self, principal, section_id, data, reading_id=None):
        with self.sessions.begin() as s:
            actor = AccountService.actor(s, principal, {'teacher', 'admin'})
            section = s.get(CourseSection, section_id)
            if not section: raise PermissionError('章节不存在。')
            AccountService.manager(s, actor, section.course_id)
            doc = self.document(s, actor, section.course_id, data.document_id)
            count = data.last_page - data.first_page + 1
            pages = s.scalars(select(DocumentPage.page_number).where(DocumentPage.document_id == doc.id,
                DocumentPage.page_number.between(data.first_page, data.last_page))).all()
            if len(set(pages)) != count:
                raise ValueError('页码范围不完整，请先核对资料原文。')
            item = s.scalar(select(CourseSectionReading).where(CourseSectionReading.id == reading_id,
                CourseSectionReading.section_id == section_id).with_for_update()) if reading_id else None
            if reading_id and (not item or item.revision != data.revision):
                raise ValueError('阅读安排已更新，请刷新后重新修改。')
            if not item:
                item = CourseSectionReading(section_id=section_id, creator_id=actor.id, revision=1)
                s.add(item)
            else: item.revision += 1
            for key in ('document_id', 'first_page', 'last_page', 'note', 'position'):
                setattr(item, key, getattr(data, key))
            s.flush()
            AccountService.audit(s, actor, 'section_reading_saved', item.id, section_id=str(section_id))
            return self.reading(s, item, doc)

    def delete_reading(self, principal, section_id, reading_id, revision):
        with self.sessions.begin() as s:
            actor = AccountService.actor(s, principal, {'teacher', 'admin'})
            section = s.get(CourseSection, section_id)
            if not section: raise PermissionError('章节不存在。')
            AccountService.manager(s, actor, section.course_id)
            item = s.scalar(select(CourseSectionReading).where(CourseSectionReading.id == reading_id,
                CourseSectionReading.section_id == section_id).with_for_update())
            if not item or item.revision != revision: raise ValueError('阅读安排已更新，请刷新后重试。')
            s.delete(item)
            AccountService.audit(s, actor, 'section_reading_deleted', reading_id)
            return {'deleted': True}

    @staticmethod
    def validate_annotation(answer, data, citation_count):
        # Offsets count Python Unicode code points, never UTF-16 units.
        if data.end_offset <= data.start_offset or answer[data.start_offset:data.end_offset] != data.answer_quote:
            raise ValueError('选段与已保存回答不一致，请重新选择原文。')
        if data.source_index is not None and data.source_index > citation_count:
            raise ValueError('引用编号不属于这条回答。')

    def annotations(self, principal, history_id, data=None, page=1, page_size=10):
        with self.sessions.begin() as s:
            actor = AccountService.actor(s, principal)
            access = HistoryAccess(actor.id, actor.role)
            record = s.scalar(select(QuestionRecord).where(QuestionRecord.id == history_id, access.predicate()))
            if not record: raise PermissionError('回答不存在或当前已无权访问。')
            if data:
                self.validate_annotation(record.answer, data, len(record.citations or []))
                # Replay identical feedback safely after a lost network response.
                item = s.scalar(select(AnswerFeedbackAnnotation).where(AnswerFeedbackAnnotation.history_id == history_id,
                    AnswerFeedbackAnnotation.user_id == actor.id, AnswerFeedbackAnnotation.start_offset == data.start_offset,
                    AnswerFeedbackAnnotation.end_offset == data.end_offset, AnswerFeedbackAnnotation.category == data.category,
                    AnswerFeedbackAnnotation.comment == data.comment))
                if not item:
                    item = AnswerFeedbackAnnotation(history_id=history_id, user_id=actor.id, **data.model_dump())
                    s.add(item); s.flush()
                return self.annotation_dict(item)
            review = s.scalar(select(QuestionReview).where(QuestionReview.question_record_id == history_id))
            result = {'review_status': review.status if review else 'pending',
                'review_note': review.review_note if review else None, 'revised_answer': review.revised_answer if review else None}
            return sql_page(s, select(AnswerFeedbackAnnotation).where(AnswerFeedbackAnnotation.history_id == history_id,
                AnswerFeedbackAnnotation.user_id == actor.id).order_by(AnswerFeedbackAnnotation.created_at.desc(),
                AnswerFeedbackAnnotation.id), page=page, page_size=page_size, mapper=lambda item:self.annotation_dict(item)|result)

    def review_annotations(self, principal, history_id, page=1, page_size=10):
        with self.sessions() as s:
            actor=AccountService.actor(s,principal,{'teacher','admin'})
            access=HistoryAccess(actor.id,actor.role)
            record=s.scalar(select(QuestionRecord).where(QuestionRecord.id==history_id,access.predicate(owner=False,review=True)))
            if not record: raise PermissionError('问答不存在或不在当前课程审核范围。')
            return sql_page(s,select(AnswerFeedbackAnnotation).where(AnswerFeedbackAnnotation.history_id==history_id)
                .order_by(AnswerFeedbackAnnotation.created_at.desc(),AnswerFeedbackAnnotation.id),
                page=page,page_size=page_size,mapper=self.annotation_dict)

    @staticmethod
    def annotation_dict(item):
        return {key: getattr(item, key) for key in ('answer_quote', 'start_offset', 'end_offset', 'category', 'comment', 'source_index', 'created_at')} | {'id': str(item.id)}
