<script setup lang="ts">
import { computed, defineAsyncComponent, nextTick, ref, watch } from 'vue'
import PagedList from './PagedList.vue'

type Submission = { id: string; student_name: string; answers: Record<string, string>; score: number; max_score: number; status: string; submitted_at: string | null }
type Question = { id: string; question_type: string; stem: string; options: string[]; correct_answer: string | null; explanation: string | null }
const props = defineProps<{ submissions: Submission[]; selected: Submission | null; questions: Question[]; loading: boolean; error: string; busy: boolean }>()
const emit = defineEmits<{ select: [id: string]; retry: [] }>()
const RichText = defineAsyncComponent(() => import('./RichText.vue'))
const keyword = ref('')
const status = ref('all')
const questionIndex = ref(0)
const view = ref<'answers' | 'analysis'>('answers')
const mobileRoster = ref(false)
const reviewPane = ref<HTMLElement | null>(null)
const scorePane = ref<HTMLElement | null>(null)
const filtered = computed(() => props.submissions.filter(item => (!keyword.value.trim() || item.student_name.toLocaleLowerCase().includes(keyword.value.trim().toLocaleLowerCase())) && (status.value === 'all' || (item.status === 'graded' ? 'graded' : 'pending') === status.value)))
const question = computed(() => props.questions[questionIndex.value] ?? null)
const selectedIndex = computed(() => filtered.value.findIndex(item => item.id === props.selected?.id))
const pendingCount = computed(() => props.submissions.filter(item => item.status !== 'graded').length)
const labels: Record<string, string> = { single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题', fill_blank: '填空题', short_answer: '简答题' }
watch(() => props.selected?.id, async () => { questionIndex.value = 0; view.value = 'answers'; mobileRoster.value = false; await nextTick(); reviewPane.value?.scrollTo({ top: 0 }); if (window.matchMedia('(max-width: 850px)').matches) reviewPane.value?.scrollIntoView({ block: 'start' }) })
const text = (value: unknown) => Array.isArray(value) ? value.join('；') : value == null || value === '' ? '未作答' : String(value)
const date = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', hour12: false }) : '时间未记录'
function move(step: number) {
  const item = filtered.value[selectedIndex.value + step]
  if (item && !props.busy) emit('select', item.id)
}
</script>

<template>
  <section class="grading-workspace" aria-label="作业批改工作区">
    <div class="grading-mobile-switch"><button type="button" :aria-expanded="mobileRoster" @click="mobileRoster = !mobileRoster">{{ mobileRoster ? '收起学生名单' : '选择学生' }} · {{ selected?.student_name || '尚未选择' }} ⌄</button><button type="button" :disabled="!selected" @click="scorePane?.scrollIntoView({ block: 'start' })">评分评语 ↓</button></div>
    <aside class="grading-roster" :class="{ 'is-mobile-open': mobileRoster }" aria-label="学生提交名单">
      <header><strong>学生提交</strong><span>{{ submissions.length }} 份 · {{ pendingCount }} 待批改</span></header>
      <label>查找学生<input v-model="keyword" type="search" maxlength="100" placeholder="输入学生姓名" :disabled="busy" /></label>
      <label>批改状态<select v-model="status" :disabled="busy"><option value="all">全部提交</option><option value="pending">待批改</option><option value="graded">已批改</option></select></label>
      <p v-if="loading" role="status" class="grading-empty">正在读取学生提交…</p>
      <p v-else-if="error" role="alert" class="grading-load-error">{{ error }} <button type="button" @click="emit('retry')">重试读取</button></p>
      <PagedList v-else :items="filtered" :page-size="8" :scope="`${keyword}:${status}`" label="学生提交" class="grading-roster-list" v-slot="{ items }">
        <button v-for="item in items" :key="item.id" class="grading-student-row" type="button" :class="{ active: selected?.id === item.id }" :aria-pressed="selected?.id === item.id" :disabled="busy" @click="mobileRoster=false; emit('select', item.id)"><span class="grading-student-avatar">{{ item.student_name.slice(0, 1) }}</span><span><strong>{{ item.student_name }}</strong><small>{{ item.status === 'graded' ? '已批改' : '待批改' }}</small></span><b>{{ item.status === 'graded' ? `${item.score}分` : '待评分' }}</b></button>
        <p v-if="!items.length" class="grading-empty">{{ submissions.length ? '没有匹配的学生提交，请调整条件。' : '还没有学生提交。' }}</p>
      </PagedList>
    </aside>
    <section v-if="selected" ref="reviewPane" class="grading-answer-view" aria-label="逐题作答">
      <header class="grading-student-heading"><div><h3>{{ selected.student_name }}</h3><span>{{ date(selected.submitted_at) }} 提交 · {{ selected.status === 'graded' ? '已批改' : '待批改' }}</span></div><div class="grading-student-step"><button type="button" :disabled="busy || selectedIndex <= 0" @click="move(-1)">上一位</button><button type="button" :disabled="busy || selectedIndex < 0 || selectedIndex >= filtered.length - 1" @click="move(1)">下一位</button></div></header>
      <p v-if="selectedIndex < 0 && (keyword.trim() || status !== 'all')" class="grading-filter-note">当前学生不在筛选结果中，已保留正在查看的作答。</p>
      <nav class="grading-view-tabs" aria-label="作答查看方式"><button type="button" :aria-pressed="view === 'answers'" :class="{ active: view === 'answers' }" @click="view = 'answers'">逐题作答</button><button type="button" :aria-pressed="view === 'analysis'" :class="{ active: view === 'analysis' }" @click="view = 'analysis'">✦ AI 作答分析</button></nav>
      <div v-show="view === 'answers'" class="grading-question-view">
        <nav class="grading-question-nav" aria-label="作答题号"><button v-for="(item, index) in questions" :key="item.id" type="button" :class="{ active: index === questionIndex }" :aria-pressed="index === questionIndex" :aria-label="`查看第 ${index + 1} 题`" @click="questionIndex = index">{{ index + 1 }}</button></nav>
        <article v-if="question" :key="`${selected.id}:${question.id}`" class="grading-question-card"><div class="grading-question-kicker"><span>第 {{ questionIndex + 1 }} / {{ questions.length }} 题</span><span>{{ labels[question.question_type] || '题目' }}</span></div><RichText :source="question.stem" :tools="false" /><details v-if="question.options.length" class="grading-options"><summary>查看题目选项</summary><ul class="grading-question-options"><li v-for="option in question.options" :key="option">{{ option }}</li></ul></details><section class="grading-student-answer"><h4>学生作答</h4><RichText :source="text(selected.answers[question.id])" :tools="false" /></section><details class="grading-reference"><summary>查看参考答案与解析</summary><h4>参考答案</h4><RichText :source="question.correct_answer || '未提供参考答案'" :tools="false" /><h4 v-if="question.explanation">知识点解析</h4><RichText v-if="question.explanation" :source="question.explanation" :tools="false" /></details></article>
        <p v-else class="grading-empty">这份作业未记录题目。</p>
      </div>
      <div v-show="view === 'analysis'" class="grading-analysis-view"><slot name="analysis" /></div>
    </section>
    <div v-else class="grading-select-prompt"><strong>{{ loading ? '正在准备批改工作区…' : '选择一位学生开始批改' }}</strong><p>逐题查看作答，核对参考解析，再填写成绩与评语。</p></div>
    <aside v-if="selected" ref="scorePane" class="grading-score-pane" aria-label="成绩与教师评语"><slot name="grade" /></aside>
  </section>
</template>

<style scoped>
.grading-workspace { background: #f5f7fc; display: grid; grid-template-columns: 215px minmax(0, 1fr) 280px; height: 100%; min-height: 0; }
.grading-roster, .grading-answer-view, .grading-score-pane { min-height: 0; min-width: 0; overflow: auto; overscroll-behavior: contain; }
.grading-roster { background: white; border-right: 1px solid #e4e9f2; padding: 16px 12px; }
.grading-roster > header { display: grid; gap: 6px; margin-bottom: 18px; }
.grading-roster header strong { color: #243956; font-size: 16px; }.grading-roster header span { color: #65758c; font-size: 12px; }
.grading-roster label { color: #52637c; display: grid; font-size: 12px; gap: 6px; margin: 11px 0; }
.grading-roster input, .grading-roster select { font-size: 13px; min-width: 0; width: 100%; }
.grading-roster-list { display: grid; gap: 7px; }
.grading-student-row { align-items: center; background: #f8f9fc; border: 1px solid #e6eaf2; border-radius: 10px; color: #29405f; display: grid; gap: 8px; grid-template-columns: 27px minmax(0,1fr) auto; padding: 10px 7px; text-align: left; width: 100%; }
.grading-student-row.active { background: #f0ebff; border-color: #b9a5e8; }.grading-student-avatar { background: #e7e3f4; border-radius: 8px; color: #66528e; font-size: 12px; padding: 6px; text-align: center; }
.grading-student-row > span:nth-child(2) { display: grid; gap: 4px; min-width: 0; }.grading-student-row strong { font-size: 13px; overflow-wrap: anywhere; }.grading-student-row small { color: #6a7890; font-size: 11px; }.grading-student-row b { color: #65508e; font-size: 11px; }
.grading-roster-list :deep(.list-pager) { font-size: 11px; gap: 7px; justify-content: flex-start; padding: 12px 0; }.grading-roster-list :deep(.list-pager > span) { flex-basis: 100%; }.grading-roster-list :deep(.list-pager select) { width: auto; }
.grading-answer-view { padding: 18px; }.grading-student-heading { align-items: start; display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; }.grading-student-heading h3 { color: #243956; font-size: 20px; margin: 0 0 6px; }.grading-student-heading span { color: #64748b; font-size: 12px; }
.grading-student-step { display: flex; gap: 5px; }.grading-student-step button { background: white; border: 1px solid #dce3ef; color: #52637f; font-size: 12px; padding: 8px 10px; }
.grading-filter-note { background: #fff8ea; border-radius: 8px; color: #896a35; font-size: 12px; line-height: 1.7; padding: 10px; }
.grading-view-tabs { border-bottom: 1px solid #dfe6f2; display: flex; gap: 16px; margin: 18px 0; }.grading-view-tabs button { background: none; border-bottom: 2px solid transparent; border-radius: 0; color: #687b96; font-size: 13px; padding: 9px 2px; }.grading-view-tabs button.active { border-color: #7558b4; color: #624397; }
.grading-question-nav { display: flex; flex-wrap: wrap; gap: 7px; margin-bottom: 16px; }.grading-question-nav button { background: white; border: 1px solid #dce3ef; border-radius: 8px; color: #576b86; font-size: 12px; height: 34px; min-width: 34px; padding: 6px; }.grading-question-nav button.active { background: #7455ac; border-color: #7455ac; color: white; }
.grading-question-card { background: white; border: 1px solid #e0e7f2; border-radius: 14px; color: #304561; font-size: 14px; line-height: 1.8; padding: 18px; overflow-wrap: anywhere; }.grading-question-kicker { color: #6b7f9b; display: flex; font-size: 12px; justify-content: space-between; margin-bottom: 12px; }
.grading-question-options { background: #f8faff; border-radius: 10px; list-style: none; margin: 16px 0; padding: 12px 16px; }.grading-question-options li { margin: 5px 0; }
.grading-options summary { color: #667894; cursor: pointer; font-size: 13px; margin-top: 12px; }
.grading-student-answer { background: #f5f1fc; border: 1px solid #e5dcf3; border-radius: 10px; margin: 20px 0 14px; padding: 14px; }.grading-student-answer h4, .grading-reference h4 { font-size: 13px; margin: 0 0 8px; }.grading-reference { border-top: 1px solid #e6ebf4; padding-top: 12px; }.grading-reference summary { color: #5d4a8f; cursor: pointer; font-size: 13px; font-weight: 650; }.grading-reference h4 { margin-top: 16px; }
.grading-score-pane { background: white; border-left: 1px solid #e4e9f2; display: flex; flex-direction: column; overflow: hidden; padding: 16px; }.grading-empty, .grading-select-prompt { color: #64748b; font-size: 13px; line-height: 1.8; padding: 16px 5px; }.grading-select-prompt { align-self: start; padding: 40px 24px; }.grading-load-error { color: #a54339; font-size: 12px; line-height: 1.7; }.grading-load-error button { font-size: 12px; padding: 7px; }
.grading-mobile-switch { display: none; }button:focus-visible, input:focus-visible, select:focus-visible, summary:focus-visible { outline: 3px solid #b5a3e0; outline-offset: 2px; }
@media (max-width: 1100px) { .grading-workspace { grid-template-columns: 180px minmax(0, 1fr) 240px; }.grading-answer-view { padding: 14px; }.grading-question-card { padding: 14px; } }
@media (max-width: 850px) {
  .grading-workspace { display: block; height: auto; }.grading-roster { display: none; }.grading-roster.is-mobile-open { display: block; max-height: 360px; overflow: auto; }.grading-mobile-switch { align-items: center; background: #f5f2fc; border-bottom: 1px solid #e3ddef; display: flex; gap: 8px; justify-content: space-between; padding: 12px; position: sticky; top: 0; z-index: 2; }.grading-mobile-switch button { background: white; border: 1px solid #d8cdec; color: #624d88; font-size: 13px; padding: 9px 12px; }.grading-answer-view { overflow: visible; scroll-margin-top: 65px; }.grading-score-pane { border-left: 0; border-top: 1px solid #e4e9f2; overflow: visible; padding: 18px; scroll-margin-top: 65px; }
}
</style>
