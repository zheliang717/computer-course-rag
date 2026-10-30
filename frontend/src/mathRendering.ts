import katex from 'katex'
import 'katex/dist/katex.min.css'

export function renderFormula(expression: string, displayMode: boolean) {
  return katex.renderToString(expression, {
    displayMode, throwOnError: false, trust: false, strict: 'ignore', maxExpand: 500, maxSize: 20,
  })
}
