export type AssignmentSummary = {
  id: string; course_id: string; course_title: string; title: string; status: string; due_at: string | null;
  question_count: number; submission_count: number; ungraded_count?: number; submitted: boolean;
  submission_status: string | null; score: number | null; max_score: number | null;
  late_request_status: string | null; late_approved_until: string | null;
}
export type TaskQuestion = { id: string; stem: string; question_type: string; options: string[]; correct_answer?: string | null; explanation?: string | null; knowledge_point?: string | null }
export type TaskAnswers = Record<string,string|string[]>
export const answered = (value: string|string[]|undefined) => Array.isArray(value) ? value.length>0 : !!value?.trim()
export function assignmentState(item: AssignmentSummary, now=Date.now()) {
  if(item.submitted) return item.submission_status==='graded'?'已批改':'待批改'
  if(item.status==='draft') return '草稿'
  if(item.status==='closed') return '已结束'
  if(item.due_at && Date.parse(item.due_at)<now) return item.late_request_status==='pending'?'补交申请中':item.late_request_status==='approved'&&(!item.late_approved_until||Date.parse(item.late_approved_until)>=now)?'可补交':'已截止'
  return '进行中'
}
