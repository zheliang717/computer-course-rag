<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import PagedList from './PagedList.vue'
import SchedulePlanningPanel from './SchedulePlanningPanel.vue'
import ScheduleCandidates from './ScheduleCandidates.vue'
import { dayKey, addDays, monday, clock, stamp, localInput, lessonEnd, timeState, type Lesson, type ScheduleOptions, type ScheduleRequest, type ScheduleEvent, type SchedulePage } from '../timetable'

const props = defineProps<{ base: string; token: string; role: string; focusId: string; courseFocus: string; active: boolean }>()
const emit = defineEmits<{ action: [kind: string, lesson: Lesson]; changed: []; dirty: [value: boolean]; saving: [value: boolean] }>()
const options = ref<ScheduleOptions>({ courses: [], semesters: [], calendars: [] })
const day = ref(dayKey()), semester = ref(''), course = ref(''), tab = ref('calendar')
const items = ref<Lesson[]>([]), busy = ref(false), saving = ref(false), error = ref(''), message = ref('')
const detail = ref<Lesson | null>(null), form = ref(''), discard = ref(false), dirty = ref(false)
const requestPage = ref(1), requestFilter = ref('pending'), requests = ref<SchedulePage<ScheduleRequest>>({ items: [], total: 0, page: 1, page_size: 10 })
const eventPage = ref(1), events = ref<SchedulePage<ScheduleEvent>>({ items: [], total: 0, page: 1, page_size: 5 })
const reviewing = ref<ScheduleRequest | null>(null), eventDetail = ref<ScheduleEvent | null>(null)
const reviewReason = ref(''), confirmed = ref(false), acknowledge = ref(false)
const change = ref({ kind: 'move', scope: 'single', session_date: '', duration_minutes: 90, location: '', reason: '' })
const lessonTitle=ref(''), lessonSection=ref('')
const calendar = ref({ semester: '', start_date: '', end_date: '', holidays: '', rooms: '', expected_revision: 0 })
const batch = ref({ course_id: '', title: '', section_id: '', start_week: 1, end_week: 16, weekdays: [1], parity: 'all', start_time: '08:00', duration_minutes: 90, location: '' })
type Conflict = { message: string; course_title: string; time: string; blocking: boolean }
const preview = ref<{ items: Lesson[]; digest: string; conflicts: Conflict[] } | null>(null)
const conflicts = ref<Conflict[]>([])
let controller = new AbortController(), sequence = 0, focusSequence = 0, timer: ReturnType<typeof setInterval> | undefined
const now = ref(Date.now())
const week = computed(() => monday(day.value || dayKey())), days = computed(() => Array.from({ length: 7 }, (_,i) => addDays(week.value,i)))
const courses = computed(() => options.value.courses.filter(x => !semester.value || x.semester === semester.value))
const batchCourse = computed(() => options.value.courses.find(x => x.id === batch.value.course_id))
const labels: Record<string,string> = { pending: '待审核', approved: '已通过', rejected: '未通过', withdrawn: '已撤回', move: '调整时间', room: '更换场地', cancel: '停课', makeup: '补课安排' }
const weekday = (key: string) => ['周日','周一','周二','周三','周四','周五','周六'][new Date(`${key}T12:00:00Z`).getUTCDay()]
const minutes = (date: string) => { const [h,m] = clock(date).split(':').map(Number); return h * 60 + m }
const minHour = computed(() => Math.min(8, ...days.value.flatMap(key=>onDay(key).map(x=>dayKey(x.session_date)<key?0:Math.floor(minutes(x.session_date)/60)))))
const maxHour = computed(() => Math.min(24, Math.max(20, ...days.value.flatMap(key=>onDay(key).map(x=>dayKey(lessonEnd(x))>key?24:Math.ceil(minutes(lessonEnd(x))/60))))))
const hours = computed(() => Array.from({ length: maxHour.value-minHour.value }, (_,i) => i+minHour.value))
const columnHeight = computed(() => hours.value.length * 66)
const onDay = (key: string) => items.value.filter(x => Date.parse(x.session_date) < Date.parse(`${addDays(key,1)}T00:00:00+08:00`) && Date.parse(lessonEnd(x)) > Date.parse(`${key}T00:00:00+08:00`))
function position(item: Lesson, key: string) {
  const group = onDay(key), lanes: Lesson[][] = []
  for (const row of group) {
    let lane = lanes.find(l => Date.parse(lessonEnd(l.at(-1)!)) <= Date.parse(row.session_date))
    if (!lane) { lane=[]; lanes.push(lane) } lane.push(row)
  }
  const lane = lanes.findIndex(x => x.some(row => row.id === item.id))
  const count = Math.max(1, lanes.length)
  const endMinutes = dayKey(lessonEnd(item)) !== key ? 1440 : minutes(lessonEnd(item))
  const startMinutes = dayKey(item.session_date) < key ? 0 : minutes(item.session_date)
  return { top: `${(startMinutes-minHour.value*60)*1.1}px`, height: `${Math.max(32,(endMinutes-startMinutes)*1.1)-3}px`, left: `calc(${lane/count*100}% + 2px)`, width: `calc(${100/count}% - 4px)` }
}
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const timeout = AbortSignal.timeout(30000)
  const response = await fetch(`${props.base}/api/v1${path}`, { ...init, signal: AbortSignal.any([controller.signal, timeout]), headers: { Authorization: `Bearer ${props.token}`, 'Content-Type': 'application/json' } })
  const data = await response.json().catch(() => { throw new Error('服务暂不可用，请稍后重试。') })
  if (!response.ok) {
    if (data.detail?.conflicts) conflicts.value=data.detail.conflicts
    throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.message || (response.status === 422 ? '请检查必填内容、时间和填写范围。' : '操作失败，请重试。'))
  }
  return data as T
}
function failure(e: unknown) { if (!controller.signal.aborted) error.value=e instanceof Error ? e.message : '读取失败，请重试。' }
async function load() {
  const current=++sequence; busy.value=true; error.value=''
  try {
    const params = new URLSearchParams({ start: week.value, end: addDays(week.value,7) })
    if (semester.value) params.set('semester',semester.value)
    if (course.value) params.set('course_id',course.value)
    const result=await api<{ items: Lesson[] }>(`/timetable?${params}`)
    if (current === sequence) items.value=result.items
  } catch(e) { if (current===sequence) failure(e) } finally { if(current===sequence) busy.value=false }
}
async function loadOptions() { options.value=await api<ScheduleOptions>('/timetable/options') }
async function loadRequests() {
  busy.value=true;error.value=''
  try { requests.value=await api(`/timetable/requests?page=${requestPage.value}&page_size=10${requestFilter.value ? '&status='+requestFilter.value : ''}`) } catch(e) { failure(e) } finally { busy.value=false }
}
async function loadEvents() {
  busy.value=true;error.value=''
  try { events.value=await api(`/timetable/changes?page=${eventPage.value}&page_size=5`) } catch(e) { failure(e) } finally { busy.value=false }
}
async function refresh() { if(tab.value==='requests') await loadRequests(); else if(tab.value==='changes') await loadEvents(); else await load() }
async function open(id: string) {
  if (saving.value || form.value || reviewing.value) return
  const current=++focusSequence;error.value='';busy.value=true
  try { const row=await api<Lesson>(`/timetable/sessions/${id}`);if(current===focusSequence) detail.value=row } catch(e) { failure(e) } finally { if(current===focusSequence) busy.value=false }
}
function useCandidate(item: Lesson) {
  openForm('change')
  change.value.session_date=localInput(item.session_date)
  change.value.location=item.location||''
  change.value.kind=detail.value?.schedule_status==='cancelled'?'makeup':'move'
  dirty.value=true
}

