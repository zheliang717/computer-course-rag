import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue'
import { lockBodyScroll } from './useBodyScrollLock'

export function useDialogFocus(panel: Ref<HTMLElement | null>, close: () => void, enabled: () => boolean) {
  let previous: HTMLElement | null = null
  let releaseScroll: (() => void) | null = null
  const focusable = () => Array.from(panel.value?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), textarea:not(:disabled), select:not(:disabled), [href], [tabindex="0"], summary') ?? []).filter(el => el.getClientRects().length > 0)
  watch(panel, async element => {
    if (element) {
      releaseScroll?.(); releaseScroll = lockBodyScroll()
      previous = document.activeElement instanceof HTMLElement ? document.activeElement : null
      await nextTick()
      if (element === panel.value && enabled()) (focusable()[0] ?? element).focus({ preventScroll: true })
    } else {
      releaseScroll?.(); releaseScroll = null
      if (previous?.isConnected && previous.getClientRects().length) previous.focus({ preventScroll: true })
      previous = null
    }
  }, { flush: 'post' })
  function onKeydown(event: KeyboardEvent) {
    const element = panel.value
    if (!element || !enabled() || !element.contains(document.activeElement)) return
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close() }
    else if (event.key === 'Tab') {
      const items = focusable(), first = items[0], last = items.at(-1)
      if (!first) { event.preventDefault(); element.focus(); return }
      if (event.shiftKey && (document.activeElement === first || document.activeElement === element)) { event.preventDefault(); last?.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
  }
  document.addEventListener('keydown', onKeydown)
  onBeforeUnmount(() => { document.removeEventListener('keydown', onKeydown); releaseScroll?.() })
}
