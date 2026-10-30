<script setup lang="ts">
import { computed, defineAsyncComponent, onBeforeUnmount, ref, watch } from 'vue'
import { questionKey } from '../questionReviews'
import type { QuestionReview, ReviewedChange, ReviewQuestion } from '../questionReviews'
import { calculationsMarkdown } from '../calculations'

const RichText = defineAsyncComponent(() => import('./RichText.vue'))
const CalculationReceipts = defineAsyncComponent(() => import('./CalculationReceipts.vue'))
const ReviewFindingCard = defineAsyncComponent(() => import('./ReviewFindingCard.vue'))
const props = defineProps<{ base: string; token: string; owner: string; draftId: string; index: number; question: ReviewQuestion; saved: boolean; published: boolean; consent: boolean }>()
const emit = defineEmits<{ adopt: [change: ReviewedChange]; source: [id: string, page: number] }>()
const expanded = ref(false), loading = ref(false), posting = ref(false)
const error = ref(''), items = ref<QuestionReview[]>([]), selected = ref<string | null>(null)
const page = ref(1), total = ref(0), requestId = ref('')
const numericQuestion = () => /[0-9]/.test(props.question.stem) && /计算|地址|字节|页|概率|容量|进制|表达式/.test(props.question.stem)
const requireCalculation = ref(numericQuestion())
const explanationDraft = ref('')
const chosen = computed(() => items.value.find(item => item.id === selected.value) || null)
const active = computed(() => items.value.find(item => item.status === 'processing'))
const stale = computed(() => Boolean(chosen.value && (chosen.value.stale || questionKey(chosen.value.question_snapshot) !== questionKey(props.question))))
const unverifiedToolClaim = computed(() => Boolean(chosen.value?.result && !chosen.value.result.calculations.some(item => item.status === 'completed') &&
  /工具.{0,4}(核[算对]|验[证算]|计算|复算)|经.{0,8}工具|\[计算[0-9]+\]/.test(chosen.value.result.summary + chosen.value.result.findings.map(item => item.detail + item.suggestion).join(''))))
const canAdopt = computed(() => Boolean(chosen.value?.result && !stale.value && !unverifiedToolClaim.value && props.saved && !props.published))
const focusedFindings = computed(() => chosen.value?.result?.findings.filter(item => item.assessment !== 'uncertain') || [])
const uncertainFindings = computed(() => chosen.value?.result?.findings.filter(item => item.assessment === 'uncertain') || [])
function suggestionAllowed(field: string) { return Boolean(chosen.value?.result?.suggestion_basis?.[`suggested_${field}`]?.length) }
let sequence = 0, disposed = false, timer: number | null = null
const controllers = new Set<AbortController>()
const root = () => `/api/v1/teaching-drafts/${props.draftId}/question-reviews`
const time = (value: string) => new Date(value).toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
const statusLabel = (value: QuestionReview['status']) => ({ processing: '复核中', completed: '已保存', cancelled: '已停止', failed: '未完成' }[value])
const suggestions = computed(() => {
  const result = chosen.value?.result
  if (!result) return []
  const values: Array<[ReviewedChange['field'], string, string | null]> = [
    ['stem', '题干', result.suggested_stem], ['correct_answer', '参考答案', result.suggested_correct_answer],
    ['explanation', '解析', result.suggested_explanation]]
  return values.filter(entry => typeof entry[2] === 'string' && entry[2] !== (props.question[entry[0]] ?? ''))
    .map(entry => [entry[0], entry[1], entry[2]!] as const)
})

