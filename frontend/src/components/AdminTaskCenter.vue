<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
import AdminGovernancePanel from './AdminGovernancePanel.vue'
import type { AdminOperation, AdminTaskCall, AdminTaskJob, AdminTaskQuota } from '../adminTasks'

const props = defineProps<{ request: (path: string, options?: RequestInit) => Promise<unknown>; focus: string; focusRevision: number }>()
const emit = defineEmits<{ changed: []; settings: []; users: [] }>()
type Page<T> = { items: T[]; total: number; page: number; page_size: number }
const tab = ref<'jobs' | 'quotas' | 'calls' | 'accounts' | 'model' | 'history'>('jobs')
const governancePanel = ref<{ refreshCurrent: () => void } | null>(null)
const emptyJobs: AdminTaskJob[] = []
const emptyCalls: AdminTaskCall[] = []
const emptyOperations: AdminOperation[] = []
const quotas = ref<AdminTaskQuota[]>([])
const jobStatus = ref('failed')
const keyword = ref('')
const appliedKeyword = ref('')
const callDays = ref(7)
const revision = ref(0)
const selectedJob = ref<AdminTaskJob | null>(null)
const selectedQuota = ref<AdminTaskQuota | null>(null)
const selectedCall = ref<AdminTaskCall | null>(null)
const targetLimit = ref(100)
const reason = ref('')
const operation = ref<AdminOperation | null>(null)
const operationSheet = ref<HTMLElement | null>(null)
const acknowledged = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const clock = ref(Date.now())
const controller = new AbortController()
let searchTimer: ReturnType<typeof setTimeout> | undefined
let clockTimer: ReturnType<typeof setInterval> | undefined
let readSequence = 0
let dialogSequence = 0
let live = true
let returnFocus: HTMLElement | null = null
const remainingSeconds = computed(() => operation.value ? Math.max(0, Math.ceil((Date.parse(operation.value.expires_at) - clock.value) / 1000)) : 0)
const canExecute = computed(() => operation.value?.status === 'prepared' && remainingSeconds.value > 0 && acknowledged.value && !busy.value)
const statusLabels: Record<string, string> = { queued: '排队中', processing: '处理中', completed: '已完成', failed: '失败',
  prepared: '等待确认', applied: '已执行', cancelled: '已取消', expired: '已过期', stale: '对象已变化' }
const fieldLabels: Record<string, string> = { role: '角色', daily_limit: '每日额度', title: '资料', status: '状态',
  attempts: '已处理次数', has_source_file: '原始文件可用', error_message: '失败原因', progress_percent: '处理进度' }
Object.assign(fieldLabels, { username: '登录账号', display_name: '姓名', active: '启用状态', provider: '生成服务',
  model: '模型名称', api_base: '接口基础地址', timeout_seconds: '超时秒数', fallback_offline: '离线回退',
  retrieval_top_k: '检索片段数', retrieval_min_score: '最低置信度', retrieval_vector_weight: '向量权重',
  configured: '在线参数齐备', api_key_changed: '更换密钥（不显示明文）' })
const roleLabels: Record<string, string> = { student: '学生', teacher: '教师', admin: '管理员' }
const changedKeys = computed(() => operation.value ? Object.keys(operation.value.proposed).filter(key =>
  key === 'api_key_changed' ? operation.value!.proposed[key] === true : JSON.stringify(operation.value!.before[key]) !== JSON.stringify(operation.value!.proposed[key])) : [])
const time = (value: string | null) => value ? new Date(value).toLocaleString('zh-CN') : '暂无'
function fieldValue(key: string, value: unknown): string {
  if (key === 'role') return roleLabels[String(value)] || String(value)
  if (key === 'status') return statusLabels[String(value)] || String(value)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return value === null || value === undefined ? '无' : String(value)
}
function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  return props.request(path, { ...options, signal: controller.signal }) as Promise<T>
}
const loadJobs = (page: number, size: number) => api<Page<AdminTaskJob>>(`/api/v1/admin/assistant-tasks/jobs?${new URLSearchParams({ page: String(page), page_size: String(size), status: jobStatus.value, keyword: appliedKeyword.value })}`)
const loadCalls = (page: number, size: number) => api<Page<AdminTaskCall>>(`/api/v1/admin/assistant-tasks/calls?page=${page}&page_size=${size}&days=${callDays.value}`)
const loadOperations = (page: number, size: number) => api<Page<AdminOperation>>(`/api/v1/admin/assistant-operations?page=${page}&page_size=${size}`)

