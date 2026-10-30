<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import PagedList from './PagedList.vue'
import type { AdminOperation, AdminTaskModel, AdminTaskUser } from '../adminTasks'

const props = defineProps<{
  mode: 'accounts' | 'model'; focus: string; focusRevision: number; disabled: boolean
  request: (path: string, options?: RequestInit) => Promise<unknown>
}>()
const emit = defineEmits<{ preview: [operation: AdminOperation]; busy: [busy: boolean] }>()
type Page<T> = { items: T[]; total: number; page: number; page_size: number }
const emptyUsers: AdminTaskUser[] = []
const roleLabels = { student: '学生', teacher: '教师', admin: '管理员' }
const keyword = ref('')
const query = ref('')
const role = ref('all')
const active = ref('all')
const selected = ref<AdminTaskUser | null>(null)
const change = ref<'active' | 'role'>('active')
const targetActive = ref(true)
const targetRole = ref<AdminTaskUser['role']>('student')
const savedModel = ref<AdminTaskModel | null>(null)
const editedModel = ref<AdminTaskModel | null>(null)
const newKey = ref('')
const reason = ref('')
const error = ref('')
const busy = ref(false)
const loading = ref(false)
const refresh = ref(0)
const controller = new AbortController()
let live = true
let sequence = 0
let timer: ReturnType<typeof setTimeout> | undefined
function api<T>(path: string, options: RequestInit = {}): Promise<T> {
  return props.request(path, { ...options, signal: controller.signal }) as Promise<T>
}
const loadUsers = (page: number, size: number) => api<Page<AdminTaskUser>>(`/api/v1/admin/assistant-tasks/users?${new URLSearchParams({ page: String(page), page_size: String(size), keyword: query.value, role: role.value, active: active.value })}`)

async function readUser(id: string) {
  if (busy.value) return
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const value = await api<AdminTaskUser>(`/api/v1/admin/assistant-tasks/users/${id}`)
    if (!live || current !== sequence) return
    selected.value = value
    targetActive.value = value.active
    targetRole.value = value.role
    change.value = 'active'
    reason.value = ''
  } catch (cause) { if (live && current === sequence) error.value = cause instanceof Error ? cause.message : '账号读取失败' }
  finally { if (live && current === sequence) loading.value = false }
}
async function readModel() {
  if (busy.value) return
  const current = ++sequence
  loading.value = true
  error.value = ''
  try {
    const value = await api<AdminTaskModel>('/api/v1/admin/assistant-tasks/model')
    if (!live || current !== sequence) return
    savedModel.value = value
    editedModel.value = { ...value }
    newKey.value = ''
    reason.value = ''
  } catch (cause) { if (live && current === sequence) error.value = cause instanceof Error ? cause.message : '模型配置读取失败' }
  finally { if (live && current === sequence) loading.value = false }
}
async function prepare() {
  if (busy.value || loading.value || props.disabled || reason.value.trim().length < 5) return
  let payload: Record<string, unknown>
  if (props.mode === 'accounts' && selected.value) {
    payload = { kind: change.value === 'active' ? 'set_user_active' : 'set_user_role', target_id: selected.value.id,
      ...(change.value === 'active' ? { active: targetActive.value } : { role: targetRole.value }) }
  } else if (props.mode === 'model' && editedModel.value) {
    const model = editedModel.value
    payload = { kind: 'set_model_config', target_id: 'current', config: {
      provider: model.provider, model: model.model, api_base: model.api_base, api_key: newKey.value.trim() || null,
      timeout_seconds: model.timeout_seconds, fallback_offline: model.fallback_offline, retrieval_top_k: model.retrieval_top_k,
      retrieval_min_score: model.retrieval_min_score, retrieval_vector_weight: model.retrieval_vector_weight,
    } }
  } else return
  busy.value = true
  emit('busy', true)
  error.value = ''
  try {
    const value = await api<AdminOperation>('/api/v1/admin/assistant-operations/preview', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ ...payload, reason: reason.value.trim() }),
    })
    if (!live) return
    newKey.value = ''
    emit('preview', value)
  } catch (cause) { if (live) error.value = cause instanceof Error ? cause.message : '操作预览失败，请刷新对象重试' }
  finally { if (live) { busy.value = false; emit('busy', false) } }
}
watch(keyword, () => {
  if (timer) clearTimeout(timer)
  timer = setTimeout(() => { query.value = keyword.value.trim() }, 300)
})
watch(() => [props.mode, props.focus, props.focusRevision], () => {
  selected.value = null
  error.value = ''
  newKey.value = ''
  reason.value = ''
  if (props.mode === 'accounts') active.value = props.focus === 'accounts:inactive' ? 'inactive' : 'all'
  if (props.mode === 'model') void readModel()
  else if (/^user:[0-9a-f-]{36}$/i.test(props.focus)) void readUser(props.focus.slice(5))
}, { immediate: true })
defineExpose({ refreshCurrent: () => {
  if (props.mode === 'model') void readModel()
  else if (selected.value) void readUser(selected.value.id)
  refresh.value += 1
} })
onBeforeUnmount(() => {
  live = false
  sequence += 1
  newKey.value = ''
  controller.abort()
  if (timer) clearTimeout(timer)
  emit('busy', false)
})
</script>

