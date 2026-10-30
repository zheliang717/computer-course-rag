export type AdminTaskJob = {
  id: string; document_title: string; filename: string; status: 'queued' | 'processing' | 'completed' | 'failed'
  has_source_file: boolean; progress_percent: number; attempts: number; error_message: string | null
  page_count: number | null; chunk_count: number | null; created_at: string | null
}
export type AdminTaskQuota = { role: string; role_label: string; daily_limit: number; used_today: number; resets_at: string }
export type AdminTaskCall = { id: string; role: string; user_name: string; model: string; feature: string; error_type: string; duration_ms: number; created_at: string }
export type AdminTaskUser = { id: string; username: string; display_name: string; role: 'student' | 'teacher' | 'admin'; active: boolean; created_at: string | null; is_current_actor?: boolean; is_last_active_admin?: boolean }
export type AdminTaskModel = {
  provider: 'offline' | 'openai' | 'compatible'; model: string; api_base: string; configured: boolean
  timeout_seconds: number; fallback_offline: boolean; retrieval_top_k: number; retrieval_min_score: number; retrieval_vector_weight: number
  runtime_synchronized: boolean; updated_at: string | null; credential_recovery_required?: boolean
}
export type AdminOperation = {
  id: string; kind: 'retry_document' | 'set_model_quota' | 'set_user_active' | 'set_user_role' | 'set_model_config'; target_id: string; title: string; reason: string
  before: Record<string, unknown>; proposed: Record<string, unknown>; result: { message?: string; object?: unknown; runtime_synchronized?: boolean }
  status: 'prepared' | 'applied' | 'cancelled' | 'expired' | 'stale'
  expires_at: string; created_at: string; executed_at: string | null
}