async function refreshQuotas(role?: string) {
  const current = ++readSequence
  try {
    const value = await api<AdminTaskQuota[]>('/api/v1/admin/assistant-tasks/quotas')
    if (!live || current !== readSequence) return
    quotas.value = value
    if (role) chooseQuota(value.find(item => item.role === role) || null)
  } catch (cause) { if (live && current === readSequence) error.value = cause instanceof Error ? cause.message : '额度读取失败' }
}
function chooseQuota(item: AdminTaskQuota | null) {
  selectedQuota.value = item
  selectedJob.value = null
  reason.value = ''
  if (item) targetLimit.value = item.daily_limit
}
function chooseJob(item: AdminTaskJob) {
  selectedJob.value = item
  selectedQuota.value = null
  reason.value = ''
  error.value = ''
}
async function refreshJob() {
  if (!selectedJob.value || busy.value) return
  const jobId = selectedJob.value.id
  busy.value = true
  error.value = ''
  try {
    const value = await api<Partial<AdminTaskJob>>(`/api/v1/document-jobs/${jobId}`)
    if (live && selectedJob.value?.id === jobId) selectedJob.value = { ...selectedJob.value, ...value }
    revision.value += 1
  } catch (cause) { if (live) error.value = cause instanceof Error ? cause.message : '任务读取失败' }
  finally { if (live) busy.value = false }
}
async function prepare() {
  if (busy.value || reason.value.trim().length < 5) return
  const quota = selectedQuota.value
  const job = selectedJob.value
  if (!quota && !job) return
  const dialog = ++dialogSequence
  busy.value = true
  error.value = ''
  try {
    const value = await api<AdminOperation>('/api/v1/admin/assistant-operations/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        kind: quota ? 'set_model_quota' : 'retry_document', target_id: quota ? quota.role : job!.id,
        reason: reason.value.trim(), ...(quota ? { daily_limit: targetLimit.value } : {}),
      }),
    })
    if (!live) return
    if (dialog === dialogSequence) {
      operation.value = value
      acknowledged.value = false
    }
    revision.value += 1
  } catch (cause) { if (live) error.value = cause instanceof Error ? cause.message : '预览失败，请刷新对象重试' }
  finally { if (live) busy.value = false }
}
async function resolve(execute: boolean) {
  const retrySync = operation.value?.kind === 'set_model_config' && operation.value?.status === 'applied' && operation.value.result.runtime_synchronized === false
  if (!operation.value || busy.value || (execute && !canExecute.value && !retrySync)) return
  const dialog = dialogSequence
  busy.value = true
  error.value = ''
  try {
    const value = await api<AdminOperation>(`/api/v1/admin/assistant-operations/${operation.value.id}/${execute ? 'execute' : 'cancel'}`, {
      method: 'POST', ...(execute ? { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ confirmed: true }) } : {}),
    })
    if (!live) return
    if (dialog === dialogSequence) operation.value = value
    else notice.value = value.result.message || '处理结果已保存，可在“我的处理记录”查看。'
    acknowledged.value = false
    revision.value += 1
    void refreshQuotas(selectedQuota.value?.role)
    governancePanel.value?.refreshCurrent()
    emit('changed')
  } catch (cause) { if (live) error.value = cause instanceof Error ? cause.message : '暂未完成，请重新读取操作结果' }
  finally { if (live) busy.value = false }
}
async function restoreOperation(item: AdminOperation) {
  if (busy.value) return
  const dialog = ++dialogSequence
  busy.value = true
  error.value = ''
  try {
    const value = await api<AdminOperation>(`/api/v1/admin/assistant-operations/${item.id}`)
    if (!live) return
    if (dialog === dialogSequence) {
      operation.value = value
      acknowledged.value = false
    }
  } catch (cause) { if (live) error.value = cause instanceof Error ? cause.message : '记录读取失败' }
  finally { if (live) busy.value = false }
}
function closePreview() {
  dialogSequence += 1
  if (busy.value) notice.value = '操作请求仍在处理中，可稍后在处理记录读取结果。关闭窗口不会撤销已提交的操作。'
  else if (operation.value?.status === 'prepared') notice.value = '预览暂未执行，可在“我的处理记录”中恢复；10 分钟后过期。'
  operation.value = null
}
function dialogKey(event: KeyboardEvent) {
  if (event.key === 'Escape') { event.preventDefault(); closePreview(); return }
  if (event.key !== 'Tab') return
  const elements = Array.from(operationSheet.value?.querySelectorAll<HTMLElement>('button:not([disabled]), input:not([disabled]), [tabindex="0"]') || [])
  const first = elements[0], last = elements.at(-1)
  if (!first || !last) { event.preventDefault(); operationSheet.value?.focus(); return }
  if (event.shiftKey && (document.activeElement === first || document.activeElement === operationSheet.value)) { event.preventDefault(); last.focus() }
  else if (!event.shiftKey && (document.activeElement === last || document.activeElement === operationSheet.value)) { event.preventDefault(); first.focus() }
}
watch(() => operation.value?.id, async (id, previous) => {
  if (id && !previous) {
    returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    await nextTick()
    if (live && operation.value?.id === id) operationSheet.value?.focus()
  } else if (!id && previous && returnFocus?.isConnected) returnFocus.focus()
})
function callHint(item: AdminTaskCall): string {
  if (/ValidationError|ValueError/.test(item.error_type)) return '结果结构或内容未通过校验。请回原业务页面检查输入并决定是否重新生成，不会自动重放学生或教师任务。'
  if (/Timeout/.test(item.error_type)) return '记录到超时。可核对模型响应、网络和当前超时设置；仅凭此记录无法确定根因。'
  return '请核对发生时间、错误类型及服务配置。该记录不含原提问、密钥或响应正文，不能仅凭失败类型推断具体原因。'
}
function acceptGovernancePreview(value: AdminOperation) {
  dialogSequence += 1
  operation.value = value
  acknowledged.value = false
  revision.value += 1
  error.value = ''
}
watch(keyword, () => {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => { appliedKeyword.value = keyword.value.trim() }, 300)
})
watch(() => [props.focus, props.focusRevision], () => {
  const [section, role] = props.focus.split(':')
  tab.value = section === 'quota' ? 'quotas' : section === 'user' ? 'accounts' : ['jobs', 'quotas', 'calls', 'accounts', 'model', 'history'].includes(section) ? section as typeof tab.value : 'jobs'
  selectedJob.value = null
  selectedQuota.value = null
  selectedCall.value = null
  if (section === 'calls') callDays.value = ['1', '7', '30'].includes(role) ? Number(role) : 7
  error.value = ''
  notice.value = ''
  void refreshQuotas(section === 'quota' && role in roleLabels ? role : undefined)
}, { immediate: true })
onMounted(() => {
  clockTimer = setInterval(() => { clock.value = Date.now() }, 1000)
})
onBeforeUnmount(() => {
  live = false
  readSequence += 1
  controller.abort()
  if (clockTimer) clearInterval(clockTimer)
  if (searchTimer) clearTimeout(searchTimer)
})
</script>