async function call<T>(path: string, init: RequestInit = {}): Promise<T> {
  const controller = new AbortController()
  controllers.add(controller)
  const timeout = window.setTimeout(() => controller.abort(), 20000)
  try {
    const response = await fetch(props.base + path, { ...init, signal: controller.signal,
      headers: { Authorization: `Bearer ${props.token}`, 'Content-Type': 'application/json', ...init.headers } })
    const data = await response.json()
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '本题记录暂不可读，请重试。')
    return data as T
  } finally { clearTimeout(timeout); controllers.delete(controller) }
}
function stopPolling() { if (timer !== null) clearTimeout(timer); timer = null }
function install(state: QuestionReview) {
  const index = items.value.findIndex(item => item.id === state.id)
  if (index < 0) { items.value = [state, ...items.value].slice(0, 5); total.value += 1 }
  else items.value[index] = state
  if (state.status !== 'processing' && state.request_id === requestId.value) requestId.value = ''
}
function poll() {
  stopPolling()
  if (!expanded.value || !active.value || disposed) return
  const id = active.value.id, current = sequence
  timer = window.setTimeout(async () => {
    timer = null
    try {
      const state = await call<QuestionReview>(`${root()}/${id}`)
      if (disposed || current !== sequence) return
      install(state)
      error.value = ''
      poll()
    } catch {
      if (!disposed && current === sequence) error.value = '暂时无法确认处理结果，请点“刷新记录”。不会自动重新生成。'
    }
  }, 1300)
}
async function load(targetPage = page.value) {
  if (loading.value) return
  const current = sequence
  loading.value = true; error.value = ''; stopPolling()
  try {
    const result = await call<{ items: QuestionReview[]; total: number; page: number }>(`${root()}?question_index=${props.index}&page=${targetPage}&page_size=5`)
    if (disposed || current !== sequence) return
    items.value = result.items; total.value = result.total; page.value = result.page
    if (!items.value.some(item => item.id === selected.value)) selected.value = items.value[0]?.id || null
    const known = items.value.find(item => item.request_id === requestId.value)
    if (known && known.status !== 'processing') requestId.value = ''
    poll()
  } catch (reason) { if (!disposed && current === sequence) error.value = reason instanceof Error ? reason.message : '记录读取失败。' }
  finally { if (current === sequence) loading.value = false }
}
async function toggle() {
  expanded.value = !expanded.value
  if (expanded.value) await load()
  else stopPolling()
}
async function start() {
  if (!props.saved || props.published || !props.consent || posting.value || active.value) return
  const current = sequence
  requestId.value ||= crypto.randomUUID()
  posting.value = true; error.value = ''
  try {
    const state = await call<QuestionReview>(root(), { method: 'POST', body: JSON.stringify({
      request_id: requestId.value, question_index: props.index, expected_question: props.question,
      require_calculation: requireCalculation.value, confirm_external_review: true }) })
    if (disposed || current !== sequence) return
    page.value = 1; install(state); selected.value = state.id; await load(1)
  } catch (reason) {
    if (!disposed && current === sequence) error.value = `${reason instanceof Error ? reason.message : '请求未能确认。'} 可刷新记录；再次核对使用同一请求编号，不自动新开生成。`
  } finally { if (current === sequence) posting.value = false }
}
async function cancel() {
  if (!active.value || posting.value) return
  const current = sequence, id = active.value.id
  posting.value = true; error.value = ''
  try {
    const state = await call<QuestionReview>(`${root()}/${id}/cancel`, { method: 'POST' })
    if (disposed || current !== sequence) return
    install(state); poll()
  } catch { if (!disposed && current === sequence) error.value = '停止结果待确认，请刷新记录，不要重复生成。' }
  finally { if (current === sequence) posting.value = false }
}
function adopt(field: ReviewedChange['field'], value: string) {
  if (!canAdopt.value || !chosen.value) return
  emit('adopt', { draftId: props.draftId, index: props.index, original: chosen.value.question_snapshot, field, value })
}
function reset() {
  sequence += 1; stopPolling(); controllers.forEach(controller => controller.abort()); controllers.clear()
  items.value = []; selected.value = null; expanded.value = false; posting.value = false; loading.value = false
  page.value = 1; total.value = 0; error.value = ''; requestId.value = ''
  requireCalculation.value = numericQuestion()
}
watch(() => [props.owner, props.token, props.draftId, props.index], reset)
watch(() => chosen.value?.id, () => { explanationDraft.value = chosen.value?.result?.suggested_explanation || props.question.explanation || '' })
onBeforeUnmount(() => { disposed = true; reset() })
</script>

