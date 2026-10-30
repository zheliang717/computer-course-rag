export type TeachingWeakPoint = {
  topic: string; unresolved_students: number; unresolved_questions: number; recorded_mistakes: number
}
export type TeachingPracticeSummary = {
  attempts: number; students: number; scored_attempts: number; correct_attempts: number; accuracy_percent: number | null
}
export type TeachingFocus = TeachingWeakPoint & { practice: TeachingPracticeSummary }
export type TeachingInsights = {
  course_id: string; course_title: string; generated_at: string; student_count: number; assignment_count: number
  pending_review_count: number; weak_points: TeachingWeakPoint[]; focus: TeachingFocus | null
  assignments: Array<{ id: string; title: string; submission_count: number; pending_review_count: number; has_published_review: boolean }>
}
export type TeachingImpact = {
  draft_id: string; course_id: string; topic: string | null; generated_at: string; baseline: TeachingInsights
  current_focus: TeachingFocus | null; current_student_count: number; published_at: string | null
  published_question_count: number; published_question_practice: TeachingPracticeSummary | null; note: string
}
