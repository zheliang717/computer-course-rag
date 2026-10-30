from datetime import datetime
from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, model_validator, AwareDatetime
from app.schemas import QuestionDraftItem


class EditorQuestion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    question_id: UUID | None = None
    points: float = Field(gt=0, le=1000, allow_inf_nan=False)
    content: QuestionDraftItem | None = None


class EditorInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    revision: int = Field(ge=1)
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=3000)
    due_at: AwareDatetime | None = None
    ai_policy: Literal['disabled', 'hints', 'guided'] = 'hints'
    questions: list[EditorQuestion] = Field(min_length=1, max_length=100)
    reason: str = Field(min_length=2, max_length=500)


class PublishInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    signature: str = Field(pattern=r'^[0-9a-f]{64}$')
    confirmed: Literal[True]


class ForkInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID


def assignment_editor_router(service, current_user):
    router = APIRouter(prefix='/api/v1/assignments')
    def run(fn):
        if service is None: raise HTTPException(503, '作业编辑需要持久化存储。')
        try: return fn()
        except PermissionError as exc: raise HTTPException(404, str(exc)) from exc
        except ValueError as exc: raise HTTPException(409, str(exc)) from exc

    @router.get('/{identifier}/editor')
    def get(identifier: UUID, user=Depends(current_user)): return run(lambda: service.get(user, identifier))

    @router.put('/{identifier}/editor')
    def save(identifier: UUID, data: EditorInput, user=Depends(current_user)): return run(lambda: service.save(user, identifier, data))

    @router.get('/{identifier}/publication-preview')
    def preview(identifier: UUID, user=Depends(current_user)): return run(lambda: service.preview(user, identifier))

    @router.post('/{identifier}/publish')
    def publish(identifier: UUID, data: PublishInput, user=Depends(current_user)): return run(lambda: service.publish(user, identifier, data))

    @router.post('/{identifier}/fork', status_code=201)
    def fork(identifier: UUID, data: ForkInput, user=Depends(current_user)): return run(lambda: service.fork(user, identifier, data))

    @router.get('/{identifier}/revisions')
    def history(identifier: UUID, page: int = Query(1, ge=1), page_size: int = Query(5, ge=1, le=20), user=Depends(current_user)):
        return run(lambda: service.history(user, identifier, page, page_size))
    return router
