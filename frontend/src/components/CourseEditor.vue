<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import PagedList from './PagedList.vue'
import RichText from './RichText.vue'

type Section = { id: string; title: string; description: string; archived: boolean }
type Point = { id: string; name: string; description: string; section_id: string | null }
type Content = { title: string; description: string; learning_objectives: string; assessment: string; cover_image_url: string; owner_id: string | null; sections: Section[]; knowledge_points: Point[]; knowledge_base_ids: string[] }
type State = { course_id: string; code: string; semester: string | null; status: string; revision: number; has_draft: boolean; base_signature: string; stale: boolean; content: Content; live: Content; libraries: Library[]; owner_name: string | null }
type Library = { id: string; name: string; course?: string }
type Teacher = { id: string; name: string; username: string }
type Page<T> = { items: T[]; total: number; page: number; page_size: number }
type Job = { id: string; status: string; stage: string; progress_percent: number; error_message?: string }
const props = defineProps<{ courseId: string; role: string; teacherName?: string | null; request: (path: string, options?: RequestInit) => Promise<unknown> }>()
const emit = defineEmits<{ close: []; published: []; dirty: [value: boolean]; saving: [value: boolean]; materials: []; assist: [] }>()
const state = ref<State | null>(null), baseline = ref(''), tab = ref('overview'), busy = ref(false), error = ref(''), message = ref(''), confirmed = ref(false)
const librarySearch = ref(''), libraryKeyword = ref(''), teacherSearch = ref(''), teacherKeyword = ref('')
const libraryNames = ref<Record<string, string>>({}), teacherLabel = ref(''), selectedFile = ref<File | null>(null), uploadBase = ref(''), uploadJob = ref<Job | null>(null), uploading = ref(false)
const fileInput = ref<HTMLInputElement | null>(null)
const sectionSearch = ref(''), pointSearch = ref('')
const newSections = ref(new Set<string>()), newPoints = ref(new Set<string>())
const sectionRevision = ref(0), pointRevision = ref(0)
const controller = new AbortController()
const path = `/api/v1/courses/${props.courseId}/editor`
const content = computed(() => state.value?.content)
const dirty = computed(() => !!state.value && JSON.stringify(state.value.content) !== baseline.value)
const working = computed(() => busy.value || uploading.value)
const sections = computed(() => content.value?.sections.filter(x => `${x.title} ${x.description}`.includes(sectionSearch.value)) || [])
const points = computed(() => content.value?.knowledge_points.filter(x => `${x.name} ${x.description}`.includes(pointSearch.value)) || [])
const selectedLibraries = computed(() => content.value?.knowledge_base_ids.map(id => ({ id, name: libraryNames.value[id] || '已关联资料库' })) || [])
const uploadLibraries = computed(() => state.value?.live.knowledge_base_ids.map(id => ({ id, name: libraryNames.value[id] || '已关联资料库' })) || [])
const tabs = [{ id: 'overview', name: '课程概览' }, { id: 'outline', name: '教学大纲' }, { id: 'materials', name: '课程资料' }, { id: 'points', name: '知识点' }, { id: 'preview', name: '发布预览' }]
watch(dirty, value => { emit('dirty', value); confirmed.value = false })
watch(working, value => emit('saving', value))
function accept(value: State) {
  state.value = value; baseline.value = JSON.stringify(value.content); confirmed.value = false
  teacherLabel.value = value.owner_name || '未分配'
  for (const row of value.libraries) libraryNames.value[row.id] = row.name
  uploadBase.value = value.live.knowledge_base_ids.includes(uploadBase.value) ? uploadBase.value : value.live.knowledge_base_ids[0] || ''
}
async function run(fn: () => Promise<void>) {
  if (working.value) return
  busy.value = true; error.value = ''; message.value = ''
  try { await fn() } catch (e) { if (!controller.signal.aborted) error.value = e instanceof Error ? e.message : '操作未完成，请重试。' }
  finally { busy.value = false }
}
const read = <T,>(url: string, options?: RequestInit) => props.request(url, { ...options, signal: controller.signal }) as Promise<T>
const write = (url: string, data: unknown, method = 'POST') => read<State>(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
async function load() {
  await run(async () => { accept(await read<State>(path)) })
}
function close() {
  if (working.value) return
  if (dirty.value && !window.confirm('有尚未保存的修改，确定离开？已保存的课程草稿仍会保留。')) return
  emit('close')
}
async function save() {
  await run(async () => {
    if (!state.value) return
    accept(await write(path, { revision: state.value.revision, base_signature: state.value.base_signature, content: state.value.content }, 'PUT'))
    message.value = '课程草稿已保存，尚未更新学生看到的内容。'
  })
}
async function discard() {
  if (!state.value || !window.confirm('放弃已保存的草稿和当前修改，重新读取已发布内容？')) return
  if (!state.value.has_draft) { await load(); return }
  await run(async () => { accept(await write(path + '/discard', { revision: state.value!.revision })); message.value = '已恢复当前课程内容。' })
}
async function publish() {
  if (dirty.value || !confirmed.value || !state.value?.has_draft) return
  await run(async () => {
    accept(await write(path + '/publish', { revision: state.value!.revision, confirmed: true }))
    message.value = state.value!.status === 'published' ? '课程内容已更新，学生可查看最新内容。' : '内容已确认保存；课程仍未发布，可返回课程详情发布课程。'
    emit('published')
  })
}
function addSection() { const id = crypto.randomUUID(); content.value?.sections.unshift({ id, title: '', description: '', archived: false }); newSections.value.add(id); sectionSearch.value = ''; sectionRevision.value++ }
async function assist() { if (dirty.value) await save(); if (!dirty.value && !working.value) emit('assist') }
function moveSection(id: string, offset: number) {
  const rows = content.value?.sections; if (!rows) return
  const index = rows.findIndex(x => x.id === id), target = index + offset
  if (index < 0 || target < 0 || target >= rows.length) return
  const [row] = rows.splice(index, 1); rows.splice(target, 0, row!)
}
function removeSection(id: string) {
  if (!content.value || !window.confirm('从课程草稿中移除此章节？已有教学或学习记录的章节在发布时会阻止删除。')) return
  if (content.value.knowledge_points.some(x => x.section_id === id)) { error.value = '请先调整该章节下知识点的所属章节。'; return }
  content.value.sections = content.value.sections.filter(x => x.id !== id)
}
function addPoint() { const id = crypto.randomUUID(); content.value?.knowledge_points.unshift({ id, name: '', description: '', section_id: null }); newPoints.value.add(id); pointSearch.value = ''; pointRevision.value++ }
function removePoint(id: string) {
  if (content.value && window.confirm('从课程草稿中移除此知识点？')) content.value.knowledge_points = content.value.knowledge_points.filter(x => x.id !== id)
}
function toggleLibrary(row: Library) {
  if (!content.value) return
  libraryNames.value[row.id] = row.name
  content.value.knowledge_base_ids = content.value.knowledge_base_ids.includes(row.id) ? content.value.knowledge_base_ids.filter(id => id !== row.id) : [...content.value.knowledge_base_ids, row.id]
}
async function loadLibraries(page: number, size: number) {
  const result = await read<Page<Library>>(`${path}/libraries?${new URLSearchParams({ page: String(page), page_size: String(size), keyword: libraryKeyword.value })}`)
  for (const row of result.items) libraryNames.value[row.id] = row.name
  return result
}
const loadTeachers = (page: number, size: number) => read<Page<Teacher>>(`${path}/teachers?${new URLSearchParams({ page: String(page), page_size: String(size), keyword: teacherKeyword.value })}`)
async function upload() {
  if (!selectedFile.value || !uploadBase.value || working.value) return
  if (selectedFile.value.size > 30 * 1024 * 1024) { error.value = '单份 PDF 请控制在 30 MB 内。'; return }
  uploading.value = true; error.value = ''; message.value = ''; uploadJob.value = null
  try {
    const form = new FormData(); form.append('file', selectedFile.value)
    uploadJob.value = await read<Job>(`/api/v1/knowledge-bases/${uploadBase.value}/document-jobs`, { method: 'POST', body: form })
    for (let i = 0; i < 120 && !['completed', 'failed'].includes(uploadJob.value.status); i++) {
      await new Promise<void>(resolve => { const timer = window.setTimeout(done, 1000); function done() { clearTimeout(timer); controller.signal.removeEventListener('abort', done); resolve() }; controller.signal.addEventListener('abort', done, { once: true }) })
      if (controller.signal.aborted) return
      uploadJob.value = await read<Job>(`/api/v1/document-jobs/${uploadJob.value.id}`)
    }
    if (uploadJob.value.status === 'failed') throw new Error(uploadJob.value.error_message || '资料索引失败，可到资料库重试。')
    message.value = uploadJob.value.status === 'completed' ? '资料已上传并索引，可在资料库核对发布状态和原文。' : '资料仍在后台处理，可到资料库查看进度。'
    selectedFile.value = null; if (fileInput.value) fileInput.value.value = ''; emit('published')
  } catch (e) { if (!controller.signal.aborted) error.value = e instanceof Error ? e.message : '上传未完成。' }
  finally { uploading.value = false }
}
function openMaterials() { closeForMaterials() }
function closeForMaterials() { if (!working.value && (!dirty.value || window.confirm('尚未保存的修改将丢失，确定打开资料库？'))) emit('materials') }
function beforeUnload(event: BeforeUnloadEvent) { if (dirty.value || working.value) { event.preventDefault(); event.returnValue = '' } }
onMounted(() => { window.addEventListener('beforeunload', beforeUnload); void load() })
onBeforeUnmount(() => { controller.abort(); window.removeEventListener('beforeunload', beforeUnload); emit('dirty', false); emit('saving', false) })
defineExpose({ signature: () => JSON.stringify(content.value), discardEdits: () => { if (state.value && baseline.value) state.value.content = JSON.parse(baseline.value) } })
</script>

<template>
  <DetailDialog title="编辑课程" :kicker="state ? `${state.code} · ${state.semester || '学期待设置'}` : undefined" :close-disabled="working" :view-key="tab" @close="close">
    <template #navigation><nav class="course-editor-tabs" aria-label="课程编辑区域"><button v-for="item in tabs" :key="item.id" type="button" :class="{ active: tab === item.id }" :disabled="working" @click="tab = item.id">{{ item.name }}</button></nav></template>
    <div class="course-editor">
      <p v-if="error" class="course-editor-error" role="alert">{{ error }}</p><p v-if="message" class="course-editor-success" role="status">{{ message }}</p>
      <p v-if="busy" class="course-editor-loading" role="status"><span />正在处理课程内容…</p>
      <button v-if="!state && !busy" type="button" @click="load">重新读取课程</button>
      <template v-if="state && content">
        <p v-if="state.stale" class="course-editor-error">课程内容已有其他修改。请先复制保留需要的草稿，再放弃草稿读取最新课程。</p>
        <fieldset :disabled="working || state.stale">
          <div v-show="tab === 'overview'" class="course-editor-form">
            <div class="wide course-editor-actions"><button type="button" @click="assist">让 AI 帮我完善课程</button><small>已有修改会先保存草稿，AI 建议仍需核对。</small></div>
            <label>课程名称<input v-model="content.title" maxlength="200" /></label>
            <label>封面地址<input v-model="content.cover_image_url" maxlength="1000" type="url" placeholder="https://…（可选）" /></label>
            <label class="wide">课程介绍<textarea v-model="content.description" maxlength="3000" rows="4" placeholder="面向谁、学习内容与先修要求" /></label>
            <label class="wide">学习目标<textarea v-model="content.learning_objectives" maxlength="10000" rows="4" placeholder="支持 Markdown 列表、公式与分段" /></label>
            <label class="wide">考核方式<textarea v-model="content.assessment" maxlength="10000" rows="3" placeholder="平时作业、实验与考试安排" /></label>
            <div class="wide course-editor-note">上课时间、地点和学期由排课管理维护，编辑课程内容不会调整课表。</div>
            <details v-if="role === 'admin'" class="wide"><summary>分配授课教师 · {{ teacherLabel }}</summary><form class="course-editor-search" @submit.prevent="teacherKeyword = teacherSearch.trim()"><label>查找教师<input v-model="teacherSearch" maxlength="100" /></label><button type="submit">查询</button></form><PagedList :items="([] as Teacher[])" :load-page="loadTeachers" :scope="teacherKeyword" :page-size="5" label="可分配教师" v-slot="{ items }"><button v-for="row in items" :key="row.id" class="course-editor-choice" :class="{ selected: content.owner_id === row.id }" type="button" @click="content.owner_id = row.id; teacherLabel = row.name"><strong>{{ row.name }}</strong><small>{{ row.username }}</small><span>{{ content.owner_id === row.id ? '已选择' : '选择' }}</span></button></PagedList></details>
          </div>
          <section v-show="tab === 'outline'">
            <div class="course-editor-heading"><div><h3>教学大纲</h3><p>按授课顺序组织章节，点击展开编辑。</p></div><button type="button" @click="addSection">＋ 添加章节</button></div>
            <label>查找章节<input v-model="sectionSearch" placeholder="章节名称或内容" /></label>
            <PagedList :items="sections" :scope="`${courseId}:${sectionSearch}:${sectionRevision}`" :page-size="6" label="编辑章节" v-slot="{ items }">
              <details v-for="row in items" :key="row.id" class="course-editor-card" :open="newSections.has(row.id)">
                <summary><span>第 {{ content.sections.findIndex(x => x.id === row.id) + 1 }} 章</span><strong>{{ row.title || '新章节' }}{{ row.archived?' · 已归档':'' }}</strong></summary>
                <div class="course-editor-card-body"><label>章节名称<input v-model="row.title" maxlength="200" /></label><label>章节内容<textarea v-model="row.description" maxlength="2000" rows="4" /></label><div class="course-editor-actions"><button type="button" :disabled="content.sections[0]?.id === row.id" @click="moveSection(row.id, -1)">上移</button><button type="button" :disabled="content.sections.at(-1)?.id === row.id" @click="moveSection(row.id, 1)">下移</button><button type="button" @click="row.archived=!row.archived">{{ row.archived?'恢复章节':'归档章节' }}</button><button type="button" class="danger-action" @click="removeSection(row.id)">移除章节</button></div><small>归档后不再列于课程大纲，已有课次、作业和学习记录继续保留；发布后生效。</small></div>
              </details>
              <p v-if="!items.length" class="course-editor-note">暂无匹配章节，可添加章节。</p>
            </PagedList>
          </section>
          <section v-show="tab === 'materials'">
            <div class="course-editor-heading"><div><h3>关联课程资料库</h3><p>资料库可以供多门课程使用。关联变更在发布内容后生效。</p></div><button type="button" @click="openMaterials">打开资料库 ↗</button></div>
            <div class="course-editor-tags"><button v-for="row in selectedLibraries" :key="row.id" type="button" @click="toggleLibrary(row)">{{ row.name }} ×</button><span v-if="!selectedLibraries.length">尚未选择资料库</span></div>
            <form class="course-editor-search" @submit.prevent="libraryKeyword = librarySearch.trim()"><label>查找资料库<input v-model="librarySearch" maxlength="100" /></label><button type="submit">查询</button></form>
            <PagedList :items="([] as Library[])" :load-page="loadLibraries" :scope="libraryKeyword" :page-size="5" label="可关联资料库" v-slot="{ items }"><button v-for="row in items" :key="row.id" type="button" class="course-editor-choice" :class="{ selected: content.knowledge_base_ids.includes(row.id) }" @click="toggleLibrary(row)"><strong>{{ row.name }}</strong><span>{{ content.knowledge_base_ids.includes(row.id) ? '已选择 ✓' : '关联' }}</span></button></PagedList>
            <div class="course-editor-upload"><h3>上传学习资料</h3><p>向当前已关联的资料库上传文字型 PDF。共享资料库中的上传会影响所有关联课程；试卷答案请勿上传到学生可见的学习资料库。</p><template v-if="uploadLibraries.length"><label>上传到<select v-model="uploadBase"><option v-for="row in uploadLibraries" :key="row.id" :value="row.id">{{ row.name }}</option></select></label><label>选择 PDF<input ref="fileInput" type="file" accept=".pdf,application/pdf" @change="selectedFile = ($event.target as HTMLInputElement).files?.[0] || null" /></label><button type="button" :disabled="!selectedFile || !uploadBase" @click="upload">上传并索引</button></template><p v-else>请先关联资料库并保存、发布内容；也可打开资料库新建。</p></div>
          </section>
          <section v-show="tab === 'points'">
            <div class="course-editor-heading"><div><h3>课程知识点</h3><p>维护知识点解释与所属章节。</p></div><button type="button" @click="addPoint">＋ 添加知识点</button></div><label>查找知识点<input v-model="pointSearch" placeholder="名称或解释" /></label>
            <PagedList :items="points" :scope="`${courseId}:${pointSearch}:${pointRevision}`" :page-size="6" label="编辑知识点" v-slot="{ items }">
              <details v-for="row in items" :key="row.id" class="course-editor-card" :open="newPoints.has(row.id)">
                <summary><strong>{{ row.name || '新知识点' }}</strong><span>{{ content.sections.find(x => x.id === row.section_id)?.title || '课程通用' }}</span></summary>
                <div class="course-editor-card-body"><label>知识点名称<input v-model="row.name" maxlength="200" /></label><label>所属章节<select v-model="row.section_id"><option :value="null">课程通用</option><option v-for="section in content.sections" :key="section.id" :value="section.id">{{ section.title || '未命名章节' }}</option></select></label><label>知识点解释<textarea v-model="row.description" maxlength="3000" rows="3" /></label><button type="button" class="danger-action" @click="removePoint(row.id)">移除知识点</button></div>
              </details>
              <p v-if="!items.length" class="course-editor-note">暂无匹配知识点，可添加知识点。</p>
            </PagedList>
          </section>
          <section v-show="tab === 'preview'" class="course-editor-preview">
            <h3>{{ content.title || '未命名课程' }}</h3><RichText :source="content.description || '尚未填写课程介绍。'" :tools="false" /><h4>学习目标</h4><RichText :source="content.learning_objectives || '尚未填写。'" :tools="false" /><h4>考核方式</h4><RichText :source="content.assessment || '尚未填写。'" :tools="false" /><h4>教学大纲</h4><ol><li v-for="row in content.sections.filter(x=>!x.archived)" :key="row.id">{{ row.title }}</li></ol><p>{{ content.knowledge_points.length }} 个知识点 · {{ selectedLibraries.length }} 个资料库</p>
            <p v-if="dirty" class="course-editor-note">请先保存草稿，再确认发布。</p><label v-else-if="state.has_draft" class="course-editor-confirm"><input v-model="confirmed" type="checkbox" />已核对课程内容，确认更新课程展示内容</label><p v-else class="course-editor-note">当前没有待发布的内容草稿。</p>
          </section>
        </fieldset>
      </template>
      <p v-if="uploading" class="course-editor-loading" role="status"><span />{{ uploadJob?.stage || '正在上传资料…' }} {{ uploadJob ? `${uploadJob.progress_percent}%` : '' }}</p>
    </div>
    <template #footer><span>{{ dirty ? '有未保存修改' : state?.has_draft ? '已保存草稿 · 学生暂不可见' : '当前课程内容' }}</span><div class="course-editor-actions"><button v-if="state" type="button" class="ghost-button" :disabled="working || (!dirty && !state.has_draft)" @click="discard">{{ state.stale ? '放弃草稿并重新读取' : '放弃草稿' }}</button><button type="button" :disabled="working || !dirty || state?.stale" @click="save">保存草稿</button><button v-if="tab === 'preview'" type="button" :disabled="working || dirty || !state?.has_draft || !confirmed || state?.stale" @click="publish">确认发布内容</button><button v-else type="button" class="secondary" :disabled="working || !state" @click="tab = 'preview'">发布预览</button></div></template>
  </DetailDialog>
</template>

<style scoped>
.course-editor{font-size:13px;color:#314969;line-height:1.65}.course-editor fieldset{border:0;padding:0;margin:0;min-width:0}.course-editor-tabs{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:5px;padding:10px 20px;border-bottom:1px solid #e5ebf5;flex:none;background:#fafcff}.course-editor-tabs button{font:inherit;font-size:12px;padding:10px 4px;background:transparent;color:#7183a0;min-width:0;border:0;border-radius:9px}.course-editor-tabs button.active{background:#eaf0ff;color:#3e59d0;font-weight:700}.course-editor-form{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.wide{grid-column:1/-1}.course-editor label{display:grid;gap:7px;font-size:12px;font-weight:600}.course-editor input,.course-editor textarea,.course-editor select{box-sizing:border-box;width:100%;min-width:0;font:inherit;font-weight:400;padding:10px 12px;border:1px solid #d4dff0;border-radius:10px;background:white;color:#314969;line-height:1.6}.course-editor textarea{resize:vertical}.course-editor button{font-size:12px}.course-editor h3{font-size:15px;margin:0}.course-editor p{margin:8px 0}.course-editor-note,.course-editor-heading p,.course-editor-upload p{color:#7b8ca5;font-size:12px}.course-editor-heading{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px}.course-editor-heading>div{min-width:0}.course-editor-heading>button{flex:none}.course-editor-card{border:1px solid #e1e8f3;border-radius:12px;margin-top:10px;overflow:hidden}.course-editor-card>summary{display:flex;gap:10px;align-items:center;padding:14px;cursor:pointer;background:#f9fbff;overflow-wrap:anywhere}.course-editor-card>summary>span{font-size:11px;color:#8090a8}.course-editor-card>summary>strong{font-size:13px;flex:1}.course-editor-card-body{display:grid;gap:12px;padding:14px}.course-editor-actions{display:flex;gap:8px;flex-wrap:wrap;align-items:center}.course-editor-search{display:flex;gap:8px;align-items:end;margin:12px 0}.course-editor-search label{flex:1}.course-editor-choice{display:flex;gap:10px;align-items:center;width:100%;padding:12px!important;text-align:left;border:1px solid #e0e7f3;background:white;color:#4e6687;margin:6px 0}.course-editor-choice strong{flex:1;min-width:0;overflow-wrap:anywhere}.course-editor-choice.selected{border-color:#849bf2;background:#f2f5ff}.course-editor-choice span,.course-editor-choice small{font-size:11px}.course-editor-tags{display:flex;flex-wrap:wrap;gap:6px;font-size:12px;color:#8291a8}.course-editor-tags button{background:#edf2ff;color:#526acb;font-size:11px;white-space:normal;text-align:left}.course-editor-upload{margin-top:22px;padding:16px;border-radius:14px;background:#f5f8ff;display:grid;gap:12px}.course-editor-error{padding:10px 12px;background:#fff0ed;border-radius:10px;color:#ae5140}.course-editor-success{padding:10px 12px;background:#edf9f3;border-radius:10px;color:#30795b}.course-editor-preview{overflow-wrap:anywhere}.course-editor-confirm{display:flex!important;align-items:center;padding:14px;background:#f0f5ff;border-radius:10px}.course-editor-confirm input{width:auto}.course-editor-loading{display:flex;gap:9px;align-items:center;color:#5b73c9}.course-editor-loading>span{height:14px;width:14px;border:2px solid #dce5ff;border-top-color:#5368de;border-radius:50%;animation:course-editor-spin .8s linear infinite;flex:none}@keyframes course-editor-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.course-editor-loading>span{animation:none}}@media(max-width:600px){.course-editor-form{grid-template-columns:1fr;gap:12px}.course-editor-tabs{padding:8px;gap:2px}.course-editor-tabs button{font-size:11px;padding:9px 2px}.course-editor-heading{align-items:flex-start}.course-editor{font-size:12px}.course-editor input,.course-editor textarea,.course-editor select{font-size:12px}.course-editor-actions{gap:6px}.course-editor-actions button{font-size:11px;padding:9px 10px}.course-editor-card>summary{padding:11px}.course-editor-choice small{display:none}}
</style>
