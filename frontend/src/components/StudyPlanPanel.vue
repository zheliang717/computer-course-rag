<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
import type { StudyPlan, StudyPlanItem, StudyPlanPreferences } from '../studyPlans'

const props = defineProps<{ plan: StudyPlan | null; courseId: string; busy: boolean; request: (path: string, options?: RequestInit) => Promise<unknown> }>()
const emit = defineEmits<{ create: [preferences: StudyPlanPreferences]; refresh: [preferences: StudyPlanPreferences]; open: [planId: string, itemId: string]; reload: [plan: StudyPlan] }>()
type PlanSummary = { id: string; revision: number; created_at: string; task_count: number; preferences: Partial<StudyPlanPreferences> }
const emptyHistory: PlanSummary[] = []
const focus = ref<StudyPlanPreferences['focus']>('balanced')
const minutes = ref<StudyPlanPreferences['daily_minutes']>(20)
const historyOpen = ref(false)
const historyPlan = ref<StudyPlan | null>(null)
const reading = ref(false)
const error = ref('')
const localNotice = ref('')
const controller = new AbortController()
let sequence = 0
let live = true
const displayed = computed(() => historyPlan.value || props.plan)
const pending = computed(() => displayed.value?.items.filter(item => item.completed !== true) || [])
const completed = computed(() => displayed.value?.items.filter(item => item.completed === true) || [])
const chosenPreferences = (): StudyPlanPreferences => ({ focus: focus.value, daily_minutes: minutes.value })
const typeLabel = (item: StudyPlanItem) => ({ assignment: '作业', wrong_review: '错题', section_preview: '预习', course_review: '回顾', wrong_question: '错题再练', practice_question: '独立练习' })[item.kind]
const time = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '旧版记录'
const loadHistory = (page: number, size: number) => props.request(`/api/v1/study-plans/history?course_id=${props.courseId}&page=${page}&page_size=${size}`, { signal: controller.signal }) as Promise<{ items: PlanSummary[]; total: number; page: number; page_size: number }>

async function readPlan(id: string, historical: boolean) {
  if (reading.value || props.busy) return
  const current = ++sequence
  reading.value = true
  error.value = ''
  try {
    const value = await props.request(`/api/v1/study-plans/${id}`, { signal: controller.signal }) as StudyPlan
    if (!live || current !== sequence) return
    if (historical && value.id !== props.plan?.id) historyPlan.value = value
    else { historyPlan.value = null; emit('reload', value); localNotice.value = '进展已读取，未重新生成安排。' }
  } catch (cause) { if (live && current === sequence) error.value = cause instanceof Error ? cause.message : '安排读取失败，请重试' }
  finally { if (live && current === sequence) reading.value = false }
}
watch([() => props.plan?.id, () => props.courseId], () => {
  historyPlan.value = null
  error.value = ''
  localNotice.value = ''
  focus.value = props.plan?.preferences?.focus || 'balanced'
  minutes.value = props.plan?.preferences?.daily_minutes || 20
}, { immediate: true })
onBeforeUnmount(() => { live = false; sequence += 1; controller.abort() })
</script>

