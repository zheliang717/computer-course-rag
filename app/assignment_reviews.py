"""Teacher-reviewed class feedback, optionally informed by named student work."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select

from app.assessment import AssessmentService
from app.models import (
    Assignment, AssignmentQuestion, AssignmentSubmission, AuditLog, Course, QuestionBankItem,
    SubmissionReview, TeachingDraft, User,
)
from app.teaching_drafts import TeachingDraftService
from app.analysis_basis import saved_analysis_input
from app.model_usage import ModelUsageService


class AssignmentReviewService:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def snapshot(self, assignment_id: UUID, *, actor_id: UUID, role: str, include_student_answers: bool = False) -> dict | None:
        with self._session_factory() as session:
            assignment = session.get(Assignment, assignment_id)
            actor = session.get(User, actor_id)
            if actor is None or not actor.active or actor.role != role or assignment is None or role not in {"teacher", "admin"} or not AssessmentService._can_access_assignment(
                session, assignment, actor_id, role,
            ):
                return None
            return self._snapshot(session, assignment, include_student_answers=include_student_answers)

    @staticmethod
    def prompt_data(snapshot):
        questions = sorted(snapshot['questions'], key=lambda item: item['wrong_count'], reverse=True)[:12]
        data = {key: snapshot[key] for key in ('course_title', 'assignment_title', 'submission_count',
            'graded_count', 'pending_review_count', 'average_percent', 'weak_points')}
        data.update(question_count_total=snapshot['question_count'], question_count_analyzed=len(questions),
            questions=[{**item, 'stem': item['stem'][:600], 'correct_answer': item['correct_answer'][:300],
                'explanation': (item['explanation'] or '')[:500],
                'options': [str(option)[:500] for option in item.get('options', [])[:20]],
                'input_truncated': len(item['stem']) > 600 or len(item['correct_answer']) > 300 or
                    len(item['explanation'] or '') > 500 or len(item.get('options', [])) > 20 or
                    any(len(str(option)) > 500 for option in item.get('options', []))} for item in questions])
        for question in data['questions']:
            if 'student_work' not in snapshot:
                # Aggregate-only consent must not leak a one-person free-text
                # answer through the otherwise anonymous distribution field.
                question.pop('answer_distribution', None)
                question.pop('distribution_other_count', None)
            # Do not expose an ambiguous "unscored" field as a grading status.
            question.pop('unscored_count', None)
            question['objective_counts_available'] = question['question_type'] != 'short_answer'
            if not question['objective_counts_available']:
                question.pop('correct_count', None)
                question.pop('wrong_count', None)
                question['judgment_note'] = '此题没有逐题客观正误判定；不能据此推断整份提交尚未批改。'
        if 'student_work' in snapshot:
            data.update(student_work=snapshot['student_work'], student_work_included=snapshot['student_work_included'],
                student_work_total=snapshot['student_work_total'])
        if len(json.dumps(data, ensure_ascii=False)) > 70000:
            raise ValueError('本次讲评输入过长，暂不发送给模型；请先缩小作业题量。')
        return data

    def save_draft(self, assignment_id, *, actor_id, actor_name, role, snapshot, content, model, online, usage=None, task_context=None):
        with self._session_factory() as session:
            from app.assistant_tasks import task_fence, complete_task
            task_fence(session, task_context)
            actor = session.get(User, actor_id)
            assignment = session.scalar(select(Assignment).where(Assignment.id == assignment_id).with_for_update())
            if (not actor or not actor.active or actor.role != role or role not in {'teacher', 'admin'} or
                    not assignment or not AssessmentService._can_access_assignment(session, assignment, actor_id, role)):
                raise PermissionError('作业不存在或当前用户无权生成讲评。')
            current = self._snapshot(session, assignment, include_student_answers='work_signature' in snapshot)
            if (current['signature'] != snapshot['signature'] or
                    current.get('work_signature') != snapshot.get('work_signature')):
                raise ValueError('等待期间作业提交、题目或批改记录已变化，未保存旧讲评，请按当前记录重新生成。')
            context = {'origin': 'assignment_review', 'assignment_id': str(assignment_id),
                'snapshot_signature': snapshot['signature'], 'model': model,
                **{key: snapshot[key] for key in ('submission_count', 'graded_count', 'pending_review_count',
                    'average_percent', 'weak_points')},
                'analysis_basis': saved_analysis_input('review', self.prompt_data(snapshot), online=online,
                    captured_at=snapshot.get('captured_at')),
                'analysis_initial_content': content,
                'analysis_content_sha256': hashlib.sha256(content.encode()).hexdigest()}
            if 'work_signature' in snapshot:
                context.update(work_signature=snapshot['work_signature'], includes_student_answers=True,
                    student_work_included=snapshot['student_work_included'], student_work_total=snapshot['student_work_total'])
            draft = TeachingDraft(course_id=assignment.course_id, creator_id=actor_id, draft_type='review',
                title=f"{snapshot['assignment_title'][:175]} · 作业讲评", content=content, questions=[], source_context=context)
            session.add(draft)
            session.flush()
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action='generate_assignment_review_draft',
                resource_type='assignment', resource_id=str(assignment_id), detail={'draft_id': str(draft.id),
                    'course_id': str(assignment.course_id), 'model': model, 'includes_student_answers': 'work_signature' in snapshot,
                    'student_work_included': snapshot.get('student_work_included', 0),
                    'submission_count': snapshot['submission_count'], 'basis_version': 1}))
            if usage:
                ModelUsageService.finish_in_session(session, **usage, successful=True)
            complete_task(session, task_context, draft.id)
            session.commit()
            return TeachingDraftService._dict(draft, session.get(Course, assignment.course_id))

    def publish(self, draft_id: UUID, *, actor_id: UUID, actor_name: str, role: str) -> dict | None:
        with self._session_factory() as session:
            draft = session.scalar(select(TeachingDraft).where(TeachingDraft.id == draft_id).with_for_update())
            if draft is None or role not in {"teacher", "admin"} or (role != "admin" and draft.creator_id != actor_id):
                return None
            if draft.draft_type != "review" or not draft.source_context.get("assignment_id"):
                raise ValueError("只有关联具体作业的讲评草稿可以发布。")
            if draft.status != "confirmed":
                raise ValueError("请先由教师核对并确认讲评草稿。")
            assignment_id = UUID(draft.source_context["assignment_id"])
            assignment = session.scalar(select(Assignment).where(Assignment.id == assignment_id).with_for_update())
            if assignment is None or assignment.course_id != draft.course_id or not AssessmentService._can_access_assignment(
                session, assignment, actor_id, role,
            ):
                return None
            current = self._snapshot(session, assignment, include_student_answers=bool(draft.source_context.get("work_signature")))
            if current["submission_count"] == 0:
                raise ValueError("该作业尚无提交，不能发布讲评。")
            if current["pending_review_count"]:
                raise ValueError("仍有待批改提交，请完成批改后重新生成讲评草稿。")
            if current["signature"] != draft.source_context.get("snapshot_signature"):
                raise ValueError("作业提交或批改结果已变化，请重新生成讲评草稿。")
            if draft.source_context.get("work_signature") and current.get("work_signature") != draft.source_context["work_signature"]:
                raise ValueError("学生具体作答或教师评语已变化，请重新生成详细讲评草稿。")
            previous_id = str(assignment.published_review_draft_id) if assignment.published_review_draft_id else None
            if assignment.published_review_draft_id:
                previous = session.get(TeachingDraft, assignment.published_review_draft_id)
                if previous is not None:
                    previous.status = "archived"
                    previous.source_context = {**previous.source_context, "superseded_by": str(draft.id)}
            published_at = datetime.now(timezone.utc)
            draft.status = "published"
            draft.source_context = {**draft.source_context, "published_at": published_at.isoformat()}
            assignment.published_review_draft_id = draft.id
            session.add(AuditLog(
                actor_id=actor_id, actor_name=actor_name, action="publish_assignment_review",
                resource_type="assignment", resource_id=str(assignment.id),
                detail={"draft_id": str(draft.id), "course_id": str(draft.course_id),
                        "replaced_draft_id": previous_id},
            ))
            session.commit()
            session.refresh(draft)
            return TeachingDraftService._dict(draft, session.get(Course, draft.course_id))

    def revision(self, draft_id: UUID, *, actor_id: UUID, actor_name: str, role: str) -> dict | None:
        """Copy published text for editing without another model call or replacing students' view."""
        with self._session_factory() as session:
            source = session.scalar(select(TeachingDraft).where(TeachingDraft.id == draft_id).with_for_update())
            if source is None or role not in {'teacher', 'admin'} or (role != 'admin' and source.creator_id != actor_id):
                return None
            if source.draft_type != 'review' or source.status not in {'published', 'archived'} or not source.source_context.get('assignment_id'):
                raise ValueError('只有已发布或保留的旧版作业讲评可创建修订稿。')
            assignment = session.get(Assignment, UUID(source.source_context['assignment_id']))
            if assignment is None or assignment.course_id != source.course_id or not AssessmentService._can_access_assignment(
                    session, assignment, actor_id, role):
                return None
            existing = session.scalar(select(TeachingDraft).where(TeachingDraft.creator_id == actor_id,
                TeachingDraft.course_id == source.course_id, TeachingDraft.draft_type == 'review',
                TeachingDraft.status.in_(('draft', 'confirmed')),
                TeachingDraft.source_context['revision_of'].astext == str(source.id))
                .order_by(TeachingDraft.updated_at.desc(), TeachingDraft.id.desc()).limit(1))
            if existing:
                return TeachingDraftService._dict(existing, session.get(Course, existing.course_id))
            context = {key: value for key, value in source.source_context.items() if key not in {'published_at', 'superseded_by'}}
            item = TeachingDraft(course_id=source.course_id, creator_id=actor_id, draft_type='review',
                title=(source.title + ' · 修订')[:200], content=source.content, questions=[], status='draft',
                source_context={**context, 'origin': 'teacher_revision', 'revision_of': str(source.id),
                    'revision_started_at': datetime.now(timezone.utc).isoformat()})
            session.add(item)
            session.flush()
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action='revise_assignment_review',
                resource_type='teaching_draft', resource_id=str(item.id), detail={'source_draft_id': str(source.id),
                    'assignment_id': str(assignment.id), 'course_id': str(source.course_id)}))
            session.commit()
            return TeachingDraftService._dict(item, session.get(Course, item.course_id))

    def published(self, assignment_id: UUID, *, user_id: UUID, role: str) -> dict | None:
        with self._session_factory() as session:
            assignment = session.get(Assignment, assignment_id)
            if assignment is None or not AssessmentService._can_access_assignment(session, assignment, user_id, role):
                return None
            if role == "student" and session.scalar(select(AssignmentSubmission.id).where(
                AssignmentSubmission.assignment_id == assignment_id, AssignmentSubmission.student_id == user_id,
            )) is None:
                return None
            draft = session.get(TeachingDraft, assignment.published_review_draft_id) if assignment.published_review_draft_id else None
            if draft is None or draft.status != "published" or draft.course_id != assignment.course_id:
                return None
            current = self._snapshot(session, assignment, include_student_answers=bool(draft.source_context.get("work_signature")))
            stale = current["signature"] != draft.source_context.get("snapshot_signature") or bool(
                draft.source_context.get("work_signature") and current.get("work_signature") != draft.source_context["work_signature"])
            if role == "student" and stale:
                return None
            return {"assignment_id": str(assignment.id), "draft_id": str(draft.id),
                    "title": draft.title, "content": draft.content,
                    "published_at": draft.source_context.get("published_at"), "stale": stale}

    @staticmethod
    def local_outline(snapshot: dict) -> str:
        lines = [f"## {snapshot['assignment_title']} · 作业讲评草稿", "",
                 "> 当前未使用在线模型；以下根据平台汇总统计准备，需教师补充分析后确认。", "",
                 f"已提交 {snapshot['submission_count']} 人，已批改 {snapshot['graded_count']} 人，"
                 f"待批改 {snapshot['pending_review_count']} 人。"]
        if snapshot["average_percent"] is not None:
            lines.append(f"已批改提交的平均得分率：{snapshot['average_percent']}%。")
        lines.extend(["", "### 高频易错点"])
        weak = sorted(snapshot["questions"], key=lambda item: item.get("wrong_count", 0), reverse=True)
        for question in weak[:8]:
            if question.get("wrong_count", 0):
                lines.append(f"- {question['knowledge_point'] or '未标注知识点'}："
                             f"{question['wrong_count']} 人答错；请核对「{question['stem'][:90]}」。")
        if not any(item.get("wrong_count", 0) for item in weak):
            lines.append("- 当前客观题未发现错误记录；主观题仍需结合教师评语分析。")
        lines.extend(["", "### 教师待补充", "- 针对高频错误解释原因与正确思路。",
                      "- 补充一题同类练习，并说明下次课堂如何检查掌握情况。"])
        return "\n".join(lines)

    @staticmethod
    def _snapshot(session, assignment: Assignment, *, include_student_answers: bool = False) -> dict:
        course = session.get(Course, assignment.course_id)
        links = list(session.scalars(select(AssignmentQuestion).where(
            AssignmentQuestion.assignment_id == assignment.id,
        ).order_by(AssignmentQuestion.position)).all())
        questions = {link.question_id: session.get(QuestionBankItem, link.question_id) for link in links}
        submissions = list(session.scalars(select(AssignmentSubmission).where(
            AssignmentSubmission.assignment_id == assignment.id,
        )).all())
        reviews = {row.submission_id: row for row in session.scalars(select(SubmissionReview).where(
            SubmissionReview.submission_id.in_([submission.id for submission in submissions]),
        )).all()} if submissions else {}
        graded = [item for item in submissions if item.status == "graded"]
        percentages = [
            round(100 * (reviews[item.id].score if item.id in reviews else item.score) / item.max_score, 2)
            for item in graded if item.max_score > 0
        ]
        summary_questions = []
        weak_points: Counter[str] = Counter()
        for link in links:
            question = questions[link.question_id]
            if question is None:
                continue
            correct_count = wrong_count = unscored_count = 0
            for submission in submissions:
                if question.question_type == "short_answer":
                    unscored_count += 1
                    continue
                given = str((submission.answers or {}).get(str(question.id), ""))
                if AssessmentService._answer_matches(question, given):
                    correct_count += 1
                else:
                    wrong_count += 1
            if wrong_count:
                weak_points[question.knowledge_point or "未标注知识点"] += wrong_count
            summary_questions.append({
                "question_id": str(question.id), "stem": question.stem, "question_type": question.question_type,
                "knowledge_point": question.knowledge_point, "correct_answer": question.correct_answer,
                "explanation": question.explanation, "correct_count": correct_count,
                "wrong_count": wrong_count, "unscored_count": unscored_count,
            })
        snapshot = {"assignment_id": str(assignment.id), "course_id": str(assignment.course_id),
                    "course_title": course.title if course else "课程", "assignment_title": assignment.title,
                    "question_count": len(summary_questions), "submission_count": len(submissions),
                    "graded_count": len(graded), "pending_review_count": len(submissions) - len(graded),
                    "average_percent": round(sum(percentages) / len(percentages), 1) if percentages else None,
                    "weak_points": weak_points.most_common(5), "questions": summary_questions}
        snapshot["signature"] = hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        positions = {str(link.question_id): link.position for link in links}
        # Preserve the old aggregate signature; add prompt-only fields afterwards.
        snapshot['questions'] = [{**item, 'position': positions[item['question_id']],
            'options': questions[UUID(item['question_id'])].options} for item in summary_questions]
        for item in snapshot['questions']:
            if item['question_type'] != 'short_answer':
                counts = Counter(str((submission.answers or {}).get(item['question_id'], '')) for submission in submissions)
                common = counts.most_common(12)
                item['answer_distribution'] = [{'answer': answer[:200], 'count': count,
                    'answer_truncated': len(answer) > 200} for answer, count in common]
                item['distribution_other_count'] = len(submissions) - sum(count for _, count in common)
        if include_student_answers:
            students = {row.id: row.display_name for row in session.scalars(select(User).where(
                User.id.in_([item.student_id for item in submissions]))).all()} if submissions else {}
            all_work = [{"submission_id": str(item.id), "student_name": students.get(item.student_id, "已删除学生"),
                "grading_status": item.status, "recorded_score": reviews[item.id].score if item.id in reviews else item.score,
                "max_score": item.max_score, "teacher_feedback": reviews[item.id].feedback if item.id in reviews else None,
                "graded_at": reviews[item.id].graded_at.isoformat() if item.id in reviews else None,
                "answers": item.answers or {}} for item in sorted(submissions, key=lambda row: str(row.id))]
            snapshot["work_signature"] = hashlib.sha256(json.dumps({
                "base": snapshot["signature"], "work": all_work,
                "options": {str(key): item.options for key, item in questions.items() if item is not None}},
                ensure_ascii=False, sort_keys=True).encode()).hexdigest()
            selected_questions = sorted(snapshot["questions"], key=lambda item: item["wrong_count"], reverse=True)[:12]
            question_ids = [item["question_id"] for item in selected_questions]
            sample = []
            used_chars = 0
            for item in sorted(all_work, key=lambda row: (row["grading_status"] == "graded", row["submission_id"]))[:30]:
                limited = {**item, "teacher_feedback": (item["teacher_feedback"] or "")[:800],
                    "teacher_feedback_truncated": len(item["teacher_feedback"] or "") > 800,
                    "answers": {key: str(item["answers"].get(key, ""))[:600] for key in question_ids},
                    "truncated_answer_ids": [key for key in question_ids if len(str(item["answers"].get(key, ""))) > 600]}
                size = len(json.dumps(limited, ensure_ascii=False))
                if used_chars + size > 30000:
                    break
                sample.append(limited)
                used_chars += size
            snapshot.update(student_work=sample, student_work_included=len(sample), student_work_total=len(submissions))
        snapshot['captured_at'] = datetime.now(timezone.utc).isoformat()
        return snapshot