function openForm(kind: string) {
  error.value='';conflicts.value=[];confirmed.value=false;acknowledge.value=false;preview.value=null
  if(kind==='change' && detail.value) change.value={ kind: detail.value.schedule_status==='cancelled' ? 'makeup' : 'move', scope:'single', session_date:localInput(detail.value.session_date), duration_minutes:detail.value.duration_minutes, location:detail.value.location||'', reason:'' }
  if(kind==='change' && detail.value) {lessonTitle.value=detail.value.title;lessonSection.value=detail.value.section_id||''}
  if(kind==='calendar') {
    const label=semester.value || options.value.semesters[0] || ''
    fillCalendar(label)
  }
  if(kind==='batch') batch.value.course_id=course.value || courses.value[0]?.id || ''
  form.value=kind;dirty.value=false
}
function fillCalendar(label: string) {
  const saved=options.value.calendars.find(x=>x.semester===label)
  calendar.value={ semester:label, start_date:saved?.start_date||monday(day.value), end_date:saved?.end_date||addDays(monday(day.value),111), holidays:saved?.holidays.join('\n')||'', rooms:saved?.rooms.join('\n')||'', expected_revision:saved?.revision||0 }
}
function closeForm() {
  if (saving.value) return
  if (dirty.value) { discard.value=true;return }
  form.value='';reviewing.value=null;error.value='';conflicts.value=[]
}
function discardForm() { dirty.value=false;discard.value=false;closeForm() }
function edit(event?: Event) {
  const target=event?.target as HTMLInputElement | undefined
  // Checkbox models update on change. Rendering after input but before change
  // can restore the old checked state (especially with array-valued models).
  if(event?.type==='input' && (target?.type==='checkbox' || target?.tagName==='SELECT')) return
  dirty.value=true
  if (target?.type==='checkbox' && !target.closest('fieldset')) return
  preview.value=null;confirmed.value=false;conflicts.value=[]
}
async function mutate(action: ()=>Promise<unknown>, success: string) {
  if (saving.value) return
  saving.value=true;error.value='';conflicts.value=[]
  try {
    await action();dirty.value=false;form.value='';reviewing.value=null;detail.value=null
    message.value=success;emit('changed');await refresh()
  } catch(e) { failure(e) } finally { saving.value=false }
}
async function submitChange() {
  if (!detail.value) return
  const row=detail.value, payload={ ...change.value, ...(props.role==='admin'?{title:lessonTitle.value,section_id:lessonSection.value||null}:{}), session_date:change.value.kind==='move'||change.value.kind==='makeup' ? change.value.session_date+':00+08:00' : null, expected_revision:row.revision, acknowledge_student_conflicts:acknowledge.value }
  await mutate(()=>api(`/timetable/sessions/${row.id}/${props.role==='teacher'?'requests':'change'}`,{method:'POST',body:JSON.stringify(payload)}), props.role==='teacher'?'申请已提交，等待管理员审核。':'课表已更新。')
}
function batchBody() { return { ...batch.value, section_id:batch.value.section_id||null, preview_digest:preview.value?.digest||'', confirmed:confirmed.value, acknowledge_student_conflicts:acknowledge.value } }
async function previewBatch() {
  if(saving.value) return
  saving.value=true;error.value='';preview.value=null;confirmed.value=false;conflicts.value=[]
  try { preview.value=await api('/timetable/batch/preview',{method:'POST',body:JSON.stringify(batchBody())}) } catch(e) { failure(e) } finally { saving.value=false }
}
async function saveCalendar() {
  const split=(value: string)=>value.split(/\r?\n/).map(x=>x.trim()).filter(Boolean)
  await mutate(async()=>{ await api('/timetable/calendar',{method:'PUT',body:JSON.stringify({...calendar.value,holidays:split(calendar.value.holidays),rooms:split(calendar.value.rooms)})});await loadOptions() },'校历已保存。已有课次未被自动移动。')
}
function beginReview(item: ScheduleRequest) { reviewing.value=item;reviewReason.value='';confirmed.value=false;acknowledge.value=false;dirty.value=false;error.value='';conflicts.value=[] }
async function review(approved: boolean) {
  if(!reviewing.value) return
  const id=reviewing.value.id
  await mutate(()=>api(`/timetable/requests/${id}/review`,{method:'POST',body:JSON.stringify({approved,reason:reviewReason.value,confirmed:confirmed.value,acknowledge_student_conflicts:acknowledge.value})}),approved?'申请已通过，正式课表已更新。':'申请已驳回，课表保持不变。')
}
async function withdraw(item: ScheduleRequest) {
  reviewing.value=item;form.value='withdraw';dirty.value=false;confirmed.value=false;error.value=''
}
async function complete() {
  if(!detail.value) return
  const row=detail.value
  await mutate(()=>api(`/course-sessions/${row.id}`,{method:'PATCH',body:JSON.stringify({completed:!row.completed})}),row.completed?'已撤销授课确认。':'已确认本节授课。')
}
function action(kind: string) { if(detail.value) { emit('action',kind,detail.value);detail.value=null } }
function beforeUnload(e: BeforeUnloadEvent) { if(dirty.value) {e.preventDefault();e.returnValue=''} }
watch(dirty,value=>emit('dirty',value))
watch(saving,value=>emit('saving',value))
watch([week,semester,course],()=>{if(props.active) void load()})
watch(semester,()=>{if(course.value&&!courses.value.some(x=>x.id===course.value)) course.value=''})
watch([requestPage,requestFilter],()=>{if(props.active&&tab.value==='requests') void loadRequests()})
watch(eventPage,()=>{if(props.active&&tab.value==='changes') void loadEvents()})
watch(tab,()=>void refresh())
watch(()=>props.focusId,id=>{if(id) void open(id)})
watch(()=>props.courseFocus,id=>{if(id){course.value=id;semester.value='';tab.value='calendar'}})
watch(()=>props.active,value=>{if(value) void refresh()})
onMounted(async()=>{
  window.addEventListener('beforeunload',beforeUnload)
  try {await loadOptions();if(props.courseFocus)course.value=props.courseFocus;await load();if(props.focusId)await open(props.focusId)} catch(e){failure(e)}
  timer=setInterval(()=>{now.value=Date.now();if(props.active&&!busy.value&&!saving.value&&!form.value&&!reviewing.value&&!detail.value)void refresh()},60000)
})
onBeforeUnmount(()=>{controller.abort();clearInterval(timer);window.removeEventListener('beforeunload',beforeUnload);emit('dirty',false)})
defineExpose({ hasUnsaved:()=>dirty.value, discardEdits:discardForm, signature:()=>JSON.stringify([form.value,change.value,lessonTitle.value,lessonSection.value,calendar.value,batch.value,reviewReason.value,confirmed.value,acknowledge.value]) })
</script>

