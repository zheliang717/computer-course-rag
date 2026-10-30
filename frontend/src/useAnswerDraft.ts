import { computed, onBeforeUnmount, ref, watch } from 'vue'

export type DraftAnswers = Record<string, string | string[]>
export type DraftQuestion = { id: string; stem: string; question_type: string; options: string[] }
type DraftContext = { owner: string; kind: 'assignment' | 'practice'; id: string; questions: DraftQuestion[] }
export type AnswerDraft = { version: 1; questions: DraftQuestion[]; answers: DraftAnswers; savedAt: string; revision: string }
const PREFIX = 'rag.answer-draft.v1:'

function signature(questions: DraftQuestion[]) {
  return JSON.stringify(questions.map(({ id, stem, question_type, options }) => ({ id, stem, question_type, options })))
}
function hash(value: string) {
  let a = 2166136261, b = 5381
  for (let i = 0; i < value.length; i++) {
    a = Math.imul(a ^ value.charCodeAt(i), 16777619)
    b = Math.imul(b, 33) ^ value.charCodeAt(i)
  }
  return `${(a >>> 0).toString(16)}-${(b >>> 0).toString(16)}`
}
function cleanAnswers(value: unknown, questions: DraftQuestion[]): DraftAnswers {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return {}
  const result: DraftAnswers = {}
  for (const question of questions) {
    const answer = (value as DraftAnswers)[question.id]
    if (typeof answer === 'string' && answer.trim()) result[question.id] = answer
    else if (Array.isArray(answer) && answer.length && answer.every(item => typeof item === 'string')) result[question.id] = [...answer]
  }
  return result
}
function readDraft(raw: string | null): AnswerDraft | null {
  if (!raw || raw.length > 1_000_000) return null
  try {
    const value = JSON.parse(raw) as AnswerDraft
    if (value.version !== 1 || !Array.isArray(value.questions) || !value.questions.length || value.questions.length > 300 ||
      !value.questions.every(q => typeof q.id === 'string' && typeof q.stem === 'string' && typeof q.question_type === 'string' &&
        Array.isArray(q.options) && q.options.every(item => typeof item === 'string')) ||
      typeof value.revision !== 'string' || !Number.isFinite(Date.parse(value.savedAt))) return null
    return { ...value, answers: cleanAnswers(value.answers, value.questions) }
  } catch { return null }
}

