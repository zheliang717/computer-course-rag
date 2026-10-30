export type AnswerReview = {
  status: 'ai_reviewed' | 'incomplete'
  teacher_approved: boolean
  notice: string
  anchor_location_checked?: boolean
  semantic_entailment_verified?: boolean
  sections?: Array<{ heading: string; basis: 'course' | 'supplement' | 'inference' }>
  anchors?: Array<{ section_index: number; source_index: number; quote: string; document_id: string; page_number: number }>
  corrections?: string[]
}
