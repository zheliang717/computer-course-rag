"""Insert a fictional but coherent autumn-semester dataset for private testing.

No real personal data, external calls or permission changes. Existing records
are never overwritten. Backup first, then python -m scripts.seed_realistic_data --apply.
"""

from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timedelta, timezone
import json
import os
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import func, select

from app.auth import hash_password
from app.database import get_session_factory
from app.models import (
    Assignment, AssignmentQuestion, AssignmentSubmission, AuditLog, Course,
    CourseAnnouncement, CourseEnrollment, CourseKnowledgeBase, CourseSection,
    CourseSession, KnowledgePoint, LateSubmissionRequest, LearningProgress,
    PracticeAttempt, QuestionBankItem, StudyPlan, SubmissionReview, User, WrongQuestion,
)
from scripts.realistic_course_fixtures import COURSE_SPECS, STUDENT_NAMES, TEACHERS, TOPICS


ZONE = timezone(timedelta(hours=8))
TERM_START = datetime(2026, 9, 7, tzinfo=ZONE)
AS_OF = datetime(2026, 10, 10, 12, tzinfo=ZONE)  # Client-date-based fictional snapshot.
PASSWORD = "campus123456"  # Public internal-test credential, not a production secret.


def fixture_id(kind: str, key: str):
    return uuid5(NAMESPACE_URL, f"computer-course-rag:realistic-autumn-2026:v1:{kind}:{key}")


