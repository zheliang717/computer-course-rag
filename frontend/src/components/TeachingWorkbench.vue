<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import PagedList from './PagedList.vue'
import RichText from './RichText.vue'
import { dayKey, addDays, stamp } from '../timetable'
import type { CourseRecord } from '../courseCatalog'

type Page<T> = { items: T[]; total: number; page: number; page_size: number }
type Source = { id: string; title: string; page_count: number; external_allowed: boolean; revision?: number; status?: string }
type SourcePage = { page_number: number; content: string }
type Evidence = { title: string; spans: { page_number: number; quote: string }[]; original_text: string; answer_origin: string }
type Candidate = { candidate_id: string; question_type: string; stem: string; options: string[]; correct_answer: string; explanation: string; difficulty: number; knowledge_point: string; source: Evidence; duplicate: boolean; needs_answer: boolean }
type Suggestion = { description: string; learning_objectives: string; assessment: string; sections: { title: string; description: string; knowledge_points: string[] }[] }
type Lesson = { id: string; title: string; session_date: string; duration_minutes: number; location: string | null; location_display?: string }
type Choice = { proposed: Lesson[]; warnings: string[] }
type Work = { id: string; course_id: string; kind: string; revision: number; status: string; created_at: string; content: { candidates?: Candidate[]; source?: { title: string }; suggestion?: Suggestion; notice?: string; draft_id?: string; choices?: Choice[]; original?: Lesson[]; explanation?: string; unresolved?: string[]; student_count?: number; room_options?: {code:string;name:string}[]; conditions?: { day_start: string; day_end: string; weekdays: number[]; rooms: string[] }; applied_result?: { message: string } } }
type Task = { id: string; status: string; stage: string; error?: string; result?: { workflow_id?: string }; kind: string }
type Tab = 'materials' | 'course' | 'schedule' | 'history'
const props = defineProps<{ role: string; courses: CourseRecord[]; initialCourseId?: string; initialTab?: Tab; initialPrompt?: string; initialResultId?: string; request: (path: string, init?: RequestInit) => Promise<unknown>; token: string; base: string }>()
const emit = defineEmits<{ close: []; openDraft: [id: string]; editCourse: [id: string]; changed: []; dirty: [value: boolean]; saving: [value: boolean] }>()
const tab = ref<Tab>(props.initialTab || 'materials'), courseId = ref(props.initialCourseId || props.courses[0]?.id || '')
const busy = ref(false), error = ref(''), message = ref(''), baseline = ref(''), result = ref<Work | null>(null), job = ref<Task | null>(null), setupOpen = ref(true)
const sourceKind = ref('private'), source = ref<Source | null>(null), sourcePages = ref<SourcePage[]>([]), firstPage = ref(1), lastPage = ref(1), manualExcerpt = ref('')
const query = ref(''), keyword = ref(''), archived = ref(false), resourcesRevision = ref(0), uploadOpen = ref(false), file = ref<File | null>(null), fileInput = ref<HTMLInputElement | null>(null), uploadId = ref(crypto.randomUUID())
const resourceTitle = ref(''), externalAllowed = ref(false), resourceEditing = ref(false), resourceNameEdit = ref(''), resourceExternalEdit = ref(false)
const courseRequest = ref(props.initialTab === 'course' && props.initialPrompt ? props.initialPrompt : '请结合现有课程内容，完善课程介绍、学习目标和章节大纲。')
const useSource = ref(false), shareSource = ref(false), scheduleRequest = ref(props.initialTab === 'schedule' && props.initialPrompt ? props.initialPrompt : '优先安排在合适的机房，避开教师、教室和学生已有课程。')
const scheduleMode = ref(props.role === 'admin' ? 'create' : 'replan'), startDate = ref(addDays(dayKey(), 1)), endDate = ref(addDays(dayKey(), 13)), startTime = ref('08:00'), endTime = ref('20:00'), weekdays = ref([1, 2, 3, 4, 5]), count = ref(2), duration = ref(90), lessonIds = ref<string[]>([])
const candidates = ref<Candidate[]>([]), selected = ref<string[]>([]), expanded = ref(''), suggestion = ref<Suggestion | null>(null), fields = ref<string[]>([]), confirmed = ref(false), option = ref(0), reason = ref(''), historyRevision = ref(0)
const conditionEdit=ref<{day_start:string;day_end:string;weekdays:number[];rooms:string[];explanation:string}|null>(null)
const controller = new AbortController(), objectUrls = new Set<string>()
let timer: ReturnType<typeof setTimeout> | undefined, sourceSequence = 0, live = true
const running = computed(() => !!job.value && ['queued', 'running'].includes(job.value.status))
const activeCourse = computed(() => props.courses.find(x => x.id === courseId.value))
const selectedQuestions = computed(() => candidates.value.filter(x => selected.value.includes(x.candidate_id)))
const formValue = computed(() => JSON.stringify({ conditionEdit:conditionEdit.value, courseRequest: courseRequest.value, scheduleRequest: scheduleRequest.value, excerpt: manualExcerpt.value, file: file.value?.name, resourceTitle: resourceTitle.value, candidates: candidates.value, selected: selected.value, suggestion: suggestion.value, fields: fields.value, reason: reason.value, parameters:[startDate.value,endDate.value,startTime.value,endTime.value,weekdays.value,count.value,duration.value,lessonIds.value,useSource.value,shareSource.value], resourceName: resourceEditing.value ? resourceNameEdit.value : '', resourceExternal: resourceEditing.value ? resourceExternalEdit.value : false }))
const dirty = computed(() => !!baseline.value && formValue.value !== baseline.value)
watch(dirty, value => { emit('dirty', value); confirmed.value = false })
watch(formValue, () => { confirmed.value = false })
watch(busy, value => emit('saving', value))
function clean() { baseline.value = formValue.value; confirmed.value = false }
const read = <T,>(path: string, init?: RequestInit) => props.request(path, { ...init, signal: controller.signal }) as Promise<T>
const post = <T,>(path: string, value: unknown, method = 'POST') => read<T>(path, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(value) })
async function run(fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await fn() } catch (e) { if (live && !controller.signal.aborted) error.value = e instanceof Error ? e.message : '操作未完成，请重试。' }
  finally { busy.value = false }
}
function close() { if (!busy.value && (!dirty.value || window.confirm('有尚未保存的编辑，确定离开？已提交的后台任务和保存的工作结果仍会保留。'))) emit('close') }
function chooseCourse(event: Event) { const input=event.target as HTMLSelectElement; if(dirty.value&&!window.confirm('有尚未保存的编辑，确定切换课程？'))input.value=courseId.value;else courseId.value=input.value }
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || busy.value) { event.preventDefault(); event.returnValue = '' } }
watch(courseId, () => { sourceSequence++; conditionEdit.value=null; source.value = null; sourcePages.value = []; result.value = null; candidates.value = []; suggestion.value = null; selected.value = []; lessonIds.value = []; resourceEditing.value = false; setupOpen.value = true; clean() })
watch(sourceKind, () => { sourceSequence++; source.value = null; sourcePages.value = []; resourceEditing.value = false })
const emptySources: Source[] = [], emptyLessons: Lesson[] = [], emptyHistory: Work[] = []
const sourceScope = computed(() => `${courseId.value}:${sourceKind.value}:${keyword.value}:${archived.value}:${resourcesRevision.value}`)
const loadSources = (page: number, size: number) => read<Page<Source>>(`/api/v1/courses/${courseId.value}/${sourceKind.value === 'private' ? 'teacher-resources' : 'teaching-source-documents'}?${new URLSearchParams({ page: String(page), page_size: String(size), keyword: keyword.value, archived: String(archived.value) })}`)
const loadLessons = (page: number, size: number) => read<Page<Lesson>>(`/api/v1/courses/${courseId.value}/schedule-targets?page=${page}&page_size=${size}`)
const loadHistory = (page: number, size: number) => read<Page<Work>>(`/api/v1/courses/${courseId.value}/teaching-workflows?page=${page}&page_size=${size}`)
function sourceFields() { return { resource_id: sourceKind.value === 'private' ? source.value?.id || null : null, document_id: sourceKind.value === 'public' ? source.value?.id || null : null, first_page: firstPage.value, last_page: lastPage.value } }
async function previewSource(row?: Source) {
  if (row) { source.value = row; firstPage.value = 1; lastPage.value = Math.max(1,Math.min(2, row.page_count)); manualExcerpt.value = ''; resourceEditing.value = false }
  const sequence = ++sourceSequence
  await run(async () => {
    if (!source.value) return
    const value = await post<{ pages: SourcePage[] }>('/api/v1/courses/' + courseId.value + '/teaching-source-pages', { course_id: courseId.value, ...sourceFields() })
    if (sequence === sourceSequence) sourcePages.value = value.pages
  })
}
async function upload() {
  if (!file.value || file.value.size > 30 * 1024 * 1024) { error.value = '请选择30 MB以内的文字型 PDF。'; return }
  await run(async () => {
    const form = new FormData(); form.append('file', file.value!); form.append('title', resourceTitle.value); form.append('external_allowed', String(externalAllowed.value)); form.append('upload_id', uploadId.value)
    const row = await read<Source>(`/api/v1/courses/${courseId.value}/teacher-resources`, { method: 'POST', body: form })
    sourceKind.value = 'private'; await nextTick(); source.value = row; sourcePages.value = []; firstPage.value = 1; lastPage.value = 1
    file.value = null; if (fileInput.value) fileInput.value.value = ''; resourceTitle.value = ''; uploadId.value = crypto.randomUUID(); uploadOpen.value = false; archived.value = false; resourcesRevision.value++
    message.value = '教师资料已保存，不会进入学生学习资料或问答知识库。'; clean()
  })
}
function pickFile(event: Event) { file.value = (event.target as HTMLInputElement).files?.[0] || null; uploadId.value = crypto.randomUUID() }
function editResource() { if (source.value) { resourceNameEdit.value = source.value.title; resourceExternalEdit.value = source.value.external_allowed; resourceEditing.value = true } }
async function saveResource(archive = false) {
  await run(async () => {
    if (!source.value) return
    const row = await post<Source>(`/api/v1/courses/${courseId.value}/teacher-resources/${source.value.id}`, { revision: source.value.revision, title: resourceNameEdit.value || source.value.title, external_allowed: resourceEditing.value ? resourceExternalEdit.value : source.value.external_allowed, archived: archive }, 'PATCH')
    source.value = archive ? null : row; sourcePages.value = []; resourceEditing.value = false; resourcesRevision.value++; clean(); message.value = archive ? '资料已归档，识别记录和题目出处仍保留。' : '资料信息已保存。'
  })
}
async function download() {
  await run(async () => {
    if (!source.value) return
    const response = await fetch(`${props.base}/api/v1/courses/${courseId.value}/teacher-resources/${source.value.id}/pdf`, { headers: { Authorization: 'Bearer ' + props.token }, signal: controller.signal })
    if (!response.ok) throw new Error('原文件暂不可下载，请核对资料权限。')
    const url = URL.createObjectURL(await response.blob()); objectUrls.add(url)
    const link = document.createElement('a'); link.href = url; link.download = source.value.title + '.pdf'; link.click()
    setTimeout(() => { URL.revokeObjectURL(url); objectUrls.delete(url) }, 15000)
  })
}
async function start(kind: string) {
  if (!courseId.value || running.value) return
  await run(async () => {
    let payload: Record<string, unknown>
    if (kind === 'material_extract') {
      if (!source.value || source.value.status === 'archived') throw new Error('请先选择可用资料并核对页码。')
      payload = { course_id: courseId.value, ...sourceFields(), excerpt: manualExcerpt.value }
    } else if (kind === 'course_content') {
      if (useSource.value && (!source.value || !source.value.external_allowed || !shareSource.value)) throw new Error('请先选择允许在线使用的资料，并确认本次发送选段；也可取消使用所选资料。')
      payload = { course_id: courseId.value, request: courseRequest.value, ...(useSource.value ? sourceFields() : {}), allow_external: shareSource.value }
    } else {
      if (scheduleMode.value === 'replan' && !lessonIds.value.length) throw new Error('请选择需要调整的现有课次。')
      payload = { course_id: courseId.value, request: scheduleRequest.value, start_date: startDate.value, end_date: endDate.value, day_start: startTime.value, day_end: endTime.value, weekdays: weekdays.value, count: count.value, duration_minutes: duration.value, session_ids: scheduleMode.value === 'replan' ? lessonIds.value : [] }
    }
    job.value = await post<Task>('/api/v1/assistant/tasks', { request_id: crypto.randomUUID(), kind, payload })
    result.value = null; candidates.value = []; suggestion.value = null; selected.value = []; setupOpen.value = false; clean(); clearTimeout(timer); void poll()
  })
}
async function poll() {
  if (!job.value || !live) return
  const identifier=job.value.id, ownerCourse=courseId.value
  try {
    const current=await read<Task>('/api/v1/assistant/tasks/' + identifier)
    if (!live||job.value?.id!==identifier||courseId.value!==ownerCourse) return
    job.value=current
    if (job.value.status === 'completed' && job.value.result?.workflow_id) { if (!dirty.value && !result.value) await openResult(job.value.result.workflow_id); historyRevision.value++; return }
    if (running.value) timer = setTimeout(poll, 1500)
  } catch (e) { if (live) error.value = e instanceof Error ? e.message : '任务读取失败，可以刷新状态。' }
}
async function taskAction(name: 'cancel' | 'retry') {
  if (!job.value || name === 'retry' && !window.confirm('重试可能产生新的模型调用费用，确认继续？')) return
  await run(async () => { job.value = await read<Task>(`/api/v1/assistant/tasks/${job.value!.id}/${name}`, { method: 'POST' }); clearTimeout(timer); clean(); void poll() })
}
async function openResult(id: string, force = false) {
  if (!force && dirty.value && !window.confirm('有未保存的编辑，确定切换工作结果？')) return
  const row = await read<Work>('/api/v1/teaching-workflows/' + id)
  if (courseId.value !== row.course_id) { courseId.value = row.course_id; await nextTick() }
  result.value = row; candidates.value = structuredClone(row.content.candidates || []); suggestion.value = row.content.suggestion ? structuredClone(row.content.suggestion) : null
  selected.value = []; fields.value = []; confirmed.value = false; expanded.value = ''; option.value = 0; reason.value = ''; conditionEdit.value=null
  tab.value = row.kind === 'material_extract' ? 'materials' : row.kind === 'course_content' ? 'course' : 'schedule'; setupOpen.value = false; clean()
}
function toggleCandidate(id: string) { selected.value = selected.value.includes(id) ? selected.value.filter(x => x !== id) : [...selected.value, id] }
function toggleLesson(id: string) {
  if (!lessonIds.value.includes(id) && lessonIds.value.length >= 8) { error.value = '一次最多选择8个课次。'; return }
  lessonIds.value = lessonIds.value.includes(id) ? lessonIds.value.filter(x => x !== id) : [...lessonIds.value, id]
}
async function adopt() {
  if (!result.value || !confirmed.value) return
  await run(async () => {
    const row = result.value!
    try { if (row.kind === 'material_extract') {
      const value = await post<{ draft_id: string }>(`/api/v1/teaching-workflows/${row.id}/questions`, { revision: row.revision, confirmed: true, questions: selectedQuestions.value.map(({ source, duplicate, needs_answer, ...rest }) => rest) })
      await openResult(row.id,true); message.value = '题目草稿已保存，可继续核对答案、检查并确认入库。'; emit('changed'); emit('openDraft', value.draft_id)
    } else if (row.kind === 'course_content') {
      await post(`/api/v1/teaching-workflows/${row.id}/course-content`, { revision: row.revision, confirmed: true, fields: fields.value, suggestion: suggestion.value })
      await openResult(row.id,true); message.value = '建议已写入课程草稿，尚未发布。'; emit('changed')
    } else {
      const value = await post<{ message: string }>(`/api/v1/teaching-workflows/${row.id}/schedule`, { revision: row.revision, confirmed: true, option: option.value, reason: reason.value })
      await openResult(row.id,true); message.value = value.message; emit('changed')
    }
    } catch(original) {
      const saved=await read<Work>('/api/v1/teaching-workflows/'+row.id).catch(()=>null)
      if (saved?.status==='adopted') { await openResult(row.id,true);message.value=saved.content.applied_result?.message||'处理结果已保存，可从当前工作结果继续查看。';emit('changed') }
      else throw original
    }
  })
}
function editConditions(){const value=result.value?.content.conditions;if(value)conditionEdit.value={...JSON.parse(JSON.stringify(value)),explanation:''};confirmed.value=false}
async function reviseSchedule(){await run(async()=>{if(!result.value||!conditionEdit.value)return;await post(`/api/v1/teaching-workflows/${result.value.id}/schedule-preview`,{revision:result.value.revision,conditions:{...conditionEdit.value,explanation:'用户核对后重新计算'}});await openResult(result.value.id,true);message.value='已重新计算预览，课表尚未改变。'})}
function title(kind: string) { return ({ material_extract: '原题识别', course_content: '课程内容建议', schedule_plan: 'AI 排课方案' } as Record<string, string>)[kind] || '工作结果' }
onMounted(async () => { window.addEventListener('beforeunload', beforeUnload); clean(); if (props.initialResultId) await run(() => openResult(props.initialResultId!)) })
onBeforeUnmount(() => { live = false; controller.abort(); clearTimeout(timer); window.removeEventListener('beforeunload', beforeUnload); for (const url of objectUrls) URL.revokeObjectURL(url); emit('dirty', false); emit('saving', false) })
defineExpose({ signature: () => formValue.value, discardEdits: clean })
</script>

