<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
import AssistantTaskPanel from './AssistantTaskPanel.vue'
import { lockBodyScroll } from '../useBodyScrollLock'
import type { CohortAnalysisResult, CohortOverview, CohortStudent } from '../courseCohortAnalysis'

const props = defineProps<{
  courseId: string; courses: Array<{ id: string; title: string; code?: string; semester?: string | null }>; enabled: boolean
  request: (path: string, options?: RequestInit) => Promise<unknown>; renderMarkdown: (text: string) => string
}>()
const emit = defineEmits<{
  close: []; course: [id: string]; assignment: [id: string]; student: [item: CohortStudent]
  draft: [id: string]; prepare: [topic: string, type: 'lesson_plan' | 'question_set']
}>()
const overview = ref<CohortOverview | null>(null)
const result = ref<CohortAnalysisResult | null>(null)
const loading = ref(false), generating = ref(false), error = ref(''), analysisError = ref('')
const tab = ref<'overview' | 'assignments' | 'students' | 'report'>('overview')
const search = ref(''), appliedSearch = ref(''), attention = ref('all'), refreshId = ref(0)
const followingStudent = ref('')
const taskRevision = ref(0), taskMessage = ref('')
const emptyStudents: CohortStudent[] = []
const dialog = ref<HTMLElement | null>(null), closeButton = ref<HTMLButtonElement | null>(null)
const previousFocus = document.activeElement as HTMLElement | null
let releaseScroll: (() => void) | null = null
let requestId = 0, generationId = 0
let controller: AbortController | null = null, generationController: AbortController | null = null
const summary = computed(() => overview.value?.summary)
const maximumBar = computed(() => Math.max(1, ...(overview.value?.score_distribution.map(item => item.count) || [])))
const pageScope = computed(() => `${props.courseId}:${appliedSearch.value}:${attention.value}:${refreshId.value}`)
const number = (value: number | null | undefined, suffix = '') => value == null ? '—' : `${value}${suffix}`
const studentName = (id: string) => result.value?.draft.source_context.student_names?.[id] ||
  result.value?.students.find(item => item.student_id === id)?.student_name || '原课程学生'

async function load() {
  const id = ++requestId, courseId = props.courseId
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  loading.value = true
  error.value = ''
  analysisError.value = ''
  try {
    const [stats, saved] = await Promise.all([
      props.request(`/api/v1/courses/${courseId}/cohort-overview`, { signal }),
      props.request(`/api/v1/courses/${courseId}/cohort-analysis`, { signal }).catch(cause => {
        if (id === requestId && !signal.aborted) analysisError.value = cause instanceof Error ? cause.message : '已有报告读取失败，请重试。'
        return null
      }),
    ])
    if (id !== requestId || signal.aborted || courseId !== props.courseId) return
    overview.value = stats as CohortOverview
    result.value = saved as CohortAnalysisResult | null
    refreshId.value += 1
  } catch (cause) {
    if (id === requestId && !signal.aborted) {
      overview.value = null
      result.value = null
      error.value = cause instanceof Error ? cause.message : '学情读取失败，请重试。'
    }
  } finally { if (id === requestId) loading.value = false }
}

async function generate() {
  if (generating.value || !props.enabled || !summary.value?.student_count) return
  const id = ++generationId, courseId = props.courseId
  generationController?.abort()
  generationController = new AbortController()
  const signal = generationController.signal
  tab.value = 'report'
  generating.value = true
  analysisError.value = ''
  try {
    await props.request('/api/v1/assistant/tasks', {
      method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({request_id:crypto.randomUUID(),kind:'cohort_analysis',payload:{course_id:courseId,target_id:courseId,confirm_external_analysis:true}}),
    })
    if (id === generationId && !signal.aborted && courseId === props.courseId) {
      taskRevision.value++; taskMessage.value='已加入教学任务，可离开后查看。完成报告不会改变学生成绩。'
    }
  } catch (cause) {
    if (id === generationId && !signal.aborted) analysisError.value = cause instanceof Error ? cause.message : 'AI 分析失败，请重试。'
  } finally { if (id === generationId) generating.value = false }
}

