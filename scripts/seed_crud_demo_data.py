"""Add, without rewriting existing records, clearly marked data for CRUD/paging demos."""

from __future__ import annotations

import os
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select

from app.database import get_session_factory
from app.models import Course, CourseAnnouncement, CourseSection, QuestionBankItem


QUESTIONS = {
    "DSA-2026": [
        ("栈遵循后进先出原则。", "正确", "栈", "栈的最后一个入栈元素会最先出栈。"),
        ("队列遵循后进先出原则。", "错误", "队列", "普通队列遵循先进先出原则。"),
        ("二分查找可以直接用于任意无序数组。", "错误", "查找", "二分查找要求待查序列有序。"),
        ("单链表在已知目标结点前驱时可在常数时间插入。", "正确", "链表", "修改前驱和新结点的指针即可。"),
        ("空二叉树的结点数为零。", "正确", "二叉树", "空树没有结点。"),
        ("广度优先搜索通常使用队列保存待访问结点。", "正确", "图搜索", "队列按层次推进搜索。"),
        ("深度优先搜索不能用递归实现。", "错误", "图搜索", "递归调用栈是常见的深度优先搜索实现。"),
        ("快速排序在所有输入上都保证 O(n log n) 时间复杂度。", "错误", "排序", "快速排序最坏情况下可达 O(n²)。"),
        ("归并排序的典型时间复杂度是 O(n log n)。", "正确", "排序", "各层合并总工作量为 O(n)，层数为 O(log n)。"),
        ("哈希冲突意味着两个不同键落在同一存储位置。", "正确", "散列表", "不同键计算到同一位置即发生冲突。"),
        ("邻接矩阵适合表示稠密图。", "正确", "图存储", "稠密图的边数接近顶点数平方，矩阵表示直观。"),
        ("遍历长度为 n 的数组至少需要访问其中 n 个元素。", "正确", "复杂度", "完整遍历会依次访问全部 n 个元素。"),
    ],
    "OS-2026": [
        ("进程是资源分配的基本单位之一。", "正确", "进程", "现代操作系统通常以进程组织资源。"),
        ("同一进程内的线程通常共享进程地址空间。", "正确", "线程", "线程共享代码段和堆等进程资源。"),
        ("死锁只可能由一个进程单独产生。", "错误", "死锁", "死锁通常涉及多个执行实体相互等待资源。"),
        ("互斥锁可用于保护共享临界区。", "正确", "同步", "同一时刻只允许一个持锁者进入临界区。"),
        ("时间片轮转调度会在时间片用完后重新排队。", "正确", "调度", "轮转调度通过时间片实现轮流占用处理器。"),
        ("分页管理要求进程占用一整块连续物理内存。", "错误", "内存管理", "分页允许页面映射到不连续的物理页框。"),
        ("缺页中断表示所访问的页当前不在内存中。", "正确", "虚拟内存", "系统需将目标页面调入内存。"),
        ("虚拟内存可让进程使用大于物理内存的逻辑地址空间。", "正确", "虚拟内存", "部分页面可暂存在外存中。"),
        ("文件描述符是进程访问打开文件的一种引用。", "正确", "文件系统", "操作系统通过文件描述符表管理已打开文件。"),
        ("系统调用为用户程序提供进入内核服务的入口。", "正确", "系统调用", "用户态程序通过系统调用请求受保护服务。"),
        ("上下文切换不需要保存任何处理器状态。", "错误", "进程切换", "切换通常需要保存和恢复寄存器等上下文。"),
        ("信号量可以用于线程或进程间同步。", "正确", "同步", "信号量的等待与通知操作可协调并发执行。"),
    ],
    "NET-2026": [
        ("IP 地址用于网络层的逻辑寻址。", "正确", "网络层", "IP 地址标识网络接口的逻辑位置。"),
        ("MAC 地址主要用于数据链路层寻址。", "正确", "数据链路层", "以太网帧使用 MAC 地址标识本地链路上的接口。"),
        ("TCP 是无连接的传输层协议。", "错误", "TCP", "TCP 通过连接建立、维护和释放提供可靠传输。"),
        ("UDP 自身不保证数据报一定到达。", "正确", "UDP", "UDP 不提供 TCP 式的确认重传机制。"),
        ("DNS 的主要作用之一是将域名解析为 IP 地址。", "正确", "DNS", "DNS 提供域名到地址等资源记录的解析。"),
        ("HTTP 状态码 404 常用于表示资源未找到。", "正确", "HTTP", "404 表示服务器未找到目标资源。"),
        ("路由器通常依据目标 IP 地址转发网络层数据包。", "正确", "路由", "路由表的匹配依据是目标网络前缀。"),
        ("子网掩码可用于区分 IP 地址的网络部分。", "正确", "子网", "掩码定义地址中对应网络前缀的比特。"),
        ("HTTPS 与 HTTP 的区别之一是使用 TLS 保护传输。", "正确", "HTTPS", "TLS 提供加密与身份验证能力。"),
        ("TCP 三次握手主要用于连接建立。", "正确", "TCP", "双方交换 SYN 和确认信息后建立连接。"),
        ("交换机转发以太网帧时完全不查看 MAC 地址。", "错误", "交换", "二层交换机会参考目的 MAC 地址和转发表。"),
        ("ping 常借助 ICMP 回显报文检查网络可达性。", "正确", "ICMP", "回显请求和应答是常见的连通性检查方式。"),
    ],
}


