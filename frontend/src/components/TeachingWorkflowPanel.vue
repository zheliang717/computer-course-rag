<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
import type { DraftAssignmentPreview, DraftAssignmentProgress, DraftAssignmentReceipt, TeachingWorkflow } from '../teachingWorkflow'

const props = defineProps<{ draftId: string; status: string; request: (path: string, options?: RequestInit) => Promise<unknown> }>()
const emit = defineEmits<{ openAssignment: [id: string]; changed: [] }>()
const summary = ref<TeachingWorkflow | null>(null)
const preview = ref<DraftAssignmentPreview | null>(null)
const receipt = ref<DraftAssignmentReceipt | null>(null)
const loading = ref(false)
const preparing = ref(false)
const saving = ref(false)
const error = ref('')
const title = ref('')
const description = ref('')
const dueAt = ref('')
const confirmed = ref(false)
const revision = ref(0)
const emptyRows: DraftAssignmentProgress[] = []
const controller = new AbortController()
let live = true
let sequence = 0
const statusLabel = (value: string) => ({ draft: '草稿', published: '已发布', closed: '已关闭' } as Record<string, string>)[value] || value
const time = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '未设截止'
const loadPage = (page: number, size: number) => props.request(`/api/v1/teaching-drafts/${props.draftId}/assignments?page=${page}&page_size=${size}`, { signal: controller.signal }) as Promise<{ items: DraftAssignmentProgress[]; total: number; page: number; page_size: number }>

async function readSummary() {
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const value = await props.request(`/api/v1/teaching-drafts/${props.draftId}/workflow`, { signal: controller.signal }) as TeachingWorkflow
    if (!live || current !== sequence) return
    summary.value = value
    revision.value += 1
  } catch (cause) { if (live && current === sequence) error.value = cause instanceof Error ? cause.message : '暂时无法读取教学记录，请重试。' }
  finally { if (live && current === sequence) loading.value = false }
}

async function prepare() {
  if (preparing.value || saving.value || props.status !== 'published') return
  preparing.value = true
  error.value = ''
  confirmed.value = false
  try {
    const value = await props.request(`/api/v1/teaching-drafts/${props.draftId}/assignment-preview`, { signal: controller.signal }) as DraftAssignmentPreview
    if (!live) return
    preview.value = value
    receipt.value = null
    title.value = value.default_title
    description.value = ''
    dueAt.value = ''
  } catch (cause) { if (live) error.value = cause instanceof Error ? cause.message : '预览读取失败，请重试。' }
  finally { if (live) preparing.value = false }
}

async function save() {
  if (!preview.value?.ready || !confirmed.value || saving.value || title.value.trim().length < 2) return
  const due = dueAt.value ? new Date(dueAt.value) : null
  if (due && !Number.isFinite(due.getTime())) { error.value = '请检查截止时间。'; return }
  saving.value = true
  error.value = ''
  try {
    const value = await props.request(`/api/v1/teaching-drafts/${props.draftId}/assignments`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
      body: JSON.stringify({ request_id: preview.value.request_id, expected_signature: preview.value.expected_signature,
        title: title.value.trim(), description: description.value.trim() || null, due_at: due?.toISOString() || null, confirmed: true }),
    }) as DraftAssignmentReceipt
    if (!live) return
    receipt.value = value
    preview.value = null
    emit('changed')
    await readSummary()
  } catch (cause) { if (live) error.value = `${cause instanceof Error ? cause.message : '暂未读到保存结果。'} 若请求中断，请先刷新下方关联记录；同一预览重试不会重复创建。` }
  finally { if (live) saving.value = false }
}

watch([() => props.draftId, () => props.status], () => {
  preview.value = null
  receipt.value = null
  confirmed.value = false
  void readSummary()
}, { immediate: true })
onBeforeUnmount(() => { live = false; sequence += 1; controller.abort() })
</script>