/** Only user-entered answers are cached. This never submits work or changes progress. */
export function useAnswerDraft() {
  const answers = ref<DraftAnswers>({})
  const savedAt = ref('')
  const restored = ref(false)
  const error = ref('')
  const previousVersion = ref<AnswerDraft | null>(null)
  const otherPage = ref<AnswerDraft | null>(null)
  let context: DraftContext | null = null
  let key = '', knownRevision = '', baseline = '{}', stored = '{}'
  let suspended = false
  let timer: ReturnType<typeof setTimeout> | null = null
  const hasContent = computed(() => Object.values(answers.value).some(value => Array.isArray(value) ? value.length > 0 : !!value.trim()))
  const pending = ref(false)
  function stopTimer() { if (timer !== null) clearTimeout(timer); timer = null }
  function answerText() { return JSON.stringify(cleanAnswers(answers.value, context?.questions ?? [])) }

  function persist(overwrite = false, recheck = false): boolean {
    stopTimer()
    if (!context) return true
    const text = answerText()
    if (text === stored && !error.value && !recheck) { pending.value = false; return true }
    try {
      if (context.questions.length > 300) throw new Error('题量较大，无法继续本机暂存，请先复制答案留存。')
      const raw = localStorage.getItem(key)
      const existing = readDraft(raw)
      if (raw && !existing) throw new Error('本机草稿无法读取，请先复制答案留存；当前内容仍保留在窗口中。')
      if (existing && signature(existing.questions) !== signature(context.questions)) throw new Error('草稿版本不匹配，请先复制答案留存。')
      if (!overwrite && (existing?.revision ?? '') !== knownRevision) {
        otherPage.value = existing ?? { version: 1, questions: context.questions, answers: {}, savedAt: new Date().toISOString(), revision: '' }
        throw new Error('另一页面更新了草稿。本页答案尚未覆盖它，请选择要保留的版本。')
      }
      if (text === '{}' || text === baseline) {
        localStorage.removeItem(key)
        knownRevision = ''; savedAt.value = ''
      } else {
        const draft: AnswerDraft = { version: 1, questions: context.questions, answers: JSON.parse(text), savedAt: new Date().toISOString(), revision: crypto.randomUUID() }
        const value = JSON.stringify(draft)
        if (value.length > 1_000_000) throw new Error('答案较长，无法继续本机暂存，请先复制答案留存。')
        localStorage.setItem(key, value)
        knownRevision = draft.revision; savedAt.value = draft.savedAt
      }
      stored = text; pending.value = false; error.value = ''; otherPage.value = null
      return true
    } catch (reason) {
      pending.value = false
      error.value = reason instanceof Error && /草稿|答案/.test(reason.message)
        ? reason.message : '本机暂存不可用，请先复制答案留存；关闭或刷新前会再次提醒。'
      return false
    }
  }

  function open(next: DraftContext | null, initial: DraftAnswers = {}) {
    stopTimer(); suspended = true
    context = next ? { ...next, questions: next.questions.map(({ id, stem, question_type, options }) => ({ id, stem, question_type, options: [...options] })) } : null
    answers.value = { ...initial }
    savedAt.value = ''; error.value = ''; restored.value = false; previousVersion.value = null; otherPage.value = null; pending.value = false
    key = ''; knownRevision = ''; baseline = answerText(); stored = baseline
    if (context) {
      const prefix = `${PREFIX}${encodeURIComponent(context.owner)}:${context.kind}:${encodeURIComponent(context.id)}:`
      key = prefix + hash(signature(context.questions))
      try {
        const raw = localStorage.getItem(key)
        const draft = readDraft(raw)
        if (raw && !draft) throw new Error('本机草稿无法读取，请先复制新填写的答案留存。')
        if (draft && signature(draft.questions) === signature(context.questions)) {
          answers.value = draft.answers; savedAt.value = draft.savedAt; knownRevision = draft.revision; restored.value = true
        }
        for (let i = 0; i < localStorage.length; i++) {
          const oldKey = localStorage.key(i)
          if (!oldKey || oldKey === key || !oldKey.startsWith(prefix)) continue
          const older = readDraft(localStorage.getItem(oldKey))
          if (older && (!previousVersion.value || older.savedAt > previousVersion.value.savedAt)) previousVersion.value = older
        }
        stored = answerText()
      } catch { error.value = '本机草稿读取失败，请先复制答案留存；关闭或刷新前会再次提醒。' }
    }
    suspended = false
  }
  function release() { stopTimer(); context = null; pending.value = false }
  function markSubmitted(keepOpen = false) {
    stopTimer()
    // Do not remove a newer draft saved in another tab.
    try { if (key && readDraft(localStorage.getItem(key))?.revision === knownRevision) localStorage.removeItem(key) } catch { /* server submission remains authoritative */ }
    if (keepOpen) { baseline = answerText(); stored = baseline; knownRevision = ''; pending.value = false }
    else release()
    savedAt.value = ''; restored.value = false; error.value = ''; previousVersion.value = null; otherPage.value = null
  }
  function discard() {
    if (!context) return
    try {
      const draft = readDraft(localStorage.getItem(key))
      if ((draft?.revision ?? '') !== knownRevision) { persist(false, true); return }
      localStorage.removeItem(key)
      suspended = true; answers.value = JSON.parse(baseline); suspended = false
      knownRevision = ''; stored = baseline; savedAt.value = ''; restored.value = false; pending.value = false; error.value = ''
      stopTimer()
    } catch { error.value = '未能清除本机草稿，答案仍保留，请稍后重试。' }
  }
  function restoreOtherPage() {
    if (!context || !otherPage.value) return
    suspended = true; answers.value = JSON.parse(JSON.stringify(otherPage.value.answers)); suspended = false
    knownRevision = otherPage.value.revision; savedAt.value = otherPage.value.savedAt; stored = answerText()
    restored.value = true; otherPage.value = null; error.value = ''; pending.value = false; stopTimer()
  }
  watch(answers, () => {
    if (suspended || !context) return
    pending.value = true; restored.value = false; stopTimer()
    timer = setTimeout(() => persist(), 300)
  }, { deep: true, flush: 'sync' })
  function beforeUnload(event: BeforeUnloadEvent) {
    if (!persist() && hasContent.value) { event.preventDefault(); event.returnValue = '' }
  }
  function onHidden() { if (document.visibilityState === 'hidden') persist() }
  window.addEventListener('beforeunload', beforeUnload)
  document.addEventListener('visibilitychange', onHidden)
  onBeforeUnmount(() => {
    persist(); stopTimer()
    window.removeEventListener('beforeunload', beforeUnload)
    document.removeEventListener('visibilitychange', onHidden)
  })
  return { answers, savedAt, restored, error, pending, hasContent, previousVersion, otherPage, persist, open, release, markSubmitted, discard, restoreOtherPage }
}
