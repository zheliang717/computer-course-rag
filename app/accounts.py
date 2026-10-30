"""Invitation-based onboarding and account lifecycle; no automatic privilege claims."""
from datetime import datetime, timedelta, timezone
import hashlib
import secrets
from uuid import UUID, uuid4
from sqlalchemy import select, update, or_, case
from sqlalchemy.exc import IntegrityError
from app.auth import hash_password, verify_password, principal_from_user
from app.models import User, Course, CourseEnrollment, AuditLog
from app.account_models import RegistrationPolicy, AccessInvite, CourseJoinRequest, TeacherApplication, PasswordRecovery, PasswordReset, UserAvatar
from app.avatars import AvatarConflict, avatar_state, normalize_avatar
from app.pagination import sql_page


def now(): return datetime.now(timezone.utc)
def utc(value): return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
def digest(value): return hashlib.sha256(value.encode()).hexdigest()
def normalize_code(value): return value.strip().replace('-', '').replace(' ', '').upper()


def validate_password(value):
    if not 15 <= len(value) <= 200 or not value.strip():
        raise ValueError('请使用15—200个字符的密码，可用容易记住的长句，不要求特殊符号。')
    if value.lower() in {'123456789012345', 'passwordpassword', '000000000000000'}:
        raise ValueError('这个密码过于常见，请换一个容易记住的长密码。')


