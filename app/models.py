import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, LargeBinary, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class CoursePracticePolicy(Base):
    __tablename__ = 'course_practice_policies'
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'), primary_key=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class CourseSectionReading(Base):
    __tablename__ = 'course_section_readings'
    __table_args__ = (UniqueConstraint('section_id', 'document_id', 'first_page', 'last_page', name='uq_section_reading_range'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('course_sections.id', ondelete='CASCADE'), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    first_page: Mapped[int] = mapped_column(Integer, nullable=False)
    last_page: Mapped[int] = mapped_column(Integer, nullable=False)
    note: Mapped[str] = mapped_column(String(500), nullable=False, default='')
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AnswerFeedbackAnnotation(Base):
    __tablename__ = 'answer_feedback_annotations'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    history_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('question_records.id', ondelete='CASCADE'), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    answer_quote: Mapped[str] = mapped_column(Text, nullable=False)
    start_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    end_offset: Mapped[int] = mapped_column(Integer, nullable=False)
    category: Mapped[str] = mapped_column(String(30), nullable=False)
    comment: Mapped[str] = mapped_column(String(2000), nullable=False)
    source_index: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssistantTask(Base):
    __tablename__ = 'assistant_tasks'
    __table_args__ = (UniqueConstraint('actor_id', 'request_id', name='uq_assistant_task_actor_request'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    actor_role: Mapped[str] = mapped_column(String(30), nullable=False)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'), index=True)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='queued', index=True)
    stage: Mapped[str] = mapped_column(String(200), nullable=False, default='等待开始')
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True))
    error: Mapped[str | None] = mapped_column(String(600))
    usage_log_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('model_usage_logs.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class KnowledgeBase(Base):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    course: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    documents: Mapped[list["Document"]] = relationship(back_populates="knowledge_base", cascade="all, delete-orphan")


class User(Base):
    """Local application account used by the teacher/student/admin demo roles."""

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    role: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    session_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    contact: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ModelRuntimeConfig(Base):
    """Single persisted admin configuration; provider credentials are encrypted."""

    __tablename__ = "model_runtime_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    provider: Mapped[str] = mapped_column(String(30), nullable=False)
    model: Mapped[str] = mapped_column(String(200), nullable=False)
    api_base: Mapped[str] = mapped_column(String(500), nullable=False)
    api_key_ciphertext: Mapped[str | None] = mapped_column(Text)
    timeout_seconds: Mapped[float] = mapped_column(Float, nullable=False)
    fallback_offline: Mapped[bool] = mapped_column(Boolean, nullable=False)
    retrieval_top_k: Mapped[int] = mapped_column(Integer, nullable=False)
    retrieval_min_score: Mapped[float] = mapped_column(Float, nullable=False)
    retrieval_vector_weight: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(60), nullable=False, unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    semester: Mapped[str | None] = mapped_column(String(80), index=True)
    cover_image_url: Mapped[str | None] = mapped_column(String(1000))
    schedule: Mapped[str | None] = mapped_column(String(200))
    location: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    sections: Mapped[list["CourseSection"]] = relationship(
        back_populates="course", cascade="all, delete-orphan", order_by="CourseSection.position"
    )
    classes: Mapped[list["CourseClass"]] = relationship(back_populates="course", cascade="all, delete-orphan")


class CourseContentState(Base):
    __tablename__ = 'course_content_states'
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    draft: Mapped[dict | None] = mapped_column(JSONB)
    published: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    base_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CourseSection(Base):
    __tablename__ = "course_sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    archived: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default='false')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    course: Mapped[Course] = relationship(back_populates="sections")

    __table_args__ = (UniqueConstraint("course_id", "position", name="uq_course_section_position"),)


class TeacherResource(Base):
    __tablename__ = 'teacher_resources'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'), index=True)
    creator_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    pages: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='ready')
    external_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeachingWorkResult(Base):
    __tablename__ = 'teaching_work_results'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('assistant_tasks.id', ondelete='CASCADE'), unique=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'), index=True)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default='draft')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class QuestionSource(Base):
    __tablename__ = 'question_sources'
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('question_bank_items.id', ondelete='CASCADE'), primary_key=True)
    source: Mapped[dict] = mapped_column(JSONB, nullable=False)


class CourseSession(Base):
    __tablename__ = "course_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("course_sections.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    session_date: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    location: Mapped[str | None] = mapped_column(String(200))
    completed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    schedule_status: Mapped[str] = mapped_column(String(20), nullable=False, default='scheduled', server_default='scheduled')
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    rule_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TimetableResourceCatalog(Base):
    __tablename__ = 'timetable_resource_catalogs'
    semester: Mapped[str] = mapped_column(String(80), primary_key=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TimetableCalendar(Base):
    __tablename__ = 'timetable_calendars'
    semester: Mapped[str] = mapped_column(String(80), primary_key=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)


class TimetableRule(Base):
    __tablename__ = 'timetable_rules'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'), index=True)
    settings: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TimetableRequest(Base):
    __tablename__ = 'timetable_requests'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'), index=True)
    requester_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    original: Mapped[list] = mapped_column(JSONB, nullable=False)
    proposed: Mapped[list] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(String(1000), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='pending', index=True)
    review_reason: Mapped[str | None] = mapped_column(String(1000))
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TimetableEvent(Base):
    __tablename__ = 'timetable_events'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('courses.id', ondelete='CASCADE'), index=True)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class CourseClass(Base):
    __tablename__ = "course_classes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    invite_code: Mapped[str] = mapped_column(String(32), nullable=False, unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    course: Mapped[Course] = relationship(back_populates="classes")
    enrollments: Mapped[list["ClassEnrollment"]] = relationship(
        back_populates="course_class", cascade="all, delete-orphan"
    )
    announcements: Mapped[list["ClassAnnouncement"]] = relationship(
        back_populates="course_class", cascade="all, delete-orphan"
    )


class ClassEnrollment(Base):
    __tablename__ = "class_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("course_classes.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    course_class: Mapped[CourseClass] = relationship(back_populates="enrollments")

    __table_args__ = (UniqueConstraint("class_id", "user_id", name="uq_class_enrollment_user"),)


class CourseEnrollment(Base):
    """Direct course membership, independent of legacy class grouping."""

    __tablename__ = "course_enrollments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="active", index=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("course_id", "user_id", name="uq_course_enrollment_user"),)


class ClassAnnouncement(Base):
    __tablename__ = "class_announcements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("course_classes.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    course_class: Mapped[CourseClass] = relationship(back_populates="announcements")


class CourseAnnouncement(Base):
    __tablename__ = "course_announcements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    author_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class CourseKnowledgeBase(Base):
    __tablename__ = "course_knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("course_id", "knowledge_base_id", name="uq_course_knowledge_base"),)


class KnowledgePoint(Base):
    __tablename__ = "knowledge_points"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("course_sections.id", ondelete="SET NULL"), index=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("course_id", "name", name="uq_course_knowledge_point"),)


