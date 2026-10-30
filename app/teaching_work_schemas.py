from datetime import date
from typing import Literal
from uuid import UUID
from pydantic import Field, model_validator
from app.course_editor_routes import StrictInput
from app.schedule_planning import PlanningWindow
from app.schemas import QuestionDraftItem


class MaterialTask(StrictInput):
    course_id: UUID
    resource_id: UUID | None = None
    document_id: UUID | None = None
    first_page: int = Field(default=1, ge=1)
    last_page: int = Field(default=1, ge=1)
    excerpt: str = Field(default='', max_length=10000)

    @model_validator(mode='after')
    def source(self):
        if bool(self.resource_id) == bool(self.document_id): raise ValueError('请选择一份教师资料或课程学习资料。')
        if not 0 <= self.last_page - self.first_page < 10: raise ValueError('每次选择1—10页。')
        return self


class CourseTask(StrictInput):
    course_id: UUID
    request: str = Field(min_length=2, max_length=2000)
    document_id: UUID | None = None
    resource_id: UUID | None = None
    first_page: int = Field(default=1, ge=1)
    last_page: int = Field(default=1, ge=1)
    allow_external: bool = False

    @model_validator(mode='after')
    def source(self):
        if self.resource_id and self.document_id: raise ValueError('每次选择一份参考资料。')
        if not 0 <= self.last_page - self.first_page < 10: raise ValueError('每次最多参考10页。')
        return self


class ScheduleTask(PlanningWindow):
    course_id: UUID
    request: str = Field(min_length=2, max_length=2000)
    session_ids: list[UUID] = Field(default_factory=list, max_length=8)
    count: int = Field(default=1, ge=1, le=8)
    duration_minutes: int = Field(default=90, ge=15, le=240)

    @model_validator(mode='after')
    def unique(self):
        if len(set(self.session_ids)) != len(self.session_ids): raise ValueError('课次不能重复选择。')
        return self


class CourseSuggestion(StrictInput):
    description: str = Field(default='', max_length=3000)
    learning_objectives: str = Field(default='', max_length=10000)
    assessment: str = Field(default='', max_length=10000)
    sections: list['SuggestedSection'] = Field(default_factory=list, max_length=20)


class SuggestedSection(StrictInput):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=2000)
    knowledge_points: list[str] = Field(default_factory=list, max_length=20)


class ScheduleSuggestion(StrictInput):
    day_start: str = Field(pattern=r'^\d\d:\d\d$')
    day_end: str = Field(pattern=r'^\d\d:\d\d$')
    weekdays: list[int] = Field(min_length=1, max_length=7)
    rooms: list[str] = Field(max_length=30)
    explanation: str = Field(min_length=1, max_length=2000)


class ResourceEdit(StrictInput):
    revision: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=200)
    archived: bool | None = None
    external_allowed: bool | None = None


class SelectedQuestion(QuestionDraftItem):
    candidate_id: UUID


class AdoptQuestions(StrictInput):
    revision: int = Field(ge=1)
    confirmed: bool = False
    questions: list[SelectedQuestion] = Field(min_length=1, max_length=50)


class AdoptCourse(StrictInput):
    revision: int = Field(ge=1)
    confirmed: bool = False
    fields: list[Literal['description', 'learning_objectives', 'assessment', 'sections']] = Field(min_length=1, max_length=4)
    suggestion: CourseSuggestion


class AdoptSchedule(StrictInput):
    revision: int = Field(ge=1)
    confirmed: bool = False
    option: int = Field(ge=0, le=2)
    reason: str = Field(min_length=5, max_length=500)


class ReviseSchedule(StrictInput):
    revision: int = Field(ge=1)
    conditions: ScheduleSuggestion


TASK_SCHEMAS = {'material_extract': MaterialTask, 'course_content': CourseTask, 'schedule_plan': ScheduleTask}
