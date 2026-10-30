<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import type { PracticeFeedback, PracticeQuestion } from '../practiceFeedback'

const props = defineProps<{
  questionId: string; attemptId?: string | null; enabled: boolean; assistantBusy?: boolean
  request: (path: string, options?: RequestInit) => Promise<unknown>
  renderMarkdown: (content: string) => string
}>()
const emit = defineEmits<{
  practice: [question: PracticeQuestion]; explain: [courseId: string, topic: string]
  busy: [value: boolean]; plan: [courseId: string]
}>()
const result = ref<PracticeFeedback | null>(null)
const loading = ref(false)
const generating = ref(false)
const error = ref('')
const elapsed = ref(0)
const pending = computed(() => generating.value || result.value?.state === 'processing')
let sequence = 0
let controller: AbortController | null = null
let pollTimer: ReturnType<typeof setTimeout> | undefined
let elapsedTimer: ReturnType<typeof setInterval> | undefined
let polls = 0

watch(pending, (value) => {
  emit('busy', value)
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsed.value = 0
  if (value) elapsedTimer = setInterval(() => elapsed.value += 1, 1000)
})

async function readReview(generate = false, polling = false) {
  if (generate && (pending.value || loading.value || !result.value)) return
  const id = ++sequence
  controller?.abort()
  controller = new AbortController()
  const signal = controller.signal
  if (pollTimer) clearTimeout(pollTimer)
  if (!polling) error.value = ''
  generating.value = generate
  loading.value = !generate && !polling
  const attemptId = generate ? result.value!.attempt_id : props.attemptId
  const path = attemptId ? `/api/v1/practice/attempts/${attemptId}/feedback` : `/api/v1/practice/questions/${props.questionId}/feedback`
  try {
    const value = await props.request(path, { method: generate ? 'POST' : 'GET', signal }) as PracticeFeedback | null
    if (id !== sequence) return
    result.value = value
    if (value?.state === 'processing' && polls++ < 110) {
      pollTimer = setTimeout(() => void readReview(false, true), 3000)
    }
  } catch (cause) {
    if (id !== sequence || signal.aborted) return
    error.value = cause instanceof Error ? cause.message : '暂时无法读取复盘，请重试。'
    // A concurrent tab may already be generating; offer a read instead of a second request.
    if (generate && result.value?.state !== 'processing') result.value = result.value ? { ...result.value, state: 'failed' } : null
  } finally {
    if (id === sequence) { loading.value = false; generating.value = false }
  }
}

watch(() => [props.questionId, props.attemptId], () => {
  result.value = null
  polls = 0
  void readReview()
}, { immediate: true })

onBeforeUnmount(() => {
  sequence += 1
  controller?.abort()
  if (pollTimer) clearTimeout(pollTimer)
  if (elapsedTimer) clearInterval(elapsedTimer)
  emit('busy', false)
})
</script>

<template>
  <section class="practice-coach" aria-label="AI 练习复盘" :aria-busy="loading || pending">
    <header><div><small>AI 学习助理</small><h3>做完一道题，再向前一步</h3></div><span>练习复盘</span></header>
    <p v-if="loading" class="coach-muted" role="status">正在恢复你的练习记录…</p>
    <p v-if="error" class="coach-error" role="alert">{{ error }}</p>
    <div v-if="pending" class="coach-wait" role="status"><span class="coach-orbit" aria-hidden="true"><i /><i /><i /></span><div><strong>正在理解你的作答，整理讲解…</strong><small>已等待 {{ elapsed }} 秒 · 可以关闭窗口，稍后回来查看</small></div></div>
    <template v-if="result">
      <div class="coach-meta"><span>{{ result.course_title }} · {{ result.knowledge_point }}</span><span>{{ result.is_correct === null ? '主观题 · 未自动判分' : result.is_correct ? '本次回答正确' : '本次需要巩固' }}</span></div>
      <details class="submitted-work"><summary>查看本次提交的回答 · {{ new Date(result.attempted_at).toLocaleString('zh-CN') }}</summary><p>{{ result.submitted_answer }}</p><small>截至本次：本题练习 {{ result.question_attempt_count }} 次，平台判对 {{ result.question_correct_count }} 次</small></details>
      <p v-if="result.stale" class="coach-error">题目或课程内容已更新，这份复盘基于旧记录，建议更新后阅读。</p>
      <template v-if="result.analysis">
        <div class="coach-summary answer-markdown" v-html="renderMarkdown(result.analysis.summary)" />
        <div class="coach-observations"><section v-if="result.analysis.strengths.length"><h4>可取之处</h4><div v-for="item in result.analysis.strengths" :key="item" class="answer-markdown" v-html="renderMarkdown(item)" /></section><section v-if="result.analysis.misconceptions.length"><h4>再检查一下</h4><div v-for="item in result.analysis.misconceptions" :key="item" class="answer-markdown" v-html="renderMarkdown(item)" /></section></div>
        <section class="coach-explanation"><h4>一步步弄懂</h4><div class="answer-markdown" v-html="renderMarkdown(result.analysis.explanation)" /></section>
        <section class="coach-next"><h4>接下来怎么学</h4><ol><li v-for="item in result.analysis.next_steps" :key="item"><div class="answer-markdown" v-html="renderMarkdown(item)" /></li></ol></section>
        <details class="coach-check"><summary>用一个小问题检查理解</summary><div class="answer-markdown" v-html="renderMarkdown(result.analysis.self_check)" /></details>
      </template>
      <div class="coach-actions">
        <button v-if="!result.analysis || result.stale" type="button" :disabled="pending || loading || !enabled" @click="readReview(true)">{{ pending ? '正在复盘…' : result.stale ? '更新 AI 复盘' : error || result.state === 'failed' ? '重试 AI 复盘' : 'AI 帮我复盘这次作答' }}</button>
        <button v-if="result.next_question" type="button" class="ghost-button" :disabled="pending" @click="emit('practice', result.next_question)">继续练习：{{ result.next_question.knowledge_point || '课程知识' }} ↗</button>
        <button type="button" class="ghost-button" :disabled="pending || assistantBusy || !enabled" @click="emit('explain', result.course_id, result.knowledge_point)">{{ assistantBusy ? '助手正在回答，请稍候' : '追问这个知识点 ↗' }}</button>
        <button type="button" class="ghost-button" :disabled="pending" @click="emit('plan', result.course_id)">查看学习计划 ↗</button>
      </div>
      <p class="coach-muted">{{ result.source_label }}。AI 提供学习建议，不改变成绩或掌握状态。</p>
      <p v-if="!result.analysis && enabled && !pending" class="coach-muted">点击复盘会把本题、参考解析和这次作答交给 AI 模型，不会发送其他学生记录。</p>
    </template>
    <p v-else-if="!loading && !error" class="coach-muted">先独立作答并提交，再让 AI 针对你的回答做复盘。</p>
    <p v-if="!enabled" class="coach-muted">在线 AI 暂未就绪，可以继续独立练习、查看已有复盘与原解析。</p>
    <button v-if="error || result?.state === 'processing'" type="button" class="ghost-button coach-refresh" :disabled="loading || generating" @click="polls = 0; readReview()">重新读取结果</button>
  </section>
