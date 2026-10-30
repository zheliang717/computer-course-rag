"""Course-scoped timetable. Only administrators can mutate scheduled occurrences."""
from datetime import datetime, date, time, timedelta, timezone
from zoneinfo import ZoneInfo
from uuid import UUID
import hashlib
import json

from sqlalchemy import select, text, func

from app.accounts import AccountService
from app.models import (Course, CourseSession, CourseSection, CourseEnrollment, User,
    TimetableCalendar, TimetableResourceCatalog, TimetableRule, TimetableRequest, TimetableEvent, CourseAnnouncement)
from app.pagination import sql_page
from app.timetable_resources import resource_conflicts, room_key, find_room, room_registry

SHANGHAI = ZoneInfo('Asia/Shanghai')


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def iso(value): return utc(value).isoformat()


class ScheduleConflict(ValueError):
    def __init__(self, message, conflicts=None):
        super().__init__(message)
        self.conflicts = conflicts or []


class TimetableService:
    def __init__(self, sessions): self.sessions = sessions

    @staticmethod
    def lock(s):
        # One lock order for single/batch creation, edits, approval and legacy writes.
        # The advisory lock prevents concurrent different-user room/teacher booking.
        if s.bind.dialect.name == 'postgresql':
            s.execute(text('SELECT pg_advisory_xact_lock(734801923)'))

    @staticmethod
    def actor(s, principal, roles=None): return AccountService.actor(s, principal, roles)

    @staticmethod
    def courses(s, actor):
        query = select(Course)
        if actor.role == 'teacher': query = query.where(Course.owner_id == actor.id)
        elif actor.role != 'admin':
            query = query.where(Course.status == 'published', Course.id.in_(select(CourseEnrollment.course_id).where(
                CourseEnrollment.user_id == actor.id, CourseEnrollment.status == 'active')))
        return list(s.scalars(query.order_by(Course.title, Course.id)))

    def course(self, s, actor, course_id):
        item = next((c for c in self.courses(s, actor) if c.id == course_id), None)
        if not item: raise PermissionError('课程不存在或当前账号无权访问。')
        return item

    @staticmethod
    def snapshot(item):
        return {'id':str(item.id), 'course_id':str(item.course_id), 'title':item.title,
            'section_id':str(item.section_id) if item.section_id else None,
            'session_date':iso(item.session_date), 'duration_minutes':item.duration_minutes,
            'location':item.location, 'schedule_status':item.schedule_status, 'completed':item.completed,
            'revision':item.revision, 'rule_id':str(item.rule_id) if item.rule_id else None}

    def record(self, s, item, course):
        result = self.snapshot(item)
        teacher = s.get(User, course.owner_id) if course.owner_id else None
        section = s.get(CourseSection, item.section_id) if item.section_id else None
        result.update(course_title=course.title, semester=course.semester,
            teacher_name=teacher.display_name if teacher else None,
            section_title=section.title if section else None,
            end_date=iso(utc(item.session_date)+timedelta(minutes=item.duration_minutes)))
        return result

    def options(self, principal):
        with self.sessions() as s:
            actor = self.actor(s, principal)
            courses = self.courses(s, actor)
            labels = {c.semester for c in courses if c.semester}
            return {'timezone':'Asia/Shanghai', 'courses':[{'id':str(c.id), 'title':c.title,
                'semester':c.semester, 'sections':[{'id':str(x.id),'title':x.title} for x in s.scalars(select(CourseSection).where(CourseSection.course_id==c.id,CourseSection.archived.is_(False)).order_by(CourseSection.position))]} for c in courses],
                'semesters':sorted(labels), 'calendars':[{'semester':c.semester,'revision':c.revision,**c.settings}
                    for c in s.scalars(select(TimetableCalendar)) if actor.role=='admin' or c.semester in labels]}

    def listing(self, principal, start, end, semester=None, course_id=None):
        if end <= start or (end-start).days > 35: raise ValueError('请选择最多35天的日期范围。')
        lower = datetime.combine(start, time.min, SHANGHAI).astimezone(timezone.utc)
        upper = datetime.combine(end, time.min, SHANGHAI).astimezone(timezone.utc)
        with self.sessions() as s:
            actor = self.actor(s, principal)
            courses = {c.id:c for c in self.courses(s, actor) if (not semester or c.semester==semester) and (not course_id or c.id==course_id)}
            rows = s.scalars(select(CourseSession).where(CourseSession.course_id.in_(courses),
                CourseSession.session_date >= lower-timedelta(hours=8), CourseSession.session_date < upper).order_by(CourseSession.session_date, CourseSession.id))
            items = [self.record(s, x, courses[x.course_id]) for x in rows
                if utc(x.session_date)+timedelta(minutes=x.duration_minutes)>lower]
            return {'items':items,'start':str(start),'end':str(end),'timezone':'Asia/Shanghai'}

    def detail(self, principal, session_id):
        with self.sessions() as s:
            actor = self.actor(s, principal)
            row = s.get(CourseSession, session_id)
            if not row: raise ValueError('课次不存在。')
            course = self.course(s, actor, row.course_id)
            return self.record(s, row, course)

    def save_calendar(self, principal, data):
        if data.start_date.weekday()!=0 or data.end_date<data.start_date or (data.end_date-data.start_date).days>365:
            raise ValueError('第一周周一须为星期一，学期结束日期须在其后一年内。')
        if any(d<data.start_date or d>data.end_date for d in data.holidays): raise ValueError('停课日期须在学期范围内。')
        with self.sessions.begin() as s:
            self.lock(s); actor=self.actor(s,principal,{'admin'})
            row=s.get(TimetableCalendar,data.semester)
            if (row.revision if row else 0)!=data.expected_revision: raise ScheduleConflict('校历已变化，请重新读取后再保存。')
            if not row: row=TimetableCalendar(semester=data.semester,revision=0);s.add(row)
            row.settings={**(row.settings or {}), 'start_date':str(data.start_date),'end_date':str(data.end_date),
                'holidays':sorted({str(x) for x in data.holidays}), 'rooms':sorted(set(x.strip() for x in data.rooms if x.strip()))}
            row.revision+=1
            AccountService.audit(s,actor,'timetable_calendar',row.semester,revision=row.revision)
        return self.options(principal)

    def conflict_context(self, s, lo, hi, ignored=()):
        rows=s.scalars(select(CourseSession).where(CourseSession.session_date>=lo-timedelta(hours=8),
            CourseSession.session_date<hi,CourseSession.schedule_status!='cancelled',~CourseSession.id.in_([UUID(x) for x in ignored])).order_by(CourseSession.session_date,CourseSession.id))
        existing=[self.snapshot(x) for x in rows]
        courses={c.id:c for c in s.scalars(select(Course))}
        members={}
        for course_id,user_id in s.execute(select(CourseEnrollment.course_id,CourseEnrollment.user_id).join(User, User.id==CourseEnrollment.user_id).where(
                CourseEnrollment.status=='active',User.active.is_(True),User.role=='student')):
            members.setdefault(str(course_id),set()).add(user_id)
        calendars={c.semester:dict(c.settings) for c in s.scalars(select(TimetableCalendar))}
        for catalog in s.scalars(select(TimetableResourceCatalog)):
            calendars.setdefault(catalog.semester,{})['resources']=catalog.settings
            calendars[catalog.semester]['resource_revision']=catalog.revision
        return {'existing':existing,'courses':courses,'members':members,'calendars':calendars,'room_keys':room_registry(calendars)}

    def conflicts(self, s, proposed, ignored=(), context=None):
        active=[x for x in proposed if x['schedule_status']!='cancelled']
        if not active: return []
        lo=min(datetime.fromisoformat(x['session_date']) for x in active)
        hi=max(datetime.fromisoformat(x['session_date'])+timedelta(minutes=x['duration_minutes']) for x in active)
        context=context or self.conflict_context(s,lo,hi,ignored)
        existing,courses,members,calendars=(context[k] for k in ('existing','courses','members','calendars'))
        findings=resource_conflicts(active,courses,members,calendars,SHANGHAI)
        for index,item in enumerate(active):
            a=courses[UUID(item['course_id'])]
            for other in existing+active[:index]:
                if item['id']==other['id']: continue
                b=courses[UUID(other['course_id'])]
                if b.status=='archived': continue
                begin,other_begin=datetime.fromisoformat(item['session_date']),datetime.fromisoformat(other['session_date'])
                if begin>=other_begin+timedelta(minutes=other['duration_minutes']) or other_begin>=begin+timedelta(minutes=item['duration_minutes']): continue
                room=bool(room_key(item['location'],calendars.get(a.semester,{}),context.get('room_keys')) and
                    room_key(item['location'],calendars.get(a.semester,{}),context.get('room_keys'))==room_key(other['location'],calendars.get(b.semester,{}),context.get('room_keys')))
                teacher=bool(a.owner_id and a.owner_id==b.owner_id)
                same=a.id==b.id
                students=bool(members.get(str(a.id),set()) & members.get(str(b.id),set()))
                if same or room or teacher or students:
                    findings.append({'session_id':item['id'],'other_id':other['id'],'course_title':b.title,
                        'time':other['session_date'],'blocking':True,
                        'message':' / '.join(k for k,v in [('课程重叠',same),('场地冲突',room),('教师冲突',teacher),('学生选课冲突',students)] if v)})
                if len(findings)>=10000: return findings
        return findings

    def check(self,s,proposed,ignored,ack=False):
        findings=self.conflicts(s,proposed,ignored)
        if any(x['blocking'] for x in findings): raise ScheduleConflict('存在课程、学生、教师或场地冲突，必须重新安排，未更改课表。',findings)
        for item in proposed:
            course=s.get(Course,UUID(item['course_id']))
            catalog=s.get(TimetableResourceCatalog,course.semester) if course.semester else None
            room=find_room(item['location'],{'resources':catalog.settings} if catalog else {})
            # Keep readable locations in lessons; the registry resolves names,
            # aliases and codes to the stable physical identity for conflicts.
            if room: item['location']=room['name']
        return findings

    @staticmethod
    def event(s,actor,course_id,before,after,reason,request_id=None):
        s.add(TimetableEvent(course_id=course_id,actor_id=actor.id,created_at=datetime.now(timezone.utc),detail={'before':before,'after':after,
            'reason':reason,'request_id':str(request_id) if request_id else None}))
        AccountService.audit(s,actor,'timetable_publish',course_id,request_id=str(request_id) if request_id else None,count=len(after))
        lines=[]
        for item in after[:120]:
            when=datetime.fromisoformat(item['session_date']).astimezone(SHANGHAI).strftime('%m月%d日 %H:%M')
            lines.append(f"{item['title']}：{when}，{item['duration_minutes']}分钟，{item['location'] or '地点待通知'}"+
                ('（已停课）' if item['schedule_status']=='cancelled' else ''))
        if lines:
            s.add(CourseAnnouncement(course_id=course_id,author_id=actor.id,title='课程安排更新',
                content=('课程安排已更新，请在“我的课表”查看最新信息。\n\n'+'\n'.join(lines))[:10000],published_at=datetime.now(timezone.utc)))

    def create(self,principal,course_id,data,ack=False):
        with self.sessions.begin() as s:
            self.lock(s); actor=self.actor(s,principal,{'admin'}); course=self.course(s,actor,course_id)
            row=self.new_row(s,course,data)
            proposed=[self.snapshot(row)]
            self.check(s,proposed,[],ack)
            row.location=proposed[0]['location']
            s.add(row);s.flush()
            result=self.record(s,row,course)
            self.event(s,actor,course_id,[],[self.snapshot(row)],'管理员新增课次')
        return result

    @staticmethod
    def new_row(s,course,data,rule_id=None):
        from uuid import uuid4
        if course.status=='archived': raise ValueError('已归档课程不能新增排课。')
        teacher=s.get(User,course.owner_id) if course.owner_id else None
        if not teacher or not teacher.active or teacher.role not in {'teacher','admin'}:
            raise ValueError('请先为课程分配可任教的教师。')
        section_id=UUID(str(data['section_id'])) if data.get('section_id') else None
        if section_id:
            section=s.get(CourseSection,section_id)
            if not section or section.course_id!=course.id or section.archived: raise ValueError('章节不属于该课程或已归档。')
        when=data['session_date']
        if isinstance(when,str): when=datetime.fromisoformat(when)
        if when.tzinfo is None: when=when.replace(tzinfo=SHANGHAI)
        return CourseSession(id=uuid4(),course_id=course.id,section_id=section_id,title=data['title'].strip(),
            session_date=utc(when),duration_minutes=data['duration_minutes'],location=data.get('location') or None,
            schedule_status='scheduled',revision=1,completed=False,rule_id=rule_id)

    def complete(self,principal,session_id,completed):
        with self.sessions.begin() as s:
            self.lock(s); actor=self.actor(s,principal,{'admin','teacher'})
            row=s.get(CourseSession,session_id)
            if not row: raise ValueError('课次不存在。')
            course=self.course(s,actor,row.course_id)
            if completed and row.schedule_status=='cancelled': raise ValueError('停课课次不能确认已授课。')
            if completed and utc(row.session_date)>datetime.now(timezone.utc): raise ValueError('尚未开始的课次不能确认已授课。')
            if row.completed!=completed: row.completed=completed;row.revision+=1
            AccountService.audit(s,actor,'confirm_teaching',row.id,completed=completed)
            return self.record(s,row,course)

    def proposals(self,s,row,kind,when,duration,location,scope):
        rows=[row]
        if scope=='following':
            if not row.rule_id: raise ValueError('该历史课次没有重复规则，请逐次申请，不能猜测后续范围。')
            rows=list(s.scalars(select(CourseSession).where(CourseSession.course_id==row.course_id,CourseSession.rule_id==row.rule_id,CourseSession.session_date>=row.session_date).order_by(CourseSession.session_date)))
        if len(rows)>120: raise ValueError('一次最多调整120个课次。')
        if any(x.completed for x in rows): raise ValueError('包含已确认授课的课次，请先核对，不能改写已授课安排。')
        if kind not in {'makeup','cancel'} and any(x.schedule_status=='cancelled' for x in rows):
            raise ValueError('停课课次须通过补课安排恢复，不能直接换教室或移动。')
        original=[self.snapshot(x) for x in rows]
        proposed=json.loads(json.dumps(original))
        if kind in {'move','makeup'} and when is None: raise ValueError('请填写调整后的日期时间。')
        delta=utc(when)-utc(row.session_date) if when else timedelta(0)
        for item in proposed:
            if kind=='cancel': item['schedule_status']='cancelled'
            else:
                item['schedule_status']='scheduled'
                if when: item['session_date']=iso(datetime.fromisoformat(item['session_date'])+delta)
                if duration is not None: item['duration_minutes']=duration
                if location is not None: item['location']=location.strip() or None
        return rows,original,proposed

    @staticmethod
    def apply_rows(rows,proposed):
        for row,item in zip(rows,proposed):
            row.session_date=datetime.fromisoformat(item['session_date']);row.duration_minutes=item['duration_minutes']
            row.location=item['location'];row.schedule_status=item['schedule_status'];row.revision+=1
            row.title=item['title'];row.section_id=UUID(item['section_id']) if item['section_id'] else None

    def change(self,principal,session_id,data,request=False):
        with self.sessions.begin() as s:
            self.lock(s); actor=self.actor(s,principal,{'teacher'} if request else {'admin'})
            row=s.get(CourseSession,session_id)
            if not row: raise ValueError('课次不存在。')
            course=self.course(s,actor,row.course_id)
            if course.status=='archived': raise ValueError('已归档课程不能调整课表。')
            if row.revision!=data.expected_revision: raise ScheduleConflict('原课次已变化，请重新打开后再提交。')
            if request and {'title','section_id'} & data.model_fields_set:
                raise PermissionError('教师调课申请仅调整时间、场地或停补课；课次主题与关联章节由管理员维护。')
            rows,original,proposed=self.proposals(s,row,data.kind,data.session_date,data.duration_minutes,data.location,data.scope)
            if not request:
                if data.section_id:
                    section=s.get(CourseSection,data.section_id)
                    if not section or section.course_id!=course.id or section.archived: raise ValueError('章节不属于该课程或已归档。')
                for item in proposed:
                    if data.title is not None: item['title']=data.title
                    if 'section_id' in data.model_fields_set: item['section_id']=str(data.section_id) if data.section_id else None
            if proposed==original: raise ValueError('尚未调整安排，请修改后再提交。')
            if request:
                ids={x['id'] for x in original}
                pending=s.scalars(select(TimetableRequest).where(TimetableRequest.course_id==course.id,TimetableRequest.status=='pending'))
                if any(ids & {x['id'] for x in p.original} for p in pending): raise ScheduleConflict('所选课次已有待审核申请，请先处理或撤回。')
                item=TimetableRequest(course_id=course.id,requester_id=actor.id,kind=data.kind,original=original,
                    proposed=proposed,reason=data.reason.strip(),status='pending')
                s.add(item);s.flush();AccountService.audit(s,actor,'request_timetable_change',item.id)
                return self.request_dict(s,item)
            self.check(s,proposed,[x['id'] for x in original],data.acknowledge_student_conflicts)
            self.apply_rows(rows,proposed);self.event(s,actor,course.id,original,[self.snapshot(x) for x in rows],data.reason)
            s.flush();return self.record(s,row,course)

    def request_dict(self,s,row):
        course=s.get(Course,row.course_id);teacher=s.get(User,row.requester_id)
        return {'id':str(row.id),'course_id':str(row.course_id),'course_title':course.title,'requester':teacher.display_name,
            'kind':row.kind,'status':row.status,'reason':row.reason,'review_reason':row.review_reason,
            'original':row.original,'proposed':row.proposed,'created_at':iso(row.created_at)}

    def requests(self,principal,page,page_size,status=None):
        with self.sessions() as s:
            actor=self.actor(s,principal,{'teacher','admin'})
            query=select(TimetableRequest)
            if actor.role=='teacher': query=query.where(TimetableRequest.requester_id==actor.id,TimetableRequest.course_id.in_([c.id for c in self.courses(s,actor)]))
            if status: query=query.where(TimetableRequest.status==status)
            return sql_page(s,query.order_by(TimetableRequest.created_at.desc(),TimetableRequest.id),page=page,page_size=page_size,mapper=lambda x:self.request_dict(s,x))

    def review(self,principal,request_id,approved,reason,ack=False):
        with self.sessions.begin() as s:
            self.lock(s); actor=self.actor(s,principal,{'admin'})
            item=s.get(TimetableRequest,request_id)
            if not item or item.status!='pending': raise ScheduleConflict('申请不存在或已处理，请刷新列表。')
            if approved:
                course=s.get(Course,item.course_id);teacher=s.get(User,item.requester_id)
                if not course or course.status=='archived' or not teacher or not teacher.active or teacher.role!='teacher' or course.owner_id!=teacher.id:
                    raise ScheduleConflict('申请人的任教资格已变化，不能批准旧申请。')
                rows=[s.get(CourseSession,UUID(x['id'])) for x in item.original]
                if any(x is None for x in rows) or [self.snapshot(x) for x in rows]!=item.original:
                    raise ScheduleConflict('原安排或授课确认已变化，请驳回并由教师重新申请。')
                self.check(s,item.proposed,[x['id'] for x in item.original],ack)
                self.apply_rows(rows,item.proposed)
                self.event(s,actor,item.course_id,item.original,[self.snapshot(x) for x in rows],item.reason,item.id)
            item.status='approved' if approved else 'rejected';item.review_reason=reason.strip()
            item.reviewer_id=actor.id;item.reviewed_at=datetime.now(timezone.utc)
            AccountService.audit(s,actor,'review_timetable_change',item.id,status=item.status)
            s.flush();return self.request_dict(s,item)

    def withdraw(self,principal,request_id):
        with self.sessions.begin() as s:
            self.lock(s);actor=self.actor(s,principal,{'teacher'})
            item=s.get(TimetableRequest,request_id)
            if not item or item.requester_id!=actor.id: raise PermissionError('无权撤回该申请。')
            if item.status!='pending': raise ScheduleConflict('仅待审核申请可以撤回。')
            item.status='withdrawn';item.reviewed_at=datetime.now(timezone.utc)
            AccountService.audit(s,actor,'withdraw_timetable_change',item.id)
            return {'message':'申请已撤回，课表未变动。'}

    def events(self,principal,page,page_size):
        with self.sessions() as s:
            actor=self.actor(s,principal);courses={c.id:c for c in self.courses(s,actor)}
            return sql_page(s,select(TimetableEvent).where(TimetableEvent.course_id.in_(courses)).order_by(TimetableEvent.created_at.desc(),TimetableEvent.id),
                page=page,page_size=page_size,mapper=lambda x:{'id':str(x.id),'course_title':courses[x.course_id].title,
                    'created_at':iso(x.created_at),**x.detail})

    def generate(self,s,actor,data):
        course=self.course(s,actor,data.course_id)
        calendar=s.get(TimetableCalendar,course.semester)
        if not calendar: raise ValueError('请先为该课程的学期设置校历。')
        first=date.fromisoformat(calendar.settings['start_date']);last=date.fromisoformat(calendar.settings['end_date'])
        holidays=set(calendar.settings['holidays']);result=[]
        for week in range(data.start_week,data.end_week+1):
            if data.parity=='odd' and week%2==0 or data.parity=='even' and week%2!=0: continue
            for day in sorted(set(data.weekdays)):
                target=first+timedelta(weeks=week-1,days=day-1)
                if target>last: raise ValueError('生成日期超出学期结束日期。')
                if str(target) in holidays: continue
                row=self.new_row(s,course,{'title':data.title,'section_id':data.section_id,
                    'session_date':datetime.combine(target,data.start_time,SHANGHAI),
                    'duration_minutes':data.duration_minutes,'location':data.location})
                snap=self.snapshot(row);snap['id']=f'preview-{len(result)}';result.append(snap)
        if not result or len(result)>120: raise ValueError('一次须生成1—120个有效课次。')
        payload={'rows':result,'calendar_revision':calendar.revision,'course_owner':str(course.owner_id)}
        digest=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        return course,result,digest

    def batch(self,principal,data,commit=False):
        with self.sessions.begin() as s:
            self.lock(s);actor=self.actor(s,principal,{'admin'})
            course,rows,digest=self.generate(s,actor,data)
            conflicts=self.conflicts(s,rows)
            if not commit: return {'items':rows,'digest':digest,'conflicts':conflicts}
            if not data.confirmed or data.preview_digest!=digest: raise ScheduleConflict('预览内容或校历已变化，请重新预览后确认发布。')
            self.check(s,rows,[],data.acknowledge_student_conflicts)
            rule=TimetableRule(course_id=course.id,created_by=actor.id,settings=data.model_dump(mode='json',exclude={'preview_digest','confirmed','acknowledge_student_conflicts'}))
            s.add(rule);s.flush();created=[]
            for item in rows:
                row=self.new_row(s,course,item,rule.id);s.add(row);s.flush();created.append(self.snapshot(row))
            self.event(s,actor,course.id,[],created,'管理员按排课规则发布')
            return {'count':len(created),'rule_id':str(rule.id)}
