from uuid import UUID
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import Response
from sqlalchemy.exc import IntegrityError
from app.timetable import ScheduleConflict
from app.teaching_work_schemas import ResourceEdit, AdoptQuestions, AdoptCourse, AdoptSchedule, MaterialTask, ReviseSchedule


def teaching_work_router(resources, workflows, current_user):
    router=APIRouter(prefix='/api/v1')
    def run(fn):
        if resources is None or workflows is None: raise HTTPException(503,'教学工作流需要持久化存储。')
        try: return fn()
        except PermissionError as exc: raise HTTPException(404,str(exc)) from exc
        except ScheduleConflict as exc: raise HTTPException(409,detail={'message':str(exc),'conflicts':exc.conflicts}) from exc
        except ValueError as exc: raise HTTPException(409,str(exc)) from exc
        except IntegrityError as exc: raise HTTPException(409,'记录已变化或内容重复，请刷新后核对。') from exc

    @router.get('/courses/{course_id}/teacher-resources')
    def listing(course_id:UUID,keyword:str=Query('',max_length=100),archived:bool=False,page:int=Query(1,ge=1),page_size:int=Query(6,ge=1,le=50),user=Depends(current_user)):
        return run(lambda:resources.list(user,course_id,keyword,archived,page,page_size))

    @router.get('/courses/{course_id}/teaching-source-documents')
    def documents(course_id:UUID,keyword:str=Query('',max_length=100),page:int=Query(1,ge=1),page_size:int=Query(6,ge=1,le=50),user=Depends(current_user)):
        return run(lambda:resources.documents(user,course_id,keyword,page,page_size))

    @router.post('/courses/{course_id}/teaching-source-pages')
    def pages(course_id:UUID,data:MaterialTask,user=Depends(current_user)):
        if data.course_id!=course_id: raise HTTPException(422,'课程编号不一致。')
        return run(lambda:resources.source_pages(user,course_id,data))

    @router.get('/courses/{course_id}/schedule-targets')
    def targets(course_id:UUID,page:int=Query(1,ge=1),page_size:int=Query(6,ge=1,le=50),user=Depends(current_user)):
        return run(lambda:workflows.schedule_targets(user,course_id,page,page_size))

    @router.post('/courses/{course_id}/teacher-resources',status_code=201)
    async def upload(course_id:UUID,file:UploadFile=File(),title:str=Form(''),external_allowed:bool=Form(False),upload_id:UUID|None=Form(None),user=Depends(current_user)):
        if resources is None: raise HTTPException(503,'教师资料需要持久化存储。')
        # Authorize before reading/parsing any large multipart payload.
        run(lambda:resources.list(user,course_id,'',False,1,1))
        payload=await file.read(30*1024*1024+1)
        if len(payload)>30*1024*1024: raise HTTPException(413,'单份资料不能超过30 MB。')
        return run(lambda:resources.create(user,course_id,title or file.filename or '课程出题资料',payload,external_allowed,upload_id))

    @router.get('/courses/{course_id}/teacher-resources/{resource_id}')
    def resource(course_id:UUID,resource_id:UUID,first_page:int=Query(1,ge=1),last_page:int=Query(1,ge=1),user=Depends(current_user)):
        if not 0<=last_page-first_page<10: raise HTTPException(422,'每次查看1—10页。')
        return run(lambda:resources.get(user,course_id,resource_id,first_page,last_page))

    @router.patch('/courses/{course_id}/teacher-resources/{resource_id}')
    def edit(course_id:UUID,resource_id:UUID,data:ResourceEdit,user=Depends(current_user)):
        return run(lambda:resources.edit(user,course_id,resource_id,data))

    @router.get('/courses/{course_id}/teacher-resources/{resource_id}/pdf')
    def pdf(course_id:UUID,resource_id:UUID,user=Depends(current_user)):
        payload=run(lambda:resources.pdf(user,course_id,resource_id))
        return Response(payload,media_type='application/pdf',headers={'Content-Disposition':'attachment; filename="teacher-resource.pdf"','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'})

    @router.get('/courses/{course_id}/teaching-workflows')
    def history(course_id:UUID,page:int=Query(1,ge=1),page_size:int=Query(6,ge=1,le=50),user=Depends(current_user)):
        return run(lambda:workflows.list(user,course_id,page,page_size))

    @router.get('/teaching-workflows/{identifier}')
    def get(identifier:UUID,user=Depends(current_user)): return run(lambda:workflows.get(user,identifier))

    @router.post('/teaching-workflows/{identifier}/questions')
    def questions(identifier:UUID,data:AdoptQuestions,user=Depends(current_user)):
        return run(lambda:workflows.adopt_questions(user,identifier,data))

    @router.post('/teaching-workflows/{identifier}/course-content')
    def course(identifier:UUID,data:AdoptCourse,user=Depends(current_user)):
        return run(lambda:workflows.adopt_course(user,identifier,data))

    @router.post('/teaching-workflows/{identifier}/schedule')
    def schedule(identifier:UUID,data:AdoptSchedule,user=Depends(current_user)):
        return run(lambda:workflows.adopt_schedule(user,identifier,data))

    @router.post('/teaching-workflows/{identifier}/schedule-preview')
    def revise_schedule(identifier:UUID,data:ReviseSchedule,user=Depends(current_user)):
        return run(lambda:workflows.revise_schedule(user,identifier,data))

    @router.get('/questions/{question_id}/source')
    def source(question_id:UUID,user=Depends(current_user)):
        return run(lambda:workflows.question_source(user,question_id))
    return router
