<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import DetailDialog from './DetailDialog.vue'
import { accountRequest, invitationLink, accountStateLabel } from '../accountAccess'
import type { AccountUser, AccountPage, RegistrationPolicy } from '../accountAccess'
type Tab = 'invites' | 'joins' | 'applications' | 'recoveries' | 'policy'
type Course = { id: string; title: string; code: string; status?: string; semester?: string | null }
const props = defineProps<{ base: string; token: string; user: AccountUser; courses: Course[]; courseId?: string }>()
const emit = defineEmits<{ close: []; changed: [] }>()
const tab = ref<Tab>('invites'), page = ref(1), pageSize = ref(10), status = ref(''), search = ref(''), appliedSearch = ref('')
const result = ref<AccountPage | null>(null), loading = ref(false), busy = ref(false), error = ref(''), notice = ref('')
const policy = ref<RegistrationPolicy | null>(null), policyOriginal = ref(''), policyConfirmed = ref(false)
const kind = ref('student'), label = ref(''), courseId = ref(props.courseId || ''), courseSearch = ref(''), days = ref(7), maxUses = ref(30), approval = ref(false), showCreate = ref(false)
const secret = ref(''), secretKind = ref<'invite' | 'reset'>('invite'), secretExpiry = ref(''), copied = ref(false)
const confirmAction = ref<Record<string, any> | null>(null), reason = ref(''), confirmed = ref(false)
const leaveAction = ref<(() => void) | null>(null), leaveMessage = ref('')
const isAdmin = computed(() => props.user.role === 'admin')
const tabs = computed(() => [{ value: 'invites', label: '邀请管理' }, { value: 'joins', label: '选课审核' }, ...(isAdmin.value ? [{ value: 'applications', label: '教师申请' }, { value: 'recoveries', label: '密码找回' }, { value: 'policy', label: '注册设置' }] : [])])
const publishedCourses = computed(() => props.courses.filter(c => c.status === 'published'))
const selectableCourses = computed(() => publishedCourses.value.filter(c => c.id === courseId.value || `${c.title} ${c.code} ${c.semester || ''}`.toLowerCase().includes(courseSearch.value.trim().toLowerCase())))
const statuses = computed(() => tab.value === 'invites' ? [['active', '可使用'], ['exhausted', '名额已满'], ['expired', '已过期'], ['revoked', '已撤销'], ['unavailable', '课程不可加入']] : [['pending', tab.value === 'recoveries' ? '待协助' : '待审核'], [tab.value === 'recoveries' ? 'resolved' : 'approved', tab.value === 'recoveries' ? '已协助处理' : '已通过'], ['rejected', '未通过']])
const stateLabel = (item: Record<string, any>) => tab.value === 'invites' ? statuses.value.find(s => s[0] === item.state)?.[1] || '未知状态' : accountStateLabel(item.status)
const totalPages = computed(() => Math.max(1, Math.ceil((result.value?.total || 0) / pageSize.value)))
const policyDirty = computed(() => Boolean(policyOriginal.value && JSON.stringify(policy.value) !== policyOriginal.value))
const formSnapshot = () => JSON.stringify([kind.value, label.value, courseId.value, days.value, maxUses.value, approval.value])
const formOriginal = ref('')
const formDirty = computed(() => showCreate.value && formSnapshot() !== formOriginal.value)
const req = <T,>(path: string, body?: unknown, method?: string) => accountRequest<T>(props.base, props.token, path, body, method)
let generation = 0, alive = true
function guarded(action: () => void, includeSecret = false, includeDraft = true) {
  if (busy.value) return
  if ((includeDraft && (policyDirty.value || formDirty.value)) || (includeSecret && secret.value && !copied.value)) {
    leaveMessage.value = includeSecret && secret.value && !copied.value ? '还有尚未复制的一次性链接。继续后可能无法再次查看，请先复制并妥善保存。' : '还有未保存的填写内容。继续将放弃这些修改。'
    leaveAction.value = action
  } else action()
}
function acceptLeave() { const action = leaveAction.value; leaveAction.value = null; action?.() }
function close() { guarded(() => emit('close'), true) }
function clearForm() { showCreate.value = false; label.value = ''; courseSearch.value = ''; kind.value = 'student'; days.value = 7; maxUses.value = 30; approval.value = false; courseId.value = props.courseId || '' }
function toggleCreate() { if (showCreate.value) guarded(clearForm); else { showCreate.value = true; formOriginal.value = formSnapshot() } }
watch(kind, value => { maxUses.value = value === 'teacher' ? 1 : 30; approval.value = false })
watch(() => [policy.value?.mode, policy.value?.teacher_applications], () => { policyConfirmed.value = false })
async function load() {
  const current = ++generation; loading.value = true; error.value = ''
  try {
    if (tab.value === 'policy') {
      const data = await req<RegistrationPolicy>('/auth/registration-policy')
      if (alive && current === generation) { policy.value = data; policyOriginal.value = JSON.stringify(data) }
    } else {
      const params = new URLSearchParams({ page: String(page.value), page_size: String(pageSize.value) })
      if (status.value) params.set('status', status.value)
      if (appliedSearch.value) params.set('search', appliedSearch.value)
      const data = await req<AccountPage>(`/accounts/manage/${tab.value}?${params}`)
      if (alive && current === generation) { result.value = data; if (page.value > totalPages.value) { page.value = totalPages.value; await load() } }
    }
  } catch (e) { if (alive && current === generation) error.value = (e as Error).message }
  finally { if (current === generation) loading.value = false }
}
function select(value: string) {
  if (value === tab.value) return
  guarded(() => {
    clearForm(); policy.value = null; policyOriginal.value = ''; policyConfirmed.value = false
    tab.value = value as Tab; page.value = 1; result.value = null; notice.value = ''; confirmed.value = false
    search.value = ''; appliedSearch.value = ''; status.value = value === 'invites' ? '' : 'pending'; void load()
  })
}
function filter() { appliedSearch.value = search.value.trim(); page.value = 1; void load() }
function resetFilter() { search.value = ''; appliedSearch.value = ''; status.value = tab.value === 'invites' ? '' : 'pending'; page.value = 1; void load() }
async function act(fn: () => Promise<void>) {
  if (busy.value) return
  busy.value = true; error.value = ''; notice.value = ''
  try { await fn() } catch (e) { if (alive) error.value = (e as Error).message }
  finally { busy.value = false }
}
function create() {
  const action = () => void act(async () => {
    const data = await req<{ code: string; expires_at: string }>('/accounts/invites', { label: label.value.trim(), kind: kind.value, course_id: kind.value === 'student' && courseId.value ? courseId.value : null, days: days.value, max_uses: kind.value === 'teacher' ? 1 : maxUses.value, approval_required: kind.value === 'student' && Boolean(courseId.value) && approval.value })
    secret.value = invitationLink(data.code); secretKind.value = 'invite'; secretExpiry.value = data.expires_at; copied.value = false
    notice.value = `邀请码：${data.code}。请复制链接发送给受邀人。`; clearForm(); page.value = 1; status.value = ''; search.value = ''; appliedSearch.value = ''; await load()
  })
  if (secret.value && !copied.value) { leaveMessage.value = '新链接会替换当前尚未复制的一次性链接。请先复制保存，或确认继续。'; leaveAction.value = action } else action()
}
function prepare(item: Record<string, any>, action: string) {
  if (busy.value || loading.value) return
  const open = () => { confirmAction.value = { ...item, action, kind: tab.value }; reason.value = ''; confirmed.value = false }
  if (action === 'reset' && secret.value && !copied.value) { leaveMessage.value = '当前还有尚未复制的一次性链接。请先保存，或确认继续生成新的链接。'; leaveAction.value = open } else open()
}
async function execute() {
  if (!confirmAction.value || !confirmed.value) return
  const target = confirmAction.value
  await act(async () => {
    if (target.action === 'revoke') await req(`/accounts/invites/${target.id}/revoke`, {})
    else if (target.action === 'reset') {
      const data = await req<{ token: string; expires_at: string }>(`/accounts/recoveries/${target.id}/reset-link`, { reason: reason.value.trim(), identity_verified: confirmed.value })
      secret.value = `${location.origin}/#reset=${encodeURIComponent(data.token)}`; secretKind.value = 'reset'; secretExpiry.value = data.expires_at; copied.value = false
    } else await req(`/accounts/manage/${target.kind}/${target.id}/review`, { approved: target.action === 'approve', reason: reason.value.trim(), confirmed: true })
    confirmAction.value = null; notice.value = target.action === 'reset' ? '重置链接已生成，旧重置链接已失效。请私下发送给已核实身份的本人。' : '操作已完成。'
    await load(); emit('changed')
  })
}
async function savePolicy() {
  if (!policy.value || !policyConfirmed.value || !policyDirty.value) return
  await act(async () => { policy.value = await req('/accounts/registration-policy', { ...policy.value, confirmed: true }, 'PATCH'); policyOriginal.value = JSON.stringify(policy.value); policyConfirmed.value = false; notice.value = '注册设置已保存，新的注册请求立即生效。' })
}
async function copy() { try { await navigator.clipboard.writeText(secret.value); copied.value = true } catch { notice.value = '自动复制不可用，请手动选择上方链接复制。' } }
const date = (value: string) => new Date(value).toLocaleString('zh-CN')
watch(pageSize, () => { page.value = 1; void load() })
onMounted(() => { if (!publishedCourses.value.some(c => c.id === courseId.value)) courseId.value = ''; void load() })
onUnmounted(() => { alive = false; generation++; secret.value = '' })
</script>
<template>
  <DetailDialog :title="isAdmin ? '注册、邀请与账号协助' : '课程邀请与选课审核'" kicker="ACCOUNT ACCESS" :close-disabled="busy" @close="close">
    <template #navigation><nav class="account-tabs" :class="{ 'admin-tabs': isAdmin }" aria-label="账号管理栏目"><button v-for="item in tabs" :key="item.value" type="button" :aria-pressed="tab === item.value" :disabled="busy" @click="select(item.value)">{{ item.label }}</button></nav></template>
    <div class="account-manager" :aria-busy="loading || busy">
      <p v-if="error" class="account-error" role="alert">{{ error }}<button v-if="!busy && !confirmAction" type="button" @click="guarded(() => { policyOriginal = ''; load() })">重新读取</button></p>
      <p v-if="notice" class="account-notice" role="status">{{ notice }}</p>
      <section v-if="secret" class="account-result-link"><strong>{{ secretKind === 'reset' ? '单次密码重置链接' : '邀请链接' }}</strong><small>有效至 {{ date(secretExpiry) }} · 仅本次显示，请妥善保存</small><textarea :value="secret" readonly aria-label="本次生成的链接" /><div class="account-manager-actions"><button type="button" @click="copy">{{ copied ? '已复制' : '复制链接' }}</button><button type="button" :disabled="busy" @click="guarded(() => { secret = ''; notice = '' }, true, false)">隐藏链接</button></div></section>
      <p v-if="loading" role="status"><span class="ui-spinner" aria-hidden="true" />正在读取记录…</p>
      <template v-if="tab === 'invites'">
        <div class="account-manager-header"><div><h3>邀请用户加入平台或课程</h3><p>学生邀请可关联已发布课程；教师邀请仅限一人使用。</p></div><button type="button" :disabled="busy || loading" @click="toggleCreate">{{ showCreate ? '收起新建' : '创建邀请' }}</button></div>
        <form v-if="showCreate" class="account-form" @submit.prevent="create"><fieldset :disabled="busy || loading">
          <label>邀请用途<input v-model="label" required maxlength="120" placeholder="例如：数据结构秋季学期选课" /></label>
          <label v-if="isAdmin">邀请身份<select v-model="kind"><option value="student">学生 / 平台账号</option><option value="teacher">教师（定向邀请）</option></select></label>
          <template v-if="kind === 'student'"><label>查找课程<input v-model="courseSearch" type="search" placeholder="课程名称、代码或学期" /></label><label>关联课程<select v-model="courseId" :required="!isAdmin"><option value="">{{ isAdmin ? '不绑定课程，只创建账号' : '请选择课程' }}</option><option v-for="course in selectableCourses" :key="course.id" :value="course.id">{{ course.title }} · {{ course.code }}{{ course.semester ? ` · ${course.semester}` : '' }}</option></select></label><p v-if="!publishedCourses.length" class="account-muted">暂无可邀请加入的已发布课程。{{ isAdmin ? '仍可创建不绑定课程的平台账号邀请。' : '请先发布课程。' }}</p></template>
          <label>有效天数<input v-model.number="days" type="number" min="1" max="90" required /></label><label>可使用人数<input v-model.number="maxUses" type="number" min="1" :max="kind === 'teacher' ? 1 : 500" :readonly="kind === 'teacher'" required /></label>
          <label v-if="kind === 'student' && courseId" class="account-check"><input v-model="approval" type="checkbox" />加入课程前需要教师审核</label><button type="submit" class="account-primary" :disabled="kind === 'student' && !isAdmin && !courseId"><span v-if="busy" class="ui-spinner" aria-hidden="true" />{{ busy ? '正在创建…' : '创建并显示邀请链接' }}</button>
        </fieldset></form>
      </template>
      <form v-if="tab === 'policy' && policy && !loading" class="account-form" @submit.prevent="savePolicy"><fieldset :disabled="busy"><label>注册范围<select v-model="policy.mode"><option value="closed">关闭新用户注册</option><option value="invite">邀请码注册</option><option value="open">开放学生注册</option></select></label><p class="account-muted">{{ policy.mode === 'closed' ? '新账号暂停注册，包括通过邀请注册；已有账号仍可登录和申请选课。' : policy.mode === 'invite' ? '新用户需使用有效邀请码注册。教师账号需定向邀请或审核申请。' : '学生可直接注册；注册不会自动授予课程访问或管理权限。' }}</p><label class="account-check"><input v-model="policy.teacher_applications" type="checkbox" />允许学生提交教师身份申请（需管理员审核）</label><label class="account-check"><input v-model="policyConfirmed" type="checkbox" :disabled="!policyDirty" required />我已核实注册范围，确认应用此设置</label><div class="account-manager-actions"><button class="account-primary" type="submit" :disabled="!policyConfirmed || !policyDirty">{{ busy ? '正在保存…' : '保存注册设置' }}</button><button type="button" :disabled="busy" @click="guarded(() => { policyOriginal = ''; load() })">重新读取设置</button></div></fieldset></form>
      <template v-if="tab !== 'policy'">
        <form class="account-filters" @submit.prevent="filter"><fieldset :disabled="busy || loading"><label>查找记录<input v-model="search" type="search" maxlength="120" :placeholder="tab === 'invites' ? '邀请用途、课程名称或代码' : '姓名、账号或申请内容'" /></label><label>{{ tab === 'invites' ? '邀请状态' : '申请状态' }}<select v-model="status" @change="filter"><option value="">全部状态</option><option v-for="item in statuses" :key="item[0]" :value="item[0]">{{ item[1] }}</option></select></label><div class="account-manager-actions"><button type="submit">查询</button><button type="button" @click="resetFilter">重置</button><button type="button" @click="load">刷新</button></div></fieldset></form>
        <div v-if="!loading" class="account-manager-list"><article v-for="item in result?.items || []" :key="item.id" class="account-manager-row"><div class="account-record-content"><div class="account-record-title"><strong>{{ tab === 'invites' ? item.label : `${item.display_name} · ${item.username}` }}</strong><span class="account-state" :class="`account-state-${item.state || item.status}`">{{ stateLabel(item) }}</span></div><small v-if="tab === 'invites'">{{ item.kind === 'teacher' ? '教师邀请' : item.course_title || '平台学生邀请' }} · 已使用 {{ item.uses }}/{{ item.max_uses }} 人{{ item.approval_required ? ' · 选课需审核' : '' }}</small><template v-else><small v-if="item.course_title">{{ item.course_title }}</small><p v-if="item.reason">{{ item.reason }}</p><small v-if="tab === 'recoveries'">{{ item.account_exists ? `账号${item.user_active ? '正常' : '已停用'}，需核实申请者身份` : '未匹配到账号，请人工核实' }}<template v-if="item.contact"> · 登记联系信息：{{ item.contact }}</template></small><p v-if="item.approval_blocker" class="account-record-warning">{{ item.approval_blocker }}</p></template><small>{{ tab === 'invites' ? '创建' : '申请' }}时间：{{ date(item.created_at) }}<template v-if="tab === 'invites'"> · 到期：{{ date(item.expires_at) }}</template></small><div v-if="item.review_reason" class="account-review-result"><strong>处理说明</strong><p>{{ item.review_reason }}</p><small v-if="item.reviewed_by">{{ item.reviewed_by }} · {{ date(item.reviewed_at) }}</small></div></div><div class="account-manager-actions"><button v-if="tab === 'invites' && !item.revoked" :disabled="busy" @click="prepare(item, 'revoke')">撤销邀请</button><template v-else-if="tab !== 'invites' && item.status === 'pending'"><button v-if="tab !== 'recoveries'" :disabled="busy || Boolean(item.approval_blocker)" :title="item.approval_blocker || ''" @click="prepare(item, 'approve')">审核通过</button><button v-if="tab === 'recoveries' && item.account_exists && item.user_active" :disabled="busy" @click="prepare(item, 'reset')">核实并生成重置链接</button><button :disabled="busy" @click="prepare(item, 'reject')">不予通过</button></template><button v-else-if="tab === 'recoveries' && item.status === 'resolved' && item.account_exists && item.user_active" :disabled="busy" @click="prepare(item, 'reset')">重新生成重置链接</button></div></article></div>
        <p v-if="!loading && !error && !result?.items.length" class="account-muted" role="status">{{ appliedSearch || status ? '没有符合当前筛选条件的记录，可调整条件后重试。' : '暂无记录。创建邀请或收到申请后将在这里显示。' }}</p>
        <nav v-if="result" class="list-pager" aria-label="账号记录分页"><span>共 {{ result.total }} 条 · 第 {{ page }} / {{ totalPages }} 页</span><label>每页<select v-model.number="pageSize" :disabled="busy || loading" aria-label="账号记录每页条数"><option :value="5">5条</option><option :value="10">10条</option><option :value="20">20条</option><option :value="50">50条</option></select></label><div class="pager-step-buttons"><button :disabled="busy || loading || page <= 1" @click="page--; load()">上一页</button><button :disabled="busy || loading || page >= totalPages" @click="page++; load()">下一页</button></div></nav>
      </template>
    </div>
    <DetailDialog v-if="confirmAction" title="确认账号操作" size="small" :close-disabled="busy" @close="confirmAction = null"><form class="account-form" @submit.prevent="execute"><fieldset :disabled="busy"><p>{{ confirmAction.action === 'reset' ? '请通过已知联系方式核实本人。生成后该用户之前的重置链接立即失效，新链接30分钟内仅可使用一次；不会恢复停用账号。' : confirmAction.action === 'revoke' ? '撤销后，尚未使用的邀请链接将失效；已加入的成员不受影响。' : `将处理 ${confirmAction.display_name || ''}（${confirmAction.username || ''}）的申请。` }}</p><p v-if="error" class="account-error" role="alert">{{ error }}</p><label v-if="confirmAction.action !== 'revoke'">处理说明<textarea v-model="reason" required minlength="8" maxlength="500" rows="3" placeholder="至少8个字，记录核实依据或不通过的原因" /></label><label class="account-check"><input v-model="confirmed" type="checkbox" required />{{ confirmAction.action === 'reset' ? '我已通过可信方式核实本人身份' : '已核实并确认本次操作' }}</label><div class="account-manager-actions"><button type="button" @click="confirmAction = null">取消</button><button class="account-primary" type="submit" :disabled="!confirmed"><span v-if="busy" class="ui-spinner" aria-hidden="true" />{{ busy ? '正在处理…' : '确认执行' }}</button></div></fieldset></form></DetailDialog>
    <DetailDialog v-if="leaveAction" title="继续前请确认" size="small" @close="leaveAction = null"><p class="account-muted">{{ leaveMessage }}</p><template #footer><button type="button" @click="leaveAction = null">返回继续处理</button><button type="button" @click="acceptLeave">放弃并继续</button></template></DetailDialog>
  </DetailDialog>
