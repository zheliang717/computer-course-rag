export type AccountUser = { id: string; username: string; display_name: string; role: string; role_label: string }
export type RegistrationPolicy = { mode: 'closed' | 'invite' | 'open'; teacher_applications: boolean; version: number }
export type AccountPage = { items: Record<string, any>[]; total: number; page: number; page_size: number }
export class AccountError extends Error {
  constructor(message: string, public status: number, public challenge = false) { super(message) }
}
export async function accountRequest<T>(base: string, token: string, path: string, body?: unknown, method?: string): Promise<T> {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), 25000)
  try {
    const response = await fetch(`${base}/api/v1${path}`, { method: method || (body === undefined ? 'GET' : 'POST'),
      headers: { ...(body === undefined ? {} : { 'Content-Type': 'application/json' }), ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: body === undefined ? undefined : JSON.stringify(body), signal: controller.signal })
    const data = await response.json()
    if (!response.ok) {
      const detail = data.detail
      throw new AccountError(typeof detail === 'string' ? detail : Array.isArray(detail) ? detail.map((e: { msg: string }) => e.msg).join('；') : detail?.message || '操作失败，请稍后再试。', response.status, Boolean(detail?.challenge_required))
    }
    return data as T
  } catch (error) {
    if (error instanceof AccountError) throw error
    throw new AccountError('连接中断或服务暂不可用，操作结果待核实。请先登录或刷新检查，勿连续重复提交。', 0)
  } finally { clearTimeout(timer) }
}
export const accountStateLabel = (value: string) => ({ pending: '待审核', approved: '已通过', rejected: '未通过', resolved: '已协助处理' }[value] || value)
export const invitationLink = (code: string) => `${location.origin}/#invite=${encodeURIComponent(code)}`
