import { shallowRef } from 'vue'
import DOMPurify from 'dompurify'
import { Marked } from 'marked'
import type { TokenizerExtension, Tokens } from 'marked'
import { escapeText } from './useMarkdown'

export type RenderOptions = { interactive?: boolean; streaming?: boolean; evidenceCount?: number }
type FormulaRenderer = (expression: string, displayMode: boolean) => string
const formulaRenderer = shallowRef<FormulaRenderer | null>(null)
let formulaLoading: Promise<void> | null = null
export const formulaFailed = shallowRef(false)

export function loadFormulas() {
  if (formulaRenderer.value) return Promise.resolve()
  if (formulaLoading) return formulaLoading
  formulaFailed.value = false
  formulaLoading = import('./mathRendering').then(module => { formulaRenderer.value = module.renderFormula })
    .catch(() => { formulaFailed.value = true }).finally(() => { formulaLoading = null })
  return formulaLoading
}

function formulaToken(source: string, display: boolean) {
  const match = display
    ? /^(?:\$\$([\s\S]+?)\$\$|\\\[([\s\S]+?)\\\])(?:[ \t]*\n|$)/.exec(source)
    : /^(?:\\\(([^\n]+?)\\\)|\$(?!\$)([^\s$](?:[^$\n]*?[^\s$])?)\$(?!\$))/.exec(source)
  if (!match) return
  // Do not consume an escaped closing dollar, and leave unfinished streamed expressions as text.
  const expression = match[1] ?? match[2] ?? ''
  if (!display && expression.endsWith('\\')) return
  return { type: display ? 'courseBlockMath' : 'courseInlineMath', raw: match[0], expression, display }
}

/** Math is a Markdown token, so fenced code, inline code, link destinations and escaped dollars stay literal. */
export function renderMarkdown(source: string, options: RenderOptions = {}): string {
  const math = formulaRenderer.value // Vue tracks delayed formula availability in every consumer.
  const renderMath = (expression: string, displayMode: boolean) => {
    if (!expression.trim() || expression.length > 4096) return `<code>${escapeText(expression)}</code>`
    if (!math) {
      if (!formulaFailed.value) void loadFormulas()
      return `<${displayMode ? 'div' : 'span'} class="formula-pending"${formulaFailed.value ? ' data-math-unavailable="true"' : ''}>${escapeText(expression)}</${displayMode ? 'div' : 'span'}>`
    }
    try { return math(expression.trim(), displayMode) }
    catch { return `<code>${escapeText(expression)}</code>` }
  }
  const inline: TokenizerExtension = {
    name: 'courseInlineMath', level: 'inline',
    start: value => value.search(/\$(?!\$)|\\\(/),
    tokenizer: value => formulaToken(value, false),
  }
  const block: TokenizerExtension = {
    name: 'courseBlockMath', level: 'block',
    start: value => { const match = /(?:^|\n)(?:\$\$|\\\[)/.exec(value); return match ? match.index : -1 },
    tokenizer: value => formulaToken(value, true),
  }
  const parser = new Marked({ breaks: true, gfm: true })
  parser.use({ extensions: [
    { ...block, renderer: token => renderMath(token.expression, true) },
    { ...inline, renderer: token => renderMath(token.expression, false) },
    { name: 'courseEvidence', level: 'inline', start: value => value.indexOf('[证据'),
      tokenizer(value) {
        const match = /^\[证据(\d+)\]/.exec(value)
        if (match) return { type: 'courseEvidence', raw: match[0], number: Number(match[1]) }
      }, renderer: token => options.interactive !== false && !options.streaming && token.number >= 1 && token.number <= (options.evidenceCount || 0)
        ? `<button type="button" class="inline-evidence" data-evidence-index="${token.number-1}" aria-label="打开资料依据${token.number}">资料${token.number}</button>`
        : escapeText(token.raw) },
  ], renderer: {
    html: ({ text }) => escapeText(text),
    image: ({ text }: Tokens.Image) => `<span class="answer-image-label">[图片：${escapeText(text || '未提供说明')}；未自动加载外部图片]</span>`,
    link(token: Tokens.Link) {
      const label = this.parser.parseInline(token.tokens)
      if (options.streaming || options.interactive === false || !/^(https?:\/\/|mailto:)/i.test(token.href)) return label
      return `<a href="${escapeText(token.href)}" target="_blank" rel="noopener noreferrer">${label}</a>`
    },
    code({ text, lang }: Tokens.Code) {
      const language = (lang || '代码').split(/\s/)[0]!.slice(0, 32)
      const code = `<pre><code>${escapeText(text)}</code></pre>`
      if (!options.interactive || options.streaming) return code
      return `<figure class="answer-code"><figcaption><span>${escapeText(language)}</span><button type="button" data-copy-code="true" aria-label="复制这段代码">复制代码</button></figcaption>${code}</figure>`
    },
  } })
  let parsed: string
  try { parsed = parser.parse(source, { async: false }) as string }
  catch { return `<pre class="answer-plain-text">${escapeText(source)}</pre>` }
  return DOMPurify.sanitize(parsed, {
    ADD_ATTR: ['target', 'rel', 'style', 'data-copy-code', 'data-evidence-index'],
    FORBID_TAGS: ['img', 'iframe', 'video', 'audio', 'source', 'style', 'link', 'form', 'input'],
  })
}
