export type TeachingWorkflow = {
  draft_id: string; course_id: string; course_title: string; draft_status: string; generated_at: string
  published_at: string | null; published_question_count: number; available_question_count: number
  missing_question_count: number; current_student_count: number; linked_assignment_count: number
  assignment_statuses: Record<string, number>; note: string
  independent_practice: { attempts: number; students: number; scored_attempts: number; correct_attempts: number; accuracy_percent: number | null } | null
}
export type DraftAssignmentPreview = {
  draft_id: string; course_id: string; course_title: string; request_id: string; expected_signature: string
  default_title: string; question_count: number; current_student_count: number; ready: boolean; problems: string[]; notice: string
  questions: Array<{ question_id: string; position: number; stem: string; question_type: string; options: string[]; correct_answer: string; explanation: string | null; knowledge_point: string | null; difficulty: number; changed_since_publication: boolean }>
  findings: Array<{ question_index: number; severity: string; message: string }>
}
export type DraftAssignmentReceipt = { assignment_id: string; source_draft_id: string; course_id: string; title: string; status: string; created_at: string; reused: boolean }
export type DraftAssignmentProgress = {
  id: string; title: string; status: string; due_at: string | null; created_at: string; question_count: number
  current_student_count: number; active_submission_count: number; all_submission_count: number; graded_count: number
  pending_review_count: number; unsubmitted_count: number | null; submission_percent: number | null; average_score_percent: number | null
  has_published_review: boolean
}