<template>
  <section class="admin-task-center" aria-label="管理员助手任务中心">
    <header class="task-heading"><div><small>管理助理 · 具体任务</small><h2>从发现问题，到确认处理</h2><p>查看实时对象，先核对变更，再由你决定是否执行。</p></div><div class="task-links"><button type="button" class="ghost-button" @click="emit('settings')">原模型设置页 ↗</button><button type="button" class="ghost-button" @click="emit('users')">原账号管理页 ↗</button></div></header>
    <nav class="task-tabs" aria-label="管理任务分类"><button v-for="item in [{id:'jobs',name:'资料任务'}, {id:'calls',name:'模型异常'}, {id:'quotas',name:'角色额度'}, {id:'accounts',name:'账号治理'}, {id:'model',name:'模型配置'}, {id:'history',name:'我的处理记录'}]" :key="item.id" type="button" :class="{ active: tab === item.id }" :disabled="busy" @click="tab = item.id as typeof tab">{{ item.name }}</button></nav>
    <p v-if="error" role="alert" class="task-error">{{ error }}</p><p v-if="notice" role="status" class="task-notice">{{ notice }}</p>
    <p v-if="busy" class="task-loading" role="status"><i />正在核对记录，请稍候…</p>
    <template v-if="tab === 'jobs'">
      <div class="task-filters"><label>任务状态<select v-model="jobStatus"><option value="failed">失败任务</option><option value="all">全部任务</option><option value="queued">排队中</option><option value="processing">处理中</option><option value="completed">已完成</option></select></label><label class="task-search">搜索资料<input v-model="keyword" type="search" placeholder="输入正式资料名称" /></label><button type="button" class="ghost-button" @click="revision += 1">刷新列表</button></div>
      <PagedList :items="emptyJobs" :load-page="loadJobs" :scope="`${jobStatus}:${appliedKeyword}:${revision}`" label="资料任务" v-slot="{ items, total }"><div class="task-list"><button v-for="item in items" :key="item.id" type="button" class="task-row" :disabled="busy" @click="chooseJob(item)"><div><strong>{{ item.document_title }}</strong><small>{{ item.error_message || `${item.attempts} 次处理 · ${time(item.created_at)}` }}</small></div><span :class="`state-${item.status}`">{{ statusLabels[item.status] }} ›</span></button><p v-if="!total" class="task-empty">{{ jobStatus === 'failed' ? '当前没有匹配的失败任务，无需重试。可切换“全部任务”查看处理记录。' : '没有匹配的资料任务。' }}</p></div></PagedList>
      <section v-if="selectedJob" class="task-detail"><header><div><small>资料任务详情</small><h3>{{ selectedJob.document_title || selectedJob.filename }}</h3></div><button type="button" class="ghost-button" :disabled="busy" @click="refreshJob">刷新任务状态</button></header><div class="task-facts"><span>当前状态<b>{{ statusLabels[selectedJob.status] }}</b></span><span>处理进度<b>{{ selectedJob.progress_percent }}%</b></span><span>尝试次数<b>{{ selectedJob.attempts }}</b></span><span>原始文件<b>{{ selectedJob.has_source_file ? '可用' : '不可重试或已完成清理' }}</b></span></div><p v-if="selectedJob.error_message" class="task-error">{{ selectedJob.error_message }}</p><template v-if="selectedJob.status === 'failed' && selectedJob.has_source_file"><label>重试原因<textarea v-model="reason" maxlength="500" rows="3" placeholder="说明本次处理原因，至少 5 个字" /></label><button type="button" :disabled="busy || reason.trim().length < 5" @click="prepare">预览重试操作</button></template><p v-else class="task-muted">只有保留原始文件的失败任务可以重试。处理中或已完成的任务不会重复排队。</p></section>
    </template>
    <template v-else-if="tab === 'calls'">
      <div class="task-filters"><label>时间范围<select v-model.number="callDays"><option :value="1">近 24 小时</option><option :value="7">近 7 天</option><option :value="30">近 30 天</option></select></label><span class="task-muted">仅展示已结束的失败记录，不把处理中或已取消请求算作错误。</span></div>
      <PagedList :items="emptyCalls" :load-page="loadCalls" :scope="`${callDays}:${revision}`" label="模型异常" v-slot="{ items, total }"><div class="task-list"><button v-for="item in items" :key="item.id" type="button" class="task-row" :disabled="busy" @click="selectedCall = item"><div><strong>{{ item.error_type }} · {{ item.model }}</strong><small>{{ item.user_name }} · {{ time(item.created_at) }}</small></div><span>查看详情 ›</span></button><p v-if="!total" class="task-empty">这段时间没有已结束的失败调用记录。</p></div></PagedList>
      <section v-if="selectedCall" class="task-detail"><h3>{{ selectedCall.error_type }}</h3><p>{{ callHint(selectedCall) }}</p><dl><dt>发生时间</dt><dd>{{ time(selectedCall.created_at) }}</dd><dt>调用功能</dt><dd>{{ selectedCall.feature }}</dd><dt>模型</dt><dd>{{ selectedCall.model }}</dd><dt>耗时</dt><dd>{{ (selectedCall.duration_ms / 1000).toFixed(1) }} 秒</dd></dl><div class="task-links"><button type="button" @click="tab = 'model'">核对并预览模型配置 ↗</button><button type="button" class="ghost-button" @click="tab = 'quotas'; chooseQuota(quotas.find(q => q.role === selectedCall?.role) || null)">查看该角色额度 ↗</button></div></section>
    </template>
    <template v-else-if="tab === 'quotas'">
      <div class="quota-cards"><button v-for="item in quotas" :key="item.role" type="button" :class="{ chosen: selectedQuota?.role === item.role }" :disabled="busy" @click="chooseQuota(item)"><span>{{ item.role_label }}</span><strong>{{ item.daily_limit }}<small>次 / 每人每日</small></strong><p>该角色当前计数日累计调用 {{ item.used_today }} 次</p><small>下次刷新 {{ time(item.resets_at) }}</small></button></div>
      <button type="button" class="ghost-button" :disabled="busy" @click="refreshQuotas(selectedQuota?.role)">刷新额度</button>
      <section v-if="selectedQuota" class="task-detail"><h3>调整{{ selectedQuota.role_label }}额度</h3><p>调整该角色每个账号的每日模型调用上限，不是全角色共享额度。不会补充模型服务商余额或返还已发生的调用。</p><div class="task-filters"><label>当前每人每日额度<input :value="selectedQuota.daily_limit" readonly /></label><label>新的每人每日额度<input v-model.number="targetLimit" type="number" min="1" max="100000" /></label></div><label>调整原因<textarea v-model="reason" rows="3" maxlength="500" placeholder="说明调整原因，至少 5 个字" /></label><button type="button" :disabled="busy || reason.trim().length < 5 || !Number.isInteger(targetLimit) || targetLimit < 1 || targetLimit > 100000 || targetLimit === selectedQuota.daily_limit" @click="prepare">预览额度变更</button></section>
      <p v-if="!quotas.length" class="task-empty">额度暂未加载，可点击刷新重试。</p>
    </template>
    <AdminGovernancePanel v-else-if="tab === 'accounts' || tab === 'model'" :key="tab" ref="governancePanel" :mode="tab === 'accounts' ? 'accounts' : 'model'" :focus="focus" :focus-revision="focusRevision" :request="request" :disabled="busy" @busy="busy = $event" @preview="acceptGovernancePreview" />
    <template v-else>
      <p class="task-muted">仅展示本管理员创建的预览与处理记录。关闭预览不会自动执行，过期后须重新准备。</p><button type="button" class="ghost-button" @click="revision += 1">刷新记录</button>
      <PagedList :items="emptyOperations" :load-page="loadOperations" :scope="String(revision)" label="我的处理记录" v-slot="{ items, total }"><div class="task-list"><button v-for="item in items" :key="item.id" type="button" class="task-row" :disabled="busy" @click="restoreOperation(item)"><div><strong>{{ item.title }}</strong><small>{{ item.reason }} · {{ time(item.created_at) }}</small></div><span :class="`state-${item.status}`">{{ statusLabels[item.status] }} ›</span></button><p v-if="!total" class="task-empty">还没有操作预览。可从具体资料任务或角色额度开始处理。</p></div></PagedList>
    </template>
    <div v-if="operation" class="operation-overlay" @click.self="closePreview">
      <section ref="operationSheet" class="operation-sheet" role="dialog" aria-modal="true" aria-labelledby="operation-title" tabindex="-1" @keydown="dialogKey">
        <header><div><small>人工确认 · {{ statusLabels[operation.status] }}</small><h3 id="operation-title">{{ operation.title }}</h3></div><button type="button" aria-label="关闭操作预览" @click="closePreview">×</button></header>
        <div class="operation-body">
          <p class="task-muted">原因：{{ operation.reason }}</p>
          <p class="change-summary">本次变更：{{ changedKeys.map(key => fieldLabels[key] || key).join('、') || '无字段变化' }}</p>
          <div class="operation-diff">
            <section><h4>预览时状态</h4><dl><template v-for="(value,key) in operation.before" :key="key"><dt>{{ fieldLabels[key] || key }}</dt><dd>{{ fieldValue(key, value) }}</dd></template></dl></section>
            <section><h4>拟进行的变更</h4><dl><template v-for="(value,key) in operation.proposed" :key="key"><dt :class="{ 'changed-field': changedKeys.includes(key) }">{{ fieldLabels[key] || key }}</dt><dd :class="{ 'changed-field': changedKeys.includes(key) }">{{ fieldValue(key, value) }}</dd></template></dl></section>
          </div>
          <p v-if="error" class="task-error" role="alert">{{ error }}</p>
          <template v-if="operation.status === 'prepared' && remainingSeconds"><p class="task-muted">预览 {{ Math.ceil(remainingSeconds / 60) }} 分钟后过期。服务端执行前会重新核对对象；变化后不会执行旧操作。</p><label class="confirm-check"><input v-model="acknowledged" type="checkbox" :disabled="busy" />我已核对对象、变更内容和影响，确认执行此操作</label></template>
          <p v-else-if="operation.status === 'prepared'" class="task-error">预览已过期，没有执行变更，请关闭后刷新对象。</p>
          <p v-if="operation.result.message" class="task-outcome" role="status">{{ operation.result.message }}</p>
          <p v-if="operation.kind === 'retry_document' && operation.status === 'applied'" class="task-muted">这条回执表示重新排队已接受，不表示资料已经处理成功；请回任务详情刷新当前状态。</p>
          <p v-if="operation.kind === 'set_model_config' && operation.status === 'applied'" class="task-muted">回执保留当时保存的配置。当前值请读取模型配置；重试同步始终加载最新保存值，不会恢复旧配置。</p>
        </div>
        <footer>
          <button type="button" class="ghost-button" :disabled="busy" @click="restoreOperation(operation)">重新读取结果</button>
          <template v-if="operation.status === 'prepared'"><button type="button" class="ghost-button" :disabled="busy" @click="resolve(false)">取消这次操作</button><button type="button" :disabled="!canExecute" @click="resolve(true)">{{ busy ? '处理中…' : '确认执行' }}</button></template>
          <button v-if="operation.kind === 'set_model_config' && operation.status === 'applied' && operation.result.runtime_synchronized === false" type="button" :disabled="busy" @click="resolve(true)">重试同步最新已保存配置</button>
          <button v-if="operation.status !== 'prepared'" type="button" @click="closePreview">完成</button>
        </footer>
      </section>
    </div>
  </section>