<template>
  <section class="question-review-panel" :aria-label="`第${index}题AI复核`">
    <button type="button" class="review-toggle" :aria-expanded="expanded" @click="toggle"><span>✦ AI 复核与计算<span>查看建议、复算步骤与保存记录</span></span><b>{{ expanded ? '收起 ↑' : '打开 ›' }}</b></button>
    <div v-if="expanded" class="review-content">
      <div class="review-controls"><button type="button" :disabled="loading || posting" @click="load()">{{ loading ? '读取中…' : '刷新记录' }}</button><button v-if="!active && !published" type="button" class="review-start" :disabled="loading || posting || !saved || !consent" @click="start">{{ posting ? '正在核对请求…' : requestId ? '核对这次请求' : total ? '重新复核本题' : 'AI 复核本题' }}</button></div>
      <label v-if="!published" class="review-numeric"><input v-model="requireCalculation" type="checkbox" :disabled="posting || !!active" />数值题：要求真实计算回执<small>可调整；选中后没有成功回执就不接受完整建议。</small></label>
      <p v-if="!saved" class="review-note">本题有未保存修改，请先保存；旧建议仍可回看，不会套用到新题。</p>
      <p v-else-if="!consent && !published" class="review-note">发起前请在题目列表上方确认在线复核范围。读取记录不调用模型。</p>
      <p v-if="error" class="review-error" role="alert">{{ error }}</p>
      <div v-if="active" class="review-wait" role="status"><i aria-hidden="true"><b /><b /><b /></i><div><strong>{{ active.stage }}</strong><small>完整结果会保存，可关闭页面后回看。</small></div><button type="button" :disabled="posting" @click="cancel">停止复核</button></div>
      <p v-if="!loading && !items.length" class="review-note">尚无本题复核记录。AI不会自动修改题干、答案、解析或成绩。</p>
      <nav v-if="items.length" class="review-history" aria-label="本题复核记录"><button v-for="item in items" :key="item.id" type="button" :class="{ selected: selected === item.id }" :aria-pressed="selected === item.id" @click="selected = item.id">{{ time(item.created_at) }} · {{ statusLabel(item.status) }}{{ item.stale ? ' · 旧版' : '' }}</button></nav>
      <div v-if="total > 5" class="review-pagination"><span>共{{ total }}条 · {{ page }}/{{ Math.ceil(total / 5) }}页</span><button type="button" :disabled="page <= 1 || loading || posting" @click="load(page - 1)">上一页</button><button type="button" :disabled="page * 5 >= total || loading || posting" @click="load(page + 1)">下一页</button></div>
      <template v-if="chosen">
        <p v-if="stale" class="review-warning">这是旧题或旧资料范围的复核，仅供回看，不能直接采用到当前题目。</p>
        <p v-if="!chosen.source_available" class="review-warning">原资料当前不可访问或已变化，结果暂不回读；可按当前题目重新复核。</p>
        <template v-if="chosen.result">
          <p v-if="!chosen.result.calculations.length" class="review-warning">本次没有实际计算回执。模型文字提到“工具核算”不等于已执行计算。</p>
          <p v-if="unverifiedToolClaim" class="review-warning">这份旧建议含未证实的工具描述，不能直接采用；请要求数值核对后重新复核。</p>
          <div class="review-summary"><strong>审阅意见 · 由教师决定处理</strong><p>{{ chosen.result.basis_summary }}</p><small>{{ chosen.result.grounded ? '本次提供了课程片段；请逐条核对支持关系' : '本次没有课程片段；不把通用推测当作教材结论' }}</small></div>
          <ReviewFindingCard v-for="finding in focusedFindings" :key="finding.id" :finding="finding" :base="base" :token="token" :owner="owner" :draft-id="draftId" :review-id="chosen.id" :fingerprint="chosen.question_fingerprint" :stale="stale" @source="(id, page) => emit('source', id, page)" />
          <details v-if="uncertainFindings.length" class="review-uncertain"><summary>待核实设想 · {{ uncertainFindings.length }}条</summary><p class="review-note">这些意见还没有充分对应依据，不作为已发现的题目缺陷；仍可记录你的判断。</p><ReviewFindingCard v-for="finding in uncertainFindings" :key="finding.id" :finding="finding" :base="base" :token="token" :owner="owner" :draft-id="draftId" :review-id="chosen.id" :fingerprint="chosen.question_fingerprint" :stale="stale" @source="(id, page) => emit('source', id, page)" /></details>
          <details class="review-original"><summary>AI原始概述（未逐句核实）</summary><RichText :source="chosen.result.summary" /></details>
          <p v-if="!chosen.result.findings.length" class="review-note">模型未指出具体疑点，不代表题目正确或已经教师确认。</p>
          <CalculationReceipts v-if="chosen.result.calculations.length" :records="chosen.result.calculations" :base="base" :token="token" />
          <details v-if="chosen.result.evidence.length" class="review-sources"><summary>核对课程资料 · {{ chosen.result.evidence.length }}条</summary><button v-for="source in chosen.result.evidence" :key="source.chunk_id" type="button" @click="emit('source', source.document_id, source.page_number)">{{ source.document_name }} · 第{{ source.page_number }}页 ↗</button></details>
          <div v-for="suggestion in suggestions" :key="suggestion[0]" class="review-suggestion"><strong>{{ suggestion[1] }}修改建议</strong><p>原文：{{ chosen.question_snapshot[suggestion[0]] || '未填写' }}</p><RichText :source="suggestion[2]" /><small v-if="!suggestionAllowed(suggestion[0])">此修改尚未关联具体依据，可在下方自行编辑。</small><button type="button"  :disabled="!canAdopt || !suggestionAllowed(suggestion[0])" @click="adopt(suggestion[0], suggestion[2])">填入{{ suggestion[1] }}草稿，待我核对</button></div>
          <details v-if="!published" class="review-suggestion review-editor"><summary>整理可编辑的解析</summary><p>可以编辑自己的解析；带入的是服务器计算步骤，不代表模型疑点已经核实。填入不会保存或发布。</p><button v-if="chosen.result.calculations.some(item => item.status === 'completed')" type="button" :disabled="!canAdopt" @click="explanationDraft = calculationsMarkdown(chosen.result.calculations)">带入本次计算步骤</button><label>解析整理稿（Markdown）<textarea v-model="explanationDraft" rows="7" maxlength="5000" :disabled="!canAdopt" /></label><details v-if="explanationDraft"><summary>查看排版预览</summary><RichText :source="explanationDraft" /></details><button type="button" :disabled="!canAdopt || !explanationDraft.trim() || explanationDraft.length > 5000" @click="adopt('explanation', explanationDraft)">填入解析草稿，待我核对</button></details>
          <p class="review-note">建议与计算回执只作辅助。填入后仍需保存、检查、确认，才可决定是否入库。</p>
        </template>
        <p v-else-if="chosen.status === 'failed' || chosen.status === 'cancelled'" class="review-note">{{ chosen.message }}</p>
        <details class="review-original"><summary>查看本次审核的原题</summary><p>{{ chosen.question_snapshot.stem }}</p><p v-for="option in chosen.question_snapshot.options" :key="option">{{ option }}</p><p>原参考答案：{{ chosen.question_snapshot.correct_answer }}</p><p>原解析：{{ chosen.question_snapshot.explanation || '未填写' }}</p></details>
      </template>
    </div>
  </section>
