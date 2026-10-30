type Store = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>
export type PracticeTicket = { key: string; requestId: string }

/** Keep an unknown-result submission stable across retries and page reloads.
 * Storage contains only a digest and random request ID, not the answer/token.
 * Separate intentional attempts after a successful response get new IDs.
 */
export function createPracticeSubmissionTracker(storage: () => Store | null, newId = () => crypto.randomUUID()) {
  const memory = new Map<string, string>()
  const persisted = new Set<string>()
  async function prepare(owner: string, question: string, answer: string): Promise<PracticeTicket> {
    const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify([question, answer])))
    const hex = Array.from(new Uint8Array(digest), n => n.toString(16).padStart(2, '0')).join('')
    const key = `rag.practice-submission.v1:${owner}:${hex}`
    let requestId = memory.get(key) || ''
    try {
      const store = storage()
      if (store) requestId = store.getItem(key) || (persisted.has(key) ? '' : requestId)
    } catch { /* in-page retries still use memory */ }
    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(requestId)) requestId = newId()
    memory.set(key, requestId)
    try { const store = storage(); if (store) { store.setItem(key, requestId); persisted.add(key) } } catch { /* no claim of cross-refresh recovery in a blocked browser */ }
    return { key, requestId }
  }
  function complete(ticket: PracticeTicket) {
    if (memory.get(ticket.key) === ticket.requestId) { memory.delete(ticket.key); persisted.delete(ticket.key) }
    try { const store = storage(); if (store?.getItem(ticket.key) === ticket.requestId) store.removeItem(ticket.key) } catch { /* safe to replay an old receipt */ }
  }
  return { prepare, complete }
}
