<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import { acknowledgeAnswer, pendingAnswer, readAnswerReceipt } from '../answerRequests'
import type { AnswerReceipt, AnswerRequestSurface } from '../answerRequests'

const props = defineProps<{ base: string; token: string; owner: string; surface: AnswerRequestSurface; busy: boolean; knownIds?: string[] }>()
const emit = defineEmits<{ restore: [receipt: AnswerReceipt] }>()
const receipt = ref<AnswerReceipt | null>(null)
const pendingId = ref('')
const loading = ref(false)
const error = ref('')
const dismissed = ref(false)
let controller: AbortController | null = null
let sequence = 0
async function read() {
  const current = ++sequence
  controller?.abort()
  controller = null
  loading.value = false
  const id = pendingAnswer(props.owner, props.surface)?.id
  if (id !== pendingId.value) receipt.value = null
  if (!id) { pendingId.value = ''; return }
  pendingId.value = id
  if (props.knownIds?.includes(id)) return
  const activeController = new AbortController()
  controller = activeController
  loading.value = true
  error.value = ''
  try {
    const value = await readAnswerReceipt(props.base, props.token, id, activeController.signal)
    if (current === sequence) receipt.value = value
  } catch (cause) { if (current === sequence && !activeController.signal.aborted) error.value = cause instanceof Error ? cause.message : '暂时无法读取上次请求。' }
  finally { if (current === sequence) loading.value = false }
}
function dismiss() { acknowledgeAnswer(props.owner, props.surface, pendingId.value); dismissed.value = true }
watch([() => props.owner, () => props.token, () => props.busy], () => {
  if (props.owner && props.token && !props.busy) { dismissed.value = false; void read() }
}, { immediate: true })
onBeforeUnmount(() => { sequence += 1; controller?.abort() })
</script>

<template>
  <section v-if="pendingId && !dismissed && !busy && !knownIds?.includes(pendingId)" class="answer-recovery" aria-label="上次回答请求" :aria-busy="loading">
    <strong>{{ loading ? '正在核对上次请求…' : receipt?.status === 'completed' ? '上次回答已完整保存' : receipt?.status === 'in_progress' ? '上次请求仍在处理' : receipt?.status === 'cancelled' ? '上次请求已停止' : receipt?.status === 'failed' ? '上次请求未完成' : '上次请求的结果尚未确认' }}</strong>
    <p v-if="receipt?.question">{{ receipt.question.slice(0, 90) }}{{ receipt.question.length > 90 ? '…' : '' }}</p><p v-if="error" role="alert">{{ error }}</p>
    <div><button v-if="receipt" type="button" :disabled="loading" @click="emit('restore', receipt); dismissed = true">{{ receipt.status === 'completed' ? '恢复回答' : '打开原问题' }}</button><button type="button" class="recovery-light" :disabled="loading" @click="read">重新核对</button><button type="button" class="recovery-light" :disabled="loading" @click="dismiss">暂不处理</button></div>
    <small>核对和恢复不会再次调用模型；未确认前请勿重复发送同一问题。</small>
  </section>
</template>

<style scoped>
.answer-recovery { border: 1px solid #d5e2f3; border-radius: 12px; background: #eff5ff; padding: 13px 15px; margin: 10px 0; min-width: 0; }
strong { font-size: 12px; color: #5575a0; }
p { font-size: 11px; color: #7e94b1; line-height: 1.8; margin: 8px 0; overflow-wrap: anywhere; }
div { display: flex; gap: 7px; flex-wrap: wrap; }
button { font-size: 11px; line-height: 1.65; padding: 7px 10px; }
.recovery-light { color: #7a93b4; background: #e4edfb; }
small { display: block; font-size: 10px; line-height: 1.8; color: #9aabc1; margin-top: 8px; }
button:focus-visible { outline: 3px solid #a3c1e9; outline-offset: 2px; }
</style>
