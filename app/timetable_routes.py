from datetime import date, time
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, field_validator
from app.timetable import TimetableService, ScheduleConflict
from app.timetable_resources import ResourceInput, resource_state, resource_suggestions
from app.schedule_planning import SchedulePlanningService, CandidateInput, ReplanInput


class Input(BaseModel):
    model_config=ConfigDict(extra='forbid')


class Calendar(Input):
    semester:str=Field(min_length=1,max_length=80)
    start_date:date
    end_date:date
    holidays:list[date]=Field(default_factory=list,max_length=80)
    rooms:list[str]=Field(default_factory=list,max_length=200)
    expected_revision:int=Field(ge=0)

    @field_validator('semester')
    @classmethod
    def nonblank(cls,value):
        if not value.strip(): raise ValueError('内容不能为空。')
        return value.strip()

    @field_validator('rooms')
    @classmethod
    def bounded_rooms(cls,values):
        if any(len(x)>200 for x in values): raise ValueError('场地名称过长。')
        return values


class Change(Input):
    kind:Literal['move','room','cancel','makeup']='move'
    scope:Literal['single','following']='single'
    session_date:AwareDatetime|None=None
    duration_minutes:int|None=Field(default=None,ge=15,le=480)
    location:str|None=Field(default=None,max_length=200)
    title:str|None=Field(default=None,min_length=1,max_length=200)
    section_id:UUID|None=None
    reason:str=Field(min_length=5,max_length=1000)
    expected_revision:int=Field(ge=1)
    acknowledge_student_conflicts:bool=False
    _reason=field_validator('reason')(Calendar.nonblank.__func__)

    @field_validator('reason','title')
    @classmethod
    def trim_content(cls,value,info):
        if value is None: return value
        value=value.strip()
        if len(value)<(5 if info.field_name=='reason' else 1): raise ValueError('请填写完整内容。')
        return value


class Review(Input):
    approved:bool
    reason:str=Field(min_length=5,max_length=1000)
    acknowledge_student_conflicts:bool=False
    confirmed:bool=False
    _reason=field_validator('reason')(Calendar.nonblank.__func__)

    @field_validator('reason')
    @classmethod
    def review_reason(cls,value):
        if len(value)<5: raise ValueError('请填写至少5字的审核意见。')
        return value


class Batch(Input):
    course_id:UUID
    title:str=Field(min_length=1,max_length=200)
    section_id:UUID|None=None
    start_week:int=Field(ge=1,le=53)
    end_week:int=Field(ge=1,le=53)
    weekdays:list[int]=Field(min_length=1,max_length=7)
    parity:Literal['all','odd','even']='all'
    start_time:time
    duration_minutes:int=Field(ge=15,le=480)
    location:str=Field(max_length=200)
    preview_digest:str=Field(default='',max_length=64)
    confirmed:bool=False
    acknowledge_student_conflicts:bool=False
    _title=field_validator('title')(Calendar.nonblank.__func__)

    @field_validator('weekdays')
    @classmethod
    def days(cls,values):
        if any(x<1 or x>7 for x in values): raise ValueError('星期须为1—7。')
        return values


def timetable_router(service:TimetableService|None,current_user):
    router=APIRouter(prefix='/api/v1/timetable')
    planner=SchedulePlanningService(service) if service else None
    def run(fn):
        if service is None: raise HTTPException(503,'课表需要持久化数据库。')
        try: return fn()
        except ScheduleConflict as e: raise HTTPException(409,detail={'message':str(e),'conflicts':e.conflicts}) from e
        except PermissionError as e: raise HTTPException(403,str(e)) from e
        except ValueError as e: raise HTTPException(400,str(e)) from e

    @router.get('/options')
    def options(user=Depends(current_user)): return run(lambda:service.options(user))

    @router.get('/resources')
    def resources(semester:str=Query(min_length=1,max_length=80),user=Depends(current_user)):
        return run(lambda:resource_state(service,user,semester))

    @router.get('/resource-suggestions')
    def suggestions(semester:str=Query(min_length=1,max_length=80),user=Depends(current_user)):
        return run(lambda:resource_suggestions(service,user,semester))

    @router.put('/resources')
    def save_resources(data:ResourceInput,user=Depends(current_user)):
        return run(lambda:resource_state(service,user,data.semester,data))

    @router.get('/conflicts')
    def conflicts(start:date,end:date,page:int=Query(1,ge=1),page_size:int=Query(10,ge=1,le=50),user=Depends(current_user)):
        return run(lambda:planner.audit(user,start,end,page,page_size))

    @router.post('/sessions/{session_id}/candidates')
    def candidates(session_id:UUID,data:CandidateInput,user=Depends(current_user)):
        return run(lambda:planner.candidates(user,session_id,data))

    @router.post('/replan/preview')
    def replan_preview(data:ReplanInput,user=Depends(current_user)):
        return run(lambda:planner.replan(user,data))

    @router.post('/replan/apply')
    def replan_apply(data:ReplanInput,user=Depends(current_user)):
        return run(lambda:planner.replan(user,data,commit=True))

    @router.get('')
    def listing(start:date,end:date,semester:str|None=Query(None,max_length=80),course_id:UUID|None=None,user=Depends(current_user)):
        return run(lambda:service.listing(user,start,end,semester,course_id))

    @router.get('/sessions/{session_id}')
    def detail(session_id:UUID,user=Depends(current_user)): return run(lambda:service.detail(user,session_id))

    @router.post('/sessions/{session_id}/change')
    def change(session_id:UUID,data:Change,user=Depends(current_user)):
        return run(lambda:service.change(user,session_id,data))

    @router.post('/sessions/{session_id}/requests',status_code=201)
    def request(session_id:UUID,data:Change,user=Depends(current_user)):
        return run(lambda:service.change(user,session_id,data,request=True))

    @router.get('/requests')
    def requests(page:int=Query(1,ge=1),page_size:int=Query(10,ge=1,le=50),
            status:Literal['pending','approved','rejected','withdrawn']|None=None,user=Depends(current_user)):
        return run(lambda:service.requests(user,page,page_size,status))

    @router.post('/requests/{request_id}/withdraw')
    def withdraw(request_id:UUID,user=Depends(current_user)): return run(lambda:service.withdraw(user,request_id))

    @router.post('/requests/{request_id}/review')
    def review(request_id:UUID,data:Review,user=Depends(current_user)):
        if not data.confirmed: raise HTTPException(400,'请核对影响课次后明确确认审核。')
        return run(lambda:service.review(user,request_id,data.approved,data.reason,data.acknowledge_student_conflicts))

    @router.put('/calendar')
    def calendar(data:Calendar,user=Depends(current_user)): return run(lambda:service.save_calendar(user,data))

    @router.post('/batch/preview')
    def preview(data:Batch,user=Depends(current_user)): return run(lambda:service.batch(user,data))

    @router.post('/batch/publish',status_code=201)
    def publish(data:Batch,user=Depends(current_user)): return run(lambda:service.batch(user,data,commit=True))

    @router.get('/changes')
    def events(page:int=Query(1,ge=1),page_size:int=Query(5,ge=1,le=50),user=Depends(current_user)):
        return run(lambda:service.events(user,page,page_size))
    return router
