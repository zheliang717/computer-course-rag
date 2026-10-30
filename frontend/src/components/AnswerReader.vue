<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, useId } from 'vue'
import RichText from './RichText.vue'
import CalculationReceipts from './CalculationReceipts.vue'
import { calculationsMarkdown } from '../calculations'
import type { CalculationReceipt } from '../calculations'
import { lockBodyScroll } from '../useBodyScrollLock'

const props = defineProps<{ question: string; content: string; provenance: string; citations: Array<{ document_name: string; page_number: number; document_id?: string | null }>; calculations?: CalculationReceipt[]; base?: string; token?: string }>()
const emit = defineEmits<{ close: []; source: [index: number] }>()
const dialog = ref<HTMLElement | null>(null)
const closeButton = ref<HTMLButtonElement | null>(null)
const fontSize = ref(16)
const copyStatus = ref('')
const titleId = `answer-reader-${useId()}`
const previousFocus = document.activeElement as HTMLElement | null
let releaseScroll: (() => void) | null = null
let disposed = false

function keys(event: KeyboardEvent) {
  if (!dialog.value?.contains(document.activeElement)) return
  if (event.key === 'Escape') { event.preventDefault(); event.stopImmediatePropagation(); emit('close'); return }
  if (event.key !== 'Tab' || !dialog.value) return
  const items = Array.from(dialog.value.querySelectorAll<HTMLElement>('button,a[href],summary,[tabindex]'))
    .filter(item => item.tabIndex >= 0 && !item.hasAttribute('disabled') && item.getClientRects().length)
  const first = items[0], last = items.at(-1)
  if (!first) { event.preventDefault(); dialog.value.focus(); return }
  if (event.shiftKey && (document.activeElement === first || !dialog.value.contains(document.activeElement))) {
    event.preventDefault(); last?.focus()
  } else if (!event.shiftKey && (document.activeElement === last || !dialog.value.contains(document.activeElement))) {
    event.preventDefault(); first.focus()
  }
}
async function copyAnswer(content: string) {
  try { await navigator.clipboard.writeText(content + calculationsMarkdown(props.calculations || [])); if (!disposed) copyStatus.value = '回答原文已复制，包含公式、代码标记和本轮计算回执。' }
  catch { if (!disposed) copyStatus.value = '暂时无法复制，请选中正文后手动复制。' }
}
onMounted(async () => {
  releaseScroll = lockBodyScroll()
  document.addEventListener('keydown', keys, true)
  await nextTick()
  if (!disposed) closeButton.value?.focus()
})
onBeforeUnmount(() => {
  disposed = true
  document.removeEventListener('keydown', keys, true)
  releaseScroll?.()
  if (previousFocus?.isConnected) previousFocus.focus({ preventScroll: true })
})
</script>

<template>
  <Teleport to="body">
    <div class="answer-reader-backdrop" @click.self="emit('close')">
      <section ref="dialog" class="answer-reader" role="dialog" aria-modal="true" :aria-labelledby="titleId" tabindex="-1">
        <header class="answer-reader-header"><div><small>专注阅读 · {{ provenance }}</small><h2 :id="titleId" :title="question">{{ question }}</h2></div><button ref="closeButton" type="button" class="answer-reader-close" aria-label="关闭阅读视图" @click="emit('close')">关闭 <span aria-hidden="true">×</span></button></header>
        <div class="answer-reader-toolbar"><div aria-label="正文字号"><button type="button" aria-label="缩小正文字号" :disabled="fontSize <= 14" @click="fontSize -= 2">A−</button><span>{{ fontSize }}px</span><button type="button" aria-label="放大正文字号" :disabled="fontSize >= 22" @click="fontSize += 2">A＋</button></div><button type="button" @click="copyAnswer(content)">复制原文</button><small>Esc 关闭 · 仅阅读，不会再次调用模型</small></div>
        <p v-if="copyStatus" class="answer-reader-copy" role="status">{{ copyStatus }}</p>
        <div class="answer-reader-scroll">
          <article class="answer-reader-paper" :style="{ '--reader-font-size': `${fontSize}px` }"><RichText :source="content" navigation :evidence-count="citations.length" @evidence="emit('source', $event)" /><CalculationReceipts v-if="calculations?.length" :records="calculations" :base="base || ''" :token="token || ''" /></article>
          <aside v-if="citations.length" class="answer-reader-sources" aria-label="本条回答的资料来源"><div><strong>回到资料核对</strong><small>{{ citations.length }} 条引用 · 仍需自行核对结论</small></div><button v-for="(citation, index) in citations" :key="index" type="button" :disabled="!citation.document_id" @click="emit('source', index)"><b>{{ index + 1 }}</b><span>{{ citation.document_name }}<small>第 {{ citation.page_number }} 页{{ citation.document_id ? '' : ' · 旧记录暂无精确定位' }}</small></span><i aria-hidden="true">↗</i></button></aside>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.answer-reader-backdrop { align-items: center; background: rgba(19,34,62,.55); backdrop-filter: blur(5px); display: flex; inset: 0; justify-content: center; padding: 28px; position: fixed; z-index: 350; }