async function loadStudents(page: number, size: number) {
  const query = new URLSearchParams({ page: String(page), page_size: String(size), search: appliedSearch.value, attention: attention.value })
  return await props.request(`/api/v1/courses/${props.courseId}/cohort-students?${query}`) as {
    items: CohortStudent[]; total: number; page: number; page_size: number
  }
}
function searchStudents() { appliedSearch.value = search.value.trim(); refreshId.value += 1 }
function focusStudents(filter: string) { attention.value = filter; tab.value = 'students' }
function followStudent(id: string) {
  const item = result.value?.students.find(student => student.student_id === id)
  if (item) followRecord(item)
}
function followRecord(item: CohortStudent) {
  if (item.latest_submission_id) emit('student', item)
  else { followingStudent.value = item.student_name; tab.value = 'assignments' }
}
function handleKeys(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.stopPropagation(); emit('close') }
  if (event.key !== 'Tab') return
  const controls = [...(dialog.value?.querySelectorAll<HTMLElement>('button:not(:disabled), select:not(:disabled), input:not(:disabled), [tabindex="0"]') || [])]
    .filter(item => item.getClientRects().length > 0)
  const first = controls[0], last = controls.at(-1)
  if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus() }
}
watch(() => props.courseId, () => {
  generationId += 1; generationController?.abort(); generating.value = false
  overview.value = null; result.value = null; search.value = ''; appliedSearch.value = ''; attention.value = 'all'; tab.value = 'overview'
  followingStudent.value = ''
  if (props.courseId) void load()
}, { immediate: true })
onMounted(() => { releaseScroll = lockBodyScroll(); void nextTick(() => closeButton.value?.focus()) })
onUnmounted(() => {
  releaseScroll?.()
  requestId += 1; generationId += 1; controller?.abort(); generationController?.abort()
  if (previousFocus?.isConnected) previousFocus.focus()
})
</script>