class LearningProgress(Base):
    __tablename__ = "learning_progress"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("course_sections.id", ondelete="CASCADE"), index=True)
    progress_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    mastery_percent: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("student_id", "section_id", name="uq_learning_progress_section"),)


class StudyPlan(Base):
    """Student-private action plan; completion is derived from real learning activity."""

    __tablename__ = "study_plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    items: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    previous_plan_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("study_plans.id", ondelete="SET NULL"))
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    source_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (Index("ix_study_plans_student_course_created", "student_id", "course_id", "created_at"),)


class StudyNote(Base):
    """Private excerpt and commentary tied to a published course document."""

    __tablename__ = "study_notes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("documents.id", ondelete="SET NULL"), index=True)
    source_title: Mapped[str] = mapped_column(String(500), nullable=False)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    origin: Mapped[str] = mapped_column(String(30), nullable=False, default="excerpt")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)

    __table_args__ = (Index("ix_study_notes_student_course_created", "student_id", "course_id", "created_at"),)


class QuestionBankItem(Base):
    __tablename__ = "question_bank_items"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    section_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("course_sections.id", ondelete="SET NULL"), index=True)
    creator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    question_type: Mapped[str] = mapped_column(String(30), nullable=False, default="single_choice", index=True)
    stem: Mapped[str] = mapped_column(Text, nullable=False)
    options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    correct_answer: Mapped[str] = mapped_column(Text, nullable=False)
    explanation: Mapped[str | None] = mapped_column(Text)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    knowledge_point: Mapped[str | None] = mapped_column(String(200), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class TeachingDraft(Base):
    """AI-assisted teaching content that requires explicit teacher confirmation."""

    __tablename__ = "teaching_drafts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    creator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    draft_type: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    questions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="draft", index=True)
    confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class Assignment(Base):
    __tablename__ = "assignments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("courses.id", ondelete="CASCADE"), index=True)
    class_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("course_classes.id", ondelete="SET NULL"), index=True)
    creator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    published_review_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("teaching_drafts.id", ondelete="SET NULL"), index=True,
    )
    source_draft_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("teaching_drafts.id", ondelete="SET NULL"), index=True)
    workflow_request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="published", index=True)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default='1')
    ai_policy: Mapped[str] = mapped_column(String(20), nullable=False, default='hints', server_default='hints')
    previous_version_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('assignments.id', ondelete='SET NULL'), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    questions: Mapped[list["AssignmentQuestion"]] = relationship(
        back_populates="assignment", cascade="all, delete-orphan", order_by="AssignmentQuestion.position"
    )

    __table_args__ = (UniqueConstraint("workflow_request_id", name="uq_assignments_workflow_request"),)


