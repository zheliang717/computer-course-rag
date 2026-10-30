<script setup lang="ts">
import { nextTick, onBeforeUnmount, ref, watch } from 'vue'
import type { CalculationReceipt } from '../calculations'
import { calculationFieldLabels } from '../calculations'

const props = defineProps<{ records: CalculationReceipt[]; base: string; token: string }>()
const editing = ref<CalculationReceipt | null>(null)
const draft = ref<Record<string, string>>({})
const result = ref<CalculationReceipt | null>(null)
const error = ref('')
const busy = ref(false)
let controller: AbortController | null = null
let sequence = 0
let manualResultElement: HTMLElement | null = null
function setManualResultElement(element: unknown) {
  manualResultElement = element instanceof HTMLElement ? element : null
}

function closeEditor() {
  sequence += 1
  controller?.abort()
  controller = null
  editing.value = null
  result.value = null
  error.value = ''
  busy.value = false
}

function edit(record: CalculationReceipt) {
  closeEditor()
  editing.value = record
  draft.value = { ...record.arguments }
}

async function recalculate() {
  const record = editing.value
  if (!record || busy.value) return
  const requestSequence = ++sequence
  controller?.abort()
  const current = new AbortController()
  controller = current
  const timeout = setTimeout(() => current.abort(), 10000)
  busy.value = true
  error.value = ''
  result.value = null
  try {
    const args: Record<string, unknown> = { ...draft.value }
    if (record.tool === 'trace_binary_search') {
      args.values = JSON.parse(draft.value.values || '[]'); args.target = Number(draft.value.target)
    } else if (record.tool === 'simulate_page_replacement') {
      args.references = JSON.parse(draft.value.references || '[]'); args.frames = Number(draft.value.frames)
    }
    const response = await fetch(`${props.base}/api/v1/assistant/calculations`, {
      method: 'POST', signal: current.signal,
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${props.token}` },
      body: JSON.stringify({ tool: record.tool, arguments: args }),
    })
    const body = await response.json().catch(() => null)
    if (requestSequence !== sequence) return
    if (!response.ok) throw new Error(typeof body?.detail === 'string' ? body.detail : '暂时无法计算，请核对参数后重试。')
    if (body?.tool !== record.tool || body?.origin !== 'manual' || !['completed', 'error'].includes(body?.status) || !Array.isArray(body?.steps)) {
      throw new Error('计算回执不完整，请重新复算。')
    }
    result.value = body
    await nextTick()
    if (requestSequence === sequence) manualResultElement?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  } catch (cause) {
    if (requestSequence === sequence) error.value = current.signal.aborted ? '本次复算未返回结果，请重新尝试。' : cause instanceof Error ? cause.message : '暂时无法复算。'
  } finally {
    clearTimeout(timeout)
    if (requestSequence === sequence) { busy.value = false; controller = null }
  }
}

watch(() => props.records, closeEditor)
watch(() => props.token, closeEditor)
onBeforeUnmount(closeEditor)
</script>

<template>
  <details v-if="records.length" class="calculation-receipts">
    <summary><span class="calculation-icon" aria-hidden="true">∑</span><strong>工具计算回执</strong><span>{{ records.length }} 项</span><small>查看参数与步骤⌄</small></summary>
    <p class="calculation-boundary">参数由 AI 整理；工具只复算这些参数，不代表整道题或讲解已核实。你可以改参数再次计算。</p>
    <article v-for="(record, index) in records" :key="record.id" class="calculation-record" :data-calculation-id="record.id" :data-calculation-status="record.status">
      <header><h4>{{ record.reference || `计算${index + 1}` }} · {{ record.title }}</h4><span :class="{ 'is-error': record.status === 'error' }">{{ record.status === 'completed' ? '按给定参数计算' : '未完成计算' }}</span></header>
      <dl v-if="Object.keys(record.arguments).length" class="calculation-inputs"><template v-for="(value, key) in record.arguments" :key="key"><dt>{{ calculationFieldLabels[key] || key }}</dt><dd><code>{{ value }}</code></dd></template></dl>
      <ol v-if="record.steps.length" class="calculation-steps"><li v-for="(step, stepIndex) in record.steps" :key="stepIndex"><span>{{ step.label }}</span><code>{{ step.expression }} = <b>{{ step.result }}</b></code></li></ol>
      <div v-if="record.status === 'completed'" class="calculation-result"><small>计算结果</small><strong>{{ record.result }}</strong><span v-if="record.exact_result !== record.result">精确值：{{ record.exact_result }}</span></div>
      <p v-if="record.error" class="calculation-error">{{ record.error }}</p>
      <p class="calculation-boundary">{{ record.boundary }}</p>
      <button v-if="record.tool !== 'unsupported'" type="button" class="calculation-edit-button" :aria-label="`调整计算 ${index + 1} 的参数`" @click="edit(record)">调整参数再算 ›</button>
      <form v-if="editing?.id === record.id" class="calculation-editor" @submit.prevent="recalculate">
        <div class="calculation-editor-heading"><strong>自行复算</strong><button type="button" aria-label="关闭自行复算" @click="closeEditor">×</button></div>
        <label v-for="(_, key) in draft" :key="key">{{ calculationFieldLabels[key] || key }}<input v-model="draft[key]" :disabled="busy" :maxlength="['expression','values','references'].includes(key) ? 1000 : 70" :spellcheck="false" /></label>
        <p>{{ record.tool === 'translate_page_address' ? '整数默认十进制；十六进制带 0x，二进制带 0b。页大小以字节计，物理页号不是物理基址。' : record.tool === 'trace_binary_search' ? '数组填写如 [1,3,5,7]，须升序；目标为整数。' : record.tool === 'simulate_page_replacement' ? '算法填写 LRU、FIFO 或 OPT；页框数1—8；访问序列填写如 [1,2,3,1]。' : '支持数字与 + − * / // % **、括号和整数位运算；^ 是异或，不是乘方。不执行变量、函数或代码。' }}</p>
        <button type="submit" :disabled="busy || Object.values(draft).some(value => !value.trim())">{{ busy ? '计算中…' : '计算' }}</button><small>本地计算，不调用模型，不改动原回答。</small>
        <p v-if="error" class="calculation-error" role="alert">{{ error }}</p>
        <section v-if="result" :ref="setManualResultElement" class="calculation-manual-result" aria-label="你的复算结果" aria-live="polite"><h5>你的复算 · 不改写原记录</h5><p v-if="result.error" class="calculation-error">{{ result.error }}</p><template v-else><ol class="calculation-steps"><li v-for="(step, stepIndex) in result.steps" :key="stepIndex"><span>{{ step.label }}</span><code>{{ step.expression }} = <b>{{ step.result }}</b></code></li></ol><div class="calculation-result"><small>新结果</small><strong>{{ result.result }}</strong><span v-if="result.exact_result !== result.result">精确值：{{ result.exact_result }}</span></div><p class="calculation-boundary">{{ result.boundary }}</p></template></section>
      </form>
    </article>
  </details>
</template>

<style scoped>
.calculation-receipts { background: #f5f9fe; border: 1px solid #d5e2f3; border-radius: 12px; color: #314964; font-size: 12px; margin: 15px 0; overflow: hidden; }
summary { align-items: center; cursor: pointer; display: flex; flex-wrap: wrap; gap: 7px; list-style: none; padding: 12px; }
summary::-webkit-details-marker { display: none; }
summary > small { color: #657d9b; margin-left: auto; }
.calculation-icon { align-items: center; background: #dfeafa; border-radius: 7px; color: #3864a1; display: inline-flex; font-size: 17px; height: 25px; justify-content: center; width: 25px; }
.calculation-receipts[open] > summary { border-bottom: 1px solid #dce7f6; }
.calculation-boundary { color: #677d94; font-size: 11px; line-height: 1.8; margin: 10px 12px; }
.calculation-record { background: #fff; border: 1px solid #dfe8f3; border-radius: 9px; margin: 10px; padding: 12px; }
.calculation-record header { align-items: center; display: flex; flex-wrap: wrap; gap: 7px; justify-content: space-between; }
h4, h5 { font-size: 12px; margin: 0; }
.calculation-record header > span { color: #46755f; font-size: 10px; }
.calculation-record header > span.is-error { color: #a55445; }
.calculation-inputs { column-gap: 10px; display: grid; grid-template-columns: minmax(70px, auto) minmax(0, 1fr); margin: 12px 0; row-gap: 7px; }
dt { color: #738498; }
dd { margin: 0; }
code { color: #315985; font-family: Consolas, monospace; font-size: 12px; overflow-wrap: anywhere; white-space: pre-wrap; }
.calculation-steps { list-style: none; margin: 12px 0; padding: 0; }
.calculation-steps li { background: #f6f8fc; border-radius: 7px; margin: 6px 0; padding: 8px; }
.calculation-steps li > span { color: #738498; display: block; font-size: 10px; margin-bottom: 4px; }
.calculation-result { background: #ecf5f1; border-radius: 8px; color: #245c46; display: grid; gap: 5px; padding: 10px; }
.calculation-result strong { font-family: Consolas, monospace; font-size: 18px; overflow-wrap: anywhere; }
.calculation-result small, .calculation-result span { font-size: 10px; }
.calculation-record > .calculation-boundary { margin: 10px 0; }
.calculation-edit-button { background: #ecf2fb; border: 1px solid #d4e1f1; border-radius: 7px; color: #315985; cursor: pointer; font-size: 11px; padding: 7px 9px; }
.calculation-editor { border-top: 1px solid #e0e8f3; margin-top: 12px; padding-top: 12px; }
.calculation-editor-heading { align-items: center; display: flex; justify-content: space-between; }
.calculation-editor-heading button { background: transparent; color: #64758a; font-size: 20px; padding: 3px 8px; }
.calculation-editor label { color: #5b718b; display: grid; font-size: 11px; gap: 5px; margin: 10px 0; }
.calculation-editor input { background: #fafcff; border: 1px solid #ccdbee; border-radius: 7px; color: #283d57; font: 13px Consolas, monospace; min-width: 0; padding: 10px; width: 100%; }
.calculation-editor p { color: #6f8094; font-size: 11px; line-height: 1.8; margin: 8px 0; }
.calculation-editor button[type=submit] { background: #416fa9; border-radius: 7px; color: #fff; cursor: pointer; font-size: 12px; padding: 8px 14px; }
.calculation-editor > small { color: #718297; display: block; font-size: 10px; margin-top: 8px; }
.calculation-manual-result { border: 1px dashed #93b2d8; border-radius: 8px; margin-top: 12px; padding: 10px; }
.calculation-error { color: #a24f3d !important; font-size: 11px; line-height: 1.8; }
button:disabled { cursor: wait; opacity: .6; }
button:focus-visible, input:focus-visible, summary:focus-visible { outline: 2px solid #5685c0; outline-offset: 3px; }
</style>
