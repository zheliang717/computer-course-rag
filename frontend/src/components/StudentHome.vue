<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
import TodaySchedule from './TodaySchedule.vue'
import type { CourseRecord } from '../courseCatalog'
import type { StudyPlan } from '../studyPlans'

type Assignment = { id: string; course_title: string; title: string; status: string; submitted: boolean; due_at: string | null; late_request_status: string | null; late_approved_until: string | null; question_count: number; submission_status: string | null }
type Session = { id: string; course_id: string; title: string; session_date: string; duration_minutes: number; location: string | null; completed: boolean }
type Progress = { course_id: string; course_title: string; progress_percent: number; completed_sessions: number; session_count: number; completed_assignments: number; assignment_count: number }
const props = defineProps<{ assignments: Assignment[]; sessions: Session[]; courses: CourseRecord[]; reports: Progress[]; plans: StudyPlan[]; now: number; busy: boolean; error: string; opening: string }>()
const emit = defineEmits<{ assignment: [id: string]; course: [course: CourseRecord]; assistant: []; assignments: []; courses: []; plan: [courseId: string]; retry: []; schedule: []; session: [id: string] }>()
const taskView = ref<'ready' | 'late' | 'submitted'>('ready')
const progressPanel = ref<HTMLElement | null>(null)
const published = computed(() => props.assignments.filter(item => item.status === 'published'))
const overdue = (item: Assignment) => !!item.due_at && Date.parse(item.due_at) < props.now
const ready = (item: Assignment) => !item.submitted && (!overdue(item) || (item.late_request_status === 'approved' && (!item.late_approved_until || Date.parse(item.late_approved_until) > props.now)))
const deadline = (item: Assignment) => overdue(item) && item.late_request_status === 'approved' && item.late_approved_until ? item.late_approved_until : item.due_at
const groups = computed(() => ({
  ready: published.value.filter(ready).sort((a, b) => (deadline(a) ? Date.parse(deadline(a)!) : Infinity) - (deadline(b) ? Date.parse(deadline(b)!) : Infinity)),
  late: published.value.filter(item => !item.submitted && !ready(item)).sort((a, b) => Date.parse(b.due_at || '') - Date.parse(a.due_at || '')),
  submitted: published.value.filter(item => item.submitted),
}))
const taskTabs = [{ value: 'ready', label: '可提交' }, { value: 'late', label: '补交事项' }, { value: 'submitted', label: '已提交' }] as const
let initialTaskChosen = false
watch([() => props.busy, groups], () => {
  if (props.busy || props.error || initialTaskChosen || !published.value.length) return
  taskView.value = groups.value.ready.length ? 'ready' : groups.value.late.length ? 'late' : 'submitted'
  initialTaskChosen = true
}, { immediate: true })
const formatDate = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : '未设截止时间'
function hint(item: Assignment) {
  if (item.submitted) return item.submission_status === 'graded' ? '已批改 · 查看反馈' : '已提交 · 等待批改'
  if (ready(item)) return overdue(item) ? `获批补交 · ${item.late_approved_until ? formatDate(item.late_approved_until) + ' 前' : '可提交'}` : item.due_at ? `${formatDate(item.due_at)} 截止` : '未设截止时间'
  return item.late_request_status === 'pending' ? '补交申请待审批' : item.late_request_status === 'rejected' ? '补交申请未通过 · 查看详情' : '已截止 · 查看补交安排'
}
function showProgress() {
  progressPanel.value?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  progressPanel.value?.focus({ preventScroll: true })
}
defineExpose({ showProgress })
</script>

