export type StudentAnswerAnalysisContent = {
  summary: string
  question_reviews: Array<{ question_id: string; observation: string; next_step: string }>
  teaching_suggestions: string[]
  feedback_draft: string
}

export type StudentAnswerAnalysisResult<TDraft = { id: string; content: string }> = {
  draft: TDraft
  analysis: StudentAnswerAnalysisContent
  student_name: string
  stale: boolean
  question_count_total: number
  question_count_analyzed: number
  content_edited?: boolean | null
}