<template>
  <div class="governance-panel" :aria-busy="busy || loading">
    <p v-if="loading" role="status" class="governance-note">正在读取最新对象…</p>
    <p v-if="busy" role="status" class="governance-note">正在核对并准备预览，尚未修改账号或配置…</p>
    <p v-if="error" class="governance-error" role="alert">{{ error }}</p>
    <template v-if="mode === 'accounts'">
      <div class="governance-filters"><label class="search-field">查找账号<input v-model="keyword" type="search" placeholder="姓名、登录账号或学号" /></label><label>角色<select v-model="role"><option value="all">全部角色</option><option value="student">学生</option><option value="teacher">教师</option><option value="admin">管理员</option></select></label><label>状态<select v-model="active"><option value="all">全部状态</option><option value="active">已启用</option><option value="inactive">已停用</option></select></label><button type="button" class="ghost-button" @click="refresh += 1">刷新列表</button></div>
      <PagedList :items="emptyUsers" :load-page="loadUsers" :scope="`${query}:${role}:${active}:${refresh}`" label="账号查询" v-slot="{ items, total }"><div class="user-rows"><button v-for="item in items" :key="item.id" type="button" class="user-row" :disabled="busy || disabled" @click="readUser(item.id)"><div><strong>{{ item.display_name }}</strong><small>{{ item.username }} · {{ roleLabels[item.role] }}</small></div><span>{{ item.active ? '已启用' : '已停用' }} ›</span></button><p v-if="!total" class="governance-empty">没有找到匹配的账号。</p></div></PagedList>
      <section v-if="selected" class="governance-detail"><header><div><small>具体账号</small><h3>{{ selected.display_name }} <span>{{ selected.username }}</span></h3></div><button type="button" class="ghost-button" :disabled="busy || loading || disabled" @click="readUser(selected.id)">刷新当前账号</button></header><p>当前为{{ roleLabels[selected.role] }}，账号{{ selected.active ? '已启用' : '已停用' }}。角色变更不会自动迁移课程、作业或成绩。</p><p v-if="selected.is_current_actor" class="governance-warning">这是当前登录账号。不能修改自己的角色；如停用自己，后续请求将退出当前登录。</p><p v-if="selected.is_last_active_admin" class="governance-warning">这是最后一名启用管理员，不能停用或降为其他角色。</p><div class="change-tabs"><button type="button" :class="{ chosen: change === 'active' }" :disabled="busy || disabled" @click="change = 'active'">调整启用状态</button><button type="button" :class="{ chosen: change === 'role' }" :disabled="busy || disabled || selected.is_current_actor || selected.is_last_active_admin" @click="change = 'role'">调整角色</button></div><label v-if="change === 'active'">目标状态<select v-model="targetActive" :disabled="busy || disabled || selected.is_last_active_admin"><option :value="true">启用账号</option><option :value="false">停用账号</option></select></label><label v-else>目标角色<select v-model="targetRole" :disabled="busy || disabled || selected.is_current_actor || selected.is_last_active_admin"><option value="student">学生</option><option value="teacher">教师</option><option value="admin">管理员</option></select></label><label>处理原因<textarea v-model="reason" maxlength="500" rows="3" placeholder="说明影响和处理原因，至少 5 个字" /></label><button type="button" :disabled="busy || loading || disabled || reason.trim().length < 5 || (change === 'active' ? targetActive === selected.active : targetRole === selected.role)" @click="prepare">预览账号变更</button></section>
    </template>
    <template v-else>
      <div class="model-heading"><div><h3>生成模型与检索配置</h3><p>先准备前后对照，确认后才影响后续课程问答与助手任务。</p></div><button type="button" class="ghost-button" :disabled="busy || loading || disabled" @click="readModel">重新读取已保存配置</button></div>
      <p v-if="savedModel" class="governance-note">{{ savedModel.configured ? '在线参数已配置；不代表本次已探测服务连通性。' : '当前为离线模式或尚未配置在线密钥。' }} {{ savedModel.runtime_synchronized ? '当前服务进程与已保存配置一致。' : '当前进程与已保存配置不一致，请核对处理记录并同步配置。' }}</p>
      <p v-if="savedModel?.credential_recovery_required" class="governance-warning">已保存密钥暂不可读取。可填写新密钥准备修复预览，或明确切换到离线模式；不会显示旧密钥或暗中改用其他在线凭据。</p>
      <form v-if="editedModel" class="model-form" @submit.prevent="prepare">
        <div class="model-grid"><label>生成服务<select v-model="editedModel.provider" :disabled="busy || disabled"><option value="offline">离线证据回答</option><option value="compatible">兼容模型服务</option><option value="openai">OpenAI 服务</option></select></label><label>模型名称<input v-model="editedModel.model" maxlength="200" required :disabled="busy || disabled" /></label><label class="wide-field">接口基础地址<input v-model="editedModel.api_base" type="url" maxlength="500" required :disabled="busy || disabled" placeholder="不包含密钥或查询参数" /></label><label class="wide-field">新 API Key（留空保留现有值）<input v-model="newKey" type="password" maxlength="1000" autocomplete="new-password" :disabled="busy || disabled" placeholder="不回显原密钥，也不会写入本地浏览器存储" /></label><label>请求超时（秒）<input v-model.number="editedModel.timeout_seconds" type="number" min="3" max="300" step="1" required :disabled="busy || disabled" /></label><label>检索片段数<input v-model.number="editedModel.retrieval_top_k" type="number" min="1" max="20" required :disabled="busy || disabled" /></label><label>最低置信度<input v-model.number="editedModel.retrieval_min_score" type="number" min="0" max="1" step="0.01" required :disabled="busy || disabled" /></label><label>向量检索权重<input v-model.number="editedModel.retrieval_vector_weight" type="number" min="0" max="1" step="0.01" required :disabled="busy || disabled" /></label></div><label class="check-label"><input v-model="editedModel.fallback_offline" type="checkbox" :disabled="busy || disabled" />在线回答失败时允许离线回退</label><p class="governance-warning">模型或接口变更影响后续调用，调节检索参数会影响资料命中。新密钥只加密存入待确认记录，预览不显示明文；取消后清除该待确认密钥。</p><label>变更原因<textarea v-model="reason" rows="3" minlength="5" maxlength="500" required :disabled="busy || disabled" placeholder="说明本次调整及预期影响" /></label><button type="submit" :disabled="busy || loading || disabled || reason.trim().length < 5">预览模型与检索配置变更</button>
      </form>
      <button v-else-if="!loading" type="button" class="ghost-button" @click="readModel">重试读取模型配置</button>
    </template>
  </div>
