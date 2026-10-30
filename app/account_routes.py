"""Bounded account endpoints, independent of teaching and model generation."""
import base64
import secrets
import time
from threading import Lock
from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from app.accounts import AccountService, digest
from app.security import SlidingWindowRateLimiter
from app.avatars import AvatarConflict, MAX_AVATAR_TEXT


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class ChallengeInput(Input):
    challenge_id: str = Field(default='',max_length=80)
    challenge_answer: str = Field(default='',max_length=12)


class Register(ChallengeInput):
    username: str = Field(min_length=3,max_length=80,pattern=r'^[A-Za-z0-9][A-Za-z0-9_.-]{2,79}$')
    display_name: str = Field(min_length=1,max_length=120)
    password: str = Field(min_length=15,max_length=200)
    invite_code: str = Field(default='',max_length=80)
    teacher_reason: str = Field(default='',max_length=1000)

    @field_validator('display_name')
    @classmethod
    def name_not_blank(cls,v):
        if not v.strip(): raise ValueError('请填写姓名。')
        return v.strip()


class Code(Input):
    code: str = Field(min_length=1,max_length=80)


class Invite(Input):
    label: str = Field(min_length=1,max_length=120)
    kind: Literal['student','teacher']='student'
    course_id: UUID | None=None
    approval_required: bool=False
    max_uses: int=Field(default=30,ge=1,le=500)
    days: int=Field(default=7,ge=1,le=90)

    @field_validator('label')
    @classmethod
    def nonempty(cls,v):
        if not v.strip(): raise ValueError('请填写邀请用途。')
        return v.strip()


class Profile(Input):
    display_name: str=Field(min_length=1,max_length=120)
    contact: str=Field(default='',max_length=200)
    _name=field_validator('display_name')(Register.name_not_blank.__func__)


class Avatar(Input):
    image: str | None = Field(..., max_length=MAX_AVATAR_TEXT)
    expected_revision: UUID | None = Field(...)


class Password(ChallengeInput):
    current_password: str=Field(min_length=1,max_length=200)
    new_password: str=Field(min_length=15,max_length=200)


class Recover(ChallengeInput):
    username: str=Field(min_length=1,max_length=80)
    note: str=Field(min_length=5,max_length=500)


class Reset(ChallengeInput):
    token: str=Field(min_length=20,max_length=100)
    password: str=Field(min_length=15,max_length=200)


class Reason(Input):
    reason: str=Field(min_length=8,max_length=500)

    @field_validator('reason')
    @classmethod
    def meaningful(cls, value):
        if len(value.strip()) < 8: raise ValueError('请填写至少8个有效字符的核实或申请说明。')
        return value.strip()


class Review(Reason):
    approved: bool
    confirmed: bool


class Policy(Input):
    mode: Literal['closed','invite','open']
    teacher_applications: bool
    version: int=Field(ge=1)
    confirmed: bool


class ResetIssue(Reason):
    identity_verified: bool


class AccountGuard:
    """Single-node abuse guard; challenges are supplementary, not proof of identity."""
    def __init__(self):
        self.limiter=SlidingWindowRateLimiter()
        self.failures={}
        self.challenges={}
        self.lock=Lock()

    def check(self,key,data):
        allowed,_,retry=self.limiter.check(key,limit=20)
        if not allowed: raise HTTPException(429,'操作过于频繁，请稍后重试。',headers={'Retry-After':str(retry)})
        with self.lock:
            count,expiry=self.failures.get(key,(0,0))
            required=count>=2 and expiry>time.monotonic()
            if required:
                item=self.challenges.pop(data.challenge_id,None)
                if not item or item[0]<time.monotonic() or item[1]!=digest(data.challenge_answer.strip().upper()):
                    raise HTTPException(400,detail={'message':'请完成图形验证后再试。','challenge_required':True})

    def failed(self,key):
        with self.lock:
            if len(self.failures)>10000: self.failures={k:v for k,v in self.failures.items() if v[1]>time.monotonic()}
            count,expiry=self.failures.get(key,(0,0))
            self.failures[key]=((count if expiry>time.monotonic() else 0)+1,time.monotonic()+900)

    def success(self,key):
        with self.lock: self.failures.pop(key,None)

    def image(self):
        answer=''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(5))
        ident=secrets.token_urlsafe(20)
        with self.lock:
            self.challenges={k:v for k,v in self.challenges.items() if v[0]>time.monotonic()}
            if len(self.challenges)>1000: raise HTTPException(429,'验证请求较多，请稍后刷新。')
            self.challenges[ident]=(time.monotonic()+300,digest(answer))
        letters=''.join(f'<text x="{18+i*29}" y="34" transform="rotate({secrets.randbelow(25)-12} {18+i*29} 34)" fill="#{secrets.choice(["315fa5","6650a1","2c7c81"])}">{c}</text>' for i,c in enumerate(answer))
        lines=''.join(f'<path d="M0 {secrets.randbelow(48)} Q80 {secrets.randbelow(48)} 180 {secrets.randbelow(48)}" stroke="#a6b8d2" fill="none"/>' for _ in range(5))
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="180" height="50"><rect width="180" height="50" rx="8" fill="#edf3fd"/>{lines}<g font-family="monospace" font-size="27" font-weight="bold">{letters}</g></svg>'
        return {'id':ident,'image':'data:image/svg+xml;base64,'+base64.b64encode(svg.encode()).decode()}


