import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { Ref } from 'vue'
import { defaultAvatar, readAvatar } from './avatars'
import type { AvatarState } from './avatars'

export function useAccountAvatar(base: string, token: Ref<string>, userId: Readonly<Ref<string>>) {
  const avatar = ref<AvatarState>(defaultAvatar())
  let sequence = 0, lastRead = 0, alive = true
  async function refresh(force = false) {
    const identity = userId.value, credential = token.value
    if (!identity || identity.startsWith('demo-') || !credential || (!force && Date.now() - lastRead < 10000)) return
    lastRead = Date.now()
    const generation = ++sequence
    try {
      const result = await readAvatar(base, credential)
      if (alive && generation === sequence && identity === userId.value && credential === token.value) avatar.value = result
    } catch { /* Keep the last known avatar when offline; editing offers an explicit retry. */ }
  }
  function updated(value: AvatarState) {
    sequence += 1; avatar.value = value; lastRead = Date.now()
    // Notify sibling tabs without persisting the photo in browser storage.
    try { localStorage.setItem('rag_avatar_changed', JSON.stringify({ user: userId.value, at: Date.now(), revision: value.revision })) } catch { /* Sync on focus remains available. */ }
  }
  function focus() { if (document.visibilityState === 'visible') void refresh() }
  function storage(event: StorageEvent) {
    if (event.key !== 'rag_avatar_changed' || !event.newValue) return
    try { if (JSON.parse(event.newValue).user === userId.value) void refresh(true) } catch { /* Ignore malformed unrelated storage. */ }
  }
  watch([token, userId], () => { sequence += 1; avatar.value = defaultAvatar(); lastRead = 0; void refresh(true) }, { immediate: true })
  onMounted(() => { window.addEventListener('focus', focus); document.addEventListener('visibilitychange', focus); window.addEventListener('storage', storage) })
  onUnmounted(() => { alive = false; sequence += 1; window.removeEventListener('focus', focus); document.removeEventListener('visibilitychange', focus); window.removeEventListener('storage', storage) })
  return { avatar, updated }
}
