export type Lesson = {
  id: string; course_id: string; title: string; section_id: string | null; session_date: string;
  duration_minutes: number; location: string | null; completed: boolean; revision: number;
  schedule_status: string; rule_id: string | null; course_title: string; teacher_name: string | null;
  semester: string | null; section_title: string | null; end_date: string;
}
export type ScheduleCourse = { id: string; title: string; semester: string; sections: { id: string; title: string }[] }
export type SchoolCalendar = { semester: string; start_date: string; end_date: string; holidays: string[]; rooms: string[]; revision: number }
export type ScheduleOptions = { courses: ScheduleCourse[]; semesters: string[]; calendars: SchoolCalendar[] }
export type ScheduleRequest = { id: string; course_id: string; course_title: string; requester: string; kind: string; status: string; reason: string; review_reason: string | null; original: Lesson[]; proposed: Lesson[]; created_at: string }
export type ScheduleEvent = { id: string; course_title: string; reason: string; created_at: string; before: Lesson[]; after: Lesson[] }
export type SchedulePage<T> = { items: T[]; total: number; page: number; page_size: number }
export const dayKey = (value: string | number | Date = Date.now()) => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Shanghai', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(value))
  const get = (name: string) => parts.find(p => p.type === name)!.value
  return `${get('year')}-${get('month')}-${get('day')}`
}
export const addDays = (day: string, amount: number) => new Date(Date.parse(`${day}T12:00:00Z`) + amount * 86400000).toISOString().slice(0, 10)
export const monday = (day: string) => addDays(day, -((new Date(`${day}T12:00:00Z`).getUTCDay() + 6) % 7))
export const clock = (value: string) => new Date(value).toLocaleTimeString('zh-CN', { timeZone: 'Asia/Shanghai', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })
export const stamp = (value: string) => `${dayKey(value)} ${clock(value)}`
export const localInput = (value: string) => `${dayKey(value)}T${clock(value)}`
export const lessonEnd = (lesson: { session_date: string; duration_minutes: number }) => new Date(Date.parse(lesson.session_date) + lesson.duration_minutes * 60000).toISOString()
export const timeState = (lesson: { session_date: string; duration_minutes: number; schedule_status?: string }, now = Date.now()) => lesson.schedule_status === 'cancelled' ? '已停课' : now < Date.parse(lesson.session_date) ? '未开始' : now < Date.parse(lessonEnd(lesson)) ? '正在上课' : '已结束'
