import type { CalculationReceipt } from './calculations'

export type ReviewQuestion = { question_type: string; stem: string; options: string[]; correct_answer: string; explanation?: string | null; difficulty: number; knowledge_point?: string | null }
export type ReviewAnchor = { kind: 'question' | 'source' | 'calculation'; matched: boolean; label: string; excerpt: string; reason: string; quote?: string | null; document_id?: string | null; page_number?: number | null }
export type ReviewFinding = { id: string; category: string; detail: string; suggestion: string; assessment: 'issue' | 'improvement' | 'uncertain'; claim_type: string; basis_status: 'linked' | 'missing' | 'invalid' | 'legacy'; basis_note: string; anchors: ReviewAnchor[] }
export type QuestionReview = {
  id: string; request_id: string; draft_id: string; question_index: number; question_fingerprint: string
  calculation_required: boolean
  question_snapshot: ReviewQuestion; status: 'processing' | 'completed' | 'cancelled' | 'failed'
  stage: string; message: string; stale: boolean; source_available: boolean
  created_at: string; updated_at: string; finished_at: string | null
  result: null | { summary: string; findings: ReviewFinding[]; analysis_version: number; basis_summary: string; suggestion_basis: Record<string, string[]>; suggestion_notes: Record<string, string>
    suggested_stem: string | null; suggested_correct_answer: string | null; suggested_explanation: string | null
    grounded: boolean; calculations: CalculationReceipt[]
    evidence: Array<{ document_id: string; document_name: string; page_number: number; chunk_id: string }> }
}
export type ReviewedChange = { draftId: string; index: number; original: ReviewQuestion; field: 'stem' | 'correct_answer' | 'explanation'; value: string }
export function questionKey(q: ReviewQuestion): string {
  return JSON.stringify([q.question_type, q.stem, q.options, q.correct_answer, q.explanation ?? null, q.difficulty, q.knowledge_point ?? null])
}
