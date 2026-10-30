"""Create an idempotent, presentation-ready dataset for all current workbenches."""
from __future__ import annotations

import os
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import select

from app.auth import hash_password
from app.database import get_session_factory
from app.demo_schedule import DEMO_DURATION_MINUTES, DEMO_SLOTS, current_demo_semester, demo_session_dates
from app.models import (
    Assignment, AssignmentQuestion, AssignmentSubmission, AuditLog, CourseAnnouncement,
    ClassEnrollment, Course, CourseClass, CourseEnrollment, CourseKnowledgeBase, CourseSection, CourseSession, Document,
    EvaluationRun, KnowledgeBase, KnowledgePoint, LateSubmissionRequest, LearningProgress,
    PracticeAttempt, QuestionBankItem, QuestionRecord, QuestionReview, SubmissionReview,
    TutorConversation, User, WrongQuestion,
)


def one(session, model, **filters):
    return session.scalar(select(model).filter_by(**filters))


def ensure(session, model, defaults=None, **filters):
    item = one(session, model, **filters)
    if item is None:
        item = model(**filters, **(defaults or {}))
        session.add(item)
        session.flush()
    return item


def main() -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://rag:rag@127.0.0.1:5432/rag")
    session_factory = get_session_factory()
    now = datetime.now(timezone.utc)
    demo_semester = current_demo_semester(now)
    with session_factory() as session:
        admin = one(session, User, username="admin")
        teacher = one(session, User, username="teacher")
        student = one(session, User, username="student")
        if not all((admin, teacher, student)):
            raise RuntimeError("请先启动平台，让系统创建默认三角色账号。")

        for username, display_name in (("student02", "李明"), ("student03", "王小雨"), ("student04", "陈浩")):
            ensure(session, User, username=username, defaults={
                "display_name": display_name, "role": "student",
                "password_hash": hash_password("student123"), "active": True,
            })
        students = [student] + [one(session, User, username=name) for name in ("student02", "student03", "student04")]

        course_specs = (
            ("DSA-2026", "数据结构与算法", demo_semester, "周一 08:00-09:40", "博学楼 A203", "线性结构、树、图、查找、排序与算法设计。", ("课程概论", "线性表与栈队列", "树与二叉树", "图与算法")),
            ("OS-2026", "操作系统原理", demo_semester, "周三 10:00-11:40", "计算机楼 302", "进程、内存、文件系统与并发控制。", ("操作系统概论", "进程与线程", "内存管理", "文件系统")),
            ("NET-2026", "计算机网络", demo_semester, "周五 14:00-15:40", "实验楼 B406", "从分层体系结构到 TCP/IP 与网络安全。", ("网络体系结构", "数据链路层", "网络层", "传输层")),
        )
        courses = []
        for code, title, semester, schedule, location, description, sections in course_specs:
            course = ensure(session, Course, code=code, defaults={
                "title": title, "semester": semester, "schedule": schedule, "location": location, "description": description,
                "status": "published", "owner_id": teacher.id,
            })
            course.title, course.semester, course.schedule, course.location = title, semester, schedule, location
            course.description, course.status = description, "published"
            course.owner_id = teacher.id
            for position, section_title in enumerate(sections, 1):
                ensure(session, CourseSection, course_id=course.id, position=position, defaults={
                    "title": section_title, "description": f"{section_title}的核心概念、例题和练习。",
                })
            courses.append(course)

        for course in courses:
            sections = list(session.scalars(select(CourseSection).where(CourseSection.course_id == course.id).order_by(CourseSection.position)).all())
            session_total, completed_total = DEMO_SLOTS[course.code][3:]
            scheduled_dates = demo_session_dates(now, course.code)
            for index in range(session_total):
                section = sections[min(index * len(sections) // session_total, len(sections) - 1)]
                title = f"第 {index + 1} 次课：{section.title}"
                item = ensure(session, CourseSession, course_id=course.id, title=title, defaults={
                    "section_id": section.id,
                    "session_date": scheduled_dates[index],
                    "duration_minutes": DEMO_DURATION_MINUTES,
                    "location": course.location,
                    "completed": index < completed_total,
                })
                item.section_id, item.duration_minutes, item.location = section.id, DEMO_DURATION_MINUTES, course.location
                item.completed = index < completed_total

        class_specs = (
            (courses[0], "数据结构 1 班", "DSA1A"),
            (courses[1], "操作系统 1 班", "OS1A"),
            (courses[2], "计算机网络实验班", "NETLAB"),
        )
        classes = []
        for course, name, invite_code in class_specs:
            course_class = ensure(session, CourseClass, invite_code=invite_code, defaults={
                "course_id": course.id, "teacher_id": teacher.id, "name": name, "status": "active",
            })
            for learner in students:
                ensure(session, ClassEnrollment, class_id=course_class.id, user_id=learner.id, defaults={"status": "active"})
                ensure(session, CourseEnrollment, course_id=course.id, user_id=learner.id, defaults={"status": "active"})
            classes.append(course_class)

        announcements = (
            (courses[0], "本周学习安排", "请完成二叉树遍历章节，并在周五前提交配套作业。"),
            (courses[0], "答疑时间", "周三 19:00 开放线上答疑，可提前在 AI 课程导师中整理问题。"),
            (courses[1], "实验提醒", "进程调度实验需要提交运行截图和结果分析。"),
            (courses[2], "课程资料已更新", "本课程已关联开放教材，可在课程详情的对应资料中查看。"),
        )
        for course, title, content in announcements:
            ensure(session, CourseAnnouncement, course_id=course.id, title=title, defaults={
                "author_id": teacher.id, "content": content,
            })

        registry_path = Path(__file__).resolve().parents[1] / "materials" / "sources.json"
        source_records = json.loads(registry_path.read_text(encoding="utf-8"))["sources"]
        registered_sources = {source["title"]: source for source in source_records}
        knowledge_bases = list(session.scalars(select(KnowledgeBase).order_by(KnowledgeBase.created_at)).all())
        for course in courses:
            for base in knowledge_bases:
                base_documents = list(session.scalars(select(Document).where(Document.knowledge_base_id == base.id)).all())
                # Demo data must not attach a data-structures library to unrelated courses.
                if course.code == "DSA-2026" and base_documents and all(
                    (
                        document.filename in registered_sources
                        and registered_sources[document.filename].get("course_code", "DSA-2026") == "DSA-2026"
                    ) or document.filename.startswith("教师精选问答：")
                    for document in base_documents
                ):
                    ensure(session, CourseKnowledgeBase, course_id=course.id, knowledge_base_id=base.id)
        for document in session.scalars(select(Document)).all():
            source = registered_sources.get(document.filename)
            if source:
                document.source_url = source["document_url"]
                document.license_name = source["license"]
                document.license_url = source["license_url"]
            elif document.filename.startswith("教师精选问答："):
                document.source_url = None
                document.license_name = "系统生成教学内容"
                document.license_url = None
            document.version_label = document.version_label or "1.0"

        points_by_course = {
            "DSA-2026": ("栈与队列", "二叉树遍历", "图的最短路径", "动态规划"),
            "OS-2026": ("进程状态", "信号量", "虚拟内存", "页面置换"),
            "NET-2026": ("OSI 分层", "IP 路由", "TCP 可靠传输", "拥塞控制"),
        }
        for course in courses:
            sections = list(session.scalars(select(CourseSection).where(CourseSection.course_id == course.id).order_by(CourseSection.position)).all())
            for index, point in enumerate(points_by_course[course.code]):
                ensure(session, KnowledgePoint, course_id=course.id, name=point, defaults={
                    "section_id": sections[min(index, len(sections) - 1)].id,
                    "description": f"掌握{point}的定义、工作过程、典型应用和常见误区。",
                })
            for learner_index, learner in enumerate(students):
                for section_index, section in enumerate(sections):
                    progress = min(100.0, 35.0 + learner_index * 12 + section_index * 16)
                    mastery = min(96.0, progress - 8 + learner_index * 3)
                    record = ensure(session, LearningProgress, student_id=learner.id, section_id=section.id, defaults={
                        "course_id": course.id, "progress_percent": progress, "mastery_percent": mastery,
                    })
                    record.progress_percent, record.mastery_percent = progress, mastery

        question_specs = {
            "DSA-2026": (
                ("single_choice", "栈最典型的访问顺序是什么？", ["先进先出", "后进先出", "随机访问", "按优先级"], "后进先出", "栈只允许在栈顶插入和删除。", "栈与队列", 1),
                ("true_false", "二叉树的每个结点最多有两个孩子。", ["正确", "错误"], "正确", "这是二叉树的基本定义。", "二叉树遍历", 1),
                ("short_answer", "请说明动态规划的两个关键性质。", [], "最优子结构和重叠子问题", "通常从最优子结构与重叠子问题判断能否使用动态规划。", "动态规划", 3),
                ("multiple_choice", "下列哪些数据结构遵循受限位置访问？", ["栈", "队列", "数组", "散列表"], "栈,队列", "栈和队列分别限制在端点进行插入或删除。", "栈与队列", 2),
                ("fill_blank", "二叉树的前序遍历顺序是____、____、____。", [], "根结点/根||左子树||右子树", "前序遍历先访问根，再访问左子树和右子树。", "二叉树遍历", 2),
            ),
            "OS-2026": (
                ("single_choice", "下列哪项属于进程的基本状态？", ["运行态", "编译态", "链接态", "安装态"], "运行态", "进程常见状态包括就绪、运行和阻塞。", "进程状态", 1),
                ("true_false", "信号量可以用于进程同步和互斥。", ["正确", "错误"], "正确", "P/V 操作可协调并发进程。", "信号量", 2),
                ("short_answer", "什么是缺页中断？", [], "访问的页面不在内存时由硬件触发的中断", "操作系统需将目标页面调入内存后恢复执行。", "虚拟内存", 3),
                ("multiple_choice", "下列哪些属于进程同步工具？", ["信号量", "互斥锁", "页表", "文件描述符"], "信号量,互斥锁", "信号量和互斥锁都可协调并发执行。", "信号量", 2),
                ("fill_blank", "虚拟地址经过____转换为物理地址。", [], "页表/MMU", "页表由内存管理单元参与完成地址映射。", "虚拟内存", 2),
            ),
            "NET-2026": (
                ("single_choice", "TCP 属于哪一层协议？", ["应用层", "传输层", "网络层", "数据链路层"], "传输层", "TCP 在传输层提供可靠的端到端服务。", "TCP 可靠传输", 1),
                ("true_false", "IP 协议本身保证分组可靠到达。", ["正确", "错误"], "错误", "IP 提供尽力而为的无连接服务。", "IP 路由", 2),
                ("short_answer", "TCP 如何实现可靠传输？", [], "序号、确认、超时重传和流量控制", "TCP 综合使用序号、确认、校验、重传与窗口机制。", "TCP 可靠传输", 3),
                ("multiple_choice", "下列哪些机制用于 TCP 可靠传输？", ["序号", "确认", "超时重传", "ARP 广播"], "序号,确认,超时重传", "序号、确认与重传是 TCP 可靠性的核心机制。", "TCP 可靠传输", 2),
                ("fill_blank", "TCP/IP 模型中，TCP 位于____层，IP 位于____层。", [], "传输||网络/网际", "TCP 提供端到端传输，IP 负责跨网络寻址与转发。", "OSI 分层", 2),
            ),
        }
        questions_by_course = {}
        for course in courses:
            sections = list(session.scalars(select(CourseSection).where(CourseSection.course_id == course.id).order_by(CourseSection.position)).all())
            items = []
            for index, (kind, stem, options, answer, explanation, point, difficulty) in enumerate(question_specs[course.code]):
                item = ensure(session, QuestionBankItem, course_id=course.id, stem=stem, defaults={
                    "section_id": sections[min(index + 1, len(sections) - 1)].id,
                    "creator_id": teacher.id, "question_type": kind, "options": options,
                    "correct_answer": answer, "explanation": explanation,
                    "knowledge_point": point, "difficulty": difficulty,
                })
                items.append(item)
            questions_by_course[course.code] = items

        assignment_specs = (
            (classes[0], "演示：树与算法阶段练习", "完成后系统自动批改客观题，简答题由教师复核。", now + timedelta(days=5), "published"),
            (classes[1], "演示：进程与内存综合作业", "覆盖进程同步和虚拟内存。", now + timedelta(days=8), "published"),
            (classes[2], "演示：TCP/IP 单元测验", "检验网络层与传输层核心概念。", now - timedelta(days=2), "closed"),
        )
        assignments = []
        for course_class, title, description, due_at, status in assignment_specs:
            assignment = ensure(session, Assignment, class_id=course_class.id, title=title, defaults={
                "creator_id": teacher.id, "description": description, "due_at": due_at, "status": status,
            })
            assignment.status, assignment.due_at = status, due_at
            course = next(item for item in courses if item.id == course_class.course_id)
            for position, question_item in enumerate(questions_by_course[course.code], 1):
                ensure(session, AssignmentQuestion, assignment_id=assignment.id, question_id=question_item.id, defaults={
                    "position": position, "points": 10.0,
                })
            assignments.append(assignment)

        score_matrix = ((26, "graded"), (20, "submitted"), (29, "graded"), (16, "submitted"))
        for assignment_index, assignment in enumerate(assignments):
            linked = list(session.scalars(select(AssignmentQuestion).where(AssignmentQuestion.assignment_id == assignment.id).order_by(AssignmentQuestion.position)).all())
            questions = [session.get(QuestionBankItem, link.question_id) for link in linked]
            for learner_index, learner in enumerate(students):
                if assignment_index == 0 and learner.id == student.id:
                    continue  # 默认学生保留一份待完成作业，便于测试提交。
                score, submission_status = score_matrix[learner_index]
                answers = {str(item.id): item.correct_answer if learner_index != 3 else "错误示例" for item in questions}
                submission = ensure(session, AssignmentSubmission, assignment_id=assignment.id, student_id=learner.id, defaults={
                    "answers": answers, "score": float(score), "max_score": 30.0, "status": submission_status,
                })
                if submission_status == "graded":
                    ensure(session, SubmissionReview, submission_id=submission.id, defaults={
                        "teacher_id": teacher.id, "score": float(score),
                        "feedback": "概念掌握较好，请继续注意答题过程的完整性。",
                    })

        first_questions = questions_by_course["DSA-2026"]
        for index, item in enumerate(first_questions):
            wrong = ensure(session, WrongQuestion, student_id=student.id, question_id=item.id, defaults={
                "wrong_count": index + 1, "retry_count": index, "correct_streak": 0,
                "last_answer": "演示错误答案", "mastered": index == 2,
                "last_practiced_at": now - timedelta(days=index),
            })
            ensure(session, PracticeAttempt, student_id=student.id, question_id=item.id, answer="演示错误答案", defaults={
                "is_correct": False, "source": "adaptive",
            })

        late_assignment = assignments[2]
        ensure(session, LateSubmissionRequest, assignment_id=late_assignment.id, student_id=student.id, defaults={
            "reason": "因课程实验环境故障，希望延迟一天提交。", "status": "pending",
        })

        kb_id = knowledge_bases[0].id if knowledge_bases else None
        conversation = ensure(session, TutorConversation, user_id=student.id, title="演示：二叉树遍历答疑", defaults={
            "knowledge_base_id": kb_id,
        })
        record1 = ensure(session, QuestionRecord, conversation_id=conversation.id, user_id=student.id, question="前序、中序和后序遍历有什么区别？", defaults={
            "knowledge_base_id": kb_id, "answer":"三种遍历的区别在于访问根结点的时机：前序先访问根，中序在左子树之后访问根，后序最后访问根。",
            "message":"已根据课程资料回答。", "model":"qwen-plus", "accepted":True,
            "citations":[], "rating":5, "favorite":True,
        })
        record2 = ensure(session, QuestionRecord, conversation_id=conversation.id, user_id=student.id, question="能举一个具体例子吗？", defaults={
            "knowledge_base_id": kb_id, "answer":"例如根结点 A，左孩子 B，右孩子 C：前序为 A-B-C，中序为 B-A-C，后序为 B-C-A。",
            "message":"已结合前文继续回答。", "model":"qwen-plus", "accepted":True,
            "citations":[], "rating":None, "favorite":False,
        })
        approved = ensure(session, QuestionReview, question_record_id=record1.id, defaults={
            "reviewer_id": teacher.id, "status":"approved", "revised_answer":record1.answer,
            "review_note":"回答准确，可作为课程答疑示例。",
        })
        del approved, record2
        ensure(session, QuestionRecord, user_id=student.id, question="演示：为什么动态规划要保存子问题结果？", defaults={
            "knowledge_base_id": kb_id, "answer":"保存子问题结果可以避免重复计算，从而显著降低时间复杂度。",
            "message":"等待教师审核。", "model":"qwen-plus", "accepted":True, "citations":[], "favorite":False,
        })

        ensure(session, EvaluationRun, dataset_version="demo-v2.0", defaults={
            "name":"演示：课程 RAG 综合评测", "case_count":150,
            "metrics":{"recall_at_5":0.91,"mrr":0.89,"citation_accuracy":0.95,"refusal_accuracy":1.0,"latency_p50_ms":42,"latency_p95_ms":148,"throughput_qps":91},
            "details":[], "created_by":"系统管理员",
        })
        for action, resource_type, detail in (
            ("seed", "demo_data", {"scope":"all_modules"}),
            ("publish", "course", {"code":"DSA-2026"}),
            ("review", "question_answer", {"status":"approved"}),
        ):
            if not session.scalar(select(AuditLog).where(AuditLog.action == action, AuditLog.resource_type == resource_type, AuditLog.actor_name == "演示数据生成器")):
                session.add(AuditLog(actor_id=admin.id, actor_name="演示数据生成器", action=action, resource_type=resource_type, detail=detail))

        session.commit()
        print("Demo data ready: 3 courses, 3 classes, 4 students, announcements, resources, questions, assignments, learning analytics, tutor history and admin data.")


if __name__ == "__main__":
    main()