class AssignmentRevisionSnapshot(Base):
    __tablename__ = 'assignment_revision_snapshots'
    __table_args__ = (UniqueConstraint('assignment_id', 'revision', name='uq_assignment_revision_snapshot'),)
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('assignments.id', ondelete='CASCADE'), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AssignmentQuestion(Base):
    __tablename__ = "assignment_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question_bank_items.id", ondelete="CASCADE"), index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    points: Mapped[float] = mapped_column(Float, nullable=False, default=10.0)

    assignment: Mapped[Assignment] = relationship(back_populates="questions")

    __table_args__ = (
        UniqueConstraint("assignment_id", "question_id", name="uq_assignment_question_item"),
        UniqueConstraint("assignment_id", "position", name="uq_assignment_question_position"),
    )


class AssignmentSubmission(Base):
    __tablename__ = "assignment_submissions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    answers: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="submitted", index=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_assignment_submission_student"),)


class LateSubmissionRequest(Base):
    """Student request and teacher decision for submitting after an assignment deadline."""

    __tablename__ = "late_submission_requests"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    assignment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignments.id", ondelete="CASCADE"), index=True)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    review_note: Mapped[str | None] = mapped_column(Text)
    approved_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    requested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("assignment_id", "student_id", name="uq_late_request_assignment_student"),)


class SubmissionReview(Base):
    __tablename__ = "submission_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    submission_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("assignment_submissions.id", ondelete="CASCADE"), unique=True, index=True)
    teacher_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text)
    graded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class WrongQuestion(Base):
    __tablename__ = "wrong_questions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question_bank_items.id", ondelete="CASCADE"), index=True)
    wrong_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    correct_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_answer: Mapped[str | None] = mapped_column(Text)
    mastered: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    last_practiced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("student_id", "question_id", name="uq_wrong_question_student"),)