</template>
<style scoped>
.account-tabs { flex: none; display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 14px 26px 0; }
.account-tabs.admin-tabs { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.account-tabs button { min-width: 0; padding: 9px 5px; font-size: .84rem; }
.account-manager-row > .account-manager-actions { display: flex; max-width: 240px; justify-content: flex-end; }
.account-filters { margin: 16px 0; padding: 14px; border-radius: 14px; background: #f5f7fc; }
.account-filters fieldset { border: 0; padding: 0; margin: 0; display: grid; grid-template-columns: minmax(160px, 1fr) minmax(130px, .5fr) auto; gap: 12px; align-items: end; }
.account-filters label { display: grid; gap: 6px; font-size: .84rem; color: #52627f; }
.account-record-content { min-width: 0; flex: 1; overflow-wrap: anywhere; }
.account-record-title { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.account-record-content > small { display: block; margin-top: 6px; line-height: 1.6; }
.account-state { font-size: .76rem; border-radius: 20px; padding: 3px 9px; background: #edf1f8; color: #596581; white-space: nowrap; }
.account-state-active, .account-state-approved, .account-state-resolved { background: #e6f6ed; color: #24764d; }
.account-state-pending { background: #fff3d9; color: #91620b; }
.account-review-result { padding: 10px 12px; margin-top: 10px; border-radius: 10px; background: #f4f7fb; font-size: .84rem; }
.account-review-result p { margin: 6px 0; white-space: pre-wrap; }
.account-record-warning { color: #91620b; font-size: .84rem; background: #fff7e7; padding: 8px 10px; border-radius: 8px; }
.account-result-link textarea { overflow-wrap: anywhere; }
@media(max-width: 760px) { .account-filters fieldset { grid-template-columns: minmax(0, 1fr) minmax(112px, .65fr); } .account-filters .account-manager-actions { grid-column: 1 / -1; } .account-filters .account-manager-actions button { flex: 1; } }
@media(max-width: 600px) { .account-tabs { margin: 8px 16px 0; gap: 3px; } .account-tabs.admin-tabs { grid-template-columns: repeat(3, minmax(0, 1fr)); } .account-tabs button { font-size: .8rem; min-height: 40px; } .account-manager-row > .account-manager-actions { max-width: none; width: 100%; justify-content: flex-start; } }
@media(max-width: 420px) { .account-filters fieldset { grid-template-columns: minmax(0, 1fr); } }
</style>
