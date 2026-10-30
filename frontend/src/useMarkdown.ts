import { shallowRef } from 'vue'
import type { RenderOptions } from './answerRendering'

type Renderer = (source: string, options?: RenderOptions) => string
const renderer = shallowRef<Renderer | null>(null)
export const markdownState = shallowRef<'idle' | 'loading' | 'ready' | 'failed'>('idle')
let pending: Promise<void> | null = null

export function escapeText(value: string) {
  return value.replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]!))
}

export function loadMarkdown() {
  if (renderer.value) return Promise.resolve()
  if (pending) return pending
  markdownState.value = 'loading'
  pending = import('./answerRendering').then(module => {
    renderer.value = module.renderMarkdown
    markdownState.value = 'ready'
  }).catch(() => { markdownState.value = 'failed' }).finally(() => { pending = null })
  return pending
}

/** The original answer stays available even when an optional formatting chunk is unavailable. */
export function renderMarkdown(source: string, options?: RenderOptions): string {
  if (renderer.value) return renderer.value(source, options)
  if (source && markdownState.value !== 'failed') void loadMarkdown()
  return `<pre class="answer-plain-text">${escapeText(source)}</pre>`
}
