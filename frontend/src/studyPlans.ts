export type StudyPlanPreferences = { focus: 'balanced' | 'assignments' | 'review'; daily_minutes: 10 | 20 | 40 | 60 }
export type StudyPlanItem = {
  id: string; kind: 'assignment' | 'wrong_review' | 'section_preview' | 'course_review' | 'wrong_question' | 'practice_question'
  target_id: string | null; title: string; detail: string; due_at: string | null
  available: boolean; completed: boolean | null; status: string; status_message: string; action_label: string
  estimated_minutes: number | null; knowledge_point: string | null; attempt_id: string | null; completed_at: string | null
}
export type StudyPlan = {
  id: string; course_id: string; course_title: string; created_at: string | null
  items: StudyPlanItem[]; actionable_count: number; completed_count: number
  revision: number; previous_plan_id: string | null; preferences: StudyPlanPreferences
  needs_refresh: boolean; legacy_plan: boolean; refresh_notice: string; next_item_id: string | null
  feedback: string; source_label: string; change_summary: { new_tasks?: number; kept_completed?: number }
}
export type StudyPlanTarget = { kind: 'assignment' | 'question' | 'practice_feedback' | 'section' | 'course'; course_id: string; target_id: string; attempt_id: string | null; practice_source: 'wrong_question' | 'diagnostic' | null }
