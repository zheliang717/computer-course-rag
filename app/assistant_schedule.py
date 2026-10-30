"""AI chooses bounded search preferences; deterministic code owns every slot."""
from datetime import datetime, time, timedelta, timezone
from uuid import UUID, uuid4
from sqlalchemy import select
from app.models import Course, CourseSession, TimetableRequest, User
from app.schedule_planning import SchedulePlanningService, CandidateInput
from app.teaching_work_schemas import ScheduleTask, ScheduleSuggestion
from app.timetable import SHANGHAI, ScheduleConflict, utc
from app.course_editor import signature
from app.accounts import AccountService


class AssistantSchedule:
    def __init__(self, timetable):
        self.timetable = timetable
        self.planner = SchedulePlanningService(timetable)

    def inputs(self, s, actor, data):
        course = self.timetable.course(s, actor, data.course_id)
        if course.status == 'archived': raise ValueError('已归档课程不能排课。')
        teacher = s.get(User, course.owner_id) if course.owner_id else None
        if not teacher or not teacher.active or teacher.role not in {'teacher', 'admin'}: raise ValueError('请先为课程分配启用的授课教师。')
        if actor.role == 'teacher' and not data.session_ids: raise ValueError('教师请选择待调课的现有课次；新增课次由管理员安排。')
        today = datetime.now(SHANGHAI).date()
        if data.start_date < today: raise ValueError('请选择今天或之后的候选日期。')
        lo, hi = self.planner.horizon(data)
        context = self.timetable.conflict_context(s, lo, hi, list(map(str, data.session_ids)))
        calendar = context['calendars'].get(course.semester, {})
        rooms = calendar.get('resources', {}).get('rooms', [])
        allowed = {r['code']: r for r in rooms}
        if not allowed:
            for name in calendar.get('rooms', []): allowed.setdefault(name, {'code':name, 'name':name, 'kind':'未分类'})
        if not allowed: raise ValueError('本学期没有可用教室，请管理员先维护教室与校历。')
        if data.rooms and not set(data.rooms) <= set(allowed): raise ValueError('所选教室不属于当前学期资源。')
        if data.rooms: allowed = {k:v for k,v in allowed.items() if k in data.rooms}
        rows = []
        for identifier in data.session_ids:
            row = s.get(CourseSession, identifier)
            if not row or row.course_id != course.id or row.completed or row.schedule_status == 'cancelled':
                raise ValueError('所选课次已变化、已授课或不属于该课程。')
            rows.append(row)
        return course, rows, context, allowed

    def model_context(self, s, actor, data):
        course, rows, _, allowed = self.inputs(s, actor, data)
        return dict(course_title=course.title, semester=course.semester, operation='replan' if rows else 'create',
            count=len(rows) or data.count, hard_window=data.model_dump(mode='json', exclude={'request'}),
            rooms=list(allowed.values()), sessions=[self.timetable.snapshot(x) for x in rows])

    def build(self, s, actor, params):
        data = ScheduleTask.model_validate(params['request'])
        suggestion = ScheduleSuggestion.model_validate(params['conditions'])
        course, rows, context, allowed = self.inputs(s, actor, data)
        if not set(suggestion.rooms) <= set(allowed) or not suggestion.rooms: raise ValueError('AI 返回了不可用教室，请调整条件后重新生成。')
        window = CandidateInput.model_validate({**data.model_dump(include=set(CandidateInput.model_fields)), 'day_start':suggestion.day_start,
            'day_end':suggestion.day_end, 'weekdays':suggestion.weekdays, 'rooms':suggestion.rooms})
        if not (data.day_start <= window.day_start < window.day_end <= data.day_end) or not set(window.weekdays) <= set(data.weekdays):
            raise ValueError('AI 建议超出了你设定的日期/时段，请修改需求后重试。')
        original = [self.timetable.snapshot(row) for row in rows]
        if not rows:
            anchor = datetime.combine(data.start_date, window.day_start, SHANGHAI)
            for index, identifier in enumerate(params['new_ids']):
                rows.append(CourseSession(id=UUID(identifier), course_id=course.id, title=f'{course.title} · 教学课次 {index+1}',
                    session_date=utc(anchor + timedelta(minutes=index*data.duration_minutes)), duration_minutes=data.duration_minutes,
                    location=suggestion.rooms[0], revision=1, completed=False, schedule_status='scheduled'))
        choices, checked, reasons = [], 0, []
        for variant in range(3):
            proposed, warnings = [], []
            for index, row in enumerate(rows):
                options, count, exhausted = self.planner.candidates_in_session(s, row, window,
                    {**context, 'existing':context['existing']+proposed, 'not_before':datetime.now(timezone.utc)}, variant+1 if index==0 else 1)
                checked += count
                choice = variant if index == 0 else 0
                if len(options) <= choice or checked > 12000:
                    reasons.append('当前有界搜索未找到完整方案；可扩大日期/时段、增加教室或减少调整课次。')
                    proposed = []; break
                selected = options[choice]; proposed.append(selected)
                warnings += selected.get('resource_warnings', [])
            if proposed and not any(x['proposed'] == proposed for x in choices):
                choices.append(dict(proposed=proposed, warnings=list(dict.fromkeys(warnings))))
            if checked > 12000: break
        roster = {key:sorted(map(str,value)) for key,value in context['members'].items()}
        owners = {str(k):[str(v.owner_id),v.status,v.semester] for k,v in context['courses'].items()}
        token = signature(dict(params=params, original=original, choices=choices, existing=context['existing'],
            calendars=context['calendars'], members=roster, owners=owners))
        return dict(original=original, choices=choices, signature=token, checked_candidates=checked,
            explanation=suggestion.explanation, conditions=params['conditions'], parameters=params,
            room_options=[dict(code=x['code'],name=x['name']) for x in allowed.values()],
            notice='按时间距离优先的有界候选方案，并非全校最优解；确认前不会调整课表。',
            unresolved=list(dict.fromkeys(reasons)) if not choices else [], student_count=len(context['members'].get(str(course.id),[])),
            mode='replan' if original else 'create')

    def adopt(self, s, actor, result, option, reason):
        saved = result.content
        current = self.build(s, actor, saved['parameters'])
        if saved['signature'] != current['signature']: raise ScheduleConflict('课表、资源或课程成员已变化，请重新生成方案后核对。')
        if option >= len(current['choices']): raise ValueError('所选方案不存在。')
        proposed = current['choices'][option]['proposed']
        ignored = [x['id'] for x in current['original']]
        self.timetable.check(s, proposed, ignored)
        if actor.role == 'teacher':
            if not current['original']: raise PermissionError('教师不能直接新增课次。')
            pending = s.scalars(select(TimetableRequest).where(TimetableRequest.course_id == result.course_id, TimetableRequest.status=='pending'))
            if any(set(ignored) & {x['id'] for x in p.original} for p in pending): raise ScheduleConflict('所选课次已有待审核申请。')
            row = TimetableRequest(course_id=result.course_id, requester_id=actor.id, kind='move',
                original=current['original'], proposed=proposed, reason=reason, status='pending')
            s.add(row); s.flush(); AccountService.audit(s, actor, 'request_timetable_change', row.id, workflow_id=str(result.id))
            return dict(request_id=str(row.id), message='调课申请已提交，待管理员审批；课表尚未改变。')
        if actor.role != 'admin': raise PermissionError('只有管理员能应用排课。')
        if current['original']:
            rows = [s.get(CourseSession, UUID(x['id'])) for x in current['original']]
            self.timetable.apply_rows(rows, proposed)
        else:
            course = s.get(Course, result.course_id)
            rows = []
            for item in proposed:
                row = self.timetable.new_row(s, course, item); row.id = UUID(item['id']); s.add(row); rows.append(row)
        s.flush()
        self.timetable.event(s, actor, result.course_id, current['original'], [self.timetable.snapshot(x) for x in rows], reason)
        return dict(updated_count=len(rows), message='已按确认方案更新课表，变更记录与课程通知已保存。')
