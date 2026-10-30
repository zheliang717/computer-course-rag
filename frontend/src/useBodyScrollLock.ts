let depth = 0
let overflow = '', padding = ''
export function lockBodyScroll() {
  if (depth++ === 0) {
    overflow = document.body.style.overflow
    padding = document.body.style.paddingRight
    const width = window.innerWidth - document.documentElement.clientWidth
    if (width > 0) document.body.style.paddingRight = `${parseFloat(getComputedStyle(document.body).paddingRight) + width}px`
    document.body.style.overflow = 'hidden'
  }
  let released = false
  return () => {
    if (released) return
    released = true
    if (--depth === 0) { document.body.style.overflow = overflow; document.body.style.paddingRight = padding }
  }
}