</template>

<style scoped>
.governance-panel { min-width: 0; }
.governance-filters, .governance-detail > header, .model-heading, .change-tabs { display: flex; align-items: end; flex-wrap: wrap; gap: 12px; margin: 16px 0; }
.search-field { flex: 1; min-width: min(210px,100%); }
label { display: grid; gap: 8px; color: #607796; font-size: 12px; }
input, select, textarea { font: inherit; box-sizing: border-box; width: 100%; min-width: 0; border: 1px solid #d4e0ef; border-radius: 10px; padding: 11px 12px; color: #3d577a; background: #fff; }
select { appearance: none; padding-right: 34px; background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='14' height='14' viewBox='0 0 24 24' fill='none' stroke='%23778ba7' stroke-width='2'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E"); background-repeat: no-repeat; background-position: right 12px center; }
input:focus-visible, select:focus-visible, textarea:focus-visible, button:focus-visible { outline: 3px solid #9bbce7; outline-offset: 2px; }
input:disabled, select:disabled, textarea:disabled { background-color: #f0f3f8; }
textarea { resize: vertical; margin-bottom: 14px; }
button { font-size: 12px; }
h3 { margin: 8px 0; font-size: 17px; color: #35527b; }
h3 > span { font-size: 11px; font-weight: 400; color: #8b9bb0; }
p { font-size: 12px; line-height: 1.8; color: #7c8fa8; }
.user-rows { display: grid; gap: 9px; margin: 12px 0; }
.user-row { display: flex; justify-content: space-between; align-items: center; gap: 14px; text-align: left; background: #fff; border: 1px solid #e0e8f3; border-radius: 12px; padding: 15px 18px; color: #4c688d; }
.user-row:hover { background: #f3f7fd; border-color: #bad0ef; }
.user-row small { display: block; margin-top: 6px; color: #889bb5; font-size: 11px; }
.user-row > span { font-size: 11px; flex: none; }
.governance-detail, .model-form { background: #f7faff; border: 1px solid #dbe6f5; border-radius: 15px; padding: 22px; margin-top: 18px; }
.governance-detail > header, .model-heading { align-items: center; justify-content: space-between; }
.governance-detail > header small { font-size: 11px; color: #8198b7; }
.governance-detail > label { margin: 16px 0 0; }
.change-tabs button { border-radius: 9px; padding: 9px 12px; background: #edf2fa; color: #758eaf; }
.change-tabs button.chosen { background: #e0ebfc; color: #416ca7; }
.governance-note, .governance-warning, .governance-error { border-radius: 10px; padding: 11px 13px; font-size: 12px; line-height: 1.8; }
.governance-note { background: #edf4fc; color: #6684ad; }
.governance-warning, .governance-error { background: #fff1e5; color: #9c6a43; }
.governance-empty { text-align: center; padding: 25px; background: #f5f8fc; border-radius: 12px; }
.model-grid { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 16px; }
.wide-field { grid-column: 1/-1; }
.check-label { display: flex; align-items: center; gap: 9px; margin: 18px 0; }
.check-label input { width: auto; }
@media(max-width:600px) { .model-grid { grid-template-columns: 1fr; } .governance-detail,.model-form { padding: 15px; } .model-heading { align-items: start; } }
</style>