def account_router(service: AccountService | None, current_user, guard=None):
    router=APIRouter(prefix='/api/v1')
    guard=guard or AccountGuard()

    def svc():
        if not service: raise HTTPException(503,'账号注册需要持久化数据库，当前环境暂不可用。')
        return service

    def perform(fn):
        try: return fn()
        except AvatarConflict as exc: raise HTTPException(409, str(exc)) from exc
        except IntegrityError as exc: raise HTTPException(409,'记录已发生变化，本次操作未保存，请刷新核对后再试。') from exc
        except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
        except ValueError as exc: raise HTTPException(400,str(exc)) from exc

    def protected(request,data,kind,fn):
        key=f'{kind}:{request.client.host if request.client else "unknown"}'
        guard.check(key,data)
        try: result=perform(fn)
        except HTTPException:
            guard.failed(key)
            raise
        guard.success(key)
        return result

    @router.get('/auth/registration-policy')
    def policy(): return svc().policy()

    @router.get('/auth/challenge')
    def challenge(): return guard.image()

    @router.post('/auth/invite-preview')
    def preview(data:Code): return perform(lambda:svc().preview(data.code))

    @router.post('/auth/register',status_code=201)
    def register(data:Register,request:Request): return protected(request,data,'register',lambda:svc().register(data))

    @router.post('/auth/recover')
    def recover(data:Recover,request:Request): return protected(request,data,'recover',lambda:svc().recover(data.username,data.note))

    @router.post('/auth/reset-password')
    def reset(data:Reset,request:Request):
        protected(request,data,'reset',lambda:svc().reset(data.token,data.password))
        return {'message':'密码已重置，旧登录状态已失效，请使用新密码登录。'}

    @router.get('/accounts/profile')
    def profile(user=Depends(current_user)): return perform(lambda:svc().profile(user))

    @router.patch('/accounts/profile')
    def edit(data:Profile,user=Depends(current_user)): return perform(lambda:svc().update_profile(user,data))

    @router.get('/accounts/avatar')
    def avatar(user=Depends(current_user)):
        from fastapi.responses import JSONResponse
        return JSONResponse(perform(lambda:svc().avatar(user)), headers={'Cache-Control':'private, no-store'})

    @router.put('/accounts/avatar')
    def save_avatar(data:Avatar,user=Depends(current_user)):
        allowed, _, retry = guard.limiter.check('avatar:' + user.id, limit=20)
        if not allowed:
            raise HTTPException(429, '更换头像过于频繁，请稍后再试。', headers={'Retry-After':str(retry)})
        from fastapi.responses import JSONResponse
        return JSONResponse(perform(lambda:svc().save_avatar(user, data.image, data.expected_revision)), headers={'Cache-Control':'private, no-store'})

    @router.post('/accounts/password')
    def password(data:Password,request:Request,user=Depends(current_user)):
        protected(request,data,'password:'+user.id,lambda:svc().change_password(user,data))
        return {'message':'密码已修改，所有旧登录状态已失效，请重新登录。'}

    @router.post('/accounts/join-course')
    def join(data:Code,user=Depends(current_user)): return perform(lambda:svc().join(user,data.code))

    @router.post('/accounts/teacher-application')
    def apply(data:Reason,user=Depends(current_user)):
        perform(lambda:svc().apply_teacher(user,data.reason))
        return {'message':'教师申请已提交，审核前权限保持不变。'}

    @router.get('/accounts/manage/{kind}')
    def listing(kind:Literal['invites','applications','recoveries','joins'],page:int=Query(1,ge=1),page_size:int=Query(10,ge=1,le=50),status:Literal['pending','approved','rejected','resolved','active','expired','exhausted','revoked','unavailable']|None=None,search:str=Query('',max_length=120),user=Depends(current_user)):
        return perform(lambda:svc().listing(user,kind,page,page_size,status,search))

    @router.post('/accounts/invites',status_code=201)
    def invite(data:Invite,user=Depends(current_user)): return perform(lambda:svc().create_invite(user,data))

    @router.post('/accounts/invites/{invite_id}/revoke')
    def revoke(invite_id:UUID,user=Depends(current_user)):
        perform(lambda:svc().revoke_invite(user,invite_id))
        return {'message':'邀请已撤销，原链接不能再使用。'}

    @router.patch('/accounts/registration-policy')
    def save_policy(data:Policy,user=Depends(current_user)):
        if not data.confirmed: raise HTTPException(400,'请确认注册范围的变更。')
        return perform(lambda:svc().save_policy(user,data))

    @router.post('/accounts/manage/{kind}/{item_id}/review')
    def review(kind:Literal['applications','joins','recoveries'],item_id:UUID,data:Review,user=Depends(current_user)):
        if not data.confirmed: raise HTTPException(400,'请确认审核操作。')
        perform(lambda:svc().review(user,kind,item_id,data.approved,data.reason))
        return {'message':'申请已处理，请刷新查看最新状态。'}

    @router.post('/accounts/recoveries/{item_id}/reset-link')
    def issue(item_id:UUID,data:ResetIssue,user=Depends(current_user)):
        if not data.identity_verified: raise HTTPException(400,'请先通过线下可信方式核实申请人的身份。')
        return perform(lambda:svc().issue_reset(user,item_id,data.reason))

    return router
