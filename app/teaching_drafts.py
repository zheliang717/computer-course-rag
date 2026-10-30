from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.models import AuditLog, Course, QuestionBankItem, TeachingDraft, TeachingWorkResult, QuestionSource
from app.question_quality import review_question_set
from app.pagination import sql_page


class TeachingDraftService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def list(self, *, creator_id: UUID, role: str, course_id: UUID | None = None,
             page: int | None = None, page_size: int = 10, exclude_archived: bool = False) -> list[dict] | dict:
        with self._session_factory() as session:
            query = select(TeachingDraft).join(Course, Course.id == TeachingDraft.course_id).order_by(TeachingDraft.updated_at.desc(), TeachingDraft.id.desc())
            if role != "admin":
                query = query.where(TeachingDraft.creator_id == creator_id, Course.owner_id == creator_id)
            if course_id:
                query = query.where(TeachingDraft.course_id == course_id)
            if exclude_archived:
                query = query.where(TeachingDraft.status != "archived")
            if page is not None:
                return sql_page(session, query, page=page, page_size=page_size,
                                mapper=lambda item: self._dict(item, session.get(Course, item.course_id)))
            return [self._dict(item, session.get(Course, item.course_id)) for item in session.scalars(query).all()]

    def get(self, draft_id: UUID, *, actor_id: UUID, role: str) -> dict | None:
        with self._session_factory() as session:
            item = session.get(TeachingDraft, draft_id)
            course = session.get(Course, item.course_id) if item else None
            if item is None or course is None or role not in {"teacher", "admin"}:
                return None
            if role != "admin" and (item.creator_id != actor_id or course.owner_id != actor_id):
                return None
            return self._dict(item, course)

    def create(self, *, creator_id: UUID, data: dict, task_context=None, usage=None) -> dict:
        with self._session_factory() as session:
            course_id = UUID(data.pop("course_id"))
            course = session.get(Course, course_id)
            if course is None:
                raise LookupError("课程不存在。")
            task = None
            if task_context:
                service, task_id, attempt, principal = task_context
                task = service.fence(session, principal, task_id, attempt)
                if task.course_id != course_id: raise PermissionError('任务课程不匹配。')
            item = TeachingDraft(course_id=course_id, creator_id=creator_id, **data)
            session.add(item); session.flush()
            if usage:
                from app.model_usage import ModelUsageService
                ModelUsageService.finish_in_session(session, **usage, successful=True)
            if task is not None:
                task.status, task.stage, task.result = 'completed', '草稿已保存，等待教师审核', {'draft_id': str(item.id)}
                task.updated_at, task.lease_expires_at = datetime.now(timezone.utc), None
            session.commit(); session.refresh(item)
            return self._dict(item, course)

    def update(self, draft_id: UUID, *, actor_id: UUID, role: str, data: dict) -> dict | None:
        with self._session_factory() as session:
            item = session.scalar(select(TeachingDraft).where(TeachingDraft.id == draft_id).with_for_update())
            if not self._accessible(session, item, actor_id, role):
                return None
            if item.status == "published":
                raise ValueError("已入库的题目草稿不可修改。")
            content_changed = any(
                key in data and data[key] is not None and data[key] != getattr(item, key)
                for key in ("title", "content", "questions")
            )
            if content_changed and item.status == "confirmed":
                if data.get("status") != "confirmed":
                    item.status = "draft"
                item.confirmed_at = None
            for key, value in data.items():
                if value is not None:
                    setattr(item, key, value)
            if data.get("status") == "confirmed" and item.confirmed_at is None:
                item.confirmed_at = datetime.now(timezone.utc)
            elif data.get("status") == "draft":
                item.confirmed_at = None
            session.commit(); session.refresh(item)
            return self._dict(item, session.get(Course, item.course_id))

    def check_questions(self, draft_id: UUID, *, actor_id: UUID, role: str) -> dict | None:
        with self._session_factory() as session:
            item = session.get(TeachingDraft, draft_id)
            if not self._accessible(session, item, actor_id, role):
                return None
            if item.draft_type != "question_set":
                raise ValueError("只有题目草稿可以执行题目质量检查。")
            existing = self._existing_questions(session, item.course_id)
            findings = review_question_set(item.questions, existing)
            return {
                "draft_id": str(item.id), "question_count": len(item.questions),
                "error_count": sum(entry["severity"] == "error" for entry in findings),
                "warning_count": sum(entry["severity"] == "warning" for entry in findings),
                "findings": findings,
            }

    def question_for_review(self, draft_id: UUID, *, actor_id: UUID, role: str,
                            question_index: int) -> dict | None:
        with self._session_factory() as session:
            item = session.get(TeachingDraft, draft_id)
            if not self._accessible(session, item, actor_id, role):
                return None
            if item.draft_type != "question_set":
                raise ValueError("只有题目草稿可以进行 AI 复核。")
            if question_index > len(item.questions):
                raise ValueError("题目序号超出当前草稿范围。")
            return {"draft_id": str(item.id), "course_id": str(item.course_id),
                    "question_index": question_index, "question": item.questions[question_index - 1]}

    def publish_questions(self, draft_id: UUID, *, actor_id: UUID, role: str,
                          actor_name: str = "") -> tuple[dict, list[str]] | None:
        with self._session_factory() as session:
            item = session.scalar(select(TeachingDraft).where(TeachingDraft.id == draft_id).with_for_update())
            if item is None or (role != "admin" and item.creator_id != actor_id):
                return None
            course = session.get(Course, item.course_id)
            if course is None or (role != "admin" and course.owner_id != actor_id):
                return None
            if item.draft_type != "question_set":
                raise ValueError("只有题目草稿可以写入题库。")
            if item.status != "confirmed":
                raise ValueError("请先逐题审核并确认草稿。")
            if not item.questions:
                raise ValueError("草稿中没有可入库的结构化题目。")
            findings = review_question_set(item.questions, self._existing_questions(session, item.course_id))
            first_error = next((entry for entry in findings if entry["severity"] == "error"), None)
            if first_error:
                raise ValueError(f"第 {first_error['question_index']} 题质量检查未通过：{first_error['message']}")
            created_ids: list[str] = []
            work = None
            try:
                work_id=item.source_context.get('work_result_id')
                work=session.get(TeachingWorkResult,UUID(work_id)) if work_id else None
            except (ValueError,TypeError): pass
            trusted_sources = {x['candidate_id']: x['source'] for x in work.content.get('candidates', [])} if (
                work and work.kind=='material_extract' and work.course_id==item.course_id and
                work.content.get('draft_id')==str(item.id)) else {}
            for question in item.questions:
                question_type = question["question_type"]
                options = [str(value).strip() for value in question.get("options", []) if str(value).strip()]
                answer = question["correct_answer"].strip()
                if question_type in {"single_choice", "multiple_choice", "true_false"} and len(options) < 2:
                    raise ValueError("选择题、判断题或多选题至少需要两个选项。")
                if question_type == "multiple_choice" and len([value for value in answer.replace("，", ",").split(",") if value.strip()]) < 2:
                    raise ValueError("多选题至少需要两个正确答案，使用逗号分隔。")
                entry = QuestionBankItem(course_id=item.course_id, creator_id=actor_id,
                    question_type=question_type, stem=question["stem"].strip(), options=options,
                    correct_answer=answer, explanation=question.get("explanation"),
                    difficulty=question.get("difficulty", 2), knowledge_point=question.get("knowledge_point"))
                session.add(entry)
                session.flush()
                created_ids.append(str(entry.id))
                if question.get('source_id') in trusted_sources:
                    session.add(QuestionSource(question_id=entry.id,source={**trusted_sources[question['source_id']],
                        'candidate_id':question['source_id'],'work_result_id':str(work.id),'teacher_confirmed':True,
                        'answer_origin':'teacher_reviewed','original_answer_origin':trusted_sources[question['source_id']].get('answer_origin')}))
            item.status = "published"
            item.source_context = {**item.source_context, "published_question_ids": created_ids,
                                   "published_at": datetime.now(timezone.utc).isoformat()}
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action="publish_questions",
                resource_type="teaching_draft", resource_id=str(draft_id),
                detail={"course_id": str(item.course_id), "question_ids": created_ids}))
            session.commit()
            session.refresh(item)
            return self._dict(item, session.get(Course, item.course_id)), created_ids

    @staticmethod
    def _accessible(session, item, actor_id, role):
        course = session.get(Course, item.course_id) if item else None
        return bool(item and course and (role == 'admin' or role == 'teacher' and
            item.creator_id == actor_id and course.owner_id == actor_id))

    @staticmethod
    def _existing_questions(session, course_id: UUID) -> list[dict]:
        return [
            {"id": str(question_id), "stem": stem}
            for question_id, stem in session.execute(
                select(QuestionBankItem.id, QuestionBankItem.stem).where(QuestionBankItem.course_id == course_id)
            ).all()
        ]

    @staticmethod
    def _dict(item: TeachingDraft, course: Course | None) -> dict:
        from app.teaching_quality import findings
        context={**item.source_context,'teaching_quality':dict(policy='concept-boundaries-v1',teacher_approved=False,findings=findings(item.content))}
        return {"id": str(item.id), "course_id": str(item.course_id), "course_title": course.title if course else "已删除课程",
                "creator_id": str(item.creator_id) if item.creator_id else None, "draft_type": item.draft_type,
                "title": item.title, "content": item.content, "source_context": context, "questions": item.questions,
                "status": item.status, "confirmed_at": item.confirmed_at, "created_at": item.created_at, "updated_at": item.updated_at}