<template>
  <section class="study-plan-panel" aria-label="课程学习安排" :aria-busy="busy || reading">
    <header><div><small>学习助理 · {{ historyPlan ? '历史安排' : '下一步学习' }}</small><h3>{{ displayed ? displayed.course_title : '安排这一门课' }}</h3></div><button v-if="courseId" type="button" class="plan-light-button" :disabled="busy || reading" @click="historyOpen = !historyOpen">{{ historyOpen ? '收起历史' : '历史安排' }}</button></header>
    <p v-if="historyPlan" class="plan-notice">正在查看第 {{ historyPlan.revision }} 版安排；任务状态依据当前活动显示，不是当时完成率快照。<button type="button" @click="historyPlan = null">返回当前安排</button></p>
    <div v-if="!historyPlan" class="plan-preferences"><label>本次侧重<select v-model="focus" :disabled="busy"><option value="balanced">均衡推进</option><option value="assignments">作业优先</option><option value="review">复习巩固</option></select></label><label>建议投入<select v-model.number="minutes" :disabled="busy"><option :value="10">10 分钟</option><option :value="20">20 分钟</option><option :value="40">40 分钟</option><option :value="60">60 分钟</option></select></label></div>
    <div v-if="!historyPlan" class="plan-controls"><button type="button" :disabled="busy || reading || !courseId" @click="plan ? emit('refresh', chosenPreferences()) : emit('create', chosenPreferences())">{{ busy ? '正在整理安排…' : plan ? '更新学习安排' : '创建学习安排' }}</button><button v-if="plan" type="button" class="plan-light-button" :disabled="busy || reading" @click="readPlan(plan.id, false)">刷新进展</button></div>
    <p v-if="busy || reading" role="status" class="plan-wait"><span />{{ busy ? '正在结合课程记录整理任务…' : '正在恢复学习记录…' }}</p>
    <p v-if="error" role="alert" class="plan-error">{{ error }}</p><p v-if="localNotice" class="plan-muted" role="status">{{ localNotice }}</p>
    <template v-if="displayed">
      <div class="plan-progress"><strong>已完成 {{ displayed.completed_count }} 项<span v-if="displayed.actionable_count"> / {{ displayed.actionable_count }} 项任务</span></strong><small>第 {{ displayed.revision }} 版 · {{ time(displayed.created_at) }}</small></div>
      <p class="plan-feedback">{{ displayed.feedback }}</p>
      <p v-if="!historyPlan && displayed.needs_refresh" class="plan-notice">{{ displayed.legacy_plan ? '这是一份旧版安排，可更新为具体作业与逐题练习。' : '课程或学习记录有新变化，可更新下一步安排。' }}</p>
      <p v-if="displayed.refresh_notice" class="plan-muted">{{ displayed.refresh_notice }}</p>
      <div class="plan-tasks"><button v-for="item in pending" :key="item.id" type="button" :class="['plan-task', { next: item.id === displayed.next_item_id }]" :disabled="busy || reading || !item.available" @click="emit('open', displayed.id, item.id)"><div class="plan-task-top"><span>{{ typeLabel(item) }}</span><b v-if="item.id === displayed.next_item_id">建议先做</b><small v-if="item.estimated_minutes">约 {{ item.estimated_minutes }} 分钟</small></div><strong>{{ item.title }}</strong><p v-if="item.detail !== item.status_message">{{ item.detail }}</p><footer><small>{{ item.status_message }}</small><b>{{ item.available ? `${item.action_label} ›` : '暂不可用' }}</b></footer></button></div>
      <details v-if="completed.length" class="plan-completed"><summary>已完成的目标 · {{ completed.length }} 项</summary><button v-for="item in completed" :key="item.id" type="button" class="plan-task" :disabled="busy || reading || !item.available" @click="emit('open', displayed.id, item.id)"><strong>✓ {{ item.title }}</strong><footer><small>{{ item.status_message }}</small><b>{{ item.action_label }} ›</b></footer></button></details>
      <p class="plan-muted">{{ displayed.source_label }}。预计时长仅供安排，任务可分次完成。</p>
    </template>
    <p v-else-if="!busy" class="plan-muted">选择学习侧重后，整理可以直接打开的作业、独立练习与章节建议。</p>
    <section v-if="historyOpen && courseId" class="plan-history"><h4>过去的安排</h4><PagedList :items="emptyHistory" :load-page="loadHistory" :scope="`${courseId}:${plan?.id || ''}`" :page-size="5" label="学习安排历史" v-slot="{ items, total }"><button v-for="item in items" :key="item.id" type="button" class="plan-history-row" :disabled="busy || reading" @click="readPlan(item.id, true)"><div><strong>第 {{ item.revision }} 版 · {{ item.task_count }} 项</strong><small>{{ time(item.created_at) }}</small></div><span>{{ item.id === plan?.id ? '当前' : '查看' }} ›</span></button><p v-if="!total" class="plan-muted">还没有保存的安排。</p></PagedList></section>
  </section>
</template>

