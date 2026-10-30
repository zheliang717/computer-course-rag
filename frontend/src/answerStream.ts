export class AnswerStreamError extends Error {
  constructor(message: string, readonly status: number) { super(message) }
}

/** Read authenticated POST SSE without exposing tokens in URLs or buffering the answer. */
export async function streamAnswer<T>(base: string, token: string, body: unknown, signal: AbortSignal,
  handlers: { onStage: (label: string) => void; onDelta: (text: string) => void; onReset?: () => void }): Promise<T> {
  const response = await fetch(`${base}/api/v1/questions/ask/stream`, {
    method: 'POST', headers: { 'Content-Type': 'application/json', Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body: JSON.stringify(body), signal,
  })
  if (!response.ok) {
    const error = await response.json().catch(() => null)
    throw new AnswerStreamError(typeof error?.detail === 'string' ? error.detail : '服务暂时不可用，请稍后重试。', response.status)
  }
  if (!response.body || !response.headers.get('content-type')?.includes('text/event-stream')) {
    throw new AnswerStreamError('回答连接未就绪，请刷新页面后重试。', 502)
  }
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  let pending = ''
  let timer: ReturnType<typeof setTimeout> | null = null
  const flush = () => {
    if (timer !== null) clearTimeout(timer)
    timer = null
    if (pending && !signal.aborted) { handlers.onDelta(pending); pending = '' }
  }
  const readPart = async () => {
    let idleTimer: ReturnType<typeof setTimeout> | undefined
    try {
      return await Promise.race([
        reader.read(),
        new Promise<never>((_, reject) => { idleTimer = setTimeout(() => reject(new AnswerStreamError('回答连接暂时没有新状态，请先核对处理结果。', 502)), 45000) }),
      ])
    } finally { if (idleTimer) clearTimeout(idleTimer) }
  }
  try {
    while (true) {
      const part = await readPart()
      buffer += decoder.decode(part.value, { stream: !part.done })
      // Normalize CRLF only after a complete packet, preserving split CR/LF boundaries.
      let boundary: RegExpExecArray | null
      while ((boundary = /\r?\n\r?\n/.exec(buffer))) {
        const packet = buffer.slice(0, boundary.index).replace(/\r\n/g, '\n')
        buffer = buffer.slice(boundary.index + boundary[0].length)
        let event = 'message'
        const lines: string[] = []
        for (const line of packet.split('\n')) {
          if (line.startsWith('event:')) event = line.slice(6).trim()
          else if (line.startsWith('data:')) lines.push(line.slice(5).trimStart())
        }
        if (!lines.length) continue
        let data: any
        try { data = JSON.parse(lines.join('\n')) } catch { throw new AnswerStreamError('回答连接异常，请重试。', 502) }
        if (event === 'error') throw new AnswerStreamError(data?.detail || '回答暂未完成，请重试。', data?.status || 502)
        if (event === 'cancelled') throw new AnswerStreamError(data?.detail || '请求已停止，请核对最终状态。', 409)
        if (event === 'reset') {
          if (timer !== null) clearTimeout(timer)
          timer = null
          pending = ''
          handlers.onReset?.()
          if (typeof data?.label === 'string') handlers.onStage(data.label)
        }
        if (event === 'stage' && typeof data?.label === 'string') handlers.onStage(data.label)
        if (event === 'delta' && typeof data?.text === 'string') {
          pending += data.text
          if (timer === null) timer = setTimeout(flush, 60)
        }
        if (event === 'done') {
          if (typeof data?.answer !== 'string' || !Array.isArray(data?.citations) || typeof data?.history_id !== 'string') {
            throw new AnswerStreamError('回答未能完整保存，请稍后重试。', 502)
          }
          flush()
          return data as T
        }
      }
      if (buffer.length > 512000) throw new AnswerStreamError('回答连接数据异常，请重试。', 502)
      if (part.done) break
    }
    throw new AnswerStreamError('连接已中断，本次未收到完整回答，可以重新尝试。', 502)
  } finally {
    if (timer !== null) clearTimeout(timer)
    await reader.cancel().catch(() => undefined)
    reader.releaseLock()
  }
}
