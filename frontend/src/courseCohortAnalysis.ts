export type CohortStudent = {
  student_id: string; student_name: string; username: string; submission_count: number; missing_count: number
  overdue_missing_count: number; graded_count: number; scored_count: number; pending_count: number
  average_score: number | null; weak_points: string[]; unresolved_questions: number
  latest_assignment_id: string | null; latest_submission_id: string | null
}
export type CohortAssignment = {
  id: string; title: string; due_at: string | null; overdue: boolean; submission_count: number; missing_count: number
  graded_count: number; scored_count: number; pending_count: number; average_score: number | null; pass_rate: number | null
}
export type CohortOverview = {
  course_id: string; course_title: string; generated_at: string
  summary: {
    student_count: number; assignment_count: number; expected_submissions: number; submission_count: number
    missing_count: number; overdue_missing_count: number; pending_count: number; graded_count: number; scored_count: number
    students_with_grades: number; average_score: number | null; median_score: number | null; pass_rate: number | null; submission_rate: number | null
  }
  score_distribution: Array<{ label: string; count: number }>
  weak_points: Array<{ topic: string; student_count: number; unresolved_questions: number }>
  assignments: CohortAssignment[]
}
export type CohortAnalysisResult = {
  draft: { id: string; content: string; created_at: string; source_context: { student_names?: Record<string, string> } }
  analysis: { summary: string; strengths: string[]; concerns: string[]; teaching_actions: string[]
    student_suggestions: Array<{ student_id: string; reason: string; next_step: string }> }
  stale: boolean; students: CohortStudent[]; overview: CohortOverview
  coverage: { student_count_total: number; student_count_included: number; assignment_count_total: number; assignment_count_included: number }
}
