<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
type Task = { title: string; kind: string; id: string; status: string; stage: string; error: string | null; result: { draft_id?: string; workflow_id?: string } | null; created_at: string }
const props = defineProps<{ request: (path: string, options?: RequestInit) => Promise<unknown>; refresh: number }>()
const emit = defineEmits<{ openDraft: [id: string]; openWork: [id: string] }>()
const rows = ref<Task[]>([]), busy = ref(''), error = ref(''), revision = ref(0), listOpen = ref(false)
const controller = new AbortController()
let live = true, timer: ReturnType<typeof setTimeout> | undefined, refreshing = false
function reload() { clearTimeout(timer); void refresh() }
async function refresh() {
  if (refreshing || !live) return
  refreshing = true
  try {
    const value = await props.request('/api/v1/assistant/tasks?page=1&page_size=3', { signal: controller.signal }) as { items: Task[] }
    if (live) { rows.value = value.items; error.value = '' }
  } catch (e) { if (live) error.value = e instanceof Error ? e.message : '任务读取失败' }
  finally { refreshing = false; if (live) timer = setTimeout(refresh, rows.value.some(t => ['queued', 'running'].includes(t.status)) ? 2500 : 15000) }
}
watch(() => props.refresh, () => { revision.value++; clearTimeout(timer); void refresh() }, { immediate: true })
onBeforeUnmount(() => { live = false; clearTimeout(timer); controller.abort() })
async function action(task: Task, name: 'cancel' | 'retry') {
  if (busy.value) return
  if (name === 'retry' && !window.confirm('重新生成可能产生新的模型调用费用，确认重试？')) return
  busy.value = task.id; error.value = ''
  try { await props.request(`/api/v1/assistant/tasks/${task.id}/${name}`, { method: 'POST' }); revision.value++; clearTimeout(timer); await refresh() }
  catch (e) { error.value = e instanceof Error ? e.message : '任务操作失败' }
  finally { busy.value = '' }
}
const loadPage = (page: number, size: number) => props.request(`/api/v1/assistant/tasks?page=${page}&page_size=${size}`, { signal: controller.signal }) as Promise<{ items: Task[]; total: number; page: number; page_size: number }>
const label = (status: string) => ({ queued: '等待中', running: '生成中', completed: '已完成', failed: '未完成', cancelled: '已停止' } as Record<string, string>)[status] || status
</script>
<template>
  <section class="assistant-task-panel"><header><h4>我的教学任务</h4><button type="button" @click="listOpen = !listOpen">{{ listOpen ? '收起历史' : '全部任务' }}</button></header><p v-if="error" role="alert">{{ error }} <button type="button" @click="reload">重试</button></p>
    <p v-if="!rows.length && !error" class="task-empty">生成的教案、题目、讲评与学情草稿会保存在这里，可离开后再查看。</p>
    <template v-for="task in rows" :key="task.id"><article><span v-if="['queued', 'running'].includes(task.status)" class="task-spinner" /><div><strong>{{ task.title }} · {{ label(task.status) }}</strong><p>{{ task.error || task.stage }}</p></div><button v-if="task.result?.draft_id" type="button" @click="emit('openDraft', task.result.draft_id)">查看草稿 ↗</button><button v-if="task.result?.workflow_id" type="button" @click="emit('openWork', task.result.workflow_id)">查看工作结果 ↗</button><button v-if="['queued', 'running'].includes(task.status)" type="button" :disabled="!!busy" @click="action(task, 'cancel')">停止</button><button v-if="task.status === 'failed'" type="button" :disabled="!!busy" @click="action(task, 'retry')">重试</button></article></template>
    <PagedList v-if="listOpen" :items="[] as Task[]" :load-page="loadPage" :scope="String(revision)" :page-size="5" label="教学任务历史" v-slot="{ items }"><article v-for="task in items" :key="task.id"><div><strong>{{ task.title }} · {{ label(task.status) }}</strong><p>{{ new Date(task.created_at).toLocaleString('zh-CN') }} · {{ task.stage }}</p></div><button v-if="task.result?.draft_id" type="button" @click="emit('openDraft', task.result.draft_id)">查看草稿</button><button v-if="task.result?.workflow_id" type="button" @click="emit('openWork', task.result.workflow_id)">查看工作结果</button><button v-if="task.status === 'failed'" type="button" :disabled="!!busy" @click="action(task, 'retry')">重试</button></article></PagedList>
  </section>
</template>
<style scoped>
.assistant-task-panel{border:1px solid #e0e8f5;background:#f8faff;padding:12px;border-radius:14px;margin-block:12px;font-size:12px;min-width:0}header,article{display:flex;align-items:center;gap:10px;flex-wrap:wrap}header{justify-content:space-between}h4,p{margin:0}article{border-top:1px solid #e4ebf7;padding-block:12px}article>div{flex:1;min-width:130px}article p,.task-empty{color:#76859e;line-height:1.7}.task-empty{padding-top:10px}button{font-size:12px;white-space:nowrap}.task-spinner{height:16px;width:16px;flex:none;border:2px solid #d6e0f7;border-top-color:#5265dc;border-radius:50%;animation:task-spin .9s linear infinite}[role=alert]{color:#ac443a}@keyframes task-spin{to{transform:rotate(360deg)}}@media(prefers-reduced-motion:reduce){.task-spinner{animation:none;border-color:#5265dc}}
</style>