</template>

<style scoped>
.admin-task-center { min-width: 0; }
.task-heading, .task-detail > header, .task-links, .task-filters, .task-tabs { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.task-heading, .task-detail > header { justify-content: space-between; }
.task-heading small { font-size: 11px; color: #6383af; }
h2 { margin: 7px 0; font-size: 23px; color: #293f60; }
h3 { font-size: 17px; color: #334e72; margin: 10px 0; }
h4 { font-size: 13px; color: #4a658b; margin: 0 0 14px; }
p { font-size: 12px; color: #74859b; line-height: 1.8; }
button { font-size: 12px; }
.task-tabs { border-bottom: 1px solid #e1e9f3; margin: 20px 0; padding-bottom: 10px; }
.task-tabs button { background: transparent; color: #7285a1; border-radius: 9px; padding: 10px 15px; }
.task-tabs button.active { color: #3a62a5; background: #eaf1fc; }
.task-filters { margin: 14px 0; align-items: end; }
label { display: grid; gap: 7px; color: #5a718e; font-size: 12px; }
input, select, textarea { padding: 11px 12px; color: #344e70; border: 1px solid #d6e1ee; border-radius: 9px; background: #fff; font: inherit; min-width: 0; width: 100%; box-sizing: border-box; }
input:read-only { background: #eef2f7; }
textarea { resize: vertical; margin-bottom: 13px; }
.task-search { flex: 1; min-width: min(220px, 100%); }
.task-list { display: grid; gap: 9px; margin: 12px 0; }
.task-row { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 16px 18px; width: 100%; text-align: left; background: #fff; border: 1px solid #e2e9f2; color: #445f83; border-radius: 12px; }
.task-row:hover { background: #f3f7fe; border-color: #c5d7f0; }
.task-row > div { min-width: 0; }
.task-row strong { display: block; line-height: 1.7; overflow-wrap: anywhere; }
.task-row small { display: block; color: #8494aa; margin-top: 5px; font-size: 11px; overflow-wrap: anywhere; }
.task-row > span { flex: none; font-size: 11px; }
.task-detail { padding: 22px; border-radius: 14px; border: 1px solid #dce6f3; background: #f7faff; margin-top: 20px; }
.task-detail > label { margin-top: 16px; }
.task-facts, .quota-cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 180px),1fr)); gap: 12px; margin: 16px 0; }
.task-facts span { font-size: 11px; color: #8193ad; }
.task-facts b { display: block; font-size: 14px; margin-top: 8px; color: #425f86; }
.quota-cards button { background: #fff; border: 1px solid #dce6f3; border-radius: 14px; padding: 22px; text-align: left; color: #526e94; }
.quota-cards button.chosen { border-color: #7ca5dc; background: #eff5ff; box-shadow: 0 0 0 2px #dce9fc; }
.quota-cards strong { display: block; font-size: 30px; color: #365d96; margin: 13px 0; }
.quota-cards strong small { font-size: 11px; font-weight: 400; margin-left: 8px; }
.quota-cards small { color: #8497b1; font-size: 11px; }
.task-error { border-radius: 9px; color: #a06038; background: #fff1e6; padding: 11px 13px; }
.task-notice, .task-outcome { background: #edf5fc; color: #4a719e; border-radius: 10px; padding: 12px; }
.task-muted, .task-empty { font-size: 11px; color: #8798ae; line-height: 1.8; }
.task-empty { padding: 25px; text-align: center; background: #f7f9fc; border-radius: 12px; }
.task-loading { display: flex; align-items: center; gap: 8px; color: #6a85ab; }
.task-loading i { width: 12px; height: 12px; border: 2px solid #d6e3f3; border-top-color: #7196c8; border-radius: 50%; animation: spin .9s linear infinite; }
.state-failed, .state-expired, .state-stale { color: #ae6c46; }
.state-applied, .state-completed { color: #4e8b75; }
dl { display: grid; grid-template-columns: minmax(85px, auto) 1fr; font-size: 12px; gap: 10px 16px; }
dt { color: #8192aa; } dd { color: #4f6786; margin: 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.operation-overlay { position: fixed; inset: 0; z-index: 90; background: #17294477; display: grid; place-items: center; padding: 18px; }
.operation-sheet { background: #fff; border-radius: 18px; width: min(760px,100%); max-height: min(850px, calc(100dvh - 36px)); display: flex; flex-direction: column; overflow: hidden; box-shadow: 0 22px 70px #152a4d44; }
.operation-sheet > header { display: flex; justify-content: space-between; align-items: start; gap: 14px; padding: 20px 24px; border-bottom: 1px solid #e4ebf5; flex: none; }
.operation-sheet > header small { color: #7d92b0; font-size: 11px; }
.operation-sheet > header button { background: #f0f4fa; color: #6c83a4; border-radius: 9px; padding: 6px 12px; font-size: 23px; }
.operation-body { overflow-y: auto; padding: 0 24px 20px; min-height: 0; }
.operation-diff { display: grid; grid-template-columns: repeat(auto-fit,minmax(min(100%,250px),1fr)); gap: 14px; }
.operation-diff > section { background: #f5f8fc; border: 1px solid #e0e8f3; border-radius: 12px; padding: 16px; min-width: 0; }
.operation-sheet > footer { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 9px; border-top: 1px solid #e2eaf4; padding: 16px 24px; background: #fbfcfe; flex: none; }
.confirm-check { display: flex; align-items: start; gap: 10px; font-size: 12px; line-height: 1.9; padding: 14px 0; }
.confirm-check input { width: auto; margin-top: 5px; }
.change-summary { color: #426da9; background: #ecf3ff; border-radius: 10px; padding: 11px 13px; }
.changed-field { color: #315f9e; font-weight: 700; }
button:focus-visible, input:focus-visible, select:focus-visible, textarea:focus-visible { outline: 3px solid #8cb0df; outline-offset: 2px; }
@keyframes spin { to { transform: rotate(360deg); } }
@media(prefers-reduced-motion: reduce) { .task-loading i { animation: none; } }
@media(max-width:600px) { .task-heading h2 { font-size: 20px; } .task-detail { padding: 15px; } .task-row { padding: 13px; } .operation-overlay { padding: 8px; } .operation-sheet { max-height: calc(100dvh - 16px); } .operation-sheet > header, .operation-body, .operation-sheet > footer { padding-left: 16px; padding-right: 16px; } .task-facts { grid-template-columns: repeat(2,1fr); } }
</style>
