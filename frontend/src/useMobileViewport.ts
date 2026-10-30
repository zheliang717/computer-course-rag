import { computed, onMounted, onUnmounted, ref } from 'vue'

// visualViewport shrinks when a phone keyboard opens; 100vh alone does not.
export function useMobileViewport() {
  const compactViewport = ref(window.innerWidth <= 920)
  const visibleHeight = () => Math.min(window.visualViewport?.height ?? window.innerHeight, window.innerHeight)
  const height = ref(visibleHeight())
  const top = ref(window.visualViewport?.offsetTop ?? 0)
  const update = () => {
    compactViewport.value = window.innerWidth <= 920
    height.value = visibleHeight()
    top.value = window.visualViewport?.offsetTop ?? 0
    document.documentElement.style.setProperty('--app-visual-height', `${Math.round(height.value)}px`)
    document.documentElement.style.setProperty('--app-visual-top', `${Math.round(top.value)}px`)
  }
  onMounted(() => {
    update()
    window.addEventListener('resize', update)
    window.visualViewport?.addEventListener('resize', update)
    window.visualViewport?.addEventListener('scroll', update)
  })
  onUnmounted(() => {
    document.documentElement.style.removeProperty('--app-visual-height')
    document.documentElement.style.removeProperty('--app-visual-top')
    window.removeEventListener('resize', update)
    window.visualViewport?.removeEventListener('resize', update)
    window.visualViewport?.removeEventListener('scroll', update)
  })
  const viewportStyle = computed(() => ({
    '--assistant-visible-height': `${Math.round(height.value)}px`,
    '--assistant-visible-top': `${Math.round(top.value)}px`,
  }))
  return { compactViewport, viewportStyle }
}