<template>
  <div class="cohort-backdrop" @click.self="$emit('close')" @keydown="handleKeys">
    <section ref="dialog" class="cohort-dialog" role="dialog" aria-modal="true" aria-labelledby="cohort-title">
      <header class="cohort-header"><div><span class="cohort-kicker">AI 教学助理 · 全体学情</span><h2 id="cohort-title">看见整体，也关注每位学生</h2></div><button ref="closeButton" type="button" class="cohort-close" aria-label="关闭课程学情" @click="$emit('close')">×</button></header>
      <div class="cohort-toolbar"><label>教学课程<select :value="courseId" @change="$emit('course', ($event.target as HTMLSelectElement).value)"><option v-for="course in courses" :key="course.id" :value="course.id">{{ course.title }}{{ course.code ? ` · ${course.code}` : '' }}{{ course.semester ? ` · ${course.semester}` : '' }}</option></select></label><button type="button" class="quiet-button" :disabled="loading || generating" @click="load">{{ loading ? '读取中…' : '刷新记录' }}</button><button type="button" class="generate-button" :disabled="loading || generating || !enabled || !summary?.student_count" @click="generate">✦ {{ generating ? 'AI 正在分析…' : result ? '更新 AI 综合分析' : 'AI 分析全体学情' }}</button></div>
      <nav class="cohort-tabs" aria-label="课程学情板块"><button v-for="item in ([['overview', '学情总览'], ['assignments', '作业表现'], ['students', '学生跟进'], ['report', 'AI 综合报告']] as const)" :key="item[0]" type="button" :class="{ active: tab === item[0] }" :aria-current="tab === item[0] ? 'page' : undefined" @click="tab = item[0]">{{ item[1] }}</button></nav>
      <div class="cohort-scroll"><p v-if="taskMessage" class="cohort-notice" role="status">{{ taskMessage }}</p><AssistantTaskPanel :key="courseId" :request="request" :refresh="taskRevision" @open-draft="emit('draft',$event)" />
        <p v-if="loading" class="cohort-notice" role="status">正在核对全体学生、成绩与提交记录…</p>
        <p v-if="error" class="cohort-error" role="alert">{{ error }} <button type="button" @click="load">重试</button></p>
        <template v-if="overview && summary">
          <section v-if="tab === 'overview'" class="cohort-overview">
            <div class="cohort-metrics"><button type="button" @click="focusStudents('all')"><span>在课学生</span><strong>{{ summary.student_count }}<small>人</small></strong><em>查看学生 ›</em></button><button type="button" @click="tab = 'assignments'"><span>已批改作业均分</span><strong>{{ number(summary.average_score) }}<small>/ 100</small></strong><em>{{ summary.scored_count }} 份可计分提交 ›</em></button><button type="button" @click="tab = 'assignments'"><span>作业提交率</span><strong>{{ number(summary.submission_rate, '%') }}</strong><em>{{ summary.submission_count }}/{{ summary.expected_submissions }} 人次 ›</em></button><button type="button" @click="focusStudents('overdue')"><span>已截止未交</span><strong>{{ summary.overdue_missing_count }}<small>人次</small></strong><em>查看待跟进学生 ›</em></button></div>
            <div class="cohort-overview-grid"><section class="cohort-card"><h3>已批改成绩分布</h3><p class="cohort-muted">{{ summary.students_with_grades }}/{{ summary.student_count }} 人有可计分记录 · 中位数 {{ number(summary.median_score) }} · 及格比例 {{ number(summary.pass_rate, '%') }}</p><div v-for="bucket in overview.score_distribution" :key="bucket.label" class="cohort-bar"><span>{{ bucket.label }}</span><div><i :style="{ width: `${bucket.count / maximumBar * 100}%` }" /></div><b>{{ bucket.count }} 份</b></div><p class="cohort-muted">按已批改、满分大于零的作业提交统计；未交不记零分，待批改不计入。不是期末总评。</p><button type="button" class="cohort-text-button" @click="focusStudents('ungraded')">还有 {{ summary.pending_count }} 份待批改，查看学生 ›</button></section>
              <section class="cohort-card"><h3>优先巩固的知识点</h3><button v-for="point in overview.weak_points.slice(0, 5)" :key="point.topic" type="button" class="cohort-topic" :disabled="point.topic === '未标注知识点'" @click="$emit('prepare', point.topic, 'lesson_plan')"><span><strong>{{ point.topic }}</strong><small>{{ point.student_count }} 人 · {{ point.unresolved_questions }} 条待掌握错题</small></span><b>{{ point.topic === '未标注知识点' ? '待补充题库标签' : '准备教案 ›' }}</b></button><p v-if="!overview.weak_points.length" class="cohort-muted">暂无未掌握错题记录，可先安排诊断练习。</p><p class="cohort-muted">基于现有错题记录，仅作教学线索。</p><button type="button" class="cohort-text-button" @click="tab = 'report'">查看 AI 的综合判断与教学建议 ↗</button></section></div>
          </section>
          <section v-if="tab === 'assignments'" class="cohort-card"><div class="cohort-section-heading"><div><h3>各次作业表现</h3><p v-if="followingStudent" class="cohort-notice">{{ followingStudent }} 暂无提交记录，可查看本课程作业，决定如何跟进。</p><p class="cohort-muted">按作业创建顺序展示；不同题目和参与学生可能不同，不直接等同期末成绩趋势。</p></div></div>
            <PagedList :items="overview.assignments" :page-size="6" :scope="courseId" label="作业学情" v-slot="{ items }"><button v-for="item in items" :key="item.id" type="button" class="cohort-assignment" @click="$emit('assignment', item.id)"><div><strong>{{ item.title }}</strong><small>已交 {{ item.submission_count }}/{{ summary.student_count }} · 已批改 {{ item.graded_count }} · 待批改 {{ item.pending_count }} · {{ item.overdue ? '已截止未交' : '尚未提交' }} {{ item.missing_count }}</small></div><div class="cohort-assignment-score"><b>{{ number(item.average_score) }}</b><small>已批改均分</small></div><span>查看作答 ›</span></button><p v-if="!items.length" class="cohort-muted">暂无已发布作业，可先准备诊断练习。</p></PagedList>
          </section>
          <section v-if="tab === 'students'" class="cohort-card"><h3>按学生跟进</h3><form class="cohort-student-filters" @submit.prevent="searchStudents"><input v-model="search" maxlength="100" placeholder="搜索姓名或账号" aria-label="搜索学生姓名或账号" /><button type="submit">查询</button><select v-model="attention" aria-label="学生跟进筛选"><option value="all">全部学生</option><option value="overdue">已截止未交</option><option value="low_score">已批改均分未达 60</option><option value="ungraded">有待批改作业</option><option value="no_grades">暂无已批改可计分记录</option></select></form>
            <PagedList :items="emptyStudents" :scope="pageScope" :load-page="loadStudents" :page-size="10" label="学生学情" v-slot="{ items }"><article v-for="student in items" :key="student.student_id" class="cohort-student"><div class="cohort-student-name"><strong>{{ student.student_name }}</strong><small>{{ student.username }}</small></div><div><b>{{ number(student.average_score) }}<small> / 100</small></b><small>{{ student.scored_count }} 份可计分 · 已交 {{ student.submission_count }}/{{ summary.assignment_count }}</small></div><div><span :class="{ 'cohort-warning': student.overdue_missing_count }">截止未交 {{ student.overdue_missing_count }} · 待批改 {{ student.pending_count }}</span><small>{{ student.weak_points.join('、') || '暂无错题知识点记录' }}</small></div><button type="button" @click="followRecord(student)">{{ student.latest_submission_id ? '查看作答 / AI 分析 ›' : '查看课程作业 ›' }}</button></article><p v-if="!items.length" class="cohort-muted">没有匹配的学生，可调整筛选条件。</p></PagedList>
          </section>
          <section v-if="tab === 'report'" class="cohort-report">
            <div v-if="generating" class="cohort-ai-wait" role="status"><span aria-hidden="true"><i /><i /><i /></span><div><strong>正在综合成绩、作业与薄弱知识点…</strong><small>完成后保存到教师草稿箱；不会修改学生成绩。</small></div></div>
            <p v-if="analysisError" class="cohort-error" role="alert">{{ analysisError }} <button type="button" :disabled="generating || !enabled" @click="generate">重试分析</button></p>
            <p v-if="!enabled" class="cohort-notice">在线 AI 尚未就绪，可继续查看统计与学生记录。</p>
            <p v-if="result?.stale" class="cohort-stale">课程成员、成绩或提交记录已变化。下方为历史分析，请更新后再据此安排教学。</p>
            <template v-if="result"><div class="cohort-report-meta"><span>AI 分析草稿 · {{ new Date(result.draft.created_at).toLocaleString('zh-CN', { hour12: false }) }}</span><button type="button" @click="$emit('draft', result.draft.id)">在教师草稿箱中编辑 ↗</button></div><p class="cohort-muted">全体统计覆盖 {{ result.coverage.student_count_total }} 人；模型个体记录 {{ result.coverage.student_count_included }}/{{ result.coverage.student_count_total }} 人，作业明细 {{ result.coverage.assignment_count_included }}/{{ result.coverage.assignment_count_total }} 份。</p><div class="cohort-card answer-markdown" v-html="renderMarkdown(result.draft.content)" />
              <section v-if="result.analysis.student_suggestions.length" class="cohort-card"><h3>从建议继续处理</h3><button v-for="suggestion in result.analysis.student_suggestions" :key="suggestion.student_id" type="button" class="cohort-follow" :disabled="!result.students.some(item => item.student_id === suggestion.student_id)" @click="followStudent(suggestion.student_id)"><span><strong>{{ studentName(suggestion.student_id) }}</strong><small>{{ suggestion.next_step }}</small></span><b>查看学生记录 ›</b></button></section></template>
            <div v-else-if="!generating && !loading" class="cohort-empty"><span>✦</span><h3>把全班数据转化为下一步教学行动</h3><p>分析优势与共性问题、作业完成情况，并给出具体学生的跟进建议。</p><button type="button" class="generate-button" :disabled="!enabled || !summary.student_count" @click="generate">开始 AI 综合分析</button></div>
            <p class="cohort-muted">点击分析会将本课程的统计、学生姓名与成绩记录发送给 AI 模型；报告仅供教师查看，不自动评分或发布。</p>
          </section>
          <p class="cohort-updated">平台记录更新于 {{ new Date(overview.generated_at).toLocaleString('zh-CN', { hour12: false }) }}</p>
        </template>
      </div>
    </section>
  </div>
