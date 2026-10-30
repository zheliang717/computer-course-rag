"""Calendar-scoped resources. Unknown legacy data is never invented/backfilled."""
from datetime import date, time, datetime, timedelta, timezone
import re
import unicodedata
import hashlib
from uuid import UUID
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from app.models import TimetableCalendar, TimetableResourceCatalog, User, Course, CourseSession


def normalized(value): return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or '')).casefold()


class Input(BaseModel):
    model_config = ConfigDict(extra='forbid')


class RoomResource(Input):
    code: str = Field(pattern=r'^[A-Za-z0-9][A-Za-z0-9_-]{0,29}$')
    name: str = Field(min_length=1, max_length=120)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    capacity: int = Field(ge=1, le=10000)
    equipment: list[str] = Field(default_factory=list, max_length=20)
    kind: Literal['multimedia', 'computer_lab', 'specialized_lab'] = 'multimedia'
    specialty: str = Field(default='通用', max_length=60)

    @model_validator(mode='after')
    def names(self):
        self.code = self.code.upper(); self.name = self.name.strip()
        if not self.name or any(not x.strip() or len(x) > 120 for x in self.aliases + self.equipment):
            raise ValueError('场地名称、别名与设备须为1—120字。')
        self.aliases = sorted(set(x.strip() for x in self.aliases))
        self.equipment = sorted(set(x.strip() for x in self.equipment))
        return self


class AvailableSlot(Input):
    weekday: int = Field(ge=1, le=7)
    start: time
    end: time

    @model_validator(mode='after')
    def times(self):
        if self.start.tzinfo or self.end.tzinfo or self.end <= self.start:
            raise ValueError('教师可用时段须为同一天内的北京时间。')
        return self


class TeacherAvailability(Input):
    teacher_id: UUID
    slots: list[AvailableSlot] = Field(max_length=28)


class CourseRequirement(Input):
    course_id: UUID
    equipment: list[str] = Field(default_factory=list, max_length=20)
    specialty: str = Field(default='', max_length=60)


class ResourceInput(Input):
    semester: str = Field(min_length=1, max_length=80)
    expected_revision: int = Field(ge=0)
    strict_rooms: bool = True
    resource_mode: Literal['advisory', 'enforced'] = 'advisory'
    specification_source: Literal['editable_default', 'administrator'] = 'administrator'
    rooms: list[RoomResource] = Field(min_length=1, max_length=200)
    availability: list[TeacherAvailability] = Field(default_factory=list, max_length=200)
    requirements: list[CourseRequirement] = Field(default_factory=list, max_length=200)

    @model_validator(mode='after')
    def unique_names(self):
        if len({r.code for r in self.rooms}) != len(self.rooms):
            raise ValueError('教室编号不能重复。')
        seen = {}
        for room in self.rooms:
            for alias in [room.code, room.name, *room.aliases]:
                key = normalized(alias)
                if key in seen and seen[key] != room.code: raise ValueError('教室编号、名称或别名存在冲突。')
                seen[key] = room.code
        if len({x.teacher_id for x in self.availability}) != len(self.availability): raise ValueError('教师可用时段不能重复配置。')
        if len({x.course_id for x in self.requirements}) != len(self.requirements): raise ValueError('课程设备需求不能重复配置。')
        for row in self.requirements:
            if any(not x.strip() or len(x) > 120 for x in row.equipment): raise ValueError('课程设备名称不完整。')
        return self


def find_room(location, calendar):
    key = normalized(location)
    return next((r for r in calendar.get('resources', {}).get('rooms', []) if key in {
        normalized(v) for v in [r['code'], r['name'], *r.get('aliases', [])]}), None)


def room_key(location, calendar, registry=None):
    if registry and normalized(location) in registry: return registry[normalized(location)]
    room = find_room(location, calendar)
    return normalized(room['code'] if room else location)


def room_registry(calendars):
    result={}
    for calendar in calendars.values():
        for room in calendar.get('resources',{}).get('rooms',[]):
            for name in [room['code'],room['name'],*room.get('aliases',[])]:
                result[normalized(name)]=normalized(room['code'])
    return result