def seed(session) -> Counter:
    added = Counter()

    def insert(model, key, *, unique=None, **values):
        row_id = fixture_id(model.__tablename__, key)
        row = session.get(model, row_id)
        if row is not None:
            return row
        if unique is not None and session.scalar(select(model.id).where(unique)) is not None:
            raise RuntimeError(f"{model.__tablename__} 唯一字段冲突：{key}；整批回滚，不覆盖已有数据。")
        if model is User:
            values["password_hash"] = hash_password(PASSWORD)
        row = model(id=row_id, **values)
        session.add(row)
        session.flush()
        added[model.__tablename__] += 1
        return row

    primary_teacher = session.scalar(select(User).where(User.username == "teacher", User.role == "teacher"))
    primary_student = session.scalar(select(User).where(User.username == "student", User.role == "student"))
    admin = session.scalar(select(User).where(User.username == "admin", User.role == "admin"))
    if not primary_teacher or not primary_student or not admin:
        raise RuntimeError("缺少原 teacher/student/admin 账号；未写入任何数据。")

    students = [insert(
        User, f"202410{number:02}", unique=User.username == f"202410{number:02}",
        username=f"202410{number:02}", display_name=name, role="student", active=True,
        created_at=AS_OF - timedelta(minutes=4) + timedelta(seconds=number),
    ) for number, name in enumerate(STUDENT_NAMES, 1)]
    teachers = [insert(
        User, username, unique=User.username == username, username=username,
        display_name=name, role="teacher", active=True, created_at=AS_OF - timedelta(minutes=3) + timedelta(seconds=index),
    ) for index, (username, name) in enumerate(TEACHERS)]

    for course_index, spec in enumerate(COURSE_SPECS):
        title, code, prerequisite, location, weekday, hour = spec
        owner = primary_teacher if course_index < 4 else teachers[course_index - 4]
        topics = TOPICS[course_index]
        course = insert(
            Course, code, unique=Course.code == code, title=title, code=code,
            owner_id=owner.id, status="published", semester="2026—2027 学年第一学期",
            location=location, schedule=f"周{'一二三四五'[weekday]} {hour:02}:00—{hour + 1:02}:40，第 1—16 周",
            description=f"先修课程：{prerequisite}。\n课程目标：理解{title}的核心概念，能够通过案例分析、课堂练习与上机实践解决基础问题。\n教学内容：{'、'.join(topic[0] for topic in topics)}。\n学习要求：课前预习、独立完成章节作业、在实验报告中记录关键步骤与结果。\n考核安排：平时作业 30%，实验与课堂活动 30%，期末综合考核 40%。",
            created_at=AS_OF - timedelta(minutes=2) + timedelta(seconds=course_index),
        )

        # Reuse actual same-subject libraries, without changing document metadata/rights.
        if course_index < 3:
            original = session.scalar(select(Course).where(Course.code == ("DSA-2026", "OS-2026", "NET-2026")[course_index]))
            if original:
                for link in session.scalars(select(CourseKnowledgeBase).where(CourseKnowledgeBase.course_id == original.id)).all():
                    insert(CourseKnowledgeBase, f"{code}:{link.knowledge_base_id}",
                           unique=(CourseKnowledgeBase.course_id == course.id) & (CourseKnowledgeBase.knowledge_base_id == link.knowledge_base_id),
                           course_id=course.id, knowledge_base_id=link.knowledge_base_id)

        sections, question_groups = [], []
        for position, (point, fact, distractors, problem, reference) in enumerate(topics, 1):
            section = insert(
                CourseSection, f"{code}:{position}",
                unique=(CourseSection.course_id == course.id) & (CourseSection.position == position),
                course_id=course.id, position=position, title=f"第 {position} 章  {point}",
                description=f"学习目标\n1. 准确解释{point}的含义与适用条件。\n2. 能够辨析常见误区，并说明判断依据。\n3. 通过案例展示问题分析与求解过程。\n\n核心概念\n{fact}\n\n课堂任务\n{problem}\n\n课后安排\n完成本章练习，整理易错点，带着问题参加答疑。",
            )
            sections.append(section)
            insert(KnowledgePoint, f"{code}:{point}",
                   unique=(KnowledgePoint.course_id == course.id) & (KnowledgePoint.name == point),
                   course_id=course.id, section_id=section.id, name=point, description=f"{fact}\n应用：{problem}")
            correct_index = (course_index + position) % 4
            choices = list(distractors)
            choices.insert(correct_index, fact)
            true_question = position % 2 == 1
            if point not in fact:
                raise RuntimeError(f"填空题缺少关键词：{point}；整批回滚。")
            specs = (
                ("single_choice", f"下列关于{point}的说法，正确的是（ ）。",
                 [f"{letter}. {choice}" for letter, choice in zip("ABCD", choices)], "ABCD"[correct_index]),
                ("true_false", fact if true_question else distractors[0], ["正确", "错误"], "正确" if true_question else "错误"),
                ("fill_blank", f"填写空缺的概念或术语：{fact.replace(point, '____', 1)}", [], point),
                ("short_answer", problem, [], reference),
            )
            group = [insert(
                QuestionBankItem, f"{code}:{position}:{kind}", course_id=course.id, section_id=section.id,
                creator_id=course.owner_id, question_type=kind, stem=stem, options=options, correct_answer=answer,
                explanation=f"{fact}\n\n应用分析\n{reference}", knowledge_point=point,
                difficulty=3 if kind == "short_answer" else 1 + position % 2,
                created_at=AS_OF - timedelta(minutes=1) + timedelta(seconds=course_index * 4 + position),
            ) for kind, stem, options, answer in specs]
            question_groups.append(group)

        for lesson in range(1, 17):
            date = TERM_START + timedelta(weeks=lesson - 1, days=weekday, hours=hour)
            topic = topics[(lesson - 1) // 4][0]
            lab = lesson % 4 == 0
            insert(CourseSession, f"{code}:{lesson}", course_id=course.id,
                   section_id=sections[(lesson - 1) // 4].id, session_date=date,
                   duration_minutes=100, location=f"实训楼 {201 + course_index} 机房" if lab else location,
                   title=f"第 {lesson} 周 · {topic}{'上机实践' if lab else '专题讲授'}",
                   completed=date + timedelta(minutes=100) < AS_OF and lesson <= 4 + course_index % 2,
                   created_at=TERM_START - timedelta(days=7))

        members = [primary_student] + [student for number, student in enumerate(students, 1)
                                      if number == 1 or (number + course_index) % 4 != 0]
        active_members = []
        for student in members:
            membership = session.scalar(select(CourseEnrollment).where(
                CourseEnrollment.course_id == course.id, CourseEnrollment.user_id == student.id))
            if membership is None:
                membership = insert(CourseEnrollment, f"{code}:{student.id}", course_id=course.id,
                                    user_id=student.id, status="active", joined_at=TERM_START - timedelta(days=6))
            if membership.status == "active":
                active_members.append(student)

        notices = (
            ("课程安排与考核说明", f"本学期共 16 周，每周周{'一二三四五'[weekday]} {hour:02}:00 上课，常规教室为{location}。上机课地点请查看课次详情。请提前阅读课程大纲，平时作业与实验过程都计入课程评价。", 30),
            (f"第一章练习：{topics[0][0]}", f"第一章练习已布置，请独立完成选择、判断、填空与案例题。案例分析需写出推理过程，不要只填写结论。完成后可在错题本回顾{topics[0][0]}的易错点。", 23),
            ("上机课准备事项", "上机前请检查个人账号和开发环境。实验报告应包含任务目标、关键操作、运行结果以及遇到的问题。请勿在报告截图中展示密码或服务密钥。", 18),
            (f"第二章作业：{topics[1][0]}", f"第二章作业截止时间为 10 月 15 日 23:59。重点复习{topics[1][0]}，简答题请结合题目给定的条件说明步骤。已提交同学可在批改后查看评语。", 8),
            ("本周答疑时间安排", f"10 月 12 日 17:00—18:00 在{location}集中答疑。建议提前整理最近两次作业中的疑问，并附上已尝试的方法，便于讨论。", 2),
            ("第六周预习与课堂练习", f"下周进入{topics[1][0]}专题的进一步讨论。请先阅读章节大纲，尝试回答：{topics[1][3]}。课堂将重点比较不同思路。", 1),
            ("阶段复习与作业反馈", "请核对已提交作业的批改状态。需要补交的同学先提交申请，获批后在新的期限内完成。下一阶段练习已发布，请合理安排时间。", 0),
            ("期中综合任务准备", f"期中任务将围绕{topics[0][0]}与{topics[2][0]}展开。请保留学习过程与代码版本，后续任务要求将在正式发布时说明；当前无需提前提交。", 0),
        )
        for number, (notice_title, content, days_ago) in enumerate(notices, 1):
            insert(CourseAnnouncement, f"{code}:{number}", course_id=course.id, author_id=course.owner_id,
                   title=notice_title, content=content,
                   published_at=AS_OF - timedelta(days=days_ago, minutes=10 + course_index * 8 + number))

        assignment_specs = (
            (f"第一章巩固 · {topics[0][0]}", "closed", datetime(2026, 9, 24, 23, 59, tzinfo=ZONE), TERM_START + timedelta(days=7), 0),
            (f"第二章案例分析 · {topics[1][0]}", "published", datetime(2026, 10, 15, 23, 59, tzinfo=ZONE), datetime(2026, 10, 1, 9, tzinfo=ZONE), 1),
            (f"第三章课堂练习 · {topics[2][0]}", "published", datetime(2026, 10, 22, 23, 59, tzinfo=ZONE), AS_OF - timedelta(hours=3), 2),
            (f"专题练习 · {topics[3][0]}", "published", datetime(2026, 10, 8, 23, 59, tzinfo=ZONE), datetime(2026, 9, 28, 9, tzinfo=ZONE), 3),
            ("期中综合任务", "draft", datetime(2026, 11, 2, 23, 59, tzinfo=ZONE), AS_OF - timedelta(hours=1), 0),
        )
        assignments = []
        for number, (assignment_title, status, due_at, created_at, group_index) in enumerate(assignment_specs, 1):
            assignment = insert(Assignment, f"{code}:{number}", course_id=course.id, class_id=None,
                                creator_id=course.owner_id, title=assignment_title,
                                description=f"本次作业覆盖{topics[group_index][0]}，共 4 题，每题 25 分。请独立完成；简答题应给出分析过程，涉及代码时说明关键步骤和边界条件。提交前检查是否遗漏答案。",
                                status=status, due_at=due_at, created_at=created_at)
            assignments.append(assignment)
            for position, question in enumerate(question_groups[group_index], 1):
                insert(AssignmentQuestion, f"{code}:{number}:{position}",
                       unique=(AssignmentQuestion.assignment_id == assignment.id) & (
                           (AssignmentQuestion.question_id == question.id) | (AssignmentQuestion.position == position)),
                       assignment_id=assignment.id, question_id=question.id, position=position, points=25.0)

        for student in active_members:
            number = 0 if student.id == primary_student.id else students.index(student) + 1
            for task_index in range(2):
                if number not in (0, 1) and number % (5 if task_index == 0 else 3) == 0:
                    continue
                assignment = assignments[task_index]
                group = question_groups[task_index]
                answers, incorrect = {}, []
                for q_index, question in enumerate(group[:3]):
                    correct = not ((number + course_index + q_index) % 7 == 0)
                    answer = question.correct_answer
                    if not correct:
                        answer = (next(letter for letter in "ABCD" if letter != answer)
                                  if question.question_type == "single_choice" else
                                  "错误" if answer == "正确" else "正确" if question.question_type == "true_false" else "尚未确定")
                        incorrect.append(question)
                    answers[str(question.id)] = answer
                complete_short_answer = number % 3 == 0
                answers[str(group[3].id)] = group[3].correct_answer if complete_short_answer else topics[task_index][1] + "\n需要结合具体条件逐步分析。"
                objective_score = 75.0 - len(incorrect) * 25.0
                graded = task_index == 0 or (number > 1 and number % 4 == 0)
                short_score = 25 if complete_short_answer else 12 + (number * 3 + course_index * 2) % 12
                score = objective_score + short_score if graded else objective_score
                submitted_at = (datetime(2026, 9, 22, 18, tzinfo=ZONE) if task_index == 0
                                else datetime(2026, 10, 7, 18, tzinfo=ZONE)) + timedelta(minutes=number)
                submission = insert(AssignmentSubmission, f"{code}:{task_index}:{student.id}",
                                    unique=(AssignmentSubmission.assignment_id == assignment.id) & (AssignmentSubmission.student_id == student.id),
                                    assignment_id=assignment.id, student_id=student.id, answers=answers,
                                    score=score, max_score=100.0, status="graded" if graded else "pending_review",
                                    submitted_at=submitted_at)
                if graded:
                    feedback = ("客观题完成较好。" if not incorrect else f"请订正{topics[task_index][0]}相关的客观题，注意适用条件。")
                    feedback += "案例分析步骤完整，结论清晰。" if complete_short_answer else "案例题需要补充具体步骤与条件分析，不能只复述定义。"
                    insert(SubmissionReview, f"{code}:{task_index}:{student.id}",
                           unique=SubmissionReview.submission_id == submission.id, submission_id=submission.id,
                           teacher_id=course.owner_id, score=score, feedback=feedback,
                           graded_at=submitted_at + timedelta(days=1, hours=2))
                for question in incorrect:
                    wrong_answer = answers[str(question.id)]
                    mastered = number > 1 and number % 5 == 0
                    practiced_at = submitted_at + timedelta(days=2)
                    wrong = insert(WrongQuestion, f"{code}:{question.id}:{student.id}",
                                   unique=(WrongQuestion.student_id == student.id) & (WrongQuestion.question_id == question.id),
                                   student_id=student.id, question_id=question.id, wrong_count=2,
                                   retry_count=3 if mastered else 1, correct_streak=2 if mastered else 0,
                                   mastered=mastered, last_answer=question.correct_answer if mastered else wrong_answer,
                                   last_practiced_at=practiced_at + timedelta(hours=2) if mastered else practiced_at,
                                   updated_at=practiced_at + timedelta(hours=2) if mastered else practiced_at)
                    insert(PracticeAttempt, f"{code}:{wrong.id}:first", student_id=student.id,
                           question_id=question.id, answer=wrong_answer, is_correct=False, source="wrong_retry", attempted_at=practiced_at)
                    if mastered:
                        for retry in (1, 2):
                            insert(PracticeAttempt, f"{code}:{wrong.id}:retry:{retry}", student_id=student.id,
                                   question_id=question.id, answer=question.correct_answer, is_correct=True,
                                   source="wrong_retry", attempted_at=practiced_at + timedelta(hours=retry))

            if number % 7 == 0:
                decision = ("pending", "approved", "rejected")[(number + course_index) % 3]
                insert(LateSubmissionRequest, f"{code}:{student.id}",
                       unique=(LateSubmissionRequest.assignment_id == assignments[3].id) & (LateSubmissionRequest.student_id == student.id),
                       assignment_id=assignments[3].id, student_id=student.id,
                       reason="整理实验结果后发现遗漏了提交步骤，希望申请补交，已完成的分析和运行记录可以一并提交。",
                       status=decision, reviewer_id=course.owner_id if decision != "pending" else None,
                       review_note="同意补交，请核对全部题目后于新期限内提交。" if decision == "approved" else
                                   "请先补充完整的作业分析和申请说明后重新申请。" if decision == "rejected" else None,
                       requested_at=datetime(2026, 10, 9, 19, tzinfo=ZONE),
                       reviewed_at=AS_OF - timedelta(hours=2) if decision != "pending" else None,
                       approved_until=datetime(2026, 10, 14, 23, 59, tzinfo=ZONE) if decision == "approved" else None)

            # Populate historical summary rows from the inserted activity, not arbitrary percentages.
            submitted = {item.assignment_id: item for item in session.scalars(select(AssignmentSubmission).where(
                AssignmentSubmission.student_id == student.id,
                AssignmentSubmission.assignment_id.in_([item.id for item in assignments]),
            )).all()}
            final_scores = [item.score for item in submitted.values() if item.status == "graded"]
            for position, section in enumerate(sections):
                target = assignments[position]
                insert(LearningProgress, f"{code}:{section.id}:{student.id}",
                       unique=(LearningProgress.student_id == student.id) & (LearningProgress.section_id == section.id),
                       student_id=student.id, course_id=course.id, section_id=section.id,
                       progress_percent=100.0 if target.id in submitted else 0.0,
                       mastery_percent=round(sum(final_scores) / len(final_scores), 1) if final_scores else 0.0,
                       last_active_at=AS_OF - timedelta(hours=4))
            if number in (0, 1):
                insert(StudyPlan, f"{code}:{student.id}", student_id=student.id, course_id=course.id,
                       created_at=AS_OF - timedelta(minutes=5), items=[
                           {"id": str(fixture_id("plan_item", f"{code}:{student.id}:assignment")), "kind": "assignment",
                            "target_id": str(assignments[2].id), "title": assignments[2].title,
                            "detail": "10 月 22 日前完成第三章练习，简答题写出关键步骤。", "due_at": assignments[2].due_at.isoformat()},
                           {"id": str(fixture_id("plan_item", f"{code}:{student.id}:wrong")), "kind": "wrong_review",
                            "target_id": None, "title": "回顾本课程错题", "detail": "先辨析错误原因，再尝试独立作答。", "due_at": None},
                           {"id": str(fixture_id("plan_item", f"{code}:{student.id}:preview")), "kind": "section_preview",
                            "target_id": str(sections[1].id), "title": f"预习：{sections[1].title}",
                            "detail": "阅读章节大纲，整理准备在课堂提问的问题。", "due_at": None},
                       ])

    if added:
        session.add(AuditLog(actor_id=admin.id, actor_name="内测数据导入", action="create",
                             resource_type="demo_dataset", resource_id="realistic-autumn-2026-v1",
                             detail={"synthetic": True, "purpose": "private_test", "insert_only": True,
                                     "as_of": AS_OF.isoformat(), "added": dict(added),
                                     "note": "姓名、授课、作答和评分均为虚构场景，不代表真实人员或教学活动。"}))
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="添加自然呈现的虚构学期内测数据；不覆盖现有记录。请先备份。")
    parser.add_argument("--apply", action="store_true")
    if not parser.parse_args().apply:
        print("计划添加 40 名学生、4 名教师、8 门课程及课次/公告/题库/作业/提交/批改/错题/补交申请。")
        print("未写入。请先备份开发库，再使用 --apply；不得当作真实人员或教学记录。")
        return
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://rag:rag@127.0.0.1:5432/rag")
    sessions = get_session_factory()
    with sessions.begin() as session:
        added = seed(session)
    models = (User, Course, CourseSection, CourseSession, CourseAnnouncement, QuestionBankItem, Assignment,
              AssignmentSubmission, SubmissionReview, WrongQuestion, PracticeAttempt, LateSubmissionRequest,
              CourseEnrollment, KnowledgePoint, LearningProgress, StudyPlan)
    with sessions() as session:
        totals = {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in models}
    print(json.dumps({"added": dict(added), "database_totals": totals, "synthetic": True,
                      "existing_records_unchanged": True, "snapshot_date": "2026-10-10"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
