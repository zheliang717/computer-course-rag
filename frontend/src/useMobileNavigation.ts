import { nextTick, onMounted, onUnmounted, ref, watch, type Ref } from 'vue'

/** Narrow navigation follows reading gestures; wide sidebars are manual only. */
export function useMobileNavigation(sidebar: Ref<HTMLElement | null>, compact: Ref<boolean>, blocked: () => boolean) {
  const collapsed = ref(false), height = ref(180)
  let last = 0, distance = 0, direction = 0, frame = 0, holdUntil = 0
  let intent = 0, intentUntil = 0, touchY = 0
  let observer: ResizeObserver | undefined
  function reveal() {
    collapsed.value = false
    distance = 0; direction = 0; intent = 0; intentUntil = 0; last = Math.max(0, window.scrollY)
    holdUntil = performance.now() + 700
  }
  function hide() {
    collapsed.value = true
    distance = 0; holdUntil = 0
    if (sidebar.value?.contains(document.activeElement) || document.activeElement?.closest('.platform-topbar')) void nextTick(() => {
      document.querySelector<HTMLButtonElement>('.mobile-nav-launcher')?.focus({ preventScroll: true })
    })
  }
  function update() {
    frame = 0
    const y = Math.max(0, window.scrollY), delta = y - last
    last = y
    if (!compact.value || blocked()) { distance = 0; return }
    if (y < 32) { collapsed.value = false; distance = 0; return }
    // Loading cards, focus and restored list positions are not a swipe gesture.
    if (performance.now() > intentUntil || (intent && Math.sign(delta) !== intent)) return
    if (performance.now() < holdUntil || Math.abs(delta) < 1) return
    const nextDirection = Math.sign(delta)
    distance = nextDirection === direction ? distance + Math.abs(delta) : Math.abs(delta)
    direction = nextDirection
    if (direction > 0 && y > 72 && distance >= 28) hide()
    if (direction < 0 && distance >= 14) reveal()
  }
  function scroll() { if (!frame) frame = requestAnimationFrame(update) }
  function markIntent(value: number) {
    intent = Math.sign(value); intentUntil = performance.now() + 2000; holdUntil = 0
  }
  function wheel(event: WheelEvent) { if (Math.abs(event.deltaY) > 0) markIntent(event.deltaY) }
  function touchStart(event: TouchEvent) { touchY = event.touches[0]?.clientY ?? 0 }
  function touchMove(event: TouchEvent) {
    if (event.touches.length !== 1) return
    const y = event.touches[0]!.clientY
    if (Math.abs(touchY-y) > 1) markIntent(touchY-y)
    touchY = y
  }
  function keys(event: KeyboardEvent) {
    if ((event.target as Element)?.closest('input,textarea,select,[contenteditable=true]')) return
    if (['PageDown','ArrowDown','End'].includes(event.key) || (event.key===' '&&!event.shiftKey)) markIntent(1)
    if (['PageUp','ArrowUp','Home'].includes(event.key) || (event.key===' '&&event.shiftKey)) markIntent(-1)
  }
  watch(sidebar, element => {
    observer?.disconnect()
    if (!element) return
    reveal()
    const measure = () => { if (compact.value) height.value = Math.ceil(element.getBoundingClientRect().height) }
    measure()
    observer = new ResizeObserver(measure); observer.observe(element)
  }, { flush: 'post' })
  watch(compact, () => { collapsed.value = false; distance = 0; last = Math.max(0, window.scrollY) })
  onMounted(() => {
    last = Math.max(0, window.scrollY)
    window.addEventListener('scroll', scroll, { passive: true })
    window.addEventListener('wheel', wheel, { passive: true })
    window.addEventListener('touchstart', touchStart, { passive: true })
    window.addEventListener('touchmove', touchMove, { passive: true })
    window.addEventListener('keydown', keys)
  })
  onUnmounted(() => {
    window.removeEventListener('scroll', scroll); window.removeEventListener('wheel', wheel)
    window.removeEventListener('touchstart', touchStart); window.removeEventListener('touchmove', touchMove)
    window.removeEventListener('keydown', keys); observer?.disconnect(); if (frame) cancelAnimationFrame(frame)
  })
  return { collapsed, height, reveal, hide }
}
