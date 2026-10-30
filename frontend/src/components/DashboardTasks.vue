<script setup lang="ts">
import { computed, ref } from 'vue'
import PagedList from './PagedList.vue'

type Kind = 'review' | 'late' | 'overdue'
type Task = { assignment_id: string; course_id: string; assignment_title: string; course_title: string; course_code: string
  due_at: string | null; student_count: number; submission_count: number; pending_review_count: number; pending_late_count: number; overdue_unsubmitted_count: number }
type Page = { items: Task[]; total: number; page: number; page_size: number }
const props = defineProps<{ kind: Kind; revision: string; busy: boolean; error: string
  counts: { pending_review_count: number; pending_late_count: number; overdue_unsubmitted_count: number }
  request: (path: string, options?: RequestInit) => Promise<unknown> }>()
const emit = defineEmits<{ kind: [value: Kind]; refresh: []; assignment: [id: string]; insights: [courseId: string] }>()
const keyword = ref(''), applied = ref('')
const refreshItems = computed<Task[]>(() => { void props.revision; return [] })
const tabs: Array<{ value: Kind; label: string; field: keyof typeof props.counts }> = [
  { value: 'review', label: '待批改', field: 'pending_review_count' },
  { value: 'late', label: '补交申请', field: 'pending_late_count' },
  { value: 'overdue', label: '已截止未交', field: 'overdue_unsubmitted_count' },
]
const scope = computed(() => `${props.kind}:${applied.value}`)
const current = computed(() => tabs.find(item => item.value === props.kind)!)
const amount = (item: Task) => item[current.value.field]
const unit = computed(() => props.kind === 'overdue' ? '人次' : '份')
async function load(page: number, size: number): Promise<Page> {
  const params = new URLSearchParams({ kind: props.kind, query: applied.value, page: String(page), page_size: String(size) })
  return await props.request(`/api/v1/dashboard/teaching-tasks?${params}`) as Page
}
const date = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN', { timeZone: 'Asia/Shanghai', month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false }) : '未设截止时间'
</script>

<template>
  <section class="home-teaching-tasks" aria-label="课程教学待办">
    <header><div><small>TEACHING NEXT</small><h2>教学待办</h2><p>从具体作业继续处理，也可查看对应课程学情。</p></div><button type="button" :disabled="busy" @click="emit('refresh')">{{ busy ? '刷新中…' : '刷新待办' }}</button></header>
    <div class="home-task-tabs" role="group" aria-label="教学待办类型"><button v-for="tab in tabs" :key="tab.value" type="button" :aria-pressed="kind === tab.value" :class="{ active: kind === tab.value }" @click="emit('kind', tab.value)">{{ tab.label }} <b>{{ counts[tab.field] }}</b><small>{{ tab.value === 'overdue' ? '人次' : '份' }}</small></button></div>
    <form class="home-task-search" role="search" @submit.prevent="applied = keyword.trim()"><input v-model="keyword" maxlength="100" type="search" aria-label="查找课程或作业待办" placeholder="搜索课程或作业名称…" /><button type="submit">查询</button><button v-if="applied" type="button" @click="keyword = ''; applied = ''">清空</button></form>
    <p v-if="error" class="home-task-error" role="alert">{{ error }}</p>
    <PagedList :items="refreshItems" :page-size="5" :scope="scope" :load-page="load" :label="current.label + '作业'" v-slot="{ items, loading, error: pageError }">
      <article v-for="item in items" :key="item.assignment_id" class="home-task-row"><div><span>{{ item.course_title }} · {{ item.course_code }}</span><h3>{{ item.assignment_title }}</h3><small>{{ date(item.due_at) }} · 当前 {{ item.student_count }} 名学生</small></div><p><strong>{{ amount(item) }}</strong><span>{{ unit }}{{ current.label }}</span></p><div class="home-task-actions"><button type="button" :disabled="busy" @click="emit('assignment', item.assignment_id)">{{ kind === 'review' ? '进入批改' : kind === 'late' ? '处理申请' : '查看作业' }} ↗</button><button type="button" class="home-task-light" :disabled="busy" @click="emit('insights', item.course_id)">查看课程学情</button></div></article>
      <p v-if="!loading && !pageError && !items.length" class="home-task-empty">{{ applied ? '没有匹配的待办，可清空搜索或切换类型。' : '当前没有这类待办。' }}</p>
    </PagedList>
  </section>
</template>

<style scoped>
.home-teaching-tasks { background: #fff; border: 1px solid #e0e7f2; border-radius: 18px; box-shadow: 0 8px 26px #1c315308; margin-bottom: 24px; padding: 24px; }
header { align-items: center; display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; margin-bottom: 18px; }
header small { color: #7391b9; font-size: 10px; font-weight: 750; letter-spacing: .12em; }
h2 { color: #233d60; font-size: 21px; margin: 5px 0; }
header p { color: #8494aa; font-size: 12px; line-height: 1.7; margin: 0; }
header > button { background: #edf3fd; border: 1px solid #d9e4f5; color: #3d659b; font-size: 12px; padding: 9px 12px; }
.home-task-tabs { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 15px; }
.home-task-tabs button { align-items: baseline; background: #f6f8fc; border: 1px solid #e1e7f2; color: #6f819c; display: flex; font-size: 12px; gap: 7px; padding: 10px 13px; }
.home-task-tabs button.active { background: #eaf2ff; border-color: #b8d1f7; color: #2c60a7; }
.home-task-tabs b { font-size: 15px; }
.home-task-tabs small { font-size: 10px; font-weight: 400; }
.home-task-search { display: flex; gap: 8px; margin-bottom: 12px; }
.home-task-search input { background: #f9fbfe; border: 1px solid #dce5f3; border-radius: 10px; color: #3c506d; flex: 1; font-size: 12px; min-width: 0; padding: 9px 12px; }
.home-task-search button { background: #edf3fc; color: #41679a; font-size: 12px; padding: 8px 12px; }
.home-task-row { align-items: center; border-bottom: 1px solid #edf1f7; display: grid; gap: 18px; grid-template-columns: minmax(0,1fr) auto auto; padding: 16px 0; }
.home-task-row > div:first-child { min-width: 0; }
.home-task-row span { color: #8293ac; font-size: 11px; }
.home-task-row h3 { color: #2f4564; font-size: 14px; line-height: 1.8; margin: 4px 0; overflow-wrap: anywhere; }
.home-task-row small { color: #9aa7ba; font-size: 11px; }
.home-task-row > p { display: grid; gap: 4px; margin: 0; min-width: 70px; text-align: right; }
.home-task-row strong { color: #375e96; font-size: 22px; }
.home-task-actions { display: grid; gap: 5px; }
.home-task-actions button { background: #e6effe; color: #3262a7; font-size: 11px; padding: 8px 11px; }
.home-task-actions .home-task-light { background: transparent; color: #8a9eb9; font-size: 10px; }
.home-task-error { background: #fff1ee; border-radius: 8px; color: #a15b4b; font-size: 12px; padding: 10px 12px; }
.home-task-empty { color: #94a3b8; font-size: 12px; padding: 18px 0; }
.home-teaching-tasks :deep(.list-pager) { padding-inline-end: 0; }
:is(button,input):focus-visible { outline: 3px solid #adc8ee; outline-offset: 3px; }
@media (max-width: 680px) { .home-teaching-tasks { padding: 17px; } .home-task-row { gap: 12px; grid-template-columns: minmax(0,1fr) auto; } .home-task-actions { display: flex; grid-column: 1/-1; } .home-task-tabs button { flex: 1; font-size: 11px; gap: 4px; padding: 9px; } }
</style>
