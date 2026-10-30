<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
const props = defineProps<{ base: string; token: string; owner: string; draftId: string; reviewId: string; findingId: string; fingerprint: string; stale: boolean }>()
type Decision = 'follow_up' | 'dismissed' | 'needs_check'
type Entry = { id: string; actor_name: string; decision: Decision; reason: string; created_at: string }
const opened = ref(false), loading = ref(false), saving = ref(false), error = ref(''), message = ref('')
const decision = ref<Decision>('needs_check'), reason = ref(''), page = ref(1), total = ref(0), records = ref<Entry[]>([])
const options: Array<{ id: Decision; label: string }> = [{ id: 'follow_up', label: '需要处理' }, { id: 'dismissed', label: '暂不采纳' }, { id: 'needs_check', label: '待核对' }]
const label = (value: Decision) => options.find(option => option.id === value)?.label || value
let pending: Record<string, string> | null = null, sequence = 0, disposed = false
const controllers = new Set<AbortController>()
const endpoint = () => `/api/v1/teaching-drafts/${props.draftId}/question-reviews/${props.reviewId}/decisions`
async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController(); controllers.add(controller)
  const timeout = window.setTimeout(() => controller.abort(), 15000)
  try {
    const response = await fetch(props.base + path, { ...init, signal: controller.signal,
      headers: { Authorization: `Bearer ${props.token}`, 'Content-Type': 'application/json' } })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '记录暂不可用，请稍后重试。')
    return data as T
  } finally { clearTimeout(timeout); controllers.delete(controller) }
}
async function load(target = page.value) {
  if (loading.value) return
  const current = sequence; loading.value = true; error.value = ''
  try {
    const result = await api<{ items: Entry[]; total: number; page: number }>(`${endpoint()}?finding_id=${props.findingId}&page=${target}&page_size=5`)
    if (disposed || sequence !== current) return
    records.value = result.items; total.value = result.total; page.value = result.page
  } catch (value) { if (!disposed && sequence === current) error.value = value instanceof Error ? value.message : '处理记录读取失败。' }
  finally { if (sequence === current) loading.value = false }
}
async function toggle() { opened.value = !opened.value; if (opened.value) await load() }
async function save() {
  if (saving.value || props.stale || (!pending && reason.value.trim().length < 5)) return
  pending ||= { request_id: crypto.randomUUID(), finding_id: props.findingId,
    expected_question_fingerprint: props.fingerprint, decision: decision.value, reason: reason.value.trim() }
  const current = sequence; saving.value = true; error.value = ''; message.value = ''
  try {
    await api<Entry>(endpoint(), { method: 'POST', body: JSON.stringify(pending) })
    if (disposed || sequence !== current) return
    pending = null; message.value = '判断已记录。原题、AI意见和成绩没有改变。'; reason.value = ''; await load(1)
  } catch (value) { if (!disposed && sequence === current) error.value = `${value instanceof Error ? value.message : '保存结果待确认。'} 再次核对沿用本次编号，不重复新增。` }
  finally { if (sequence === current) saving.value = false }
}
function reset() {
  sequence += 1; controllers.forEach(controller => controller.abort()); controllers.clear()
  opened.value = false; loading.value = false; saving.value = false; pending = null
  error.value = ''; message.value = ''; records.value = []; total.value = 0; page.value = 1; reason.value = ''; decision.value = 'needs_check'
}
watch(() => [props.owner, props.token, props.draftId, props.reviewId, props.findingId], reset)
onBeforeUnmount(() => { disposed = true; reset() })
</script>