def resource_conflicts(active, courses, members, calendars, shanghai):
    findings = []
    for item in active:
        course = courses[UUID(item['course_id'])]
        calendar = calendars.get(course.semester, {})
        resources = calendar.get('resources')
        if not resources: continue  # Existing unconfigured calendars remain explicitly legacy.
        room = find_room(item['location'], calendar)
        errors = []
        enforce = resources.get('resource_mode', 'advisory') == 'enforced'
        if not room and resources.get('strict_rooms', True): errors.append(('未使用已登记的教室编号或别名', enforce))
        if room:
            size = len(members.get(str(course.id), set()))
            if size > room['capacity']: errors.append((f'教室容量不足（{room["capacity"]}座 / {size}名在课学生）', enforce))
            requirement = next((x for x in resources.get('requirements', []) if x['course_id'] == str(course.id)), {})
            required = requirement.get('equipment', [])
            missing = set(map(normalized, required)) - set(map(normalized, room['equipment']))
            if missing: errors.append(('教室设备不满足课程需求：' + '、'.join(sorted(missing)), enforce))
            specialty = requirement.get('specialty','')
            if specialty and normalized(specialty) != normalized(room.get('specialty','通用')):
                errors.append(('教室专业用途与课程建议不一致：' + specialty, enforce))
        when = datetime.fromisoformat(item['session_date']).astimezone(shanghai)
        end = when + timedelta(minutes=item['duration_minutes'])
        availability = next((r for r in resources.get('availability', []) if r['teacher_id'] == str(course.owner_id)), None)
        if availability is not None:
            windows = sorted((time.fromisoformat(r['start']), time.fromisoformat(r['end'])) for r in availability['slots'] if r['weekday'] == when.isoweekday())
            merged = []
            for start, finish in windows:
                if merged and start <= merged[-1][1]: merged[-1] = (merged[-1][0], max(merged[-1][1], finish))
                else: merged.append((start, finish))
            if end.date() != when.date() or not any(start <= when.time() and finish >= end.time() for start, finish in merged):
                errors.append(('不在教师已配置的可用时段内', True))
        for error, blocking in errors:
            findings.append({'session_id': item['id'], 'other_id': '', 'course_title': course.title,
                'time': item['session_date'], 'blocking': blocking, 'message': error})
    return findings


def resource_state(service, principal, semester, data=None):
    from app.accounts import AccountService
    with service.sessions.begin() as s:
        if data: service.lock(s)
        actor = service.actor(s, principal, {'admin'})
        calendar = s.scalar(select(TimetableCalendar).where(TimetableCalendar.semester == semester).with_for_update())
        catalog = s.scalar(select(TimetableResourceCatalog).where(TimetableResourceCatalog.semester == semester).with_for_update())
        if not s.scalar(select(Course.id).where(Course.semester == semester).limit(1)):
            raise ValueError('请先选择现有课程所属学期。')
        if data:
            if (catalog.revision if catalog else 0) != data.expected_revision: raise ValueError('资源已变化，请刷新后再保存。')
            teacher_ids = {x.teacher_id for x in data.availability}
            valid = set(s.scalars(select(User.id).where(User.id.in_(teacher_ids), User.active.is_(True), User.role == 'teacher')))
            if teacher_ids != valid: raise ValueError('教师不存在或当前不可任教。')
            course_ids = {x.course_id for x in data.requirements}
            valid_courses = set(s.scalars(select(Course.id).where(Course.id.in_(course_ids), Course.semester == semester)))
            if course_ids != valid_courses: raise ValueError('课程不属于本学期。')
            resources = data.model_dump(mode='json', exclude={'semester', 'expected_revision'})
            # Preserve known names/codes, so existing lessons keep resolving after
            # display-name changes. A physical room has one code across semesters.
            for room in resources['rooms']:
                old=next((r for r in (catalog.settings.get('rooms',[]) if catalog else []) if
                    r['code']==room['code'] or normalized(r['name'])==normalized(room['name'])),None)
                if old: room['aliases']=sorted(set(room['aliases']+[old['name'],old['code'],*old.get('aliases',[])]))
            ResourceInput.model_validate({**resources,'semester':semester,'expected_revision':data.expected_revision})
            if catalog:
                from app.accounts import utc
                for when,duration,location in s.execute(select(CourseSession.session_date,CourseSession.duration_minutes,
                        CourseSession.location).join(Course).where(Course.semester==semester,
                        CourseSession.completed.is_(False),CourseSession.schedule_status!='cancelled')):
                    if when and utc(when)+timedelta(minutes=duration)>=datetime.now(timezone.utc) and find_room(location,{'resources':catalog.settings}) and not find_room(location,{'resources':resources}):
                        raise ValueError('该教室仍有待授课安排，不能移除其编号或名称；请先调整相关课次，或保留原教室。')
            for other in s.scalars(select(TimetableResourceCatalog).where(TimetableResourceCatalog.semester!=semester)):
                for old in other.settings.get('rooms',[]):
                    old_names={normalized(v) for v in [old['name'],*old.get('aliases',[])] if normalized(v)!=normalized(old['code'])}
                    for room in resources['rooms']:
                        names={normalized(v) for v in [room['name'],*room['aliases']] if normalized(v)!=normalized(room['code'])}
                        same_code=normalized(old['code'])==normalized(room['code'])
                        if same_code and not old_names & names: raise ValueError('该教室编号已用于其他学期的不同场地，请使用独立编号或保留同一场地的原名称别名。')
                        if old_names & names and not same_code: raise ValueError('同一场地在不同学期须使用相同稳定编号，请核对教室目录。')
            if not catalog: catalog=TimetableResourceCatalog(semester=semester,revision=0);s.add(catalog)
            catalog.settings = resources
            catalog.revision += 1
            AccountService.audit(s, actor, 'timetable_resources_saved', semester, revision=catalog.revision)
        teachers = list(s.scalars(select(User).where(User.active.is_(True), User.role == 'teacher').order_by(User.display_name, User.id)))
        return {'semester': semester, 'revision': catalog.revision if catalog else 0, 'resources': catalog.settings if catalog else None,
            'teachers': [{'id': str(t.id), 'name': t.display_name} for t in teachers],
            'legacy_rooms': calendar.settings.get('rooms', []) if calendar else [], 'notice': '资源保存不会移动现有课次；请通过冲突检查和重排预览处理旧安排。'}