</template>

<style scoped>
.practice-coach { background: linear-gradient(140deg, #f0f7ff, #f8fafc 65%); border: 1px solid #d8e6f6; border-radius: 18px; padding: 22px; margin-top: 18px; color: #34485f; }
header, .coach-meta, .coach-actions, .coach-wait { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
header { justify-content: space-between; }
header small { color: #5579b4; font-size: 11px; letter-spacing: .04em; }
h3 { margin: 7px 0 10px; font-size: 18px; }
header > span { padding: 6px 11px; background: #e4eefc; border-radius: 20px; font-size: 11px; color: #5574a3; }
h4 { font-size: 13px; color: #3d5981; margin: 0 0 10px; }
.coach-meta { justify-content: space-between; font-size: 11px; color: #6a7f9c; padding: 8px 0 12px; }
.submitted-work, .coach-check { padding: 12px; background: #fff; border: 1px solid #e1e9f3; border-radius: 10px; font-size: 12px; }
summary { cursor: pointer; line-height: 1.7; color: #476589; }
.submitted-work p { white-space: pre-wrap; overflow-wrap: anywhere; max-height: 180px; overflow-y: auto; }
.submitted-work small { color: #7c8fa9; }
.coach-summary { margin: 16px 0; font-weight: 500; }
.coach-observations { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 210px), 1fr)); gap: 12px; }
.coach-observations > section, .coach-explanation, .coach-next { padding: 16px; border: 1px solid #e1e9f3; border-radius: 12px; background: #fff; min-width: 0; }
.coach-explanation, .coach-next, .coach-check { margin-top: 12px; }
.coach-next ol { padding-left: 20px; margin-bottom: 0; }
.coach-actions { margin-top: 18px; }
.coach-actions button { font-size: 12px; line-height: 1.6; padding: 9px 13px; }
.coach-muted { font-size: 11px; color: #7c8da5; line-height: 1.8; margin-bottom: 0; }
.coach-error { background: #fff2e7; color: #9a5a2a; font-size: 12px; line-height: 1.8; padding: 10px 12px; border-radius: 10px; }
.coach-wait { background: #e8f0fc; padding: 16px; border-radius: 12px; margin: 12px 0; }
.coach-wait strong, .coach-wait small { display: block; font-size: 12px; line-height: 1.8; color: #4c6c99; }
.coach-wait small { font-size: 11px; }
.coach-orbit { display: flex; gap: 4px; }
.coach-orbit i { width: 6px; height: 6px; border-radius: 50%; background: #6c91c8; animation: pulse 1.3s ease-in-out infinite; }
.coach-orbit i:nth-child(2) { animation-delay: .15s; }
.coach-orbit i:nth-child(3) { animation-delay: .3s; }
.coach-refresh { margin-top: 12px; font-size: 11px; }
button:focus-visible, summary:focus-visible { outline: 3px solid #82abe2; outline-offset: 3px; }
@keyframes pulse { 50% { opacity: .25; transform: translateY(-4px); } }
@media (prefers-reduced-motion: reduce) { .coach-orbit i { animation: none; } }
@media (max-width: 600px) { .practice-coach { padding: 14px; } .coach-actions { flex-direction: column; align-items: stretch; } h3 { font-size: 16px; } }
</style>