</template>

<style scoped>
.cohort-backdrop { position: fixed; inset: 0; z-index: 100; background: #172c4b80; backdrop-filter: blur(6px); display: grid; place-items: center; padding: 24px; }
.cohort-dialog { background: #f4f7fc; border: 1px solid #e2e9f3; border-radius: 24px; box-shadow: 0 30px 100px #0b1f4240; display: flex; flex-direction: column; width: min(1160px, 100%); max-height: calc(100dvh - 48px); overflow: hidden; }
.cohort-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 24px 30px 14px; background: #fff; }
.cohort-kicker { color: #6485b3; font-size: 11px; letter-spacing: 1.5px; }
h2 { margin: 7px 0 0; font-size: 23px; color: #263c5c; } h3 { margin: 0 0 12px; color: #2c4466; font-size: 16px; }
button { cursor: pointer; } button:disabled { cursor: not-allowed; opacity: .5; } button:focus-visible, input:focus-visible, select:focus-visible { outline: 3px solid #9bbdf8; outline-offset: 3px; }
.cohort-close { background: #f0f4fa; color: #657990; font-size: 25px; width: 40px; height: 40px; border-radius: 12px; padding: 0; flex-shrink: 0; }
.cohort-toolbar { display: flex; gap: 10px; align-items: end; padding: 8px 30px 18px; background: #fff; }
.cohort-toolbar label { color: #73849c; display: grid; gap: 5px; font-size: 11px; flex: 1; }
select, input { border: 1px solid #dce5f2; background: #f8faff; color: #314d76; border-radius: 10px; min-height: 40px; padding: 8px 12px; font: inherit; }
.cohort-toolbar select { width: 100%; max-width: 460px; font-size: 13px; }
.quiet-button { background: #edf3fc; color: #53709b; padding: 11px 14px; border-radius: 10px; font-size: 12px; }
.generate-button { background: linear-gradient(120deg, #3f6ed7, #6571d9); color: white; padding: 12px 17px; border-radius: 10px; font-size: 13px; box-shadow: 0 4px 12px #5671cd20; }
.cohort-tabs { display: flex; gap: 6px; padding: 0 30px; background: white; border-bottom: 1px solid #e2e9f4; }
.cohort-tabs button { background: transparent; border-radius: 0; border-bottom: 3px solid transparent; padding: 14px 19px; color: #7a8ba5; font-size: 13px; }
.cohort-tabs button.active { color: #3e6fd0; border-color: #5a83dd; font-weight: 700; }
.cohort-scroll { overflow-y: auto; overscroll-behavior: contain; padding: 24px 30px; min-height: 200px; }
.cohort-metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 20px; }
.cohort-metrics button { background: white; border: 1px solid #e1e8f3; border-radius: 15px; padding: 19px; text-align: left; display: grid; gap: 10px; }
.cohort-metrics span { color: #72839d; font-size: 12px; }.cohort-metrics strong { color: #2c486e; font-size: 30px; line-height: 1.2; }.cohort-metrics small { font-size: 12px; font-weight: 400; padding-left: 4px; }.cohort-metrics em { font-style: normal; color: #6d85a8; font-size: 11px; }
.cohort-overview-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }.cohort-card { padding: 22px; background: #fff; border: 1px solid #e1e8f3; border-radius: 16px; }
.cohort-muted { color: #8390a5; font-size: 11px; line-height: 1.8; margin: 10px 0; }.cohort-bar { display: grid; grid-template-columns: 72px 1fr 44px; gap: 10px; align-items: center; font-size: 12px; color: #667d9b; margin: 17px 0; }.cohort-bar > div { background: #edf2fa; height: 10px; border-radius: 5px; overflow: hidden; }.cohort-bar i { height: 100%; background: linear-gradient(90deg, #8aa7e8, #597ed5); display: block; border-radius: inherit; }.cohort-bar b { font-size: 11px; font-weight: 500; text-align: right; }
.cohort-topic, .cohort-follow { width: 100%; background: #f7f9fe; border: 1px solid #e8edf6; padding: 13px; display: flex; justify-content: space-between; gap: 12px; text-align: left; border-radius: 10px; margin-top: 9px; color: #3f5a81; }.cohort-topic strong, .cohort-follow strong { font-size: 13px; }.cohort-topic small, .cohort-follow small { display: block; font-size: 11px; color: #8392a9; line-height: 1.6; margin-top: 5px; }.cohort-topic b, .cohort-follow b { font-size: 11px; white-space: nowrap; font-weight: 500; align-self: center; }
.cohort-text-button { background: #edf3fe; color: #537abe; border-radius: 8px; padding: 9px 12px; font-size: 11px; margin-top: 8px; }
.cohort-assignment { display: flex; align-items: center; width: 100%; gap: 22px; border-radius: 11px; border: 1px solid #e8edf5; background: #fafcff; color: #4d6585; padding: 17px; text-align: left; margin: 11px 0; }.cohort-assignment > div:first-child { flex: 1; }.cohort-assignment strong { font-size: 13px; }.cohort-assignment small { display: block; color: #8a98ac; font-size: 11px; margin-top: 7px; line-height: 1.6; }.cohort-assignment-score { text-align: center; }.cohort-assignment-score b { color: #3f66a0; font-size: 23px; }.cohort-assignment > span { font-size: 11px; }
.cohort-student-filters { display: flex; gap: 8px; margin: 16px 0; flex-wrap: wrap; }.cohort-student-filters input { flex: 1; min-width: 130px; font-size: 13px; }.cohort-student-filters select { font-size: 12px; }.cohort-student-filters button { background: #eaf1fe; color: #4d75b6; border-radius: 9px; padding: 8px 14px; }
.cohort-student { display: grid; grid-template-columns: minmax(90px, .7fr) minmax(120px, 1fr) minmax(130px, 1.5fr) auto; gap: 18px; align-items: center; border-bottom: 1px solid #edf1f7; padding: 17px 0; color: #4d6689; font-size: 12px; }.cohort-student small { display: block; font-size: 10px; color: #8d9ab0; line-height: 1.7; margin-top: 4px; }.cohort-student b > small { display: inline; }.cohort-student-name strong { color: #324f77; font-size: 14px; }.cohort-student button { padding: 9px; background: #edf3fc; color: #557ab6; font-size: 11px; border-radius: 8px; }.cohort-warning { color: #b78346; }
.cohort-report { display: grid; gap: 15px; }.cohort-report-meta { display: flex; justify-content: space-between; align-items: center; gap: 15px; font-size: 11px; color: #7b8ea9; }.cohort-report-meta button { background: #e7eefc; color: #4c74b9; padding: 9px 13px; border-radius: 8px; }.cohort-notice, .cohort-stale, .cohort-error { border-radius: 10px; padding: 13px 16px; font-size: 12px; line-height: 1.7; }.cohort-notice { background: #eaf1fd; color: #5e7aa5; }.cohort-stale { background: #fff4df; color: #98713c; }.cohort-error { background: #fff0f0; color: #b16060; }.cohort-error button { background: transparent; color: inherit; text-decoration: underline; padding: 4px; }
.cohort-ai-wait { background: #eef3ff; padding: 20px; border: 1px solid #dae5ff; border-radius: 14px; display: flex; gap: 18px; align-items: center; color: #5372aa; }.cohort-ai-wait small { display: block; color: #8195b4; font-size: 11px; margin-top: 7px; }.cohort-ai-wait > span { display: flex; gap: 5px; }.cohort-ai-wait i { width: 7px; height: 7px; border-radius: 50%; background: #7898d5; animation: cohort-pulse 1.2s ease-in-out infinite; }.cohort-ai-wait i:nth-child(2) { animation-delay: .16s; }.cohort-ai-wait i:nth-child(3) { animation-delay: .32s; }@keyframes cohort-pulse { 50% { transform: translateY(-5px); opacity: .4; } }
.cohort-empty { text-align: center; padding: 40px 12px; color: #8294ad; }.cohort-empty > span { font-size: 34px; color: #7196d3; }.cohort-empty h3 { margin-top: 16px; }.cohort-empty p { font-size: 12px; line-height: 1.8; }.cohort-empty button { margin-top: 15px; }.cohort-updated { font-size: 10px; color: #99a6b9; text-align: right; margin: 18px 0 0; }
@media (max-width: 780px) { .cohort-backdrop { padding: 10px; }.cohort-dialog { max-height: calc(100dvh - 20px); border-radius: 16px; }.cohort-header { padding: 18px 16px 10px; }h2 { font-size: 18px; }.cohort-toolbar { padding: 8px 16px 14px; flex-wrap: wrap; }.cohort-toolbar label { flex-basis: 100%; }.cohort-toolbar select { max-width: none; }.cohort-tabs { padding: 0 10px; gap: 0; }.cohort-tabs button { padding: 13px 11px; font-size: 12px; }.cohort-scroll { padding: 16px; }.cohort-metrics { grid-template-columns: 1fr 1fr; gap: 9px; }.cohort-metrics button { padding: 14px; }.cohort-metrics strong { font-size: 25px; }.cohort-overview-grid { grid-template-columns: 1fr; gap: 14px; }.cohort-card { padding: 16px; }.cohort-student { grid-template-columns: 1fr 1fr; gap: 12px; }.cohort-student > div:nth-child(3) { grid-column: 1 / -1; }.cohort-student button { grid-column: 1 / -1; }.cohort-assignment { gap: 10px; padding: 12px; }.cohort-assignment > span { display: none; }.cohort-report-meta { flex-wrap: wrap; } }
@media (prefers-reduced-motion: reduce) { .cohort-ai-wait i { animation: none; } }
</style>
