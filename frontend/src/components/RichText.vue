<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, useId, watch } from 'vue'
import { loadMarkdown, markdownState, renderMarkdown } from '../useMarkdown'

const props = withDefaults(defineProps<{ source: string; streaming?: boolean; navigation?: boolean; tools?: boolean; presentation?: boolean; outlineLabel?: string; evidenceCount?: number }>(), { streaming: false, navigation: false, tools: true, presentation: false, outlineLabel: '本条回答目录', evidenceCount: 0 })
const emit = defineEmits<{ layout: []; evidence: [index: number] }>()
const staged = ref(props.source)
const content = ref<HTMLElement | null>(null)
const headings = ref<Array<{ label: string; level: number }>>([])
const feedback = ref('')
const contentId = `answer-text-${useId()}`
let nodes: HTMLElement[] = []
let renderTimer: ReturnType<typeof setTimeout> | undefined
let copyTimer: ReturnType<typeof setTimeout> | undefined
let sequence = 0
let disposed = false

watch([() => props.source, () => props.streaming], () => {
  if (!props.streaming) {
    if (renderTimer) clearTimeout(renderTimer)
    renderTimer = undefined
    staged.value = props.source
  } else if (!renderTimer) {
    renderTimer = setTimeout(() => { renderTimer = undefined; staged.value = props.source }, 120)
  }
})
const html = computed(() => renderMarkdown(staged.value, { interactive: props.tools, streaming: props.streaming, evidenceCount: props.evidenceCount }))
const formulaUnavailable = computed(() => html.value.includes('data-math-unavailable'))

watch([html, () => props.navigation, () => props.presentation], async () => {
  const current = ++sequence
  await nextTick()
  if (disposed || current !== sequence) return
  nodes = Array.from(content.value?.querySelectorAll<HTMLElement>('h1, h2, h3') || [])
  headings.value = nodes.map((node, index) => {
    node.id = `${contentId}-section-${index}`
    node.tabIndex = -1
    return { label: node.textContent || `第 ${index + 1} 节`, level: Number(node.tagName.slice(1)) }
  })
  content.value?.querySelectorAll('.answer-opening').forEach(node => node.classList.remove('answer-opening'))
  if (props.presentation) {
    const opening = Array.from(content.value?.children || []).find(node =>
      node.tagName === 'P' && (node.textContent?.trim().length || 0) >= 16 && (node.textContent?.length || 0) <= 600)
    opening?.classList.add('answer-opening')
  }
  emit('layout')
}, { immediate: true, flush: 'post' })

function jump(index: number) {
  const node = nodes[index]
  if (!node) return
  node.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
  node.focus({ preventScroll: true })
}

async function copyCode(event: MouseEvent) {
  const evidence = (event.target as Element)?.closest<HTMLButtonElement>('button[data-evidence-index]')
  if (evidence && content.value?.contains(evidence)) {
    const index = Number(evidence.dataset.evidenceIndex)
    if (Number.isInteger(index) && index >= 0 && index < props.evidenceCount) emit('evidence', index)
    return
  }
  const button = (event.target as Element)?.closest<HTMLButtonElement>('button[data-copy-code]')
  if (!button || !content.value?.contains(button)) return
  const code = button.closest('figure')?.querySelector('code')?.textContent
  if (code === undefined || code === null) return
  try {
    await navigator.clipboard.writeText(code)
    if (disposed || !content.value?.contains(button)) return
    feedback.value = '代码已复制，可粘贴到编辑器。'
    button.textContent = '已复制'
    if (copyTimer) clearTimeout(copyTimer)
    copyTimer = setTimeout(() => {
      content.value?.querySelectorAll('button[data-copy-code]').forEach(item => { item.textContent = '复制代码' })
      feedback.value = ''
    }, 2200)
  } catch { if (!disposed) feedback.value = '暂时无法复制，请选中代码后手动复制。' }
}

async function retryFormulas() {
  const module = await import('../answerRendering')
  await module.loadFormulas()
}
onBeforeUnmount(() => {
  disposed = true; sequence += 1
  if (renderTimer) clearTimeout(renderTimer)
  if (copyTimer) clearTimeout(copyTimer)
})
</script>

