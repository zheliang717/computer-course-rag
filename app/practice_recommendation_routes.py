from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PracticePolicyInput(BaseModel):
    model_config = ConfigDict(extra='forbid')
    due: int = Field(ge=0, le=100)
    variant: int = Field(ge=0, le=100)
    new: int = Field(ge=0, le=100)
    taught: int = Field(ge=0, le=100)
    interval_days: list[int] = Field(min_length=1, max_length=8)
    revision: int = Field(ge=0)

    @model_validator(mode='after')
    def totals(self):
        if sum((self.due, self.variant, self.new, self.taught)) != 100:
            raise ValueError('四类比例之和须为100%。')
        if any(type(n) is not int or not 1 <= n <= 180 for n in self.interval_days) or sorted(set(self.interval_days)) != self.interval_days:
            raise ValueError('复习间隔须为1—180天的递增整数。')
        return self


def practice_recommendation_router(service, current_user):
    router = APIRouter(prefix='/api/v1')
    def run(fn):
        if service is None: raise HTTPException(503, '练习策略需要持久化存储。')
        try: return fn()
        except PermissionError as exc: raise HTTPException(404, str(exc)) from exc
        except ValueError as exc: raise HTTPException(409, str(exc)) from exc

    @router.get('/courses/{course_id}/practice-policy')
    def policy(course_id: UUID, user=Depends(current_user)):
        return run(lambda: service.policy(user, course_id))

    @router.put('/courses/{course_id}/practice-policy')
    def save(course_id: UUID, data: PracticePolicyInput, user=Depends(current_user)):
        return run(lambda: service.policy(user, course_id, data))

    @router.get('/questions/{question_id}/statistics')
    def stats(question_id: UUID, user=Depends(current_user)):
        return run(lambda: service.statistics(user, question_id))
    return router
