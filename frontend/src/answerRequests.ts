import { AnswerStreamError, streamAnswer } from './answerStream'

export type AnswerRequestStatus = 'in_progress' | 'completed' | 'cancelled' | 'failed' | 'unknown'
export type AnswerRequestSurface = 'assistant' | 'tutor'
export type AnswerReceipt<T = unknown> = {
  request_id: string; status: Exclude<AnswerRequestStatus, 'unknown'>; question: string
  context: { knowledge_base_id?: string | null; assistant_course_id?: string | null; assistant_scope?: string | null; answer_mode?: string; conversation_id?: string | null; source_document_id?: string | null; quick_action?: string | null }
  answer: T | null; message: string; error_status: number | null; can_retry: boolean
  created_at: string; updated_at: string; finished_at: string | null
}
type PendingPointer = { id: string; fingerprint: string; createdAt: number }
const key = (owner: string, surface: AnswerRequestSurface) => `rag:pending-answer:${owner}:${surface}`

export function pendingAnswer(owner: string, surface: AnswerRequestSurface): PendingPointer | null {
  try {
    const value = JSON.parse(sessionStorage.getItem(key(owner, surface)) || 'null')
    return value && typeof value.id === 'string' && /^[0-9a-f-]{36}$/i.test(value.id) ? value : null
  } catch { return null }
}

export function acknowledgeAnswer(owner: string, surface: AnswerRequestSurface, id: string) {
  try { if (pendingAnswer(owner, surface)?.id === id) sessionStorage.removeItem(key(owner, surface)) } catch { /* Private browsing can disable storage. */ }
}

async function control<T>(base: string, token: string, id: string, method: 'GET' | 'POST', reason?: string, signal?: AbortSignal): Promise<AnswerReceipt<T>> {
  const controller = new AbortController()
  const abort = () => controller.abort()
  if (signal?.aborted) controller.abort()
  else signal?.addEventListener('abort', abort, { once: true })
  const timeout = setTimeout(abort, 10000)
  try {
    const response = await fetch(`${base}/api/v1/answer-requests/${id}${method === 'POST' ? '/cancel' : ''}`, {
      method, signal: controller.signal, headers: { Authorization: `Bearer ${token}`, ...(method === 'POST' ? { 'Content-Type': 'application/json' } : {}) },
      ...(method === 'POST' ? { body: JSON.stringify({ reason: reason || 'user' }) } : {}),
    })
    const value = await response.json().catch(() => null)
    if (!response.ok) throw new AnswerStreamError(typeof value?.detail === 'string' ? value.detail : '暂时无法核对请求状态。', response.status)
    if (value?.request_id !== id || !['in_progress', 'completed', 'cancelled', 'failed'].includes(value?.status)) {
      throw new AnswerStreamError('请求回执不完整，请稍后重新核对。', 502)
    }
    return value as AnswerReceipt<T>
  } finally { clearTimeout(timeout); signal?.removeEventListener('abort', abort) }
}

export const readAnswerReceipt = <T>(base: string, token: string, id: string, signal?: AbortSignal) => control<T>(base, token, id, 'GET', undefined, signal)
export const cancelAnswerRequest = <T>(base: string, token: string, id: string, reason: 'user' | 'context_change' | 'reset' = 'user') => control<T>(base, token, id, 'POST', reason)

/** Only the receipt ID and a digest are stored in this tab; never the prompt, token, or partial answer. */
export async function sendAnswerRequest<T>(base: string, token: string, owner: string, surface: AnswerRequestSurface,
  body: Record<string, unknown>, signal: AbortSignal,
  handlers: { onStage: (label: string) => void; onDelta: (text: string) => void; onReset?: () => void; onRequest: (id: string, state: AnswerRequestStatus) => void }): Promise<T> {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(JSON.stringify(body)))
  const fingerprint = Array.from(new Uint8Array(hash)).map(value => value.toString(16).padStart(2, '0')).join('')
  const previous = pendingAnswer(owner, surface)
  let id: string = crypto.randomUUID()
  if (previous?.fingerprint === fingerprint) {
    id = previous.id
    handlers.onRequest(id, 'unknown')
    const state = await readAnswerReceipt<T>(base, token, id, signal)
    handlers.onRequest(id, state.status)
    if (state.status === 'completed' && state.answer) { acknowledgeAnswer(owner, surface, id); return state.answer }
    if (state.status === 'in_progress') throw new AnswerStreamError(state.message, 409)
    // A deliberate user retry after a known terminal result gets a new attempt ID.
    id = crypto.randomUUID()
  }
  if (signal.aborted) throw new DOMException('请求已停止。', 'AbortError')
  try { sessionStorage.setItem(key(owner, surface), JSON.stringify({ id, fingerprint, createdAt: Date.now() })) } catch { /* In-memory owner turn still holds its ID. */ }
  handlers.onRequest(id, 'in_progress')
  try {
    const answer = await streamAnswer<T>(base, token, { ...body, request_id: id }, signal, handlers)
    handlers.onRequest(id, 'completed')
    acknowledgeAnswer(owner, surface, id)
    return answer
  } catch (cause) {
    if (signal.aborted) throw cause
    handlers.onStage('连接未返回完整结果，正在核对服务端回执…')
    let state: AnswerReceipt<T>
    try {
      state = await readAnswerReceipt<T>(base, token, id, signal)
    } catch (lookupError) {
      if (lookupError instanceof AnswerStreamError && lookupError.status === 404 &&
          cause instanceof AnswerStreamError && cause.status >= 400 && cause.status < 500 && cause.status !== 409) {
        handlers.onRequest(id, 'failed')
        acknowledgeAnswer(owner, surface, id)
        throw cause
      }
      handlers.onRequest(id, 'unknown')
      throw new AnswerStreamError('连接已结束，但处理结果尚未确认。请先查看处理结果，不要重复发送。', 502)
    }
    handlers.onRequest(id, state.status)
    if (state.status === 'completed' && state.answer) { acknowledgeAnswer(owner, surface, id); return state.answer }
    throw new AnswerStreamError(state.message, state.error_status || 409)
  }
}