<template>
  <div class="student-home-content" :aria-busy="busy">
    <p v-if="busy" class="home-load-state" role="status"><span class="pagination-spinner" /> 正在更新学习安排…</p>
    <p v-if="error" class="home-load-error" role="alert">{{ error }} <button type="button" :disabled="busy" @click="emit('retry')">重新读取</button></p>
    <div class="student-home-primary">
      <section class="home-card home-assignments" aria-label="我的作业待办">
        <header><div><small>WHAT'S NEXT</small><h2>先完成这些</h2></div><button type="button" class="text-button" @click="emit('assignments')">全部作业 ›</button></header>
        <div class="home-view-switch" role="group" aria-label="首页作业分类"><button v-for="tab in taskTabs" :key="tab.value" type="button" :aria-pressed="taskView === tab.value" @click="taskView = tab.value">{{ tab.label }} <b>{{ groups[tab.value].length }}</b></button></div>
        <PagedList :items="groups[taskView]" :scope="taskView" :page-size="4" label="首页作业" v-slot="{ items }">
          <button v-for="item in items" :key="item.id" type="button" class="home-assignment-row" :disabled="!!opening || busy" @click="emit('assignment', item.id)"><span class="home-task-mark" :class="taskView" aria-hidden="true">{{ taskView === 'submitted' ? '✓' : taskView === 'late' ? '!' : '↗' }}</span><span class="home-row-content"><small>{{ item.course_title }} · {{ item.question_count }} 道题</small><strong>{{ item.title }}</strong><span :class="{ 'late-hint': taskView === 'late' }">{{ opening === item.id ? '正在打开作业…' : hint(item) }}</span></span><span class="home-row-arrow" aria-hidden="true">›</span></button>
          <div v-if="!busy && !error && !items.length" class="home-empty"><strong>{{ taskView === 'ready' ? '当前没有可直接提交的作业' : taskView === 'late' ? '暂无需要处理的补交事项' : '还没有已提交的作业' }}</strong><p>{{ taskView === 'ready' && groups.late.length ? '还有已截止作业，可在“补交事项”查看申请与审批。' : '也可以查看课程资料，或向 AI 助手提问。' }}</p></div>
        </PagedList>
      </section>
      <TodaySchedule :sessions="sessions" :courses="courses" :now="now" :busy="busy" :error="error" @schedule="emit('schedule')" @session="emit('session',$event)" />
    </div>
    <section ref="progressPanel" tabindex="-1" class="home-card home-course-progress" aria-label="分课程学习进度">
      <header><div><small>COURSE PROGRESS</small><h2>分课程学习进度</h2></div><button type="button" class="text-button" @click="emit('courses')">全部课程 ›</button></header>
      <PagedList :items="reports" :page-size="6" label="首页课程进度" v-slot="{ items }"><div class="home-progress-grid"><button v-for="report in items" :key="report.course_id" type="button" @click="courses.find(item => item.id === report.course_id) && emit('course', courses.find(item => item.id === report.course_id)!)"><span><strong>{{ report.course_title }}</strong><b>{{ report.progress_percent }}%</b></span><i aria-hidden="true"><em :style="{ width: `${report.progress_percent}%` }" /></i><small>已授课 {{ report.completed_sessions }}/{{ report.session_count }} 次 <span>作业 {{ report.completed_assignments }}/{{ report.assignment_count }}</span></small></button></div><p v-if="!busy && !error && !items.length" class="home-empty">暂无课程进度记录。</p></PagedList>
    </section>
    <div class="student-home-secondary">
      <section class="home-card home-plans"><header><div><small>MY STUDY PLANS</small><h2>学习计划</h2></div></header><PagedList v-if="plans.length" :items="plans" :page-size="3" label="首页学习计划" v-slot="{ items }"><button v-for="plan in items" :key="plan.id" type="button" class="home-plan-row" @click="emit('plan', plan.course_id)"><span><strong>{{ plan.course_title }}</strong><small>{{ plan.items.find(item => !item.completed)?.title || '打开查看学习安排' }}</small></span><b>{{ plan.actionable_count ? `${plan.completed_count}/${plan.actionable_count}` : `${plan.items.length} 项建议` }} ›</b></button></PagedList><div v-else-if="!busy && !error" class="home-empty"><p>还没有学习计划，可在助手中选择课程后创建。</p><button type="button" class="text-button" @click="emit('assistant')">打开助手 ›</button></div></section>
      <section class="home-ai-entry"><span aria-hidden="true">✦</span><h2>遇到问题，随时问 AI</h2><p>带着课程资料讲解知识，陪你梳理思路。</p><button type="button" @click="emit('assistant')">开始提问 ↗</button></section>
    </div>
  </div>
</template>

