from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import UUID
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from app.auth import AuthService,hash_password
from app.models import User,AuthSession

@pytest.fixture
def setup(postgres_sessions,monkeypatch):
    from app import main
    with postgres_sessions.begin() as s:
        for name in ('session_a','session_b'):s.add(User(username=name,display_name=name,role='student',password_hash=hash_password('OnlyTest123!')))
    auth=AuthService(postgres_sessions,secret='browser-session-test',required=True)
    monkeypatch.setattr(main,'auth',auth);monkeypatch.setattr(main,'security_service',None)
    monkeypatch.setattr(main,'account_guard',SimpleNamespace(check=lambda *a:None,success=lambda *a:None,failed=lambda *a:None))
    return TestClient(main.app),auth,postgres_sessions

def login(c,name='session_a',remember=True):
    r=c.post('/api/v1/auth/login',json=dict(username=name,password='OnlyTest123!',remember_me=remember));assert r.status_code==200
    return r,r.json()

def test_http_only_refresh_fixed_expiry_and_logout_revokes_legacy_and_cookie(setup):
    c,auth,sessions=setup;r,data=login(c);sid=data['browser_session'];marker={'Authorization':'Bearer cookie-session:'+sid}
    assert all('HttpOnly' in v and 'SameSite=strict' in v for v in r.headers.get_list('set-cookie'))
    with sessions() as s:original=s.get(AuthSession,UUID(sid)).expires_at
    # Simulate short access expiry; refresh remains available to the browser.
    c.cookies.delete(auth.cookie_names[0]);assert c.get('/api/v1/auth/me',headers=marker).status_code==200
    assert auth.cookie_names[0] in c.cookies
    with sessions() as s:assert s.get(AuthSession,UUID(sid)).expires_at==original
    assert c.get('/api/v1/auth/sessions',headers=marker).json()['items'][0]['current']
    assert c.post('/api/v1/auth/logout',headers=marker).status_code==200
    assert c.post('/api/v1/auth/refresh').status_code==401
    assert c.get('/api/v1/auth/me',headers={'Authorization':'Bearer '+data['access_token']}).status_code==401

def test_cross_account_marker_and_device_revocation_are_rejected(setup):
    c,auth,sessions=setup;_,a=login(c);_,b=login(c,'session_b')
    assert c.get('/api/v1/auth/me',headers={'Authorization':'Bearer cookie-session:'+a['browser_session']}).status_code==401
    marker={'Authorization':'Bearer cookie-session:'+b['browser_session']}
    assert c.delete('/api/v1/auth/sessions/'+a['browser_session'],headers=marker).status_code==404
    assert c.delete('/api/v1/auth/sessions/'+b['browser_session'],headers=marker).status_code==200
    assert c.post('/api/v1/auth/refresh').status_code==401
    assert auth.verify_token(a['access_token'])

def test_expired_refresh_and_invalid_bearer_do_not_fall_back_to_cookie(setup):
    c,auth,sessions=setup;_,a=login(c)
    assert c.get('/api/v1/auth/me',headers={'Authorization':'Bearer invalid'}).status_code==401
    with sessions.begin() as s:s.get(AuthSession,UUID(a['browser_session'])).expires_at=datetime.now(timezone.utc)-timedelta(seconds=1)
    assert c.post('/api/v1/auth/refresh').status_code==401
    other=AuthService(sessions,secret='another-environment',required=True)
    assert other.cookie_names!=auth.cookie_names
