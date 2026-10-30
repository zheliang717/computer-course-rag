from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.exc import IntegrityError


class ReadingInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: UUID
    first_page: int = Field(ge=1, le=100000)
    last_page: int = Field(ge=1, le=100000)
    note: str = Field(default='', max_length=500)
    position: int = Field(default=1, ge=1, le=10000)
    revision: int | None = Field(default=None, ge=1)

    @model_validator(mode='after')
    def range(self):
        if self.last_page < self.first_page or self.last_page - self.first_page >= 500:
            raise ValueError('每项阅读范围应为1—500页。')
        return self


class AnnotationInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    answer_quote: str = Field(min_length=2, max_length=2000)
    start_offset: int = Field(ge=0, le=100000)
    end_offset: int = Field(ge=1, le=100000)
    category: Literal['factual', 'calculation', 'citation', 'unclear', 'other']
    comment: str = Field(min_length=2, max_length=2000)
    source_index: int | None = Field(default=None, ge=1, le=20)


def learning_assistance_router(service, current_user):
    router = APIRouter(prefix='/api/v1')
    def run(fn):
        if service is None: raise HTTPException(503, '课程辅助服务需要持久化存储。')
        try: return fn()
        except PermissionError as exc: raise HTTPException(404, str(exc)) from exc
        except ValueError as exc: raise HTTPException(409, str(exc)) from exc
        except IntegrityError as exc: raise HTTPException(409, '存在重复或已变更的记录，请刷新后核对。') from exc

    @router.get('/sections/{section_id}/readings')
    def readings(section_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50), user=Depends(current_user)):
        return run(lambda: service.readings(user, section_id, page, page_size))

    @router.post('/sections/{section_id}/readings', status_code=201)
    def create(section_id: UUID, data: ReadingInput, user=Depends(current_user)):
        return run(lambda: service.save_reading(user, section_id, data))

    @router.put('/sections/{section_id}/readings/{reading_id}')
    def update(section_id: UUID, reading_id: UUID, data: ReadingInput, user=Depends(current_user)):
        return run(lambda: service.save_reading(user, section_id, data, reading_id))

    @router.delete('/sections/{section_id}/readings/{reading_id}')
    def delete(section_id: UUID, reading_id: UUID, revision: int = Query(ge=1), user=Depends(current_user)):
        return run(lambda: service.delete_reading(user, section_id, reading_id, revision))

    @router.get('/history/{history_id}/annotations')
    def annotations(history_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50), user=Depends(current_user)):
        return run(lambda: service.annotations(user, history_id, page=page, page_size=page_size))

    @router.post('/history/{history_id}/annotations', status_code=201)
    def annotate(history_id: UUID, data: AnnotationInput, user=Depends(current_user)):
        return run(lambda: service.annotations(user, history_id, data))

    @router.get('/question-reviews/{history_id}/annotations')
    def review_annotations(history_id: UUID, page: int = Query(1, ge=1), page_size: int = Query(5, ge=1, le=20), user=Depends(current_user)):
        return run(lambda: service.review_annotations(user, history_id, page, page_size))
    return router