<template>
  <section class="teaching-workflow" aria-label="本批题目教学跟进" :aria-busy="loading || preparing || saving">
    <header><div><small>从题目到课堂</small><h3>本批题目的后续安排</h3></div><button type="button" class="light-button" :disabled="loading || saving" @click="readSummary">{{ loading ? '读取中…' : '刷新记录' }}</button></header>
    <div class="workflow-path"><span :class="{ reached: status === 'published' }">① 审核并入库</span><i>→</i><span :class="{ reached: summary?.linked_assignment_count }">② 准备课程作业</span><i>→</i><span :class="{ reached: summary?.assignment_statuses.published || summary?.assignment_statuses.closed }">③ 查看提交与讲评</span></div>
    <p v-if="loading || preparing || saving" class="workflow-wait" role="status"><span />{{ saving ? '正在保存作业草稿，请稍候…' : preparing ? '正在核对本批题目与课程信息…' : '正在读取最新教学记录…' }}</p>
    <p v-if="error" role="alert" class="workflow-error">{{ error }}</p>
    <template v-if="summary">
      <div class="workflow-metrics"><article><small>本批题库</small><strong>{{ summary.available_question_count }} <em>道</em></strong></article><article><small>关联作业</small><strong>{{ summary.linked_assignment_count }} <em>份</em></strong></article><article><small>当前课程成员</small><strong>{{ summary.current_student_count }} <em>人</em></strong></article></div>
      <p v-if="summary.missing_question_count" class="workflow-error">原批次中有 {{ summary.missing_question_count }} 道题已不可用，请先核对题库。</p>
      <div v-if="summary.independent_practice" class="practice-strip"><strong>独立练习</strong><p v-if="summary.independent_practice.attempts">{{ summary.independent_practice.students }} 人参与 · {{ summary.independent_practice.attempts }} 次作答 · {{ summary.independent_practice.scored_attempts }} 次可判分<span v-if="summary.independent_practice.accuracy_percent !== null"> · 正确率 {{ summary.independent_practice.accuracy_percent }}%</span></p><p v-else>本批题目还没有独立练习记录。</p></div>
    </template>
    <div class="workflow-primary"><button type="button" :disabled="preparing || saving || status !== 'published'" @click="prepare">{{ preparing ? '正在准备…' : preview ? '重新读取题目预览' : '用本批题目准备作业' }}</button><small>{{ status === 'published' ? '先核对内容并保存草稿，学生暂不可见。' : '逐题审核、确认并入库后，可继续准备作业。' }}</small></div>
    <section v-if="preview" class="assignment-preview" aria-label="作业草稿预览">
      <header><h4>核对作业草稿</h4><button type="button" class="light-button" :disabled="saving" @click="preview = null">收起预览</button></header>
      <p>{{ preview.course_title }} · {{ preview.question_count }} 道题 · 当前 {{ preview.current_student_count }} 位课程成员</p>
      <p v-for="problem in preview.problems" :key="problem" class="workflow-error">{{ problem }}</p>
      <label>作业名称<input v-model="title" maxlength="200" :disabled="saving" /></label>
      <div class="preview-fields"><label>截止时间<input v-model="dueAt" type="datetime-local" :disabled="saving" /></label><label>补充说明<textarea v-model="description" rows="2" maxlength="3000" :disabled="saving" placeholder="可补充完成要求，留空也可保存。" /></label></div>
      <details v-for="question in preview.questions" :key="question.question_id" class="preview-question"><summary>第 {{ question.position }} 题 · {{ question.knowledge_point || '课程知识' }}<b v-if="question.changed_since_publication">题库内容已调整，请重新核对</b></summary><p>{{ question.stem }}</p><ul v-if="question.options.length"><li v-for="option in question.options" :key="option">{{ option }}</li></ul><p><strong>参考答案：</strong>{{ question.correct_answer }}</p><p><strong>解析：</strong>{{ question.explanation || '尚未补充' }}</p></details>
      <p v-for="(finding, index) in preview.findings" :key="index" class="workflow-muted">第 {{ finding.question_index }} 题：{{ finding.message }}</p>
      <p class="workflow-muted">{{ preview.notice }} 成员以实际发布后的课程访问范围为准。</p>
      <label class="preview-confirm"><input v-model="confirmed" type="checkbox" :disabled="saving || !preview.ready" /><span>已核对本批题目与作业信息，确认仅保存为草稿。</span></label>
      <button type="button" :disabled="!preview.ready || !confirmed || saving || title.trim().length < 2" @click="save">{{ saving ? '正在保存…' : '确认保存作业草稿' }}</button>
    </section>
    <section v-if="receipt" class="assignment-receipt" role="status"><strong>{{ receipt.reused ? '已恢复原作业' : '作业草稿已保存' }}</strong><p>{{ receipt.title }} · {{ statusLabel(receipt.status) }}</p><small v-if="receipt.status === 'draft'">学生暂不可见；进入作业详情核对后，由你单独发布。</small><button type="button" @click="emit('openAssignment', receipt.assignment_id)">{{ receipt.status === 'draft' ? '打开作业草稿核对 ↗' : '打开关联作业 ↗' }}</button></section>
    <section class="linked-assignments"><header><h4>关联作业与后续表现</h4><small>当前课程成员口径</small></header><PagedList :items="emptyRows" :load-page="loadPage" :scope="`${draftId}:${revision}`" :page-size="5" label="关联作业" v-slot="{ items, total }"><article v-for="item in items" :key="item.id" class="linked-assignment"><header><strong>{{ item.title }}</strong><span>{{ statusLabel(item.status) }}</span></header><small>{{ item.question_count }} 道题 · {{ time(item.due_at) }}</small><div v-if="item.status !== 'draft'" class="assignment-progress"><span>已交 {{ item.active_submission_count }}/{{ item.current_student_count }}</span><span>待批改 {{ item.pending_review_count }}</span><span>已批改 {{ item.graded_count }}</span><span>{{ item.average_score_percent === null ? '暂无已批改均分' : `已批改均分 ${item.average_score_percent}%` }}</span></div><p v-else class="workflow-muted">尚未发布，学生暂不可见。</p><p v-if="item.all_submission_count !== item.active_submission_count" class="workflow-muted">另有 {{ item.all_submission_count - item.active_submission_count }} 份原课程成员的提交保留在详情中。</p><div class="assignment-actions"><span v-if="item.has_published_review">已有讲评记录，可进入核对</span><button type="button" class="light-button" @click="emit('openAssignment', item.id)">{{ item.status === 'draft' ? '核对并发布 ↗' : '查看作答 · 批改与讲评 ↗' }}</button></div></article><p v-if="!total" class="workflow-muted">还没有从本批题目创建的关联作业。普通作业与旧记录不自动追认来源。</p></PagedList></section>
    <p v-if="summary" class="workflow-muted">{{ summary.note }}</p>
  </section>
