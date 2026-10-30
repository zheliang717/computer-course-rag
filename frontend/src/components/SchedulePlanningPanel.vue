<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import PagedList from './PagedList.vue'
import { addDays, stamp, type Lesson, type ScheduleCourse } from '../timetable'
type Room = { code: string; name: string; capacity: number | null; aliases: string[]; equipment: string[]; kind: string; specialty: string }
type Availability = { teacher_id: string; slots: { weekday: number; start: string; end: string }[] }
type Requirement = { course_id: string; equipment: string[]; specialty: string }
type Resources = { strict_rooms: boolean; resource_mode: string; specification_source: string; rooms: Room[]; availability: Availability[]; requirements: Requirement[] }
type ResourceState = { semester: string; revision: number; resources: Resources | null; teachers: { id: string; name: string }[]; legacy_rooms: string[] }
type Conflict = { session_id: string; other_id: string; message: string; course_title: string; time: string }
type Plan = { original: Lesson[]; proposed: (Lesson & { resource_warnings?: string[]; location_display?: string })[]; ready: boolean; signature: string; unresolved: { id: string; title: string; reason: string }[]; notice: string; checked_candidates: number }
const props = defineProps<{ request: (path: string, options?: RequestInit) => Promise<unknown>; semesters: string[]; semester: string; week: string; courses: ScheduleCourse[]; lessons: Lesson[] }>()
const emit = defineEmits<{ changed: []; open: [id: string] }>()
const mode = ref(''), semester = ref(''), busy = ref(false), dirty = ref(false), error = ref(''), message = ref(''), resourceState = ref<ResourceState | null>(null), resources = ref<Resources>({ strict_rooms: true, resource_mode: 'advisory', specification_source: 'administrator', rooms: [], availability: [], requirements: [] })
const dates = ref({ start_date: props.week, end_date: addDays(props.week,6), day_start: '08:00', day_end: '20:00', weekdays: [1,2,3,4,5], rooms: [] as string[] }), selected = ref<string[]>([]), plan = ref<Plan | null>(null), confirmed = ref(false), auditQuery = ref(''), reason = ref('管理员核对后确认辅助重排')
const empty: Conflict[] = [], rows = computed(() => props.lessons.filter(x => !x.completed && x.schedule_status!=='cancelled'))
const relevantCourses = computed(() => props.courses.filter(x=>x.semester===semester.value))
const roomList=ref<{showLastPage:()=>Promise<void>}|null>(null), availabilityList=ref<{showLastPage:()=>Promise<void>}|null>(null), requirementList=ref<{showLastPage:()=>Promise<void>}|null>(null)
let generation = 0
watch(() => props.semesters.join('|'), () => {
  if (mode.value==='resources' && !semester.value && props.semesters.length) {
    semester.value=props.semester || props.semesters[0] || ''
    void loadResources()
  }
})
watch(() => JSON.stringify([dates.value,selected.value]), () => { plan.value = null; confirmed.value = false })
const split = (text: string) => text.split(/[,，\n]/).map(s=>s.trim()).filter(Boolean)
const courseTitle = (id: string) => props.courses.find(x=>x.id===id)?.title || '课程'
async function open(kind: string) {
  mode.value = kind; error.value = ''; message.value = ''; dirty.value = false; plan.value = null; confirmed.value = false
  semester.value = props.semester || props.semesters[0] || ''; dates.value.start_date = props.week; dates.value.end_date = addDays(props.week,6); selected.value = []
  if (kind==='audit') auditQuery.value = new URLSearchParams({start:dates.value.start_date,end:dates.value.end_date}).toString()
  if (kind==='resources') await loadResources()
}
function close() { if (busy.value) return; if (dirty.value && !window.confirm('资源表单尚未保存，确认放弃修改？')) return; generation++; mode.value = '' }
async function loadResources() {
  if (!semester.value) { error.value='请选择已有课程的学期。'; return }
  if (dirty.value && !window.confirm('放弃当前未保存的资源修改？')) return
  const current = ++generation; busy.value=true; error.value=''
  try {
    const value = await props.request(`/timetable/resources?semester=${encodeURIComponent(semester.value)}`) as ResourceState
    if (current!==generation) return
    resourceState.value=value; resources.value=JSON.parse(JSON.stringify(value.resources || {strict_rooms:true,resource_mode:'advisory',specification_source:'administrator',rooms:[],availability:[],requirements:[]})); dirty.value=false
  } catch(e) { error.value=e instanceof Error?e.message:'资源读取失败' }
  finally { busy.value=false }
}
async function saveResources() {
  if (!resourceState.value || busy.value) return
  if (semester.value !== resourceState.value.semester) { error.value='请先读取所选学期的资源，再进行保存。'; return }
  if (resources.value.rooms.some(room => !room.code.trim() || !room.name.trim() || !Number.isInteger(room.capacity) || Number(room.capacity)<1 || Number(room.capacity)>10000)) { error.value='请补全每间教室的编号、名称和有效座位数（1—10000）。'; return }
  if (resources.value.availability.some(row=>!row.teacher_id) || resources.value.requirements.some(row=>!row.course_id)) { error.value='请选择可用时段对应的教师，以及设备需求对应的课程。'; return }
  busy.value=true; error.value=''
  try {
    const result=await props.request('/timetable/resources',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({semester:resourceState.value.semester,expected_revision:resourceState.value.revision,...resources.value})}) as ResourceState
    resourceState.value=result; dirty.value=false; message.value='资源约束已保存，现有课次未移动。可继续检查历史冲突。'; emit('changed')
  } catch(e) {error.value=e instanceof Error?e.message:'资源保存失败'}
  finally {busy.value=false}
}
const loadAudit = (page: number, size: number) => props.request(`/timetable/conflicts?${auditQuery.value}&page=${page}&page_size=${size}`) as Promise<{items:Conflict[];total:number;page:number;page_size:number}>
function queryAudit() { auditQuery.value = new URLSearchParams({start:dates.value.start_date,end:dates.value.end_date}).toString() }
async function preview() {
  if (busy.value) return
  busy.value=true;error.value='';confirmed.value=false;plan.value=null
  try {plan.value=await props.request('/timetable/replan/preview',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...dates.value,session_ids:selected.value,reason:reason.value})}) as Plan}
  catch(e){error.value=e instanceof Error?e.message:'重排预览失败'}finally{busy.value=false}
}
async function apply() {
  if (!plan.value?.ready || !confirmed.value || busy.value) return
  busy.value=true;error.value=''
  try {const result=await props.request('/timetable/replan/apply',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({...dates.value,session_ids:selected.value,reason:reason.value,signature:plan.value.signature,confirmed:true})}) as {notice:string}; message.value=result.notice; plan.value=null; confirmed.value=false; emit('changed')}
  catch(e){error.value=e instanceof Error?e.message:'结果未确认，请查看课表变更后再操作'}finally{busy.value=false}
}
async function suggestedSpecs() {
  if (busy.value || !resourceState.value) return
  if (dirty.value && !window.confirm('使用建议规格替换当前尚未保存的表单？')) return
  busy.value=true;error.value=''
  try { const value=await props.request(`/timetable/resource-suggestions?semester=${encodeURIComponent(resourceState.value.semester)}`) as Resources & {notice:string}; resources.value={strict_rooms:value.strict_rooms,resource_mode:value.resource_mode,specification_source:value.specification_source,rooms:value.rooms,availability:value.availability,requirements:value.requirements}; dirty.value=true; message.value=value.notice }
  catch(e){error.value=e instanceof Error?e.message:'建议规格读取失败'}finally{busy.value=false}
}
function addRoom() { resources.value.rooms.push({code:'',name:'',capacity:null,aliases:[],equipment:[],kind:'multimedia',specialty:'通用'}); dirty.value=true; void nextTick(()=>roomList.value?.showLastPage()) }
function addAvailability() { resources.value.availability.push({teacher_id:'',slots:[]}); dirty.value=true; void nextTick(()=>availabilityList.value?.showLastPage()) }
function addRequirement() { resources.value.requirements.push({course_id:'',equipment:[],specialty:''}); dirty.value=true; void nextTick(()=>requirementList.value?.showLastPage()) }
</script>
<template>
  <section class="schedule-planning-panel"><div><strong>排课辅助</strong><small>检查约束，再确认调整</small></div><div><button type="button" @click="open('resources')">教室与可用时段</button><button type="button" @click="open('audit')">冲突清单</button><button type="button" @click="open('replan')">辅助重排</button></div></section>
  <DetailDialog v-if="mode" :title="mode==='resources'?'教室、教师与课程约束':mode==='audit'?'现有课表冲突检查':'辅助重排预览'" :close-disabled="busy" @close="close"><p v-if="error" class="planning-error" role="alert">{{ error }}</p><p v-if="message" class="planning-message" role="status">{{ message }}</p><p v-if="busy" role="status"><span class="ui-spinner" /> 正在核对，请稍候…</p>
    <section v-if="mode==='resources'" class="planning-resources" :inert="busy" :aria-busy="busy"><div class="planning-row"><label>学期<select v-model="semester" :disabled="busy"><option v-for="label in semesters" :key="label">{{ label }}</option></select></label><button type="button" :disabled="busy" @click="loadResources">读取本学期资源</button></div>
      <template v-if="resourceState"><p>可先使用建议规格，再按实际需要修改。保存不会移动现有课次。</p><div class="planning-row"><button type="button" :disabled="busy" @click="suggestedSpecs">使用建议教室规格</button><label>容量与设备约束<select v-model="resources.resource_mode" @change="dirty=true"><option value="advisory">仅提醒（推荐）</option><option value="enforced">严格检查</option></select></label></div><p v-if="resourceState.legacy_rooms.length">原场地：{{ resourceState.legacy_rooms.join('、') }}</p><header class="planning-row"><h3>教室目录</h3><button type="button" @click="addRoom">添加教室 ＋</button></header><label class="planning-check"><input v-model="resources.strict_rooms" type="checkbox" @change="dirty=true" />核对已登记教室（仅提醒时不阻止）</label>
      <PagedList ref="roomList" :items="resources.rooms" :page-size="4" label="教室目录" v-slot="{items}"><article v-for="room in items" :key="resources.rooms.indexOf(room)" class="planning-resource-card"><div class="planning-grid"><label>稳定编号<input v-model="room.code" maxlength="30" placeholder="例如 JXA-101" @input="dirty=true" /></label><label>显示名称<input v-model="room.name" maxlength="120" placeholder="实际楼宇与教室" @input="dirty=true" /></label><label>教室类型<select v-model="room.kind" @change="dirty=true"><option value="multimedia">多媒体教室</option><option value="computer_lab">通用机房</option><option value="specialized_lab">专业机房</option></select></label><label>专业用途<input v-model="room.specialty" maxlength="60" @input="dirty=true" /></label><label>参考座位数<input v-model.number="room.capacity" type="number" min="1" max="10000" required @input="dirty=true" /></label><label>设备（逗号分隔）<input :value="room.equipment.join(', ')" @change="room.equipment=split(($event.target as HTMLInputElement).value); dirty=true" /></label><label class="planning-wide">旧名称 / 别名（逗号分隔）<input :value="room.aliases.join(', ')" @change="room.aliases=split(($event.target as HTMLInputElement).value); dirty=true" /></label></div><button type="button" @click="resources.rooms.splice(resources.rooms.indexOf(room),1); dirty=true">移除教室</button></article></PagedList>
      <header class="planning-row"><h3>教师可用时段</h3><button type="button" @click="addAvailability">配置教师 ＋</button></header><p>未配置的教师不限制时段；配置后仅允许下列时段，空时段表示该教师本学期暂不可排课。</p>
      <PagedList ref="availabilityList" :items="resources.availability" :page-size="4" label="教师可用时段" v-slot="{items}"><article v-for="row in items" :key="resources.availability.indexOf(row)" class="planning-resource-card"><label>教师<select v-model="row.teacher_id" @change="dirty=true"><option disabled value="">选择教师</option><option v-for="teacher in resourceState.teachers" :key="teacher.id" :value="teacher.id">{{ teacher.name }}</option></select></label><div v-for="(slot,j) in row.slots" :key="j" class="planning-slot"><select v-model.number="slot.weekday" aria-label="星期" @change="dirty=true"><option v-for="d in 7" :key="d" :value="d">周{{ '一二三四五六日'[d-1] }}</option></select><input v-model="slot.start" type="time" aria-label="可用起始时间" @change="dirty=true" /><span>至</span><input v-model="slot.end" type="time" aria-label="可用结束时间" @change="dirty=true" /><button type="button" @click="row.slots.splice(j,1);dirty=true">移除</button></div><div class="planning-row"><button type="button" @click="row.slots.push({weekday:1,start:'08:00',end:'12:00'});dirty=true">增加可用时段</button><button type="button" @click="resources.availability.splice(resources.availability.indexOf(row),1);dirty=true">取消本教师限制</button></div></article></PagedList>
      <header class="planning-row"><h3>课程设备需求</h3><button type="button" @click="addRequirement">增加需求 ＋</button></header><PagedList ref="requirementList" :items="resources.requirements" :page-size="5" label="课程需求" v-slot="{items}"><article v-for="row in items" :key="resources.requirements.indexOf(row)" class="planning-resource-card"><label>课程<select v-model="row.course_id" @change="dirty=true"><option disabled value="">选择本学期课程</option><option v-for="c in relevantCourses" :key="c.id" :value="c.id">{{ c.title }}</option></select></label><label>所需设备<input :value="row.equipment.join(', ')" @change="row.equipment=split(($event.target as HTMLInputElement).value);dirty=true" /></label><label>建议专业用途<input v-model="row.specialty" maxlength="60" @input="dirty=true" /></label><button type="button" @click="resources.requirements.splice(resources.requirements.indexOf(row),1);dirty=true">移除需求</button></article></PagedList></template>
    </section>
    <template v-else><div class="planning-grid"><label>起始日期<input v-model="dates.start_date" type="date" required /></label><label>结束日期<input v-model="dates.end_date" type="date" :min="dates.start_date" :max="addDays(dates.start_date,mode==='audit'?34:13)" required /></label></div>
      <template v-if="mode==='audit'"><p>按所选日期检查课程、教师、学生、教室及已配置的资源约束；只列清单，不自动改课。</p><button type="button" @click="queryAudit">检查所选范围</button><PagedList :items="empty" :load-page="loadAudit" :scope="auditQuery" :page-size="10" label="课表冲突" v-slot="{items,total,loading}"><article v-for="(item,i) in items" :key="i" class="planning-conflict"><strong>{{ item.course_title }} · {{ item.message }}</strong><p>{{ stamp(item.time) }}</p><button type="button" @click="close(); emit('open',item.session_id)">查看课次与候选安排 ↗</button></article><p v-if="!loading&&!total">所选日期范围内未发现冲突。</p></PagedList></template>
      <template v-else><div class="planning-grid"><label>每日开始<input v-model="dates.day_start" type="time" /></label><label>每日结束<input v-model="dates.day_end" type="time" /></label></div><div class="planning-weekdays"><label v-for="d in 7" :key="d"><input v-model="dates.weekdays" type="checkbox" :value="d" />{{ '一二三四五六日'[d-1] }}</label></div><h3>选择当前周待调整课次（最多12项）</h3><p>已授课与已停课课次不参与重排。可先回到课表选择其他周。</p><PagedList :items="rows" :page-size="8" label="选择重排课次" v-slot="{items}"><label v-for="row in items" :key="row.id" class="planning-lesson"><input v-model="selected" type="checkbox" :value="row.id" :disabled="!selected.includes(row.id)&&selected.length>=12" /><span><strong>{{ row.course_title }} · {{ row.title }}</strong><small>{{ stamp(row.session_date) }} · {{ row.location }}</small></span></label></PagedList><label>调整说明<input v-model="reason" minlength="5" maxlength="500" /></label><button type="button" :disabled="busy||!selected.length||!dates.weekdays.length" @click="preview">预览重排方案</button>
      <section v-if="plan" class="planning-preview"><p>{{ plan.notice }} 已检查 {{ plan.checked_candidates }} 个候选。</p><p v-for="row in plan.unresolved" :key="row.id" class="planning-error">{{ row.title }}：{{ row.reason }}</p><article v-for="row in plan.proposed" :key="row.id" class="planning-resource-card"><strong>{{ courseTitle(row.course_id) }} · {{ row.title }}</strong><p>原：{{ stamp(plan.original.find(x=>x.id===row.id)!.session_date) }} · {{ plan.original.find(x=>x.id===row.id)?.location }}</p><p>新：{{ stamp(row.session_date) }} · {{ row.location_display || row.location }} · {{ row.duration_minutes }} 分钟</p><p v-for="(warning,j) in row.resource_warnings || []" :key="j" class="planning-error">提醒：{{ warning }}</p></article><label v-if="plan.ready" class="planning-check"><input v-model="confirmed" type="checkbox" />已核对所有受影响课次，确认按预览更新课表</label></section></template>
    </template>
    <template #footer><span>{{ mode==='resources'?'现有课表保持不动':mode==='audit'?'冲突必须解决，不能填写理由放行':'管理员明确确认后才会保存' }}</span><button v-if="mode==='resources'" type="button" :disabled="busy||!dirty||!resources.rooms.length" @click="saveResources">保存资源约束</button><button v-if="mode==='replan'&&plan?.ready" type="button" :disabled="busy||!confirmed" @click="apply">确认应用重排</button></template>
  </DetailDialog>