<template>
  <section class="finding-decision" aria-label="教师处理记录">
    <button type="button" class="decision-toggle" :aria-expanded="opened" @click="toggle">{{ opened ? '收起教师判断 ↑' : '查看 / 记录教师判断 ›' }}</button>
    <div v-if="opened" class="decision-body">
      <p>记录你对这条意见的处理，不等于确认题目正确，也不会自动改题。</p>
      <p v-if="stale" class="decision-message">题目已变化，当前只能回看原版本记录。</p>
      <div class="decision-options" role="group" aria-label="我的判断"><button v-for="option in options" :key="option.id" type="button" :aria-pressed="decision === option.id" :disabled="stale || saving || !!pending" @click="decision = option.id">{{ option.label }}</button></div>
      <label>判断理由<textarea v-model="reason" rows="3" maxlength="500" :disabled="stale || saving || !!pending" placeholder="说明你核对了什么，以及是否需要修改…" /></label>
      <div class="decision-actions"><button type="button" :disabled="stale || saving || (!pending && reason.trim().length < 5)" @click="save">{{ saving ? '保存中…' : pending ? '核对这次保存' : '保存我的判断' }}</button><button type="button" :disabled="loading || saving" @click="load()">刷新记录</button></div>
      <p v-if="message" class="decision-message" role="status">{{ message }}</p><p v-if="error" class="decision-error" role="alert">{{ error }}</p>
      <ol v-if="records.length" class="decision-history"><li v-for="entry in records" :key="entry.id"><div><b>{{ label(entry.decision) }}</b><small>{{ entry.actor_name }} · {{ new Date(entry.created_at).toLocaleString('zh-CN') }}</small></div><p>{{ entry.reason }}</p></li></ol>
      <p v-else-if="!loading">尚无已读取的处理记录。</p>
      <nav v-if="total > 5" class="decision-pages" aria-label="处理记录分页"><span>{{ page }}/{{ Math.ceil(total / 5) }}页 · 共{{ total }}条</span><button type="button" :disabled="page <= 1 || loading || saving" @click="load(page - 1)">上一页</button><button type="button" :disabled="page * 5 >= total || loading || saving" @click="load(page + 1)">下一页</button></nav>
    </div>
  </section>
</template>

<style scoped>
.finding-decision { border-top: 1px solid #e2eaf5; margin-top: 13px; padding-top: 9px; }.decision-toggle { background: transparent; border: 0; color: #4c70a1; font-size: 11px; padding: 5px 0; }.decision-body { background: #f5f8fd; border-radius: 10px; margin-top: 8px; padding: 13px; }.decision-body p { color: #798ca5; font-size: 11px; line-height: 1.8; margin: 6px 0 12px; }.decision-options,.decision-actions,.decision-pages { display: flex; flex-wrap: wrap; gap: 7px; }.decision-options button,.decision-actions button,.decision-pages button { background: #fff; border: 1px solid #d8e4f3; color: #5d789e; font-size: 11px; padding: 7px 10px; }.decision-options button[aria-pressed=true] { background: #e4edff; border-color: #9db9e7; color: #3b60a2; }.decision-body label { color: #71859f; display: grid; font-size: 11px; gap: 7px; margin: 12px 0; }.decision-body textarea { box-sizing: border-box; font-family: inherit; font-size: 12px; line-height: 1.8; resize: vertical; width: 100%; }.decision-actions button:first-child { background: #4f6fb7; color: #fff; }.decision-history { list-style: none; margin: 14px 0 0; padding: 0; }.decision-history li { background: #fff; border: 1px solid #e3ebf6; border-radius: 8px; margin-top: 7px; padding: 10px; }.decision-history li div { align-items: center; display: flex; flex-wrap: wrap; gap: 10px; }.decision-history b { color: #526f99; font-size: 11px; }.decision-history small { color: #95a2b5; font-size: 10px; }.decision-history li p { color: #667b98; margin-bottom: 0; white-space: pre-wrap; }.decision-body .decision-message { color: #3c7b74; }.decision-body .decision-error { color: #a56b3f; }.decision-pages { align-items: center; color: #8b9db4; font-size: 10px; margin-top: 10px; }button:disabled { cursor: not-allowed; opacity: .5; }
</style>