class PracticeAttempt(Base):
    """A durable audit trail for adaptive practice and wrong-question retries."""

    __tablename__ = "practice_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    question_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("question_bank_items.id", ondelete="CASCADE"), index=True)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    is_correct: Mapped[bool | None] = mapped_column(Boolean, index=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False, default="adaptive", index=True)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class PracticeSubmissionReceipt(Base):
    """Owner-scoped retry receipt; historical attempts are not rewritten."""
    __tablename__ = 'practice_submission_receipts'
    student_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), primary_key=True)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('practice_attempts.id', ondelete='CASCADE'), nullable=False, unique=True)
    request_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class PracticeFeedback(Base):
    """One cached, student-owned coaching result for an immutable practice attempt."""

    __tablename__ = "practice_feedback"

    attempt_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("practice_attempts.id", ondelete="CASCADE"), primary_key=True)
    snapshot_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="processing")
    analysis: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    model: Mapped[str | None] = mapped_column(String(200))
    generation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AdminAssistantOperation(Base):
    """Explicit human-reviewed operations; never contains arbitrary model commands."""

    __tablename__ = "admin_assistant_operations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    target_id: Mapped[str] = mapped_column(String(100), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    expected_signature: Mapped[str] = mapped_column(String(64), nullable=False)
    before: Mapped[dict] = mapped_column(JSONB, nullable=False)
    proposed: Mapped[dict] = mapped_column(JSONB, nullable=False)
    private_payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="prepared", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_type: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    resource_id: Mapped[str | None] = mapped_column(String(100), index=True)
    detail: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class LoginAttempt(Base):
    __tablename__ = "login_attempts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    ip_address: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    successful: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class RequestLog(Base):
    __tablename__ = "request_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[str] = mapped_column(String(36), nullable=False, unique=True, index=True)
    method: Mapped[str] = mapped_column(String(10), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False, index=True)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ModelUsageLog(Base):
    __tablename__ = "model_usage_logs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    role: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    feature: Mapped[str] = mapped_column(String(60), nullable=False, index=True)
    provider: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_ms: Mapped[float] = mapped_column(Float, nullable=False)
    successful: Mapped[bool] = mapped_column(Boolean, nullable=False, index=True)
    error_type: Mapped[str | None] = mapped_column(String(120), index=True)
    usage_detail: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class ModelQuota(Base):
    __tablename__ = "model_quotas"

    role: Mapped[str] = mapped_column(String(30), primary_key=True)
    daily_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    case_count: Mapped[int] = mapped_column(Integer, nullable=False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    details: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    created_by: Mapped[str] = mapped_column(String(120), nullable=False, default="system")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    license_name: Mapped[str | None] = mapped_column(String(200))
    license_url: Mapped[str | None] = mapped_column(Text)
    external_model_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    version_label: Mapped[str] = mapped_column(String(80), nullable=False, default="1.0")
    publication_status: Mapped[str] = mapped_column(String(30), nullable=False, default="published", index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="pending", index=True)
    page_count: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    content_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    knowledge_base: Mapped[KnowledgeBase] = relationship(back_populates="documents")
    chunks: Mapped[list["Chunk"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    pages: Mapped[list["DocumentPage"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class DocumentPage(Base):
    __tablename__ = "document_pages"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter: Mapped[str | None] = mapped_column(String(500))
    content: Mapped[str] = mapped_column(Text, nullable=False)

    document: Mapped[Document] = relationship(back_populates="pages")

    __table_args__ = (UniqueConstraint("document_id", "page_number", name="uq_document_page_number"),)


class DocumentIngestionJob(Base):
    """Persistent PDF parsing/indexing task with retryable source payload."""

    __tablename__ = "document_ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="CASCADE"), index=True)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    creator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(120), nullable=False, default="application/pdf")
    source_payload: Mapped[bytes | None] = mapped_column(LargeBinary)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="queued", index=True)
    progress_percent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    page_count: Mapped[int | None] = mapped_column(Integer)
    chunk_count: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    base_revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default='0')
    lease_token: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)


class DocumentVersion(Base):
    __tablename__ = 'document_versions'
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('documents.id', ondelete='CASCADE'), index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    filename: Mapped[str] = mapped_column(String(500), nullable=False)
    pages: Mapped[list] = mapped_column(JSONB, nullable=False)
    chunks: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_payload: Mapped[bytes | None] = mapped_column(LargeBinary)
    preprocessing: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    creator_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    __table_args__ = (UniqueConstraint('document_id', 'revision', name='uq_document_content_version'),)


class OperationalTask(Base):
    __tablename__='operational_tasks'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    request_id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),unique=True)
    kind: Mapped[str]=mapped_column(String(40),nullable=False)
    parameters: Mapped[dict]=mapped_column(JSONB,nullable=False)
    status: Mapped[str]=mapped_column(String(30),nullable=False,default='queued',index=True)
    progress: Mapped[int]=mapped_column(Integer,nullable=False,default=0)
    attempt: Mapped[int]=mapped_column(Integer,nullable=False,default=0)
    lease_token: Mapped[uuid.UUID|None]=mapped_column(UUID(as_uuid=True))
    lease_until: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    result: Mapped[dict]=mapped_column(JSONB,nullable=False,default=dict)
    error: Mapped[str|None]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class AuthSession(Base):
    __tablename__='auth_sessions'
    id: Mapped[uuid.UUID]=mapped_column(UUID(as_uuid=True),primary_key=True,default=uuid.uuid4)
    user_id: Mapped[uuid.UUID]=mapped_column(ForeignKey('users.id',ondelete='CASCADE'),index=True)
    refresh_hash: Mapped[str|None]=mapped_column(String(64),unique=True)
    session_version: Mapped[int]=mapped_column(Integer,nullable=False)
    label: Mapped[str]=mapped_column(String(200),nullable=False,default='浏览器会话')
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False)
    revoked_at: Mapped[datetime|None]=mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())
    last_seen_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),server_default=func.now())