def resource_suggestions(service, principal, semester):
    with service.sessions() as s:
        service.actor(s,principal,{'admin'})
        courses=list(s.scalars(select(Course).where(Course.semester==semester).order_by(Course.id)))
        if not courses: raise ValueError('请先选择课程所属学期。')
        registered={}
        for catalog in s.scalars(select(TimetableResourceCatalog).order_by(TimetableResourceCatalog.semester)):
            for room in catalog.settings.get('rooms',[]):
                for alias in [room['code'],room['name'],*room.get('aliases',[])]: registered[normalized(alias)]=room
        locations={}
        for location,title in s.execute(select(CourseSession.location,Course.title).join(Course).where(Course.semester==semester,
                CourseSession.location.is_not(None)).order_by(CourseSession.location)):
            if not normalized(location):continue
            display=registered.get(normalized(location),{}).get('name',location.strip())
            entry=locations.setdefault(normalized(display),{'name':display,'aliases':set(),'courses':[]})
            entry['aliases'].add(location.strip());entry['courses'].append(title)
        if not locations:
            locations={str(i):{'name':name,'aliases':{name},'courses':[]} for i,name in enumerate(['多媒体教室01','通用机房01','网络实训室01'])}
        rooms,counters=[],{'multimedia':0,'computer_lab':0,'specialized_lab':0}
        for key,row in sorted(locations.items()):
            name=row['name']; titles=' '.join(row['courses'])
            specialized=bool(re.search('网络实训|硬件|嵌入式|物联网|电子|网络实验',name) or
                re.search('机房|实验|实训',name) and re.search('网络|硬件|嵌入式|物联网',titles))
            lab=bool(re.search('机房|实验|实训',name) or re.search('程序设计|Python|Web|数据库|Linux|软件工程',titles,re.I))
            kind='specialized_lab' if specialized else 'computer_lab' if lab else 'multimedia'
            counters[kind]+=1
            specialty='网络与系统' if specialized else '软件与应用' if lab else '通用'
            devices=['计算机','投影','网络设备'] if specialized else ['计算机','投影','互联网'] if lab else ['投影','音响']
            rooms.append({'code':registered.get(normalized(name),{}).get('code') or 'R-'+hashlib.sha256(normalized(name).encode()).hexdigest()[:8].upper(),
                'name':name,'kind':kind,'specialty':specialty,'capacity':30 if specialized else 40 if lab else 60,
                'aliases':sorted(row['aliases']),'equipment':devices})
        requirements=[]
        for course in courses:
            if re.search('程序设计|Python|Web|数据库|Linux|软件工程|实训|实验',course.title,re.I):
                requirements.append({'course_id':str(course.id),'equipment':['计算机','投影'],'specialty':'软件与应用'})
        return {'semester':semester,'strict_rooms':True,'resource_mode':'advisory','specification_source':'editable_default',
            'rooms':rooms[:200],'availability':[],'requirements':requirements,
            'notice':'按用途拟定的初始规格：多媒体60座、通用机房40座、专业机房30座。容量与设备默认仅提示，管理员可调整；时间冲突始终阻止。'}
