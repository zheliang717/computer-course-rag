from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError


class StrictInput(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class SectionContent(StrictInput):
    id: UUID
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=2000)
    archived: bool = False


class PointContent(StrictInput):
    id: UUID
    name: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=3000)
    section_id: UUID | None = None


class CourseContent(StrictInput):
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default='', max_length=3000)
    learning_objectives: str = Field(default='', max_length=10000)
    assessment: str = Field(default='', max_length=10000)
    cover_image_url: str = Field(default='', max_length=1000)
    owner_id: UUID | None = None
    sections: list[SectionContent] = Field(default_factory=list, max_length=200)
    knowledge_points: list[PointContent] = Field(default_factory=list, max_length=1000)
    knowledge_base_ids: list[UUID] = Field(default_factory=list, max_length=100)

    @field_validator('cover_image_url')
    @classmethod
    def safe_image(cls, value):
        if value and not (value.lower().startswith(('https://', 'http://')) or value.startswith('/') and not value.startswith('//')):
            raise ValueError('封面请使用 HTTP 或 HTTPS 图片地址。')
        return value


class DraftInput(StrictInput):
    revision: int = Field(ge=0)
    base_signature: str = Field(min_length=64, max_length=64)
    content: CourseContent


class RevisionInput(StrictInput):
    revision: int = Field(ge=1)


class PublishInput(RevisionInput):
    confirmed: bool = False


def course_editor_router(service, current_user):
    router = APIRouter(prefix='/api/v1/courses/{course_id}/editor')

    def run(fn):
        if service is None: raise HTTPException(503, '课程编辑需要持久化存储。')
        try: return fn()
        except PermissionError as exc: raise HTTPException(404, str(exc)) from exc
        except ValueError as exc: raise HTTPException(409, str(exc)) from exc
        except IntegrityError as exc: raise HTTPException(409, '课程内容存在重复或已经变化，请刷新后核对。') from exc

    @router.get('')
    def get(course_id: UUID, user=Depends(current_user)):
        return run(lambda: service.get(user, course_id))

    @router.put('')
    def save(course_id: UUID, data: DraftInput, user=Depends(current_user)):
        return run(lambda: service.save(user, course_id, data))

    @router.post('/publish')
    def publish(course_id: UUID, data: PublishInput, user=Depends(current_user)):
        return run(lambda: service.publish(user, course_id, data.revision, data.confirmed))

    @router.post('/discard')
    def discard(course_id: UUID, data: RevisionInput, user=Depends(current_user)):
        return run(lambda: service.discard(user, course_id, data.revision))

    @router.get('/libraries')
    def libraries(course_id: UUID, keyword: str = Query('', max_length=100), page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50), user=Depends(current_user)):
        return run(lambda: service.libraries(user, course_id, keyword, page, page_size))

    @router.get('/teachers')
    def teachers(course_id: UUID, keyword: str = Query('', max_length=100), page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50), user=Depends(current_user)):
        return run(lambda: service.teachers(user, course_id, keyword, page, page_size))

    return router