</template>
<style scoped>
.schedule-planning-panel,.schedule-planning-panel>div,.planning-row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.schedule-planning-panel{justify-content:space-between;border:1px solid #dde6f5;background:#f7faff;border-radius:12px;padding:12px;margin-block:12px;font-size:13px}.schedule-planning-panel small{color:#8392aa;font-size:11px}.schedule-planning-panel button,button{font-size:12px}.planning-resources{display:grid;gap:12px;font-size:12px}.planning-row{justify-content:space-between}.planning-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin-block:12px}.planning-wide{grid-column:1/-1}label{display:grid;gap:6px;font-size:12px;min-width:0}input,select{font:inherit;min-width:0;width:100%;box-sizing:border-box}.planning-resource-card{border:1px solid #dfe7f5;background:#f9fbff;border-radius:12px;padding:12px;display:grid;gap:10px}.planning-resource-card p,p{color:#7b8ca5;font-size:12px;line-height:1.8;margin-block:8px}h3{font-size:14px;margin-block:10px}.planning-check,.planning-weekdays,.planning-weekdays>label{display:flex;align-items:center;gap:8px;flex-wrap:wrap}.planning-check input,.planning-weekdays input{width:auto}.planning-slot{display:grid;grid-template-columns:70px minmax(0,1fr) auto minmax(0,1fr) auto;align-items:center;gap:6px}.planning-lesson{display:flex;align-items:center;gap:10px;padding:12px;border-bottom:1px solid #e3ebf7}.planning-lesson input{width:auto;flex:none}.planning-lesson span{display:grid;gap:6px;min-width:0}.planning-lesson small{color:#8090a7}.planning-conflict{border-bottom:1px solid #e4ebf5;padding-block:14px;font-size:12px}.planning-error{color:#ac4b37!important}.planning-message{color:#3d7865!important}.planning-preview{margin-top:15px;display:grid;gap:10px}@media(max-width:500px){.planning-grid{grid-template-columns:1fr}.planning-slot{grid-template-columns:65px minmax(0,1fr) auto minmax(0,1fr)}.planning-slot>button{grid-column:4}.planning-wide{grid-column:auto}.schedule-planning-panel>div{width:100%}}
</style>