NOTICE_TOPICS = (
    "课程资料查阅", "章节练习入口", "题库筛选体验", "作业提交演练", "错题回顾入口", "课程问答体验",
)


def main() -> None:
    os.environ.setdefault("DATABASE_URL", "postgresql+psycopg://rag:rag@127.0.0.1:5432/rag")
    sessions = get_session_factory()
    added_questions = 0
    added_notices = 0
    with sessions.begin() as session:
        courses = {course.code: course for course in session.scalars(select(Course).where(Course.code.in_(QUESTIONS))).all()}
        missing = set(QUESTIONS) - set(courses)
        if missing:
            raise RuntimeError(f"缺少演示课程：{', '.join(sorted(missing))}。请先检查现有课程，未写入任何数据。")
        for code, specs in QUESTIONS.items():
            course = courses[code]
            sections = session.scalars(select(CourseSection).where(CourseSection.course_id == course.id)
                                       .order_by(CourseSection.position)).all()
            for index, (stem, answer, point, explanation) in enumerate(specs, 1):
                item_id = uuid5(NAMESPACE_URL, f"computer-course-rag:crud-demo:v1:{code}:question:{index}")
                if session.get(QuestionBankItem, item_id) is not None:
                    continue
                session.add(QuestionBankItem(
                    id=item_id, course_id=course.id, section_id=sections[(index - 1) % len(sections)].id if sections else None,
                    creator_id=course.owner_id, question_type="true_false", stem=f"[演示题] {stem}",
                    options=["正确", "错误"], correct_answer=answer, explanation=explanation,
                    difficulty=1 + (index % 3), knowledge_point=point,
                ))
                added_questions += 1
            for index, topic in enumerate(NOTICE_TOPICS, 1):
                item_id = uuid5(NAMESPACE_URL, f"computer-course-rag:crud-demo:v1:{code}:notice:{index}")
                if session.get(CourseAnnouncement, item_id) is not None:
                    continue
                session.add(CourseAnnouncement(
                    id=item_id, course_id=course.id, author_id=course.owner_id,
                    title=f"[演示公告] {topic} · {course.title}",
                    content=f"这是一条功能测试公告，不代表真实教学安排。请在「{course.title}」中体验{topic}，并尝试公告翻页、查看等操作。",
                ))
                added_notices += 1
    print(f"新增演示题目 {added_questions} 道，演示公告 {added_notices} 条；现有记录未修改。")


if __name__ == "__main__":
    main()