<template>
  <section class="timetable" aria-label="课程课表" :aria-busy="busy || saving">
    <header class="tt-heading"><div><small>YOUR TIME, WELL PLANNED</small><h2>{{ role==='admin'?'排课管理':role==='teacher'?'教学课表':'我的课表' }}</h2><p>{{ role==='admin'?'统一安排每一次教学，审核教师调课申请。':role==='teacher'?'掌握授课安排，提交调课申请与确认授课。':'这一周的学习安排，一眼就清楚。' }}</p></div><div v-if="role==='admin'" class="tt-actions"><button type="button" @click="openForm('calendar')">校历与场地</button><button type="button" class="tt-primary" @click="openForm('batch')">＋ 生成课次</button></div></header>
    <nav class="tt-tabs" aria-label="课表功能"><button type="button" :aria-pressed="tab==='calendar'" @click="tab='calendar'">周课表</button><button v-if="role!=='student'" type="button" :aria-pressed="tab==='requests'" @click="tab='requests'">{{ role==='admin'?'调课审批':'我的申请' }}</button><button type="button" :aria-pressed="tab==='changes'" @click="tab='changes'">课表变更</button></nav>
    <p v-if="message" class="tt-success" role="status">{{ message }} <button type="button" aria-label="关闭提示" @click="message=''">×</button></p>
    <p v-if="error && !form && !reviewing" class="tt-error" role="alert">{{ error }} <button type="button" :disabled="busy" @click="refresh">重试</button></p>
    <p v-if="busy || saving" class="tt-loading" role="status"><span class="tt-spinner" />{{ saving?'正在保存，请稍候…':'正在更新课表…' }}</p>
    <template v-if="tab==='calendar'">
      <div class="tt-toolbar"><div class="tt-date-nav"><button type="button" aria-label="上一周" @click="day=addDays(day,-7)">‹</button><button type="button" @click="day=dayKey()">今天</button><button type="button" aria-label="下一周" @click="day=addDays(day,7)">›</button><label><span class="sr-only">跳转日期</span><input v-model="day" type="date" required /></label></div><div class="tt-filters"><label>学期<select v-model="semester" aria-label="筛选学期"><option value="">全部学期</option><option v-for="label in options.semesters" :key="label">{{ label }}</option></select></label><label>课程<select v-model="course" aria-label="筛选课程"><option value="">全部课程</option><option v-for="item in courses" :key="item.id" :value="item.id">{{ item.title }}</option></select></label></div></div>
      <div class="tt-week-label"><strong>{{ week }} — {{ addDays(week,6) }}</strong><span>北京时间 · 点击课次查看详情</span><button type="button" :disabled="busy" @click="load">刷新</button></div>
      <SchedulePlanningPanel v-if="role==='admin'" :request="api" :semesters="options.semesters" :semester="semester" :week="week" :courses="options.courses" :lessons="items" @changed="loadOptions();load();emit('changed')" @open="open" />
      <div class="tt-mobile-days" aria-label="选择上课日期"><button v-for="key in days" :key="key" type="button" :aria-pressed="day===key" :class="{today:key===dayKey(now)}" @click="day=key"><small>{{ weekday(key) }}</small><strong>{{ key.slice(8) }}</strong><i :class="{occupied:onDay(key).length}" /></button></div>
      <div class="tt-week-scroll"><div class="tt-week"><div class="tt-week-corner">时间</div><div v-for="key in days" :key="key" class="tt-day-heading" :class="{today:key===dayKey(now)}"><strong>{{ weekday(key) }}</strong><small>{{ key.slice(5).replace('-',' / ') }}</small></div><div class="tt-hours" :style="{height:columnHeight+'px'}"><span v-for="hour in hours" :key="hour" :style="{top:(hour-minHour)*66+'px'}">{{ String(hour).padStart(2,'0') }}:00</span></div><div v-for="key in days" :key="key" class="tt-day-column" :style="{height:columnHeight+'px'}"><button v-for="item in onDay(key)" :key="item.id" type="button" class="tt-event" :class="{cancelled:item.schedule_status==='cancelled',live:timeState(item,now)==='正在上课',taught:item.completed}" :style="position(item,key)" :title="`${item.course_title} · ${item.title} · ${stamp(item.session_date)}`" @click="open(item.id)"><small>{{ clock(item.session_date) }}—{{ clock(lessonEnd(item)) }}</small><strong>{{ item.course_title }}</strong><span>{{ item.title }}</span><small>{{ item.location || '地点待通知' }}</small><b v-if="item.schedule_status==='cancelled'">已停课</b><b v-else-if="item.completed">已授课</b></button></div></div></div>
      <div class="tt-day-agenda"><h3>{{ weekday(day) }} · {{ day }} <span>{{ onDay(day).length }} 节</span></h3><button v-for="item in onDay(day)" :key="item.id" type="button" class="tt-agenda-item" :class="{cancelled:item.schedule_status==='cancelled',live:timeState(item,now)==='正在上课'}" @click="open(item.id)"><span class="tt-agenda-time"><strong>{{ clock(item.session_date) }}</strong><small>{{ clock(lessonEnd(item)) }}</small></span><span class="tt-agenda-info"><strong>{{ item.course_title }}</strong><span>{{ item.title }}</span><small>{{ item.location || '地点待通知' }} · {{ item.teacher_name || '教师待公布' }}</small><b>{{ timeState(item,now) }}{{ item.completed?' · 已授课':'' }}</b></span><span aria-hidden="true">›</span></button><p v-if="!onDay(day).length&&!busy" class="tt-empty">今天没有课程，点击上方日期查看其他安排。</p></div>
      <p v-if="!items.length&&!busy&&!error" class="tt-empty tt-desktop-empty">本周没有课次安排，可以切换日期、学期或课程。</p>
    </template>
    <section v-else-if="tab==='requests'" class="tt-list-panel"><div class="tt-list-heading"><h3>{{ role==='admin'?'待办与审批记录':'调课申请记录' }}</h3><label>申请状态<select v-model="requestFilter" @change="requestPage=1"><option value="">全部状态</option><option v-for="status in ['pending','approved','rejected','withdrawn']" :key="status" :value="status">{{ labels[status] }}</option></select></label></div><button v-for="item in requests.items" :key="item.id" type="button" class="tt-request-row" @click="beginReview(item)"><span class="tt-status" :class="item.status">{{ labels[item.status] }}</span><span><strong>{{ item.course_title }} · {{ labels[item.kind] }}</strong><small>{{ item.requester }} · {{ item.original.length }} 个课次 · {{ stamp(item.created_at) }}</small><span>{{ item.reason }}</span></span><b>查看 ›</b></button><p v-if="!requests.items.length&&!busy" class="tt-empty">暂无{{ labels[requestFilter] || '' }}申请。{{ role==='teacher'?'点击课表中的课次，即可申请调整。':'' }}</p><div class="tt-pager"><span>共 {{ requests.total }} 条</span><button type="button" :disabled="busy||requestPage<=1" @click="requestPage--">上一页</button><span>{{ requestPage }}</span><button type="button" :disabled="busy||requestPage*10>=requests.total" @click="requestPage++">下一页</button></div></section>
    <section v-else class="tt-list-panel"><h3>最近课表变更</h3><button v-for="item in events.items" :key="item.id" type="button" class="tt-history-row" @click="eventDetail=item"><span><strong>{{ item.course_title }}</strong><small>{{ stamp(item.created_at) }} · {{ item.after.length }} 个课次</small><span>{{ item.reason }}</span></span><b>查看详情 ›</b></button><p v-if="!events.items.length&&!busy" class="tt-empty">暂无课表变更通知。</p><div class="tt-pager"><span>共 {{ events.total }} 条</span><button type="button" :disabled="busy||eventPage<=1" @click="eventPage--">上一页</button><span>{{ eventPage }}</span><button type="button" :disabled="busy||eventPage*5>=events.total" @click="eventPage++">下一页</button></div></section>

    <DetailDialog v-if="detail && !form" :title="detail.course_title" kicker="课次详情" @close="detail=null"><div class="tt-detail"><span class="tt-status">{{ timeState(detail,now) }}</span><h3>{{ detail.title }}</h3><dl><dt>上课时间</dt><dd>{{ stamp(detail.session_date) }} — {{ clock(lessonEnd(detail)) }}<template v-if="dayKey(lessonEnd(detail))!==dayKey(detail.session_date)">（{{ dayKey(lessonEnd(detail)) }}）</template></dd><dt>上课场地</dt><dd>{{ detail.location || '地点待通知' }}</dd><dt>任课教师</dt><dd>{{ detail.teacher_name || '待公布' }}</dd><dt>关联章节</dt><dd>{{ detail.section_title || '未关联章节' }}</dd><dt>所属学期</dt><dd>{{ detail.semester || '未设置' }}</dd><dt>授课记录</dt><dd>{{ detail.completed?'教师已确认授课':'尚未确认授课' }}</dd></dl><div class="tt-actions"><button type="button" @click="action('course')">课程详情</button><button type="button" @click="action('materials')">学习资料</button><button type="button" @click="action('assignments')">对应作业</button><button type="button" class="tt-primary" @click="action('assistant')">{{ role==='teacher'?'AI 帮我备课':'AI 帮我预习' }}</button></div></div><ScheduleCandidates v-if="role!=='student'&&!detail.completed" :key="detail.id" :lesson="detail" :request="api" @choose="useCandidate" /><template #footer><span>{{ detail.duration_minutes }} 分钟 · 北京时间</span><div class="tt-actions"><button v-if="role!=='student' && detail.schedule_status!=='cancelled' && (detail.completed || Date.parse(detail.session_date)<=now)" type="button" :disabled="saving" @click="complete">{{ detail.completed?'撤销授课确认':'确认已授课' }}</button><button v-if="role!=='student'&&!detail.completed" type="button" class="tt-primary" @click="openForm('change')">{{ role==='teacher'?'申请调课':'调整安排' }}</button></div></template></DetailDialog>

    <DetailDialog v-if="form && form!=='withdraw'" :title="form==='calendar'?'校历与场地':form==='batch'?'按规则生成课次':role==='teacher'?'提交调课申请':'调整课次安排'" :close-disabled="saving" @close="closeForm">
      <form id="timetable-form" class="tt-form" @input="edit" @change="edit" @submit.prevent="form==='calendar'?saveCalendar():form==='batch'?mutate(()=>api('/timetable/batch/publish',{method:'POST',body:JSON.stringify(batchBody())}),'课次已发布。'):submitChange()">
        <div v-if="form==='change' && role==='admin' && detail" class="tt-form-grid"><label>课次主题<input v-model="lessonTitle" required maxlength="200" /></label><label>关联章节<select v-model="lessonSection"><option value="">不关联章节</option><option v-for="section in options.courses.find(x=>x.id===detail!.course_id)?.sections||[]" :key="section.id" :value="section.id">{{ section.title }}</option></select></label></div>
        <template v-if="form==='change' && detail"><div class="tt-summary"><strong>{{ detail.course_title }} · {{ detail.title }}</strong><p>{{ stamp(detail.session_date) }} — {{ clock(lessonEnd(detail)) }} · {{ detail.location || '地点待通知' }}</p></div><div class="tt-form-grid"><label>调整类型<select v-model="change.kind"><option v-if="detail.schedule_status!=='cancelled'" value="move">调整时间</option><option v-if="detail.schedule_status!=='cancelled'" value="room">更换场地</option><option value="cancel">停课</option><option value="makeup">补课安排</option></select></label><label>影响范围<select v-model="change.scope"><option value="single">仅本次课</option><option v-if="detail.rule_id" value="following">此规则的本次及后续课次</option></select></label><label v-if="change.kind==='move'||change.kind==='makeup'">新的上课时间（北京时间）<input v-model="change.session_date" type="datetime-local" required /></label><label v-if="change.kind!=='cancel'">时长（分钟）<input v-model.number="change.duration_minutes" type="number" min="15" max="480" required /></label><label v-if="change.kind!=='cancel'">新的上课场地<input v-model="change.location" maxlength="200" /></label></div><label>调整原因<textarea v-model="change.reason" required minlength="5" maxlength="1000" rows="3" placeholder="请说明原因，方便管理员核对安排" /></label></template>
        <template v-else-if="form==='calendar'"><div class="tt-form-grid"><label class="tt-full">学期<select :value="calendar.semester" required @change="fillCalendar(($event.target as HTMLSelectElement).value)"><option v-for="label in options.semesters" :key="label">{{ label }}</option></select></label><label>第一周周一<input v-model="calendar.start_date" type="date" required /></label><label>学期结束日期<input v-model="calendar.end_date" type="date" :min="calendar.start_date" required /></label><label>停课日期（每行一个日期）<textarea v-model="calendar.holidays" rows="5" placeholder="2026-10-01" /></label><label>可用场地（每行一处）<textarea v-model="calendar.rooms" rows="5" placeholder="教学楼 A101" /></label></div><p class="tt-note">保存校历用于后续排课，不会重排已有课次。</p></template>
        <template v-else-if="form==='batch'"><div class="tt-form-grid"><label class="tt-full">课程<select v-model="batch.course_id" required @change="batch.section_id='' "><option value="" disabled>请选择课程</option><option v-for="item in options.courses" :key="item.id" :value="item.id">{{ item.title }} · {{ item.semester || '未设置学期' }}</option></select></label><label>课次主题<input v-model="batch.title" required maxlength="200" /></label><label>关联章节<select v-model="batch.section_id"><option value="">不关联章节</option><option v-for="section in batchCourse?.sections || []" :key="section.id" :value="section.id">{{ section.title }}</option></select></label><label>开始周<input v-model.number="batch.start_week" type="number" required min="1" max="53" /></label><label>结束周<input v-model.number="batch.end_week" type="number" required :min="batch.start_week" max="53" /></label><fieldset class="tt-full"><legend>上课日</legend><label v-for="(name,i) in ['一','二','三','四','五','六','日']" :key="i" class="tt-check"><input v-model="batch.weekdays" type="checkbox" :value="i+1" />周{{ name }}</label></fieldset><label>重复方式<select v-model="batch.parity"><option value="all">每周</option><option value="odd">单周</option><option value="even">双周</option></select></label><label>开始时间（北京时间）<input v-model="batch.start_time" type="time" required /></label><label>时长（分钟）<input v-model.number="batch.duration_minutes" type="number" required min="15" max="480" /></label><label>上课场地<input v-model="batch.location" list="tt-rooms" maxlength="200" /><datalist id="tt-rooms"><option v-for="room in options.calendars.find(x=>x.semester===batchCourse?.semester)?.rooms || []" :key="room" :value="room" /></datalist></label></div><p class="tt-note">按所选学期校历生成，停课日期自动跳过。发布前请预览全部日期。</p><button type="button" :disabled="saving||!batch.course_id||!batch.title.trim()||!batch.weekdays.length" @click="previewBatch">{{ saving?'正在生成预览…':'预览课次与冲突' }}</button><section v-if="preview" class="tt-preview"><h3>将新增 {{ preview.items.length }} 个课次</h3><PagedList :items="preview.items" :page-size="6" label="排课预览" v-slot="{items: rows}"><div v-for="item in rows" :key="item.id" class="tt-preview-row"><strong>{{ stamp(item.session_date) }} — {{ clock(lessonEnd(item)) }}</strong><span>{{ item.title }} · {{ item.location || '地点待通知' }}</span></div></PagedList><p v-if="!preview.conflicts.length" class="tt-success">未发现时间冲突。</p><p v-for="(item,i) in preview.conflicts" :key="i" class="tt-error">{{ item.blocking?'不能发布':'请核实' }}：{{ item.message }} · {{ item.course_title }} · {{ stamp(item.time) }}</p><label class="tt-check"><input v-model="confirmed" type="checkbox" />我已核对预览课次，确认发布</label></section></template>
      </form>
      <p v-if="error" class="tt-error" role="alert">{{ error }}</p><p v-for="(item,i) in conflicts" :key="i" class="tt-error">{{ item.message }} · {{ item.course_title }} · {{ stamp(item.time) }}</p>
      <template #footer><span>{{ form==='change'&&role==='teacher'?'提交后等待管理员审核':'修改仅在保存 / 发布后生效' }}</span><button type="submit" form="timetable-form" class="tt-primary" :disabled="saving||(form==='batch'&&(!preview||!confirmed||preview.conflicts.some(x=>x.blocking)))">{{ saving?'正在处理…':form==='calendar'?'保存校历':form==='batch'?'确认发布':role==='teacher'?'提交申请':'保存安排' }}</button></template>
    </DetailDialog>

    <DetailDialog v-if="reviewing" :title="form==='withdraw'?'撤回调课申请':'调课申请详情'" :close-disabled="saving" @close="closeForm"><div class="tt-summary"><span class="tt-status" :class="reviewing.status">{{ labels[reviewing.status] }}</span><h3>{{ reviewing.course_title }} · {{ labels[reviewing.kind] }}</h3><p>{{ reviewing.requester }} · {{ stamp(reviewing.created_at) }}</p><p>{{ reviewing.reason }}</p><p v-if="reviewing.review_reason">审核意见：{{ reviewing.review_reason }}</p></div><PagedList :items="reviewing.original" :page-size="5" label="受影响课次" v-slot="{items: rows}"><div v-for="before in rows" :key="before.id" class="tt-comparison"><strong>{{ before.title }}</strong><div><span>原安排</span><p>{{ stamp(before.session_date) }} — {{ clock(lessonEnd(before)) }} · {{ before.location || '地点待通知' }}</p></div><div v-for="after in reviewing.proposed.filter(x=>x.id===before.id)" :key="after.id"><span>申请调整为</span><p>{{ after.schedule_status==='cancelled'?'停课':`${stamp(after.session_date)} — ${clock(lessonEnd(after))} · ${after.location || '地点待通知'}` }}</p></div></div></PagedList><template v-if="role==='admin'&&reviewing.status==='pending'"><label class="tt-field">审核意见<textarea v-model="reviewReason" rows="3" minlength="5" maxlength="1000" @input="dirty=true" /></label><label class="tt-check"><input v-model="confirmed" type="checkbox" @change="dirty=true" />已核对所有受影响课次，确认本次审核</label></template><p v-if="error" class="tt-error" role="alert">{{ error }}</p><p v-for="(item,i) in conflicts" :key="i" class="tt-error">{{ item.message }} · {{ item.course_title }} · {{ stamp(item.time) }}</p><template #footer><span>{{ reviewing.original.length }} 个课次</span><div class="tt-actions"><template v-if="role==='admin'&&reviewing.status==='pending'"><button type="button" :disabled="saving||!confirmed||reviewReason.trim().length<5" @click="review(false)">驳回申请</button><button type="button" class="tt-primary" :disabled="saving||!confirmed||reviewReason.trim().length<5" @click="review(true)">通过并更新课表</button></template><button v-if="role==='teacher'&&reviewing.status==='pending'" type="button" :disabled="saving" @click="form==='withdraw'?mutate(()=>api(`/timetable/requests/${reviewing!.id}/withdraw`,{method:'POST'}),'申请已撤回，课表未改变。'):withdraw(reviewing)">{{ form==='withdraw'?'确认撤回申请':'撤回申请' }}</button><button v-if="role==='teacher'&&['rejected','withdrawn'].includes(reviewing.status)" type="button" @click="{const id=reviewing.original[0]?.id;reviewing=null;if(id)open(id)}">重新打开课次申请</button></div></template></DetailDialog>
    <DetailDialog v-if="eventDetail" title="课表变更详情" @close="eventDetail=null"><h3>{{ eventDetail.course_title }}</h3><p>{{ eventDetail.reason }} · {{ stamp(eventDetail.created_at) }}</p><PagedList :items="eventDetail.after" :page-size="5" label="变更课次" v-slot="{items: rows}"><div v-for="after in rows" :key="after.id" class="tt-comparison"><strong>{{ after.title }}</strong><p v-for="before in eventDetail.before.filter(x=>x.id===after.id)" :key="before.id">原：{{ stamp(before.session_date) }} · {{ before.location || '地点待通知' }}</p><p>现：{{ after.schedule_status==='cancelled'?'已停课':`${stamp(after.session_date)} — ${clock(lessonEnd(after))} · ${after.location || '地点待通知'}` }}</p><button type="button" @click="eventDetail=null;open(after.id)">打开课次 ›</button></div></PagedList></DetailDialog>
    <DetailDialog v-if="discard" title="放弃未保存的修改？" size="small" @close="discard=false"><p>已填写的内容尚未提交。</p><template #footer><button type="button" @click="discard=false">继续填写</button><button type="button" @click="discardForm">放弃修改</button></template></DetailDialog>
  </section>
