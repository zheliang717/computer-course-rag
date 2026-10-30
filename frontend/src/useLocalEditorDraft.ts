import { computed, onBeforeUnmount, ref, shallowRef } from 'vue'
type Stored<T> = { schema: 1; baseline: string; value: T; revision: string; savedAt: string }
const prefix = 'rag_editor_draft_v1:'
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
export function useLocalEditorDraft<T>(validate: (value: unknown) => boolean = value => !!value && typeof value === 'object') {
  const value = shallowRef<T | null>(null)
  const recovery = shallowRef<Stored<T> | null>(null)
  const error = ref(''), savedAt = ref(''), restored = ref(false), changedElsewhere = ref(false)
  let key = '', baseline = '', revision = '', timer: ReturnType<typeof setTimeout> | null = null
  const dirty = computed(() => value.value !== null && JSON.stringify(value.value) !== baseline)
  const sameBaseline = computed(() => recovery.value?.baseline === baseline)
  function read(raw: string | null): Stored<T> | null {
    if (!raw) return null
    if (raw.length > 1_000_000) throw new Error('本机草稿较大，请先复制当前内容。')
    const item = JSON.parse(raw)
    if (item.schema !== 1 || typeof item.baseline !== 'string' || typeof item.revision !== 'string' || typeof item.savedAt !== 'string' || !validate(item.value)) throw new Error('本机编辑草稿无法读取，请先复制当前内容。')
    return item
  }
  function stop() { if (timer) clearTimeout(timer); timer = null }
  function persist(force = false): boolean {
    stop()
    if (!key || value.value === null) return true
    if (!force && (recovery.value || changedElsewhere.value)) {
      error.value = '请先选择要保留的草稿版本，未覆盖或删除待恢复内容。'
      return false
    }
    try {
      let current: Stored<T> | null = null
      try { current = read(localStorage.getItem(key)) } catch (cause) { if (!force) throw cause }
      if (!force && (current?.revision || '') !== revision) { recovery.value = current; changedElsewhere.value = true; throw new Error('另一页面更新了本机草稿。请选择版本后继续，当前内容尚未覆盖它。') }
      if (!dirty.value) {
        if (current) localStorage.removeItem(key)
        revision = ''; savedAt.value = ''
      } else {
        const item: Stored<T> = { schema: 1, baseline, value: clone(value.value), revision: crypto.randomUUID(), savedAt: new Date().toISOString() }
        const text = JSON.stringify(item)
        if (text.length > 1_000_000) throw new Error('本机草稿较大，请先复制当前内容。')
        localStorage.setItem(key, text); revision = item.revision; savedAt.value = item.savedAt
      }
      error.value = ''; changedElsewhere.value = false; recovery.value = null
      return true
    } catch (cause) { error.value = cause instanceof Error && /草稿|内容/.test(cause.message) ? cause.message : '本机暂存不可用，请先复制当前内容；当前编辑仍保留在页面中。'; return false }
  }
  function open(owner: string, kind: string, id: string, initial: T) {
    stop()
    key = `${prefix}${encodeURIComponent(owner)}:${kind}:${encodeURIComponent(id)}`
    baseline = JSON.stringify(initial); value.value = clone(initial); revision = ''; savedAt.value = ''; restored.value = false; recovery.value = null; changedElsewhere.value = false; error.value = ''
    try {
      const stored = read(localStorage.getItem(key))
      if (!stored) return
      revision = stored.revision
      if (stored.baseline === baseline) { value.value = clone(stored.value); restored.value = true; savedAt.value = stored.savedAt }
      else recovery.value = stored
    } catch (cause) { error.value = cause instanceof Error ? cause.message : '本机编辑草稿无法读取。'; changedElsewhere.value = true }
  }
  function set(next: T) { value.value = clone(next); stop(); if (!changedElsewhere.value && !recovery.value) timer = setTimeout(() => persist(), 250) }
  function recover() {
    if (!recovery.value) return
    value.value = clone(recovery.value.value); revision = recovery.value.revision; recovery.value = null; changedElsewhere.value = false; restored.value = true
    persist(true)
  }
  function keepCurrent() { recovery.value = null; changedElsewhere.value = false; persist(true) }
  function clear() {
    stop()
    try { const current = read(key ? localStorage.getItem(key) : null); if (key && (!current || current.revision === revision)) localStorage.removeItem(key) }
    catch { /* Preserve an unreadable or other-page draft rather than deleting it. */ }
    revision = ''; savedAt.value = ''; recovery.value = null; changedElsewhere.value = false; restored.value = false; error.value = ''
  }
  function release() { stop(); key = ''; baseline = ''; revision = ''; value.value = null; recovery.value = null; error.value = ''; savedAt.value = ''; restored.value = false; changedElsewhere.value = false }
  function storage(event: StorageEvent) {
    if (event.key !== key || !key) return
    try { const next = read(event.newValue); if ((next?.revision || '') !== revision) { stop(); recovery.value = next; changedElsewhere.value = true; error.value = '另一页面更新或清除了草稿，请选择要保留的版本。' } }
    catch { error.value = '另一页面写入的草稿无法读取，请先复制当前内容。'; changedElsewhere.value = true }
  }
  window.addEventListener('storage', storage)
  onBeforeUnmount(() => { persist(); window.removeEventListener('storage', storage); stop() })
  return { value, recovery, error, savedAt, restored, changedElsewhere, dirty, sameBaseline, open, set, persist, recover, keepCurrent, clear, release }
}