.answer-reader { background: #f0f4fa; border: 1px solid #d3deee; border-radius: 22px; box-shadow: 0 26px 100px #10213c45; display: flex; flex-direction: column; height: min(900px,calc(100dvh - 56px)); max-width: 1100px; min-height: 0; overflow: hidden; width: 100%; }
.answer-reader-header { align-items: flex-start; background: #fff; border-bottom: 1px solid #e2e9f4; display: flex; flex: none; gap: 20px; justify-content: space-between; padding: 22px 28px 18px; }
.answer-reader-header > div { min-width: 0; }
.answer-reader-header small { color: #7187a4; font-size: 11px; }
.answer-reader-header h2 { -webkit-box-orient: vertical; -webkit-line-clamp: 2; color: #243b5d; display: -webkit-box; font-size: 19px; line-height: 1.6; margin: 6px 0 0; overflow: hidden; overflow-wrap: anywhere; }
.answer-reader-close { align-items: center; background: #edf2fa; border: 1px solid #dce5f1; color: #48617f; display: flex; flex: none; font-size: 12px; gap: 10px; padding: 9px 12px; }
.answer-reader-close span { font-size: 20px; line-height: 1; }
.answer-reader-toolbar { align-items: center; background: #f9fbff; border-bottom: 1px solid #e1e8f3; display: flex; flex: none; flex-wrap: wrap; gap: 12px; padding: 10px 28px; }
.answer-reader-toolbar > div { align-items: center; border-right: 1px solid #dce4ef; display: flex; gap: 8px; padding-inline-end: 12px; }
.answer-reader-toolbar button { background: #e9f0fa; border: 1px solid #dce5f3; color: #365d91; font-size: 11px; padding: 6px 9px; }
.answer-reader-toolbar span { color: #6a7f9b; font-size: 11px; }
.answer-reader-toolbar small { color: #8b9ab0; font-size: 10px; margin-inline-start: auto; }
.answer-reader-scroll { min-height: 0; overflow-y: auto; overscroll-behavior: contain; padding: 24px; scrollbar-gutter: stable; }
.answer-reader-paper { background: #fff; border: 1px solid #e0e7f1; border-radius: 16px; margin: 0 auto; max-width: 880px; padding: 30px 42px; }
.answer-reader-paper :deep(.answer-markdown) { color: #29394f; font-size: var(--reader-font-size); line-height: 1.95; }
.answer-reader-paper :deep(.answer-markdown h1) { font-size: 1.65em; }
.answer-reader-paper :deep(.answer-markdown h2) { border-bottom: 1px solid #e6edf5; font-size: 1.3em; padding-bottom: .5em; }
.answer-reader-paper :deep(.answer-markdown h3) { font-size: 1.12em; }
.answer-reader-paper :deep(.answer-markdown table) { font-size: .9em; max-width: 100%; }
.answer-reader-paper :deep(.answer-markdown .katex-display) { max-width: 100%; overflow-x: auto; overflow-y: hidden; padding-block: 6px; }
.answer-reader-sources { background: #f8fbff; border: 1px solid #dbe5f3; border-radius: 14px; display: grid; gap: 8px; margin: 20px auto 0; max-width: 880px; padding: 20px; }
.answer-reader-sources > div { display: grid; gap: 4px; margin-bottom: 6px; }
.answer-reader-sources strong { color: #3a587f; font-size: 13px; }
.answer-reader-sources small { color: #8496af; font-size: 11px; }
.answer-reader-sources > button { align-items: center; background: #fff; border: 1px solid #e0e8f4; color: #3d5d88; display: flex; font-size: 12px; gap: 12px; padding: 10px 12px; text-align: left; }
.answer-reader-sources b { color: #93a8c5; font-size: 10px; }
.answer-reader-sources span { display: grid; flex: 1; gap: 3px; min-width: 0; overflow-wrap: anywhere; }
.answer-reader-sources i { color: #8ca6ca; font-style: normal; }
.answer-reader-copy { background: #eef8f1; color: #3a7754; flex: none; font-size: 11px; margin: 0; padding: 8px 28px; }
.answer-reader :is(button,summary):focus-visible { outline: 3px solid #9bbcef; outline-offset: 3px; }
@media (max-width: 680px) { .answer-reader-backdrop { padding: 0; } .answer-reader { border: 0; border-radius: 0; height: 100dvh; } .answer-reader-header { gap: 12px; padding: 15px 16px; } .answer-reader-header h2 { font-size: 16px; } .answer-reader-toolbar { gap: 8px; padding: 9px 16px; } .answer-reader-toolbar small { display: none; } .answer-reader-scroll { padding: 12px; } .answer-reader-paper { border-radius: 12px; padding: 20px 18px; } .answer-reader-sources { padding: 14px; } }
</style>