<template>
  <div class="rich-answer" :class="{ 'answer-teaching-layout': presentation }" :aria-busy="streaming">
    <details v-if="navigation && !streaming && headings.length >= (presentation ? 2 : 3)" class="answer-outline" @toggle="emit('layout')">
      <summary>{{ presentation ? '按重点跳读' : outlineLabel }} <span>{{ headings.length }} 节</span></summary>
      <nav aria-label="回答章节目录"><button v-for="(heading, index) in headings" :key="index" type="button" :aria-controls="`${contentId}-section-${index}`" :class="{ subordinate: heading.level > 2 }" @click="jump(index)"><span>{{ index + 1 }}</span>{{ heading.label }}</button></nav>
    </details>
    <div v-if="markdownState === 'loading'" class="formatting-status" role="status">正在排版，原文已保留…</div>
    <div v-else-if="markdownState === 'failed'" class="formatting-status" role="status">排版资源暂不可用，以下为原文。<button type="button" @click="loadMarkdown">重新排版</button></div>
    <div :id="contentId" ref="content" class="answer-markdown" :class="{ 'is-streaming': streaming }" aria-live="off" @click="copyCode" v-html="html" />
    <div v-if="formulaUnavailable" class="formatting-status">公式暂以原表达式显示。<button type="button" @click="retryFormulas">重试公式排版</button></div>
    <p v-if="feedback" class="answer-copy-feedback" role="status">{{ feedback }}</p>
  </div>
</template>

<style>
.rich-answer { min-width: 0; }
.rich-answer .answer-markdown { margin-top: 0; }
.rich-answer .answer-markdown :is(h1,h2,h3) { scroll-margin-block-start: 22px; }
.rich-answer .answer-markdown :is(h1,h2,h3):focus { outline: 2px solid #94b6ef; outline-offset: 7px; border-radius: 3px; }
.answer-outline { background: #f4f7fc; border: 1px solid #e0e7f2; border-radius: 12px; margin-bottom: 20px; }
.answer-outline summary { color: #345279; cursor: pointer; font-size: 12px; font-weight: 700; padding: 12px 14px; }
.answer-outline summary > span { color: #8293ac; float: right; font-size: 11px; font-weight: 400; }
.answer-outline nav { display: grid; gap: 4px; padding: 0 10px 10px; }
.answer-outline nav button { align-items: baseline; background: transparent; border-radius: 7px; color: #455c79; display: flex; font-size: 12px; gap: 9px; line-height: 1.6; padding: 6px 9px; text-align: left; }
.answer-outline nav button:hover { background: #e6effc; color: #1f5bae; }
.answer-outline nav button.subordinate { padding-inline-start: 18px; }
.answer-outline nav button > span { color: #94a8c3; flex: none; font-size: 10px; min-width: 17px; }
.answer-outline :is(button,summary):focus-visible, .answer-code button:focus-visible { outline: 3px solid #9dbced; outline-offset: 2px; }
.answer-markdown .answer-code { background: #172033; border: 1px solid #2c3b53; border-radius: 12px; margin: 1.1em 0; overflow: hidden; min-width: 0; }
.answer-markdown .answer-code figcaption { align-items: center; background: #202e45; color: #aabbd2; display: flex; font-family: 'Cascadia Code',Consolas,monospace; font-size: 11px; justify-content: space-between; padding: 8px 12px; }
.answer-markdown .answer-code button { background: #344661; border: 1px solid #4b5c76; border-radius: 6px; color: #e7eef9; font-family: inherit; font-size: 11px; line-height: 1.5; padding: 5px 8px; }
.answer-markdown .answer-code pre { border-radius: 0; margin: 0; padding: 14px 16px; text-align: left; }
.answer-markdown .answer-plain-text { background: #f7f9fd; color: #334155; font-family: inherit; white-space: pre-wrap; }
.answer-markdown .formula-pending { background: #f2f5fa; border-radius: 4px; color: #5c6c83; font-family: 'Cascadia Code',Consolas,monospace; overflow-wrap: anywhere; padding: 2px 4px; }
.answer-markdown div.formula-pending { margin: 1em 0; padding: 10px 12px; text-align: center; }
.answer-image-label { color: #6b7d96; font-size: .85em; }
.answer-markdown .inline-evidence { display: inline-flex; align-items: center; margin: 0 3px; padding: 1px 7px; min-height: 24px; border: 1px solid #c7dafa; border-radius: 7px; background: #eef5ff; color: #2e62a5; font-size: .72em; vertical-align: baseline; white-space: nowrap; cursor: pointer; }
.answer-markdown .inline-evidence:focus-visible { outline: 3px solid #9dbced; outline-offset: 2px; }
.formatting-status, .answer-copy-feedback { color: #617c9c; font-size: 11px; line-height: 1.8; margin: 8px 0; }
.formatting-status button { background: #e9f0fb; color: #315d94; font-size: 11px; margin-inline-start: 8px; padding: 4px 7px; }
.answer-copy-feedback { color: #28735a; }
</style>
