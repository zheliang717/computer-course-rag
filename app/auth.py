"""Small self-contained local authentication service for the single-node demo."""

import base64
import hashlib
import hmac
import json
import secrets
import time
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID,uuid4
from datetime import datetime,timedelta,timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User,AuthSession,RevokedAuthToken


ROLE_LABELS = {"admin": "管理员", "teacher": "教师", "student": "学生"}
LOGIN_SECONDS = 8 * 60 * 60
REMEMBER_LOGIN_SECONDS = 7 * 24 * 60 * 60
DEFAULT_USERS = (
    ("admin", "管理员", "admin", "admin123"),
    ("teacher", "教师演示账号", "teacher", "teacher123"),
    ("student", "学生演示账号", "student", "student123"),
)


@dataclass(frozen=True)
class Principal:
    id: str
    username: str
    display_name: str
    role: str
    session_version: int = 1

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    rounds = 180_000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, rounds)
    return f"pbkdf2_sha256${rounds}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds_text, salt_hex, digest_hex = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        expected = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), int(rounds_text)
        ).hex()
        return hmac.compare_digest(expected, digest_hex)
    except (TypeError, ValueError):
        return False


def principal_from_user(user: User) -> Principal:
    return Principal(id=str(user.id), username=user.username, display_name=user.display_name, role=user.role, session_version=user.session_version)