<template>
  <DetailDialog :title="role === 'admin' ? 'AI 管理工作间' : 'AI 教学工作间'" kicker="需求 → 建议 → 核对确认" :close-disabled="busy" :view-key="tab" @close="close">
    <template #navigation><nav class="workbench-tabs" aria-label="AI 工作流程"><button v-for="item in [{id:'materials',name:'资料出题'},{id:'course',name:'课程完善'},{id:'schedule',name:'排课助手'},{id:'history',name:'工作记录'}]" :key="item.id" type="button" :class="{active:tab===item.id}" @click="tab=item.id as Tab">{{ item.name }}</button></nav></template>
    <div class="teaching-workbench">
      <p v-if="error" class="work-error" role="alert">{{ error }}</p><p v-if="message" class="work-success" role="status">{{ message }}</p>
      <div class="work-course"><label>当前课程<select :value="courseId" @change="chooseCourse" aria-label="当前课程" :disabled="busy||running"><option v-for="course in courses" :key="course.id" :value="course.id">{{ course.title }} · {{ course.semester || '未设置学期' }}</option></select></label><button v-if="(result||job) && tab!=='history'" type="button" class="secondary" :disabled="running" @click="setupOpen=!setupOpen">{{ setupOpen?'收起设置':'准备新任务' }}</button></div>
      <p v-if="!courseId" class="work-note">暂无可管理课程，请先创建课程或分配任课教师。</p>
      <div v-if="job" class="work-job" role="status"><span v-if="running" class="work-spinner" /><div><strong>{{ title(job.kind) }} · {{ running?'处理中':job.status==='completed'?'已完成':job.status==='failed'?'未完成':'已停止' }}</strong><p>{{ job.error || job.stage }}</p></div><button v-if="running" type="button" :disabled="busy" @click="taskAction('cancel')">停止</button><button v-if="job.status==='failed'" type="button" :disabled="busy" @click="taskAction('retry')">重试</button><button v-if="job.result?.workflow_id" type="button" :disabled="busy" @click="run(()=>openResult(job!.result!.workflow_id!))">恢复结果</button><button v-else type="button" :disabled="busy" @click="poll">刷新状态</button></div>
      <p v-if="busy" class="work-loading" role="status"><span class="work-spinner" />正在处理，请稍候…</p>
      <fieldset :disabled="busy||!courseId">
        <section v-if="(tab==='materials'||tab==='course')&&setupOpen" class="work-setup">
          <div v-if="tab==='materials'||useSource" class="work-source-picker">
            <div class="work-heading"><div><h3>选择出题或参考资料</h3><p>教师专用资料不进入学生资料库。原题识别在站内完成。</p></div><button type="button" @click="uploadOpen=!uploadOpen">上传教师资料</button></div>
            <div v-if="uploadOpen" class="work-upload"><label>资料名称<input v-model="resourceTitle" maxlength="200" placeholder="例如：数据结构课程习题选编" /></label><label>文字型 PDF<input ref="fileInput" type="file" accept=".pdf,application/pdf" @change="pickFile" /></label><label class="work-check"><input v-model="externalAllowed" type="checkbox" />允许将选定的少量片段用于在线 AI 课程建议</label><button type="button" :disabled="!file" @click="upload">保存教师资料</button><small>最大30 MB；扫描件请先转成可复制文字的 PDF。</small></div>
            <div class="work-source-nav"><button type="button" :class="{active:sourceKind==='private'}" @click="sourceKind='private'">教师专用资料</button><button type="button" :class="{active:sourceKind==='public'}" @click="sourceKind='public'">课程学习资料</button><label v-if="sourceKind==='private'" class="work-check"><input v-model="archived" type="checkbox" />已归档</label></div>
            <form class="work-search" @submit.prevent="keyword=query.trim()"><label>查找资料<input v-model="query" maxlength="100" placeholder="输入资料名称" /></label><button type="submit">查询</button></form>
            <PagedList :items="emptySources" :load-page="loadSources" :scope="sourceScope" :page-size="5" label="教学参考资料" v-slot="{items}"><button v-for="row in items" :key="row.id" type="button" class="work-source-row" :class="{selected:source?.id===row.id}" @click="previewSource(row)"><strong>{{ row.title }}</strong><small>{{ row.page_count }} 页</small><span>{{ source?.id===row.id?'已选择':'查看 ›' }}</span></button><p v-if="!items.length" class="work-note">暂无匹配资料，可上传教师资料或切换资料来源。</p></PagedList>
            <div v-if="source" class="work-source-detail"><div class="work-heading"><strong>{{ source.title }}</strong><div v-if="sourceKind==='private'" class="work-actions"><button type="button" @click="editResource">编辑资料</button><button type="button" @click="download">下载原文件</button></div></div>
              <div v-if="resourceEditing" class="work-upload"><label>资料显示名称<input v-model="resourceNameEdit" maxlength="200" /></label><label class="work-check"><input v-model="resourceExternalEdit" type="checkbox" />允许少量片段用于在线 AI 建议</label><div class="work-actions"><button type="button" @click="saveResource(false)">{{ source.status==='archived'?'恢复资料':'保存资料信息' }}</button><button v-if="source.status!=='archived'" type="button" class="danger-action" @click="saveResource(true)">归档资料</button></div></div>
              <div class="work-range"><label>起始页<input v-model.number="firstPage" type="number" min="1" :max="source.page_count" /></label><label>结束页<input v-model.number="lastPage" type="number" :min="firstPage" :max="Math.min(source.page_count,firstPage+9)" /></label><button type="button" @click="previewSource()">查看所选原文</button></div>
              <details v-for="page in sourcePages" :key="page.page_number" class="work-page"><summary>第 {{ page.page_number }} 页原文</summary><pre>{{ page.content || '该页没有可复制的文字。' }}</pre></details>
            </div>
          </div>
          <template v-if="tab==='materials'"><label>手动选段（可选）<textarea v-model="manualExcerpt" rows="3" maxlength="10000" placeholder="没有标准题号时，从上方原文复制需要整理的完整题目；留空则按题号识别。" /></label><button type="button" :disabled="!source||source.status==='archived'||running" @click="start('material_extract')">{{ manualExcerpt?'整理所选原题':'识别所选页原题' }}</button></template>
          <template v-else><label>希望 AI 帮你完善什么<textarea v-model="courseRequest" rows="4" maxlength="2000" /></label><label class="work-check"><input v-model="useSource" type="checkbox" />参考选定资料</label><label v-if="useSource" class="work-check"><input v-model="shareSource" type="checkbox" />我确认本次将所选片段发送给在线 AI 模型</label><p class="work-note">不选资料时仅参考现有课程内容；建议不会直接发布，也不会覆盖现有章节。</p><button type="button" :disabled="running||!courseRequest.trim()" @click="start('course_content')">生成课程完善建议</button></template>
        </section>
        <section v-if="tab==='schedule'&&setupOpen" class="work-setup">
          <div class="work-heading"><div><h3>{{ role==='admin'?'准备排课方案':'准备调课申请' }}</h3><p>先描述需求，再核对 AI 整理的条件与程序计算出的课次。</p></div></div>
          <label v-if="role==='admin'">排课任务<select v-model="scheduleMode" aria-label="排课任务"><option value="create">新增课次</option><option value="replan">调整现有课次</option></select></label>
          <div v-if="scheduleMode==='replan'"><div class="work-heading"><strong>待调整课次 · 已选 {{ lessonIds.length }} / 8</strong><button type="button" @click="lessonIds=[]">清空选择</button></div><PagedList :items="emptyLessons" :load-page="loadLessons" :scope="courseId" :page-size="5" label="待调课课次" v-slot="{items}"><label v-for="row in items" :key="row.id" class="work-lesson"><input type="checkbox" :checked="lessonIds.includes(row.id)" @change="toggleLesson(row.id)" /><span><strong>{{ row.title }}</strong><small>{{ stamp(row.session_date) }} · {{ row.location || '地点待定' }} · {{ row.duration_minutes }} 分钟</small></span></label><p v-if="!items.length" class="work-note">没有可调整的未授课课次。</p></PagedList></div>
          <div class="work-grid"><label>候选开始日期<input v-model="startDate" type="date" :min="dayKey()" /></label><label>候选结束日期<input v-model="endDate" type="date" :min="startDate" :max="addDays(startDate,13)" /></label><label>每日开始时间<input v-model="startTime" type="time" /></label><label>每日结束时间<input v-model="endTime" type="time" /></label><template v-if="scheduleMode==='create'"><label>新增课次数<input v-model.number="count" type="number" min="1" max="8" /></label><label>单节时长（分钟）<input v-model.number="duration" type="number" min="15" max="240" /></label></template></div>
          <div class="work-weekdays"><label v-for="(name,i) in ['一','二','三','四','五','六','日']" :key="i" class="work-check"><input v-model="weekdays" type="checkbox" :value="i+1" />周{{ name }}</label></div>
          <label>排课需求<textarea v-model="scheduleRequest" rows="4" maxlength="2000" placeholder="例如：优先机房，尽量安排在周二或周四下午，避开已有课程。" /></label><p class="work-note">候选日期最多14天；时间冲突不能放行。{{ scheduleMode==='replan'?'保留所选课次时长。':'' }}{{ role==='teacher'?'确认后仅提交申请，由管理员审批。':'确认前不更改任何课表。' }}</p><button type="button" :disabled="running||!weekdays.length||!scheduleRequest.trim()" @click="start('schedule_plan')">让 AI 准备{{ role==='teacher'?'调课':'排课' }}方案</button>
        </section>
        <section v-if="result&&tab==='materials'&&result.kind==='material_extract'" class="work-result">
          <div class="work-heading"><div><h3>{{ result.content.source?.title }} · 原题候选</h3><p>{{ result.content.notice }}</p></div><span>{{ candidates.length }} 题</span></div>
          <p v-if="!candidates.length" class="work-note">没有识别到标准题号。可展开“准备新任务”，查看原文后复制完整题目到手动选段。</p>
          <div><PagedList :items="candidates" :scope="result.id" :page-size="5" label="原题候选" v-slot="{items}"><article v-for="row in items" :key="row.candidate_id" class="work-candidate"><div class="work-candidate-heading"><input type="checkbox" :disabled="result.status!=='draft'" :aria-label="`选择题目 ${row.stem.slice(0,30)}`" :checked="selected.includes(row.candidate_id)" @change="toggleCandidate(row.candidate_id)" /><button type="button" @click="expanded=expanded===row.candidate_id?'':row.candidate_id"><strong>{{ row.stem }}</strong><small>{{ row.source.spans.map(x=>'第'+x.page_number+'页').join('、') }} · {{ row.correct_answer?'有参考答案':'待补充答案' }}{{ row.duplicate?' · 疑似重复':'' }}</small></button></div>
            <fieldset v-if="expanded===row.candidate_id" class="work-candidate-edit" :disabled="result.status!=='draft'"><div class="work-grid"><label>题型<select v-model="row.question_type" aria-label="原题题型"><option value="single_choice">单选题</option><option value="multiple_choice">多选题</option><option value="true_false">判断题</option><option value="fill_blank">填空题</option><option value="short_answer">简答题</option></select></label><label>设计难度<select v-model.number="row.difficulty" aria-label="原题设计难度"><option v-for="n in 5" :key="n" :value="n">{{ n }} 级</option></select></label></div><label>原题题干<textarea v-model="row.stem" rows="4" maxlength="5000" /></label><label>选项（每行一项）<textarea :value="row.options.join('\n')" rows="3" @input="row.options=($event.target as HTMLTextAreaElement).value.split('\n').filter(x=>x.trim())" /></label><label>参考答案<textarea v-model="row.correct_answer" rows="2" maxlength="2000" placeholder="原文未提供时可先留空，入库前须补充。" /></label><label>知识点<input v-model="row.knowledge_point" maxlength="200" /></label><label>解析<textarea v-model="row.explanation" rows="3" maxlength="5000" /></label><details class="work-page"><summary>核对资料出处 · {{ row.source.title }}</summary><pre v-for="(span,i) in row.source.spans" :key="i">第 {{ span.page_number }} 页：{{ span.quote }}</pre></details></fieldset>
          </article></PagedList><p v-if="selectedQuestions.some(x=>!x.correct_answer.trim())" class="work-note">所选题目中仍有待补充答案，可先保存到草稿，但不能直接入库。</p><label v-if="candidates.length&&result.status==='draft'" class="work-check work-confirm"><input v-model="confirmed" type="checkbox" />已核对所选原题，保存为待审核题目草稿</label></div>
          <button v-if="result.content.draft_id" type="button" @click="emit('openDraft',result.content.draft_id)">打开题目草稿 ↗</button>
        </section>
        <section v-if="result&&tab==='course'&&suggestion&&result.kind==='course_content'" class="work-result">
          <h3>课程内容建议</h3><p class="work-note">{{ result.content.notice }} {{ result.content.source?`参考《${result.content.source.title}》`:'未使用资料，仅参考现有课程信息。' }}</p>
          <div><label class="work-check"><input :disabled="result.status!=='draft'" v-model="fields" type="checkbox" value="description" />采纳课程介绍</label><label>建议课程介绍<textarea :disabled="result.status!=='draft'" v-model="suggestion.description" rows="4" maxlength="3000" /></label><label class="work-check"><input :disabled="result.status!=='draft'" v-model="fields" type="checkbox" value="learning_objectives" />采纳学习目标</label><label>建议学习目标<textarea :disabled="result.status!=='draft'" v-model="suggestion.learning_objectives" rows="4" maxlength="10000" /></label><label class="work-check"><input :disabled="result.status!=='draft'" v-model="fields" type="checkbox" value="assessment" />采纳考核建议</label><label>建议考核方式<textarea :disabled="result.status!=='draft'" v-model="suggestion.assessment" rows="3" maxlength="10000" /></label><label class="work-check"><input :disabled="result.status!=='draft'" v-model="fields" type="checkbox" value="sections" />追加以下章节与知识点（不覆盖已有章节，同名章节不重复添加）</label>
            <PagedList :items="suggestion.sections" :page-size="5" label="建议章节" v-slot="{items}"><details v-for="(section,i) in items" :key="i" class="work-page"><summary>{{ section.title }} · {{ section.knowledge_points.length }} 个知识点</summary><label>建议章节名称<input :disabled="result.status!=='draft'" v-model="section.title" maxlength="200" /></label><label>建议章节内容<textarea :disabled="result.status!=='draft'" v-model="section.description" rows="3" maxlength="2000" /></label><label>建议知识点（每行一个）<textarea :disabled="result.status!=='draft'" :value="section.knowledge_points.join('\n')" rows="3" @input="section.knowledge_points=($event.target as HTMLTextAreaElement).value.split('\n').map(x=>x.trim()).filter(Boolean)" /></label></details></PagedList><label class="work-check work-confirm"><input :disabled="result.status!=='draft'" v-model="confirmed" type="checkbox" />已核对勾选内容，写入课程草稿</label></div>
          <button v-if="result.status==='adopted'" type="button" @click="emit('editCourse',result.course_id)">前往课程草稿核对与发布 ↗</button>
        </section>
        <section v-if="result&&tab==='schedule'&&result.kind==='schedule_plan'" class="work-result">
          <h3>{{ role==='teacher'?'调课申请预览':'排课方案预览' }}</h3><RichText :source="result.content.explanation||''" :tools="false" /><p class="work-note">{{ result.content.notice }} 涉及本课程 {{ result.content.student_count || 0 }} 名学生。</p>
          <div v-if="result.content.conditions" class="work-conditions"><span>{{ result.content.conditions.day_start }}—{{ result.content.conditions.day_end }}</span><span>{{ result.content.conditions.weekdays.map(x=>'周'+['一','二','三','四','五','六','日'][x-1]).join('、') }}</span><span>{{ result.content.conditions.rooms.map(code=>result!.content.room_options?.find(x=>x.code===code)?.name||code).join('、') }}</span></div>
          <button v-if="result.status==='draft'&&!conditionEdit" type="button" class="secondary" @click="editConditions">核对条件 / 重新计算预览</button>
          <div v-if="conditionEdit" class="work-upload"><strong>核对排课条件</strong><p class="work-note">只能在原候选范围内调整。重新计算不调用 AI，也不会更改课表。</p><div class="work-grid"><label>预览开始时间<input v-model="conditionEdit.day_start" type="time" /></label><label>预览结束时间<input v-model="conditionEdit.day_end" type="time" /></label></div><div class="work-weekdays"><label v-for="(name,i) in ['一','二','三','四','五','六','日']" :key="i" class="work-check"><input v-model="conditionEdit.weekdays" type="checkbox" :value="i+1" />周{{ name }}</label></div><div class="work-weekdays"><label v-for="room in result.content.room_options" :key="room.code" class="work-check"><input v-model="conditionEdit.rooms" type="checkbox" :value="room.code" />{{ room.name }}</label></div><div class="work-actions"><button type="button" :disabled="!conditionEdit.weekdays.length||!conditionEdit.rooms.length" @click="reviseSchedule">重新计算方案</button><button type="button" class="secondary" @click="conditionEdit=null">取消调整</button></div></div>
          <p v-for="(text,i) in result.content.unresolved" :key="i" class="work-error">{{ text }}</p>
          <fieldset :disabled="result.status!=='draft'"><article v-for="(choice,i) in result.content.choices" :key="i" class="work-plan" :class="{selected:option===i}"><label class="work-check"><input v-model.number="option" type="radio" :value="i" name="schedule-option" />方案 {{ i+1 }} · {{ choice.proposed.length }} 个课次</label><template v-if="option===i"><div v-for="lesson in choice.proposed" :key="lesson.id" class="work-plan-lesson"><strong>{{ lesson.title }}</strong><small v-if="result.content.original?.find(x=>x.id===lesson.id)">原：{{ stamp(result.content.original.find(x=>x.id===lesson.id)!.session_date) }} · {{ result.content.original.find(x=>x.id===lesson.id)?.location_display || result.content.original.find(x=>x.id===lesson.id)?.location }}</small><span>新：{{ stamp(lesson.session_date) }} · {{ lesson.location_display || lesson.location }} · {{ lesson.duration_minutes }} 分钟</span></div><p v-for="(warning,j) in choice.warnings" :key="j" class="work-note">提醒：{{ warning }}</p></template></article>
            <template v-if="result.content.choices?.length"><label>调整说明<input v-model="reason" minlength="5" maxlength="500" placeholder="至少5个字，说明本次安排原因" /></label><label class="work-check work-confirm"><input v-model="confirmed" type="checkbox" />{{ role==='teacher'?'已核对方案，确认提交调课申请':'已核对所有课次与影响，确认更新课表' }}</label></template></fieldset>
          <p v-if="result.content.applied_result" class="work-success">{{ result.content.applied_result.message }}</p>
        </section>
        <section v-if="tab==='history'&&courseId"><h3>已保存的工作结果</h3><p class="work-note">任务完成后自动保留，刷新或关闭窗口后可继续查看。</p><PagedList :items="emptyHistory" :load-page="loadHistory" :scope="`${courseId}:${historyRevision}`" :page-size="6" label="教学工作记录" v-slot="{items}"><button v-for="row in items" :key="row.id" type="button" class="work-source-row" @click="run(()=>openResult(row.id))"><strong>{{ title(row.kind) }}</strong><small>{{ new Date(row.created_at).toLocaleString('zh-CN') }}</small><span>{{ row.status==='adopted'?'已使用':'待核对' }} ›</span></button></PagedList></section>
      </fieldset>
    </div>
    <template #footer><span>{{ running?'任务后台运行，可稍后恢复查看':result?.status==='adopted'?'工作结果已保存':dirty?'有未保存的编辑':'核对确认后才执行相应操作' }}</span><button v-if="result?.status==='draft'&&((tab==='materials'&&result.kind==='material_extract')||(tab==='course'&&result.kind==='course_content')||(tab==='schedule'&&result.kind==='schedule_plan'))" type="button" :disabled="busy||!confirmed||(tab==='materials'&&!selected.length)||(tab==='course'&&!fields.length)||(tab==='schedule'&&(!result.content.choices?.length||reason.trim().length<5))" @click="adopt">{{ tab==='materials'?`保存所选 ${selected.length} 题到草稿`:tab==='course'?'采纳到课程草稿':role==='teacher'?'确认提交调课申请':'确认应用排课方案' }}</button></template>
  </DetailDialog>
