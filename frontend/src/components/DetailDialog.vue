<script setup lang="ts">
import { nextTick, onMounted, onBeforeUnmount, ref, useId, watch } from 'vue'
import { lockBodyScroll } from '../useBodyScrollLock'
const props = withDefaults(defineProps<{ title: string; kicker?: string; description?: string | null; viewKey?: string; closeDisabled?: boolean; closeLabel?: string; initialScrollTop?: number; size?: 'normal' | 'small'; alert?: boolean }>(), { closeLabel: '关闭窗口', initialScrollTop: 0, size: 'normal', alert: false })
const emit = defineEmits<{ close: []; scroll: [top: number] }>()
const dialog = ref<HTMLDialogElement | null>(null)
const body = ref<HTMLElement | null>(null)
watch(() => props.viewKey, () => { if (body.value) body.value.scrollTop = 0 })
const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
const titleId = `detail-${useId()}`
let releaseScroll: (() => void) | null = null
const pointerOnBackdrop = ref(false)
function trapFocus(event: KeyboardEvent) {
  if (event.key !== 'Tab' || !dialog.value) return
  const items = Array.from(dialog.value.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [href], [tabindex="0"], summary')).filter(item => item.getClientRects().length > 0)
  const first = items[0], last = items.at(-1)
  if (!first) { event.preventDefault(); dialog.value.focus(); return }
  if (event.shiftKey && (document.activeElement === first || document.activeElement === dialog.value)) { event.preventDefault(); last?.focus({ preventScroll: true }) }
  else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus({ preventScroll: true }) }
}
onMounted(async () => {
  releaseScroll = lockBodyScroll()
  dialog.value?.showModal()
  await nextTick()
  if (body.value) body.value.scrollTop = props.initialScrollTop
})
onBeforeUnmount(() => {
  dialog.value?.close()
  releaseScroll?.()
  const topDialog = Array.from(document.querySelectorAll('dialog[open]')).at(-1)
  if (previousFocus?.isConnected && previousFocus.getClientRects().length && (!topDialog || topDialog.contains(previousFocus))) previousFocus.focus({ preventScroll: true })
})
defineExpose({ scrollTo: (top: number) => { if (body.value) body.value.scrollTop = top } })
</script>

<template>
  <Teleport to="body">
    <dialog ref="dialog" class="detail-dialog" :role="alert ? 'alertdialog' : 'dialog'" :aria-labelledby="titleId" @keydown="trapFocus" @cancel.prevent="!closeDisabled && emit('close')" @pointerdown="pointerOnBackdrop = $event.target === $event.currentTarget" @click="!closeDisabled && pointerOnBackdrop && $event.target === $event.currentTarget && emit('close')">
      <section class="detail-dialog-frame" :class="{ 'is-small': size === 'small' }">
        <header class="detail-dialog-heading"><div><p v-if="kicker" class="section-kicker">{{ kicker }}</p><h2 :id="titleId">{{ title }}</h2><p v-if="description" class="detail-description">{{ description }}</p></div><button type="button" class="detail-close" :disabled="closeDisabled" autofocus :aria-label="closeLabel" @click="emit('close')">×</button></header>
        <slot name="navigation" />
        <div ref="body" class="detail-dialog-body" tabindex="0" role="region" :aria-label="`${title}内容`" @scroll.passive="emit('scroll', ($event.target as HTMLElement).scrollTop)"><slot /></div>
        <footer v-if="$slots.footer" class="detail-dialog-footer"><slot name="footer" /></footer>
      </section>
    </dialog>
  </Teleport>
</template>

<style scoped>
.detail-dialog { background: transparent; border: 0; color: #263e5b; height: 100dvh; margin: auto; max-height: 100dvh; max-width: 100vw; outline: none; overflow: hidden; padding: 20px; width: 100vw; }.detail-dialog[open] { align-items: center; display: flex; justify-content: center; }.detail-dialog::backdrop { background: #10213c85; backdrop-filter: blur(3px); }.detail-dialog-frame { background: white; border: 1px solid #e0e8f2; border-radius: 20px; box-shadow: 0 30px 100px #0b1f4240; display: flex; flex-direction: column; max-height: min(92dvh,960px); max-width: 1080px; min-height: 0; min-width: 0; overflow: hidden; width: 100%; }.detail-dialog-heading { align-items: flex-start; background: white; border-bottom: 1px solid #e8edf4; display: flex; flex: none; gap: 20px; justify-content: space-between; padding: 22px 26px 18px; }.detail-dialog-heading > div { min-width: 0; }.detail-dialog-heading h2 { color: #243e60; font-size: 22px; line-height: 1.5; margin: 4px 0; overflow-wrap: anywhere; }.detail-description { color: #7b8da4; display: -webkit-box; font-size: 12px; line-height: 1.8; margin: 6px 0 0; overflow: hidden; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }.detail-close { background: #eff4fb; color: #6b83a3; flex: none; font-size: 22px; height: 36px; line-height: 1; padding: 0; width: 36px; }.detail-dialog-body { min-height: 0; overflow: auto; overscroll-behavior: contain; padding: 22px 26px; scrollbar-gutter: stable; }.detail-dialog-footer { align-items: center; background: #f8fafd; border-top: 1px solid #e5ecf5; color: #7990ae; display: flex; flex: none; flex-wrap: wrap; font-size: 12px; gap: 12px; justify-content: space-between; padding: 12px 26px; }.detail-close:focus-visible { outline: 3px solid #a6c8ee; outline-offset: 3px; }
.detail-dialog-frame.is-small { max-width: 540px; }
.detail-dialog-frame:not(.is-small) { height: min(92dvh,960px); }
.detail-dialog-body { flex: 1 1 auto; }
@media(max-width:600px) { .detail-dialog { padding: 10px; }.detail-dialog-frame { border-radius: 16px; max-height: 96dvh; }.detail-dialog-heading { gap: 12px; padding: 16px; }.detail-dialog-heading h2 { font-size: 18px; }.detail-dialog-body { padding: 16px; }.detail-dialog-footer { font-size: 11px; padding: 11px 16px; } }
@media(max-width:600px) { .detail-dialog-frame:not(.is-small) { height: 96dvh; } }
</style>