</template>

<style scoped>
.question-review-panel { border: 1px solid #d6e4f5; border-radius: 14px; margin-top: 16px; overflow: hidden; }
.review-toggle { align-items: center; background: #eef5ff; border: 0; border-radius: 0; color: #375782; display: flex; gap: 16px; justify-content: space-between; padding: 14px 16px; text-align: left; width: 100%; }
.review-toggle > span { font-size: 13px; font-weight: 650; }.review-toggle span span { color: #7388a4; display: block; font-size: 11px; font-weight: 400; margin: 5px 0 0 16px; }.review-toggle b { flex: none; font-size: 11px; }
.review-content { background: #fbfdff; padding: 16px; }.review-controls,.review-pagination { align-items: center; display: flex; flex-wrap: wrap; gap: 9px; }
.review-controls button,.review-pagination button,.review-wait button,.review-suggestion button { background: #eaf1fc; border: 1px solid #d7e4f7; color: #365b91; font-size: 12px; padding: 8px 12px; }.review-controls .review-start { background: #4968bd; border-color: #4968bd; color: #fff; margin-inline-start: auto; }
.review-note,.review-pagination span { color: #7588a1; font-size: 11px; line-height: 1.8; }.review-error,.review-warning { background: #fff4e4; border-radius: 9px; color: #8e6426; font-size: 12px; line-height: 1.8; padding: 10px 12px; }
.review-numeric { align-items: center; color: #516f96; display: flex; flex-wrap: wrap; font-size: 11px; gap: 7px; margin-top: 12px; }.review-numeric input { accent-color: #566fc0; width: auto; }.review-numeric small { color: #8395ac; font-size: 10px; }
.review-summary > p { color: #48668c; font-size: 12px; line-height: 1.9; }.review-uncertain { background: #fffbf3; border: 1px solid #eadfc8; border-radius: 10px; margin: 14px 0; padding: 12px; }.review-uncertain > summary { color: #9a8057; cursor: pointer; font-size: 12px; font-weight: 600; }.review-suggestion > small { color: #a08e6a; display: block; font-size: 11px; line-height: 1.8; margin: 10px 0; }
.review-editor summary { color: #426591; cursor: pointer; font-size: 12px; padding: 4px 0; }.review-editor label { color: #667e9d; display: grid; font-size: 11px; gap: 8px; margin: 12px 0; }.review-editor textarea { box-sizing: border-box; font-family: inherit; font-size: 12px; line-height: 1.7; resize: vertical; width: 100%; }.review-editor > button { margin-top: 10px; }
.review-wait { align-items: center; background: #edf4ff; border-radius: 10px; display: flex; flex-wrap: wrap; gap: 12px; margin-top: 12px; padding: 14px; }.review-wait > div { flex: 1; }.review-wait strong { color: #3c5f93; font-size: 12px; }.review-wait small { color: #7187a5; display: block; font-size: 10px; margin-top: 6px; }.review-wait i { display: flex; gap: 3px; }.review-wait b { animation: review-pulse 1.2s infinite; background: #718cda; border-radius: 50%; height: 5px; width: 5px; }.review-wait b:nth-child(2) { animation-delay: .2s; }.review-wait b:nth-child(3) { animation-delay: .4s; }
.review-history { display: flex; flex-wrap: wrap; gap: 7px; margin: 16px 0; }.review-history button { background: #fff; border: 1px solid #dfe8f5; color: #7a8da7; font-size: 10px; padding: 7px 9px; }.review-history .selected { background: #e8efff; border-color: #a7bdea; color: #375baa; }
.review-summary { background: #fff; border: 1px solid #e2eaf5; border-radius: 12px; margin: 14px 0; padding: 15px; }.review-summary > strong,.review-suggestion > strong { color: #385679; font-size: 13px; }.review-summary > small { color: #8193ac; display: block; font-size: 10px; margin: 5px 0 10px; }
.review-finding { align-items: flex-start; border-bottom: 1px solid #e7edf6; display: flex; gap: 12px; padding: 12px 0; }.review-finding > b { background: #eff2fa; border-radius: 6px; color: #687c9b; flex: none; font-size: 10px; padding: 5px 7px; }.review-finding > div { min-width: 0; }.review-finding small { color: #6f87a6; font-size: 11px; line-height: 1.8; }
.review-sources,.review-original { border-top: 1px solid #e2eaf4; color: #7186a2; font-size: 11px; margin-top: 14px; padding-top: 12px; }.review-sources summary,.review-original summary { cursor: pointer; padding: 5px 0; }.review-sources button { background: #f0f5fc; border: 0; color: #4e719e; display: block; font-size: 11px; margin: 6px 0; padding: 9px 12px; text-align: left; width: 100%; }.review-original p { overflow-wrap: anywhere; white-space: pre-wrap; }
.review-suggestion { background: #f1f6ff; border: 1px solid #d9e6fc; border-radius: 12px; margin-top: 14px; padding: 14px; }.review-suggestion > p { color: #8a99b0; font-size: 11px; line-height: 1.8; max-height: 120px; overflow-y: auto; white-space: pre-wrap; }.review-content :deep(.answer-markdown) { font-size: 13px; line-height: 1.8; }.review-content button:disabled { cursor: not-allowed; opacity: .5; }
@keyframes review-pulse { 0%,80%,100% { opacity: .3; transform: translateY(0); } 40% { opacity: 1; transform: translateY(-3px); } }
@media (prefers-reduced-motion: reduce) { .review-wait b { animation: none; } }
@media (max-width: 600px) { .review-content { padding: 12px; }.review-finding { gap: 8px; }.review-wait > div { min-width: 160px; } }
</style>
