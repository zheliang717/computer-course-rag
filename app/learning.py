import secrets
from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.models import AuditLog, ClassAnnouncement, ClassEnrollment, Course, CourseAnnouncement, CourseClass, CourseContentState, CourseEnrollment, CourseKnowledgeBase, CourseSection, CourseSession, Document, User


@dataclass(frozen=True)
class CourseOverview:
    course: Course
    sections: list[CourseSection]
    section_count: int
    class_count: int
    student_count: int
    teacher_name: str | None
    content: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ClassOverview:
    course_class: CourseClass
    course_title: str
    student_count: int


from app.pagination import sql_page


class LearningService:
    """Course and class application service for the teaching-platform foundation."""

    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    def ensure_defaults(self) -> None:
        with self._session_factory() as session:
            course = session.scalar(select(Course).where(Course.code == "DSA-2026"))
            teacher = session.scalar(select(User).where(User.username == "teacher"))
            student = session.scalar(select(User).where(User.username == "student"))
            if course is None:
                course = Course(
                    title="数据结构与算法",
                    code="DSA-2026",
                    description="围绕线性结构、树、图、查找、排序与算法设计开展课程学习。",
                    semester="2026-2027 第一学期",
                    status="published",
                    owner_id=teacher.id if teacher else None,
                )
                session.add(course)
                session.flush()
                for position, title in enumerate(("课程概论", "树与二叉树", "查找", "贪心与动态规划"), 1):
                    session.add(CourseSection(course_id=course.id, title=title, position=position))
            course_class = session.scalar(select(CourseClass).where(CourseClass.invite_code == "DS2026"))
            if course_class is None:
                course_class = CourseClass(
                    course_id=course.id,
                    teacher_id=teacher.id if teacher else None,
                    name="数据结构课程演示班",
                    invite_code="DS2026",
                )
                session.add(course_class)
                session.flush()
            if student is not None:
                enrollment = session.scalar(
                    select(ClassEnrollment).where(
                        ClassEnrollment.class_id == course_class.id,
                        ClassEnrollment.user_id == student.id,
                    )
                )
                if enrollment is None:
                    session.add(ClassEnrollment(class_id=course_class.id, user_id=student.id))
                direct = session.scalar(select(CourseEnrollment).where(
                    CourseEnrollment.course_id == course.id, CourseEnrollment.user_id == student.id))
                if direct is None:
                    session.add(CourseEnrollment(course_id=course.id, user_id=student.id))
            session.commit()

    def _course_ids_for_user(self, session: Session, user_id: UUID, role: str) -> list[UUID] | None:
        if role == "admin":
            return None
        if role == "teacher":
            return list(session.scalars(select(Course.id).where(Course.owner_id == user_id)).all())
        return list(session.scalars(select(CourseEnrollment.course_id).where(
            CourseEnrollment.user_id == user_id, CourseEnrollment.status == "active")).all())

    def list_course_members(self, course_id: UUID, *, page: int | None = None, page_size: int = 10) -> list[dict] | dict:
        with self._session_factory() as session:
            statement = select(CourseEnrollment, User).join(User, User.id == CourseEnrollment.user_id).where(
                CourseEnrollment.course_id == course_id).order_by(User.display_name, User.id)
            if page is not None:
                return sql_page(session, statement, page=page, page_size=page_size,
                                mapper=lambda row: self._course_member_dict(*row), scalar=False)
            rows = session.execute(statement).all()
            return [self._course_member_dict(enrollment, user) for enrollment, user in rows]

    def enroll_course(self, course_id: UUID, *, username: str) -> dict:
        with self._session_factory() as session:
            if session.get(Course, course_id) is None:
                raise LookupError("课程不存在。")
            user = session.scalar(select(User).where(User.username == username.strip().lower()))
            if user is None or user.role != "student":
                raise LookupError("学生账号不存在。")
            if not user.active:
                raise ValueError("账号已停用，不能加入课程。")
            enrollment = session.scalar(select(CourseEnrollment).where(
                CourseEnrollment.course_id == course_id, CourseEnrollment.user_id == user.id))
            if enrollment is None:
                enrollment = CourseEnrollment(course_id=course_id, user_id=user.id)
                session.add(enrollment)
            else:
                enrollment.status = "active"
            session.commit(); session.refresh(enrollment)
            return self._course_member_dict(enrollment, user)

    def update_course_member(self, course_id: UUID, user_id: UUID, *, status: str) -> dict | None:
        with self._session_factory() as session:
            enrollment = session.scalar(select(CourseEnrollment).where(
                CourseEnrollment.course_id == course_id, CourseEnrollment.user_id == user_id))
            if enrollment is None:
                return None
            enrollment.status = status
            session.commit()
            user = session.get(User, user_id)
            return self._course_member_dict(enrollment, user)

    @staticmethod
    def _course_member_dict(enrollment: CourseEnrollment, user: User) -> dict:
        return {"enrollment_id": str(enrollment.id), "user_id": str(user.id),
                "username": user.username, "display_name": user.display_name,
                "status": enrollment.status, "joined_at": enrollment.joined_at}

    def list_courses(self, *, user_id: UUID, role: str, page: int | None = None, page_size: int = 10) -> list[CourseOverview] | dict:
        with self._session_factory() as session:
            allowed_ids = self._course_ids_for_user(session, user_id, role)
            statement = select(Course).options(selectinload(Course.sections)).order_by(Course.created_at.desc(), Course.id.desc())
            if allowed_ids is not None:
                statement = statement.where(Course.id.in_(allowed_ids))
            if page is not None:
                result=sql_page(session,statement,page=page,page_size=page_size,mapper=lambda item:item)
                result['items']=self._overviews(session,result['items'])
                return result
            courses = list(session.scalars(statement).all())
            return self._overviews(session,courses)

    def catalog_courses(self, *, user_id: UUID, role: str, page: int, page_size: int,
                        keyword: str = "", course_status: str = "all", materials: str = "all") -> dict:
        """Filter authorized courses before paging; count actual published, ready sources."""
        with self._session_factory() as session:
            bases = select(CourseKnowledgeBase.course_id,
                           func.count(CourseKnowledgeBase.knowledge_base_id).label("base_count")).group_by(
                               CourseKnowledgeBase.course_id).subquery()
            documents = select(CourseKnowledgeBase.course_id,
                               func.count(func.distinct(Document.id)).label("document_count")).join(
                                   Document, Document.knowledge_base_id == CourseKnowledgeBase.knowledge_base_id).where(
                                       Document.status == "ready", Document.publication_status == "published").group_by(
                                           CourseKnowledgeBase.course_id).subquery()
            ready_count = func.coalesce(documents.c.document_count, 0)
            statement = select(Course, func.coalesce(bases.c.base_count, 0), ready_count).outerjoin(
                bases, bases.c.course_id == Course.id).outerjoin(
                    documents, documents.c.course_id == Course.id).options(selectinload(Course.sections))
            allowed_ids = self._course_ids_for_user(session, user_id, role)
            if allowed_ids is not None:
                statement = statement.where(Course.id.in_(allowed_ids))
            term = keyword.strip()
            if term:
                statement = statement.where(or_(Course.title.icontains(term, autoescape=True),
                    Course.code.icontains(term, autoescape=True), Course.semester.icontains(term, autoescape=True)))
            if course_status != "all":
                statement = statement.where(Course.status == course_status)
            if materials == "missing":
                statement = statement.where(ready_count == 0)
            elif materials == "available":
                statement = statement.where(ready_count > 0)
            result=sql_page(session,statement.order_by(Course.created_at.desc(),Course.id.desc()),
                page=page,page_size=page_size,scalar=False,mapper=lambda row:row)
            rows=result['items']
            overviews=self._overviews(session,[row[0] for row in rows])
            result['items']=[{'overview':overview,'knowledge_base_count':int(row[1]),'ready_document_count':int(row[2])} for row,overview in zip(rows,overviews)]
            return result

    def get_course(self, course_id: UUID, *, user_id: UUID, role: str) -> CourseOverview | None:
        with self._session_factory() as session:
            allowed_ids = self._course_ids_for_user(session, user_id, role)
            if allowed_ids is not None and course_id not in allowed_ids:
                return None
            course = session.scalar(
                select(Course).where(Course.id == course_id).options(selectinload(Course.sections))
            )
            return self._overview(session, course) if course else None

    def create_course(self, *, owner_id: UUID | None, title: str, code: str, description: str | None,
                      semester: str | None, cover_image_url: str | None, schedule: str | None,
                      location: str | None, status: str) -> CourseOverview:
        with self._session_factory() as session:
            course = Course(
                owner_id=owner_id,
                title=title.strip(),
                code=code.strip().upper(),
                description=description,
                semester=semester.strip() if semester else None,
                cover_image_url=cover_image_url.strip() if cover_image_url else None,
                schedule=schedule.strip() if schedule else None,
                location=location.strip() if location else None,
                status=status,
            )
            session.add(course)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("课程代码已经存在。") from exc
            session.refresh(course)
            return self._overview(session, course)

    def update_course(self, course_id: UUID, **changes) -> CourseOverview | None:
        with self._session_factory() as session:
            course = session.get(Course, course_id)
            if course is None:
                return None
            for key, value in changes.items():
                if key in {"title", "semester", "cover_image_url", "schedule", "location"} and isinstance(value, str):
                    value = value.strip() or None
                setattr(course, key, value)
            session.commit()
            session.refresh(course)
            return self._overview(session, course)

    def add_section(self, course_id: UUID, *, title: str, description: str | None, position: int) -> CourseOverview | None:
        with self._session_factory() as session:
            course = session.get(Course, course_id)
            if course is None:
                return None
            session.add(CourseSection(course_id=course_id, title=title.strip(), description=description, position=position))
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("该章节序号已经存在。") from exc
            course = session.scalar(
                select(Course).where(Course.id == course_id).options(selectinload(Course.sections))
            )
            return self._overview(session, course)

    def list_sessions(self, course_id: UUID, *, page: int | None = None, page_size: int = 10) -> list[dict] | dict:
        with self._session_factory() as session:
            statement = select(CourseSession).where(CourseSession.course_id == course_id).order_by(CourseSession.session_date, CourseSession.id)
            section_titles = {item.id: item.title for item in session.scalars(select(CourseSection).where(CourseSection.course_id == course_id)).all()}
            if page is not None:
                return sql_page(session, statement, page=page, page_size=page_size,
                                mapper=lambda item: self._session_dict(item, section_titles.get(item.section_id)))
            items = list(session.scalars(statement).all())
            return [self._session_dict(item, section_titles.get(item.section_id)) for item in items]

    def create_session(self, course_id: UUID, **data) -> dict:
        with self._session_factory() as session:
            if session.get(Course, course_id) is None:
                raise LookupError("课程不存在。")
            section_id = UUID(data["section_id"]) if data.get("section_id") else None
            if section_id:
                section = session.get(CourseSection, section_id)
                if section is None or section.course_id != course_id:
                    raise ValueError("章节不属于当前课程。")
            item = CourseSession(
                course_id=course_id, section_id=section_id, title=data["title"].strip(),
                session_date=data["session_date"], duration_minutes=data["duration_minutes"],
                location=data.get("location") or None,
            )
            session.add(item)
            session.commit()
            session.refresh(item)
            return self._session_dict(item, section.title if section_id else None)

    def update_session(self, session_id: UUID, **changes) -> dict | None:
        with self._session_factory() as session:
            item = session.get(CourseSession, session_id)
            if item is None:
                return None
            for key, value in changes.items():
                setattr(item, key, value)
            session.commit()
            session.refresh(item)
            section_title = session.scalar(select(CourseSection.title).where(CourseSection.id == item.section_id)) if item.section_id else None
            return self._session_dict(item, section_title)

    @staticmethod
    def _session_dict(item: CourseSession, section_title: str | None) -> dict:
        return {
            "id": str(item.id), "course_id": str(item.course_id),
            "section_id": str(item.section_id) if item.section_id else None,
            "section_title": section_title, "title": item.title, "session_date": item.session_date,
            "duration_minutes": item.duration_minutes, "location": item.location, "completed": item.completed,
            "schedule_status":item.schedule_status, "revision":item.revision,"rule_id":str(item.rule_id) if item.rule_id else None,
        }

    def create_class(self, course_id: UUID, *, teacher_id: UUID | None, name: str, invite_code: str | None) -> ClassOverview | None:
        with self._session_factory() as session:
            course = session.get(Course, course_id)
            if course is None:
                return None
            code = (invite_code or secrets.token_hex(4)).strip().upper()
            course_class = CourseClass(
                course_id=course_id,
                teacher_id=teacher_id,
                name=name.strip(),
                invite_code=code,
            )
            session.add(course_class)
            try:
                session.commit()
            except IntegrityError as exc:
                session.rollback()
                raise ValueError("班级邀请码已经存在。") from exc
            session.refresh(course_class)
            return ClassOverview(course_class=course_class, course_title=course.title, student_count=0)

    def list_classes(self, *, user_id: UUID, role: str) -> list[ClassOverview]:
        with self._session_factory() as session:
            statement = select(CourseClass, Course.title).join(Course, Course.id == CourseClass.course_id)
            if role == "teacher":
                statement = statement.where(CourseClass.teacher_id == user_id)
            elif role == "student":
                statement = statement.join(ClassEnrollment, ClassEnrollment.class_id == CourseClass.id).where(
                    ClassEnrollment.user_id == user_id,
                    ClassEnrollment.status == "active",
                )
            rows = session.execute(statement.order_by(CourseClass.created_at.desc())).all()
            return [
                ClassOverview(
                    course_class=course_class,
                    course_title=course_title,
                    student_count=self._class_student_count(session, course_class.id),
                )
                for course_class, course_title in rows
            ]

    def join_class(self, *, user_id: UUID, invite_code: str) -> ClassOverview | None:
        with self._session_factory() as session:
            course_class = session.scalar(
                select(CourseClass).where(
                    CourseClass.invite_code == invite_code.strip().upper(),
                    CourseClass.status == "active",
                )
            )
            if course_class is None:
                return None
            existing = session.scalar(
                select(ClassEnrollment).where(
                    ClassEnrollment.class_id == course_class.id,
                    ClassEnrollment.user_id == user_id,
                )
            )
            if existing is None:
                session.add(ClassEnrollment(class_id=course_class.id, user_id=user_id))
            elif existing.status != "active":
                existing.status = "active"
            direct = session.scalar(select(CourseEnrollment).where(
                CourseEnrollment.course_id == course_class.course_id, CourseEnrollment.user_id == user_id))
            if direct is None:
                session.add(CourseEnrollment(course_id=course_class.course_id, user_id=user_id))
            else:
                direct.status = "active"
            session.commit()
            course = session.get(Course, course_class.course_id)
            return ClassOverview(
                course_class=course_class,
                course_title=course.title if course else "课程",
                student_count=self._class_student_count(session, course_class.id),
            )

    def list_class_members(self, class_id: UUID) -> list[dict]:
        with self._session_factory() as session:
            rows = session.execute(
                select(ClassEnrollment, User)
                .join(User, User.id == ClassEnrollment.user_id)
                .where(ClassEnrollment.class_id == class_id)
                .order_by(ClassEnrollment.joined_at.desc())
            ).all()
            return [{
                "enrollment_id": str(enrollment.id), "user_id": str(user.id), "username": user.username,
                "display_name": user.display_name, "status": enrollment.status, "joined_at": enrollment.joined_at,
            } for enrollment, user in rows]

    def update_class_member(self, class_id: UUID, user_id: UUID, status: str) -> dict | None:
        with self._session_factory() as session:
            enrollment = session.scalar(select(ClassEnrollment).where(
                ClassEnrollment.class_id == class_id, ClassEnrollment.user_id == user_id
            ))
            if enrollment is None:
                return None
            enrollment.status = status
            session.commit()
            user = session.get(User, user_id)
            return {
                "enrollment_id": str(enrollment.id), "user_id": str(user_id),
                "username": user.username if user else "", "display_name": user.display_name if user else "未知用户",
                "status": enrollment.status, "joined_at": enrollment.joined_at,
            }

    def create_announcement(self, class_id: UUID, *, author_id: UUID | None, title: str, content: str) -> dict | None:
        with self._session_factory() as session:
            if session.get(CourseClass, class_id) is None:
                return None
            item = ClassAnnouncement(class_id=class_id, author_id=author_id, title=title.strip(), content=content.strip())
            session.add(item)
            session.commit()
            session.refresh(item)
            author = session.get(User, author_id) if author_id else None
            return self._announcement_dict(item, author.display_name if author else "系统管理员")

    def list_announcements(self, class_id: UUID) -> list[dict]:
        with self._session_factory() as session:
            rows = session.execute(
                select(ClassAnnouncement, User.display_name)
                .outerjoin(User, User.id == ClassAnnouncement.author_id)
                .where(ClassAnnouncement.class_id == class_id)
                .order_by(ClassAnnouncement.published_at.desc())
            ).all()
            return [self._announcement_dict(item, author_name or "系统管理员") for item, author_name in rows]

    def create_course_announcement(self, course_id: UUID, *, author_id: UUID | None, author_name: str,
                                   title: str, content: str) -> dict | None:
        with self._session_factory() as session:
            if session.get(Course, course_id) is None:
                return None
            item = CourseAnnouncement(course_id=course_id, author_id=author_id, title=title.strip(), content=content.strip())
            session.add(item)
            session.flush()
            session.add(AuditLog(actor_id=author_id, actor_name=author_name, action="publish_course_announcement",
                                 resource_type="course", resource_id=str(course_id),
                                 detail={"announcement_id": str(item.id), "title": item.title}))
            session.commit()
            session.refresh(item)
            author = session.get(User, author_id) if author_id else None
            return self._course_announcement_dict(item, author.display_name if author else "系统管理员")

    def list_course_announcements(self, course_id: UUID) -> list[dict]:
        with self._session_factory() as session:
            rows = session.execute(
                select(CourseAnnouncement, User.display_name)
                .outerjoin(User, User.id == CourseAnnouncement.author_id)
                .where(CourseAnnouncement.course_id == course_id)
                .order_by(CourseAnnouncement.published_at.desc(), CourseAnnouncement.id.desc())
            ).all()
            return [self._course_announcement_dict(item, author_name or "系统管理员") for item, author_name in rows]

    def list_course_announcements_page(self, course_id: UUID, *, page: int, page_size: int) -> dict:
        with self._session_factory() as session:
            total = int(session.scalar(select(func.count(CourseAnnouncement.id)).where(
                CourseAnnouncement.course_id == course_id)) or 0)
            rows = session.execute(
                select(CourseAnnouncement, User.display_name)
                .outerjoin(User, User.id == CourseAnnouncement.author_id)
                .where(CourseAnnouncement.course_id == course_id)
                .order_by(CourseAnnouncement.published_at.desc(), CourseAnnouncement.id.desc())
                .offset((page - 1) * page_size).limit(page_size)
            ).all()
            return {"items": [self._course_announcement_dict(item, name or "系统管理员") for item, name in rows],
                    "total": total, "page": page, "page_size": page_size}

    def get_course_announcement(self, course_id: UUID, announcement_id: UUID) -> dict | None:
        with self._session_factory() as session:
            row = session.execute(
                select(CourseAnnouncement, User.display_name)
                .outerjoin(User, User.id == CourseAnnouncement.author_id)
                .where(CourseAnnouncement.course_id == course_id, CourseAnnouncement.id == announcement_id)
            ).first()
            return self._course_announcement_dict(row[0], row[1] or "系统管理员") if row else None

    def update_course_announcement(self, course_id: UUID, announcement_id: UUID, *, actor_id: UUID,
                                   actor_name: str, role: str, title: str, content: str) -> dict | None:
        with self._session_factory() as session:
            item = session.scalar(select(CourseAnnouncement).where(
                CourseAnnouncement.id == announcement_id, CourseAnnouncement.course_id == course_id,
            ).with_for_update())
            course = session.get(Course, course_id)
            if item is None or course is None or (role == "teacher" and course.owner_id != actor_id):
                return None
            before = {"title": item.title, "content": item.content}
            item.title, item.content = title.strip(), content.strip()
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action="update_course_announcement",
                                 resource_type="course", resource_id=str(course_id),
                                 detail={"announcement_id": str(item.id), "before": before,
                                         "after": {"title": item.title, "content": item.content}}))
            session.commit()
            author = session.get(User, item.author_id) if item.author_id else None
            return self._course_announcement_dict(item, author.display_name if author else "系统管理员")

    def delete_course_announcement(self, course_id: UUID, announcement_id: UUID, *, actor_id: UUID,
                                   actor_name: str, role: str) -> bool:
        with self._session_factory() as session:
            item = session.scalar(select(CourseAnnouncement).where(
                CourseAnnouncement.id == announcement_id, CourseAnnouncement.course_id == course_id,
            ).with_for_update())
            course = session.get(Course, course_id)
            if item is None or course is None or (role == "teacher" and course.owner_id != actor_id):
                return False
            session.add(AuditLog(actor_id=actor_id, actor_name=actor_name, action="delete_course_announcement",
                                 resource_type="course", resource_id=str(course_id),
                                 detail={"announcement_id": str(item.id), "title": item.title,
                                         "content": item.content}))
            session.delete(item)
            session.commit()
            return True

    @staticmethod
    def _course_announcement_dict(item: CourseAnnouncement, author_name: str) -> dict:
        return {
            "id": str(item.id), "course_id": str(item.course_id), "title": item.title,
            "content": item.content, "author_name": author_name, "published_at": item.published_at,
        }

    @staticmethod
    def _announcement_dict(item: ClassAnnouncement, author_name: str) -> dict:
        return {
            "id": str(item.id), "class_id": str(item.class_id), "title": item.title, "content": item.content,
            "author_name": author_name, "published_at": item.published_at,
        }

    def _overviews(self,session,courses):
        if not courses:return []
        ids=[course.id for course in courses]
        classes=dict(session.execute(select(CourseClass.course_id,func.count()).where(CourseClass.course_id.in_(ids)).group_by(CourseClass.course_id)).all())
        students=dict(session.execute(select(CourseEnrollment.course_id,func.count()).where(CourseEnrollment.course_id.in_(ids),CourseEnrollment.status=='active').group_by(CourseEnrollment.course_id)).all())
        teachers=dict(session.execute(select(User.id,User.display_name).where(User.id.in_({c.owner_id for c in courses if c.owner_id}))).all())
        content = {x.course_id: x.published for x in session.scalars(select(CourseContentState).where(CourseContentState.course_id.in_(ids)))}
        # Both callers selectin-load sections within this request; no shared cache.
        return [CourseOverview(course,sorted([x for x in course.sections if not x.archived],key=lambda s:s.position),sum(not x.archived for x in course.sections),
            int(classes.get(course.id,0)),int(students.get(course.id,0)),teachers.get(course.owner_id),content.get(course.id, {})) for course in courses]

    def _overview(self, session: Session, course: Course) -> CourseOverview:
        class_count = int(session.scalar(select(func.count(CourseClass.id)).where(CourseClass.course_id == course.id)) or 0)
        student_count = int(session.scalar(select(func.count(CourseEnrollment.id)).where(
            CourseEnrollment.course_id == course.id, CourseEnrollment.status == "active")) or 0)
        section_count = int(session.scalar(select(func.count(CourseSection.id)).where(CourseSection.course_id == course.id, CourseSection.archived.is_(False))) or 0)
        sections = list(
            session.scalars(
                select(CourseSection).where(CourseSection.course_id == course.id, CourseSection.archived.is_(False)).order_by(CourseSection.position)
            ).all()
        )
        teacher_name = session.scalar(select(User.display_name).where(User.id == course.owner_id)) if course.owner_id else None
        state = session.get(CourseContentState, course.id)
        return CourseOverview(course, sections, section_count, class_count, student_count, teacher_name, state.published if state else {})

    @staticmethod
    def _class_student_count(session: Session, class_id: UUID) -> int:
        return int(
            session.scalar(
                select(func.count(ClassEnrollment.id)).where(
                    ClassEnrollment.class_id == class_id,
                    ClassEnrollment.status == "active",
                )
            )
            or 0
        )