<style scoped>
.student-home-content { display: grid; gap: 20px; }.student-home-primary { align-items: start; display: grid; gap: 20px; grid-template-columns: minmax(0, 1.35fr) minmax(0, 1fr); }.home-card { background: white; border: 1px solid #e1e8f2; border-radius: 18px; min-width: 0; padding: 22px; }.home-card header { align-items: center; display: flex; gap: 12px; justify-content: space-between; margin-bottom: 16px; }.home-card header small { color: #6684a7; font-size: 10px; font-weight: 750; letter-spacing: .1em; }.home-card h2, .home-ai-entry h2 { color: #203857; font-size: 19px; margin: 5px 0 0; }.home-card .text-button { flex: none; font-size: 12px; padding: 6px 0; }.home-view-switch { background: #f2f5fa; border-radius: 11px; display: flex; gap: 4px; margin-bottom: 9px; padding: 4px; }.home-view-switch button { background: transparent; color: #677c96; flex: 1; font-size: 12px; padding: 9px 5px; }.home-view-switch button[aria-pressed=true] { background: white; box-shadow: 0 2px 6px #152b4910; color: #265f9f; }.home-view-switch b { font-size: 11px; margin-left: 5px; }.home-assignment-row { align-items: center; background: transparent; border-bottom: 1px solid #edf1f7; border-radius: 0; color: #243d5c; display: flex; gap: 12px; padding: 17px 2px; text-align: left; width: 100%; }.home-assignment-row:hover, .home-schedule-row:hover, .home-plan-row:hover { background: #f7faff; }.home-task-mark { align-items: center; background: #edf4ff; border-radius: 10px; color: #3471bd; display: flex; flex: none; font-size: 16px; height: 36px; justify-content: center; width: 36px; }.home-task-mark.late { background: #fff4e6; color: #ae762c; }.home-task-mark.submitted { background: #eaf7f0; color: #397a5e; }.home-row-content { display: grid; flex: 1; gap: 6px; min-width: 0; }.home-row-content small { color: #788ba3; font-size: 11px; font-weight: 400; }.home-row-content strong { font-size: 13px; line-height: 1.65; overflow-wrap: anywhere; }.home-row-content > span { color: #54779e; font-size: 11px; font-weight: 400; }.home-row-content .late-hint { color: #a27640; }.home-row-arrow { color: #8196af; font-size: 20px; }.home-schedule-row { background: transparent; border-bottom: 1px solid #edf1f7; border-radius: 0; color: #2b4260; display: grid; gap: 6px; line-height: 1.7; padding: 15px 2px; text-align: left; width: 100%; }.home-schedule-row strong { font-size: 13px; }.home-schedule-row span { color: #617994; font-size: 12px; font-weight: 400; }.home-schedule-row .schedule-date { color: #396ca6; font-size: 11px; font-weight: 700; }.home-schedule-row small { color: #8292a7; font-size: 11px; font-weight: 400; }.home-empty { color: #7589a1; font-size: 12px; line-height: 1.9; padding: 24px 3px; }.home-empty strong { color: #556e8d; }.home-empty p { margin: 6px 0; }.home-progress-grid { display: grid; gap: 12px; grid-template-columns: repeat(2, minmax(0, 1fr)); }.home-progress-grid > button { background: #f8fafd; border: 1px solid #e5ebf4; color: #304764; display: grid; gap: 12px; min-width: 0; padding: 17px; text-align: left; }.home-progress-grid > button:hover { border-color: #a8c7ef; }.home-progress-grid button > span { align-items: baseline; display: flex; gap: 10px; justify-content: space-between; }.home-progress-grid strong { font-size: 13px; overflow-wrap: anywhere; }.home-progress-grid b { color: #326aab; flex: none; font-size: 15px; }.home-progress-grid i { background: #e3eaf4; border-radius: 8px; height: 6px; overflow: hidden; }.home-progress-grid em { background: linear-gradient(90deg,#4e81d1,#78a5e9); border-radius: inherit; display: block; height: 100%; }.home-progress-grid small { color: #7c8da4; display: flex; flex-wrap: wrap; font-size: 11px; font-weight: 400; gap: 9px; justify-content: space-between; }.home-course-progress { scroll-margin-top: 110px; }.student-home-secondary { display: grid; gap: 20px; grid-template-columns: minmax(0,1.35fr) minmax(0,1fr); }.home-plan-row { align-items: center; background: transparent; border-bottom: 1px solid #edf1f7; border-radius: 0; color: #2b4260; display: flex; gap: 14px; padding: 14px 0; text-align: left; width: 100%; }.home-plan-row span { display: grid; flex: 1; gap: 5px; min-width: 0; }.home-plan-row strong { font-size: 13px; }.home-plan-row small { color: #7b8fa9; font-size: 11px; font-weight: 400; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }.home-plan-row b { color: #527bb1; flex: none; font-size: 12px; }.home-ai-entry { align-self: start; background: linear-gradient(135deg,#eaf3ff,#f1f1ff); border: 1px solid #d8e6f8; border-radius: 18px; padding: 26px; }.home-ai-entry > span { color: #4a75b7; font-size: 23px; }.home-ai-entry p { color: #6b82a1; font-size: 12px; line-height: 1.9; }.home-ai-entry button { background: #316cba; font-size: 13px; margin-top: 10px; padding: 11px 18px; }.home-load-state, .home-load-error { align-items: center; color: #657e9e; display: flex; flex-wrap: wrap; font-size: 12px; gap: 10px; margin: 0; }.home-load-error { background: #fff2ed; border-radius: 10px; color: #a26451; padding: 12px; }.home-load-error button { font-size: 12px; padding: 7px 10px; }:is(button):focus-visible { outline: 3px solid #a7c8f1; outline-offset: 3px; }.home-card :deep(.list-pager) { font-size: 10px; gap: 6px; padding: 14px 0 0; }.home-card :deep(.list-pager button), .home-card :deep(.list-pager select) { font-size: 11px; padding: 7px 8px; }
@media(max-width:1100px) { .student-home-primary, .student-home-secondary { grid-template-columns: 1fr; }.home-card { padding: 19px; } }
@media(max-width:600px) { .home-progress-grid { grid-template-columns: 1fr; }.home-card { padding: 16px; }.home-card h2 { font-size: 17px; }.home-task-mark { display: none; }.home-view-switch button { font-size: 11px; }.home-view-switch b { margin-left: 2px; }.home-row-content strong { font-size: 13px; } }
</style>
