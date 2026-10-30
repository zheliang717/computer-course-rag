from datetime import timedelta
from uuid import UUID
import os
import pytest
from fastapi import FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from app.database import Base
from app.models import User, Course, CourseEnrollment, AuditLog
from app.auth import AuthService, hash_password, principal_from_user, REMEMBER_LOGIN_SECONDS
from app.accounts import AccountService, now
from app.account_models import RegistrationPolicy, AccessInvite, PasswordRecovery, PasswordReset
from app.account_routes import account_router, Register, Invite, Password, Policy

PASS='a memorable test phrase 2026'


@pytest.fixture
def setup():
    database_url=os.environ.get('ACCOUNT_TEST_DATABASE_URL','')
    if database_url:
        from sqlalchemy.engine import make_url
        # Explicit disposable DB only; never run fixture teardown against application data.
        assert make_url(database_url).database in {'rag_accounts_ux14_check','rag_r1_tests_20261028','rag_today_concurrency_20261028'}
        engine=create_engine(database_url)
        Base.metadata.drop_all(engine)
    else:
        engine=create_engine('sqlite+pysqlite://',connect_args={'check_same_thread':False},poolclass=StaticPool)
    Base.metadata.create_all(engine)
    sessions=sessionmaker(bind=engine)
    with sessions.begin() as s:
        s.add(RegistrationPolicy(id=1,mode='invite',teacher_applications=True,version=1))
        a=User(username='admin_new',display_name='管理',role='admin',active=True,password_hash=hash_password(PASS),session_version=1)
        t=User(username='teacher_new',display_name='教师',role='teacher',active=True,password_hash=hash_password(PASS),session_version=1)
        s.add_all([a,t]);s.flush()
        c=Course(title='课程',code='NEW',owner_id=t.id,status='published');s.add(c);s.flush()
        actor,teacher,course=principal_from_user(a),principal_from_user(t),c.id
    service=AccountService(sessions)
    auth=AuthService(sessions,secret='test-only-secret',required=True)
    def user(authorization:str|None=Header(None)):
        p=auth.verify_token((authorization or '').removeprefix('Bearer '))
        if not p: raise HTTPException(401,'请登录')
        return p
    app=FastAPI(); app.include_router(account_router(service,user))
    yield service,sessions,actor,teacher,course,auth,TestClient(app)
    if database_url: Base.metadata.drop_all(engine)
    engine.dispose()


def reg(code='',username='new_student',**kw):
    return Register(username=username,display_name='新同学',password=PASS,invite_code=code,**kw)