class AuthService:
    def __init__(self, session_factory: Callable[[], Session] | None, *, secret: str, required: bool) -> None:
        self._session_factory = session_factory
        self._secret = secret.encode("utf-8")
        self.required = required
        self._revoked_memory={}
        self._memory_users = {
            username: Principal(id=f"demo-{username}", username=username, display_name=display_name, role=role)
            for username, display_name, role, _ in DEFAULT_USERS
        }
        self._memory_passwords = {username: password for username, _, _, password in DEFAULT_USERS}

    def ensure_defaults(self) -> None:
        if self._session_factory is None:
            return
        with self._session_factory() as session:
            for username, display_name, role, password in DEFAULT_USERS:
                user = session.scalar(select(User).where(User.username == username))
                if user is None:
                    session.add(
                        User(
                            username=username,
                            display_name=display_name,
                            role=role,
                            password_hash=hash_password(password),
                            active=True,
                        )
                    )
            session.commit()

    def authenticate(self, username: str, password: str) -> Principal | None:
        normalized = username.strip().lower()
        if self._session_factory is None:
            principal = self._memory_users.get(normalized)
            return principal if principal and hmac.compare_digest(self._memory_passwords[normalized], password) else None
        with self._session_factory() as session:
            user = session.scalar(select(User).where(User.username == normalized, User.active.is_(True)))
            if user is None or not verify_password(password, user.password_hash):
                return None
            return principal_from_user(user)

    def issue_token(self, principal: Principal, *, expires_in: int = LOGIN_SECONDS, session_id=None) -> str:
        if self._session_factory is not None and session_id is None:
            session_id=uuid4()
            with self._session_factory.begin() as session:
                session.add(AuthSession(id=session_id,user_id=UUID(principal.id),session_version=principal.session_version,
                    label='兼容接口会话',expires_at=datetime.now(timezone.utc)+timedelta(seconds=expires_in)))
        payload = {
            "sub": principal.id,
            "username": principal.username,
            "display_name": principal.display_name,
            "role": principal.role,
            "ver": principal.session_version,
            "exp": int(time.time()) + expires_in,
        }
        if session_id:payload['sid']=str(session_id)
        encoded = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        signature = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded}.{_b64(signature)}"

    def verify_token(self, token: str) -> Principal | None:
        try:
            if len(token)>8192 or hashlib.sha256(token.encode()).hexdigest() in self._revoked_memory:return None
            encoded, signature = token.split(".", 1)
            expected = hmac.new(self._secret, encoded.encode("ascii"), hashlib.sha256).digest()
            if not hmac.compare_digest(_unb64(signature), expected):
                return None
            payload = json.loads(_unb64(encoded).decode("utf-8"))
            if int(payload["exp"]) <= int(time.time()):
                return None
            if self._session_factory is not None:
                with self._session_factory() as session:
                    revoked=session.get(RevokedAuthToken,hashlib.sha256(token.encode()).hexdigest())
                    if revoked:return None
                    user = session.get(User, UUID(str(payload["sub"])))
                    if user is None or not user.active or int(payload.get('ver', 1)) != user.session_version:
                        return None
                    if payload.get('sid'):
                        device=session.get(AuthSession,UUID(payload['sid']))
                        if not device or device.user_id!=user.id or device.revoked_at or _utc(device.expires_at)<=datetime.now(timezone.utc) or device.session_version!=user.session_version:return None
                    return principal_from_user(user)
            return Principal(
                id=str(payload["sub"]),
                username=str(payload["username"]),
                display_name=str(payload["display_name"]),
                role=str(payload["role"]),
            )
        except (KeyError, TypeError, ValueError, UnicodeDecodeError, json.JSONDecodeError):
            return None

    @property
    def cookie_names(self):
        suffix=hashlib.sha256(self._secret).hexdigest()[:12]
        return 'rag_access_'+suffix,'rag_refresh_'+suffix

    def token_session(self,token):
        if not self.verify_token(token):return None
        return json.loads(_unb64(token.split('.')[0])).get('sid')

    def browser_login(self,principal,lifetime,request,response):
        legacy=self.issue_token(principal,expires_in=lifetime)
        if self._session_factory is None:return legacy,None
        sid=self.token_session(legacy);refresh=secrets.token_urlsafe(40)
        with self._session_factory.begin() as s:
            row=s.get(AuthSession,UUID(sid));row.refresh_hash=hashlib.sha256(refresh.encode()).hexdigest()
            row.label=(request.headers.get('user-agent') or '浏览器')[:200]
        self._set_cookies(response,request,self.issue_token(principal,expires_in=900,session_id=sid),refresh,lifetime)
        return legacy,sid

    def _set_cookies(self,response,request,access,refresh=None,lifetime=None):
        secure=request.url.scheme=='https' or request.headers.get('x-forwarded-proto')=='https'
        access_name,refresh_name=self.cookie_names
        response.set_cookie(access_name,access,max_age=900,httponly=True,secure=secure,samesite='strict',path='/api/v1')
        if refresh is not None:response.set_cookie(refresh_name,refresh,max_age=lifetime,httponly=True,secure=secure,samesite='strict',path='/api/v1')

    def cookie_principal(self,request,response,expected_sid=None):
        if self._session_factory is None:return None,None
        access_name,refresh_name=self.cookie_names;access=request.cookies.get(access_name,'')
        p=self.verify_token(access) if access else None
        if p:
            sid=self.token_session(access)
            return (p,sid) if not expected_sid or sid==expected_sid else (None,None)
        refresh=request.cookies.get(refresh_name,'')
        if not refresh:return None,None
        with self._session_factory.begin() as s:
            row=s.scalar(select(AuthSession).where(AuthSession.refresh_hash==hashlib.sha256(refresh.encode()).hexdigest()).with_for_update())
            if not row or row.revoked_at or _utc(row.expires_at)<=datetime.now(timezone.utc) or (expected_sid and str(row.id)!=expected_sid):return None,None
            user=s.get(User,row.user_id)
            if not user or not user.active or user.session_version!=row.session_version:return None,None
            row.last_seen_at=datetime.now(timezone.utc);p=principal_from_user(user);sid=str(row.id)
            remaining=max(1,int((_utc(row.expires_at)-datetime.now(timezone.utc)).total_seconds()))
        self._set_cookies(response,request,self.issue_token(p,expires_in=min(900,remaining),session_id=sid))
        return p,sid

    def logout(self,token='',session_id=None):
        p=self.verify_token(token) if token and not session_id else None
        if p:session_id=self.token_session(token)
        if self._session_factory is not None:
            with self._session_factory.begin() as s:
                if session_id:
                    row=s.get(AuthSession,UUID(session_id))
                    if row:row.revoked_at=datetime.now(timezone.utc)
                elif p:
                    payload=json.loads(_unb64(token.split('.')[0]));key=hashlib.sha256(token.encode()).hexdigest()
                    if not s.get(RevokedAuthToken,key):s.add(RevokedAuthToken(token_hash=key,expires_at=datetime.fromtimestamp(payload['exp'],timezone.utc)))
        elif p:self._revoked_memory[hashlib.sha256(token.encode()).hexdigest()]=True

    def clear_cookies(self,response):
        for name in self.cookie_names:response.delete_cookie(name,path='/api/v1',httponly=True,samesite='strict')

def _utc(value):return value.replace(tzinfo=timezone.utc) if not value.tzinfo else value


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
