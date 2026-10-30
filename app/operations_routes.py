import csv
import io
import json
from datetime import datetime,timedelta,timezone
from typing import Literal
from uuid import UUID
from fastapi import APIRouter,Depends,HTTPException,Query,Response
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel
from sqlalchemy import select
from app.models import AuditLog,Assignment,AssignmentSubmission,SubmissionReview,User,LoginAttempt,RequestLog
from app.evaluation_tasks import DATASETS

def csv_response(columns,rows,filename):
    if len(rows)>10000:raise HTTPException(422,'结果超过一万行，请缩小筛选范围后导出。')
    def safe(value):
        if value is None:return ''
        if isinstance(value,(list,dict)):value=json.dumps(value,ensure_ascii=False)
        if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@','\t','\r')):return "'"+value
        return value
    output=io.StringIO();writer=csv.writer(output);writer.writerow([label for _,label in columns])
    writer.writerows([[safe(row.get(key)) for key,_ in columns] for row in rows])
    return Response('\ufeff'+output.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="{filename}.csv"','Cache-Control':'no-store'})

class EvaluationCreate(BaseModel):
    request_id:UUID
    dataset:Literal['dsa','osnet','http','memory']

def operations_router(service,evaluations,sessions,current_user,require_manager,cohort):
    r=APIRouter(prefix='/api/v1')
    def admin(user=Depends(current_user)):
        if user.role!='admin':raise HTTPException(403,'仅管理员可使用评测与日志导出。')
        if service is None:raise HTTPException(503,'此功能需要持久化数据库。')
        return user
    @r.get('/admin/evaluation-datasets')
    def datasets(user=Depends(admin)):return [{'id':k,'name':v[0]} for k,v in DATASETS.items()]
    @r.post('/admin/evaluation-tasks',status_code=202)
    def create(body:EvaluationCreate,user=Depends(admin)):
        try:return service.create(user,body.request_id,body.dataset)
        except ValueError as e:raise HTTPException(409,str(e))
    @r.get('/admin/evaluation-tasks')
    def tasks(page:int=Query(1,ge=1),page_size:int=Query(6,ge=1,le=30),user=Depends(admin)):return service.page(page,page_size)
    @r.get('/admin/evaluation-tasks/{task_id}')
    def task(task_id:UUID,user=Depends(admin)):
        row=service.get(task_id)
        if not row:raise HTTPException(404,'任务不存在。')
        return row
    @r.post('/admin/evaluation-tasks/{task_id}/cancel')
    def cancel(task_id:UUID,user=Depends(admin)):
        try:return service.cancel(task_id,user)
        except ValueError as e:raise HTTPException(404,str(e))
    @r.get('/admin/evaluation-compare')
    def compare(ids:str=Query(...,max_length=120),user=Depends(admin)):
        try:keys=[UUID(i) for i in ids.split(',')]
        except ValueError:raise HTTPException(422,'评测编号无效。')
        if not 2<=len(set(keys))<=3:raise HTTPException(422,'请选择两到三份不同报告。')
        runs=[evaluations.get(i) for i in keys]
        if not all(runs):raise HTTPException(404,'报告不存在。')
        versions={(i['dataset_version'],i['metrics'].get('dataset_sha256'),i['metrics'].get('source_fingerprint'),i['metrics'].get('gate_details',{}).get('policy'),json.dumps(i['metrics'].get('retrieval_config'),sort_keys=True)) for i in runs}
        comparable=len(versions)==1 and all(i['metrics'].get('source_fingerprint') and i['metrics'].get('dataset_sha256') and i['metrics'].get('retrieval_config') for i in runs)
        return dict(comparable=comparable,notice='题集、资料快照与质量标准一致，可比较。' if comparable else '题集、资料快照或质量标准不同，仅并列查看，不据此判定提升。',runs=[{k:v for k,v in i.items() if k!='details'} for i in runs])
    @r.get('/admin/evaluations/{run_id}/download')
    def download(run_id:UUID,format:Literal['json','csv']='json',user=Depends(admin)):
        run=evaluations.get(run_id)
        if not run:raise HTTPException(404,'报告不存在。')
        if format=='csv':return csv_response([('id','用例'),('question','问题'),('kind','类型'),('accepted','接受'),('expected_documents','预期资料'),('retrieved_documents','检索资料'),('retrieved_pages','页码'),('expected_rank','正确排名'),('latency_ms','耗时ms')],run['details'],'evaluation-'+str(run_id))
        return Response(json.dumps(jsonable_encoder(run),ensure_ascii=False,indent=2),media_type='application/json',headers={'Content-Disposition':f'attachment; filename="evaluation-{run_id}.json"','Cache-Control':'no-store'})
    @r.get('/courses/{course_id}/exports/{kind}')
    def export_course(course_id:UUID,kind:Literal['grades','analytics'],search:str=Query('',max_length=100),
                      attention:Literal['all','overdue','low_score','ungraded','no_grades']='all',user=Depends(current_user)):
        if user.role not in ('teacher','admin'):raise HTTPException(403,'仅教师与管理员可导出课程数据。')
        require_manager(course_id,user)
        if kind=='analytics':
            result=cohort.student_page(course_id,actor_id=UUID(user.id),role=user.role,page=1,page_size=10001,search=search,attention=attention)
            if result is None:raise HTTPException(404,'课程不存在。')
            return csv_response([('student_name','姓名'),('username','账号'),('submission_count','已提交'),('missing_count','未提交'),('overdue_missing_count','逾期未交'),('pending_count','待批改'),('average_score','平均成绩百分比'),('weak_points','薄弱知识点')],result['items'],'course-analytics-'+str(course_id))
        with sessions() as s:
            q=select(AssignmentSubmission,Assignment.title,User.display_name,User.username,SubmissionReview).join(Assignment,Assignment.id==AssignmentSubmission.assignment_id).join(User,User.id==AssignmentSubmission.student_id).outerjoin(SubmissionReview,SubmissionReview.submission_id==AssignmentSubmission.id).where(Assignment.course_id==course_id)
            if search.strip():q=q.where((User.display_name.icontains(search.strip(),autoescape=True))|(User.username.icontains(search.strip(),autoescape=True))|(Assignment.title.icontains(search.strip(),autoescape=True)))
            data=s.execute(q.order_by(Assignment.id,User.username,AssignmentSubmission.id).limit(10001)).all()
            rows=[dict(assignment=title,name=name,username=username,status=sub.status,score=(review.score if review else sub.score) if sub.status=='graded' else None,max_score=sub.max_score,submitted_at=sub.submitted_at.isoformat()) for sub,title,name,username,review in data]
        return csv_response([('assignment','作业'),('name','姓名'),('username','账号'),('status','状态'),('score','已批改分数'),('max_score','满分'),('submitted_at','提交时间')],rows,'course-grades-'+str(course_id))
    @r.get('/admin/exports/{kind}')
    def export_audits(kind:Literal['audits','logins','requests'],days:int=Query(7,ge=1,le=90),search:str=Query('',max_length=100),user=Depends(admin)):
        with sessions() as s:
            cutoff=datetime.now(timezone.utc)-timedelta(days=days)
            if kind=='logins':
                q=select(LoginAttempt).where(LoginAttempt.created_at>=cutoff)
                if search.strip():q=q.where(LoginAttempt.username.icontains(search.strip(),autoescape=True))
                rows=[dict(created_at=i.created_at.isoformat(),username=i.username,ip=i.ip_address,successful=i.successful)for i in s.scalars(q.order_by(LoginAttempt.created_at.desc(),LoginAttempt.id.desc()).limit(10001))]
                return csv_response([('created_at','时间'),('username','账号'),('ip','访问地址'),('successful','登录成功')],rows,'login-logs')
            if kind=='requests':
                q=select(RequestLog).where(RequestLog.created_at>=cutoff)
                if search.strip():q=q.where((RequestLog.path.icontains(search.strip(),autoescape=True))|(RequestLog.method.icontains(search.strip(),autoescape=True)))
                rows=[dict(created_at=i.created_at.isoformat(),request_id=i.request_id,method=i.method,path=i.path,status=i.status_code,duration=i.duration_ms)for i in s.scalars(q.order_by(RequestLog.created_at.desc(),RequestLog.id.desc()).limit(10001))]
                return csv_response([('created_at','时间'),('request_id','请求编号'),('method','请求方法'),('path','路径'),('status','状态码'),('duration','耗时ms')],rows,'request-logs')
            q=select(AuditLog).where(AuditLog.created_at>=datetime.now(timezone.utc)-timedelta(days=days))
            if search.strip():q=q.where((AuditLog.actor_name.icontains(search.strip(),autoescape=True))|(AuditLog.action.icontains(search.strip(),autoescape=True)))
            rows=[dict(created_at=i.created_at.isoformat(),actor=i.actor_name,action=i.action,resource_type=i.resource_type,resource_id=i.resource_id) for i in s.scalars(q.order_by(AuditLog.created_at.desc(),AuditLog.id.desc()).limit(10001))]
        return csv_response([('created_at','时间'),('actor','操作人'),('action','操作'),('resource_type','对象类型'),('resource_id','对象编号')],rows,'audit-logs')
    return r
