from datetime import datetime,timezone
from uuid import UUID
from fastapi import APIRouter,Depends,Request,Response,HTTPException,Query
from sqlalchemy import select
from app.auth import _utc
from app.models import AuthSession,User,AuditLog
from app.pagination import sql_page

def session_router(auth_provider,current_user):
    r=APIRouter(prefix='/api/v1/auth')
    @r.post('/refresh')
    def refresh(request:Request,response:Response):
        auth=auth_provider();principal,sid=auth.cookie_principal(request,response)
        if not principal:raise HTTPException(401,'登录已结束，请重新登录。')
        return dict(browser_session=sid,user=dict(id=principal.id,username=principal.username,display_name=principal.display_name,role=principal.role,role_label=principal.role_label))
    @r.post('/logout')
    def logout(request:Request,response:Response):
        auth=auth_provider();token=request.headers.get('authorization','').removeprefix('Bearer ').strip()
        if token.startswith('cookie-session:') or not token:
            p,sid=auth.cookie_principal(request,response,token.split(':',1)[1] if token else None)
            if p:auth.logout(session_id=sid)
        else:auth.logout(token=token)
        auth.clear_cookies(response);return dict(message='已退出登录。')
    @r.get('/sessions')
    def sessions(request:Request,response:Response,page:int=Query(1,ge=1),page_size:int=Query(6,ge=1,le=30),user=Depends(current_user)):
        auth=auth_provider()
        if auth._session_factory is None:raise HTTPException(503,'当前运行方式不支持设备管理。')
        token=request.headers.get('authorization','').removeprefix('Bearer ').strip()
        current=token.split(':',1)[1] if token.startswith('cookie-session:') else auth.token_session(token) if token else auth.cookie_principal(request,response)[1]
        with auth._session_factory() as s:
            q=select(AuthSession).where(AuthSession.user_id==UUID(user.id),AuthSession.session_version==user.session_version).order_by(AuthSession.created_at.desc())
            def view(row):return dict(id=str(row.id),label=row.label,created_at=row.created_at,last_seen_at=row.last_seen_at,expires_at=row.expires_at,
                current=str(row.id)==current,active=not row.revoked_at and _utc(row.expires_at)>datetime.now(timezone.utc))
            return sql_page(s,q,page=page,page_size=page_size,mapper=view)
    @r.delete('/sessions/{session_id}')
    def revoke(session_id:UUID,user=Depends(current_user)):
        auth=auth_provider()
        if auth._session_factory is None:raise HTTPException(503,'当前运行方式不支持设备管理。')
        with auth._session_factory.begin() as s:
            row=s.scalar(select(AuthSession).where(AuthSession.id==session_id,AuthSession.user_id==UUID(user.id)).with_for_update())
            if not row:raise HTTPException(404,'会话不存在。')
            row.revoked_at=datetime.now(timezone.utc)
            s.add(AuditLog(actor_id=UUID(user.id),actor_name=user.display_name,action='revoke_session',resource_type='auth_session',resource_id=str(row.id),detail={}))
        return dict(message='该设备会话已结束。')
    return r
