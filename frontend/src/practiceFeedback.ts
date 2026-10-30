export type PracticeQuestion = {
  id: string; course_id: string; section_id: string | null; question_type: string
  stem: string; options: string[]; correct_answer: string | null; explanation: string | null
  difficulty: number; knowledge_point: string | null
}

export type PracticeFeedback = {
  attempt_id: string; question_id: string; course_id: string; course_title: string; knowledge_point: string
  submitted_answer: string; attempted_at: string; is_correct: boolean | null
  question_attempt_count: number; question_correct_count: number
  analysis: { summary: string; strengths: string[]; misconceptions: string[]; explanation: string; next_steps: string[]; self_check: string } | null
  state: 'not_generated' | 'processing' | 'ready' | 'failed'; stale: boolean; reused: boolean
  next_question: PracticeQuestion | null; source_label: string
}
