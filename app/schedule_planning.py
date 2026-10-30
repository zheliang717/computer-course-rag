"""Bounded conflict-free candidates and explicit greedy replan previews."""
from datetime import date, time, datetime, timedelta
from uuid import UUID
import hashlib
import json
from pydantic import Field, model_validator
from sqlalchemy import select
from app.timetable_resources import Input, find_room
from app.models import CourseSession, TimetableCalendar, Course
from app.timetable import SHANGHAI, utc, iso, ScheduleConflict


class PlanningWindow(Input):
    start_date: date
    end_date: date
    day_start: time = time(8)
    day_end: time = time(20)
    weekdays: list[int] = Field(default_factory=lambda:[1,2,3,4,5], min_length=1, max_length=7)
    rooms: list[str] = Field(default_factory=list, max_length=30)
    step_minutes: int = Field(default=30, ge=15, le=120)

    @model_validator(mode='after')
    def bounds(self):
        if not 0 <= (self.end_date-self.start_date).days <= 13: raise ValueError('候选搜索范围为1—14天。')
        if self.day_start.tzinfo or self.day_end.tzinfo or self.day_start >= self.day_end: raise ValueError('每日搜索时段须在同一天内。')
        if any(not 1 <= d <= 7 for d in self.weekdays): raise ValueError('星期须为1—7。')
        if any(not x.strip() or len(x)>200 for x in self.rooms): raise ValueError('教室编号不完整。')
        return self


class CandidateInput(PlanningWindow):
    max_candidates: int = Field(default=10, ge=1, le=20)


class ReplanInput(PlanningWindow):
    session_ids: list[UUID] = Field(min_length=1, max_length=12)
    signature: str = Field(default='', max_length=64)
    confirmed: bool = False
    reason: str = Field(default='管理员确认辅助重排', min_length=5, max_length=500)


