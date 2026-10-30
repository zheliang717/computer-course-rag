"""Insert-only, repeatable business demo data; never seed textbooks or model logs.

Back up the development database first, then run:
    python -m scripts.seed_scale_demo_data --apply
Existing records, passwords, memberships and teacher edits are never refreshed.
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
    Assignment, AssignmentQuestion, AuditLog, Course, CourseAnnouncement,
    CourseEnrollment, CourseSection, CourseSession, KnowledgePoint,
    QuestionBankItem, User,
)


DEMO_PASSWORD = "demo123456"  # Public demo accounts only; not a production credential.
STUDENT_COUNT = 100
TEACHER_COUNT = 12
ZONE = timezone(timedelta(hours=8))

# Authored interaction fixtures, not imported or teacher-approved teaching material.
FACTS = {
    "dsa": (
        ("栈遵循后进先出原则。", "栈"),
        ("队列遵循先进先出原则。", "队列"),
        ("二分查找要求待查序列有序。", "二分查找"),
        ("广度优先搜索通常使用队列保存待访问结点。", "广度优先搜索"),
    ),
    "os": (
        ("进程是资源分配的基本单位之一。", "进程"),
        ("同一进程内的线程通常共享进程地址空间。", "线程"),
        ("缺页中断表示所访问的页当前不在内存中。", "缺页中断"),
        ("系统调用为用户程序提供进入内核服务的入口。", "系统调用"),
    ),
    "net": (
        ("IP 地址用于网络层的逻辑寻址。", "IP 地址"),
        ("MAC 地址主要用于数据链路层寻址。", "MAC 地址"),
        ("TCP 通过连接建立、维护和释放提供可靠传输。", "TCP"),
        ("DNS 提供域名到地址等资源记录的解析。", "DNS"),
    ),
    "python": (
        ("列表是 Python 中一种可变的序列类型。", "列表"),
        ("字典使用键值对组织数据。", "字典"),
        ("函数可将一段可重复使用的逻辑封装起来。", "函数"),
        ("异常可通过 try 和 except 进行捕获和处理。", "异常"),
    ),
    "sql": (
        ("主键用于唯一标识表中的一条记录。", "主键"),
        ("外键可用于建立表之间的引用关系。", "外键"),
        ("WHERE 子句用于筛选满足条件的记录。", "WHERE"),
        ("事务将一组数据库操作组织为一个逻辑工作单元。", "事务"),
    ),
    "web": (
        ("HTML 用于组织网页内容的结构。", "HTML"),
        ("CSS 用于描述网页的样式和布局。", "CSS"),
        ("JavaScript 可用于实现网页交互逻辑。", "JavaScript"),
        ("HTTP 是客户端与服务器交换消息的一种协议。", "HTTP"),
    ),
    "oop": (
        ("封装将数据与操作数据的方法组织在一起。", "封装"),
        ("继承允许一个类复用另一个类的部分结构与行为。", "继承"),
        ("多态允许统一接口具有不同的具体实现。", "多态"),
        ("对象通常具有自身的状态与行为。", "对象"),
    ),
    "engineering": (
        ("需求分析用于明确用户需要解决的问题。", "需求分析"),
        ("版本控制可记录和管理项目文件的变更。", "版本控制"),
        ("单元测试主要检查相对独立的代码单元。", "单元测试"),
        ("代码审查帮助发现代码中的问题并交流改进建议。", "代码审查"),
    ),
    "linux": (
        ("pwd 命令用于显示当前工作目录。", "pwd"),
        ("ls 命令用于列出目录中的内容。", "ls"),
        ("cd 命令用于切换当前工作目录。", "cd"),
        ("mkdir 命令用于创建目录。", "mkdir"),
    ),
}

COURSES = (
    ("数据结构基础", "dsa"), ("算法设计与复杂度", "dsa"),
    ("线性结构与树", "dsa"), ("图算法导论", "dsa"),
    ("查找与排序", "dsa"), ("算法实践", "dsa"),
    ("操作系统基础", "os"), ("进程线程与并发", "os"),
    ("内存与虚拟内存", "os"), ("文件系统与 I/O", "os"),
    ("系统调用与安全", "os"), ("操作系统实践", "os"),
    ("计算机网络基础", "net"), ("网络协议与分层", "net"),
    ("传输层协议", "net"), ("HTTP 与 Web 网络", "net"),
    ("DNS 与路由", "net"), ("网络实验", "net"),
    ("Python 程序设计", "python"), ("SQL 数据库基础", "sql"),
    ("Web 开发导论", "web"), ("面向对象程序设计", "oop"),
    ("软件工程导论", "engineering"), ("Linux 使用基础", "linux"),
)

NOTICES = (
    ("欢迎与课程导学", "先查看课程大纲，再选择一个基础知识点开始学习。"),
    ("本周课堂安排", "时间与地点请以课程详情中的演示课次为准。"),
    ("基础概念回顾", "打开题库按本课程筛选，完成一组基础练习。"),
    ("第一阶段作业", "进入题目与作业查看已发布作业，并在截止前提交。"),
    ("学习资料说明", "本课程为演示课程，题目和大纲不是教师审定教材；不要当作正式资料。"),
    ("AI 助手使用", "可请助手解释概念或推荐学习入口，未绑定资料时不要将解释当作教材引用。"),
    ("课程成员演示", "课程成员为虚构演示账号，不包含真实学生个人信息。"),
    ("课堂练习提示", "选择判断、选择、填空或简答题，体验不同作答方式。"),
    ("作业截止提醒", "已关闭的演示作业仅用于查看状态；仍可完成其他已发布作业。"),
    ("课程反馈入口", "可通过助手追问，并对回答是否有帮助给出反馈。"),
)


def demo_id(kind: str, key: str):
    return uuid5(NAMESPACE_URL, f"computer-course-rag:scale-demo:v1:{kind}:{key}")


def seed(session) -> Counter:
    added = Counter()
    now = datetime.now(ZONE)

    def insert(model, key: str, *, unique=None, **values):
        item_id = demo_id(model.__tablename__, key)
        existing = session.get(model, item_id)
        if existing is not None:
            return existing
        if unique is not None and session.scalar(select(model.id).where(unique)) is not None:
            raise RuntimeError(f"{model.__tablename__} 的唯一字段冲突（{key}）；整批回滚，不覆盖记录。")
        if model is User:
            values["password_hash"] = hash_password(DEMO_PASSWORD)
        item = model(id=item_id, **values)
        session.add(item)
        session.flush()  # Parent rows must exist before inserting related records.
        added[model.__tablename__] += 1
        return item

    primary_teacher = session.scalar(select(User).where(User.username == "teacher", User.role == "teacher"))
    primary_student = session.scalar(select(User).where(User.username == "student", User.role == "student"))
    admin = session.scalar(select(User).where(User.username == "admin", User.role == "admin"))
    if not primary_teacher or not primary_student or not admin:
        raise RuntimeError("缺少原有 teacher/student/admin 演示账号；未写入任何数据。")

    students = []
    for index in range(1, STUDENT_COUNT + 1):
        username = f"demo_student_{index:03}"
        students.append(insert(
            User, username, unique=User.username == username, username=username,
            display_name=f"演示学生 {index:03}", role="student", active=index <= 90,
        ))
    teachers = []
    for index in range(1, TEACHER_COUNT + 1):
        username = f"demo_teacher_{index:02}"
        teachers.append(insert(
            User, username, unique=User.username == username, username=username,
            display_name=f"演示教师 {index:02}", role="teacher", active=True,
        ))

    for index, (title, family) in enumerate(COURSES, 1):
        code = f"DEMO-SCALE-{index:03}"
        owner = primary_teacher if index <= 12 else teachers[index - 13]
        day = (index - 1) // 4
        hour = (8, 10, 14, 16)[(index - 1) % 4]
        location = f"演示教学楼 {100 + index} 室"
        course = insert(
            Course, code, unique=Course.code == code, code=code,
            title=f"[演示课程] {title}", owner_id=owner.id, status="published",
            semester="2026—2027 第一学期（演示）", location=location,
            schedule=f"周{'一二三四五六'[day]} {hour:02}:00—{hour + 1:02}:30（演示）",
            description=f"用于课程、成员、公告、练习和作业交互的虚构演示课程。内容覆盖{title}相关基础概念，不代表真实教学安排或正式教材。",
            created_at=now - timedelta(days=index),
        )
        facts = FACTS[family]
        sections = []
        for position, (statement, point) in enumerate(facts, 1):
            sections.append(insert(
                CourseSection, f"{code}:{position}",
                unique=(CourseSection.course_id == course.id) & (CourseSection.position == position),
                course_id=course.id, position=position, title=f"第 {position} 章 · {point}",
                description=f"[演示大纲]\n学习目标：理解{point}的基本含义。\n课堂导入：{statement}\n学习活动：概念辨析、示例讨论与章节作业。\n本大纲为交互演示内容，需教师另行审核后才能用于正式教学。",
            ))
            insert(
                KnowledgePoint, f"{code}:{position}",
                unique=(KnowledgePoint.course_id == course.id) & (KnowledgePoint.name == point),
                course_id=course.id, section_id=sections[-1].id, name=point,
                description=f"[演示知识点] {statement}",
            )

        # Only direct course membership; do not add or change legacy classes.
        members = [primary_student] + [students[((index - 1) * 4 + offset) % 90] for offset in range(30)]
        for student in members:
            existing_membership = session.scalar(select(CourseEnrollment).where(
                CourseEnrollment.course_id == course.id, CourseEnrollment.user_id == student.id,
            ))
            if existing_membership is None:
                insert(CourseEnrollment, f"{code}:{student.id}", course_id=course.id,
                       user_id=student.id, status="active", joined_at=now - timedelta(days=30))

        for number in range(1, 13):
            start = datetime(2026, 9, 7, hour, tzinfo=ZONE) + timedelta(days=day, weeks=number - 1)
            section = sections[(number - 1) // 3]
            insert(
                CourseSession, f"{code}:{number}", course_id=course.id, section_id=section.id,
                title=f"[演示课次] 第 {number} 次 · {section.title}", session_date=start,
                duration_minutes=90, location=location,
                completed=start < now and number <= 2 + index % 4,
            )

        questions = []
        for position, (statement, point) in enumerate(facts, 1):
            others = [fact[0] for fact in facts if fact[1] != point]
            specs = (
                ("true_false", f"判断：{statement}", ["正确", "错误"], "正确"),
                ("single_choice", f"下列哪项正确描述了「{point}」？",
                 [f"A. {statement}"] + [f"{letter}. {text}" for letter, text in zip("BCD", others)], "A"),
                ("fill_blank", f"填写空缺的术语：{statement.replace(point, '____', 1)}", [], point),
                ("short_answer", f"解释「{point}」的基本含义，并举一个简单例子。", [], statement),
            )
            for question_type, stem, options, answer in specs:
                questions.append(insert(
                    QuestionBankItem, f"{code}:{position}:{question_type}", course_id=course.id,
                    section_id=sections[position - 1].id, creator_id=course.owner_id,
                    question_type=question_type, stem=f"[演示题] {stem}", options=options,
                    correct_answer=answer, knowledge_point=point, difficulty=1 + (position % 3),
                    explanation=f"{statement}\n本题为功能演示题；简答题的示例与表达应由教师核对。",
                ))

        for number, (topic, content) in enumerate(NOTICES, 1):
            insert(
                CourseAnnouncement, f"{code}:{number}", course_id=course.id,
                author_id=course.owner_id, title=f"[演示公告] {topic} · {title}",
                content=f"【功能演示，非真实通知】\n{content}\n课程：{course.title}。",
                published_at=now - timedelta(days=10 - number, hours=index % 4),
            )

        for number in range(1, 4):
            status = ("published", "draft", "closed")[number - 1]
            due = now + timedelta(days=14) if number == 1 else now + timedelta(days=28) if number == 2 else now - timedelta(days=7)
            assignment = insert(
                Assignment, f"{code}:{number}", course_id=course.id, class_id=None,
                creator_id=course.owner_id, title=f"[演示作业] {title} · 第 {number} 组章节练习",
                description="功能演示作业，包含判断、选择、填空与简答题。简答题提交后由教师批改；不是正式课程成绩依据。",
                status=status, due_at=due, created_at=now - timedelta(days=number * 4),
            )
            for position, question in enumerate(questions[(number - 1) * 4:number * 4], 1):
                insert(
                    AssignmentQuestion, f"{code}:{number}:{position}",
                    unique=(AssignmentQuestion.assignment_id == assignment.id) & (
                        (AssignmentQuestion.question_id == question.id) | (AssignmentQuestion.position == position)),
                    assignment_id=assignment.id, question_id=question.id, position=position, points=25.0,
                )

    if added:
        session.add(AuditLog(
            actor_id=admin.id, actor_name=admin.display_name, action="create", resource_type="demo_dataset",
            resource_id="scale-demo-v1", detail={"demo_only": True, "insert_only": True, "added": dict(added)},
        ))
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description="仅添加大型演示数据，不覆盖现有记录；请先备份演示数据库。")
    parser.add_argument("--apply", action="store_true", help="明确确认向当前演示数据库写入数据")
    args = parser.parse_args()
    if not args.apply:
        print("计划新增：112 个账号、24 门课程、96 个章节/知识点、288 个课次、384 道题、240 条公告、72 份作业。")
        print("尚未写入。备份演示库后使用 --apply；不要在正式教学库运行。")
        return
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://rag:rag@127.0.0.1:5432/rag")
    sessions = get_session_factory()
    with sessions.begin() as session:
        added = seed(session)
    with sessions() as session:
        totals = {model.__tablename__: session.scalar(select(func.count()).select_from(model)) for model in (
            User, Course, CourseSection, CourseSession, CourseEnrollment, KnowledgePoint,
            QuestionBankItem, CourseAnnouncement, Assignment, AssignmentQuestion,
        )}
    print(json.dumps({"added": dict(added), "database_totals": totals, "existing_records_unchanged": True}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