<style scoped>
.study-plan-panel { background: #f6f9fe; border: 1px solid #dce6f3; border-radius: 16px; padding: 17px; min-width: 0; }
header, .plan-controls, .plan-progress, .plan-task-top, .plan-task footer, .plan-history-row { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; }
header, .plan-task footer, .plan-history-row { justify-content: space-between; }
header small { color: #7791b3; font-size: 11px; }
h3 { color: #34537c; font-size: 16px; line-height: 1.6; margin: 5px 0 10px; }
h4 { font-size: 13px; color: #5b7599; }
button { font-size: 12px; line-height: 1.65; }
.plan-light-button { background: #e9f0fa; color: #6682a8; padding: 8px 10px; }
.plan-preferences { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin: 10px 0 13px; }
label { color: #7489a6; display: grid; gap: 7px; font-size: 11px; }
select { width: 100%; min-width: 0; border: 1px solid #d4e0ef; background-color: #fff; border-radius: 9px; padding: 10px; font: inherit; color: #4f6d94; }
.plan-controls { margin-bottom: 14px; }
.plan-progress { align-items: start; justify-content: space-between; margin: 15px 0 0; }
.plan-progress strong { font-size: 13px; color: #3d628f; }
.plan-progress strong span { color: #8c9eb6; font-size: 11px; font-weight: 400; }
.plan-progress > small { font-size: 10px; color: #97a5b9; }
.plan-feedback { color: #57769c; font-size: 12px; line-height: 1.8; margin: 12px 0; }
.plan-tasks { display: grid; gap: 10px; }
.plan-task { width: 100%; min-width: 0; text-align: left; color: #49668d; background: #fff; border: 1px solid #e0e8f4; padding: 13px; border-radius: 12px; }
.plan-task.next { border-color: #a8c4e9; box-shadow: inset 3px 0 #7fa6db; }
.plan-task:disabled { opacity: .6; }
.plan-task-top { font-size: 10px; margin-bottom: 8px; }
.plan-task-top > span { color: #6c88af; background: #edf3fc; border-radius: 5px; padding: 2px 6px; }
.plan-task-top b { color: #6592ca; font-weight: 500; }
.plan-task-top small { margin-left: auto; color: #9baabe; }
.plan-task > strong { display: block; font-size: 12px; color: #3e5f8b; overflow-wrap: anywhere; }
.plan-task > p { font-size: 11px; color: #8a9bb1; margin: 7px 0; line-height: 1.8; overflow-wrap: anywhere; }
.plan-task footer { margin-top: 10px; border-top: 1px solid #eff3f8; padding-top: 8px; }
.plan-task footer small { color: #93a1b5; font-size: 10px; flex: 1; min-width: 0; }
.plan-task footer b { font-size: 10px; color: #6a8ab4; font-weight: 500; }
.plan-completed { border-top: 1px solid #dfe8f4; padding-top: 12px; margin-top: 16px; }
summary { color: #758fab; font-size: 11px; cursor: pointer; padding: 5px 0; }
.plan-completed .plan-task { margin-top: 10px; background: #fafffd; }
.plan-muted { font-size: 10px; line-height: 1.9; color: #9aa9bd; }
.plan-notice, .plan-error { padding: 10px 12px; border-radius: 10px; font-size: 11px; line-height: 1.8; }
.plan-notice { color: #6e86a8; background: #e9f0fb; }
.plan-notice button { color: #4b73a6; background: transparent; padding: 3px 0; display: block; font-size: 11px; }
.plan-error { color: #aa7652; background: #fff1e6; }
.plan-history { margin-top: 18px; border-top: 1px solid #dce6f2; }
.plan-history-row { width: 100%; padding: 10px 0; border-bottom: 1px solid #e6edf6; background: transparent; color: #6e87a7; text-align: left; }
.plan-history-row strong { display: block; font-size: 11px; }
.plan-history-row small { display: block; font-size: 10px; color: #9eabbd; margin-top: 4px; }
.plan-history-row > span { font-size: 10px; }
.plan-wait { display: flex; align-items: center; gap: 8px; font-size: 11px; color: #7d95b5; }
.plan-wait > span { width: 10px; height: 10px; border: 2px solid #d7e4f5; border-top-color: #7a9cc9; border-radius: 50%; animation: spin 1s linear infinite; }
button:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid #9cbee8; outline-offset: 2px; }
@keyframes spin { to { transform: rotate(360deg); } }
@media(prefers-reduced-motion:reduce) { .plan-wait > span { animation: none; } }
@media(max-width:430px) { .plan-preferences { grid-template-columns: 1fr; } .study-plan-panel { padding: 13px; } }
</style>