class AccountService:
    def __init__(self, sessions): self.sessions = sessions

    @staticmethod
    def actor(s, principal, roles=None):
        user = s.scalar(select(User).where(User.id == UUID(principal.id)).with_for_update())
        if not user or not user.active or user.session_version != principal.session_version:
            raise PermissionError('登录状态已失效，请重新登录。')
        if roles and user.role not in roles: raise PermissionError('当前角色无权执行此操作。')
        return user

    @staticmethod
    def manager(s, user, course_id):
        course = s.get(Course, course_id)
        if not course or user.role not in {'admin', 'teacher'} or (user.role != 'admin' and course.owner_id != user.id):
            raise PermissionError('只能管理自己负责的课程。')
        return course

    @staticmethod
    def audit(s, actor, action, resource_id, **details):
        s.add(AuditLog(actor_id=actor.id if actor else None, actor_name=actor.display_name if actor else '账号注册', action=action,
                       resource_type='account_lifecycle', resource_id=str(resource_id), detail=details, created_at=now()))

    def policy(self):
        with self.sessions() as s:
            p = s.get(RegistrationPolicy, 1)
            return {'mode': p.mode if p else 'closed', 'teacher_applications': bool(p and p.teacher_applications), 'version': p.version if p else 0}

    def save_policy(self, principal, data):
        with self.sessions.begin() as s:
            actor = self.actor(s, principal, {'admin'})
            p = s.scalar(select(RegistrationPolicy).where(RegistrationPolicy.id == 1).with_for_update())
            if not p or p.version != data.version: raise ValueError('注册设置已更新，请刷新后重新确认。')
            p.mode, p.teacher_applications = data.mode, data.teacher_applications
            p.version += 1
            self.audit(s, actor, 'registration_policy', 1, mode=p.mode, teacher_applications=p.teacher_applications)
        return self.policy()

    @staticmethod
    def valid_invite(s, code, lock=False):
        q = select(AccessInvite).where(AccessInvite.code_hash == digest(normalize_code(code)))
        invite = s.scalar(q.with_for_update() if lock else q)
        if not invite or invite.revoked or utc(invite.expires_at) <= now() or invite.uses >= invite.max_uses:
            raise ValueError('邀请无效、已到期或名额已用完，请联系邀请人。')
        if invite.course_id:
            course = s.get(Course, invite.course_id)
            if not course or course.status != 'published': raise ValueError('该课程当前不能加入，请联系教师。')
        return invite

    def preview(self, code):
        with self.sessions() as s:
            inv = self.valid_invite(s, code)
            course = s.get(Course, inv.course_id) if inv.course_id else None
            teacher = s.get(User, course.owner_id) if course and course.owner_id else None
            return {'kind':inv.kind, 'label':inv.label, 'course_title':course.title if course else None,
                    'semester':course.semester if course else None, 'teacher':teacher.display_name if teacher else None,
                    'approval_required':inv.approval_required, 'expires_at':inv.expires_at}

    def create_invite(self, principal, data):
        with self.sessions.begin() as s:
            actor = self.actor(s, principal, {'teacher','admin'})
            if data.kind == 'teacher' and (actor.role != 'admin' or data.course_id): raise PermissionError('教师邀请只能由管理员创建，不能附带课程成员权限。')
            if data.course_id:
                course = self.manager(s, actor, data.course_id)
                if course.status != 'published': raise ValueError('请选择已发布课程，未发布或已归档课程不能创建选课邀请。')
            elif actor.role != 'admin': raise PermissionError('教师需选择自己负责的课程。')
            code = ''.join(secrets.choice('ABCDEFGHJKLMNPQRSTUVWXYZ23456789') for _ in range(12))
            item = AccessInvite(code_hash=digest(code), label=data.label.strip(), kind=data.kind, course_id=data.course_id,
                approval_required=bool(data.course_id and data.kind == 'student' and data.approval_required),
                max_uses=1 if data.kind == 'teacher' else data.max_uses, uses=0, expires_at=now()+timedelta(days=data.days), revoked=False, created_by=actor.id)
            s.add(item); s.flush()
            self.audit(s, actor, 'create_invite', item.id, kind=item.kind, course_id=str(item.course_id) if item.course_id else None)
            result = {'id':str(item.id),'code':code,'expires_at':item.expires_at}
        return result

    def revoke_invite(self, principal, invite_id):
        with self.sessions.begin() as s:
            actor = self.actor(s, principal, {'teacher','admin'})
            item = s.scalar(select(AccessInvite).where(AccessInvite.id == invite_id).with_for_update())
            if not item: raise ValueError('邀请不存在。')
            if actor.role != 'admin':
                if not item.course_id: raise PermissionError('无权撤销此邀请。')
                self.manager(s, actor, item.course_id)
            item.revoked=True
            self.audit(s, actor, 'revoke_invite', item.id)

    @staticmethod
    def attach(s, user, inv):
        if not inv.course_id: return '账号已就绪，可以在个人中心加入课程。'
        if user.role != 'student': raise ValueError('课程学习邀请仅适用于学生账号。')
        member = s.scalar(select(CourseEnrollment).where(CourseEnrollment.course_id == inv.course_id, CourseEnrollment.user_id == user.id))
        if member:
            if member.status != 'active': raise ValueError('该课程成员资格已停用，请联系教师处理。')
            return '你已经加入该课程。'
        request = s.scalar(select(CourseJoinRequest).where(CourseJoinRequest.course_id == inv.course_id, CourseJoinRequest.user_id == user.id).order_by(CourseJoinRequest.created_at.desc()))
        if request:
            if request.status == 'pending': return '加入课程的申请正在等待教师审核。'
            if request.status == 'rejected': raise ValueError('该课程申请未通过，请联系教师处理，不会自动重新开通。')
        if inv.approval_required:
            s.add(CourseJoinRequest(user_id=user.id, course_id=inv.course_id, status='pending'))
            return '账号已创建，加入课程的申请正在等待教师审核。'
        s.add(CourseEnrollment(course_id=inv.course_id, user_id=user.id, status='active'))
        return '已加入课程，可以开始学习。'

    def register(self, data):
        validate_password(data.password)
        try:
            with self.sessions.begin() as s:
                policy = s.scalar(select(RegistrationPolicy).where(RegistrationPolicy.id == 1).with_for_update())
                if not policy or policy.mode == 'closed': raise ValueError('当前暂不开放注册，请联系管理员。')
                inv = self.valid_invite(s, data.invite_code, True) if data.invite_code else None
                if policy.mode == 'invite' and not inv: raise ValueError('当前采用邀请注册，请填写邀请人提供的邀请码。')
                if data.teacher_reason and not policy.teacher_applications: raise ValueError('当前暂停教师申请。')
                if data.teacher_reason and len(data.teacher_reason.strip()) < 8: raise ValueError('请填写至少8个字符的教师申请说明。')
                if data.teacher_reason and inv and inv.course_id: raise ValueError('教师申请请使用平台邀请或联系管理员，不要使用课程学生邀请码。')
                username = data.username.strip().lower()
                if s.scalar(select(User.id).where(User.username == username)): raise ValueError('无法使用这个账号注册，请尝试其他账号或使用登录/找回入口。')
                user = User(username=username, display_name=data.display_name.strip(), role='teacher' if inv and inv.kind == 'teacher' else 'student',
                            password_hash=hash_password(data.password), active=True, session_version=1)
                s.add(user); s.flush()
                notice = '注册成功，请登录课程空间。'
                if inv:
                    notice = self.attach(s,user,inv)
                    inv.uses += 1
                if data.teacher_reason and user.role == 'student':
                    s.add(TeacherApplication(user_id=user.id,reason=data.teacher_reason.strip(),status='pending'))
                    notice += ' 教师身份申请已提交，审核前使用学生权限。'
                self.audit(s,user,'self_register',user.id,role=user.role,invite_id=str(inv.id) if inv else None)
            return {'message': notice, 'username':username}
        except IntegrityError as exc: raise ValueError('注册未完成，账号可能已被占用。请检查后重试或登录。') from exc

    def join(self, principal, code):
        with self.sessions.begin() as s:
            user = self.actor(s,principal,{'student'})
            inv = self.valid_invite(s,code,True)
            if inv.kind != 'student' or not inv.course_id: raise ValueError('请使用课程学习邀请码。教师身份需由管理员核实。')
            existing = s.scalar(select(CourseEnrollment).where(CourseEnrollment.user_id==user.id,CourseEnrollment.course_id==inv.course_id))
            pending = s.scalar(select(CourseJoinRequest.id).where(CourseJoinRequest.user_id==user.id,CourseJoinRequest.course_id==inv.course_id,CourseJoinRequest.status=='pending'))
            result = self.attach(s,user,inv)
            if not existing and not pending: inv.uses += 1
            self.audit(s,user,'join_course',inv.course_id)
            return {'message':result}

    def profile(self, principal):
        with self.sessions() as s:
            user = self.actor(s,principal)
            teacher = s.scalar(select(TeacherApplication).where(TeacherApplication.user_id==user.id))
            joins = s.execute(select(CourseJoinRequest,Course.title).join(Course,Course.id==CourseJoinRequest.course_id).where(CourseJoinRequest.user_id==user.id).order_by(CourseJoinRequest.created_at.desc()).limit(50)).all()
            return {'id':str(user.id),'username':user.username,'display_name':user.display_name,'role':user.role,'contact':user.contact or '',
                    'teacher_application': {'status':teacher.status,'reason':teacher.reason,'review_reason':teacher.review_reason} if teacher else None,
                    'course_requests':[{'id':str(r.id),'course_title':t,'status':r.status,'reason':r.reason} for r,t in joins]}

    def avatar(self, principal):
        with self.sessions() as s:
            user = self.actor(s, principal)
            return avatar_state(s.get(UserAvatar, user.id))

    def save_avatar(self, principal, image, expected_revision):
        encoded = normalize_avatar(image) if image is not None else None
        with self.sessions.begin() as s:
            # The user always exists; locking it serializes first uploads as well
            # as replacements, and rechecks suspension/session revocation.
            user = self.actor(s, principal)
            row = s.get(UserAvatar, user.id)
            actual = row.revision if row else None
            if actual != (str(expected_revision) if expected_revision else None):
                raise AvatarConflict('头像已在其他页面更新，请先重新读取，再确认是否替换。')
            if row is None:
                row = UserAvatar(user_id=user.id)
                s.add(row)
            row.image, row.revision = encoded, str(uuid4())
            # Keep a revision even for default avatars to prevent stale uploads
            # from silently undoing a reset in another tab or device.
            self.audit(s, user, 'reset_avatar' if encoded is None else 'update_avatar', user.id)
            s.flush()
            result = avatar_state(row)
        return result

    def update_profile(self, principal, data):
        with self.sessions.begin() as s:
            user=self.actor(s,principal)
            user.display_name=data.display_name.strip(); user.contact=data.contact.strip() or None
            self.audit(s,user,'update_profile',user.id)
        return self.profile(principal)

    def change_password(self, principal, data):
        validate_password(data.new_password)
        with self.sessions.begin() as s:
            user=self.actor(s,principal)
            if not verify_password(data.current_password,user.password_hash): raise ValueError('当前密码不正确。')
            if verify_password(data.new_password,user.password_hash): raise ValueError('新密码不能与当前密码相同。')
            user.password_hash=hash_password(data.new_password); user.session_version+=1
            s.execute(update(PasswordReset).where(PasswordReset.user_id==user.id).values(used=True))
            self.audit(s,user,'change_password',user.id)

    def apply_teacher(self, principal, reason):
        with self.sessions.begin() as s:
            user=self.actor(s,principal,{'student'})
            p=s.get(RegistrationPolicy,1)
            if not p or not p.teacher_applications: raise ValueError('当前暂停教师申请。')
            app=s.scalar(select(TeacherApplication).where(TeacherApplication.user_id==user.id))
            if app and app.status in {'pending','approved'}: raise ValueError('已存在待审核或已通过的教师申请。')
            if app: app.reason=reason.strip(); app.status='pending'; app.review_reason=None
            else: s.add(TeacherApplication(user_id=user.id,reason=reason.strip(),status='pending'))
            self.audit(s,user,'teacher_application',user.id)

    def recover(self, username, note):
        with self.sessions.begin() as s:
            normalized=username.strip().lower()
            user=s.scalar(select(User).where(User.username==normalized))
            # Same acknowledgement whether or not the account exists.
            pending=s.scalar(select(PasswordRecovery.id).where(PasswordRecovery.username==normalized,PasswordRecovery.status=='pending'))
            if not pending: s.add(PasswordRecovery(username=normalized,user_id=user.id if user else None,note=note.strip(),status='pending'))
        return {'message':'申请已接收。如账号与身份信息核实一致，管理员会通过约定方式协助重置；本页面不会显示账号是否存在。'}

    def issue_reset(self, principal, recovery_id, reason):
        with self.sessions.begin() as s:
            actor=self.actor(s,principal,{'admin'})
            row=s.scalar(select(PasswordRecovery).where(PasswordRecovery.id==recovery_id).with_for_update())
            if not row or row.status not in {'pending','resolved'} or not row.user_id: raise ValueError('申请不可处理，需先核实有效账号和身份。')
            target=s.scalar(select(User).where(User.id==row.user_id).with_for_update())
            if not target or not target.active: raise ValueError('账号不可用，请先在用户治理中核实，重置不会恢复停用账号。')
            s.execute(update(PasswordReset).where(PasswordReset.user_id==target.id).values(used=True))
            raw=secrets.token_urlsafe(32)
            expiry=now()+timedelta(minutes=30)
            s.add(PasswordReset(user_id=target.id,token_hash=digest(raw),expires_at=expiry,used=False,created_by=actor.id))
            row.status='resolved'
            self.audit(s,actor,'issue_password_reset',target.id,reason=reason,recovery_id=str(row.id))
            return {'token':raw,'expires_at':expiry,'message':'链接仅显示一次，30分钟有效，使用后失效；请私下交给已核实身份的用户。'}

    def reset(self, raw, password):
        validate_password(password)
        with self.sessions.begin() as s:
            # Lock the user before the token, matching password-change/issuance lock order.
            lookup=s.scalar(select(PasswordReset).where(PasswordReset.token_hash==digest(raw)))
            if not lookup: raise ValueError('链接无效或已过期，请重新申请。')
            user=s.scalar(select(User).where(User.id==lookup.user_id).with_for_update())
            row=s.scalar(select(PasswordReset).where(PasswordReset.id==lookup.id).with_for_update().execution_options(populate_existing=True))
            if not user or not user.active or row.used or utc(row.expires_at)<=now(): raise ValueError('链接无效或已过期，请重新申请。')
            user.password_hash=hash_password(password); user.session_version+=1
            s.execute(update(PasswordReset).where(PasswordReset.user_id==user.id).values(used=True))
            self.audit(s,user,'reset_password',user.id)

    def review(self, principal, kind, item_id, approve, reason):
        with self.sessions.begin() as s:
            actor=self.actor(s,principal,{'teacher','admin'})
            model={'applications':TeacherApplication,'joins':CourseJoinRequest,'recoveries':PasswordRecovery}[kind]
            row=s.scalar(select(model).where(model.id==item_id).with_for_update())
            if not row or row.status!='pending': raise ValueError('此申请已处理或不存在，请刷新列表。')
            if kind=='joins': self.manager(s,actor,row.course_id)
            elif actor.role!='admin': raise PermissionError('此申请只能由管理员处理。')
            if kind=='recoveries' and approve: raise ValueError('密码找回需使用身份核实后的单次重置入口。')
            if approve:
                user=s.scalar(select(User).where(User.id==row.user_id).with_for_update())
                if not user or not user.active: raise ValueError('账号已停用或不存在。')
                if kind=='applications':
                    if user.role!='student': raise ValueError('该账号角色已变化，请先核实。')
                    if s.scalar(select(CourseEnrollment.id).where(CourseEnrollment.user_id==user.id,CourseEnrollment.status=='active').limit(1)):
                        raise ValueError('该账号仍有在学课程。请先核实并处理学生课程身份，再批准教师身份，避免混用同一个角色。')
                    user.role='teacher'; user.session_version+=1
                elif kind=='joins':
                    course=s.get(Course,row.course_id)
                    if not course or course.status!='published' or user.role!='student': raise ValueError('课程或学生身份当前不允许加入。')
                    member=s.scalar(select(CourseEnrollment).where(CourseEnrollment.user_id==user.id,CourseEnrollment.course_id==row.course_id))
                    if member and member.status!='active': raise ValueError('已有停用记录，请在课程成员管理中明确处理。')
                    if not member: s.add(CourseEnrollment(course_id=row.course_id,user_id=user.id,status='active'))
            row.status='approved' if approve else 'rejected'
            if kind=='applications': row.review_reason=reason
            self.audit(s,actor,'review_'+kind,row.id,approved=approve,reason=reason)

    def listing(self, principal, kind, page, page_size, status=None, search=''):
        with self.sessions() as s:
            actor=self.actor(s,principal,{'teacher','admin'})
            model={'invites':AccessInvite,'applications':TeacherApplication,'recoveries':PasswordRecovery,'joins':CourseJoinRequest}[kind]
            q=select(model).order_by(model.created_at.desc(),model.id.desc())
            if actor.role!='admin':
                if kind not in {'invites','joins'}: raise PermissionError('无权读取这些账号申请。')
                q=q.where(model.course_id.in_(select(Course.id).where(Course.owner_id==actor.id)))
            stamp=now()
            if kind=='invites':
                q=q.outerjoin(Course,Course.id==AccessInvite.course_id)
                state=case((AccessInvite.revoked.is_(True),'revoked'),(AccessInvite.expires_at<=stamp,'expired'),
                           (AccessInvite.uses>=AccessInvite.max_uses,'exhausted'),
                           (AccessInvite.course_id.is_not(None) & or_(Course.id.is_(None),Course.status!='published'),'unavailable'),else_='active')
                if status:
                    if status not in {'active','expired','exhausted','revoked','unavailable'}: raise ValueError('邀请状态筛选无效。')
                    q=q.where(state==status)
                fields=[AccessInvite.label,Course.title,Course.code]
            else:
                allowed={'pending','resolved','rejected'} if kind=='recoveries' else {'pending','approved','rejected'}
                if status:
                    if status not in allowed: raise ValueError('申请状态筛选无效。')
                    q=q.where(model.status==status)
                q=q.outerjoin(User,User.id==model.user_id)
                fields=[User.username,User.display_name,model.note if kind=='recoveries' else model.reason]
                if kind=='recoveries': fields.append(model.username)
                if kind=='joins':
                    q=q.outerjoin(Course,Course.id==model.course_id)
                    fields.extend([Course.title,Course.code])
            if search.strip():
                term='%'+search.strip().replace('\\','\\\\').replace('%','\\%').replace('_','\\_')+'%'
                q=q.where(or_(*(field.ilike(term,escape='\\') for field in fields)))
            def item(r):
                d={'id':str(r.id),'created_at':r.created_at}
                if kind=='invites':
                    c=s.get(Course,r.course_id) if r.course_id else None
                    invite_state='revoked' if r.revoked else 'expired' if utc(r.expires_at)<=stamp else 'exhausted' if r.uses>=r.max_uses else 'unavailable' if r.course_id and (not c or c.status!='published') else 'active'
                    d.update(label=r.label,kind=r.kind,course_title=c.title if c else None,course_id=str(r.course_id) if r.course_id else None,approval_required=r.approval_required,uses=r.uses,max_uses=r.max_uses,expires_at=r.expires_at,revoked=r.revoked,state=invite_state)
                else:
                    u=s.get(User,r.user_id) if r.user_id else None
                    d.update(username=u.username if u else getattr(r,'username','未知账号'),display_name=u.display_name if u else '待核实',status=r.status,
                             reason=getattr(r,'reason',getattr(r,'note','')),user_active=bool(u and u.active))
                    if kind=='recoveries': d.update(account_exists=u is not None,contact=u.contact if u else None)
                    if kind=='joins':
                        course=s.get(Course,r.course_id)
                        d['course_title']=course.title if course else '课程已移除'
                    if r.status!='pending':
                        action='issue_password_reset' if kind=='recoveries' and r.status=='resolved' else 'review_'+kind
                        events=select(AuditLog).where(AuditLog.resource_type=='account_lifecycle',AuditLog.action==action)
                        # Password reset audit resources reference the account; its detail links the recovery.
                        events=events.where(AuditLog.resource_id==str(r.user_id) if action=='issue_password_reset' else AuditLog.resource_id==str(r.id))
                        event=next((e for e in s.scalars(events.order_by(AuditLog.created_at.desc(),AuditLog.id.desc()))
                                    if action!='issue_password_reset' or e.detail.get('recovery_id')==str(r.id)),None)
                        if event: d.update(review_reason=event.detail.get('reason',''),reviewed_by=event.actor_name,reviewed_at=event.created_at)
                        elif kind=='applications': d['review_reason']=r.review_reason
                    if r.status=='pending' and kind in {'applications','joins'}:
                        blocker=''
                        if not u or not u.active: blocker='账号已停用或不存在，请先在用户管理中核实。'
                        elif u.role!='student': blocker='该账号已不再是学生，请核实当前身份。'
                        elif kind=='applications' and s.scalar(select(CourseEnrollment.id).where(CourseEnrollment.user_id==u.id,CourseEnrollment.status=='active').limit(1)):
                            blocker='此账号仍有在学课程，请先处理学生课程身份，再批准教师申请。'
                        elif kind=='joins':
                            member=s.scalar(select(CourseEnrollment).where(CourseEnrollment.user_id==u.id,CourseEnrollment.course_id==r.course_id))
                            if not course or course.status!='published': blocker='课程当前未发布，暂不能批准加入。'
                            elif member and member.status!='active': blocker='此学生有停用的课程成员记录，请在课程成员管理中处理。'
                        d['approval_blocker']=blocker
                return d
            return sql_page(s,q,page=page,page_size=page_size,mapper=item)