def test_register_course_and_secret_storage(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    code=svc.create_invite(teacher,Invite(label='课程邀请',course_id=course,max_uses=1))['code']
    assert svc.preview(code)['course_title']=='课程'
    svc.register(reg(code))
    principal=auth.authenticate('new_student',PASS)
    assert principal.role=='student'
    with sessions() as s:
        assert s.scalar(select(CourseEnrollment).where(CourseEnrollment.user_id==UUID(principal.id)))
        inv=s.scalar(select(AccessInvite)); assert inv.uses==1 and inv.code_hash!=code
        assert code not in ''.join(str(r.detail) for r in s.scalars(select(AuditLog)))
    with pytest.raises(ValueError): svc.register(reg(code,username='second_student'))


def test_role_injection_and_permissions(setup):
    svc,_,admin,teacher,course,auth,client=setup
    assert client.post('/api/v1/auth/register',json={**reg().model_dump(),'role':'admin'}).status_code==422
    with pytest.raises(PermissionError): svc.create_invite(teacher,Invite(label='错误',kind='teacher'))
    invite=svc.create_invite(admin,Invite(label='教师邀请',kind='teacher',max_uses=1))
    svc.register(reg(invite['code'],username='invited_teacher'))
    assert auth.authenticate('invited_teacher',PASS).role=='teacher'
    assert client.get('/api/v1/accounts/manage/recoveries',headers={'Authorization':'Bearer '+auth.issue_token(teacher)}).status_code==403


def test_open_closed_and_teacher_review(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    with pytest.raises(ValueError): svc.register(reg())
    svc.save_policy(admin,Policy(mode='open',teacher_applications=True,version=1,confirmed=True))
    with pytest.raises(ValueError): svc.save_policy(admin,Policy(mode='open',teacher_applications=True,version=1,confirmed=True))
    svc.register(reg(teacher_reason='申请成为本平台课程教师'))
    p=auth.authenticate('new_student',PASS); old=auth.issue_token(p)
    row=svc.listing(admin,'applications',1,10)['items'][0]
    with pytest.raises(PermissionError): svc.review(teacher,'applications',UUID(row['id']),True,'已核实教师身份资料')
    svc.review(admin,'applications',UUID(row['id']),True,'已核实教师身份资料')
    assert auth.authenticate('new_student',PASS).role=='teacher' and auth.verify_token(old) is None
    svc.save_policy(admin,Policy(mode='closed',teacher_applications=True,version=2,confirmed=True))
    with pytest.raises(ValueError): svc.register(reg(username='blocked_student'))


def test_join_approval_duplicate_and_suspension(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    invite=svc.create_invite(teacher,Invite(label='需审核',course_id=course,approval_required=True))
    svc.register(reg(invite['code']))
    p=auth.authenticate('new_student',PASS)
    svc.join(p,invite['code'])
    with sessions() as s: assert s.scalar(select(AccessInvite)).uses==1
    request=svc.listing(teacher,'joins',1,10)['items'][0]
    svc.review(teacher,'joins',UUID(request['id']),True,'教师已核对学生选课信息')
    with sessions.begin() as s: s.scalar(select(CourseEnrollment)).status='inactive'
    with pytest.raises(ValueError): svc.join(p,invite['code'])
    svc.revoke_invite(teacher,UUID(invite['id']))
    with pytest.raises(ValueError): svc.preview(invite['code'])


def test_password_change_revokes_legacy_and_current_tokens(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    old=auth.issue_token(teacher)
    with pytest.raises(ValueError): svc.change_password(teacher,Password(current_password='wrong',new_password=PASS+'new'))
    assert auth.verify_token(old)
    svc.change_password(teacher,Password(current_password=PASS,new_password=PASS+'new'))
    assert auth.verify_token(old) is None
    assert auth.authenticate('teacher_new',PASS) is None
    assert auth.authenticate('teacher_new',PASS+'new')


@pytest.mark.parametrize('reason', ['password', 'disabled', 'session_version'])
def test_remembered_login_obeys_account_invalidation(setup, reason):
    svc,sessions,admin,teacher,course,auth,client=setup
    token=auth.issue_token(teacher, expires_in=REMEMBER_LOGIN_SECONDS)
    assert auth.verify_token(token)
    if reason == 'password':
        svc.change_password(teacher,Password(current_password=PASS,new_password=PASS+'new'))
    else:
        with sessions.begin() as s:
            user=s.get(User,UUID(teacher.id))
            if reason == 'disabled': user.active=False
            else: user.session_version+=1
    assert auth.verify_token(token) is None


def test_recovery_generic_single_use_and_disabled(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    assert svc.recover('teacher_new','通过本人线下核实联系')==svc.recover('unknown_user','通过本人线下核实联系')
    rows=svc.listing(admin,'recoveries',1,10)['items']
    known=next(r for r in rows if r['username']=='teacher_new')
    old=auth.issue_token(teacher)
    link=svc.issue_reset(admin,UUID(known['id']),'线下核实本人身份和账号')
    with sessions() as s: assert s.scalar(select(PasswordReset)).token_hash!=link['token']
    svc.reset(link['token'],PASS+'changed')
    assert auth.verify_token(old) is None
    with pytest.raises(ValueError): svc.reset(link['token'],PASS+'again')
    svc.recover('teacher_new','再次申请线下核实联系')
    row=next(r for r in svc.listing(admin,'recoveries',1,10,'pending')['items'] if r['username']=='teacher_new')
    link=svc.issue_reset(admin,UUID(row['id']),'线下再次核实本人身份和账号')
    with sessions.begin() as s: s.get(User,UUID(teacher.id)).active=False
    with pytest.raises(ValueError): svc.reset(link['token'],PASS+'disabled')


def test_failed_registration_rolls_back_and_pagination(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    inv=svc.create_invite(teacher,Invite(label='邀请',course_id=course))
    with pytest.raises(ValueError): svc.register(reg(inv['code'],teacher_reason='申请成为课程负责教师'))
    with sessions() as s:
        assert s.scalar(select(User).where(User.username=='new_student')) is None
        assert s.scalar(select(AccessInvite)).uses==0
    page=svc.listing(teacher,'invites',1,1)
    assert page['total']==1 and len(page['items'])==1 and 'code_hash' not in page['items'][0]


def test_challenge_after_failed_attempts_and_no_anonymous_management(setup):
    _,_,_,_,_,_,client=setup
    for _ in range(2): assert client.post('/api/v1/auth/register',json=reg().model_dump()).status_code==400
    result=client.post('/api/v1/auth/register',json=reg().model_dump())
    assert result.json()['detail']['challenge_required']
    challenge=client.get('/api/v1/auth/challenge').json()
    assert challenge['image'].startswith('data:image/svg+xml;base64,')
    assert client.get('/api/v1/accounts/manage/invites').status_code==401


def test_management_invite_states_search_and_draft_guard(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    for label in ['可用 100%_真实','到期邀请','已满邀请','撤销邀请','课程暂不可加入']:
        svc.create_invite(teacher,Invite(label=label,course_id=course))
    with sessions.begin() as s:
        rows={r.label:r for r in s.scalars(select(AccessInvite))}
        rows['到期邀请'].expires_at=now()-timedelta(seconds=1)
        rows['已满邀请'].uses=rows['已满邀请'].max_uses
        rows['撤销邀请'].revoked=True
        draft=Course(title='草稿',code='DRAFT',status='draft',owner_id=UUID(teacher.id));s.add(draft);s.flush()
        draft_id=draft.id
        rows['课程暂不可加入'].course_id=draft.id
    for state,label in [('active','可用 100%_真实'),('expired','到期邀请'),('exhausted','已满邀请'),('revoked','撤销邀请'),('unavailable','课程暂不可加入')]:
        data=svc.listing(admin,'invites',1,2,state)
        assert data['total']==1 and data['items'][0]['label']==label and data['items'][0]['state']==state
    assert svc.listing(admin,'invites',1,10,search='100%_')['total']==1
    assert svc.listing(admin,'invites',1,10,search='NEW')['total']==4
    assert svc.listing(admin,'invites',2,2)['total']==5
    with pytest.raises(ValueError): svc.create_invite(admin,Invite(label='不能发草稿邀请',course_id=draft_id))
    invited=svc.create_invite(admin,Invite(label='单人教师',kind='teacher',max_uses=20))
    row=svc.listing(admin,'invites',1,10,search='单人教师')['items'][0]
    assert row['max_uses']==1 and invited['code']
    headers={'Authorization':'Bearer '+auth.issue_token(admin)}
    assert client.get('/api/v1/accounts/manage/joins?status=expired',headers=headers).status_code==400
    assert client.get('/api/v1/accounts/manage/invites?search=100%25_',headers=headers).json()['total']==1


def test_management_review_receipts_and_scope(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    code=svc.create_invite(teacher,Invite(label='需审核',course_id=course,approval_required=True))['code']
    svc.register(reg(code))
    row=svc.listing(teacher,'joins',1,10,'pending',search='新同学')['items'][0]
    assert not row['approval_blocker']
    svc.review(teacher,'joins',UUID(row['id']),True,'已线下核对学生选课材料')
    receipt=svc.listing(admin,'joins',1,10,'approved')['items'][0]
    assert receipt['review_reason']=='已线下核对学生选课材料'
    assert receipt['reviewed_by']=='教师' and receipt['reviewed_at']
    with sessions.begin() as s:
        outsider=User(username='other_teacher',display_name='他课教师',role='teacher',active=True,password_hash=hash_password(PASS),session_version=1)
        s.add(outsider);s.flush();other=principal_from_user(outsider)
    assert svc.listing(other,'joins',1,10,search='新同学')['total']==0
    with pytest.raises(PermissionError): svc.listing(other,'applications',1,10)


def test_management_teacher_application_blocker_and_receipt(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    code=svc.create_invite(teacher,Invite(label='选课',course_id=course))['code']
    svc.register(reg(code))
    student=auth.authenticate('new_student',PASS)
    svc.apply_teacher(student,'本人准备承担相关课程教学工作')
    row=svc.listing(admin,'applications',1,10,'pending')['items'][0]
    assert '在学课程' in row['approval_blocker']
    with pytest.raises(ValueError): svc.review(admin,'applications',UUID(row['id']),True,'核实后尝试批准教师身份')
    svc.review(admin,'applications',UUID(row['id']),False,'请先处理当前学生课程身份')
    receipt=svc.listing(admin,'applications',1,10,'rejected')['items'][0]
    assert receipt['review_reason']=='请先处理当前学生课程身份' and receipt['reason']=='本人准备承担相关课程教学工作'


def test_management_reissue_reset_invalidates_old_link(setup):
    svc,sessions,admin,teacher,course,auth,client=setup
    svc.recover('teacher_new','本人申请重新核实账号密码')
    row=svc.listing(admin,'recoveries',1,10,'pending')['items'][0]
    old_login=auth.issue_token(teacher)
    first=svc.issue_reset(admin,UUID(row['id']),'通过预留联系方式核实本人')
    second=svc.issue_reset(admin,UUID(row['id']),'用户遗失链接再次核实本人')
    assert first['token']!=second['token'] and auth.verify_token(old_login)
    with pytest.raises(ValueError): svc.reset(first['token'],PASS+' old')
    receipt=svc.listing(admin,'recoveries',1,10,'resolved',search='teacher_new')['items'][0]
    assert receipt['review_reason']=='用户遗失链接再次核实本人'
    assert not any('token' in key for key in receipt)
    svc.reset(second['token'],PASS+' new')
    assert auth.verify_token(old_login) is None and auth.authenticate('teacher_new',PASS+' new')
    with pytest.raises(ValueError): svc.reset(second['token'],PASS+' reused')
    svc.recover('missing_user','不知道账号请协助核实身份')
    missing=svc.listing(admin,'recoveries',1,10,'pending')['items'][0]
    svc.review(admin,'recoveries',UUID(missing['id']),False,'未能匹配账号已告知申请人')
    assert svc.listing(admin,'recoveries',1,10,'rejected')['items'][0]['review_reason']=='未能匹配账号已告知申请人'
    with pytest.raises(ValueError): svc.issue_reset(admin,UUID(missing['id']),'不能重发已拒绝的申请链接')