</template>

<style scoped>
.teaching-workflow { border: 1px solid #dbe5f2; border-radius: 15px; background: #f7faff; padding: 17px; min-width: 0; }
header, .workflow-path, .workflow-primary, .assignment-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
header, .assignment-actions { justify-content: space-between; }
header small, .workflow-muted, .workflow-primary small, .linked-assignment > small { font-size: 11px; color: #8395ad; line-height: 1.8; }
h3, h4 { color: #405e86; font-size: 14px; margin: 5px 0 9px; }
h4 { font-size: 12px; }
button { font-size: 12px; line-height: 1.6; }
.light-button { background: #eaf0fa; color: #6682a8; padding: 7px 10px; }
.workflow-path { font-size: 11px; color: #9aa9bd; margin: 13px 0; }
.workflow-path span { border: 1px solid #e1e8f2; padding: 6px 8px; border-radius: 8px; }
.workflow-path span.reached { color: #5279ae; background: #eaf2ff; border-color: #cdddf3; }
.workflow-path i { font-style: normal; }
.workflow-metrics { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 10px; }
.workflow-metrics article { background: #fff; padding: 12px; border: 1px solid #e2eaf4; border-radius: 10px; }
.workflow-metrics small { color: #899bb4; font-size: 11px; }
.workflow-metrics strong { display: block; color: #4e6d96; font-size: 23px; margin-top: 7px; }
em { font-size: 11px; font-weight: 400; font-style: normal; color: #9aabc0; }
.practice-strip { color: #7b91ad; background: #eef4fc; margin: 12px 0; padding: 10px 12px; border-radius: 10px; font-size: 11px; }
.practice-strip p { margin: 5px 0 0; }
.workflow-primary { margin: 14px 0; }
.assignment-preview { border: 1px solid #cbdcf3; background: #fff; border-radius: 12px; padding: 15px; }
.assignment-preview > p, .preview-question p, .preview-question li { color: #7188a7; font-size: 12px; line-height: 1.9; overflow-wrap: anywhere; }
label { display: grid; gap: 7px; color: #748aa9; font-size: 11px; margin: 10px 0; }
input, textarea { width: 100%; min-width: 0; box-sizing: border-box; color: #4d6c95; font: inherit; font-size: 12px; border: 1px solid #d3dfef; border-radius: 9px; background: #f9fbff; padding: 10px; }
.preview-fields { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.preview-question { border-top: 1px solid #e4ebf5; padding: 11px 0; }
summary { color: #58789f; font-size: 11px; cursor: pointer; line-height: 1.8; }
summary b { color: #a28762; font-weight: 400; margin-left: 10px; }
.preview-confirm { display: flex; align-items: start; gap: 8px; line-height: 1.8; margin-top: 16px; }
.preview-confirm input { width: 15px; height: 15px; flex: 0 0 15px; accent-color: #718fc0; }
.assignment-receipt { background: #eef8f4; color: #678a7a; border-radius: 12px; padding: 14px; margin: 12px 0; }
.assignment-receipt strong, .assignment-receipt p { font-size: 12px; }
.assignment-receipt small { display: block; font-size: 11px; line-height: 1.8; margin-bottom: 9px; }
.linked-assignments { margin-top: 18px; border-top: 1px solid #dee7f3; padding-top: 12px; }
.linked-assignment { border: 1px solid #e0e8f3; border-radius: 11px; padding: 13px; background: #fff; margin: 10px 0; }
.linked-assignment header strong { color: #4f6e96; font-size: 12px; overflow-wrap: anywhere; }
.linked-assignment header > span { font-size: 10px; background: #edf3fc; color: #7c95b8; border-radius: 5px; padding: 3px 7px; }
.assignment-progress { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; font-size: 11px; color: #7b91af; margin: 12px 0; }
.assignment-actions { margin-top: 10px; border-top: 1px solid #edf2f8; padding-top: 10px; }
.assignment-actions span { font-size: 10px; color: #9cabc0; }
.workflow-error { color: #aa7955 !important; background: #fff2e7; border-radius: 9px; padding: 10px; font-size: 11px; line-height: 1.8; }
.workflow-wait { display: flex; align-items: center; gap: 8px; font-size: 11px; color: #8198b8; }
.workflow-wait span { width: 10px; height: 10px; border: 2px solid #d7e4f5; border-top-color: #7c9dcc; border-radius: 50%; animation: workflow-spin 1s linear infinite; }
button:focus-visible, input:focus-visible, textarea:focus-visible, summary:focus-visible { outline: 3px solid #acc7ec; outline-offset: 2px; }
@keyframes workflow-spin { to { transform: rotate(360deg); } }
@media(prefers-reduced-motion:reduce) { .workflow-wait span { animation: none; } }
@media(max-width:560px) { .preview-fields { grid-template-columns: 1fr; gap: 0; } .workflow-path { gap: 5px; } .workflow-metrics { gap: 6px; } .workflow-metrics article { padding: 9px; } .teaching-workflow { padding: 12px; } }
</style>