</template>

<style scoped>
.timetable{color:#263f5e;min-width:0}.tt-heading{display:flex;justify-content:space-between;align-items:center;gap:18px;margin-bottom:20px}.tt-heading small{font-size:10px;letter-spacing:.13em;color:#7e92b0}.tt-heading h2{font-size:clamp(21px,2vw,28px);margin:7px 0}.tt-heading p,.tt-note{font-size:12px;color:#7e90a8;line-height:1.8}.tt-actions{display:flex;flex-wrap:wrap;gap:8px;align-items:center}.timetable button,.tt-form button,.tt-comparison button{font-size:12px;background:#edf3fb;color:#416695;border:1px solid #dbe5f2;border-radius:10px;padding:10px 14px}.timetable button:disabled{opacity:.5;cursor:not-allowed}.timetable .tt-primary,.tt-primary{background:#346fc3!important;color:white!important;border-color:#346fc3!important}.tt-tabs{display:flex;gap:6px;border-bottom:1px solid #dfe7f1;padding-bottom:12px;margin-bottom:18px}.tt-tabs button[aria-pressed=true]{background:#e4edfd;color:#235da6;border-color:#bbd1f1}.tt-toolbar{display:flex;align-items:end;justify-content:space-between;gap:12px;flex-wrap:wrap}.tt-date-nav{display:flex;gap:6px;align-items:center}.tt-filters{display:flex;gap:12px;min-width:0}.tt-filters label,.tt-list-heading label{display:grid;gap:5px;font-size:10px;color:#7b8fa9;min-width:0}.timetable input,.timetable select,.tt-form input,.tt-form select,.tt-form textarea,.tt-field textarea{border:1px solid #d9e3f1;border-radius:10px;color:#2b4669;background:#fff;font:inherit;font-size:12px;padding:10px 12px;min-width:0;max-width:100%;box-sizing:border-box}.tt-filters select{max-width:230px}.tt-week-label{display:flex;gap:14px;align-items:center;margin:20px 0;font-size:13px;flex-wrap:wrap}.tt-week-label span{color:#8090a7;font-size:11px}.tt-week-label button{margin-left:auto}.tt-week-scroll{overflow:auto;border:1px solid #dfe7f1;border-radius:14px;background:white}.tt-week{display:grid;grid-template-columns:55px repeat(7,minmax(100px,1fr));min-width:800px}.tt-week-corner,.tt-day-heading{padding:14px 4px;text-align:center;font-size:11px;border-bottom:1px solid #e6edf5;background:#f9fbfe}.tt-day-heading{display:grid;gap:5px}.tt-day-heading small{font-size:10px;color:#8192aa}.tt-day-heading.today{background:#eaf2ff;color:#2866b2}.tt-hours{position:relative;background:#fbfcfe}.tt-hours span{position:absolute;right:7px;font-size:10px;color:#92a0b4;transform:translateY(4px)}.tt-day-column{position:relative;border-left:1px solid #edf1f6;background:repeating-linear-gradient(to bottom,transparent 0,transparent 65px,#edf1f6 65px,#edf1f6 66px)}.timetable .tt-event{position:absolute;display:flex;flex-direction:column;align-items:start;gap:4px;text-align:left;padding:8px 7px;background:#edf3ff;color:#315583;border:1px solid #cfddf3;border-left:3px solid #6896d9;border-radius:7px;overflow:hidden;min-height:0}.tt-event strong{font-size:11px;line-height:1.4}.tt-event span{font-size:10px;font-weight:400;line-height:1.4}.tt-event small{font-size:9px;line-height:1.3}.tt-event b{font-size:9px}.timetable .tt-event.live{background:#e8f7f0;border-color:#9acfb9;border-left-color:#3a9a78}.timetable .tt-event.cancelled,.tt-agenda-item.cancelled{background:#f4f4f6;color:#8f97a4;border-color:#dcdfe6;border-left-color:#b4bcc8}.tt-event.cancelled strong{text-decoration:line-through}.tt-mobile-days,.tt-day-agenda{display:none}.tt-loading{font-size:12px;color:#5680ae;display:flex;gap:8px;align-items:center}.tt-spinner{display:inline-block;width:14px;height:14px;border:2px solid #cfdef2;border-top-color:#4382cd;border-radius:50%;animation:tt-spin .8s linear infinite;flex:none}@keyframes tt-spin{to{transform:rotate(360deg)}}.tt-success,.tt-error{padding:12px 14px;background:#edf8f1;color:#35775b;font-size:12px;border-radius:10px;line-height:1.8;overflow-wrap:anywhere}.tt-error{background:#fff0eb;color:#ad5e4f}.tt-success button{float:right;background:transparent;border:0;padding:0 5px}.tt-empty{font-size:13px;color:#8595a9;padding:28px 12px;text-align:center;line-height:1.8}.tt-list-panel{border:1px solid #e1e8f2;background:white;border-radius:16px;padding:22px}.tt-list-heading{display:flex;gap:12px;align-items:center;justify-content:space-between}.tt-list-panel h3{font-size:16px}.timetable .tt-request-row,.timetable .tt-history-row{background:white;border:0;border-bottom:1px solid #edf0f5;border-radius:0;display:flex;gap:18px;align-items:center;width:100%;text-align:left;padding:20px 0}.tt-request-row>span:nth-child(2),.tt-history-row>span{display:grid;gap:7px;flex:1;min-width:0}.tt-request-row strong,.tt-history-row strong{font-size:13px}.tt-request-row small,.tt-history-row small{font-size:11px;color:#8999ae;font-weight:400}.tt-request-row>span>span,.tt-history-row>span>span{font-size:12px;color:#7186a2;font-weight:400;overflow-wrap:anywhere}.tt-status{display:inline-flex;align-self:start;flex:none;font-size:11px;background:#edf2fa;color:#55749d;border-radius:6px;padding:6px 9px}.tt-status.pending{background:#fff3df;color:#a97830}.tt-status.approved{background:#e9f6ee;color:#468564}.tt-status.rejected{background:#fff0eb;color:#aa6756}.tt-pager{display:flex;gap:12px;justify-content:end;align-items:center;font-size:12px;color:#8093aa;margin-top:20px}.tt-detail h3{font-size:21px}.tt-detail dl{display:grid;grid-template-columns:95px minmax(0,1fr);gap:18px;font-size:13px;margin:25px 0 30px}.tt-detail dt{color:#7c8fa8}.tt-detail dd{margin:0;overflow-wrap:anywhere}.tt-detail .tt-actions button{font-size:12px}.tt-form,.tt-field{display:grid;gap:18px;color:#344d6a;font-size:12px}.tt-form label,.tt-field{display:grid;gap:9px;font-size:12px}.tt-form-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.tt-full{grid-column:1/-1}.tt-form textarea,.tt-field textarea{resize:vertical;line-height:1.8;width:100%}.tt-form fieldset{border:1px solid #e2e9f3;border-radius:10px;display:flex;flex-wrap:wrap;gap:12px;padding:15px}.tt-check,.tt-form .tt-check{display:flex;align-items:start;gap:9px;font-size:12px;font-weight:400;line-height:1.8;margin:12px 0;color:#617998}.tt-check input[type=checkbox]{flex:none;width:17px;height:17px;margin:2px 0;accent-color:#3976c8}.tt-summary{background:#f5f8fd;border:1px solid #e3ebf6;border-radius:12px;padding:18px;font-size:13px;line-height:1.8;margin-bottom:20px}.tt-summary h3{font-size:16px}.tt-summary p{overflow-wrap:anywhere;margin:8px 0;color:#7890aa}.tt-preview-row{display:grid;gap:6px;padding:12px 0;border-bottom:1px solid #e9eef6;font-size:12px}.tt-preview-row span{color:#8395ab}.tt-comparison{font-size:12px;line-height:1.8;padding:18px 0;border-bottom:1px solid #e5ecf5}.tt-comparison>div{display:grid;grid-template-columns:80px 1fr;gap:12px;margin-top:12px}.tt-comparison p{margin:0;overflow-wrap:anywhere}.tt-comparison>div>span{color:#8b9db4}.tt-comparison>div:last-child{color:#3875b6}.sr-only{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0,0,0,0)}button:focus-visible,input:focus-visible,select:focus-visible,textarea:focus-visible{outline:3px solid #a8c8ef;outline-offset:2px}
@media(max-width:900px){.tt-heading{align-items:start;flex-direction:column}.tt-toolbar{align-items:stretch}.tt-filters{width:100%}.tt-filters label{flex:1}.tt-filters select{max-width:100%;width:100%}}
@media(max-width:700px){.tt-week-scroll,.tt-desktop-empty{display:none}.tt-mobile-days{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:3px;margin:14px 0}.tt-mobile-days button{background:white;border-color:transparent;display:grid;justify-items:center;gap:7px;padding:10px 2px}.tt-mobile-days button[aria-pressed=true]{background:#346fc3;color:white}.tt-mobile-days small{font-size:10px;font-weight:400}.tt-mobile-days strong{font-size:16px}.tt-mobile-days i{height:4px;width:4px;border-radius:50%;background:transparent}.tt-mobile-days i.occupied{background:#91b4e7}.tt-mobile-days .today:not([aria-pressed=true]){border-color:#b4cdeb;color:#346fc3}.tt-day-agenda{display:block}.tt-day-agenda h3{font-size:14px;margin:22px 0 14px;display:flex;justify-content:space-between}.tt-day-agenda h3 span{font-size:11px;color:#8597ae;font-weight:400}.timetable .tt-agenda-item{display:flex;align-items:center;gap:14px;width:100%;text-align:left;background:white;color:#3e5977;margin:12px 0;padding:16px 12px;border:1px solid #e0e8f4;border-radius:13px}.timetable .tt-agenda-item.live{background:#f0faf5;border-color:#a9d8c3}.tt-agenda-time{align-self:start;display:grid;gap:7px;border-right:1px solid #e6ecf5;padding-right:12px;flex:none}.tt-agenda-time strong{font-size:16px}.tt-agenda-time small{font-size:11px;font-weight:400;color:#8197b1}.tt-agenda-info{display:grid;gap:7px;flex:1;min-width:0;overflow-wrap:anywhere}.tt-agenda-info strong{font-size:13px}.tt-agenda-info>span{font-size:12px;font-weight:400}.tt-agenda-info small{font-size:10px;font-weight:400;color:#7c91ac}.tt-agenda-info b{font-size:10px;color:#6e8eb8}.tt-week-label{font-size:11px;gap:8px;margin:14px 0}.tt-week-label span{font-size:10px}.tt-date-nav{flex-wrap:wrap;width:100%}.tt-date-nav label{flex:1}.tt-date-nav input{width:100%}.tt-date-nav button{padding:10px 12px}.tt-heading p{font-size:11px}.tt-list-panel{padding:15px}.tt-request-row{gap:9px!important;flex-wrap:wrap}.tt-request-row>b{display:none}.tt-request-row>span:nth-child(2){flex-basis:65%}.tt-history-row>b{font-size:10px;flex:none}.tt-pager{gap:7px;font-size:10px}.tt-pager button{font-size:10px;padding:8px}.tt-form-grid{grid-template-columns:1fr}.tt-full{grid-column:auto}.tt-detail dl{grid-template-columns:72px 1fr;font-size:12px;gap:15px}.tt-detail h3{font-size:18px}.tt-comparison>div{grid-template-columns:1fr;gap:5px}.tt-form input,.tt-form select,.tt-form textarea{font-size:13px}}
@media(prefers-reduced-motion:reduce){.tt-spinner{animation:none}}
.tt-heading>div>small,.tt-heading h2{display:none}.tt-heading{margin-bottom:14px}.tt-heading p{margin:0}
@media(max-width:700px){.timetable{padding-bottom:70px}.tt-heading{gap:10px}.tt-heading p{font-size:11px}}
</style>
