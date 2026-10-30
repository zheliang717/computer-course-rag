export type CourseRecord = {
  id: string
  title: string
  code: string
  description: string | null
  learning_objectives?: string
  assessment?: string
  semester: string | null
  cover_image_url: string | null
  teacher_name: string | null
  schedule: string | null
  location: string | null
  status: string
  owner_id: string | null
  section_count: number
  class_count: number
  student_count: number
  created_at: string | null
  sections: Array<{ id: string; title: string; description: string | null; position: number }>
}
export type CatalogCourse = CourseRecord & { knowledge_base_count: number; ready_document_count: number }