class SchedulePlanningService:
    def __init__(self, timetable): self.timetable = timetable

    @staticmethod
    def horizon(data):
        return datetime.combine(data.start_date, time.min, SHANGHAI), datetime.combine(data.end_date+timedelta(days=1), time.min, SHANGHAI)

    def candidates_in_session(self, s, row, data, context, limit):
        course = context['courses'][row.course_id]
        calendar = context['calendars'].get(course.semester, {})
        rooms = list(dict.fromkeys(data.rooms or [r['code'] for r in calendar.get('resources',{}).get('rooms',[])] or
            calendar.get('rooms',[]) or ([row.location] if row.location else [])))[:30]
        if not rooms: return [], 0, False
        start, end = self.horizon(data)
        slots = []
        for offset in range((data.end_date-data.start_date).days+1):
            day = data.start_date+timedelta(days=offset)
            if day.isoweekday() not in data.weekdays or str(day) in calendar.get('holidays',[]): continue
            if calendar and not calendar.get('start_date',str(day)) <= str(day) <= calendar.get('end_date',str(day)): continue
            when = datetime.combine(day,data.day_start,SHANGHAI)
            finish = datetime.combine(day,data.day_end,SHANGHAI)
            while when+timedelta(minutes=row.duration_minutes) <= finish:
                for index, room in enumerate(rooms):
                    distance = abs((utc(when)-utc(row.session_date)).total_seconds())
                    slots.append((distance, when, index, room))
                when += timedelta(minutes=data.step_minutes)
        result, checked = [], 0
        for _, when, _, room in sorted(slots):
            if context.get('not_before') and utc(when) <= context['not_before']: continue
            checked += 1
            if checked > 3000: return result, 3000, True
            proposed = {**self.timetable.snapshot(row), 'session_date':iso(when), 'location':room, 'schedule_status':'scheduled'}
            findings = self.timetable.conflicts(s,[proposed],context=context)
            if not any(x['blocking'] for x in findings):
                room_info=find_room(room,calendar)
                proposed['location_display']=room_info['name'] if room_info else room
                proposed['resource_warnings'] = [x['message'] for x in findings]
                result.append(proposed)
                if len(result) >= limit: break
        return result, checked, False

    def candidates(self, principal, session_id, data):
        with self.timetable.sessions() as s:
            actor = self.timetable.actor(s,principal,{'admin','teacher'})
            row = s.get(CourseSession,session_id)
            if not row: raise ValueError('课次不存在。')
            self.timetable.course(s,actor,row.course_id)
            if row.completed: raise ValueError('已授课课次不能重排。')
            lo,hi=self.horizon(data)
            context=self.timetable.conflict_context(s,lo,hi,[str(row.id)])
            items, checked, exhausted=self.candidates_in_session(s,row,data,context,data.max_candidates)
            return {'items':items,'base_revision':row.revision,'checked_candidates':checked,'search_limit_reached':exhausted,
                'notice':'候选是当前约束快照，不是预订；保存或审批时会再次检查。' if items else
                    '当前有界搜索未找到候选。请扩大可用日期/教室、检查教师时段或调整课程安排，不代表数学上无解。'}

    def replan(self, principal, data, commit=False):
        if len(set(data.session_ids)) != len(data.session_ids): raise ValueError('课次不能重复。')
        with self.timetable.sessions.begin() as s:
            self.timetable.lock(s)
            actor = self.timetable.actor(s,principal,{'admin'})
            rows=list(s.scalars(select(CourseSession).where(CourseSession.id.in_(data.session_ids)).order_by(
                CourseSession.session_date,CourseSession.id).with_for_update()))
            if len(rows)!=len(data.session_ids) or any(row.completed or row.schedule_status=='cancelled' for row in rows):
                raise ValueError('课次已变化、已授课或已停课，请重新选择。')
            lo,hi=self.horizon(data)
            ignored=[str(row.id) for row in rows]
            context=self.timetable.conflict_context(s,lo,hi,ignored)
            original=[self.timetable.snapshot(row) for row in rows]
            proposed,unresolved,checked=[],[],0
            for row in rows:
                course=self.timetable.course(s,actor,row.course_id)
                if course.status=='archived': raise ValueError('已归档课程不能重排。')
                options,count,exhausted=self.candidates_in_session(s,row,data,{**context,'existing':context['existing']+proposed},1)
                checked+=count
                if not options:
                    unresolved.append({'id':str(row.id),'title':row.title,'course_title':course.title,'search_limit_reached':exhausted,
                        'reason':'当前有界贪心搜索未找到位置；可缩小重排范围、补充教室/教师时段或调整日期后重试。'})
                else: proposed.append(options[0])
            # Bind the preview to actual roster, resource rules and existing bookings.
            state={'original':original,'proposed':proposed,'unresolved':unresolved,
                'existing':context['existing'],'calendars':context['calendars'],
                'members':{key:sorted(map(str,value)) for key,value in context['members'].items()},
                'owners':{str(c.id):str(c.owner_id) for c in context['courses'].values()}}
            signature=hashlib.sha256(json.dumps(state,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
            ready=not unresolved
            if not commit:
                return {'original':original,'proposed':proposed,'unresolved':unresolved,'ready':ready,'signature':signature,
                    'checked_candidates':checked,'algorithm':'bounded_greedy_nearest_time',
                    'notice':'按原时间距离优先、有界顺序放置；不是全校最优求解。确认前不会更改任何课次。'}
            if not ready or not data.confirmed or signature!=data.signature:
                raise ScheduleConflict('重排预览已变化或存在未解决课次，请重新预览后明确确认。')
            self.timetable.check(s,proposed,ignored)
            self.timetable.apply_rows(rows,proposed)
            after=[self.timetable.snapshot(row) for row in rows]
            for course_id in {row.course_id for row in rows}:
                self.timetable.event(s,actor,course_id,[x for x in original if x['course_id']==str(course_id)],
                    [x for x in after if x['course_id']==str(course_id)],data.reason)
            return {'updated_count':len(rows),'items':after,'notice':'已按确认预览更新课表，原安排保留在变更记录中。'}

    def audit(self, principal, start_date, end_date, page, page_size):
        if not 0 <= (end_date-start_date).days <= 34: raise ValueError('单次冲突检查范围为1—35天。')
        with self.timetable.sessions() as s:
            self.timetable.actor(s,principal,{'admin'})
            lo=datetime.combine(start_date,time.min,SHANGHAI);hi=datetime.combine(end_date+timedelta(days=1),time.min,SHANGHAI)
            rows=list(s.scalars(select(CourseSession).join(Course).where(CourseSession.session_date>=lo,
                CourseSession.session_date<hi,CourseSession.schedule_status!='cancelled',Course.status!='archived').order_by(CourseSession.id)))
            findings=self.timetable.conflicts(s,[self.timetable.snapshot(row) for row in rows],[str(row.id) for row in rows])
            return {'items':findings[(page-1)*page_size:page*page_size],'total':len(findings),'page':page,'page_size':page_size,
                'truncated':len(findings)>=10000,'checked_sessions':len(rows),
                'notice':'仅检查所选日期范围；历史冲突列出但不自动修改。超过一万条时需缩小日期范围。'}
