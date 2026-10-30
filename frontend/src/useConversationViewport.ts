import { nextTick, onBeforeUnmount, watch, type Ref } from 'vue'

type Anchor = { key: string; offset: number }

/** Retain the visible message, including late Markdown/math reflow after prepend. */
export function useConversationViewport(container: Ref<HTMLElement | null>, active: () => boolean) {
  let anchor: Anchor | null = null
  let savedTop = 0
  let observer: ResizeObserver | undefined
  let disposed = false

  function save() {
    const box = container.value
    if (!box) return
    savedTop = box.scrollTop
    const top = box.getBoundingClientRect().top
    const items = Array.from(box.querySelectorAll<HTMLElement>('[data-message-key]'))
    const visible = items.find(item => item.getBoundingClientRect().bottom > top + 1)
    anchor = visible?.dataset.messageKey
      ? { key: visible.dataset.messageKey, offset: visible.getBoundingClientRect().top - top } : null
  }
  function restore() {
    const box = container.value
    if (!box || !active() || disposed) return
    const target = anchor && Array.from(box.querySelectorAll<HTMLElement>('[data-message-key]'))
      .find(item => item.dataset.messageKey === anchor?.key)
    if (target && anchor) {
      const delta = target.getBoundingClientRect().top - box.getBoundingClientRect().top - anchor.offset
      if (Math.abs(delta) > .5) box.scrollTop += delta
    } else if (anchor) {
      box.scrollTop = savedTop
    }
  }
  function release() { anchor = null }
  function hold() { if (!anchor) save() }
  function clear() { anchor = null; savedTop = 0 }
  watch(container, async box => {
    observer?.disconnect()
    await nextTick()
    if (!box || disposed || box !== container.value) return
    const stack = box.querySelector('.assistant-message-stack')
    if (stack && typeof ResizeObserver !== 'undefined') {
      observer = new ResizeObserver(() => { if (anchor) restore() })
      observer.observe(stack)
      observer.observe(box)
      const pager = box.querySelector('.assistant-message-pager')
      if (pager) observer.observe(pager)
    }
  }, { flush: 'post' })
  onBeforeUnmount(() => { disposed = true; observer?.disconnect() })
  return { save, hold, restore, release, clear }
}