class RevokedAuthToken(Base):
    __tablename__='revoked_auth_tokens'
    token_hash: Mapped[str]=mapped_column(String(64),primary_key=True)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),nullable=False,index=True)


class Chunk(Base):
    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    page_number: Mapped[int] = mapped_column(Integer, nullable=False)
    chapter: Mapped[str | None] = mapped_column(String(500))
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_metadata: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(512))

    document: Mapped[Document] = relationship(back_populates="chunks")

    __table_args__ = (
        Index("ix_chunks_document_page_position", "document_id", "page_number", "position", unique=True),
        Index("ix_chunks_embedding_hnsw", "embedding", postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"}),
    )


class TutorConversation(Base):
    __tablename__ = "tutor_conversations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("knowledge_bases.id", ondelete="SET NULL"), index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True)


class QuestionRecord(Base):
    """A durable audit trail for questions, answers, evidence and feedback."""

    __tablename__ = "question_records"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_base_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("knowledge_bases.id", ondelete="SET NULL"), index=True
    )
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("tutor_conversations.id", ondelete="SET NULL"), index=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    citations: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    actions: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    external_context_safe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    context_document_ids: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    access_context: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    rating: Mapped[int | None] = mapped_column(Integer)
    feedback: Mapped[str | None] = mapped_column(Text)
    favorite: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)


class TeachingQuestionReview(Base):
    """Durable advisory result for an exact saved question, never a grade."""

    __tablename__ = 'teaching_question_reviews'
    __table_args__ = (UniqueConstraint('actor_id', 'request_id', name='uq_question_reviews_actor_request'),
        Index('ix_question_reviews_draft_question_created', 'draft_id', 'question_index', 'created_at'))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    draft_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teaching_drafts.id', ondelete='CASCADE'), nullable=False)
    actor_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    actor_role: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    question_index: Mapped[int] = mapped_column(Integer, nullable=False)
    question_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    question_snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    answer_scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    evidence: Mapped[list] = mapped_column(JSONB, nullable=False)
    provider: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(120), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='processing')
    stage: Mapped[str] = mapped_column(String(200), nullable=False)
    result: Mapped[dict | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    usage_log_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('model_usage_logs.id', ondelete='SET NULL'))
    usage_data: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    error_message: Mapped[str | None] = mapped_column(String(600))
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class TeachingReviewDecision(Base):
    """Append-only teacher handling notes; never edits an AI result or a grade."""

    __tablename__ = 'teaching_review_decisions'
    __table_args__ = (UniqueConstraint('actor_id', 'request_id', name='uq_review_decisions_actor_request'),
        Index('ix_review_decisions_review_finding_created', 'review_id', 'finding_id', 'created_at'))
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    review_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('teaching_question_reviews.id', ondelete='CASCADE'), nullable=False)
    finding_id: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('users.id', ondelete='SET NULL'))
    actor_name: Mapped[str] = mapped_column(String(120), nullable=False)
    decision: Mapped[str] = mapped_column(String(20), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    question_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AnswerRequest(Base):
    """Owner-scoped receipt; incomplete answer text is never stored here."""

    __tablename__ = 'answer_requests'

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True)
    client_request_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_signature: Mapped[str | None] = mapped_column(String(64))
    question: Mapped[str] = mapped_column(Text, nullable=False, default='')
    context: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default='in_progress', index=True)
    history_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('question_records.id', ondelete='SET NULL'), unique=True)
    usage_log_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey('model_usage_logs.id', ondelete='SET NULL'))
    response: Mapped[dict | None] = mapped_column(JSONB)
    error_status: Mapped[int | None] = mapped_column(Integer)
    error_message: Mapped[str | None] = mapped_column(String(600))
    lease_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint('user_id', 'client_request_id', name='uq_answer_requests_owner_client'),)


class QuestionReview(Base):
    """Teacher moderation result for one AI tutor conversation."""

    __tablename__ = "question_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    question_record_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("question_records.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    reviewer_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, index=True)
    revised_answer: Mapped[str | None] = mapped_column(Text)
    review_note: Mapped[str | None] = mapped_column(Text)
    published_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id", ondelete="SET NULL"), index=True
    )
    reviewed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