</template>

<style scoped>
.teaching-workbench{font-size:13px;color:#344e6f;line-height:1.7;min-width:0}.teaching-workbench fieldset{border:0;margin:0;padding:0;min-width:0}.workbench-tabs{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:5px;padding:10px 18px;border-bottom:1px solid #e4ebf5;flex:none}.workbench-tabs button{background:#f6f8fd;color:#7889a4;font-size:12px;padding:10px 4px;border:0;min-width:0}.workbench-tabs button.active,.work-source-nav button.active{background:#eaf0ff;color:#4662d2;font-weight:700}.teaching-workbench label{display:grid;gap:6px;font-size:12px;font-weight:600}.teaching-workbench :is(input:not([type=checkbox]):not([type=radio]),textarea,select){width:100%;min-width:0;box-sizing:border-box;font:inherit;font-weight:400;border:1px solid #d4dff1;border-radius:10px;padding:10px 12px;color:#344e6f;background:white;line-height:1.6}.teaching-workbench textarea{resize:vertical}.teaching-workbench button{font-size:12px}.work-course,.work-heading,.work-actions,.work-search,.work-source-nav,.work-weekdays{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.work-course{margin-bottom:18px;align-items:end}.work-course>label,.work-search>label{flex:1;min-width:0}.work-heading{justify-content:space-between;margin-bottom:12px}.work-heading>div{min-width:0}.work-heading p,.work-note,.work-upload small,.work-heading>span{font-size:12px;color:#7d8da5;margin:6px 0}.teaching-workbench h3{font-size:15px;margin:0 0 8px}.work-setup,.work-result{display:grid;gap:14px;margin-top:16px}.work-source-picker,.work-source-detail,.work-upload{border:1px solid #e1e8f5;border-radius:14px;padding:14px;min-width:0}.work-upload{display:grid;gap:12px;background:#f7faff;margin-bottom:12px}.work-source-nav{margin-bottom:12px}.work-source-nav button{background:#f1f5fb;color:#7288a5}.work-source-row{width:100%;display:flex;align-items:center;gap:10px;text-align:left;padding:12px!important;margin:7px 0;background:#f8faff;color:#466080;border:1px solid #e2e9f4;min-width:0}.work-source-row strong{flex:1;min-width:0;overflow-wrap:anywhere}.work-source-row small,.work-source-row>span{font-size:11px;color:#8191aa}.work-source-row.selected{border-color:#9db0f0;background:#eff3ff}.work-range{display:grid;grid-template-columns:1fr 1fr auto;gap:10px;align-items:end;margin:12px 0}.work-page{border:1px solid #e0e7f3;border-radius:10px;padding:12px;margin-top:9px;min-width:0}.work-page summary{font-weight:600;cursor:pointer;color:#496594}.work-page pre{font:inherit;font-size:12px;white-space:pre-wrap;overflow-wrap:anywhere;max-height:300px;overflow:auto;background:#f8faff;padding:10px;border-radius:8px}.work-page label{margin-top:10px}.work-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}.work-check{display:flex!important;align-items:center;gap:8px;font-weight:400!important}.work-check input,.work-lesson>input,.work-candidate-heading>input{width:16px;height:16px;flex:none}.work-weekdays{padding:10px;background:#f7faff;border-radius:10px}.work-lesson{display:flex!important;gap:10px;align-items:center;padding:12px 4px;border-bottom:1px solid #e5ebf4}.work-lesson>span{display:grid;min-width:0}.work-lesson small{color:#8091aa;font-size:11px}.work-candidate{border:1px solid #dfe7f4;border-radius:12px;overflow:hidden;margin-top:10px}.work-candidate-heading{display:flex;gap:10px;align-items:center;padding:12px}.work-candidate-heading>button{display:grid;gap:5px;background:transparent;color:#3b5275;text-align:left;min-width:0;padding:0;box-shadow:none;flex:1}.work-candidate-heading strong{display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;font-size:13px;overflow-wrap:anywhere}.work-candidate-heading small{font-size:11px;color:#8092ad}.work-candidate-edit{display:grid;gap:12px;padding:14px;border-top:1px solid #e5ebf5;background:#fbfcff}.work-confirm{background:#f0f4ff;padding:14px;border-radius:10px}.work-job{display:flex;align-items:center;gap:10px;background:#f1f5ff;border:1px solid #dfe7fb;padding:12px;border-radius:12px;flex-wrap:wrap}.work-job>div{flex:1;min-width:130px}.work-job p{font-size:12px;color:#7d8eaa;margin:3px 0}.work-spinner{display:inline-block;width:16px;height:16px;flex:none;border:2px solid #d6e1fc;border-top-color:#5570df;border-radius:50%;animation:work-spin .9s linear infinite}.work-loading{display:flex;align-items:center;gap:8px;color:#637ed5;font-size:12px}.work-error{background:#fff0ec;color:#a64b3c;border-radius:10px;padding:12px}.work-success{background:#edf8f1;color:#367457;border-radius:10px;padding:12px}.work-plan{border:1px solid #dfe7f4;border-radius:12px;padding:14px;margin:12px 0;min-width:0}.work-plan.selected{border-color:#9cafeb;background:#f7f9ff}.work-plan-lesson{display:grid;gap:6px;padding:10px 0;border-top:1px solid #e4ebf6;margin-top:10px;overflow-wrap:anywhere}.work-plan-lesson small{color:#8390a4;font-size:11px}.work-plan-lesson span{color:#466599;font-size:12px}.work-conditions{display:flex;flex-wrap:wrap;gap:6px}.work-conditions>span{background:#eef3fc;color:#647ea3;font-size:11px;padding:6px 9px;border-radius:8px}@keyframes work-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.work-spinner{animation:none}}@media(max-width:600px){.teaching-workbench{font-size:12px}.teaching-workbench :is(input:not([type=checkbox]):not([type=radio]),textarea,select){font-size:12px}.workbench-tabs{padding:8px;gap:3px}.workbench-tabs button{font-size:11px}.work-source-row small{display:none}.work-source-picker,.work-source-detail,.work-upload{padding:11px}.work-range{grid-template-columns:1fr 1fr}.work-range>button{grid-column:1/-1}.work-course>label{flex-basis:100%}.work-actions{gap:6px}.work-weekdays{gap:12px 9px}.work-job button{font-size:11px}.work-candidate-heading{padding:10px}.work-candidate-edit{padding:11px}.work-plan{padding:11px}}
</style>
