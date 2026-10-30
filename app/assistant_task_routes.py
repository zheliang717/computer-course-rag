from uuid import UUID
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, model_validator
from app.schemas import TeachingDraftGenerate


class AnalysisPayload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    course_id: UUID
    target_id: UUID
    confirm_external_analysis: bool = False
    include_student_answers: bool = True
    local_only: bool = False


class TaskInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    request_id: UUID
    kind: Literal['teaching_draft', 'assignment_review', 'student_analysis', 'cohort_analysis', 'material_extract', 'course_content', 'schedule_plan'] = 'teaching_draft'
    payload: dict

    @model_validator(mode='after')
    def validate_payload(self):
        from app.teaching_work_schemas import TASK_SCHEMAS
        schema = TASK_SCHEMAS.get(self.kind) or (TeachingDraftGenerate if self.kind == 'teaching_draft' else AnalysisPayload)
        self.payload = schema.model_validate(self.payload).model_dump(mode='json')
        return self


def assistant_task_router(service, current_user):
    router = APIRouter(prefix='/api/v1/assistant/tasks')
    def run(fn):
        if service is None: raise HTTPException(503, '后台任务需要持久化存储。')
        try: return fn()
        except PermissionError as exc: raise HTTPException(404, str(exc)) from exc
        except ValueError as exc: raise HTTPException(409, str(exc)) from exc

    @router.post('', status_code=202)
    def create(data: TaskInput, user=Depends(current_user)):
        return run(lambda: service.create(user, data.request_id, data.payload, data.kind))

    @router.get('')
    def listing(page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50), user=Depends(current_user)):
        return run(lambda: service.list(user, page, page_size))

    @router.get('/{task_id}')
    def get(task_id: UUID, user=Depends(current_user)):
        return run(lambda: service.get(user, task_id))

    @router.post('/{task_id}/{action}')
    def action(task_id: UUID, action: Literal['cancel', 'retry'], user=Depends(current_user)):
        return run(lambda: service.action(user, task_id, action))
    return router
