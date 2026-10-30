<script setup lang="ts">
import { createPracticeSubmissionTracker } from './practiceSubmission'
import { prepareTeacherTask } from './teacherTaskRequests'
import { useFloatingAssistant } from './useFloatingAssistant'
import { computed, defineAsyncComponent, nextTick, onMounted, onUnmounted, provide, ref, watch } from 'vue'
import { renderMarkdown } from './useMarkdown'
const AnswerReviewPanel = defineAsyncComponent(() => import('./components/AnswerReviewPanel.vue'))
const ChapterReadings = defineAsyncComponent(() => import('./components/ChapterReadings.vue'))
const AnswerAnnotation = defineAsyncComponent(() => import('./components/AnswerAnnotation.vue'))
const AnswerFeedbackReview = defineAsyncComponent(() => import('./components/AnswerFeedbackReview.vue'))
const AssistantTaskPanel = defineAsyncComponent(() => import('./components/AssistantTaskPanel.vue'))
const PracticePolicyPanel = defineAsyncComponent(() => import('./components/PracticePolicyPanel.vue'))
const QuestionStatistics = defineAsyncComponent(() => import('./components/QuestionStatistics.vue'))
const AssignmentEditor = defineAsyncComponent(() => import('./components/AssignmentEditor.vue'))
import type { AnswerReview } from './answerReview'
import PagedList from './components/PagedList.vue'
import TeacherInsightsPanel from './components/TeacherInsightsPanel.vue'
import TeachingImpactPanel from './components/TeachingImpactPanel.vue'
const CourseEditor = defineAsyncComponent(() => import('./components/CourseEditor.vue'))
const TeachingWorkbench = defineAsyncComponent(() => import('./components/TeachingWorkbench.vue'))
const QuestionOrigin = defineAsyncComponent(() => import('./components/QuestionOrigin.vue'))
import StudentAnswerAnalysisPanel from './components/StudentAnswerAnalysisPanel.vue'
import type { CohortStudent } from './courseCohortAnalysis'
import type { StudentAnswerAnalysisResult } from './studentAnswerAnalysis'
import type { TeachingInsights, TeachingImpact } from './teachingInsights'
import type { StudyPlan, StudyPlanPreferences, StudyPlanTarget } from './studyPlans'
import { acknowledgeAnswer, cancelAnswerRequest, readAnswerReceipt, sendAnswerRequest } from './answerRequests'
import type { AnswerReceipt, AnswerRequestStatus } from './answerRequests'
import PromptComposer from './components/PromptComposer.vue'
import AccountAccess from './components/AccountAccess.vue'
import AccountAvatar from './components/AccountAvatar.vue'
import PlatformUpdates from './components/PlatformUpdates.vue'
const DocumentVersions=defineAsyncComponent(()=>import('./components/DocumentVersions.vue'))
const EvaluationWorkbench=defineAsyncComponent(()=>import('./components/EvaluationWorkbench.vue'))
const DataExports=defineAsyncComponent(()=>import('./components/DataExports.vue'))
import { useAccountAvatar } from './useAccountAvatar'
import type { AccountUser } from './accountAccess'
import AnswerDraftNotice from './components/AnswerDraftNotice.vue'
import { useAnswerDraft } from './useAnswerDraft'
import { useDialogFocus } from './useDialogFocus'
import CourseDirectory from './components/CourseDirectory.vue'
import GradingWorkspace from './components/GradingWorkspace.vue'
import GradingLeaveConfirm from './components/GradingLeaveConfirm.vue'
import StudentHome from './components/StudentHome.vue'
import AssignmentDirectory from './components/AssignmentDirectory.vue'
import QuestionDirectory from './components/QuestionDirectory.vue'
import StudentAssignmentWorkspace from './components/StudentAssignmentWorkspace.vue'
import { dayKey, addDays, stamp, lessonEnd, type Lesson } from './timetable'
const TimetableWorkspace = defineAsyncComponent(() => import('./components/TimetableWorkspace.vue'))
import DetailDialog from './components/DetailDialog.vue'
import UnsavedChangesDialog from './components/UnsavedChangesDialog.vue'
import EditorDraftNotice from './components/EditorDraftNotice.vue'
import DocumentPreview from './components/DocumentPreview.vue'
import { useLocalEditorDraft } from './useLocalEditorDraft'
import { viewMemoryKey } from './viewMemory'
import type { CourseRecord } from './courseCatalog'
import { useConversationViewport } from './useConversationViewport'
import { useMobileViewport } from './useMobileViewport'
import { useMobileNavigation } from './useMobileNavigation'
import type { CalculationReceipt } from './calculations'
import { questionKey } from './questionReviews'
import type { ReviewedChange } from './questionReviews'

const CourseCohortAnalysisPanel = defineAsyncComponent(() => import('./components/CourseCohortAnalysisPanel.vue'))
const PracticeFeedbackPanel = defineAsyncComponent(() => import('./components/PracticeFeedbackPanel.vue'))
const AdminTaskCenter = defineAsyncComponent(() => import('./components/AdminTaskCenter.vue'))
const StudyPlanPanel = defineAsyncComponent(() => import('./components/StudyPlanPanel.vue'))
const TeachingWorkflowPanel = defineAsyncComponent(() => import('./components/TeachingWorkflowPanel.vue'))
const AnswerRecoveryNotice = defineAsyncComponent(() => import('./components/AnswerRecoveryNotice.vue'))
const RichText = defineAsyncComponent(() => import('./components/RichText.vue'))
const AnswerReader = defineAsyncComponent(() => import('./components/AnswerReader.vue'))
const CalculationReceipts = defineAsyncComponent(() => import('./components/CalculationReceipts.vue'))
const QuestionReviewPanel = defineAsyncComponent(() => import('./components/QuestionReviewPanel.vue'))
const AnalysisBasisPanel = defineAsyncComponent(() => import('./components/AnalysisBasisPanel.vue'))
const FeedbackReplaceConfirm = defineAsyncComponent(() => import('./components/FeedbackReplaceConfirm.vue'))
const DashboardTasks = defineAsyncComponent(() => import('./components/DashboardTasks.vue'))
const AccountCenter = defineAsyncComponent(() => import('./components/AccountCenter.vue'))
const AccountManagement = defineAsyncComponent(() => import('./components/AccountManagement.vue'))

type KnowledgeBase = {
  id: string
  name: string
  course: string
  description: string | null
  document_count: number
  created_at: string | null
}

type User = {
  id: string
  username: string
  display_name: string
  role: string
  role_label: string
}

type SystemStatus = {
  auth_required: boolean
  llm_provider: string
  llm_model: string
  llm_configured: boolean
  embedding_provider: string
  indexed_chunks: number
}

type DocumentRecord = {
  id: string
  knowledge_base_id: string
  name: string
  source_url: string | null
  license_name: string | null
  license_url: string | null
  external_model_allowed: boolean
  version_label: string
  publication_status: 'draft' | 'published' | 'archived'
  status: 'pending' | 'ready' | 'error' | string
  page_count: number | null
  chunk_count: number
  error_message: string | null
  created_at: string | null
}
type DocumentContent = { document: DocumentRecord; pages: Array<{ page_number: number; chapter: string | null; content: string; chunks: Array<{ id: string; page_number: number; chapter: string | null; position: number; content: string }> }> }

type DocumentJob = {
  id: string; knowledge_base_id: string; document_id: string; filename: string
  status: 'queued' | 'processing' | 'completed' | 'failed' | 'cancelled'; progress_percent: number; attempts: number
  page_count: number | null; chunk_count: number | null; error_message: string | null
  created_at: string | null; started_at: string | null; finished_at: string | null
}

type Citation = {
  document_id?: string | null
  chunk_id?: string | null
  document_name: string
  page_number: number
  chapter: string | null
  text: string
  score: number
}

type AnswerMode = 'rag' | 'general' | 'hybrid'

type AnswerModeOption = {
  value: AnswerMode
  label: string
  hint: string
  description: string
}

type AssistantMaterialScope = {
  domain_key: string; course_id: string | null; course_title: string | null; course_code: string | null; semester: string | null
  knowledge_base_ids: string[]; knowledge_bases: Array<{ id: string; name: string }>
  storage_knowledge_base_id: string | null; source_document_id: string | null; source_document_name: string | null
  ready_document_count: number; online_document_count: number; notice: string
  requested_knowledge_base_id?: string | null; purpose?: 'course_qa' | 'teaching' | 'management' | null
}
type TutorRestoredScope = { course_id: string | null; course_title?: string | null; requested_knowledge_base_id: string | null; purpose?: AssistantMaterialScope['purpose']; domain_key?: string }
type AskResponse = {
  assignment_context?: AssignmentAssistantContext | null
  answer_review?: AnswerReview | null
  accepted: boolean
  message: string
  answer: string
  model: string
  answer_mode: AnswerMode | null
  citations: Citation[]
  history_id: string | null
  conversation_id: string | null
  answer_scope?: AssistantMaterialScope | null
  calculations?: CalculationReceipt[]
  actions?: Array<{ kind: 'course' | 'assignment' | 'wrong_question' | 'study_plan' | 'teacher_plan' | 'teacher_questions' | 'course_analysis' | 'admin_tasks'; target_id: string; title: string; detail: string; topic?: string | null }>
  favorite?: boolean
  rating?: number | null
  feedback?: string | null
}

type HistoryItem = {
  assignment_context?: AssignmentAssistantContext | null
  answer_review?: AnswerReview | null
  id: string
  answer_mode: AnswerMode | null
  answer_mode_source: 'saved' | 'request_receipt' | 'unknown'
  knowledge_base_id: string | null
  conversation_id: string | null
  assistant_course_id?: string | null
  assistant_scope?: 'course_qa' | 'teaching' | 'management' | null
  context_verified?: boolean
  answer_scope?: AssistantMaterialScope | null
  calculations?: CalculationReceipt[]
  question: string
  answer: string
  message: string
  model: string
  accepted: boolean
  citations: Citation[]
  actions?: NonNullable<AskResponse['actions']>
  rating: number | null
  feedback: string | null
  favorite: boolean
  created_at: string | null
}
type AssistantConversationRecord = { id: string; knowledge_base_id: string | null; title: string; message_count: number; created_at: string | null; updated_at: string | null }
type ConversationMessagePage = { conversation_id: string; knowledge_base_id: string | null; items: HistoryItem[]; message_count: number; has_more: boolean; next_before: string | null }

type QuestionReview = HistoryItem & {
  review_status: 'pending' | 'approved' | 'rejected'
  revised_answer: string | null
  review_note: string | null
  reviewer_name: string | null
  published_document_id: string | null
  reviewed_at: string | null
}

type ClassMember = { enrollment_id: string; user_id: string; username: string; display_name: string; status: string; joined_at: string | null }
type CourseAnnouncement = { id: string; course_id: string; title: string; content: string; author_name: string; published_at: string | null }
type PageResult<T> = { items: T[]; total: number; page: number; page_size: number }

type DashboardSummary = {
  role: string
  course_count: number
  class_count: number
  student_count: number
  pending_tasks: number
  question_count: number
  course_membership_count: number
  pending_review_count: number
  pending_late_count: number
  overdue_unsubmitted_count: number
  document_count: number
  indexed_chunk_count: number
  as_of: string | null
  recent_courses: CourseRecord[]
}

type QuestionItem = {
  id: string; course_id: string; section_id: string | null; question_type: string; stem: string
  options: string[]; correct_answer: string | null; explanation: string | null; difficulty: number; knowledge_point: string | null
}

type AssignmentRecord = {
  revision?: number; ai_policy?: 'disabled' | 'hints' | 'guided'; previous_version_id?: string | null
  source_draft_id?: string | null
  id: string; course_id: string; class_id: string | null; course_title: string; title: string; description: string | null; status: string
  due_at: string | null; question_count: number; submission_count: number; submitted: boolean
  submission_status: string | null; submitted_answers: Record<string, string> | null
  score: number | null; max_score: number | null
  teacher_feedback: string | null; created_at: string | null; questions?: QuestionItem[]
  late_request_status: string | null; late_approved_until: string | null
}
type PublishedAssignmentReview = { assignment_id: string; draft_id: string; title: string; content: string; published_at: string | null; stale: boolean }
type SubmissionDetail = { id: string; assignment_id: string; student_id: string; student_name: string; answers: Record<string, string>; score: number; max_score: number; status: string; feedback: string | null; submitted_at: string | null; graded_at: string | null; grading_version: string }
type LateSubmissionRequest = { id: string; assignment_id: string; assignment_title: string; student_id: string; student_name: string; reason: string; status: string; reviewer_name: string | null; review_note: string | null; approved_until: string | null; requested_at: string | null; reviewed_at: string | null; used_at: string | null }

type WrongQuestionRecord = {
  id: string; question: QuestionItem; wrong_count: number; retry_count: number; correct_streak: number; last_answer: string | null; mastered: boolean; last_practiced_at: string | null; updated_at: string | null
}
type PracticeSource = 'wrong_question' | 'diagnostic' | 'spaced_review' | 'weak_variant' | 'taught_review'
type PracticeRecommendation = { question: QuestionItem; priority: number; reason: string; source: PracticeSource; retry_count: number }
const practiceSourceLabel = (source: PracticeSource) => ({ wrong_question: '错题再练', diagnostic: '新题诊断', spaced_review: '到期复习', weak_variant: '薄弱点变式', taught_review: '已授课巩固' })[source]
type PracticeResult = { attempt_id?: string | null; question_id: string; is_correct: boolean | null; needs_review: boolean; correct_answer: string | null; explanation: string | null; correct_streak: number; mastered: boolean; message: string }

type LearningReport = {
  course_id: string; course_title: string; progress_percent: number; mastery_percent: number
  assignment_count: number; completed_assignments: number; average_score: number; wrong_question_count: number
  completed_sessions: number; session_count: number
  sections: Array<{ section_id: string; section_title: string; progress_percent: number; mastery_percent: number }>
}
type SelectedPassage = { courseId: string; documentId: string; knowledgeBaseId: string; sourceTitle: string; pageNumber: number; text: string }
type StudyNote = { id: string; course_id: string; course_title: string; document_id: string | null; source_title: string; page_number: number; excerpt: string; content: string; origin: 'excerpt' | 'assistant'; source_available: boolean; created_at: string | null }
type CourseSessionRecord = { id: string; course_id: string; section_id: string | null; section_title: string | null; title: string; session_date: string; duration_minutes: number; location: string | null; completed: boolean; schedule_status?: string; revision?: number; rule_id?: string | null }

type CourseAnalytics = {
  course_id: string; course_title: string; student_count: number; assignment_count: number
  submission_rate: number; average_score: number; average_progress: number; weak_knowledge_points: string[]
}

type LinkedKnowledgeBase = { id: string; name: string; course: string; description: string | null; created_at: string | null }
type KnowledgePointRecord = { id: string; course_id: string; section_id: string | null; name: string; description: string | null }
type AdminMetrics = { user_count: number; course_count: number; class_count: number; knowledge_base_count: number; document_count: number; indexed_chunk_count: number; question_count: number; assignment_count: number; rag_question_count: number; average_feedback: number; document_status: Record<string, number> }
type AdminUser = { id: string; username: string; display_name: string; role: 'student' | 'teacher' | 'admin'; active: boolean; created_at: string | null }
type AuditLog = { id: string; actor_name: string; action: string; resource_type: string; resource_id: string | null; detail: Record<string, unknown>; created_at: string | null }
type ModelConfig = { provider: string; model: string; api_base: string; configured: boolean; timeout_seconds: number; fallback_offline: boolean; embedding_provider: string; embedding_model: string; retrieval_top_k: number; retrieval_min_score: number; retrieval_vector_weight: number }
type SecurityOverview = {
  failed_logins_24h: number; rate_limited_requests_24h: number; server_errors_24h: number; average_duration_ms_24h: number
  login_attempts: Array<{ id: string; username: string; ip_address: string; successful: boolean; created_at: string | null }>
  request_logs: Array<{ id: string; request_id: string; method: string; path: string; status_code: number; duration_ms: number; ip_address: string; created_at: string | null }>
}
type EvaluationRun = { id: string; name: string; dataset_version: string; case_count: number; metrics: Record<string, any>; details: Array<Record<string, any>>; created_by: string; created_at: string | null }
type ModelUsageDetail = { upstream_requests: number; tool_attempts: number; token_source: 'provider' | 'estimated' | 'mixed' | 'none' }
type ModelUsageOverview = { days: number; total_calls: number; recorded_upstream_requests: number; upstream_untracked_requests: number; successful_calls: number; failed_calls: number; success_rate: number; input_tokens: number; output_tokens: number; average_duration_ms: number; by_model: Array<{ model: string; calls: number; tokens: number; failures: number }>; recent: Array<{ id: string; role: string; feature: string; model: string; tokens: number; duration_ms: number; successful: boolean; error_type: string | null; created_at: string | null; usage_detail: ModelUsageDetail | null }> }
type ModelQuota = { role: 'student' | 'teacher' | 'admin'; daily_limit: number }
type AssistantAction = { id: string; eyebrow: string; title: string; detail: string; button: string; tone: 'primary' | 'warning' | 'neutral' }
type AssistantTurn = {
  id: number; question: string; displayQuestion: string; courseId: string; courseTitle: string
  passage: SelectedPassage | null; answer: AskResponse | null; error: string; contextChanged: boolean; expanded: boolean; sourcesExpanded: boolean
  partial?: string
  requestId?: string; requestState?: AnswerRequestStatus; sourceDocumentId?: string | null
  checkingReceipt?: boolean
}
type AdminOperationsReport = { period_days: number; generated_at: string; period_start: string; overall_status: 'healthy' | 'warning'; metrics: Record<string, number>; checks: Array<{ id: string; status: 'healthy' | 'warning' | 'neutral'; title: string; detail: string; action_id: string }> }
const adminReportPeriods: Array<1 | 7 | 30> = [1, 7, 30]
type AdminConfirmation = { kind: 'user_status'; userId: string; targetActive: boolean; title: string; detail: string } | { kind: 'user_role'; userId: string; targetRole: AdminUser['role']; title: string; detail: string } | { kind: 'create_admin'; title: string; detail: string } | { kind: 'model_config'; title: string; detail: string } | { kind: 'model_quota'; role: ModelQuota['role']; targetLimit: number; title: string; detail: string } | { kind: 'document_sharing'; documentId: string; allowed: boolean; title: string; detail: string }
type DraftQuestion = { question_type: 'single_choice' | 'multiple_choice' | 'true_false' | 'fill_blank' | 'short_answer'; stem: string; options: string[]; correct_answer: string; explanation: string | null; difficulty: number; knowledge_point: string | null }
type TeachingDraft = { id: string; course_id: string; course_title: string; creator_id: string | null; draft_type: string; title: string; content: string; source_context: Record<string, unknown> & { teaching_quality?: { findings: Array<{message:string}> }; concept_corrections?: Array<{message:string}> }; questions: DraftQuestion[]; status: 'draft' | 'confirmed' | 'archived' | 'published'; confirmed_at: string | null; created_at: string | null; updated_at: string | null }
type DraftEvidence = { document_name: string; page_number: number; chunk_id: string; score: number }
type DraftQualityFinding = { question_index: number; severity: 'error' | 'warning'; code: string; message: string; related_question_index: number | null; related_question_id: string | null }
type DraftQualityReport = { draft_id: string; question_count: number; error_count: number; warning_count: number; findings: DraftQualityFinding[] }

type WorkspacePage = 'dashboard' | 'courses' | 'tutor' | 'assessments' | 'admin' | 'timetable' | 'practice' | 'questionbank' | 'reports'

const apiBase = import.meta.env.VITE_API_BASE ?? ''
const token = ref(localStorage.getItem('rag_token') ?? '')
const logoutBusy=ref(false)
const user = ref<User | null>(null)
const { avatar: accountAvatar, updated: updateAccountAvatar } = useAccountAvatar(apiBase, token, computed(() => user.value?.id || ''))
const accountCenterOpen = ref(false)
const accountManagementOpen = ref(false)
const accountManagementCourse = ref('')
const accountLink = new URLSearchParams(location.hash.slice(1))
const accountInvite = ref(accountLink.get('invite') || '')
const resetLinkSecret = ref(accountLink.get('reset') || '')
if (accountInvite.value || resetLinkSecret.value) window.history.replaceState(null, '', location.pathname + location.search)
watch(user, (value) => { if (value && accountInvite.value && !resetLinkSecret.value) accountCenterOpen.value = true }, { flush: 'post' })
function consumeAccountLink() {
  accountInvite.value = ''
  if (resetLinkSecret.value) { resetLinkSecret.value = ''; resetAuthenticatedSession() }
}
function openAccountManagement(courseId = '') { accountManagementCourse.value = courseId; accountManagementOpen.value = true }
async function accountAuthenticated(result: { access_token: string; browser_session?:string|null; user: AccountUser }) {
  loginError.value = ''; startupError.value = ''
  token.value = result.browser_session ? 'cookie-session:'+result.browser_session : result.access_token
  localStorage.removeItem('rag_token')
  if(!result.browser_session)localStorage.setItem('rag_token',token.value)
  user.value = result.user
  if (user.value.role !== 'admin') setAnswerMode('hybrid')
  try { await loadAppData() } catch (error) { startupError.value = error instanceof Error ? error.message : '数据读取失败，请刷新重试。' }
}
const authChecking = ref(true)
const assistantFab=ref<HTMLElement|null>(null)
useFloatingAssistant(assistantFab)
const startupError = ref('')
const loginUsername = ref('')
const loginPassword = ref('')
const loginError = ref('')
const loginBusy = ref(false)
const clockNow = ref(Date.now())
let clockTimer: number | null = null
const modelStatus = ref<SystemStatus | null>(null)
const question = ref('')
const answerModeStorageKey = 'rag_answer_mode_v2'
const answerMode = ref<AnswerMode>('hybrid')
const selectedFile = ref<File | null>(null)
const documentId = ref(`upload-${Date.now()}`)
const status = ref('')
const answer = ref<AskResponse | null>(null)
const displayedAnswerQuestion = ref('')
const readerAnswer = ref<{ question: string; answer: AskResponse } | null>(null)
const activeConversationId = ref<string | null>(null)
const busy = ref(false)
const answerDraft = ref('')
let answerAbortController: AbortController | null = null
let answerRequestId = 0
const tutorServerRequestId = ref('')
const tutorRequestState = ref<AnswerRequestStatus | null>(null)
const tutorRequestQuestion = ref('')
const tutorRequestContext = ref({ kb: '', mode: '' })
const tutorRestoredScope = ref<TutorRestoredScope | null>(null)
const tutorHistoryNotice = ref('')
const tutorReceiptBusy = ref(false)
const globalAssistantOpen = ref(false)
const { compactViewport, viewportStyle } = useMobileViewport()
const assistantContextExpanded = ref(false)
const mobileSidebar = ref<HTMLElement|null>(null)
const mobileNavigation = useMobileNavigation(mobileSidebar, compactViewport, () =>
  globalAssistantOpen.value || Boolean(document.querySelector('dialog[open], .assignment-modal')))
const mobileNavigationCollapsed = mobileNavigation.collapsed
const mobileNavigationHeight = mobileNavigation.height
const mobileNavigationOnTop = ref(false)
function closeMobileNavigation() {
  mobileNavigationOnTop.value=false; mobileNavigation.hide()
  if(globalAssistantOpen.value) void nextTick(()=>document.querySelector<HTMLButtonElement>('.assistant-nav-entry')?.focus({preventScroll:true}))
}
function openAssistantNavigation() {
  mobileNavigationOnTop.value=true; mobileNavigation.reveal()
  void nextTick(()=>mobileSidebar.value?.querySelector<HTMLButtonElement>('.mobile-nav-dismiss')?.focus({preventScroll:true}))
}
watch(compactViewport,()=>{mobileNavigationOnTop.value=false})
watch([globalAssistantOpen, compactViewport], ([open, compact]) => {
  document.body.classList.toggle('mobile-assistant-open', open && compact)
  if (open && compact) void nextTick(() => {
    const panel = document.getElementById('global-ai-assistant')
    if (panel && !panel.contains(document.activeElement)) panel.focus({ preventScroll: true })
  })
}, { flush: 'post' })
function assistantMobileKeys(event: KeyboardEvent) {
  if (!compactViewport.value || event.isComposing) return
  if (event.key === 'Escape') {
    event.preventDefault()
    if (assistantInline.value) activePage.value = 'dashboard'
    else globalAssistantOpen.value = false
  }
  if (event.key !== 'Tab') return
  const panel = event.currentTarget as HTMLElement
  const items = Array.from(panel.querySelectorAll<HTMLElement>('button:not(:disabled),input:not(:disabled),textarea:not(:disabled),select:not(:disabled),[href],summary,[tabindex="0"]')).filter(item => item.getClientRects().length > 0)
  const first = items[0], last = items.at(-1)
  if (!first) { event.preventDefault(); panel.focus(); return }
  if (event.shiftKey && (document.activeElement === first || document.activeElement === panel)) { event.preventDefault(); last?.focus() }
  else if (!event.shiftKey && (document.activeElement === last || document.activeElement === panel)) { event.preventDefault(); first.focus() }
}
const assistantView = ref<'chat' | 'tools' | 'history'>('chat')
const assistantTurns = ref<AssistantTurn[]>([])
const assistantHistory = ref<AssistantConversationRecord[]>([])
const assistantHistoryQuery = ref('')
const assistantHistoryHasMore = ref(false)
const filteredAssistantHistory = computed(() => assistantHistory.value)
const assistantHistoryBusy = ref(false)
const assistantHistoryError = ref('')
const assistantActionError = ref('')
const assistantHistoryScopeNotice = ref('')
const assistantChatScroll = ref<HTMLElement | null>(null)
const assistantViewport = useConversationViewport(assistantChatScroll, () => globalAssistantOpen.value && assistantView.value === 'chat')
const assistantPagedConversationId = ref<string | null>(null)
const assistantMessageBefore = ref<string | null>(null)
const assistantMessageHasMore = ref(false)
const assistantMessageCount = ref<number | null>(null)
const assistantOlderBusy = ref(false)
const assistantOlderError = ref('')
let assistantOlderSequence = 0
let assistantOlderController: AbortController | null = null
let assistantArchiveTurnId = 0
const assistantLoadedMessageCount = computed(() => new Set(assistantTurns.value
  .filter(item => item.answer?.conversation_id === assistantPagedConversationId.value)
  .map(item => item.answer?.history_id).filter(Boolean)).size)
const assistantFollowing = ref(true)
const assistantContentBelow = ref(false)
const assistantHasUnread = ref(false)
const assistantWaitSeconds = ref(0)
const assistantWaitLabel = ref('正在准备请求…')
const assistantNoteTurnId = ref<number | null>(null)
const assistantPendingContextChange = ref(false)
let assistantRequestId = 0
let assistantAbortController: AbortController | null = null
let assistantWaitTimer: number | null = null
let assistantHistoryRequestId = 0
let assistantHistoryController: AbortController | null = null
let assistantHistorySearchTimer: ReturnType<typeof setTimeout> | null = null
const globalAssistantQuestion = ref('')
const globalAssistantAnswer = ref<AskResponse | null>(null)
const globalAssistantBusy = ref(false)
const globalAssistantConversationId = ref<string | null>(null)
const assistantConversationKnowledgeBaseId = ref<string | null>(null)
const loadingCatalog = ref(true)
const knowledgeBases = ref<KnowledgeBase[]>([])
const documents = ref<DocumentRecord[]>([])
const documentTotal = ref(0)
const documentJobs = ref<DocumentJob[]>([])
const selectedDocumentContent = ref<DocumentContent | null>(null)
const versionDocumentId=ref('')
const documentPreviewTargetPage = ref<number | null>(null)
const documentOpening = ref<string | null>(null)
const documentOpenError = ref<{ id: string; page: number | null; message: string } | null>(null)
let documentReadSequence = 0
let documentReadController: AbortController | null = null
function cancelDocumentOpen() { documentReadSequence += 1; documentReadController?.abort(); documentOpening.value = null; documentOpenError.value = null }
const selectedPassage = ref<SelectedPassage | null>(null)
const assistantAnswerPassage = ref<SelectedPassage | null>(null)
const studyNoteDraft = ref('')
const studyNoteBusy = ref(false)
const studyNoteStatus = ref('')
const studyNoteStatusError = ref(false)
const documentSourceUrl = ref('')
const documentLicenseName = ref('')
const documentLicenseUrl = ref('')
const documentVersion = ref('1.0')
const documentPublicationStatus = ref<'draft' | 'published' | 'archived'>('published')
const history = ref<HistoryItem[]>([])
const tutorHistoryBusy = ref(false)
let documentLoadSequence = 0
let historyLoadSequence = 0
let catalogLoadSequence = 0
const indexedChunks = ref(0)
const selectedKnowledgeBaseId = ref('')
const showCreateForm = ref(false)
const showMobileCatalog = ref(false)
const newKnowledgeBaseName = ref('')
const newKnowledgeBaseCourse = ref('数据结构与算法')
const newKnowledgeBaseDescription = ref('')
const feedbackBusy = ref(false)
const activePage = ref<WorkspacePage>('dashboard')
const timetableFocusId = ref(''), timetableCourseFocus = ref('')
const timetableWorkspace = ref<InstanceType<typeof TimetableWorkspace> | null>(null), timetableDirty=ref(false), timetableSaving=ref(false)
const assignmentCourseFilter=ref('')
const assignmentCreateOpen=ref(false),questionEditorOpen=ref(false),lateApprovalOpen=ref(false)
const questionPreview=ref<QuestionItem|null>(null),pendingQuestionDelete=ref<QuestionItem|null>(null)
const pendingAssignmentStatus=ref<'draft'|'published'|'closed'|null>(null)
function closeAssignmentCreate() { if(guardFormExit(closeAssignmentCreate,'关闭作业创建',['assignment-create'],true))assignmentCreateOpen.value=false }
function closeQuestionEditor() { if(guardFormExit(closeQuestionEditor,'关闭题目编辑',['question-editor'],true))questionEditorOpen.value=false }
function prepareAssessmentAI() { openUnifiedAssistant();assistantView.value='tools' }
watch([assignmentCreateOpen,questionEditorOpen,pendingQuestionDelete,pendingAssignmentStatus],([create,edit,remove,status])=>{if(create||edit||remove||status)platformStatus.value=''})
async function assignmentPickerPage(page:number,pageSize:number):Promise<PageResult<QuestionItem>> {
  if(!newAssignmentCourseId.value)return {items:[],total:0,page:1,page_size:pageSize}
  return request(`/api/v1/questions/page?${new URLSearchParams({course_id:newAssignmentCourseId.value,page:String(page),page_size:String(pageSize)})}`)
}
function openTimetableSession(id: string) { selectedCourse.value=null; timetableFocusId.value=''; activePage.value='timetable'; void nextTick(()=>{timetableFocusId.value=id}) }
function openTimetableCourse(id: string) { selectedCourse.value=null;timetableCourseFocus.value='';activePage.value='timetable';void nextTick(()=>{timetableCourseFocus.value=id}) }
async function timetableAction(kind: string, lesson: Lesson) {
  const course=platformCourses.value.find(x=>x.id===lesson.course_id)
  if(kind==='assistant') {
    assistantDraftCourseId.value=lesson.course_id
    openUnifiedAssistant()
    globalAssistantQuestion.value=`已查到的平台课次：${lesson.course_title} · ${lesson.title}${lesson.section_title?'（'+lesson.section_title+'）':''}；北京时间 ${stamp(lesson.session_date)} 至 ${stamp(lessonEnd(lesson))}，${lesson.location||'场地待通知'}，${lesson.teacher_name||'教师待公布'}，${lesson.schedule_status==='cancelled'?'已停课':lesson.completed?'已确认授课':'尚未确认授课'}。请结合课程资料，${user.value?.role==='teacher'?'帮我准备这一课的教学重点、课堂活动与练习':user.value?.role==='admin'?'帮我梳理本节课的管理核对事项，未查询的信息请勿猜测':'帮我预习这一课，梳理关键知识与自测问题'}。如需调课，只能提交申请并由管理员审批，不要声称已替我修改安排。`
  } else if(kind==='assignments') { assignmentCourseFilter.value=lesson.course_id;activePage.value='assessments';learningTab.value='assignments' }
  else if(course) { await openCourseDetail(course);if(kind==='materials')courseDetailTab.value='materials' }
}
const visitedPages = ref(new Set<WorkspacePage>(['dashboard']))
const listViewMemory = new Map<string, unknown>()
provide(viewMemoryKey, { values: listViewMemory, owner: () => `${user.value?.id || ''}:${user.value?.role || ''}`, page: () => activePage.value })
const workspaceScroll = new Map<string, number>()
let workspaceScrollTicket = 0
const tutorPane = ref<'assistant' | 'materials'>('assistant')
const assistantInline = computed(() => activePage.value === 'tutor' && tutorPane.value === 'assistant')
const assistantPreferredMode = ref<AnswerMode | null>(null)
const assistantActiveMode = computed<AnswerMode>(() => assistantConversationAnswerMode.value ?? assistantPreferredMode.value ?? (user.value?.role === 'admin' ? 'general' : 'hybrid'))
watch(tutorPane, (pane) => {
  if (activePage.value === 'tutor') globalAssistantOpen.value = pane === 'assistant'
}, { flush: 'sync' })
function openUnifiedAssistant() {
  activePage.value = 'tutor'
  if (activePage.value !== 'tutor') return
  tutorPane.value = 'assistant'
  assistantView.value = 'chat'
  globalAssistantOpen.value = true
}
function openMaterialWorkspace() {
  activePage.value = 'tutor'
  if (activePage.value !== 'tutor') return
  tutorPane.value = 'materials'
  globalAssistantOpen.value = false
}
function setAssistantMode(mode: AnswerMode) {
  if (globalAssistantBusy.value || assistantHistoryBusy.value || assistantOlderBusy.value || mode === assistantActiveMode.value) return
  assistantPreferredMode.value = mode
  clearAssistantMessagePaging()
  if (assistantTurns.value.length) assistantPendingContextChange.value = true
  globalAssistantConversationId.value = null
  assistantConversationKnowledgeBaseId.value = null
  assistantConversationDomainKey.value = ''
  assistantConversationAnswerMode.value = null
  assistantHistoryScopeNotice.value = '已切换回答模式，下一问将开启新会话；原回答仍可查看。'
}
const dashboardSummary = ref<DashboardSummary | null>(null)
const dashboardTaskKind = ref<'review' | 'late' | 'overdue'>('review')
const dashboardRefreshing = ref(false)
const dashboardError = ref('')
const platformLoading = ref(false)
const assignmentOpenPending = ref(0)
const platformLoadError = ref('')
const studentHome = ref<InstanceType<typeof StudentHome> | null>(null)
const homeAssignmentOpening = ref('')
let homeAssignmentReturn: { id: string; top: number; focus: HTMLElement | null } | null = null
const dashboardTeachingTasks = ref<HTMLElement | null>(null)
const homeLateApprovalPanel = ref<HTMLElement | null>(null)
const homeLateAssignmentId = ref('')
const homeLateAssignmentTitle = ref('')
let dashboardRequestSequence = 0
let dashboardController: AbortController | null = null
let platformDataSequence = 0
let questionPageSequence = 0
const platformCourses = ref<CourseRecord[]>([])
const courseCatalogFocus = ref<'all' | 'missing'>('all')
const courseCatalogFocusRevision = ref(0)
const courseCatalogRevision = ref(0)
function openCourseCatalog(focus: 'all' | 'missing' = 'all') {
  activePage.value = 'courses'
  if (activePage.value !== 'courses') return
  selectedCourse.value = null
  courseCatalogFocus.value = focus
  courseCatalogFocusRevision.value += 1
  globalAssistantOpen.value = false
}
const newCourseTitle = ref('')
const newCourseCode = ref('')
const newCourseDescription = ref('')
const newCourseSemester = ref('2026-2027 第一学期')
const newCourseCover = ref('')
const platformBusy = ref(false)
const pendingAdminConfirmation = ref<AdminConfirmation | null>(null)
const platformStatus = ref('')
const questionBank = ref<QuestionItem[]>([])
const questionPageItems = ref<QuestionItem[]>([])
const questionPageTotal = ref(0)
const questionPageIndex = ref(1)
const questionFilterCourse = ref('')
const questionFilterType = ref('')
const questionFilterKeyword = ref('')
const questionPageCount = computed(() => Math.max(1, Math.ceil(questionPageTotal.value / 10)))
const assignments = ref<AssignmentRecord[]>([])
const assessmentRevision=ref(0)
watch(assignments,()=>assessmentRevision.value++)
const wrongQuestions = ref<WrongQuestionRecord[]>([])
const practiceRecommendations = ref<PracticeRecommendation[]>([])
const practiceDraft = useAnswerDraft()
const practiceAnswers = practiceDraft.answers
const practiceResults = ref<Record<string, PracticeResult>>({})
const selectedPractice = ref<PracticeRecommendation | null>(null)
const lastPractice=ref<PracticeRecommendation|null>(null)
const practicePlanAttemptId = ref<string | null>(null)
const practiceCoachBusy = ref(false)
watch(token, () => {
  selectedCourse.value = null
  homeAssignmentReturn = null
  if (gradingSaving.value) platformBusy.value = false
  gradingSaving.value = false
  pendingGradingExit.value = null
  assignmentSubmissionsRequestId += 1
  assignmentSubmissionsLoading.value = false
  selectedSubmission.value = null
  assignmentDraft.release()
  selectedAssignment.value = null
  assignmentAnswers.value = {}
  practiceDraft.release()
  selectedPractice.value = null
  practicePlanAttemptId.value = null
  practiceAnswers.value = {}
  practiceResults.value = {}
  practiceCoachBusy.value = false
})
const learningTab = ref<'assignments' | 'questions' | 'practice' | 'wrong' | 'reviews' | 'reports'>('assignments')
const visitedLearningTabs = ref(new Set<string>(['assignments']))
watch(learningTab, async (next, previous) => {
  visitedLearningTabs.value.add(next)
  if (activePage.value !== 'assessments') return
  workspaceScroll.set(`assessments:${previous}`, window.scrollY)
  const ticket = ++workspaceScrollTicket
  await nextTick()
  if (activePage.value === 'assessments' && learningTab.value === next && ticket === workspaceScrollTicket) window.scrollTo({ top: workspaceScroll.get(`assessments:${next}`) || 0, behavior: 'instant' })
}, { flush: 'sync' })
const selectedAssignment = ref<AssignmentRecord | null>(null)
let assignmentOpenRequestId = 0
const assignmentPublishedReview = ref<PublishedAssignmentReview | null>(null)
const assignmentReviewBusy = ref(false)
const assignmentReviewMessage = ref('')
const assignmentDraft = useAnswerDraft()
const assignmentAnswers = assignmentDraft.answers
const assignmentDialog = ref<HTMLElement | null>(null)
const practiceDialog = ref<HTMLElement | null>(null)
const draftCloseWarning = ref<'assignment' | 'practice' | null>(null)
watch([assignmentDraft.error, practiceDraft.error], ([assignmentError, practiceError]) => {
  if ((draftCloseWarning.value === 'assignment' && !assignmentError) ||
      (draftCloseWarning.value === 'practice' && !practiceError)) draftCloseWarning.value = null
}, { flush: 'sync' })
function closeAnswerDialog(kind: 'assignment' | 'practice', force = false) {
  if (user.value?.role === 'student' && platformBusy.value) return false
  if (kind === 'assignment' && !guardFormExit(() => closeAnswerDialog(kind, force), '关闭作业', ['assignment-late'])) return false
  if (kind === 'assignment' && !guardGradingExit(() => closeAnswerDialog(kind, force), '关闭作业')) return false
  const draft = kind === 'assignment' ? assignmentDraft : practiceDraft
  if (!force && !draft.persist() && draft.hasContent.value) { draftCloseWarning.value = kind; return false }
  draftCloseWarning.value = null
  draft.release()
  if (kind === 'assignment') {
    pendingAssignmentStatus.value=null
    const returnPoint = homeAssignmentReturn?.id === selectedAssignment.value?.id ? homeAssignmentReturn : null
    homeAssignmentReturn = null
    assignmentOpenRequestId += 1; selectedAssignment.value = null; selectedSubmission.value = null
    if (returnPoint) {
      activePage.value = 'dashboard'
      void nextTick(() => window.requestAnimationFrame(() => {
        if (activePage.value !== 'dashboard') return
        window.scrollTo({ top: returnPoint.top, behavior: 'instant' })
        if (returnPoint.focus?.isConnected) returnPoint.focus.focus({ preventScroll: true })
      }))
    }
  }
  else selectedPractice.value = null
  return true
}
function saveAnswerDraftsBeforeExit(next?: () => void, label = '离开批改') {
  if (!guardGradingExit(next, label)) return false
  if (!guardFormExit(next || (() => {}), label, undefined, label === '退出账号')) return false
  if (user.value?.role === 'student' && platformBusy.value && (selectedAssignment.value || selectedPractice.value)) return false
  for (const [kind, draft] of [['assignment', assignmentDraft], ['practice', practiceDraft]] as const) {
    if (!draft.persist() && draft.hasContent.value) { draftCloseWarning.value = kind; return false }
  }
  return true
}
useDialogFocus(assignmentDialog, () => closeAnswerDialog('assignment'), () => !globalAssistantOpen.value && !pendingGradingExit.value)
useDialogFocus(practiceDialog, () => closeAnswerDialog('practice'), () => !globalAssistantOpen.value)
let restoringWorkspacePage = false
watch(activePage, async (page, previous) => {
  if (restoringWorkspacePage) return
  if (!saveAnswerDraftsBeforeExit(() => { activePage.value = page }, '切换栏目')) {
    restoringWorkspacePage = true; activePage.value = previous; restoringWorkspacePage = false
    return
  }
  if (previous === 'tutor') assistantViewport.save()
  if (page === 'tutor') { tutorPane.value = 'assistant'; assistantView.value = 'chat'; globalAssistantOpen.value = true }
  else if (previous === 'tutor') globalAssistantOpen.value = false
  if (page !== 'assessments') {
    assignmentOpenRequestId += 1
    assignmentDraft.release(); practiceDraft.release()
    selectedAssignment.value = null; selectedPractice.value = null
  }
  if (page !== 'assessments' && page !== 'dashboard') homeAssignmentReturn = null
  workspaceScroll.set(previous === 'assessments' ? `assessments:${learningTab.value}` : previous === 'admin' ? `admin:${adminTab.value}` : previous, window.scrollY)
  visitedPages.value.add(page)
  const scrollTicket = ++workspaceScrollTicket
  await nextTick()
  if (activePage.value === page && scrollTicket === workspaceScrollTicket) window.scrollTo({ top: workspaceScroll.get(page === 'assessments' ? `assessments:${learningTab.value}` : page === 'admin' ? `admin:${adminTab.value}` : page) || 0, left: 0, behavior: 'instant' })
}, { flush: 'sync' })
const submissionMessage = ref('')
const newQuestionStem = ref('')
const newQuestionType = ref<'single_choice' | 'multiple_choice' | 'true_false' | 'fill_blank' | 'short_answer'>('single_choice')
const newQuestionOptions = ref('')
const newQuestionAnswer = ref('')
const newQuestionPoint = ref('')
const newQuestionCourseId = ref('')
const newQuestionExplanation = ref('')
const newQuestionDifficulty = ref(2)
const editingQuestionId = ref('')
const newAssignmentTitle = ref('')
const newAssignmentCourseId = ref('')
const selectedQuestionIds = ref<string[]>([])
const assignmentQuestionOptions = computed(() => questionBank.value.filter(item => item.course_id === newAssignmentCourseId.value))
const newAssignmentDueAt = ref('')
const assignmentSubmissions = ref<SubmissionDetail[]>([])
const lateSubmissionRequests = ref<LateSubmissionRequest[]>([])
const lateRequestReason = ref('')
const selectedSubmission = ref<SubmissionDetail | null>(null)
const studentAnswerAnalysis = ref<StudentAnswerAnalysisResult<TeachingDraft> | null>(null)
const studentAnswerAnalysisBusy = ref(false)
const studentAnswerAnalysisLoading = ref(false)
const studentAnswerAnalysisError = ref('')
const studentAnswerTaskMessage = ref('')
const reviewFeedbackOnly = ref(false)
let studentAnswerAnalysisRequestId = 0
let studentAnswerAnalysisController: AbortController | null = null
watch(() => [selectedAssignment.value?.id, selectedSubmission.value?.id, selectedSubmission.value?.status,
  selectedSubmission.value?.score, selectedSubmission.value?.feedback], () => {
  studentAnswerAnalysisRequestId += 1
  studentAnswerAnalysisController?.abort()
  studentAnswerAnalysis.value = null
  studentAnswerAnalysisBusy.value = false
  studentAnswerAnalysisLoading.value = false
  studentAnswerAnalysisError.value = ''
  studentAnswerTaskMessage.value = ''
  if (selectedSubmission.value && selectedAssignment.value && user.value?.role !== 'student') void loadStudentAnswerAnalysis()
})
const gradeScore = ref(0)
const gradeFeedback = ref('')
type GradeEdit = { score: number; feedback: string; version: string }
const gradingDraft = useLocalEditorDraft<GradeEdit>(value => { const item = value as GradeEdit | null; return !!item && Number.isFinite(item.score) && typeof item.feedback === 'string' && item.feedback.length <= 5000 && typeof item.version === 'string' })
let applyingGradeDraft = false
const gradingRemoteChanged = ref<SubmissionDetail | null>(null)
const gradingResultUnknown = ref(false)
watch([gradeScore, gradeFeedback], () => {
  if (!applyingGradeDraft && selectedSubmission.value && user.value?.role !== 'student') gradingDraft.set({ score: gradeScore.value, feedback: gradeFeedback.value, version: selectedSubmission.value.grading_version })
}, { flush: 'sync' })
function applyGradeDraft() {
  const value = gradingDraft.value.value
  if (!value || !Number.isFinite(value.score) || typeof value.feedback !== 'string' || value.feedback.length > 5000) return
  applyingGradeDraft = true; gradeScore.value = value.score; gradeFeedback.value = value.feedback; applyingGradeDraft = false
  if (selectedSubmission.value) gradingDraft.set({ score: value.score, feedback: value.feedback, version: selectedSubmission.value.grading_version })
}
function recoverGradeDraft() { gradingDraft.recover(); applyGradeDraft() }
function acceptRemoteGrade(keepEdit: boolean) {
  if (!gradingRemoteChanged.value) return
  const currentEdit = { score: gradeScore.value, feedback: gradeFeedback.value }
  const latest = gradingRemoteChanged.value
  selectedSubmission.value = latest
  gradingRemoteChanged.value = null; gradingResultUnknown.value = false
  gradingDraft.clear()
  gradingDraft.open(user.value!.id, 'grading', latest.id, { score: latest.score, feedback: latest.feedback || '', version: latest.grading_version })
  applyingGradeDraft = true
  gradeScore.value = keepEdit ? currentEdit.score : latest.score
  gradeFeedback.value = keepEdit ? currentEdit.feedback : latest.feedback || ''
  applyingGradeDraft = false
  gradingDraft.set({ score: gradeScore.value, feedback: gradeFeedback.value, version: latest.grading_version }); gradingDraft.persist()
  submissionMessage.value = keepEdit ? '已以最新记录为基线保留本机编辑，请核对后明确保存。' : '已采用服务器最新记录。'
}
const gradingSaving = ref(false)
const assignmentSubmissionsLoading = ref(false)
const assignmentSubmissionsError = ref('')
let assignmentSubmissionsRequestId = 0
const assignmentManagerPane = ref<'overview' | 'grading' | 'questions' | 'review' | 'settings'>('overview')
const pendingGradingExit = ref<{ token: string; assignmentId: string; submissionId: string; next?: () => void; label: string } | null>(null)
const gradingDirty = computed(() => user.value?.role !== 'student' && Boolean(selectedAssignment.value && selectedSubmission.value && selectedAssignment.value.id === selectedSubmission.value.assignment_id) &&
  (gradeScore.value !== selectedSubmission.value!.score || gradeFeedback.value !== (selectedSubmission.value!.feedback || '')))
const gradeValid = computed(() => Boolean(selectedSubmission.value) && Number.isFinite(gradeScore.value) && gradeScore.value >= 0 && gradeScore.value <= selectedSubmission.value!.max_score && gradeFeedback.value.length <= 5000)
function guardGradingExit(next?: () => void, label = '离开批改') {
  if (gradingSaving.value) { submissionMessage.value = '批改正在保存，请等待结果确认后再离开。'; return false }
  gradingDraft.persist()
  if (!gradingDirty.value || !selectedAssignment.value || !selectedSubmission.value) return true
  pendingGradingExit.value = { token: token.value, assignmentId: selectedAssignment.value.id, submissionId: selectedSubmission.value.id, next, label }
  return false
}
function discardGradingAndContinue() {
  const pending = pendingGradingExit.value
  pendingGradingExit.value = null
  if (!pending || pending.token !== token.value || pending.assignmentId !== selectedAssignment.value?.id || pending.submissionId !== selectedSubmission.value?.id || gradingSaving.value) return
  gradeScore.value = selectedSubmission.value!.score
  gradeFeedback.value = selectedSubmission.value!.feedback || ''
  gradingDraft.clear(); gradingDraft.release(); gradingRemoteChanged.value = null; gradingResultUnknown.value = false
  pending.next?.()
}
function stashGradingAndContinue() {
  const pending = pendingGradingExit.value
  if (!pending || pending.token !== token.value || pending.submissionId !== selectedSubmission.value?.id || pending.assignmentId !== selectedAssignment.value?.id || gradingSaving.value) return
  if (!gradingDraft.persist() || gradingDraft.recovery.value || gradingDraft.changedElsewhere.value) { pendingGradingExit.value = null; submissionMessage.value = '本机草稿尚未安全暂存，请处理草稿提示或复制内容后再离开。'; return }
  pendingGradingExit.value = null
  applyingGradeDraft = true; gradeScore.value = selectedSubmission.value!.score; gradeFeedback.value = selectedSubmission.value!.feedback || ''; applyingGradeDraft = false
  pending.next?.()
}
function warnBeforeGradingUnload(event: BeforeUnloadEvent) {
  gradingDraft.persist(); teachingEditorDraft.persist()
  if (gradingDirty.value || gradingSaving.value || dirtyFormGroups(true).length || platformBusy.value) { event.preventDefault(); event.returnValue = '' }
}
watch(() => [token.value, selectedAssignment.value?.id, selectedSubmission.value?.id], () => { pendingGradingExit.value = null })
const pendingStudentFeedback = ref<{ token: string; submissionId: string; analysisId: string; previous: string; value: string } | null>(null)
watch(() => [token.value, selectedAssignment.value?.id, selectedSubmission.value?.id, studentAnswerAnalysis.value?.draft.id], () => { pendingStudentFeedback.value = null })
const questionReviews = ref<QuestionReview[]>([])
const reviewEdits = new Map<string, { item: QuestionReview; baseline: { revised_answer: string | null; review_note: string | null } }>()
function trackReviewItems(items: QuestionReview[]) {
  for (const item of items) {
    const previous = reviewEdits.get(item.id)
    const baseline = { revised_answer: item.revised_answer, review_note: item.review_note }
    if (previous && JSON.stringify([previous.item.revised_answer, previous.item.review_note]) !== JSON.stringify([previous.baseline.revised_answer, previous.baseline.review_note])) Object.assign(item, { revised_answer: previous.item.revised_answer, review_note: previous.item.review_note })
    reviewEdits.set(item.id, { item, baseline: previous && JSON.stringify([previous.item.revised_answer, previous.item.review_note]) !== JSON.stringify([previous.baseline.revised_answer, previous.baseline.review_note]) ? previous.baseline : baseline })
  }
}
const pendingReviewCount = ref(0)
const learningReports = ref<LearningReport[]>([])
const studentStudyPlans = ref<StudyPlan[]>([])
const studentStudyNotes = ref<StudyNote[]>([])
const studyPlanBusy = ref(false)
const selectedLearningSection = ref<{ report: LearningReport; section: LearningReport['sections'][number] } | null>(null)
const courseAnalytics = ref<CourseAnalytics | null>(null)
const selectedCourse = ref<CourseRecord | null>(null)
const selectedCoursePoint = ref<KnowledgePointRecord | null>(null)
const courseEditorId = ref(''), courseEditorDirty = ref(false), courseEditorSaving = ref(false)
const courseEditorPanel = ref<InstanceType<typeof CourseEditor> | null>(null)
const workbenchOpen = ref(false), workbenchDirty = ref(false), workbenchSaving = ref(false)
const workbenchPanel = ref<InstanceType<typeof TeachingWorkbench> | null>(null)
const workbenchConfig = ref<{ tab:'materials'|'course'|'schedule'|'history'; courseId:string; prompt:string; resultId:string }>({tab:'materials',courseId:'',prompt:'',resultId:''})
let workbenchChanged = false
function openTeachingWorkbench(tab:'materials'|'course'|'schedule'|'history', prompt='', resultId='', courseId='') {
  if (!canManage.value) return
  if (workbenchOpen.value && workbenchDirty.value && !window.confirm('有未保存的工作编辑，确定切换？')) return
  workbenchConfig.value = {tab, prompt, resultId, courseId:courseId || selectedCourse.value?.id || assistantDraftCourseId.value || platformCourses.value[0]?.id || ''}
  workbenchChanged=false;workbenchOpen.value=true
}
function closeTeachingWorkbench() {
  workbenchOpen.value=false;workbenchDirty.value=false;workbenchSaving.value=false
  assistantTasksRevision.value++
  if (workbenchChanged) { void loadPlatformData(); if (selectedCourse.value) void openCourseDetail(selectedCourse.value) }
}
function openCourseAssistant() {
  const id=courseEditorId.value
  courseEditorId.value='';courseEditorDirty.value=false;courseEditorSaving.value=false
  openTeachingWorkbench('course','','',id)
}
async function openWorkbenchDraft(id:string) { closeTeachingWorkbench(); await nextTick(); await openCohortDraft(id) }
async function editWorkbenchCourse(id:string) {
  closeTeachingWorkbench(); await nextTick()
  const course=await request<CourseRecord>(`/api/v1/courses/${id}`)
  await openCourseDetail(course);openCourseEditor()
}
let courseEditorChanged = false
function openCourseEditor() {
  if (!selectedCourse.value || !guardFormExit(openCourseEditor, '编辑课程', ['course'])) return
  courseEditorChanged = false; courseEditorId.value = selectedCourse.value.id
}
function closeCourseEditor(materials = false) {
  const course = selectedCourse.value
  courseEditorId.value = ''; courseEditorDirty.value = false; courseEditorSaving.value = false
  if (materials) { selectedCourse.value = null; openMaterialWorkspace() }
  else if (courseEditorChanged && course) { void openCourseDetail(course); void loadPlatformData() }
}
const courseDetailTab = ref<'overview' | 'materials' | 'sessions' | 'members'>('overview')
const courseDetailLoading = ref(false)
const courseDetailError = ref('')
let courseDetailRequestId = 0
let courseDetailController: AbortController | null = null
watch(selectedCourse, (current, previous) => {
  if (!current && previous) {
    courseDetailRequestId += 1
    courseDetailController?.abort()
    courseDetailLoading.value = false
    courseCatalogRevision.value += 1
  }
})
function closeCourseDetail() { if (guardFormExit(closeCourseDetail, '关闭课程详情', ['course'])) selectedCourse.value = null }
const courseMembers = ref<ClassMember[]>([])
const newCourseMemberUsername = ref('')
const selectedOutlineSection = ref<CourseRecord['sections'][number] | null>(null)
const courseAnnouncements = ref<CourseAnnouncement[]>([])
const announcementPageIndex = ref(1)
const announcementTotal = ref(0)
const announcementPageCount = computed(() => Math.max(1, Math.ceil(announcementTotal.value / 5)))
const editingAnnouncementId = ref('')
const announcementStatus = ref('')
const newAnnouncementTitle = ref('')
const newAnnouncementContent = ref('')
const courseKnowledgeBases = ref<LinkedKnowledgeBase[]>([])
const courseMaterials = ref<DocumentRecord[]>([])
const courseSessions = ref<CourseSessionRecord[]>([])
const studentCourseSessions = ref<CourseSessionRecord[]>([])
const newSessionTitle = ref('')
const newSessionDate = ref('')
const newSessionLocation = ref('')
const newSessionSectionId = ref('')
const courseKnowledgePoints = ref<KnowledgePointRecord[]>([])
const adminMetrics = ref<AdminMetrics | null>(null)
const adminUsers = ref<AdminUser[]>([])
const pendingRoleChanges = ref<Record<string, AdminUser['role']>>({})
const adminRoleReason = ref('')
const adminQuotaReason = ref('')
const documentSharingReason = ref('')
const auditLogs = ref<AuditLog[]>([])
const adminModelConfig = ref<ModelConfig | null>(null)
const modelConfigBaseline = ref<ModelConfig | null>(null)
const securityOverview = ref<SecurityOverview | null>(null)
const evaluationRuns = ref<EvaluationRun[]>([])
const modelUsageOverview = ref<ModelUsageOverview | null>(null)
const modelQuotas = ref<ModelQuota[]>([])
const modelQuotaDrafts = ref<Record<ModelQuota['role'], number>>({ student: 0, teacher: 0, admin: 0 })
const adminInsights = ref<AssistantAction[]>([])
const adminReport = ref<AdminOperationsReport | null>(null)
const adminReportBusy = ref(false)
const adminReportError = ref('')
const teachingDrafts = ref<TeachingDraft[]>([])
const activeTeachingDrafts = computed(() => teachingDrafts.value.filter(item => item.status !== 'archived'))
const selectedTeachingDraft = ref<TeachingDraft | null>(null)
const teachingDraftFeedback = ref({ message: '', error: false })
const draftQualityReport = ref<DraftQualityReport | null>(null)
const draftQualityFingerprint = ref('')
const draftQualityBusy = ref(false)
const draftAIReviewConsent = ref(false)
const draftGenerateCourseId = ref('')
const draftGenerateTopic = ref('')
const draftShareCourseMaterials = ref(false)
const draftGenerateType = ref<'teaching_plan' | 'lesson_plan' | 'question_set'>('teaching_plan')
const assistantDraftCourseId = ref('')
const assistantMaterialScope = ref<AssistantMaterialScope | null>(null)
const assistantMaterialScopeBusy = ref(false)
const assistantMaterialScopeError = ref('')
const assistantConversationDomainKey = ref('')
const assistantConversationAnswerMode = ref<AnswerMode | null>(null)
let assistantMaterialSequence = 0
let assistantMaterialController: AbortController | null = null
const studentCourseKnowledgeBases = ref<Record<string, LinkedKnowledgeBase[]>>({})
const assistantDraftTopic = ref('')
const assistantShareCourseMaterials = ref(false)
const assistantDraftBusy = ref(false)
const assignmentEditingId = ref<string | null>(null)
type AssignmentAssistantContext = { assignment_id: string; question_id: string; title: string; course_id: string; policy: string; revision: number }
const assistantAssignmentContext = ref<{ id: string; questionId: string; title: string; courseId: string; policy: string } | null>(null)
function restoreAssignmentContext(context?: AssignmentAssistantContext | null) {
  assistantAssignmentContext.value = context ? { id: context.assignment_id, questionId: context.question_id,
    title: context.title, courseId: context.course_id, policy: context.policy } : null
}
watch(assistantDraftCourseId, value => { if (assistantAssignmentContext.value?.courseId !== value) assistantAssignmentContext.value = null })
watch(token, () => { assignmentEditingId.value = null; assistantAssignmentContext.value = null; returnFromCitation = null })
const assistantTasksRevision = ref(0)
const teacherInsights = ref<TeachingInsights | null>(null)
const courseAnalysisOpen = ref(false)
const courseAnalysisCourseId = ref('')
const teacherInsightsBusy = ref(false)
const teacherInsightsError = ref('')
const teacherFocusTopic = ref('')
const teacherAnalysisConsent = ref(false)
const teacherDraftIntent = ref<'lesson_plan' | 'question_set'>('lesson_plan')
const teacherDraftSettings = ref<HTMLElement | null>(null)
const teachingImpact = ref<TeachingImpact | null>(null)
const teachingImpactBusy = ref(false)
const teachingImpactError = ref('')
let teacherInsightsRequestId = 0
let teacherInsightsController: AbortController | null = null
let teachingImpactRequestId = 0
let teachingImpactController: AbortController | null = null
watch(assistantDraftCourseId, () => {
  clearAssistantMessagePaging()
  assistantHistoryScopeNotice.value = ''
  teacherInsightsRequestId += 1
  teacherInsightsController?.abort()
  teacherInsights.value = null
  teacherInsightsBusy.value = false
  teacherInsightsError.value = ''
  assistantShareCourseMaterials.value = false
  clearTeacherFocus()
  if (user.value?.role === 'teacher' && globalAssistantOpen.value && assistantView.value === 'tools') void loadTeacherInsights()
  if (globalAssistantBusy.value) {
    stopAssistantWaiting()
    const latest = assistantTurns.value.at(-1)
    if (latest && !latest.answer) latest.error = '课程已切换，请在新课程下重新提问。'
  }
  if (assistantTurns.value.length) assistantPendingContextChange.value = true
  globalAssistantConversationId.value = null
  assistantConversationKnowledgeBaseId.value = null
  assistantConversationDomainKey.value = ''
  assistantConversationAnswerMode.value = null
  globalAssistantAnswer.value = null
  assistantAnswerPassage.value = null
  assistantNoteTurnId.value = null
  studyNoteDraft.value = ''
})
watch(globalAssistantOpen, (open) => {
  if (!open && !assistantFollowing.value) assistantViewport.save()
  if (open && assistantView.value === 'tools' && user.value?.role === 'teacher') void loadTeacherInsights()
  if (open && assistantView.value === 'chat') {
    if (assistantTurns.value.length && !assistantFollowing.value) void nextTick(() => assistantViewport.restore())
    else if (assistantTurns.value.length) void scrollAssistantToLatestAnswer()
    else void scrollAssistantToBottom()
    assistantHasUnread.value = false
  }
})
watch(assistantView, (view, previous) => {
  if (previous === 'chat' && !assistantFollowing.value) assistantViewport.save()
  if (view === 'chat') {
    if (assistantTurns.value.length && !assistantFollowing.value) void nextTick(() => assistantViewport.restore())
    else if (assistantTurns.value.length) void scrollAssistantToLatestAnswer()
    else void scrollAssistantToBottom()
    assistantHasUnread.value = false
  }
  if (view === 'history') void loadAssistantHistory()
  if (view === 'tools' && globalAssistantOpen.value && user.value?.role === 'teacher') void loadTeacherInsights()
})
watch(() => [selectedTeachingDraft.value?.id, selectedTeachingDraft.value?.status], () => {
  teachingImpactRequestId += 1
  teachingImpactController?.abort()
  teachingImpact.value = null
  teachingImpactBusy.value = false
  teachingImpactError.value = ''
  if (selectedTeachingDraft.value?.source_context.teaching_snapshot) void loadTeachingImpact()
})
watch(assistantHistoryQuery, () => {
  assistantHistoryRequestId += 1
  assistantHistoryController?.abort()
  assistantHistoryBusy.value = false
  assistantHistory.value = []
  assistantHistoryHasMore.value = false
  if (assistantHistorySearchTimer !== null) clearTimeout(assistantHistorySearchTimer)
  assistantHistorySearchTimer = setTimeout(() => {
    if (user.value && assistantView.value === 'history') void loadAssistantHistory(true)
  }, 280)
})
watch(selectedLearningSection, (item) => {
  if (user.value?.role === 'student' && item) assistantDraftCourseId.value = item.report.course_id
})
const adminTab = ref<'overview' | 'tasks' | 'users' | 'model' | 'quotas' | 'evaluation' | 'security' | 'audit'>('overview')
const visitedAdminTabs = ref(new Set<string>(['overview']))
watch(adminTab, async (next, previous) => {
  visitedAdminTabs.value.add(next)
  if (activePage.value !== 'admin') return
  workspaceScroll.set(`admin:${previous}`, window.scrollY)
  const ticket = ++workspaceScrollTicket
  await nextTick()
  if (activePage.value === 'admin' && adminTab.value === next && ticket === workspaceScrollTicket) window.scrollTo({ top: workspaceScroll.get(`admin:${next}`) || 0, behavior: 'instant' })
}, { flush: 'sync' })
const adminTaskFocus = ref('jobs')
const adminTaskFocusRevision = ref(0)
const adminUserFilter = ref<'all' | 'active' | 'inactive'>('all')
const adminUserRole = ref<'all' | AdminUser['role']>('all')
const adminUserKeyword = ref('')
const adminUserQuery = ref('')
const adminUserQueryRevision = ref(0)
const adminUserScope = computed(() => JSON.stringify([adminUserQuery.value, adminUserRole.value, adminUserFilter.value, adminUserQueryRevision.value]))
function searchAdminUsers() { adminUserQuery.value = adminUserKeyword.value.trim(); adminUserQueryRevision.value += 1 }
function resetAdminUserSearch() {
  adminUserKeyword.value = ''; adminUserQuery.value = ''; adminUserRole.value = 'all'; adminUserFilter.value = 'all'; adminUserQueryRevision.value += 1
}
function loadAdminUserPage(page: number, pageSize: number) {
  return request<PageResult<AdminUser>>(`/api/v1/admin/assistant-tasks/users?${new URLSearchParams({
    page: String(page), page_size: String(pageSize), keyword: adminUserQuery.value,
    role: adminUserRole.value, active: adminUserFilter.value,
  })}`)
}
const newUserName = ref('')
const newUserDisplayName = ref('')
const newUserRole = ref<'student' | 'teacher' | 'admin'>('student')
const newUserPassword = ref('')
const modelApiKey = ref('')
const modelSettingsDirty = computed(() => Boolean(modelApiKey.value || (modelConfigBaseline.value && adminModelConfig.value && JSON.stringify(adminModelConfig.value) !== JSON.stringify(modelConfigBaseline.value))))
const questionEditorBaseline = ref('')
const draftView = ref<'edit' | 'preview' | 'sources'>('edit')
type TeachingEdit = Pick<TeachingDraft, 'title' | 'content' | 'questions'>
const teachingEditorDraft = useLocalEditorDraft<TeachingEdit>(value => { const item = value as TeachingEdit | null; return !!item && typeof item.title === 'string' && typeof item.content === 'string' && Array.isArray(item.questions) && item.questions.length <= 300 && item.questions.every(question => question && typeof question.stem === 'string' && typeof question.correct_answer === 'string' && Array.isArray(question.options) && question.options.every(option => typeof option === 'string')) })
let applyingTeachingDraft = false
let teachingEditingId = ''
const draftQuestionsWithIndex = computed(() => selectedTeachingDraft.value?.questions.map((item, index) => ({ item, index })) || [])
watch(() => selectedTeachingDraft.value?.id, id => {
  if (!id || id === teachingEditingId || !selectedTeachingDraft.value || !user.value) return
  teachingEditorDraft.persist(); teachingEditingId = id
  teachingEditorDraft.open(user.value.id, 'teaching', id, teachingEditOf(teachingDrafts.value.find(item => item.id === id) || selectedTeachingDraft.value))
}, { flush: 'sync' })
watch(() => selectedTeachingDraft.value && [selectedTeachingDraft.value.title, selectedTeachingDraft.value.content, selectedTeachingDraft.value.questions], () => {
  if (!applyingTeachingDraft && selectedTeachingDraft.value && selectedTeachingDraft.value.status !== 'published') teachingEditorDraft.set(teachingEditOf(selectedTeachingDraft.value))
}, { deep: true, flush: 'sync' })
function teachingEditOf(draft: TeachingDraft): TeachingEdit { return JSON.parse(JSON.stringify({ title: draft.title, content: draft.content, questions: draft.questions })) }
function recoverTeachingDraft() {
  teachingEditorDraft.recover()
  const value = teachingEditorDraft.value.value
  if (!value || !selectedTeachingDraft.value || typeof value.title !== 'string' || typeof value.content !== 'string' || !Array.isArray(value.questions)) return
  applyingTeachingDraft = true; Object.assign(selectedTeachingDraft.value, JSON.parse(JSON.stringify(value))); applyingTeachingDraft = false
}
function discardTeachingDraftEdits() {
  const original = teachingDrafts.value.find(item => item.id === selectedTeachingDraft.value?.id)
  teachingEditorDraft.clear()
  if (!original) { teachingEditorDraft.release(); selectedTeachingDraft.value = null; return }
  applyingTeachingDraft = true
  selectedTeachingDraft.value = JSON.parse(JSON.stringify(original))
  applyingTeachingDraft = false
  // Reset the draft helper too: closing must not re-persist discarded edits.
  teachingEditorDraft.set(teachingEditOf(original))
  teachingEditorDraft.persist()
}
type DirtyForm = { id: string; label: string; signature: string; discard: () => void }
const pendingFormExit = ref<{ owner: string; token: string; action: string; groups: DirtyForm[]; next: () => void } | null>(null)
function questionEditorValue() { return JSON.stringify([newQuestionCourseId.value, newQuestionType.value, newQuestionStem.value, newQuestionOptions.value, newQuestionAnswer.value, newQuestionPoint.value, newQuestionExplanation.value, newQuestionDifficulty.value]) }
function dirtyFormGroups(all = false, only?: string[]): DirtyForm[] {
  const result: DirtyForm[] = []
  function add(id: string, label: string, dirty: boolean, value: unknown, discard: () => void) { if (dirty && (!only || only.some(scope => id === scope || id.startsWith(`${scope}-`)))) result.push({ id, label, signature: JSON.stringify(value), discard }) }
  if (selectedCourse.value && !courseDetailLoading.value) {
    const original = courseAnnouncements.value.find(item => item.id === editingAnnouncementId.value)
    add('course-announcement', '课程公告修改', Boolean(editingAnnouncementId.value ? newAnnouncementTitle.value !== original?.title || newAnnouncementContent.value !== original?.content : newAnnouncementTitle.value || newAnnouncementContent.value), [selectedCourse.value.id, editingAnnouncementId.value, newAnnouncementTitle.value, newAnnouncementContent.value], resetAnnouncementEditor)
    add('course-session', '待添加课次', Boolean(newSessionTitle.value || newSessionDate.value || newSessionSectionId.value || newSessionLocation.value !== (selectedCourse.value.location || '')), [selectedCourse.value.id, newSessionTitle.value, newSessionDate.value, newSessionSectionId.value, newSessionLocation.value], () => { newSessionTitle.value = ''; newSessionDate.value = ''; newSessionSectionId.value = ''; newSessionLocation.value = selectedCourse.value?.location || '' })
    add('course-member', '待添加课程成员', Boolean(newCourseMemberUsername.value), [selectedCourse.value.id, newCourseMemberUsername.value], () => { newCourseMemberUsername.value = '' })
  }
  if (selectedTeachingDraft.value) add('draft', '教学草稿修改', teachingDraftHasUnsavedChanges(selectedTeachingDraft.value), [selectedTeachingDraft.value.id, teachingEditOf(selectedTeachingDraft.value)], discardTeachingDraftEdits)
  if (selectedDocumentContent.value) {
    const item = selectedDocumentContent.value.document
    const current = [documentSourceUrl.value, documentLicenseName.value, documentLicenseUrl.value, documentVersion.value, documentPublicationStatus.value]
    const baseline = [item.source_url || '', item.license_name || '', item.license_url || '', item.version_label, item.publication_status]
    add('document', '资料信息修改', canManage.value && JSON.stringify(current) !== JSON.stringify(baseline), [item.id, current], () => { documentSourceUrl.value = baseline[0]!; documentLicenseName.value = baseline[1]!; documentLicenseUrl.value = baseline[2]!; documentVersion.value = baseline[3]!; documentPublicationStatus.value = item.publication_status })
  }
  add('assignment-late', '尚未提交的补交申请', Boolean(selectedAssignment.value && lateRequestReason.value.trim()), [selectedAssignment.value?.id, lateRequestReason.value], () => { lateRequestReason.value = '' })
  add('timetable', '未提交的课表修改', timetableDirty.value, timetableWorkspace.value?.signature(), () => timetableWorkspace.value?.discardEdits())
  add('course-editor', '尚未保存的课程内容', courseEditorDirty.value, courseEditorPanel.value?.signature(), () => courseEditorPanel.value?.discardEdits())
  add('teaching-workbench', '尚未保存的教学工作编辑', workbenchDirty.value, workbenchPanel.value?.signature(), () => workbenchPanel.value?.discardEdits())
  if (!all) return result
  add('course-create', '新建课程', Boolean(newCourseTitle.value || newCourseCode.value || newCourseDescription.value || newCourseCover.value || newCourseSemester.value !== '2026-2027 第一学期'), [newCourseTitle.value,newCourseCode.value,newCourseDescription.value,newCourseCover.value,newCourseSemester.value], () => { newCourseTitle.value = ''; newCourseCode.value = ''; newCourseDescription.value = ''; newCourseCover.value = ''; newCourseSemester.value = '2026-2027 第一学期' })
  add('document-upload', '尚未上传的资料文件', Boolean(selectedFile.value), [selectedFile.value?.name, selectedFile.value?.size, selectedFile.value?.lastModified], () => { selectedFile.value = null })
  add('question-editor', '题目编辑', Boolean(editingQuestionId.value ? questionEditorValue() !== questionEditorBaseline.value : newQuestionStem.value || newQuestionAnswer.value || newQuestionOptions.value || newQuestionPoint.value || newQuestionExplanation.value), questionEditorValue(), resetQuestionEditor)
  add('assignment-create', '新建作业', Boolean(newAssignmentTitle.value || selectedQuestionIds.value.length || newAssignmentDueAt.value), [newAssignmentTitle.value, selectedQuestionIds.value, newAssignmentDueAt.value], () => { newAssignmentTitle.value = ''; selectedQuestionIds.value = []; newAssignmentDueAt.value = '' })
  add('user-create', '新建用户（含未保存密码）', Boolean(newUserName.value || newUserDisplayName.value || newUserPassword.value), [newUserName.value,newUserDisplayName.value,newUserRole.value,newUserPassword.value], () => { newUserName.value = ''; newUserDisplayName.value = ''; newUserPassword.value = '' })
  add('model-config', '模型设置（密钥不在本机暂存）', modelSettingsDirty.value, [adminModelConfig.value, modelApiKey.value], () => { adminModelConfig.value = modelConfigBaseline.value ? JSON.parse(JSON.stringify(modelConfigBaseline.value)) : null; modelApiKey.value = '' })
  add('knowledge-base-create', '新建资料库', Boolean(newKnowledgeBaseName.value || newKnowledgeBaseDescription.value), [newKnowledgeBaseName.value,newKnowledgeBaseCourse.value,newKnowledgeBaseDescription.value], () => { newKnowledgeBaseName.value = ''; newKnowledgeBaseDescription.value = '' })
  add('preparation-topic', '备课或出题主题', Boolean(assistantDraftTopic.value || draftGenerateTopic.value), [assistantDraftTopic.value, draftGenerateTopic.value], () => { assistantDraftTopic.value = ''; draftGenerateTopic.value = '' })
  add('assistant-input', '尚未发送的助手提问', Boolean(globalAssistantQuestion.value.trim()), globalAssistantQuestion.value, () => { globalAssistantQuestion.value = '' })
  add('study-note', '尚未保存的学习笔记', Boolean(studyNoteDraft.value.trim()), studyNoteDraft.value, () => { studyNoteDraft.value = '' })
  add('model-quotas', 'AI角色额度修改', modelQuotas.value.some(item => modelQuotaDrafts.value[item.role] !== item.daily_limit), modelQuotaDrafts.value, () => { modelQuotaDrafts.value = Object.fromEntries(modelQuotas.value.map(item => [item.role, item.daily_limit])) as Record<ModelQuota['role'], number> })
  for (const [id, entry] of reviewEdits) add(`review-${id}`, '问答审核修改', JSON.stringify([entry.item.revised_answer, entry.item.review_note]) !== JSON.stringify([entry.baseline.revised_answer, entry.baseline.review_note]), [id, entry.item.revised_answer, entry.item.review_note], () => { Object.assign(entry.item, entry.baseline) })
  return result
}
function guardFormExit(next: () => void, action: string, only?: string[], all = false) {
  if (platformBusy.value || timetableSaving.value || courseEditorSaving.value || workbenchSaving.value) { platformStatus.value = '正在处理当前操作，请等待结果后再离开。'; return false }
  const groups = dirtyFormGroups(all, only)
  if (!groups.length) return true
  pendingFormExit.value = { owner: user.value?.id || '', token: token.value, action, groups, next }
  return false
}
function discardFormsAndContinue() {
  const pending = pendingFormExit.value
  pendingFormExit.value = null
  if (!pending || pending.owner !== user.value?.id || pending.token !== token.value || platformBusy.value) return
  const current = dirtyFormGroups(true)
  if (pending.groups.some(group => current.find(item => item.id === group.id)?.signature !== group.signature)) { platformStatus.value = '编辑内容已经变化，请重新确认离开操作。'; return }
  for (const group of pending.groups) group.discard()
  pending.next()
}
function stashTeachingAndContinue() {
  const pending = pendingFormExit.value
  if (!pending || pending.groups.some(group => group.id !== 'draft') || pending.owner !== user.value?.id || pending.token !== token.value || platformBusy.value) return
  if (!teachingEditorDraft.persist() || teachingEditorDraft.recovery.value || teachingEditorDraft.changedElsewhere.value) { pendingFormExit.value = null; teachingDraftFeedback.value = { message: '本机草稿未能安全暂存，请先处理提示或复制内容。', error: true }; return }
  const original = teachingDrafts.value.find(item => item.id === selectedTeachingDraft.value?.id)
  if (!original) return
  applyingTeachingDraft = true; selectedTeachingDraft.value = JSON.parse(JSON.stringify(original)); applyingTeachingDraft = false
  pendingFormExit.value = null; pending.next()
}
function closeTeachingDraft() {
  if (!guardFormExit(closeTeachingDraft, '关闭教学草稿', ['draft'])) return
  teachingEditorDraft.persist(); teachingEditorDraft.release(); teachingEditingId = ''; selectedTeachingDraft.value = null
}
let returnFromCitation: (() => void) | null = null
function closeDocumentPreview() {
  if (studyNoteBusy.value || !guardFormExit(closeDocumentPreview, '关闭资料预览', ['document'])) return
  selectedDocumentContent.value = null
  const restore = returnFromCitation; returnFromCitation = null; restore?.()
}

const answerModeOptions: AnswerModeOption[] = [
  {
    value: 'rag',
    label: '严格课程 RAG',
    hint: '只用资料论证',
    description: '只使用当前课程资料回答，回答可追溯到具体文档和页码。',
  },
  {
    value: 'hybrid',
    label: '课程优先',
    hint: '资料论证 + AI',
    description: '优先用已核准的课程资料辅助 AI 讲解；未核准资料仅展示本地检索证据，不发送给外部模型。',
  },
  {
    value: 'general',
    label: '通用助手',
    hint: '直接询问 AI',
    description: '直接使用 AI 模型的通用知识回答，不要求引用当前课程资料。',
  },
]

const selectedKnowledgeBase = computed(() =>
  knowledgeBases.value.find((item) => item.id === selectedKnowledgeBaseId.value) ?? null,
)
const canAsk = computed(() =>
  question.value.trim().length > 0 &&
  !busy.value &&
  !tutorHistoryBusy.value &&
  (answerMode.value === 'general' || Boolean(selectedKnowledgeBaseId.value) || Boolean(tutorRestoredScope.value)),
)
const tutorPendingMatches = computed(() => question.value === tutorRequestQuestion.value &&
  selectedKnowledgeBaseId.value === tutorRequestContext.value.kb && answerMode.value === tutorRequestContext.value.mode &&
  (tutorRequestState.value === 'unknown' || tutorRequestState.value === 'in_progress'))
const totalDocuments = computed(() => knowledgeBases.value.reduce((sum, item) => sum + item.document_count, 0))
const pendingAssignments = computed(() => assignments.value.filter((item) => !item.submitted && item.status === 'published').length)
const overdueAssignments = computed(() => assignments.value.filter((item) =>
  !item.submitted && item.status === 'published' && assignmentIsOverdue(item) && !canSubmitAssignment(item)).length)
function nextPendingAssignment(items: AssignmentRecord[]) {
  const pending = items.filter((item) => !item.submitted && item.status === 'published')
  const upcoming = pending.filter((item) => !assignmentIsOverdue(item))
    .sort((a, b) => (a.due_at ? Date.parse(a.due_at) : Infinity) - (b.due_at ? Date.parse(b.due_at) : Infinity))
  const approvedLate = pending.filter((item) => assignmentIsOverdue(item) && canSubmitAssignment(item))
    .sort((a, b) => (a.late_approved_until ? Date.parse(a.late_approved_until) : Infinity) - (b.late_approved_until ? Date.parse(b.late_approved_until) : Infinity))
  const overdue = pending.filter((item) => assignmentIsOverdue(item) && !canSubmitAssignment(item))
    .sort((a, b) => Date.parse(b.due_at || '') - Date.parse(a.due_at || ''))
  return upcoming[0] ?? approvedLate[0] ?? overdue[0] ?? null
}
const nextStudentAssignment = computed(() => nextPendingAssignment(assignments.value))
const nextStudentSession = computed(() => studentCourseSessions.value
  .filter((item) => item.schedule_status !== 'cancelled' && Date.parse(item.session_date) + item.duration_minutes * 60000 > clockNow.value)
  .sort((a, b) => Date.parse(a.session_date) - Date.parse(b.session_date))[0] ?? null)
const selectedStudyCourseId = computed(() => assistantDraftCourseId.value || nextStudentAssignment.value?.course_id || platformCourses.value[0]?.id || '')
const selectedStudyPlan = computed(() => studentStudyPlans.value.find((item) => item.course_id === selectedStudyCourseId.value) ?? null)
const assistantNextAssignment = computed(() => nextPendingAssignment(assignments.value.filter(item => item.course_id === selectedStudyCourseId.value)))
const assistantNextSession = computed(() => studentCourseSessions.value.filter(item => item.course_id === selectedStudyCourseId.value && item.schedule_status !== 'cancelled' && Date.parse(item.session_date) + item.duration_minutes * 60000 > clockNow.value)
  .sort((a, b) => Date.parse(a.session_date) - Date.parse(b.session_date))[0] ?? null)
const assistantWrongQuestions = computed(() => wrongQuestions.value.filter(item => !item.mastered && item.question.course_id === selectedStudyCourseId.value))
const visibleStudyNotes = computed(() => studentStudyNotes.value.filter((item) => !assistantDraftCourseId.value || item.course_id === assistantDraftCourseId.value))
const pendingReviews = computed(() => pendingReviewCount.value)
const averageLearningProgress = computed(() => {
  if (!learningReports.value.length) return 0
  return Math.round(learningReports.value.reduce((sum, item) => sum + item.progress_percent, 0) / learningReports.value.length)
})
const assignmentCompletion = computed(() => {
  const total = learningReports.value.reduce((sum, item) => sum + item.assignment_count, 0)
  const completed = learningReports.value.reduce((sum, item) => sum + item.completed_assignments, 0)
  return total ? Math.round(completed / total * 100) : 0
})
const canManage = computed(() => user.value?.role === 'teacher' || user.value?.role === 'admin')
const isAdmin = computed(() => user.value?.role === 'admin')
const modelLabel = computed(() => {
  if (!modelStatus.value || modelStatus.value.llm_provider === 'offline') return '离线证据回答'
  return modelStatus.value.llm_configured ? `在线 · ${modelStatus.value.llm_model}` : '在线模型未配置'
})
const answerModeOption = computed(() => answerModeOptions.find((option) => option.value === answerMode.value) ?? answerModeOptions[0])
const nonGenerativeModels = new Set(['platform-data', 'local-evidence', 'offline', 'offline-fallback'])
function safeMaterialLink(value: string | null): string | null {
  if (!value) return null
  try {
    const url = new URL(value)
    return url.protocol === 'https:' || url.protocol === 'http:' ? url.href : null
  } catch {
    return null
  }
}
function isGeneratedModelAnswer(response: AskResponse): boolean {
  return !nonGenerativeModels.has(response.model)
}
function answerProvenanceLabel(response: AskResponse): string {
  if (response.model === 'platform-data') return '依据平台记录 · 非 AI 推测'
  if (response.model === 'local-evidence') return '本地资料证据 · 未经 AI 讲解'
  if (response.model === 'offline-fallback') return '模型暂不可用 · 离线回退'
  if (response.model === 'offline') return '离线模板回答 · 非在线模型'
  return response.citations.length ? `AI 讲解 · 参考 ${response.citations.length} 条课程资料` : 'AI 生成 · 请核对'
}
function answerEvidenceNote(response: AskResponse): string {
  if (response.model === 'platform-data') return '本条内容依据平台课程与学习记录整理，未调用在线模型；打开具体任务可查看最新状态。'
  if (response.model === 'local-evidence') return '以上仅为站内检索证据，未发送给外部模型，也不是 AI 归纳讲解。'
  if (response.model === 'offline' || response.model === 'offline-fallback') return '本条由离线方式提供，并非在线模型讲解；请核对资料原文。'
  if (!response.answer_mode) return '这条历史未保存引用片段，无法据此推断原回答模式或是否检索过资料。'
  if (response.answer_mode === 'general') return '通用助手模式未检索本轮课程资料，回答基于 AI 通用知识，请自行核对。'
  return response.answer_mode === 'hybrid' ? '本轮未获得足够可引用的课程片段，通用解释不宜当作教材原文。' : '当前资料不足以确定答案。'
}
const tutorWorkspaceLabel = computed(() => user.value?.role === 'teacher' ? 'AI 教学助理' : user.value?.role === 'admin' ? 'AI 管理助理' : 'AI 课程导师')
const tutorHeroHeadline = computed(() => user.value?.role === 'teacher' ? '从备课到反馈，随时协作' : user.value?.role === 'admin' ? '让平台管理更有依据' : '把每个问题问明白')
const tutorHeroKicker = computed(() => user.value?.role === 'teacher' ? 'AI TEACHING STUDIO' : user.value?.role === 'admin' ? 'AI MANAGEMENT STUDIO' : 'AI LEARNING STUDIO')
const tutorGuideDescription = computed(() => user.value?.role === 'teacher'
  ? '结合课程资料准备讲解、练习与教学计划，生成内容可继续修改。'
  : user.value?.role === 'admin'
    ? '结合平台状态与资料信息梳理问题，关键变更仍由管理员确认。'
    : '优先检索课程资料；模型可用且资料获准外发时由 AI 讲解，否则明确展示本地证据。')
const tutorAskDescription = computed(() => user.value?.role === 'teacher'
  ? '围绕课程内容交流教案、题目和教学思路，资料引用帮助你核对结果。'
  : user.value?.role === 'admin'
    ? '询问平台运行、资料治理与配置问题，建议会尽量说明依据。'
    : '先检索当前资料库；模型可用且资料获准外发时由 AI 讲解，否则只展示本地证据。')
const tutorQuestionPlaceholder = computed(() => {
  if (user.value?.role === 'teacher') return answerMode.value === 'general' ? '例如：如何设计循序渐进的课堂练习？' : '例如：根据树与二叉树资料准备教学提纲'
  if (user.value?.role === 'admin') return answerMode.value === 'general' ? '例如：如何排查模型调用失败？' : '例如：当前资料库有哪些需要核对的内容？'
  return answerMode.value === 'general' ? '例如：请解释人工智能和机器学习的区别' : '例如：动态规划最优子结构是什么？'
})
const roleWorkspaceDescription = computed(() => user.value?.role === 'teacher' ? '备课、出题与学情分析' : user.value?.role === 'admin' ? '平台治理与运行分析' : '课程学习与练习')
const tutorWorkspaceDescription = computed(() => user.value?.role === 'teacher'
  ? '结合课程资料准备教学内容与题目草稿，生成结果由教师审核后使用。'
  : user.value?.role === 'admin'
    ? '结合资料和平台状态分析问题；涉及配置与管理变更时由管理员确认。'
    : '课程资料负责提供论据，AI 模型负责理解、推导，并把答案讲清楚。')
const workspaceItems = computed(() => {
  const common = [
    { value: 'dashboard' as WorkspacePage, label: user.value?.role === 'student' ? '首页' : '工作台', icon: '⌂' },
    { value: 'tutor' as WorkspacePage, label: tutorWorkspaceLabel.value, icon: '✦' },
    { value: 'assessments' as WorkspacePage, label: user.value?.role === 'student' ? '我的作业' : '作业管理', icon: '✓' },
    { value: 'courses' as WorkspacePage, label: user.value?.role === 'admin' ? '课程与资料' : user.value?.role === 'teacher' ? '教学课程' : '我的课程', icon: '▤' },
  ]
  const timetable = { value: 'timetable' as WorkspacePage, label: user.value?.role === 'admin' ? '排课管理' : user.value?.role === 'teacher' ? '教学课表' : '我的课表', icon: '▦' }
  if (user.value?.role === 'admin') return [common[0], { value: 'admin' as WorkspacePage, label: '管理控制台', icon: '⚙' }, timetable, common[3], common[1]]
  if (user.value?.role === 'teacher') return [common[0], timetable, common[3], common[2], {value:'questionbank' as WorkspacePage,label:'题库管理',icon:'▤'}, common[1]]
  return [common[0], timetable, common[2], {value:'practice' as WorkspacePage,label:'练习中心',icon:'◎'}, {value:'reports' as WorkspacePage,label:'学习情况',icon:'▥'}, common[3], common[1]]
})
const activeWorkspaceItem=computed<WorkspacePage>(()=>activePage.value!=='assessments'?activePage.value:learningTab.value==='reports'?'reports':['questions','reviews'].includes(learningTab.value)&&user.value?.role!=='student'?'questionbank':['practice','questions','wrong'].includes(learningTab.value)?'practice':'assessments')
const workspaceTitle = computed(() => workspaceItems.value.find((item) => item.value === activeWorkspaceItem.value)?.label ?? (activePage.value==='assessments'?'作业管理':'工作台'))
const assistantRoleTitle = computed(() => tutorWorkspaceLabel.value)
const assistantScope = computed(() => user.value?.role === 'student' ? 'course_qa' : user.value?.role === 'teacher' ? 'teaching' : 'management')
watch([globalAssistantOpen, assistantDraftCourseId, token, () => user.value?.role], () => {
  assistantMaterialController?.abort()
  assistantMaterialSequence += 1
  assistantMaterialScope.value = null
  assistantMaterialScopeError.value = ''
  assistantMaterialScopeBusy.value = false
  if (globalAssistantOpen.value && user.value) void loadAssistantMaterialScope()
})

async function loadAssistantMaterialScope() {
  if (!user.value) return
  const sequence = ++assistantMaterialSequence
  const owner = user.value.id
  const requestedToken = token.value
  const courseId = user.value.role === 'admin' ? '' : assistantDraftCourseId.value
  assistantMaterialController?.abort()
  const controller = new AbortController()
  assistantMaterialController = controller
  assistantMaterialScopeBusy.value = true
  assistantMaterialScopeError.value = ''
  try {
    const params = new URLSearchParams({ purpose: assistantScope.value })
    if (courseId) params.set('course_id', courseId)
    const scope = await request<AssistantMaterialScope>(`/api/v1/assistant/context?${params}`, { signal: controller.signal })
    if (sequence === assistantMaterialSequence && requestedToken === token.value && owner === user.value?.id) assistantMaterialScope.value = scope
  } catch (error) {
    if (sequence === assistantMaterialSequence && !controller.signal.aborted) assistantMaterialScopeError.value = error instanceof Error ? error.message : '暂时无法核对课程资料。'
  } finally {
    if (sequence === assistantMaterialSequence) { assistantMaterialScopeBusy.value = false; assistantMaterialController = null }
  }
}

function answerScopeLabel(data: AskResponse) {
  const scope = data.answer_scope
  if (!scope) return ''
  const label = scope.course_id ? [scope.course_title, scope.course_code, scope.semester].filter(Boolean).join(' · ') : '未指定课程'
  return `${label}${scope.source_document_name ? ` · 选段来源：《${scope.source_document_name}》` : ''}`
}
const assistantPrompts = computed(() => user.value?.role === 'student'
  ? ['帮我安排当前课程的学习计划', '帮我分析薄弱知识点', '下一个作业是什么？', '我今天有什么课？']
  : user.value?.role === 'teacher'
    ? ['分析全班成绩和学习情况', '为当前课程准备教学计划', '根据章节生成练习题草稿']
    : ['解释当前管理页面', '如何排查资料导入失败', '说明模型配置项的影响'])
const assistantActions = computed<AssistantAction[]>(() => {
  if (user.value?.role === 'student') {
    const unmastered = assistantWrongQuestions.value.length
    return [
      assistantNextAssignment.value
        ? { id: 'student-next-assignment',
            eyebrow: assignmentIsOverdue(assistantNextAssignment.value) ? (canSubmitAssignment(assistantNextAssignment.value) ? '获批补交' : assistantNextAssignment.value.late_request_status === 'pending' ? '补交待审批' : '逾期未交') : '下一项作业',
            title: assistantNextAssignment.value.title,
            detail: `${assistantNextAssignment.value.course_title} · ${assistantNextAssignment.value.due_at ? `截止 ${historyTime(assistantNextAssignment.value.due_at)}` : '截止时间待定'}${assignmentLateHint(assistantNextAssignment.value)}`,
            button: assignmentIsOverdue(assistantNextAssignment.value) && !canSubmitAssignment(assistantNextAssignment.value) ? '查看补交' : '进入作答',
            tone: assignmentIsOverdue(assistantNextAssignment.value) ? 'warning' : 'primary' }
        : { id: 'student-courses', eyebrow: '学习', title: '当前没有待处理作业', detail: '可以继续查看课程进度与下一课次。', button: '查看课程', tone: 'neutral' },
      assistantNextSession.value
        ? { id: 'student-next-session', eyebrow: '下一节课', title: assistantNextSession.value.title, detail: `${platformCourses.value.find((course) => course.id === assistantNextSession.value?.course_id)?.title || '课程'} · ${historyTime(assistantNextSession.value.session_date)} · ${assistantNextSession.value.location || '地点待定'}`, button: '查看课程', tone: 'neutral' }
        : { id: 'student-schedule', eyebrow: '课程表', title: '暂无即将开始的课次', detail: '打开课程查看完整的学期安排。', button: '查看课程', tone: 'neutral' },
      unmastered
        ? { id: 'student-wrong', eyebrow: '巩固', title: `本课程 ${unmastered} 道错题待巩固`, detail: '打开一道错题，作答后继续复盘。', button: '开始练习', tone: 'warning' }
        : { id: 'student-practice', eyebrow: '练习', title: '安排本课程练习', detail: '在下方选择复习巩固，整理具体练习任务。', button: '查看安排', tone: 'neutral' },
      selectedStudyPlan.value
        ? { id: 'student-plan', eyebrow: '学习计划', title: selectedStudyPlan.value.actionable_count
            ? `${selectedStudyPlan.value.course_title} · ${selectedStudyPlan.value.completed_count}/${selectedStudyPlan.value.actionable_count} 项任务完成`
            : `${selectedStudyPlan.value.course_title} · ${selectedStudyPlan.value.items.length} 项学习建议`,
            detail: '按作业、错题与课次更新，可打开每项任务。', button: '查看计划', tone: 'primary' }
        : { id: 'student-plan', eyebrow: '学习计划', title: '创建本课程学习计划', detail: '依据真实作业、错题和课次生成可执行任务。', button: '创建计划', tone: 'primary' },
    ]
  }
  if (user.value?.role === 'teacher') {
    return [
      { id: 'teacher-insights', eyebrow: '全体学情', title: '综合查看成绩与学习情况', detail: '成绩分布、作业表现、实名学生跟进与 AI 教学建议。', button: '打开学情总览', tone: 'primary' },
      pendingReviews.value
        ? { id: 'teacher-reviews', eyebrow: '待处理', title: `${pendingReviews.value} 条问答等待审核`, detail: '核对答案后可修订并发布为课程资料。', button: '进入审核', tone: 'warning' }
        : { id: 'teacher-questions', eyebrow: '题库', title: `已有 ${questionBank.value.length} 道课程题目`, detail: '继续维护题目或选择题目发布作业。', button: '管理题库', tone: 'neutral' },
      { id: 'teacher-plan', eyebrow: '备课', title: '生成教学计划草稿', detail: '结合课程资料生成，交由教师审核。', button: '生成草稿', tone: 'primary' },
      { id: 'teacher-lesson', eyebrow: '教案', title: '准备单次课教案', detail: '整理教学目标、课堂活动和时间安排。', button: '生成草稿', tone: 'neutral' },
      { id: 'teacher-quiz', eyebrow: '出题', title: '生成题目草稿', detail: '生成后可逐题修改、确认并入库。', button: '生成草稿', tone: 'neutral' },
    ]
  }
  const failedJobs = documentJobs.value.filter((item) => item.status === 'failed').length
  const risks = (securityOverview.value?.failed_logins_24h || 0) + (securityOverview.value?.server_errors_24h || 0)
  const fallback: AssistantAction[] = [
    failedJobs
      ? { id: 'admin-jobs', eyebrow: '资料任务', title: `${failedJobs} 个资料任务处理失败`, detail: '进入任务队列查看原因并决定是否重试。', button: '检查任务', tone: 'warning' }
      : { id: 'admin-overview', eyebrow: '平台', title: '资料处理队列运行正常', detail: '查看平台数据与最近资料任务。', button: '平台概览', tone: 'neutral' },
    risks
      ? { id: 'admin-security', eyebrow: '运行提醒', title: `${risks} 条安全或服务事件`, detail: '查看最近登录与请求记录，定位异常来源。', button: '检查运行', tone: 'warning' }
      : { id: 'admin-model', eyebrow: 'AI 服务', title: '查看模型与检索配置', detail: '检查在线状态和当前 RAG 参数。', button: '查看配置', tone: 'primary' },
  ]
  const reportAction: AssistantAction = { id: 'admin-report', eyebrow: '巡检报告', title: '生成平台运行报告', detail: '按真实数据检查课程资料、模型调用和安全事件。', button: '今日巡检', tone: 'primary' }
  const taskAction: AssistantAction = { id: 'admin-task-center', eyebrow: '任务处理', title: '打开管理任务中心', detail: '查看具体异常与额度，预览、确认并回看操作。', button: '处理任务', tone: 'primary' }
  return [reportAction, taskAction, ...adminInsights.value.slice(0, 2), ...fallback].filter((action, index, actions) => actions.findIndex((item) => item.id === action.id) === index).slice(0, 4)
})
const assistantSelectedCourse = computed(() => platformCourses.value.find((item) => item.id === assistantDraftCourseId.value) ?? null)
const assistantPageContext = computed(() => {
  const tab = activePage.value === 'assessments' ? `学习功能：${learningTab.value}` : activePage.value === 'admin' ? `管理功能：${adminTab.value}` : ''
  // UI location is a hint, not an authoritative copy of academic records.
  return `当前页面：${workspaceTitle.value}；${tab}`
})
const assistantWaitingHint = computed(() => assistantWaitSeconds.value >= 15
  ? '响应时间较长，可以继续浏览页面；回答完成后会留在这里。'
  : '你可以继续浏览页面，回答完成后会保留在对话中。')

function answerModeLabel(mode: AnswerMode | null) {
  return answerModeOptions.find((option) => option.value === mode)?.label ?? '原回答模式未记录'
}

function openWorkspace(page: WorkspacePage) {
  mobileNavigationOnTop.value=false
  mobileNavigation.reveal()
  if (page === 'tutor') { openUnifiedAssistant(); return }
  if(['assessments','practice','questionbank','reports'].includes(page)) {
    activePage.value='assessments'
    if(activePage.value!=='assessments')return
    learningTab.value=page==='practice'?'practice':page==='questionbank'?'questions':page==='reports'?'reports':'assignments'
    return
  }
  activePage.value = page
}

function runAssistantAction(action: AssistantAction) {
  if (action.id === 'student-next-assignment' && assistantNextAssignment.value) { learningTab.value = 'assignments'; activePage.value = 'assessments'; void openAssignment(assistantNextAssignment.value) }
  else if (action.id === 'student-next-session' && assistantNextSession.value) openTimetableSession(assistantNextSession.value.id)
  else if (action.id === 'student-assignments') { learningTab.value = 'assignments'; activePage.value = 'assessments' }
  else if (action.id === 'student-schedule') activePage.value = 'timetable'
  else if (action.id === 'student-wrong') { const item = assistantWrongQuestions.value[0]; if (item) { learningTab.value = 'wrong'; activePage.value = 'assessments'; openQuestionPractice(item.question, 'wrong_question') } }
  else if (action.id === 'student-practice') { assistantView.value = 'tools'; globalAssistantOpen.value = true; return }
  else if (action.id === 'student-courses') activePage.value = 'courses'
  else if (action.id === 'student-plan') { assistantView.value = 'tools'; globalAssistantOpen.value = true; if (!selectedStudyPlan.value) void createStudyPlan(); return }
  else if (action.id === 'teacher-reviews') { learningTab.value = 'reviews'; activePage.value = 'assessments' }
  else if (action.id === 'teacher-questions') { learningTab.value = 'questions'; activePage.value = 'assessments' }
  else if (action.id === 'teacher-insights') { openCourseAnalysis(assistantDraftCourseId.value); return }
  else if (action.id === 'teacher-plan') { void generateAssistantTeachingDraft('teaching_plan'); return }
  else if (action.id === 'teacher-lesson') { void generateAssistantTeachingDraft('lesson_plan'); return }
  else if (action.id === 'teacher-quiz') { void generateAssistantTeachingDraft('question_set'); return }
  else if (action.id === 'admin-report') { void loadAdminReport(1); return }
  else if (action.id === 'admin-task-center' || action.id === 'admin-jobs') { openAdminTaskCenter('jobs'); return }
  else if (action.id === 'admin-overview') { adminTab.value = 'overview'; activePage.value = 'admin' }
  else if (action.id === 'admin-security') { adminTab.value = 'security'; activePage.value = 'admin' }
  else if (action.id === 'admin-model') { adminTab.value = 'model'; activePage.value = 'admin' }
  else if (action.id === 'admin-model-failures') { openAdminTaskCenter('calls:1'); return }
  else if (action.id === 'admin-inactive-users') { openAdminTaskCenter('accounts:inactive'); return }
  else if (action.id === 'admin-course-materials') { openCourseCatalog('missing'); return }
  globalAssistantOpen.value = false
}

async function openAssistantResponseAction(action: NonNullable<AskResponse['actions']>[number]) {
  assistantActionError.value = ''
  try {
    if (action.kind === 'course') {
      const currentCourse = await request<CourseRecord>(`/api/v1/courses/${action.target_id}`)
      if (!await openCourseDetail(currentCourse)) throw new Error('课程详情暂时无法打开，请稍后重试。')
    } else if (action.kind === 'assignment') {
      if (!await openAssignment({ id: action.target_id })) throw new Error(platformStatus.value || '作业已不可访问或暂时无法打开，请刷新后重试。')
      learningTab.value = 'assignments'
      activePage.value = 'assessments'
    } else if (action.kind === 'wrong_question') {
      if (user.value?.role !== 'student') throw new Error('此入口仅适用于学生练习。')
      const currentQuestion = await request<QuestionItem>(`/api/v1/questions/${action.target_id}`)
      learningTab.value = 'wrong'
      activePage.value = 'assessments'
      openQuestionPractice(currentQuestion, 'wrong_question')
    } else if (action.kind === 'admin_tasks') {
      if (user.value?.role !== 'admin') throw new Error('此入口仅适用于管理员。')
      openAdminTaskCenter(action.target_id)
      return
    } else if (action.kind === 'study_plan') {
      if (user.value?.role !== 'student') throw new Error('此入口仅适用于学生学习计划。')
      const currentCourse = await request<CourseRecord>(`/api/v1/courses/${action.target_id}`)
      studentStudyPlans.value = await request<StudyPlan[]>('/api/v1/study-plans')
      assistantDraftCourseId.value = currentCourse.id
      assistantView.value = 'tools'
      globalAssistantOpen.value = true
      return
    } else if (action.kind === 'course_analysis') {
      if (!canManage.value) throw new Error('此入口适用于课程教学管理。')
      const course = await request<CourseRecord>(`/api/v1/courses/${action.target_id}`)
      openCourseAnalysis(course.id)
      return
    } else if (action.kind === 'teacher_plan' || action.kind === 'teacher_questions') {
      if (user.value?.role !== 'teacher') throw new Error('此入口仅适用于教师备课。')
      const requestedToken = token.value
      const course = await request<CourseRecord>(`/api/v1/courses/${action.target_id}`)
      if (requestedToken !== token.value || user.value?.role !== 'teacher') return
      assistantDraftCourseId.value = course.id
      await nextTick()
      prepareTeacherFocus(action.topic || '', action.kind === 'teacher_questions' ? 'question_set' : 'lesson_plan')
      return
    } else {
      throw new Error('这张操作卡片已不受支持，请重新提问获取当前建议。')
    }
    globalAssistantOpen.value = false
  } catch (error) {
    assistantActionError.value = error instanceof Error ? error.message : '目标暂时无法打开，请稍后重试。'
  }
}

async function openAssistantCourseMaterials(courseId: string) {
  const course = platformCourses.value.find((item) => item.id === courseId)
  if (!course) { platformStatus.value = '课程安排已变化，请刷新后重试。'; return }
  activePage.value = 'courses'
  await openCourseDetail(course)
  globalAssistantOpen.value = false
}

function clearTeacherFocus() {
  if (teacherFocusTopic.value && assistantDraftTopic.value === teacherFocusTopic.value) assistantDraftTopic.value = ''
  teacherFocusTopic.value = ''
  teacherAnalysisConsent.value = false
}

function prepareTeacherFocus(topic: string, type: 'lesson_plan' | 'question_set') {
  if (user.value?.role !== 'teacher' || !assistantDraftCourseId.value || assistantDraftBusy.value) return
  teacherFocusTopic.value = topic
  assistantDraftTopic.value = topic
  teacherDraftIntent.value = type
  teacherAnalysisConsent.value = false
  assistantActionError.value = ''
  assistantView.value = 'tools'
  globalAssistantOpen.value = true
  void nextTick(() => teacherDraftSettings.value?.scrollIntoView({ block: 'start', behavior: 'instant' }))
}

function openCourseAnalysis(courseId: string) {
  if (!canManage.value) return
  const id = courseId || platformCourses.value[0]?.id
  if (!id) { platformStatus.value = '请先创建或选择教学课程。'; return }
  courseAnalysisCourseId.value = id
  courseAnalysisOpen.value = true
  globalAssistantOpen.value = false
}

async function openCohortAssignment(id: string) {
  await openTeacherReview(id)
  if (selectedAssignment.value?.id === id) courseAnalysisOpen.value = false
}

async function openCohortStudent(item: CohortStudent) {
  if (!item.latest_assignment_id) {
    courseAnalysisOpen.value = false
    openTeacherAssignments()
    platformStatus.value = `${item.student_name} 暂无提交记录，可在课程作业中查看需要跟进的任务。`
    return
  }
  const requestedToken = token.value
  await openCohortAssignment(item.latest_assignment_id)
  if (requestedToken !== token.value || selectedAssignment.value?.id !== item.latest_assignment_id) return
  const submission = assignmentSubmissions.value.find(record => record.id === item.latest_submission_id)
  if (submission) selectSubmission(submission)
}

function prepareFromCohort(topic: string, type: 'lesson_plan' | 'question_set') {
  assistantDraftCourseId.value = courseAnalysisCourseId.value
  courseAnalysisOpen.value = false
  if (user.value?.role === 'admin') {
    draftGenerateCourseId.value = courseAnalysisCourseId.value
    draftGenerateTopic.value = topic
    draftGenerateType.value = type
    activePage.value = 'courses'
    platformStatus.value = '已将知识点带入教学草稿设置，请确认后生成。'
    return
  }
  void nextTick(() => prepareTeacherFocus(topic, type))
}

async function openCohortDraft(id: string) {
  try {
    const requestedToken = token.value
    const draft = await request<TeachingDraft>(`/api/v1/teaching-drafts/${id}`)
    if (requestedToken !== token.value || !canManage.value) return
    teachingDrafts.value = [draft, ...teachingDrafts.value.filter(item => item.id !== id)]
    courseAnalysisOpen.value = false
    activePage.value = 'courses'
    openTeachingDraft(draft)
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '学情草稿暂时无法打开。' }
}

async function loadTeacherInsights() {
  if (user.value?.role !== 'teacher' || !assistantDraftCourseId.value || teacherInsightsBusy.value) return
  const courseId = assistantDraftCourseId.value
  const requestedToken = token.value
  const requestId = ++teacherInsightsRequestId
  teacherInsightsController?.abort()
  const controller = new AbortController()
  teacherInsightsController = controller
  teacherInsightsBusy.value = true
  teacherInsightsError.value = ''
  const current = () => requestId === teacherInsightsRequestId && requestedToken === token.value &&
    user.value?.role === 'teacher' && courseId === assistantDraftCourseId.value
  try {
    const result = await request<TeachingInsights>(`/api/v1/courses/${courseId}/teaching-insights`, { signal: controller.signal })
    if (current()) teacherInsights.value = result
  } catch (error) {
    if (current() && !controller.signal.aborted) {
      teacherInsights.value = null
      teacherInsightsError.value = error instanceof Error ? error.message : '学情暂不可用，请重试。'
    }
  } finally { if (current()) teacherInsightsBusy.value = false }
}

async function loadTeachingImpact() {
  const draft = selectedTeachingDraft.value
  if (!draft?.source_context.teaching_snapshot || !canManage.value) return
  const requestedToken = token.value
  const requestId = ++teachingImpactRequestId
  teachingImpactController?.abort()
  const controller = new AbortController()
  teachingImpactController = controller
  teachingImpactBusy.value = true
  teachingImpactError.value = ''
  const current = () => requestId === teachingImpactRequestId && requestedToken === token.value &&
    draft.id === selectedTeachingDraft.value?.id
  try {
    const result = await request<TeachingImpact>(`/api/v1/teaching-drafts/${draft.id}/learning-impact`, { signal: controller.signal })
    if (current()) teachingImpact.value = result
  } catch (error) {
    if (current() && !controller.signal.aborted) teachingImpactError.value = error instanceof Error ? error.message : '回看数据暂不可用。'
  } finally { if (current()) teachingImpactBusy.value = false }
}

function openTeacherAssignments() {
  learningTab.value = 'assignments'
  activePage.value = 'assessments'
  globalAssistantOpen.value = false
}

async function openTeacherReview(assignmentId: string) {
  await openAssistantResponseAction({ kind: 'assignment', target_id: assignmentId, title: '准备讲评', detail: '' })
}

async function createStudyPlan(preferences?: StudyPlanPreferences) {
  await saveStudyPlan(preferences, false)
}

async function refreshStudyPlan(preferences: StudyPlanPreferences) {
  await saveStudyPlan(preferences, true)
}

async function saveStudyPlan(preferences: StudyPlanPreferences | undefined, refresh: boolean) {
  if (user.value?.role !== 'student' || studyPlanBusy.value) return
  const courseId = selectedStudyCourseId.value
  if (!courseId) { platformStatus.value = '请先选择一门课程。'; return }
  assistantDraftCourseId.value = courseId
  studyPlanBusy.value = true
  const requestedToken = token.value
  try {
    const previous = selectedStudyPlan.value
    const path = refresh && previous ? `/api/v1/study-plans/${previous.id}/refresh` : '/api/v1/study-plans'
    const plan = await request<StudyPlan>(path, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(refresh && previous ? { preferences } : { course_id: courseId, preferences }),
    })
    if (user.value?.role !== 'student' || requestedToken !== token.value) return
    studentStudyPlans.value = [plan, ...studentStudyPlans.value.filter((item) => item.course_id !== courseId)]
    if (selectedStudyCourseId.value === courseId) {
      assistantView.value = 'tools'
      globalAssistantOpen.value = true
      platformStatus.value = plan.refresh_notice || `已保存「${plan.course_title}」第 ${plan.revision} 版安排。`
    }
  } catch (error) { if (token.value === requestedToken) platformStatus.value = error instanceof Error ? error.message : '学习安排暂未保存，请重试' }
  finally { if (token.value === requestedToken) studyPlanBusy.value = false }
}

function reloadStudyPlan(plan: StudyPlan) {
  if (user.value?.role !== 'student') return
  studentStudyPlans.value = [plan, ...studentStudyPlans.value.filter(item => item.course_id !== plan.course_id)]
}

function showStudyPlan(courseId: string) {
  assistantDraftCourseId.value = courseId
  assistantView.value = 'tools'
  globalAssistantOpen.value = true
}

async function openStudyPlanTask(planId: string, itemId: string) {
  if (user.value?.role !== 'student') return
  const requestedToken = token.value
  try {
    const target = await request<StudyPlanTarget>(`/api/v1/study-plans/${planId}/items/${itemId}/target`)
    if (requestedToken !== token.value || user.value?.role !== 'student') return
    if (target.kind === 'assignment') {
      const assignment = await request<AssignmentRecord>(`/api/v1/assignments/${target.target_id}`)
      if (requestedToken !== token.value) return
      learningTab.value = 'assignments'; activePage.value = 'assessments'
      await openAssignment(assignment)
    } else if (target.kind === 'question' || target.kind === 'practice_feedback') {
      const question = await request<QuestionItem>(`/api/v1/questions/${target.target_id}`)
      if (requestedToken !== token.value) return
      learningTab.value = 'practice'; activePage.value = 'assessments'
      openQuestionPractice(question, target.practice_source || 'diagnostic')
      practicePlanAttemptId.value = target.attempt_id
    } else {
      const course = await request<CourseRecord>(`/api/v1/courses/${target.course_id}`)
      if (requestedToken !== token.value) return
      activePage.value = 'courses'
      await openCourseDetail(course)
      if (requestedToken !== token.value) return
      selectedOutlineSection.value = target.kind === 'section' ? selectedCourse.value?.sections.find(item => item.id === target.target_id) || null : null
    }
    if (requestedToken === token.value) globalAssistantOpen.value = false
  } catch (cause) { if (requestedToken === token.value) assistantActionError.value = cause instanceof Error ? cause.message : '任务暂不可打开，请刷新安排' }
}

async function loadAdminReport(days: 1 | 7 | 30) {
  if (user.value?.role !== 'admin' || adminReportBusy.value) return
  adminReportBusy.value = true
  adminReportError.value = ''
  const requestedToken = token.value
  try {
    const report = await request<AdminOperationsReport>(`/api/v1/admin/operations-report?days=${days}`)
    if (user.value?.role !== 'admin' || token.value !== requestedToken) return
    adminReport.value = report
    assistantView.value = 'tools'
    globalAssistantOpen.value = true
  } catch (error) {
    if (user.value?.role === 'admin' && token.value === requestedToken) adminReportError.value = error instanceof Error ? error.message : '巡检报告生成失败'
  } finally { adminReportBusy.value = false }
}

function downloadAdminReport() {
  const report = adminReport.value
  if (!report || user.value?.role !== 'admin') return
  const period = report.period_days === 1 ? '今日' : report.period_days === 7 ? '本周' : '近30天'
  const lines = [
    `# 平台${period}运行报告`,
    '', `生成时间：${new Date(report.generated_at).toLocaleString('zh-CN')}`,
    `统计窗口：${new Date(report.period_start).toLocaleString('zh-CN')} 至 ${new Date(report.generated_at).toLocaleString('zh-CN')}`,
    `整体状态：${report.overall_status === 'healthy' ? '正常' : '需要关注'}`,
    '', '## 关键数据',
    `- 已发布课程：${report.metrics.published_courses ?? 0}；缺资料课程：${report.metrics.missing_material_courses ?? 0}`,
    `- 就绪资料：${report.metrics.ready_documents ?? 0}；当前失败导入任务：${report.metrics.failed_jobs ?? 0}`,
    `- 本期课程问答：${report.metrics.period_rag_questions ?? 0}；新增作业：${report.metrics.period_assignments ?? 0}`,
    `- 模型调用：${report.metrics.period_model_calls ?? 0}；失败：${report.metrics.period_model_failures ?? 0}`,
    `- 估算 Token：${(report.metrics.period_input_tokens ?? 0) + (report.metrics.period_output_tokens ?? 0)}`,
    `- 失败登录：${report.metrics.period_failed_logins ?? 0}；限流：${report.metrics.period_rate_limited ?? 0}；服务异常：${report.metrics.period_server_errors ?? 0}`,
    '', '## 巡检结论',
    ...report.checks.map((item) => `- ${item.status === 'warning' ? '需关注' : item.status === 'healthy' ? '正常' : '提示'}｜${item.title}：${item.detail}`),
    '', '本报告由平台记录自动汇总，具体处置请在管理控制台核实。',
  ]
  const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = `平台运行报告-${report.period_days}天-${report.generated_at.slice(0, 10)}.md`
  link.click()
  URL.revokeObjectURL(url)
}

function clearAssistantWaitTimer() {
  if (assistantWaitTimer !== null) window.clearInterval(assistantWaitTimer)
  assistantWaitTimer = null
}

async function scrollAssistantToBottom() {
  assistantViewport.release()
  await nextTick()
  if (globalAssistantOpen.value && assistantView.value === 'chat' && assistantChatScroll.value) {
    assistantChatScroll.value.scrollTop = assistantTurns.value.length ? assistantChatScroll.value.scrollHeight : 0
    assistantFollowing.value = true
    assistantContentBelow.value = false
  }
}

function trackAssistantScroll() {
  const container = assistantChatScroll.value
  if (!container) return
  assistantFollowing.value = container.scrollHeight - container.scrollTop - container.clientHeight < 100
  if (assistantFollowing.value) assistantContentBelow.value = false
}

function assistantAnswerLayout(turnId: number) {
  assistantViewport.restore()
  if (assistantTurns.value.at(-1)?.id !== turnId) return
  if (!globalAssistantBusy.value) { trackAssistantScroll(); return }
  if (assistantFollowing.value && !readerAnswer.value) void scrollAssistantToBottom()
  else if (globalAssistantBusy.value) assistantContentBelow.value = true
}

function jumpToAssistantSources(event: MouseEvent) {
  const source = (event.currentTarget as HTMLElement).closest('.assistant-response')?.querySelector<HTMLDetailsElement>('details.assistant-sources')
  if (!source) return
  source.open = true
  void nextTick(() => {
    source.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
    source.querySelector('summary')?.focus({ preventScroll: true })
  })
}

function readAnswer(value: AskResponse, originalQuestion: string) {
  readerAnswer.value = { question: originalQuestion || '回答详情', answer: value }
}

async function openReaderSource(index: number) {
  const citation = readerAnswer.value?.answer.citations[index]
  if (!citation?.document_id) return
  await openCitation(citation)
}

async function scrollAssistantToLatestAnswer() {
  assistantViewport.release()
  await nextTick()
  const container = assistantChatScroll.value
  if (!globalAssistantOpen.value || assistantView.value !== 'chat' || !container) return
  const target = container.querySelector<HTMLElement>('.assistant-turn:last-child')
  if (!target) { void scrollAssistantToBottom(); return }
  container.scrollTop += target.getBoundingClientRect().top - container.getBoundingClientRect().top - 12
}

async function loadAssistantHistory(reset = true) {
  if ((!reset && assistantHistoryBusy.value) || !user.value) return
  const before = reset ? null : assistantHistory.value.at(-1)?.id
  if (!reset && (!assistantHistoryHasMore.value || !before)) return
  assistantHistoryBusy.value = true
  assistantHistoryError.value = ''
  const requestId = ++assistantHistoryRequestId
  assistantHistoryController?.abort()
  const controller = new AbortController()
  assistantHistoryController = controller
  const requestedToken = token.value
  const requestedUserId = user.value.id
  try {
    const records = await request<AssistantConversationRecord[]>(
      `/api/v1/tutor/conversations?limit=20&query=${encodeURIComponent(assistantHistoryQuery.value.trim())}${before ? `&before=${encodeURIComponent(before)}` : ''}`,
      { signal: controller.signal })
    if (requestId === assistantHistoryRequestId && requestedToken === token.value && requestedUserId === user.value?.id) {
      const seen = new Set(reset ? [] : assistantHistory.value.map((item) => item.id))
      assistantHistory.value = reset ? records : [
        ...assistantHistory.value, ...records.filter((item) => !seen.has(item.id)),
      ]
      assistantHistoryHasMore.value = records.length === 20
    }
  } catch (error) {
    if (requestId === assistantHistoryRequestId && !controller.signal.aborted && requestedToken === token.value && requestedUserId === user.value?.id) {
      assistantHistoryError.value = error instanceof Error ? error.message : '对话记录读取失败'
    }
  } finally {
    if (requestId === assistantHistoryRequestId) {
      assistantHistoryBusy.value = false
      assistantHistoryController = null
    }
  }
}

function clearAssistantMessagePaging() {
  assistantOlderSequence += 1
  assistantOlderController?.abort()
  assistantOlderController = null
  assistantOlderBusy.value = false
  assistantOlderError.value = ''
  assistantPagedConversationId.value = null
  assistantMessageBefore.value = null
  assistantMessageHasMore.value = false
  assistantMessageCount.value = null
  assistantViewport.clear()
}

function archivedAssistantTurn(item: HistoryItem, baseId: string | null): AssistantTurn {
  const course = item.context_verified
    ? platformCourses.value.find(courseItem => courseItem.id === item.assistant_course_id) : null
  const base = knowledgeBases.value.find(baseItem => baseItem.id === baseId)
  return { id: --assistantArchiveTurnId, question: item.question,
    displayQuestion: item.question.split('\n')[0].slice(0, 180),
    courseId: item.context_verified ? item.assistant_course_id || '' : '',
    courseTitle: course?.title || (base ? `历史资料：${base.name}` : ''), passage: null,
    error: '', contextChanged: false, expanded: false, sourcesExpanded: false,
    answer: { accepted: item.accepted, message: item.message, answer: item.answer, model: item.model,
      answer_mode: item.answer_mode, citations: item.citations,
      history_id: item.id, conversation_id: item.conversation_id, actions: item.actions ?? [], answer_scope: item.answer_scope, calculations: item.calculations ?? [], answer_review: item.answer_review, assignment_context: item.assignment_context } }
}

async function loadOlderAssistantMessages() {
  const conversationId = assistantPagedConversationId.value
  const before = assistantMessageBefore.value
  if (!user.value || !conversationId || !before || !assistantMessageHasMore.value ||
    assistantOlderBusy.value || globalAssistantBusy.value || assistantHistoryBusy.value) return
  const sequence = ++assistantOlderSequence
  const requestedToken = token.value
  const owner = user.value.id
  assistantOlderController?.abort()
  const controller = new AbortController()
  assistantOlderController = controller
  assistantViewport.save()
  assistantOlderBusy.value = true
  assistantOlderError.value = ''
  const current = () => sequence === assistantOlderSequence && requestedToken === token.value &&
    owner === user.value?.id && conversationId === assistantPagedConversationId.value &&
    conversationId === globalAssistantConversationId.value
  try {
    const page = await request<ConversationMessagePage>(`/api/v1/tutor/conversations/${conversationId}/messages/page?limit=20&before=${encodeURIComponent(before)}`,
      { signal: controller.signal })
    if (!current()) return
    if (page.conversation_id !== conversationId) throw new Error('会话范围不一致，请重新打开历史。')
    const loaded = new Set(assistantTurns.value.map(turn => turn.answer?.history_id).filter(Boolean))
    const incoming = page.items.filter(item => !loaded.has(item.id))
    // User input releases the anchor. If they moved while fetching, retain
    // their new position; otherwise keep the pre-loading-button geometry.
    assistantViewport.hold()
    assistantFollowing.value = false
    assistantTurns.value = [...incoming.map(item => archivedAssistantTurn(item, page.knowledge_base_id)), ...assistantTurns.value]
    assistantMessageBefore.value = page.next_before
    assistantMessageHasMore.value = page.has_more
    assistantMessageCount.value = page.message_count
    await nextTick()
    if (current()) assistantViewport.restore()
  } catch (error) {
    if (current() && !controller.signal.aborted) assistantOlderError.value = error instanceof Error ? error.message : '更早消息暂时无法读取，请重试。'
  } finally {
    if (sequence === assistantOlderSequence) { assistantOlderBusy.value = false; assistantOlderController = null }
  }
}

async function resumeAssistantConversation(record: Pick<AssistantConversationRecord, 'id'>) {
  if (assistantHistoryBusy.value || globalAssistantBusy.value || !user.value) return
  clearAssistantMessagePaging()
  const requestId = ++assistantHistoryRequestId
  assistantHistoryController?.abort()
  const controller = new AbortController()
  assistantHistoryController = controller
  assistantHistoryBusy.value = true
  assistantHistoryError.value = ''
  const requestedToken = token.value
  const requestedUserId = user.value.id
  try {
    const page = await request<ConversationMessagePage>(`/api/v1/tutor/conversations/${record.id}/messages/page?limit=20`, { signal: controller.signal })
    const messages = page.items
    if (requestId !== assistantHistoryRequestId || requestedToken !== token.value || requestedUserId !== user.value?.id) return
    if (!messages.length) { assistantHistoryError.value = '此对话暂无可恢复的消息。'; return }
    if (page.conversation_id !== record.id) throw new Error('会话范围不一致，请重新打开历史。')
    const base = page.knowledge_base_id ? knowledgeBases.value.find((item) => item.id === page.knowledge_base_id) : null
    const latest = messages.at(-1)
    const course: CourseRecord | null = latest?.context_verified
      ? platformCourses.value.find(item => item.id === latest.assistant_course_id) || null : null
    if (user.value.role !== 'admin') {
      // A display-name match is not a course association; unknown legacy scope must not inherit another selection.
      assistantDraftCourseId.value = course?.id || ''
      await nextTick()
    }
    if (requestId !== assistantHistoryRequestId || requestedToken !== token.value || requestedUserId !== user.value?.id) return
    resetAssistantConversation()
    restoreAssignmentContext(latest?.assignment_context)
    assistantHistoryScopeNotice.value = latest?.context_verified
      ? course ? `已按保存的课程范围恢复：${course.title}。` : '已恢复历史回答；该轮没有选定课程。'
      : !course && user.value?.role !== 'admin'
      ? `已恢复历史回答${base ? `，资料范围为“${base.name}”` : ''}。记录未能确认当前课程关联，已取消原选课；如需处理课程任务，请先选择课程。`
      : ''
    if (!latest?.answer_mode) assistantHistoryScopeNotice.value += ' 原回答模式未记录；下一问将新建会话，不自动继承旧内容。'
    else assistantHistoryScopeNotice.value += ` 后续沿用“${answerModeLabel(latest.answer_mode)}”。`
    assistantTurns.value = messages.map(item => archivedAssistantTurn(item, page.knowledge_base_id))
    assistantPagedConversationId.value = page.conversation_id
    assistantMessageBefore.value = page.next_before
    assistantMessageHasMore.value = page.has_more
    assistantMessageCount.value = page.message_count
    globalAssistantAnswer.value = assistantTurns.value.at(-1)?.answer ?? null
    globalAssistantConversationId.value = record.id
    assistantConversationKnowledgeBaseId.value = page.knowledge_base_id
    assistantConversationDomainKey.value = latest?.answer_scope?.domain_key || ''
    assistantConversationAnswerMode.value = latest?.answer_mode ?? null
    assistantActionError.value = ''
    assistantView.value = 'chat'
    await scrollAssistantToLatestAnswer()
  } catch (error) {
    if (requestId === assistantHistoryRequestId && requestedToken === token.value && requestedUserId === user.value?.id) {
      assistantHistoryError.value = error instanceof Error ? error.message : '对话恢复失败'
    }
  } finally { if (requestId === assistantHistoryRequestId) { assistantHistoryBusy.value = false; assistantHistoryController = null } }
}

function resetAssistantConversation() {
  assistantAssignmentContext.value = null
  clearAssistantMessagePaging()
  assistantHistoryScopeNotice.value = ''
  const pending = assistantTurns.value.at(-1)
  if (globalAssistantBusy.value && pending?.requestId && token.value) {
    void cancelAnswerRequest(apiBase, token.value, pending.requestId, 'reset').catch(() => undefined)
  }
  assistantRequestId += 1
  assistantAbortController?.abort()
  assistantAbortController = null
  clearAssistantWaitTimer()
  globalAssistantBusy.value = false
  assistantWaitSeconds.value = 0
  assistantTurns.value = []
  assistantFollowing.value = true
  assistantContentBelow.value = false
  assistantHasUnread.value = false
  assistantPendingContextChange.value = false
  assistantNoteTurnId.value = null
  assistantAnswerPassage.value = null
  studyNoteDraft.value = ''
  globalAssistantAnswer.value = null
  globalAssistantConversationId.value = null
  assistantConversationKnowledgeBaseId.value = null
  assistantConversationDomainKey.value = ''
  assistantConversationAnswerMode.value = null
  globalAssistantQuestion.value = ''
}

async function stopAssistantWaiting() {
  if (!globalAssistantBusy.value) return
  const sequence = ++assistantRequestId
  const requestedToken = token.value
  const owner = user.value?.id
  const latest = assistantTurns.value.at(-1)
  const courseId = assistantDraftCourseId.value
  const cancellation = latest?.requestId ? cancelAnswerRequest<AskResponse>(apiBase, requestedToken, latest.requestId) : null
  assistantAbortController?.abort()
  assistantAbortController = null
  clearAssistantWaitTimer()
  globalAssistantBusy.value = false
  if (latest && !latest.answer) {
    latest.partial = ''
    latest.requestState = cancellation ? 'unknown' : 'cancelled'
    latest.error = cancellation ? '正在确认停止结果…' : '已停止发送，尚未开始生成。'
  }
  if (!cancellation || !latest) return
  latest.checkingReceipt = true
  try {
    const receipt = await cancellation
    if (sequence !== assistantRequestId || owner !== user.value?.id || requestedToken !== token.value) return
    latest.requestState = receipt.status
    latest.error = receipt.message
    // Keep the old turn's receipt, but never install its conversation into a changed course.
    if (receipt.answer && courseId === assistantDraftCourseId.value) applyAssistantReceipt(latest, receipt)
  } catch {
    if (sequence === assistantRequestId && owner === user.value?.id) latest.error = '停止结果尚未确认，请先查看处理结果。'
  } finally { latest.checkingReceipt = false }
}

function applyAssistantReceipt(turn: AssistantTurn, receipt: AnswerReceipt<AskResponse>) {
  if (!user.value) return
  turn.requestId = receipt.request_id
  turn.requestState = receipt.status
  turn.partial = ''
  turn.error = receipt.answer ? '' : receipt.message
  if (!receipt.answer) return
  turn.answer = receipt.answer
  acknowledgeAnswer(user.value!.id, 'assistant', receipt.request_id)
  // Restoring an older turn is read-only; only the latest turn may become the follow-up context.
  if (assistantTurns.value.at(-1)?.id === turn.id && (!turn.courseId || turn.courseId === assistantDraftCourseId.value)) {
    if (assistantPagedConversationId.value === receipt.answer.conversation_id) assistantMessageCount.value = null
    else clearAssistantMessagePaging()
    globalAssistantAnswer.value = receipt.answer
    restoreAssignmentContext(receipt.answer.assignment_context)
    globalAssistantConversationId.value = receipt.answer.conversation_id
    assistantConversationKnowledgeBaseId.value = receipt.context.knowledge_base_id || null
    assistantConversationDomainKey.value = receipt.answer.answer_scope?.domain_key || ''
    assistantConversationAnswerMode.value = receipt.answer.answer_mode
  }
}

async function retryAssistantTurn(turn: AssistantTurn) {
  if (globalAssistantBusy.value || turn.checkingReceipt) return
  if (turn.requestId && (turn.requestState === 'in_progress' || turn.requestState === 'unknown')) {
    const requestedToken = token.value
    const owner = user.value?.id
    turn.checkingReceipt = true
    try {
      const receipt = await readAnswerReceipt<AskResponse>(apiBase, requestedToken, turn.requestId)
      if (requestedToken === token.value && owner === user.value?.id && assistantTurns.value.includes(turn)) applyAssistantReceipt(turn, receipt)
    } catch { turn.error = '暂时无法确认结果，请稍后再查看；本次没有重新调用模型。' }
    finally { turn.checkingReceipt = false }
    return
  }
  if (turn.courseId !== assistantDraftCourseId.value && user.value?.role !== 'admin') {
    assistantActionError.value = '请先切回原课程，再重新尝试这条问题。'
    return
  }
  if (turn.sourceDocumentId && !turn.passage) {
    assistantActionError.value = '请重新打开原资料并选取内容，再发送选段问题。'
    return
  }
  if (turn.requestId && user.value) acknowledgeAnswer(user.value.id, 'assistant', turn.requestId)
  assistantTurns.value = assistantTurns.value.filter((item) => item.id !== turn.id)
  void askGlobalAssistant(turn.question, turn.passage ?? undefined)
}

async function restoreAssistantRequest(value: AnswerReceipt) {
  if (globalAssistantBusy.value || assistantHistoryBusy.value || assistantOlderBusy.value || !user.value || assistantTurns.value.some(item => item.checkingReceipt)) return
  const owner = user.value.id
  const requestedToken = token.value
  const receipt = value as AnswerReceipt<AskResponse>
  const existing = assistantTurns.value.find(item => item.requestId === receipt.request_id)
  if (existing) { applyAssistantReceipt(existing, receipt); return }
  assistantDraftCourseId.value = receipt.context.assistant_course_id || ''
  await nextTick()
  if (owner !== user.value?.id || requestedToken !== token.value || globalAssistantBusy.value) return
  const turn: AssistantTurn = { id: ++assistantRequestId, question: receipt.question, displayQuestion: receipt.question,
    courseId: receipt.context.assistant_course_id || '', courseTitle: assistantSelectedCourse.value?.title || '',
    passage: null, answer: null, error: '', contextChanged: false, expanded: false, sourcesExpanded: false,
    sourceDocumentId: receipt.context.source_document_id }
  assistantTurns.value.push(turn)
  applyAssistantReceipt(assistantTurns.value.at(-1)!, receipt)
  assistantView.value = 'chat'
  void scrollAssistantToLatestAnswer()
}

async function askGlobalAssistant(prompt?: string, passage?: SelectedPassage) {
  const value = (prompt ?? globalAssistantQuestion.value).trim()
  if (!value || globalAssistantBusy.value || assistantHistoryBusy.value || assistantOlderBusy.value || !user.value) return
  if (!passage && canManage.value && /帮我|请|生成|准备|安排|调整|申请|优化|完善/.test(value)) {
    const route=/排课|调课|重排|安排.*(?:课程|上课|课次)/.test(value)?'schedule':/提取.*题|识别.*题|资料.*选题/.test(value)?'materials':/课程介绍|课程大纲|教学大纲|学习目标/.test(value)?'course':null
    if (route) { globalAssistantQuestion.value='';openTeachingWorkbench(route,value);return }
  }
  assistantViewport.release()
  const unresolved = assistantTurns.value.find(item => item.question === value && item.courseId === assistantDraftCourseId.value &&
    (item.requestState === 'in_progress' || item.requestState === 'unknown'))
  if (unresolved) { await retryAssistantTurn(unresolved); return }
  assistantActionError.value = ''
  assistantHistoryScopeNotice.value = ''
  const requestedCourseId = user.value?.role === 'teacher' || user.value?.role === 'student' ? assistantDraftCourseId.value : null
  const requestedToken = token.value
  const requestedUserId = user.value.id
  const requestedMode = assistantActiveMode.value
  const requestId = ++assistantRequestId
  const controller = new AbortController()
  assistantAbortController = controller
  const turn: AssistantTurn = {
    id: requestId, question: value,
    displayQuestion: passage ? `${value.split('\n')[0]}\n《${passage.sourceTitle}》第 ${passage.pageNumber} 页选段` : value,
    courseId: assistantDraftCourseId.value, courseTitle: assistantSelectedCourse.value?.title || '',
    passage: passage ?? null, answer: null, error: '', contextChanged: false, expanded: false, sourcesExpanded: false, partial: '', sourceDocumentId: passage?.documentId,
  }
  assistantTurns.value.push(turn)
  // Mutate the reactive proxy, not the raw object that was pushed into the ref array.
  const activeTurn = assistantTurns.value.at(-1)!
  assistantView.value = 'chat'
  assistantHasUnread.value = false
  assistantAnswerPassage.value = null
  assistantNoteTurnId.value = null
  studyNoteDraft.value = ''
  globalAssistantQuestion.value = ''
  globalAssistantBusy.value = true
  assistantContextExpanded.value = false
  assistantWaitSeconds.value = 0
  assistantWaitLabel.value = user.value?.role === 'student' ? '正在准备课程回答…' : '正在联系 AI 助手…'
  assistantWaitTimer = window.setInterval(() => { assistantWaitSeconds.value += 1 }, 1000)
  void scrollAssistantToBottom()
  try {
    const courseId = requestedCourseId || null
    const params = new URLSearchParams({ purpose: assistantScope.value })
    if (courseId) params.set('course_id', courseId)
    if (passage) params.set('source_document_id', passage.documentId)
    const scope = await request<AssistantMaterialScope>(`/api/v1/assistant/context?${params}`, { signal: controller.signal })
    if (requestId !== assistantRequestId) return
    assistantMaterialScope.value = scope
    assistantMaterialScopeError.value = ''
    activeTurn.contextChanged = assistantPendingContextChange.value || Boolean(globalAssistantConversationId.value &&
      (!assistantConversationAnswerMode.value || assistantConversationDomainKey.value !== scope.domain_key))
    assistantWaitLabel.value = scope.ready_document_count ? '正在检索所选课程资料并准备讲解…' : '正在准备回答；当前课程无可检索资料…'
    const data = await sendAnswerRequest<AskResponse>(apiBase, requestedToken, requestedUserId, 'assistant', {
        question: value, knowledge_base_id: null,
        answer_mode: requestedMode, conversation_id: activeTurn.contextChanged ? null : globalAssistantConversationId.value,
        assistant_scope: assistantScope.value, assistant_course_id: courseId,
        assistant_assignment_id: assistantAssignmentContext.value?.id || null,
        assistant_assignment_question_id: assistantAssignmentContext.value?.questionId || null,
        expected_domain_key: scope.domain_key,
        source_document_id: passage?.documentId ?? null, page_context: assistantPageContext.value,
    }, controller.signal, {
      onRequest: (id, state) => { if (requestId === assistantRequestId) { activeTurn.requestId = id; activeTurn.requestState = state } },
      onStage: (label) => { if (requestId === assistantRequestId) assistantWaitLabel.value = label },
      onDelta: (text) => {
        if (requestId !== assistantRequestId) return
        const container = assistantChatScroll.value
        const nearBottom = !container || assistantFollowing.value
        activeTurn.partial = (activeTurn.partial || '') + text
        if (nearBottom && !readerAnswer.value) void scrollAssistantToBottom()
        else assistantContentBelow.value = true
      },
      onReset: () => { if (requestId === assistantRequestId) activeTurn.partial = '' },
    })
    if (requestId !== assistantRequestId || requestedToken !== token.value || requestedUserId !== user.value?.id ||
        (requestedCourseId !== null && requestedCourseId !== assistantDraftCourseId.value)) return
    activeTurn.answer = data
    activeTurn.partial = ''
    globalAssistantAnswer.value = data
    if (assistantPagedConversationId.value === data.conversation_id) assistantMessageCount.value = null
    else clearAssistantMessagePaging()
    globalAssistantConversationId.value = data.conversation_id
    assistantConversationKnowledgeBaseId.value = data.answer_scope?.storage_knowledge_base_id || null
    assistantConversationDomainKey.value = data.answer_scope?.domain_key || ''
    assistantConversationAnswerMode.value = data.answer_mode
    assistantPendingContextChange.value = false
    if (passage && data.accepted && isGeneratedModelAnswer(data)) {
      assistantAnswerPassage.value = passage
      assistantNoteTurnId.value = turn.id
      studyNoteDraft.value = data.answer
    }
    if (!globalAssistantOpen.value || assistantView.value !== 'chat') assistantHasUnread.value = true
    if (assistantFollowing.value && !readerAnswer.value) void scrollAssistantToLatestAnswer()
    else assistantContentBelow.value = true
  } catch (error) {
    if (requestId !== assistantRequestId) return
    activeTurn.partial = ''
    activeTurn.error = error instanceof Error ? error.message : 'AI 助手暂时无法回答'
    platformStatus.value = activeTurn.error
    if (!globalAssistantOpen.value || assistantView.value !== 'chat') assistantHasUnread.value = true
    if (assistantFollowing.value && !readerAnswer.value) void scrollAssistantToLatestAnswer()
    else assistantContentBelow.value = true
  } finally {
    if (requestId === assistantRequestId) {
      clearAssistantWaitTimer()
      assistantAbortController = null
      globalAssistantBusy.value = false
    }
  }
}

function openStudentShortcut(target: 'progress' | 'assignments' | 'courses' | 'wrong') {
  if (target === 'progress') { studentHome.value?.showProgress(); return }
  if (target === 'courses') {
    activePage.value = 'courses'
    return
  }
  learningTab.value = target === 'wrong' ? 'wrong' : 'assignments'
  activePage.value = 'assessments'
}

function openProgressCourse(courseId: string) {
  const course = platformCourses.value.find((item) => item.id === courseId)
  if (course) openCourseDetail(course)
}

async function openCourseMaterial(material: DocumentRecord) {
  if (selectedCourse.value) assistantDraftCourseId.value = selectedCourse.value.id
  await openDocumentPreview(material)
}

function captureDocumentSelection(pageNumber: number, event: MouseEvent) {
  if (user.value?.role !== 'student' || !selectedDocumentContent.value) return
  const source = event.currentTarget as HTMLElement
  const selection = window.getSelection()
  if (!selection || !selection.anchorNode || !selection.focusNode
    || !source.contains(selection.anchorNode) || !source.contains(selection.focusNode)) return
  const text = selection.toString().trim()
  if (!text) return
  if (text.length < 10 || text.length > 1200) {
    platformStatus.value = '请选择 10 至 1200 个字的同一页原文。'
    selectedPassage.value = null
    return
  }
  const document = selectedDocumentContent.value.document
  const courses = platformCourses.value.filter((item) => studentCourseKnowledgeBases.value[item.id]?.some((base) => base.id === document.knowledge_base_id))
  const course = courses.find(item => item.id === assistantDraftCourseId.value) || (courses.length === 1 ? courses[0] : null)
  if (!course) {
    selectedPassage.value = null
    platformStatus.value = courses.length ? '这份资料用于多门课程，请先在助手中选择具体课程，或从课程详情打开资料。' : '当前资料未关联可访问课程，暂不能保存学习笔记。'
    return
  }
  studyNoteStatus.value = ''
  studyNoteStatusError.value = false
  selectedPassage.value = { courseId: course.id, documentId: document.id, knowledgeBaseId: document.knowledge_base_id,
    sourceTitle: document.name, pageNumber, text }
}

async function askSelectedPassage(kind: 'explain' | 'summary' | 'note') {
  const passage = selectedPassage.value
  if (!passage || user.value?.role !== 'student') return
  const document = selectedDocumentContent.value?.document
  if (!document || document.id !== passage.documentId) return
  if (!guardFormExit(() => { void askSelectedPassage(kind) }, '打开AI助手', ['course', 'draft', 'document'])) return
  if (!modelStatus.value?.llm_configured || !document.external_model_allowed) {
    studyNoteStatus.value = !modelStatus.value?.llm_configured
      ? '当前没有可用的在线 AI 模型，暂不能生成选段讲解；你仍可保存原文摘录。'
      : '这份资料尚未获准发送给外部模型，暂不能生成选段讲解；你仍可保存原文摘录。'
    studyNoteStatusError.value = true
    return
  }
  const instruction = kind === 'explain' ? '像老师一样解释这段内容，指出关键概念并举一个简短例子。'
    : kind === 'summary' ? '总结这段内容的要点，保留必要的术语和逻辑关系。'
      : '把这段内容整理成便于复习的学习笔记，包含核心概念、关键结论和一个自测问题。'
  assistantDraftCourseId.value = passage.courseId
  selectedKnowledgeBaseId.value = passage.knowledgeBaseId
  selectedDocumentContent.value = null
  selectedCourse.value = null; selectedTeachingDraft.value = null; readerAnswer.value = null
  globalAssistantOpen.value = true
  await askGlobalAssistant(`${instruction}\n资料：${passage.sourceTitle}，第 ${passage.pageNumber} 页。\n选段：\n${passage.text}`, passage)
}

async function saveStudyNote(passage: SelectedPassage | null, origin: 'excerpt' | 'assistant') {
  if (!passage || user.value?.role !== 'student' || studyNoteBusy.value) return
  const content = origin === 'assistant' ? studyNoteDraft.value.trim() : passage.text
  if (!content) return
  studyNoteBusy.value = true
  studyNoteStatus.value = ''
  studyNoteStatusError.value = false
  try {
    const note = await request<StudyNote>('/api/v1/study-notes', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ course_id: passage.courseId, document_id: passage.documentId,
        page_number: passage.pageNumber, excerpt: passage.text, content, origin }),
    })
    studentStudyNotes.value = [note, ...studentStudyNotes.value]
    platformStatus.value = `已保存「${note.source_title}」第 ${note.page_number} 页的学习笔记。`
    studyNoteStatus.value = platformStatus.value
    if (origin === 'assistant') assistantAnswerPassage.value = null
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '学习笔记保存失败'; studyNoteStatus.value = platformStatus.value; studyNoteStatusError.value = true }
  finally { studyNoteBusy.value = false }
}

async function openStudyNote(note: StudyNote) {
  if (!note.source_available || !note.document_id) return
  activePage.value = 'tutor'
  globalAssistantOpen.value = false
  await openDocumentById(note.document_id, note.page_number)
}

async function deleteStudyNote(note: StudyNote) {
  if (studyNoteBusy.value || !window.confirm(`确定删除「${note.source_title}」第 ${note.page_number} 页的笔记吗？`)) return
  studyNoteBusy.value = true
  studyNoteStatus.value = ''
  studyNoteStatusError.value = false
  try {
    await request<void>(`/api/v1/study-notes/${note.id}`, { method: 'DELETE' })
    studentStudyNotes.value = studentStudyNotes.value.filter((item) => item.id !== note.id)
    platformStatus.value = '学习笔记已删除。'
    studyNoteStatus.value = platformStatus.value
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '学习笔记删除失败'; studyNoteStatus.value = platformStatus.value; studyNoteStatusError.value = true }
  finally { studyNoteBusy.value = false }
}

async function openCitation(citation: Citation) {
  if (!citation.document_id) { platformStatus.value = '这条历史引用缺少文档定位信息，请重新提问获取可跳转引用。'; return }
  const owner = user.value?.id, page = activePage.value, assistant = globalAssistantOpen.value, reader = readerAnswer.value
  returnFromCitation = () => { if (user.value?.id === owner) { activePage.value = page; globalAssistantOpen.value = assistant; readerAnswer.value = reader } }
  readerAnswer.value = null
  globalAssistantOpen.value = false
  await openDocumentById(citation.document_id, citation.page_number)
  if (!selectedDocumentContent.value) { const restore = returnFromCitation; returnFromCitation = null; restore?.() }
}

function openAnswerEvidence(value: AskResponse, index: number) {
  const citation = value.citations[index]
  if (citation) void openCitation(citation)
}

function syncStudentCourseFromKnowledgeBase(knowledgeBaseId: string) {
  if (user.value?.role !== 'student') return
  const current = assistantDraftCourseId.value
  if (studentCourseKnowledgeBases.value[current]?.some((base) => base.id === knowledgeBaseId)) return
  const course = platformCourses.value.find((item) => studentCourseKnowledgeBases.value[item.id]?.some((base) => base.id === knowledgeBaseId))
  assistantDraftCourseId.value = course?.id || ''
}

function setAnswerMode(mode: AnswerMode) {
  if (busy.value || mode === answerMode.value) return
  if (tutorHistoryBusy.value) { answerRequestId += 1; tutorHistoryBusy.value = false }
  answerMode.value = mode
  localStorage.setItem(answerModeStorageKey, mode)
  answer.value = null
  activeConversationId.value = null
  status.value = answerModeOptions.find((option) => option.value === mode)?.description ?? ''
}

class ApiError extends Error {
  constructor(message: string, readonly status: number) { super(message) }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const actor=user.value?.id, requestedToken=token.value
  const task = path==='/api/v1/assistant/tasks' && options.method==='POST' && typeof options.body==='string' && actor
    ? await prepareTeacherTask(actor,JSON.parse(options.body)) : null
  if (task) {
    if (actor!==user.value?.id || requestedToken!==token.value) throw new ApiError('账号已变化，请重新打开任务。',409)
    options={...options,body:task.body}
  }
  const headers = new Headers(options.headers)
  if (token.value) headers.set('Authorization', `Bearer ${token.value}`)
  const response = await fetch(`${apiBase}${path}`, { ...options, headers })
  const raw = await response.text()
  let data = null
  try { data = raw ? JSON.parse(raw) : null } catch {
    throw new ApiError('服务暂时不可用，请稍后重试。', response.status)
  }
  if (!response.ok) {
  const detail = Array.isArray(data?.detail) ? data.detail.map((item: { msg?: string }) => item.msg || '字段不符合要求').join('；') : typeof data?.detail === 'object' ? data.detail?.message : data?.detail
    throw new ApiError(detail || '请求失败', response.status)
  }
  if (task) task.acknowledge()
  return data as T
}

function pageLoader<T>(resource: string, scopeId = '', extra = '') {
  return async (page: number, pageSize: number) => {
    const owner = user.value?.id, requestedToken = token.value
    const params = new URLSearchParams({ page: String(page), page_size: String(pageSize) })
    if (scopeId) params.set('scope_id', scopeId)
    for (const [key, value] of new URLSearchParams(extra)) params.set(key, value)
    const result = await request<PageResult<T>>(`/api/v1/paged/${resource}?${params}`)
    if (resource === 'reviews' && owner === user.value?.id && requestedToken === token.value) trackReviewItems(result.items as unknown as QuestionReview[])
    return result
  }
}

async function firstPage<T>(resource: string, scopeId = '', extra = '', pageSize = 10) {
  return (await pageLoader<T>(resource, scopeId, extra)(1, pageSize)).items
}

async function loadSystemStatus() {
  modelStatus.value = await request<SystemStatus>('/api/v1/system')
  indexedChunks.value = modelStatus.value.indexed_chunks
}

async function loadAppData() {
  // /system is protected when authentication is enabled, so the anonymous
  // initialization attempt cannot supply model status for a fresh login.
  // Reuse it after token restoration, but load it once after a new login.
  await Promise.all([
    loadKnowledgeBases(), loadPlatformData(), loadDocumentJobs(),
    ...(!modelStatus.value ? [loadSystemStatus()] : []),
  ])
}

async function loadDocumentJobs() {
  if (!canManage.value) {
    documentJobs.value = []
    return
  }
  documentJobs.value = await firstPage<DocumentJob>('jobs', selectedKnowledgeBaseId.value)
}

async function loadPlatformData() {
  const currentSequence = ++platformDataSequence
  platformLoading.value = true
  platformLoadError.value = ''
  const summarySequence = ++dashboardRequestSequence
  dashboardController?.abort()
  dashboardController = null
  dashboardRefreshing.value = false
  const requestedToken = token.value
  const owner = user.value?.id
  const current = () => currentSequence === platformDataSequence && requestedToken === token.value && owner === user.value?.id
  try {
    const [summary, courses, questions, taskItems] = await Promise.all([
      request<DashboardSummary>('/api/v1/dashboard'),
      request<CourseRecord[]>('/api/v1/courses'),
      request<QuestionItem[]>('/api/v1/questions'),
      request<AssignmentRecord[]>('/api/v1/assignments'),
    ])
    if (!current()) return
    if (summarySequence === dashboardRequestSequence) { dashboardSummary.value = summary; dashboardError.value = '' }
    platformCourses.value = courses
    courseCatalogRevision.value += 1
    if (!newQuestionCourseId.value && courses[0]) newQuestionCourseId.value = courses[0].id
    if (!newAssignmentCourseId.value && courses[0]) newAssignmentCourseId.value = courses[0].id
    if (!draftGenerateCourseId.value && courses[0]) draftGenerateCourseId.value = courses[0].id
    questionBank.value = questions
    await loadQuestionPage(questionPageIndex.value)
    if (!current()) return
    assignments.value = taskItems
    if (user.value?.role === 'student' || user.value?.role === 'teacher' || user.value?.role === 'admin') {
      const late = await request<LateSubmissionRequest[]>('/api/v1/late-submission-requests')
      if (!current()) return
      lateSubmissionRequests.value = late
    }
    if (user.value?.role === 'student') {
      const [wrong, reports, practice, linkedBases, sessionsByCourse, plans, notes] = await Promise.all([
        request<WrongQuestionRecord[]>('/api/v1/wrong-questions'), request<LearningReport[]>('/api/v1/learning/reports'),
        request<PracticeRecommendation[]>('/api/v1/practice/recommendations?limit=10'),
        request<Record<string,LinkedKnowledgeBase[]>>('/api/v1/courses/material-bindings'),
        request<{items: CourseSessionRecord[]}>(`/api/v1/timetable?start=${dayKey()}&end=${addDays(dayKey(),35)}`),
        request<StudyPlan[]>('/api/v1/study-plans'),
        request<StudyNote[]>('/api/v1/study-notes'),
      ])
      if (!current()) return
      wrongQuestions.value = wrong
      learningReports.value = reports
      practiceRecommendations.value = practice
      studentCourseKnowledgeBases.value = Object.fromEntries(courses.map(course => [course.id, linkedBases[course.id] || []]))
      studentCourseSessions.value = sessionsByCourse.items
      studentStudyPlans.value = plans
      studentStudyNotes.value = notes
    } else if (user.value?.role === 'teacher') {
      const [reviews, drafts, pending] = await Promise.all([
        pageLoader<QuestionReview>('reviews')(1, 5), firstPage<TeachingDraft>('drafts'),
        pageLoader<QuestionReview>('reviews', '', 'status=pending')(1, 1),
      ])
      if (!current()) return
      questionReviews.value = reviews.items
      teachingDrafts.value = drafts
      pendingReviewCount.value = pending.total
      if (courses[0]) {
        const overview = await request<CourseAnalytics>(`/api/v1/courses/${courses[0].id}/analytics`)
        if (!current()) return
        courseAnalytics.value = overview
      }
    } else if (user.value?.role === 'admin') {
      const [metrics, users, config, evaluations, security, logs, drafts, usage, quotas, insights] = await Promise.all([
        request<AdminMetrics>('/api/v1/admin/metrics'), firstPage<AdminUser>('users'),
        request<ModelConfig>('/api/v1/admin/model-config'), firstPage<EvaluationRun>('evaluations'), request<SecurityOverview>('/api/v1/admin/security'),
        firstPage<AuditLog>('audits'), firstPage<TeachingDraft>('drafts'), request<ModelUsageOverview>('/api/v1/admin/model-usage?days=30'), request<ModelQuota[]>('/api/v1/admin/model-quotas'), request<AssistantAction[]>('/api/v1/admin/assistant-insights'),
      ])
      if (!current()) return
      const quotaEdited = modelQuotas.value.some(item => modelQuotaDrafts.value[item.role] !== item.daily_limit)
      adminMetrics.value = metrics; adminUsers.value = users
      if (!modelSettingsDirty.value) { adminModelConfig.value = config; modelConfigBaseline.value = JSON.parse(JSON.stringify(config)) }
      evaluationRuns.value = evaluations; securityOverview.value = security; auditLogs.value = logs; teachingDrafts.value = drafts; modelUsageOverview.value = usage; modelQuotas.value = quotas; adminInsights.value = insights
      if (!quotaEdited) modelQuotaDrafts.value = Object.fromEntries(quotas.map((item) => [item.role, item.daily_limit])) as Record<ModelQuota['role'], number>
    }
  } catch (error) {
    if (current()) { platformLoadError.value = error instanceof Error ? error.message : '学习安排暂时读取失败，请重试。'; platformStatus.value = platformLoadError.value }
  } finally { if (current()) platformLoading.value = false }
}

async function refreshDashboardSummary() {
  if (!user.value || dashboardRefreshing.value) return
  const sequence = ++dashboardRequestSequence
  const requestedToken = token.value
  const owner = user.value.id
  dashboardController?.abort()
  const controller = new AbortController()
  dashboardController = controller
  dashboardRefreshing.value = true
  dashboardError.value = ''
  try {
    const result = await request<DashboardSummary>('/api/v1/dashboard', { signal: controller.signal })
    if (sequence === dashboardRequestSequence && requestedToken === token.value && owner === user.value?.id) dashboardSummary.value = result
  } catch (error) {
    if (sequence === dashboardRequestSequence && requestedToken === token.value && !controller.signal.aborted) {
      dashboardError.value = error instanceof Error ? error.message : '刷新失败，暂时保留上次读取的数据。'
    }
  } finally {
    if (sequence === dashboardRequestSequence) { dashboardRefreshing.value = false; dashboardController = null }
  }
}

function openHomeQuestions() {
  questionFilterCourse.value = ''; questionFilterType.value = ''; questionFilterKeyword.value = ''
  learningTab.value = 'questions'; activePage.value = 'assessments'
  const requestedToken = token.value
  void loadQuestionPage(1).catch(error => { if (requestedToken === token.value) platformStatus.value = error instanceof Error ? error.message : '题库暂时无法读取，请重试。' })
}

function showHomeTasks(kind: 'review' | 'late' | 'overdue') {
  dashboardTaskKind.value = kind
  void nextTick(() => {
    dashboardTeachingTasks.value?.scrollIntoView({ block: 'start', behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
    dashboardTeachingTasks.value?.focus({ preventScroll: true })
  })
}

async function openHomeAssignment(id: string) {
  if (homeAssignmentOpening.value) return
  homeAssignmentOpening.value = id
  const returnPoint = { id, top: window.scrollY, focus: document.activeElement instanceof HTMLElement ? document.activeElement : null }
  const requestedToken = token.value
  dashboardError.value = ''
  try {
  if (user.value?.role !== 'student' && dashboardTaskKind.value === 'late') {
    try {
      const item = await request<AssignmentRecord>(`/api/v1/assignments/${id}`)
      if (requestedToken !== token.value) return
      homeLateAssignmentId.value = id
      homeLateAssignmentTitle.value = item.title
      lateApprovalOpen.value=true
      selectedAssignment.value = null
      learningTab.value = 'assignments'; activePage.value = 'assessments'
      await nextTick()
      homeLateApprovalPanel.value?.scrollIntoView({ block: 'start', behavior: 'smooth' })
      homeLateApprovalPanel.value?.focus({ preventScroll: true })
    } catch (error) {
      if (requestedToken === token.value) dashboardError.value = error instanceof Error ? error.message : '申请暂不可查看，请刷新后重试。'
    }
    return
  }
  // Finish navigation before opening: a restored edit belongs to the new
  // workspace and must not be mistaken for an edit being abandoned at home.
  learningTab.value = 'assignments'; activePage.value = 'assessments'
  await nextTick()
  if (requestedToken !== token.value || activePage.value !== 'assessments') return
  if (await openAssignment({ id })) {
    if (requestedToken !== token.value || activePage.value !== 'assessments') return
    homeAssignmentReturn = returnPoint
  } else if (requestedToken === token.value) {
    activePage.value = 'dashboard'
    dashboardError.value = platformStatus.value || '作业暂不可打开，请刷新待办后重试。'
  }
  } finally { if (requestedToken === token.value) homeAssignmentOpening.value = '' }
}

async function loadQuestionPage(page = 1): Promise<void> {
  const sequence = ++questionPageSequence
  const requestedToken = token.value
  const owner = user.value?.id
  const params = new URLSearchParams({ page: String(page), page_size: '10' })
  if (questionFilterCourse.value) params.set('course_id', questionFilterCourse.value)
  if (questionFilterType.value) params.set('question_type', questionFilterType.value)
  if (questionFilterKeyword.value.trim()) params.set('keyword', questionFilterKeyword.value.trim())
  const result = await request<PageResult<QuestionItem>>(`/api/v1/questions/page?${params}`)
  if (sequence !== questionPageSequence || requestedToken !== token.value || owner !== user.value?.id) return
  if (page > 1 && result.total && !result.items.length) return loadQuestionPage(Math.max(1, Math.ceil(result.total / 10)))
  questionPageItems.value = result.items
  questionPageTotal.value = result.total
  questionPageIndex.value = result.page
}

async function loadCourseAnnouncements(page = 1): Promise<void> {
  if (!selectedCourse.value) return
  const courseId = selectedCourse.value.id, requestedToken = token.value
  let result: PageResult<CourseAnnouncement>
  try { result = await request<PageResult<CourseAnnouncement>>(`/api/v1/courses/${courseId}/announcements/page?page=${page}&page_size=5`) }
  catch (cause) { if (courseId === selectedCourse.value?.id && requestedToken === token.value) announcementStatus.value = cause instanceof Error ? cause.message : '公告暂时无法读取，请重试。'; return }
  if (courseId !== selectedCourse.value?.id || requestedToken !== token.value) return
  if (page > 1 && result.total && !result.items.length) return loadCourseAnnouncements(Math.max(1, Math.ceil(result.total / 5)))
  courseAnnouncements.value = result.items
  announcementTotal.value = result.total
  announcementPageIndex.value = result.page
}

async function createAdminUser() {
  if (!newUserName.value.trim() || !newUserDisplayName.value.trim() || newUserPassword.value.length < 8) return
  if (newUserRole.value === 'admin') {
    pendingAdminConfirmation.value = {
      kind: 'create_admin', title: '确认创建管理员账号？',
      detail: `即将创建「${newUserDisplayName.value.trim()}」（${newUserName.value.trim()}）为管理员。该账号可管理用户、资料和模型设置；请核对身份后确认。`,
    }
    return
  }
  await applyCreateAdminUser(false)
}

async function applyCreateAdminUser(confirmed: boolean) {
  platformBusy.value = true
  try {
    await request<AdminUser>('/api/v1/admin/users', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ username: newUserName.value.trim(), display_name: newUserDisplayName.value.trim(), role: newUserRole.value, password: newUserPassword.value, confirmed }) })
    newUserName.value = ''; newUserDisplayName.value = ''; newUserPassword.value = ''
    platformStatus.value = '用户已经创建。'
    await loadPlatformData()
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '用户创建失败' }
  finally { platformBusy.value = false }
}

function toggleAdminUser(item: AdminUser) {
  if (platformBusy.value || item.id === user.value?.id) return
  pendingAdminConfirmation.value = {
    kind: 'user_status', userId: item.id, targetActive: !item.active,
    title: item.active ? '确认停用账号？' : '确认启用账号？',
    detail: `${item.display_name}（${item.username}）${item.active ? '停用后将无法登录平台' : '启用后将重新获得平台访问权限'}。此操作会写入审计记录。`,
  }
}

function requestAdminRoleChange(item: AdminUser) {
  const targetRole = pendingRoleChanges.value[item.id] || item.role
  if (platformBusy.value || item.id === user.value?.id || targetRole === item.role) return
  const labels = { student: '学生', teacher: '教师', admin: '管理员' }
  adminRoleReason.value = ''
  pendingAdminConfirmation.value = {
    kind: 'user_role', userId: item.id, targetRole,
    title: `确认将账号改为${labels[targetRole]}？`,
    detail: `${item.display_name}（${item.username}）当前为${labels[item.role]}。角色变更将立即改变已有登录会话的权限，并写入审计记录。请填写操作原因后再次确认。`,
  }
}

async function applyAdminUserStatus(userId: string, targetActive: boolean) {
  platformBusy.value = true
  try {
    await request<AdminUser>(`/api/v1/admin/users/${userId}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ active: targetActive, confirmed: true }) })
    platformStatus.value = targetActive ? '账号已启用，操作已记录。' : '账号已停用，操作已记录。'
    await loadPlatformData()
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '用户状态修改失败' }
  finally { platformBusy.value = false }
}

function saveModelConfig() {
  if (!adminModelConfig.value || platformBusy.value) return
  pendingAdminConfirmation.value = {
    kind: 'model_config', title: '确认应用模型与检索配置？',
    detail: `将使用 ${adminModelConfig.value.provider === 'offline' ? '离线模式' : adminModelConfig.value.model}。保存后配置立即生效，并写入审计记录。`,
  }
}

async function confirmAdminAction() {
  const pending = pendingAdminConfirmation.value
  if (!pending || platformBusy.value) return
  pendingAdminConfirmation.value = null
  if (pending.kind === 'user_status') await applyAdminUserStatus(pending.userId, pending.targetActive)
  else if (pending.kind === 'user_role') await applyAdminUserRole(pending.userId, pending.targetRole, adminRoleReason.value)
  else if (pending.kind === 'create_admin') await applyCreateAdminUser(true)
  else if (pending.kind === 'document_sharing') await applyDocumentExternalSharing(pending.documentId, pending.allowed)
  else if (pending.kind === 'model_quota') await applyModelQuota(pending.role, pending.targetLimit, adminQuotaReason.value)
  else await applyModelConfig()
}

function requestDocumentExternalSharing() {
  const document = selectedDocumentContent.value?.document
  if (user.value?.role !== 'admin' || !document || platformBusy.value) return
  documentSharingReason.value = ''
  const allowed = !document.external_model_allowed
  pendingAdminConfirmation.value = {
    kind: 'document_sharing', documentId: document.id, allowed,
    title: allowed ? '确认批准资料外发？' : '确认撤销资料外发？',
    detail: allowed
      ? `「${document.name}」的检索片段将可发送给当前外部模型服务。请先逐份核对来源、许可和模型服务的数据处理范围；本地发布不等于外发授权。`
      : `撤销后「${document.name}」仍可在本地检索，但其片段不会再作为外部模型的论据。`,
  }
}

async function applyDocumentExternalSharing(documentId: string, allowed: boolean) {
  platformBusy.value = true
  try {
    const updated = await request<DocumentRecord>(`/api/v1/admin/documents/${documentId}/external-sharing`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ allowed, reason: documentSharingReason.value.trim(), confirmed: true }),
    })
    if (selectedDocumentContent.value?.document.id === documentId) selectedDocumentContent.value.document = updated
    status.value = allowed ? '已批准外部模型使用，操作已记录。' : '已撤销外部模型使用，操作已记录。'
    documentSharingReason.value = ''
    await loadDocuments()
  } catch (error) { status.value = error instanceof Error ? error.message : '资料外发设置失败' }
  finally { platformBusy.value = false }
}

async function applyAdminUserRole(userId: string, targetRole: AdminUser['role'], reason: string) {
  platformBusy.value = true
  try {
    await request<AdminUser>(`/api/v1/admin/users/${userId}/role`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ role: targetRole, reason: reason.trim(), confirmed: true }),
    })
    delete pendingRoleChanges.value[userId]
    adminRoleReason.value = ''
    platformStatus.value = '用户角色已更新，权限立即生效，操作已记录。'
    await loadPlatformData()
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '用户角色修改失败' }
  finally { platformBusy.value = false }
}

function auditActionLabel(action: string) {
  return ({ self_register: '自主注册', create_invite: '创建邀请', revoke_invite: '撤销邀请', registration_policy: '调整注册范围', join_course: '邀请加入课程', update_profile: '修改个人资料', change_password: '修改密码', reset_password: '重置密码', issue_password_reset: '核实并生成重置链接', teacher_application: '申请教师身份', review_applications: '审核教师申请', review_joins: '审核选课', review_recoveries: '处理找回申请', create: '新增', update: '修改', deactivate: '停用', activate: '启用', change_role: '改角色',
    delete: '删除', update_quota: '改额度', generate_assignment_review_draft: '生成讲评草稿',
    publish_assignment_review: '发布讲评', revise_assignment_review: '创建讲评修订稿', update_question: '修改题目', delete_question: '删除题目',
    publish_course_announcement: '发布公告', update_course_announcement: '修改公告',
    delete_course_announcement: '删除公告', publish_assignment: '发布作业', update_assignment_status: '更新作业状态',
    enroll_course_member: '加入课程', update_course_member: '调整课程成员', create_draft: '新建教学草稿',
    generate_draft: '生成教学草稿', update_draft: '修改教学草稿', confirm_draft: '确认教学草稿',
    ai_review_question: 'AI 复核题目', analyze_student_answers: 'AI 分析学生作答', analyze_course_cohort: 'AI 综合学情分析',
    generate_practice_feedback: 'AI 练习复盘', create_study_plan: '创建学习安排', refresh_study_plan: '更新学习安排', create_assignment_from_draft: '从题目草稿准备作业',
    prepare_admin_action: '准备管理操作预览', resolve_admin_action: '管理操作处理结果',
    publish_questions: '题目入库', approve_external_share: '批准资料外发',
    revoke_external_share: '撤销外发许可', grade: '批改作业', approved: '批准补交', rejected: '拒绝补交',
    review: '审核回答', retry: '重试导入' } as Record<string, string>)[action] || action
}

function openAdminTaskCenter(target = 'jobs') {
  if (user.value?.role !== 'admin') return
  if (!['jobs', 'quotas', 'calls', 'calls:1', 'calls:7', 'calls:30', 'accounts', 'accounts:inactive', 'model', 'history', 'quota:student', 'quota:teacher', 'quota:admin'].includes(target) && !/^user:[0-9a-f-]{36}$/i.test(target)) {
    assistantActionError.value = '此管理任务入口已失效，请重新查询。'
    return
  }
  adminTaskFocus.value = target
  adminTaskFocusRevision.value += 1
  adminTab.value = 'tasks'
  activePage.value = 'admin'
  globalAssistantOpen.value = false
}

async function refreshAdminTaskSummary() {
  const requestedToken = token.value
  try {
    const [insights, quotas, config] = await Promise.all([
      request<AssistantAction[]>('/api/v1/admin/assistant-insights'),
      request<ModelQuota[]>('/api/v1/admin/model-quotas'),
      request<ModelConfig>('/api/v1/admin/model-config'),
    ])
    if (user.value?.role !== 'admin' || requestedToken !== token.value) return
    adminInsights.value = insights
    modelQuotas.value = quotas
    adminModelConfig.value = config
  } catch { /* The task center retains the authoritative execution receipt. */ }
}

function auditResourceLabel(resource: string) {
  return ({ account_lifecycle: '注册与账号', user: '账号', course: '课程', question: '题目', question_bank_item: '题目',
    course_announcement: '课程公告', assignment: '作业', assignment_submission: '作业提交',
    late_submission_request: '补交申请', document: '资料', knowledge_base: '知识库',
    teaching_draft: '教学草稿', study_plan: '学习安排', question_answer: '问答', document_ingestion: '资料导入',
    model_config: '模型设置', model_quota: '模型额度', submission: '作业提交', practice_attempt: '练习记录', admin_assistant_operation: '管理助手操作' } as Record<string, string>)[resource] || resource
}

async function applyModelConfig() {
  if (!adminModelConfig.value) return
  platformBusy.value = true
  try {
    adminModelConfig.value = await request<ModelConfig>('/api/v1/admin/model-config', {
      method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
        provider: adminModelConfig.value.provider, model: adminModelConfig.value.model,
        api_base: adminModelConfig.value.api_base, api_key: modelApiKey.value.trim() || null,
        timeout_seconds: adminModelConfig.value.timeout_seconds, fallback_offline: adminModelConfig.value.fallback_offline,
        retrieval_top_k: adminModelConfig.value.retrieval_top_k, retrieval_min_score: adminModelConfig.value.retrieval_min_score,
        retrieval_vector_weight: adminModelConfig.value.retrieval_vector_weight, confirmed: true,
      }),
    })
    modelApiKey.value = ''; modelConfigBaseline.value = JSON.parse(JSON.stringify(adminModelConfig.value)); platformStatus.value = '模型与检索配置已保存并生效，服务重启后仍会保留。'
    await loadSystemStatus()
    auditLogs.value = await request<AuditLog[]>('/api/v1/admin/audit-logs?limit=50')
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '配置保存失败' }
  finally { platformBusy.value = false }
}

function saveModelQuota(item: ModelQuota) {
  const targetLimit = modelQuotaDrafts.value[item.role]
  if (!Number.isInteger(targetLimit) || targetLimit < 1 || targetLimit > 100000) {
    platformStatus.value = '每日额度必须是 1 到 100000 的整数。'
    return
  }
  if (targetLimit === item.daily_limit) {
    platformStatus.value = '每日额度未变化。'
    return
  }
  const label = { student: '学生', teacher: '教师', admin: '管理员' }[item.role]
  adminQuotaReason.value = ''
  pendingAdminConfirmation.value = {
    kind: 'model_quota', role: item.role, targetLimit, title: `确认修改${label}模型额度？`,
    detail: `每位${label}每天的在线模型调用额度将从 ${item.daily_limit} 次改为 ${targetLimit} 次。此变更立即影响该角色账号，并写入审计；请填写原因后确认。`,
  }
}

async function applyModelQuota(role: ModelQuota['role'], dailyLimit: number, reason: string) {
  platformBusy.value = true
  try {
    const updated = await request<ModelQuota>(`/api/v1/admin/model-quotas/${role}`, {
      method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ daily_limit: dailyLimit, reason: reason.trim(), confirmed: true }),
    })
    modelQuotas.value = modelQuotas.value.map(value => value.role === updated.role ? updated : value)
    modelQuotaDrafts.value[updated.role] = updated.daily_limit
    adminQuotaReason.value = ''
    platformStatus.value = '每日 AI 调用额度已保存并立即生效，操作已记录。'
    try { auditLogs.value = await request<AuditLog[]>('/api/v1/admin/audit-logs?limit=50') }
    catch { platformStatus.value = '额度已保存并生效，审计列表暂未刷新；可稍后重新打开页面查看。' }
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '额度保存失败' }
  finally { platformBusy.value = false }
}

async function openCourseDetail(course: CourseRecord) {
  if (!saveAnswerDraftsBeforeExit(() => { void openCourseDetail(course) }, '打开课程')) return false
  assignmentDraft.release(); practiceDraft.release()
  selectedAssignment.value = null; selectedPractice.value = null
  homeAssignmentReturn = null
  const requestId = ++courseDetailRequestId
  const requestedToken = token.value
  const owner = user.value?.id
  courseDetailController?.abort()
  const controller = new AbortController()
  courseDetailController = controller
  const current = () => requestId === courseDetailRequestId && requestedToken === token.value && owner === user.value?.id && selectedCourse.value?.id === course.id && !controller.signal.aborted
  const read = <T,>(path: string) => request<T>(path, { signal: controller.signal })
  selectedCourse.value = course
  selectedCoursePoint.value = null
  platformStatus.value = ''
  courseDetailTab.value = 'overview'
  courseDetailLoading.value = true
  courseDetailError.value = ''
  selectedOutlineSection.value = null
  courseMaterials.value = []; courseKnowledgeBases.value = []; courseKnowledgePoints.value = []; courseSessions.value = []; courseMembers.value = []
  newSessionTitle.value = ''; newSessionDate.value = ''; newSessionSectionId.value = ''; newCourseMemberUsername.value = ''
  courseAnnouncements.value = []
  announcementPageIndex.value = 1
  announcementTotal.value = 0
  editingAnnouncementId.value = ''
  newAnnouncementTitle.value = ''
  newAnnouncementContent.value = ''
  announcementStatus.value = ''
  try {
    const [detail, bases, points, sessions, announcements, members] = await Promise.all([
      read<CourseRecord>(`/api/v1/courses/${course.id}`),
      read<LinkedKnowledgeBase[]>(`/api/v1/courses/${course.id}/knowledge-bases`),
      read<KnowledgePointRecord[]>(`/api/v1/courses/${course.id}/knowledge-points`),
      read<CourseSessionRecord[]>(`/api/v1/courses/${course.id}/sessions`),
      read<PageResult<CourseAnnouncement>>(`/api/v1/courses/${course.id}/announcements/page?page=1&page_size=5`),
      canManage.value ? read<ClassMember[]>(`/api/v1/courses/${course.id}/members`) : Promise.resolve([] as ClassMember[]),
    ])
    const materials = (await Promise.all(bases.map(base => read<DocumentRecord[]>(`/api/v1/knowledge-bases/${base.id}/documents`)))).flat().filter(item => item.publication_status === 'published')
    if (!current()) return false
    courseKnowledgeBases.value = bases
    if (user.value?.role === 'student') studentCourseKnowledgeBases.value[course.id] = bases
    courseKnowledgePoints.value = points
    courseSessions.value = sessions
    if (user.value?.role === 'student') studentCourseSessions.value = [
      ...studentCourseSessions.value.filter((item) => item.course_id !== course.id), ...sessions,
    ]
    courseAnnouncements.value = announcements.items
    announcementTotal.value = announcements.total
    courseMembers.value = members
    newSessionLocation.value = detail.location || ''
    courseMaterials.value = [...new Map(materials.map(item => [item.id, item])).values()]
    selectedCourse.value = detail
    assistantDraftCourseId.value = course.id
    return true
  } catch (error) { if (current()) courseDetailError.value = error instanceof Error ? error.message : '课程内容加载失败，请重试。'; return false }
  finally { if (current()) { courseDetailLoading.value = false; courseDetailController = null } }
}

async function addCourseMember() {
  if (!selectedCourse.value || !newCourseMemberUsername.value.trim() || platformBusy.value) return
  platformBusy.value = true
  try {
    await request(`/api/v1/courses/${selectedCourse.value.id}/members`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: newCourseMemberUsername.value.trim() }),
    })
    newCourseMemberUsername.value = ''
    courseMembers.value = await request<ClassMember[]>(`/api/v1/courses/${selectedCourse.value.id}/members`)
    platformStatus.value = '学生已加入课程。'
    await loadPlatformData()
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '加入课程失败' }
  finally { platformBusy.value = false }
}

async function setCourseMemberStatus(member: ClassMember, status: 'active' | 'removed') {
  if (!selectedCourse.value || platformBusy.value) return
  if (status === 'removed' && !window.confirm(`确认将 ${member.display_name} 移出本课程？该学生将无法再访问课程作业和题库。`)) return
  platformBusy.value = true
  try {
    const updated = await request<ClassMember>(`/api/v1/courses/${selectedCourse.value.id}/members/${member.user_id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
    })
    courseMembers.value = courseMembers.value.map(item => item.user_id === updated.user_id ? updated : item)
    platformStatus.value = status === 'removed' ? '学生已移出课程。' : '学生已恢复课程访问。'
    await loadPlatformData()
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '更新课程成员失败' }
  finally { platformBusy.value = false }
}

async function createCourseSessionItem() {
  if (!selectedCourse.value || !newSessionTitle.value.trim() || !newSessionDate.value || platformBusy.value) return
  const courseId = selectedCourse.value.id, requestedToken = token.value
  platformBusy.value = true
  try {
  await request(`/api/v1/courses/${selectedCourse.value.id}/sessions`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title: newSessionTitle.value.trim(), session_date: newSessionDate.value, duration_minutes: 90,
      location: newSessionLocation.value.trim() || null, section_id: newSessionSectionId.value || null }),
  })
  if (requestedToken !== token.value || selectedCourse.value?.id !== courseId) return
  newSessionTitle.value = ''; newSessionDate.value = ''; newSessionSectionId.value = ''
  const sessions = await request<CourseSessionRecord[]>(`/api/v1/courses/${courseId}/sessions`)
  if (requestedToken === token.value && selectedCourse.value?.id === courseId) { courseSessions.value = sessions; platformStatus.value = '课次已添加。' }
  } catch (cause) { if (requestedToken === token.value) platformStatus.value = cause instanceof Error ? cause.message : '未能确认添加结果，请先重新打开课程核对，避免重复添加。' }
  finally { if (requestedToken === token.value) platformBusy.value = false }
}

async function toggleCourseSession(item: CourseSessionRecord) {
  if (platformBusy.value) return
  const requestedToken = token.value
  platformBusy.value = true
  try {
  const updated = await request<CourseSessionRecord>(`/api/v1/course-sessions/${item.id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ completed: !item.completed }),
  })
  if (requestedToken !== token.value) return
  courseSessions.value = courseSessions.value.map(value => value.id === updated.id ? updated : value)
  platformStatus.value = updated.completed ? '已标记本课次完成。' : '已撤销本课次完成标记。'
  } catch (cause) { if (requestedToken === token.value) platformStatus.value = cause instanceof Error ? cause.message : '未能确认修改结果，请重新打开课程核对。' }
  finally { if (requestedToken === token.value) platformBusy.value = false }
}

async function saveAssistantAsTeachingDraft(turn: AssistantTurn) {
  if (!turn.answer || user.value?.role !== 'teacher') return
  const course = platformCourses.value.find((item) => item.id === turn.courseId)
  if (!course) { platformStatus.value = '请先在 AI 教学助理中选择课程。'; return }
  platformBusy.value = true
  try {
    const draft = await request<TeachingDraft>('/api/v1/teaching-drafts', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      course_id: course.id, draft_type: 'teaching_plan', title: `${course.title} · AI 教学草稿`, content: turn.answer.answer,
      source_context: { origin: 'global_assistant', conversation_id: turn.answer.conversation_id, page: activePage.value },
    }) })
    teachingDrafts.value = [draft, ...teachingDrafts.value]
    selectedTeachingDraft.value = draft
    draftQualityReport.value = null
    draftAIReviewConsent.value = false
    activePage.value = 'courses'; globalAssistantOpen.value = false
    platformStatus.value = 'AI 内容已保存到教学草稿箱，确认前不会发布。'
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '草稿保存失败' }
  finally { platformBusy.value = false }
}

async function updateTeachingDraft(status?: TeachingDraft['status']) {
  if (!selectedTeachingDraft.value || platformBusy.value) return
  const requestedToken = token.value, id = selectedTeachingDraft.value.id
  const payload = { ...teachingEditOf(selectedTeachingDraft.value), ...(status ? { status } : {}) }
  teachingEditorDraft.persist()
  teachingDraftFeedback.value = { message: '', error: false }
  platformBusy.value = true
  try {
    const updated = await request<TeachingDraft>(`/api/v1/teaching-drafts/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
    if (requestedToken !== token.value || selectedTeachingDraft.value?.id !== id) return
    teachingDrafts.value = teachingDrafts.value.map(item => item.id === updated.id ? updated : item)
    teachingEditorDraft.clear()
    applyingTeachingDraft = true; selectedTeachingDraft.value = updated; applyingTeachingDraft = false
    teachingEditorDraft.open(user.value!.id, 'teaching', updated.id, teachingEditOf(updated))
    draftQualityReport.value = null
    const privateAnalysis = ['student_analysis', 'course_analysis'].includes(updated.draft_type)
    platformStatus.value = status === 'confirmed' ? (privateAnalysis ? '分析已确认并保留在教师侧，未发布给学生。' : '草稿已经教师确认，但尚未发布。')
      : status === 'archived' ? '草稿已归档。' : privateAnalysis ? '分析修改已保存，未修改成绩或发布给学生。'
      : updated.status === 'draft' && updated.draft_type === 'review' ? '修改已保存，请重新确认后发布讲评。'
      : updated.status === 'draft' && updated.draft_type === 'question_set' ? '修改已保存，请重新确认后入库。' : '草稿修改已保存。'
    teachingDraftFeedback.value = { message: platformStatus.value, error: false }
  } catch (error) {
    if (requestedToken !== token.value || selectedTeachingDraft.value?.id !== id) return
    platformStatus.value = error instanceof Error ? error.message : '草稿更新失败'
    teachingDraftFeedback.value = { message: platformStatus.value, error: true }
  }
  finally { if (requestedToken === token.value) platformBusy.value = false }
}

function openTeachingDraft(draft: TeachingDraft) {
  if (!guardGradingExit(() => openTeachingDraft(draft), '打开教学草稿')) return
  if (!guardFormExit(() => openTeachingDraft(draft), '打开教学草稿', ['draft'])) return
  teachingEditorDraft.persist()
  if (canManage.value) assistantDraftCourseId.value = draft.course_id
  if (!teachingDrafts.value.some(item => item.id === draft.id)) teachingDrafts.value = [...teachingDrafts.value, JSON.parse(JSON.stringify(draft))]
  teachingEditorDraft.open(user.value!.id, 'teaching', draft.id, teachingEditOf(draft))
  teachingEditingId = draft.id
  const local = teachingEditorDraft.value.value
  const valid = local && typeof local.title === 'string' && typeof local.content === 'string' && Array.isArray(local.questions) && local.questions.every(item => item && Array.isArray(item.options))
  applyingTeachingDraft = true
  selectedTeachingDraft.value = JSON.parse(JSON.stringify(draft))
  if (valid && draft.status !== 'published') Object.assign(selectedTeachingDraft.value!, JSON.parse(JSON.stringify(local)))
  applyingTeachingDraft = false
  draftView.value = draft.status === 'published' ? 'preview' : 'edit'
  teachingDraftFeedback.value = { message: '', error: false }
  draftQualityReport.value = null
  draftAIReviewConsent.value = false
}

function teachingDraftTypeLabel(type: string): string {
  return ({ teaching_plan: '教学计划', lesson_plan: '单次课教案', question_set: '题目草稿',
    review: '作业讲评', student_analysis: '学生作答分析', course_analysis: '课程综合学情' } as Record<string, string>)[type] || type
}

function teachingDraftEvidence(draft: TeachingDraft): DraftEvidence[] {
  return Array.isArray(draft.source_context.evidence) ? draft.source_context.evidence as DraftEvidence[] : []
}

function teachingDraftHasUnsavedChanges(draft: TeachingDraft): boolean {
  const saved = teachingDrafts.value.find(item => item.id === draft.id)
  return !saved || JSON.stringify([draft.title, draft.content, draft.questions]) !== JSON.stringify([saved.title, saved.content, saved.questions])
}

function addDraftQuestion() {
  selectedTeachingDraft.value?.questions.push({ question_type: 'single_choice', stem: '请输入题干', options: ['A. 选项一', 'B. 选项二'], correct_answer: 'A', explanation: '', difficulty: 2, knowledge_point: '' })
}

function draftQualityIsCurrent(draft: TeachingDraft): boolean {
  return draftQualityReport.value?.draft_id === draft.id && draftQualityFingerprint.value === JSON.stringify(draft.questions)
}

async function checkDraftQuestions(): Promise<void> {
  const draft = selectedTeachingDraft.value
  if (!draft || draft.draft_type !== 'question_set' || draftQualityBusy.value) return
  if (teachingDraftHasUnsavedChanges(draft)) {
    platformStatus.value = '请先保存题目修改，再运行质量检查。'
    return
  }
  draftQualityBusy.value = true
  try {
    const report = await request<DraftQualityReport>(`/api/v1/teaching-drafts/${draft.id}/quality-check`)
    draftQualityReport.value = report
    draftQualityFingerprint.value = JSON.stringify(draft.questions)
    platformStatus.value = report.error_count
      ? `发现 ${report.error_count} 项需要修正的问题；修正后请保存并重新检查。`
      : report.warning_count ? `未发现确定性错误；有 ${report.warning_count} 项提示需要教师核对。` : '未发现确定性格式或重复问题；仍需教师核对知识内容。'
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '题目检查失败' }
  finally { draftQualityBusy.value = false }
}

function adoptReviewedChange(change: ReviewedChange): void {
  const draft = selectedTeachingDraft.value
  const question = draft?.questions[change.index - 1]
  if (!draft || draft.id !== change.draftId || !question || draft.status === 'published' ||
      teachingDraftHasUnsavedChanges(draft) || questionKey(question) !== questionKey(change.original)) {
    platformStatus.value = '题目已变化，未套用旧建议。请保存并重新核对。'
    return
  }
  question[change.field] = change.value
  platformStatus.value = '建议已填入当前草稿，尚未保存、确认或入库；请核对完整题意、选项、答案及解析。'
}

async function publishDraftQuestions() {
  const draft = selectedTeachingDraft.value
  if (!draft || draft.status !== 'confirmed' || platformBusy.value) return
  if (teachingDraftHasUnsavedChanges(draft)) {
    platformStatus.value = '题目有未保存的修改。请先保存并重新确认，再写入题库。'
    return
  }
  if (!draftQualityIsCurrent(draft)) {
    platformStatus.value = '请先运行题目质量检查，再决定是否入库。'
    return
  }
  if (draftQualityReport.value?.error_count) {
    platformStatus.value = '请先修正质量检查中标记的确定性错误。'
    return
  }
  platformBusy.value = true
  try {
    const published = await request<TeachingDraft>(`/api/v1/teaching-drafts/${draft.id}/publish-questions`, { method: 'POST' })
    teachingDrafts.value = teachingDrafts.value.map(item => item.id === published.id ? published : item)
    selectedTeachingDraft.value = published
    draftQualityReport.value = null
    questionBank.value = await request<QuestionItem[]>('/api/v1/questions')
    platformStatus.value = `已将 ${published.questions.length} 道审核题目写入题库。`
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '题目入库失败' }
  finally { platformBusy.value = false }
}

async function publishAssignmentReview() {
  const draft = selectedTeachingDraft.value
  if (!draft || draft.draft_type !== 'review' || draft.status !== 'confirmed' || platformBusy.value) return
  if (teachingDraftHasUnsavedChanges(draft)) {
    platformStatus.value = '请先保存并重新确认讲评修改，再发布给学生。'
    teachingDraftFeedback.value = { message: platformStatus.value, error: true }
    return
  }
  teachingDraftFeedback.value = { message: '', error: false }
  platformBusy.value = true
  try {
    const published = await request<TeachingDraft>(`/api/v1/teaching-drafts/${draft.id}/publish-review`, { method: 'POST' })
    teachingDrafts.value = teachingDrafts.value.map(item => item.id === published.id ? published : item)
    selectedTeachingDraft.value = published
    platformStatus.value = '作业讲评已发布，仅已提交该作业的课程学生可以查看。'
    teachingDraftFeedback.value = { message: platformStatus.value, error: false }
  } catch (error) {
    platformStatus.value = error instanceof Error ? error.message : '作业讲评发布失败'
    teachingDraftFeedback.value = { message: platformStatus.value, error: true }
  }
  finally { platformBusy.value = false }
}

async function generateAssignmentReview(localOnly = false) {
  const assignment = selectedAssignment.value
  if (!assignment || user.value?.role === 'student' || assignmentReviewBusy.value) return
  if (!assignmentSubmissions.value.length) { assignmentReviewMessage.value = '还没有学生提交，暂时无法生成讲评。'; return }
  const requestedToken = token.value
  assignmentReviewBusy.value = true
  assignmentReviewMessage.value = ''
  try {
    if (!localOnly) {
      await request('/api/v1/assistant/tasks', { method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({request_id:crypto.randomUUID(),kind:'assignment_review',payload:{course_id:assignment.course_id,target_id:assignment.id,confirm_external_analysis:true,include_student_answers:true}}) })
      if (requestedToken===token.value && assignment.id===selectedAssignment.value?.id) { assistantTasksRevision.value++; assignmentReviewMessage.value='已加入教学任务，可离开页面；完成后在下方查看草稿。' }
      return
    }
    const draft = await request<TeachingDraft>(`/api/v1/assignments/${assignment.id}/review-drafts`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ local_only: localOnly, confirm_external_analysis: !localOnly, include_student_answers: !localOnly }),
    })
    if (requestedToken !== token.value || assignment.id !== selectedAssignment.value?.id) return
    teachingDrafts.value = [draft, ...teachingDrafts.value]
    openAssignmentTeachingDraft(draft)
    platformStatus.value = draft.source_context.model === 'local-statistics'
      ? '已用站内匿名统计生成提纲，未调用在线模型。请补充教学分析并核对后，再确认发布。'
      : 'AI 讲评已生成草稿。请核对统计和教学建议，保存、确认后才能发布给已提交的学生。'
    teachingDraftFeedback.value = { message: platformStatus.value, error: false }
  } catch (error) { if (requestedToken === token.value && assignment.id === selectedAssignment.value?.id) assignmentReviewMessage.value = error instanceof Error ? error.message : '讲评草稿生成失败' }
  finally { if (requestedToken === token.value) assignmentReviewBusy.value = false }
}

async function reviseAssignmentReview(id: string) {
  if (user.value?.role === 'student' || platformBusy.value) return
  const requestedToken = token.value
  const assignmentId = selectedAssignment.value?.id
  const draftId = selectedTeachingDraft.value?.id
  platformBusy.value = true
  const current = () => requestedToken === token.value && (!assignmentId || selectedAssignment.value?.id === assignmentId) && (!draftId || selectedTeachingDraft.value?.id === draftId)
  try {
    const draft = await request<TeachingDraft>(`/api/v1/teaching-drafts/${id}/review-revision`, { method: 'POST' })
    if (!current()) return
    teachingDrafts.value = [draft, ...teachingDrafts.value.filter(item => item.id !== draft.id)]
    openAssignmentTeachingDraft(draft)
    platformStatus.value = '已打开可编辑修订稿，未调用模型。当前学生讲评保持原版，重新确认发布后才替换。'
    teachingDraftFeedback.value = { message: platformStatus.value, error: false }
  } catch (cause) {
    if (current()) {
      const message = cause instanceof Error ? cause.message : '修订稿暂未打开，请重试。'
      assignmentReviewMessage.value = message
      teachingDraftFeedback.value = { message, error: true }
    }
  } finally { if (requestedToken === token.value) platformBusy.value = false }
}

async function refreshWorkflowAssignments() {
  const requestedToken = token.value
  try {
    const rows = await request<AssignmentRecord[]>('/api/v1/assignments')
    if (requestedToken === token.value && user.value?.role !== 'student') assignments.value = rows
  } catch { /* The workflow retains its authoritative receipt and reload controls. */ }
}

async function openWorkflowAssignment(id: string) {
  if (!saveAnswerDraftsBeforeExit(() => { void openWorkflowAssignment(id) }, '打开关联作业')) return
  const requestedToken = token.value
  selectedTeachingDraft.value = null
  learningTab.value = 'assignments'
  activePage.value = 'assessments'
  await nextTick()
  const opened = await openAssignment({ id })
  if (requestedToken !== token.value) return
  if (!opened) { teachingDraftFeedback.value = { message: platformStatus.value, error: true }; return }
}

async function openAssignmentSourceDraft() {
  const sourceId = selectedAssignment.value?.source_draft_id
  if (!sourceId || user.value?.role === 'student') return
  const requestedToken = token.value
  try {
    const draft = await request<TeachingDraft>(`/api/v1/teaching-drafts/${sourceId}`)
    if (requestedToken !== token.value || sourceId !== selectedAssignment.value?.source_draft_id) return
    openAssignmentTeachingDraft(draft)
  } catch (cause) { if (requestedToken === token.value) platformStatus.value = cause instanceof Error ? cause.message : '原草稿暂不可访问。' }
}

function openAssignmentTeachingDraft(draft: TeachingDraft) {
  if (!guardGradingExit(() => openAssignmentTeachingDraft(draft), '打开教学草稿')) return
  selectedAssignment.value = null
  activePage.value = 'courses'
  openTeachingDraft(draft)
}

async function generateTeachingDraft() {
  if (!draftGenerateCourseId.value || platformBusy.value) return
  const created = await createTeachingDraft(draftGenerateCourseId.value, draftGenerateType.value, draftGenerateTopic.value, draftShareCourseMaterials.value)
  if (created) { draftGenerateTopic.value = ''; draftShareCourseMaterials.value = false }
}

async function generateAssistantTeachingDraft(type: 'teaching_plan' | 'lesson_plan' | 'question_set', localOnly = false) {
  if (!assistantDraftCourseId.value) { platformStatus.value = '请先在 AI 教学助理中选择课程。'; return }
  if (assistantDraftBusy.value) return
  if (!localOnly && teacherFocusTopic.value && !teacherAnalysisConsent.value && modelStatus.value?.llm_provider !== 'offline') {
    assistantActionError.value = '请先同意发送匿名学情汇总，再生成针对性草稿。'
    return
  }
  const courseId = assistantDraftCourseId.value
  const requestedToken = token.value
  assistantDraftBusy.value = true
  try {
    const created = await createTeachingDraft(courseId, type, assistantDraftTopic.value, assistantShareCourseMaterials.value, {
      focus: teacherFocusTopic.value || null, confirmAnalysis: teacherAnalysisConsent.value, assistantContext: true, localOnly,
    })
    if (requestedToken !== token.value || courseId !== assistantDraftCourseId.value) return
    if (created) {
      clearTeacherFocus()
      assistantDraftTopic.value = ''
      assistantShareCourseMaterials.value = false
      activePage.value = 'courses'
      globalAssistantOpen.value = false
    } else assistantActionError.value = platformStatus.value
  } finally { if (requestedToken === token.value) assistantDraftBusy.value = false }
}

async function createTeachingDraft(courseId: string, type: 'teaching_plan' | 'lesson_plan' | 'question_set', topic: string, shareCourseMaterials: boolean,
  options: { focus?: string | null; confirmAnalysis?: boolean; assistantContext?: boolean; localOnly?: boolean } = {}): Promise<boolean> {
  if (platformBusy.value) return false
  platformBusy.value = true
  const requestedToken = token.value
  const requestedUserId = user.value?.id
  try {
    await request('/api/v1/assistant/tasks', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ request_id: crypto.randomUUID(), payload: { course_id: courseId, draft_type: type, topic: topic.trim() || null, question_count: 5, share_course_materials: shareCourseMaterials, include_course_insights: Boolean(options.focus), focus_knowledge_point: options.focus || null, confirm_external_analysis: options.confirmAnalysis || false, local_only: options.localOnly || false } }) })
    if (requestedToken !== token.value || requestedUserId !== user.value?.id || (options.assistantContext && courseId !== assistantDraftCourseId.value)) return false
    assistantTasksRevision.value++
    platformStatus.value = '任务已保存，可离开页面；请在“我的备课任务”查看结果。生成内容仍需教师审核。'
    return true
  } catch (error) {
    if (requestedToken === token.value && requestedUserId === user.value?.id) platformStatus.value = error instanceof Error ? error.message : 'AI 草稿生成失败'
    return false
  }
  finally { if (requestedToken === token.value) platformBusy.value = false }
}

async function completeSection(report: LearningReport, sectionId: string) {
  await request('/api/v1/learning/progress', {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ course_id: report.course_id, section_id: sectionId, progress_percent: 100 }),
  })
  await loadPlatformData()
  selectedLearningSection.value = null
}

function resetQuestionEditor() {
  questionEditorBaseline.value = ''
  editingQuestionId.value = ''
  newQuestionStem.value = ''
  newQuestionOptions.value = ''
  newQuestionAnswer.value = ''
  newQuestionPoint.value = ''
  newQuestionExplanation.value = ''
  newQuestionDifficulty.value = 2
}

function editQuestionItem(item: QuestionItem) {
  if (!guardFormExit(() => editQuestionItem(item), '编辑另一道题', ['question-editor'], true)) return
  editingQuestionId.value = item.id
  newQuestionCourseId.value = item.course_id
  newQuestionType.value = item.question_type as typeof newQuestionType.value
  newQuestionStem.value = item.stem
  newQuestionOptions.value = item.options.join('，')
  newQuestionAnswer.value = item.correct_answer || ''
  newQuestionPoint.value = item.knowledge_point || ''
  newQuestionExplanation.value = item.explanation || ''
  newQuestionDifficulty.value = item.difficulty
  questionEditorBaseline.value = questionEditorValue()
  questionPreview.value=null;questionEditorOpen.value=true
  platformStatus.value = '正在编辑题目；已用于作业或练习的题目不可修改。'
}

async function createQuestionItem() {
  if (platformBusy.value || !newQuestionCourseId.value || !newQuestionStem.value.trim() || !newQuestionAnswer.value.trim()) return
  platformBusy.value = true
  try {
    await request<QuestionItem>(editingQuestionId.value ? `/api/v1/questions/${editingQuestionId.value}` : '/api/v1/questions', {
      method: editingQuestionId.value ? 'PATCH' : 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        ...(!editingQuestionId.value ? { course_id: newQuestionCourseId.value } : {}), question_type: newQuestionType.value,
        stem: newQuestionStem.value.trim(), options: ['single_choice', 'multiple_choice', 'true_false'].includes(newQuestionType.value) ? newQuestionOptions.value.split(/[,，]/).map(value => value.trim()).filter(Boolean) : [],
        correct_answer: newQuestionAnswer.value.trim(), difficulty: newQuestionDifficulty.value,
        knowledge_point: newQuestionPoint.value.trim() || null, explanation: newQuestionExplanation.value.trim() || null,
      }),
    })
    platformStatus.value = editingQuestionId.value ? '题目已更新。' : '题目已加入课程题库。'
    resetQuestionEditor()
    questionEditorOpen.value=false
    await loadPlatformData()
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '题目创建失败' }
  finally { platformBusy.value = false }
}

async function deleteQuestionItem(item: QuestionItem,confirmed=false) {
  if (platformBusy.value) return
  if(!confirmed){pendingQuestionDelete.value=item;return}
  platformBusy.value = true
  try {
    await request(`/api/v1/questions/${item.id}`, { method: 'DELETE' })
    if (editingQuestionId.value === item.id) resetQuestionEditor()
    await loadPlatformData()
    platformStatus.value = '题目已删除。'
    questionPreview.value=null;pendingQuestionDelete.value=null
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '题目删除失败' }
  finally { platformBusy.value = false }
}

async function createLearningAssignment() {
  if (!newAssignmentCourseId.value || !newAssignmentTitle.value.trim() || !selectedQuestionIds.value.length) return
  platformBusy.value = true
  try {
    await request<AssignmentRecord>('/api/v1/assignments', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ course_id: newAssignmentCourseId.value, title: newAssignmentTitle.value.trim(), question_ids: selectedQuestionIds.value, due_at: newAssignmentDueAt.value ? new Date(newAssignmentDueAt.value).toISOString() : null, status: 'draft' }),
    })
    newAssignmentTitle.value = ''; selectedQuestionIds.value = []; newAssignmentDueAt.value = ''
    assignmentCreateOpen.value=false
    platformStatus.value = '作业草稿已保存。请打开作业核对题目，再发布给课程学生。'
    await loadPlatformData()
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '作业发布失败' }
  finally { platformBusy.value = false }
}

async function assignmentEditorSaved(id: string) {
  await openAssignment({ id })
  await loadPlatformData()
}

function askAssignmentAssistant(questionId: string) {
  const item = selectedAssignment.value
  if (!item || item.ai_policy === 'disabled' || globalAssistantBusy.value || !closeAnswerDialog('assignment')) return
  resetAssistantConversation()
  assistantDraftCourseId.value = item.course_id
  assistantAssignmentContext.value = { id: item.id, questionId, title: item.title, courseId: item.course_id, policy: item.ai_policy || 'hints' }
  globalAssistantOpen.value = true
  void askGlobalAssistant(item.ai_policy === 'guided' ? '请分步引导我理解这道题。' : '请给我这道题的概念与思路提示，不要直接代答。')
}

async function openAssignment(item: Pick<AssignmentRecord, 'id'> & {ungraded_count?:number}) {
  if (!saveAnswerDraftsBeforeExit(() => { void openAssignment(item) }, '打开另一份作业')) return false
  assignmentDraft.release()
  draftCloseWarning.value = null
  const requestedToken = token.value
  const requestId = ++assignmentOpenRequestId
  const current = () => requestedToken === token.value && requestId === assignmentOpenRequestId
  assignmentOpenPending.value += 1
  try {
    selectedSubmission.value = null
    assignmentSubmissions.value = []
    assignmentSubmissionsError.value = ''
    assignmentManagerPane.value = 'grading'
    selectedAssignment.value = null
    assignmentPublishedReview.value = null
    assignmentReviewMessage.value = ''
    const loaded = await request<AssignmentRecord>(`/api/v1/assignments/${item.id}`)
    if (!current()) return false
    selectedAssignment.value = loaded
    if(user.value?.role!=='student')assignmentManagerPane.value=loaded.status==='draft'?'questions':item.ungraded_count?'grading':'overview'
    assignments.value = assignments.value.map(existing => existing.id === item.id ? { ...existing, ...selectedAssignment.value! } : existing)
    assistantDraftCourseId.value = selectedAssignment.value.course_id
    assignmentDraft.open(user.value?.role === 'student' && !loaded.submitted
      ? { owner: user.value.id, kind: 'assignment', id: loaded.id, questions: loaded.questions ?? [] } : null,
      loaded.submitted_answers ?? {})
    submissionMessage.value = ''
    lateRequestReason.value = ''
    selectedSubmission.value = null
    if (user.value?.role !== 'student') await reloadAssignmentSubmissions()
    if (!current() || selectedAssignment.value?.id !== item.id) return false
    await loadPublishedAssignmentReview(item.id)
    return current() && selectedAssignment.value?.id === item.id
  } catch (error) { if (current()) platformStatus.value = error instanceof Error ? error.message : '作业加载失败'; return false }
  finally { assignmentOpenPending.value = Math.max(0, assignmentOpenPending.value - 1) }
}

async function reloadAssignmentSubmissions() {
  const assignmentId = selectedAssignment.value?.id
  const requestedToken = token.value
  if (!assignmentId || user.value?.role === 'student' || gradingSaving.value) return
  const sequence = ++assignmentSubmissionsRequestId
  assignmentSubmissionsLoading.value = true
  assignmentSubmissionsError.value = ''
  const current = () => sequence === assignmentSubmissionsRequestId && requestedToken === token.value && assignmentId === selectedAssignment.value?.id
  try {
    const rows = await request<SubmissionDetail[]>(`/api/v1/assignments/${assignmentId}/submissions`)
    if (!current()) return
    assignmentSubmissions.value = rows
    if (!selectedSubmission.value) {
      const first = rows.find(item => item.status !== 'graded') ?? rows[0]
      if (first) selectSubmission(first)
    }
  } catch (cause) {
    if (current()) assignmentSubmissionsError.value = cause instanceof Error ? cause.message : '学生提交暂时读取失败。'
  } finally { if (requestedToken === token.value && sequence === assignmentSubmissionsRequestId) assignmentSubmissionsLoading.value = false }
}

async function loadPublishedAssignmentReview(assignmentId: string) {
  const requestedToken = token.value
  try {
    const response = await fetch(`${apiBase}/api/v1/assignments/${assignmentId}/review`, {
      headers: { Authorization: `Bearer ${requestedToken}` },
    })
    if (requestedToken !== token.value || selectedAssignment.value?.id !== assignmentId) return
    if (response.status === 404) { assignmentPublishedReview.value = null; return }
    const data = await response.json()
    if (!response.ok) throw new Error(data?.detail ?? '讲评加载失败')
    assignmentPublishedReview.value = data as PublishedAssignmentReview
  } catch (error) {
    if (requestedToken !== token.value || selectedAssignment.value?.id !== assignmentId) return
    assignmentPublishedReview.value = null
    assignmentReviewMessage.value = error instanceof Error ? error.message : '讲评加载失败'
  }
}

function assignmentIsOverdue(item: AssignmentRecord) {
  return !!item.due_at && new Date(item.due_at).getTime() < clockNow.value
}

function canSubmitAssignment(item: AssignmentRecord) {
  if (item.submitted) return false
  if (!assignmentIsOverdue(item)) return true
  return item.late_request_status === 'approved' && (!item.late_approved_until || new Date(item.late_approved_until).getTime() > clockNow.value)
}

function assignmentLateHint(item: AssignmentRecord): string {
  if (!assignmentIsOverdue(item)) return ''
  if (canSubmitAssignment(item)) return ' · 获批补交，可直接提交'
  if (item.late_request_status === 'pending') return ' · 补交申请待教师审批'
  if (item.late_request_status === 'approved') return ' · 补交批准已过期，可重新申请'
  if (item.late_request_status === 'rejected') return ' · 补交申请未通过，可重新申请'
  return ' · 已截止，需申请补交'
}

async function requestLateSubmission() {
  if (!selectedAssignment.value || !lateRequestReason.value.trim()) return
  platformBusy.value = true
  try {
    await request<LateSubmissionRequest>(`/api/v1/assignments/${selectedAssignment.value.id}/late-requests`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ reason: lateRequestReason.value.trim() }),
    })
    platformStatus.value = '补交申请已提交，请等待教师审批。'
    lateRequestReason.value = ''
    await loadPlatformData()
    selectedAssignment.value = await request<AssignmentRecord>(`/api/v1/assignments/${selectedAssignment.value.id}`)
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '补交申请失败' }
  finally { platformBusy.value = false }
}

async function reviewLateSubmission(item: LateSubmissionRequest, statusValue: 'approved' | 'rejected') {
  platformBusy.value = true
  try {
    const approvedUntil = statusValue === 'approved' ? new Date(Date.now() + 7 * 86400000).toISOString() : null
    const updated = await request<LateSubmissionRequest>(`/api/v1/late-submission-requests/${item.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: statusValue, review_note: statusValue === 'approved' ? '同意补交，请在批准期限内完成。' : '本次补交申请未获批准。', approved_until: approvedUntil }),
    })
    lateSubmissionRequests.value = lateSubmissionRequests.value.map(value => value.id === updated.id ? updated : value)
    platformStatus.value = statusValue === 'approved' ? '已批准，学生可在 7 天内补交。' : '已驳回补交申请。'
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '审批失败' }
  finally { platformBusy.value = false }
}

async function updateAssignmentStatus(statusValue: 'draft' | 'published' | 'closed') {
  const assignment = selectedAssignment.value
  if (!assignment || platformBusy.value || user.value?.role === 'student') return
  const requestedToken = token.value
  platformBusy.value = true
  try {
    const updated = await request<AssignmentRecord>(`/api/v1/assignments/${assignment.id}/status`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: statusValue }),
    })
    if (requestedToken !== token.value) return
    if (selectedAssignment.value?.id === assignment.id) selectedAssignment.value = updated
    pendingAssignmentStatus.value=null
    await refreshWorkflowAssignments()
    platformStatus.value = statusValue === 'published' ? '作业已发布给课程学生，来源和操作记录已保留。' : '作业状态已更新。'
  } catch (cause) { if (requestedToken === token.value) platformStatus.value = cause instanceof Error ? cause.message : '作业状态暂未更新，请重试。' }
  finally { if (requestedToken === token.value) platformBusy.value = false }
}

function selectSubmission(item: SubmissionDetail) {
  if (selectedSubmission.value?.id === item.id) return
  if (!guardGradingExit(() => selectSubmission(item), '切换学生')) return
  gradingDraft.persist()
  selectedSubmission.value = item
  gradingRemoteChanged.value = null; gradingResultUnknown.value = false
  gradingDraft.open(user.value!.id, 'grading', item.id, { score: item.score, feedback: item.feedback || '', version: item.grading_version })
  applyingGradeDraft = true
  const local = gradingDraft.value.value
  gradeScore.value = local && Number.isFinite(local.score) ? local.score : item.score
  gradeFeedback.value = local && typeof local.feedback === 'string' ? local.feedback : item.feedback || ''
  applyingGradeDraft = false
  submissionMessage.value = ''
}
function selectSubmissionById(id: string) {
  const item = assignmentSubmissions.value.find(row => row.id === id)
  if (item) selectSubmission(item)
}

async function loadStudentAnswerAnalysis() {
  await requestStudentAnswerAnalysis(false)
}

async function generateStudentAnswerAnalysis() {
  await requestStudentAnswerAnalysis(true)
}

async function requestStudentAnswerAnalysis(generate: boolean) {
  const submission = selectedSubmission.value
  const assignment = selectedAssignment.value
  if (!submission || !assignment || submission.assignment_id !== assignment.id || !canManage.value) return
  if (generate && (studentAnswerAnalysisBusy.value || studentAnswerAnalysisLoading.value)) return
  const requestedToken = token.value
  const requestId = ++studentAnswerAnalysisRequestId
  studentAnswerAnalysisController?.abort()
  const controller = new AbortController()
  studentAnswerAnalysisController = controller
  studentAnswerAnalysisBusy.value = generate
  studentAnswerAnalysisLoading.value = !generate
  studentAnswerAnalysisError.value = ''
  const current = () => requestId === studentAnswerAnalysisRequestId && requestedToken === token.value &&
    submission.id === selectedSubmission.value?.id && assignment.id === selectedAssignment.value?.id
  try {
    if (generate) {
      await request('/api/v1/assistant/tasks', {method:'POST',signal:controller.signal,headers:{'Content-Type':'application/json'},
        body:JSON.stringify({request_id:crypto.randomUUID(),kind:'student_analysis',payload:{course_id:assignment.course_id,target_id:submission.id,confirm_external_analysis:true}})})
      if (current()) { assistantTasksRevision.value++; studentAnswerTaskMessage.value='已加入教学任务。可离开后查看；完成草稿不会改动成绩。' }
      return
    }
    const result = await request<StudentAnswerAnalysisResult<TeachingDraft> | null>(`/api/v1/submissions/${submission.id}/ai-analysis`, {
      signal: controller.signal, ...(generate ? { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirm_external_analysis: true }) } : {}),
    })
    if (!current()) return
    studentAnswerAnalysis.value = result
    if (result) teachingDrafts.value = [result.draft, ...teachingDrafts.value.filter(item => item.id !== result.draft.id)]
  } catch (error) {
    if (current() && !controller.signal.aborted) studentAnswerAnalysisError.value = error instanceof Error ? error.message : '作答分析暂不可用，请重试。'
  } finally {
    if (current()) { studentAnswerAnalysisBusy.value = false; studentAnswerAnalysisLoading.value = false }
  }
}

function useStudentAnalysisFeedback(value: string) {
  if (gradingSaving.value) return
  const result = studentAnswerAnalysis.value
  if (!result || result.stale || !selectedSubmission.value || value.trim().length < 2 || value.length > 2000) return
  if (gradeFeedback.value.trim() && gradeFeedback.value !== value) {
    pendingStudentFeedback.value = { token: token.value, submissionId: selectedSubmission.value.id, analysisId: result.draft.id,
      previous: gradeFeedback.value, value: value.trim() }
    return
  }
  gradeFeedback.value = value.trim()
}

function confirmStudentFeedback() {
  const pending = pendingStudentFeedback.value
  if (!pending || platformBusy.value) return
  if (pending.token !== token.value || pending.submissionId !== selectedSubmission.value?.id ||
      pending.analysisId !== studentAnswerAnalysis.value?.draft.id || studentAnswerAnalysis.value?.stale ||
      !canManage.value || pending.previous !== gradeFeedback.value) {
    pendingStudentFeedback.value = null
    submissionMessage.value = '当前作答或评语已变化，请重新核对并填入。'
    return
  }
  gradeFeedback.value = pending.value
  pendingStudentFeedback.value = null
  submissionMessage.value = '整理评语已填入，尚未保存批改；成绩未改变。'
}

function openStudentAnalysisDraft() {
  if (studentAnswerAnalysis.value) openTeachingDraft(studentAnswerAnalysis.value.draft)
}

async function gradeSubmission() {
  const submission = selectedSubmission.value
  const assignment = selectedAssignment.value
  const requestedToken = token.value
  if (!submission || !assignment || submission.assignment_id !== assignment.id || user.value?.role === 'student' || gradingSaving.value || platformBusy.value || !gradeValid.value) return
  if (gradingRemoteChanged.value || gradingResultUnknown.value || gradingDraft.recovery.value || gradingDraft.changedElsewhere.value) { submissionMessage.value = '请先核对最新记录或处理草稿版本，再保存。'; return }
  if (!/^[a-f0-9]{64}$/.test(submission.grading_version || '')) { submissionMessage.value = '当前记录缺少批改版本，请重新打开作业后保存。'; return }
  const payload = { score: gradeScore.value, feedback: gradeFeedback.value.trim() || null, expected_version: submission.grading_version }
  gradingDraft.persist()
  const current = () => requestedToken === token.value && assignment.id === selectedAssignment.value?.id && submission.id === selectedSubmission.value?.id
  gradingSaving.value = true
  platformBusy.value = true
  submissionMessage.value = ''
  try {
    const updated = await request<SubmissionDetail>(`/api/v1/submissions/${submission.id}/grade`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    if (!current()) return
    selectedSubmission.value = updated
    gradingDraft.clear()
    gradingDraft.open(user.value!.id, 'grading', updated.id, { score: updated.score, feedback: updated.feedback || '', version: updated.grading_version })
    applyingGradeDraft = true
    gradeScore.value = updated.score
    gradeFeedback.value = updated.feedback || ''
    applyingGradeDraft = false
    assignmentSubmissions.value = assignmentSubmissions.value.map(item => item.id === updated.id ? updated : item)
    submissionMessage.value = '成绩与评语已保存。'
    await loadPlatformData()
    if (current()) await loadPublishedAssignmentReview(assignment.id)
  } catch (error) {
    if (!current()) return
    gradingResultUnknown.value = true
    submissionMessage.value = error instanceof ApiError && error.status === 409 ? '服务器记录已变化，未覆盖他人的修改。正在读取最新记录…' : '未能确认保存结果，正在核对服务器当前记录；不会自动重试保存。'
    await reconcileGrading()
  }
  finally { if (requestedToken === token.value) { platformBusy.value = false; gradingSaving.value = false } }
}

async function reconcileGrading() {
  const item = selectedSubmission.value, assignment = selectedAssignment.value, requestedToken = token.value
  if (!item || !assignment) return
  try {
    const rows = await request<SubmissionDetail[]>(`/api/v1/assignments/${assignment.id}/submissions`)
    if (requestedToken !== token.value || selectedSubmission.value?.id !== item.id || selectedAssignment.value?.id !== assignment.id) return
    const latest = rows.find(row => row.id === item.id)
    if (!latest) throw new Error('当前提交不可访问，请先保留编辑内容。')
    assignmentSubmissions.value = rows
    gradingRemoteChanged.value = latest
    gradingResultUnknown.value = false
    if (latest.status === 'graded' && latest.score === gradeScore.value && (latest.feedback || '') === gradeFeedback.value.trim()) {
      acceptRemoteGrade(false)
      submissionMessage.value = '已核对：服务器当前成绩与本次输入一致，已同步显示。未重复提交。'
    } else if (latest.grading_version === item.grading_version) {
      gradingRemoteChanged.value = null
      submissionMessage.value = '已核对：服务器仍是原记录，本次输入已保留。请确认后再明确保存。'
    } else submissionMessage.value = '已读取服务器新版本。请对照下方最新成绩，选择采用最新记录或保留编辑后再保存。'
  } catch (cause) { if (requestedToken === token.value && selectedSubmission.value?.id === item.id) { gradingResultUnknown.value = true; submissionMessage.value = `暂时无法核对，当前编辑已保留；请点击“核对服务器记录”。${cause instanceof Error ? cause.message : ''}` } }
}

async function moderateAnswer(item: QuestionReview, reviewStatus: 'approved' | 'rejected', publish: boolean) {
  platformBusy.value = true
  try {
    const updated = await request<QuestionReview>(`/api/v1/question-reviews/${item.id}`, {
      method: 'PATCH', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        status: reviewStatus,
        revised_answer: item.revised_answer?.trim() || null,
        review_note: item.review_note?.trim() || null,
        publish_to_knowledge_base: publish,
      }),
    })
    Object.assign(item,updated)
    questionReviews.value = questionReviews.value.map(value => value.id === updated.id ? updated : value)
    reviewEdits.set(updated.id, { item, baseline: { revised_answer: updated.revised_answer, review_note: updated.review_note } })
    platformStatus.value = publish ? '审核完成，精选答案已建立索引并沉淀到课程知识库。' : '问答审核结果已保存。'
    await Promise.all([loadHealth(), loadKnowledgeBases()])
  } catch (error) { platformStatus.value = error instanceof Error ? error.message : '问答审核失败' }
  finally { platformBusy.value = false }
}

async function submitLearningAssignment() {
  if (!selectedAssignment.value || selectedAssignment.value.submitted || platformBusy.value) return
  const requestedToken = token.value
  const assignmentId = selectedAssignment.value.id
  let accepted=false
  assignmentDraft.persist()
  platformBusy.value = true
  try {
    const result = await request<{ score: number; max_score: number; correct_count: number; total_count: number; status: string }>(`/api/v1/assignments/${assignmentId}/submit`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers: serializeAnswers(assignmentAnswers.value) }),
    })
    if (requestedToken !== token.value) return
    accepted=true
    if(selectedAssignment.value?.id===assignmentId)selectedAssignment.value={...selectedAssignment.value,submitted:true,submission_status:result.status,score:result.status==='graded'?result.score:null,max_score:result.max_score,submitted_answers:serializeAnswers(assignmentAnswers.value)}
    if (selectedAssignment.value?.id === assignmentId) assignmentDraft.markSubmitted()
    submissionMessage.value = result.status === 'graded'
      ? `已自动批改：${result.score} / ${result.max_score} 分，答对 ${result.correct_count} / ${result.total_count} 题。`
      : '作业已提交，主观题等待教师批改。最终成绩和参考答案将在批改后显示。'
    await loadPlatformData()
    const loaded = await request<AssignmentRecord>(`/api/v1/assignments/${assignmentId}`)
    if (requestedToken !== token.value || selectedAssignment.value?.id !== assignmentId) return
    selectedAssignment.value = loaded
    assignmentDraft.open(null, loaded.submitted_answers ?? {})
    await loadPublishedAssignmentReview(assignmentId)
  } catch (error) { if (requestedToken === token.value) submissionMessage.value = accepted?'作业已提交，反馈暂未完整刷新，请返回后重新打开查看；不需要重复提交。':error instanceof Error ? error.message : '提交结果未确认，请重新打开作业核对。' }
  finally { if (requestedToken === token.value) platformBusy.value = false }
}

async function markWrongMastered(item: WrongQuestionRecord) {
  await request(`/api/v1/wrong-questions/${item.id}/mastered`, { method: 'PATCH' })
  await loadPlatformData()
}

const practiceSubmissions = createPracticeSubmissionTracker(() => localStorage)
async function submitPractice(item: PracticeRecommendation) {
  if (practiceResults.value[item.question.id]) return
  const rawAnswer = practiceAnswers.value[item.question.id] || ''
  const answer = Array.isArray(rawAnswer) ? JSON.stringify(rawAnswer) : rawAnswer.trim()
  if (!answer || platformBusy.value || practiceCoachBusy.value) return
  const requestedToken = token.value
  const owner = user.value?.id
  if (!owner) return
  const showResultDialog = !selectedPractice.value
  platformBusy.value = true
  let submitted = false
  try {
    const ticket = await practiceSubmissions.prepare(owner, item.question.id, answer)
    if (requestedToken !== token.value || user.value?.id !== owner) return
    const result = await request<PracticeResult>(`/api/v1/practice/questions/${item.question.id}/attempt`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answer, request_id: ticket.requestId }),
    })
    practiceSubmissions.complete(ticket)
    submitted = true
    if (requestedToken !== token.value || user.value?.role !== 'student') return
    if (selectedPractice.value?.question.id === item.question.id) practiceDraft.markSubmitted(true)
    practiceResults.value[item.question.id] = result
    if (selectedPractice.value?.question.id === item.question.id) practicePlanAttemptId.value = null
    if (showResultDialog && !selectedPractice.value) selectedPractice.value = item
    platformStatus.value = result.message
    const [wrong, practice, plans] = await Promise.all([
      request<WrongQuestionRecord[]>('/api/v1/wrong-questions'),
      request<PracticeRecommendation[]>('/api/v1/practice/recommendations?limit=10'),
      request<StudyPlan[]>('/api/v1/study-plans'),
    ])
    if (requestedToken !== token.value || user.value?.role !== 'student') return
    wrongQuestions.value = wrong
    practiceRecommendations.value = practice
    studentStudyPlans.value = plans
    assessmentRevision.value += 1
  } catch (error) {
    if (requestedToken === token.value && user.value?.id === owner) platformStatus.value = submitted
      ? '作答已提交，学习记录暂未刷新，请刷新页面核对，勿重复提交。'
      : `${error instanceof Error ? error.message : '提交结果暂未确认'}；同一作答重试会沿用本次提交编号。`
  }
  finally { if (requestedToken === token.value && user.value?.id === owner) platformBusy.value = false }
}

function openQuestionPractice(questionItem: QuestionItem, source: PracticeSource = 'diagnostic', retryCount = 0) {
  if (!saveAnswerDraftsBeforeExit()) return
  practiceDraft.release()
  draftCloseWarning.value = null
  practicePlanAttemptId.value = null
  selectedPractice.value = { question: questionItem, source, retry_count: retryCount, priority: 0, reason: '' }
  lastPractice.value=selectedPractice.value
  if (user.value?.role === 'student') assistantDraftCourseId.value = questionItem.course_id
  practiceDraft.open(user.value?.role === 'student'
    ? { owner: user.value.id, kind: 'practice', id: questionItem.id, questions: [questionItem] } : null,
    { [questionItem.id]: questionItem.question_type === 'multiple_choice' ? [] : '' })
  delete practiceResults.value[questionItem.id]
}

function explainPracticeTopic(courseId: string, topic: string) {
  if (user.value?.role !== 'student' || globalAssistantBusy.value) return
  if (!closeAnswerDialog('practice')) return
  assistantDraftCourseId.value = courseId
  globalAssistantOpen.value = true
  void askGlobalAssistant(`我刚练习了“${topic}”相关题目，请结合本课程可用资料讲清核心原理和常见误区，给一个不同的例子。不要推测我的具体作答或掌握程度。`)
}

function openPracticeStudyPlan(courseId: string) {
  if (!closeAnswerDialog('practice')) return
  void openAssistantResponseAction({ kind: 'study_plan', target_id: courseId, title: '学习计划', detail: '' })
}

function answerValues(store: Record<string, string | string[]>, questionId: string): string[] {
  const value = store[questionId]
  return Array.isArray(value) ? value : []
}

function toggleAnswer(store: Record<string, string | string[]>, questionId: string, option: string) {
  const values = answerValues(store, questionId)
  store[questionId] = values.includes(option) ? values.filter(value => value !== option) : [...values, option]
}

function hasAnswer(value: string | string[] | undefined): boolean {
  return Array.isArray(value) ? value.length > 0 : !!value?.trim()
}

function serializeAnswers(values: Record<string, string | string[]>): Record<string, string> {
  return Object.fromEntries(Object.entries(values).map(([key, value]) => [key, Array.isArray(value) ? JSON.stringify(value) : value]))
}

async function createPlatformCourse() {
  if (!newCourseTitle.value.trim() || !newCourseCode.value.trim() || platformBusy.value) return
  platformBusy.value = true
  platformStatus.value = '正在创建课程…'
  try {
    await request<CourseRecord>('/api/v1/courses', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title: newCourseTitle.value.trim(),
        code: newCourseCode.value.trim(),
        description: newCourseDescription.value.trim() || null,
        semester: newCourseSemester.value.trim() || null,
        cover_image_url: newCourseCover.value.trim() || null,
        status: 'draft',
      }),
    })
    newCourseTitle.value = ''
    newCourseCode.value = ''
    newCourseDescription.value = ''
    newCourseCover.value = ''
    platformStatus.value = '课程已创建，可继续配置章节、课程成员和教学资料。'
    await loadPlatformData()
  } catch (error) {
    platformStatus.value = error instanceof Error ? error.message : '课程创建失败'
  } finally {
    platformBusy.value = false
  }
}

async function updateCourseStatus(status: 'draft' | 'published' | 'archived') {
  if (!selectedCourse.value || platformBusy.value) return
  const courseId = selectedCourse.value.id, requestedToken = token.value
  platformBusy.value = true
  try {
  const updated = await request<CourseRecord>(`/api/v1/courses/${selectedCourse.value.id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status }),
  })
  if (requestedToken !== token.value || selectedCourse.value?.id !== courseId) return
  selectedCourse.value = updated
  platformStatus.value = status === 'published' ? '课程已发布，课程成员可以进入学习。' : status === 'archived' ? '课程已归档。' : '课程已转为草稿。'
  await loadPlatformData()
  } catch (cause) { if (requestedToken === token.value) platformStatus.value = cause instanceof Error ? cause.message : '未能确认课程状态，请重新打开课程核对。' }
  finally { if (requestedToken === token.value) platformBusy.value = false }
}

async function publishCourseAnnouncement() {
  if (!selectedCourse.value || !newAnnouncementTitle.value.trim() || !newAnnouncementContent.value.trim() || platformBusy.value) return
  platformBusy.value = true
  try {
    const wasEditing = Boolean(editingAnnouncementId.value)
    await request<CourseAnnouncement>(`/api/v1/courses/${selectedCourse.value.id}/announcements${wasEditing ? `/${editingAnnouncementId.value}` : ''}`, {
      method: wasEditing ? 'PUT' : 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: newAnnouncementTitle.value.trim(), content: newAnnouncementContent.value.trim() }),
    })
    resetAnnouncementEditor()
    await loadCourseAnnouncements(wasEditing ? announcementPageIndex.value : 1)
    platformStatus.value = wasEditing ? '课程公告已更新。' : '课程公告已发布。'
    announcementStatus.value = wasEditing ? '公告内容已更新。' : '课程公告已发布，学生现在可以查看。'
  } catch (error) {
    platformStatus.value = error instanceof Error ? error.message : '课程公告发布失败'
    announcementStatus.value = platformStatus.value
  } finally {
    platformBusy.value = false
  }
}

function resetAnnouncementEditor() {
  editingAnnouncementId.value = ''
  newAnnouncementTitle.value = ''
  newAnnouncementContent.value = ''
}

function editCourseAnnouncement(item: CourseAnnouncement) {
  if (!guardFormExit(() => editCourseAnnouncement(item), '编辑另一条公告', ['course-announcement'])) return
  editingAnnouncementId.value = item.id
  newAnnouncementTitle.value = item.title
  newAnnouncementContent.value = item.content
  announcementStatus.value = '正在编辑公告，保存后本课程成员将看到新内容。'
}

async function deleteCourseAnnouncement(item: CourseAnnouncement) {
  if (!selectedCourse.value || platformBusy.value || !window.confirm(`确认删除公告「${item.title}」？`)) return
  platformBusy.value = true
  try {
    await request(`/api/v1/courses/${selectedCourse.value.id}/announcements/${item.id}`, { method: 'DELETE' })
    if (editingAnnouncementId.value === item.id) resetAnnouncementEditor()
    await loadCourseAnnouncements(announcementPageIndex.value)
    announcementStatus.value = '公告已删除。'
  } catch (error) { announcementStatus.value = error instanceof Error ? error.message : '公告删除失败' }
  finally { platformBusy.value = false }
}

async function login() {
  if (!loginUsername.value.trim() || !loginPassword.value) return
  loginBusy.value = true
  loginError.value = ''
  try {
    const response = await request<{ access_token: string; browser_session?:string|null; user: User }>('/api/v1/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: loginUsername.value.trim(), password: loginPassword.value }),
    })
    token.value = response.browser_session ? 'cookie-session:'+response.browser_session : response.access_token
    localStorage.removeItem('rag_token')
    if(!response.browser_session)localStorage.setItem('rag_token',token.value)
    user.value = response.user
    if (user.value.role !== 'admin') setAnswerMode('hybrid')
    await loadAppData()
  } catch (error) {
    loginError.value = error instanceof Error ? error.message : '登录失败'
  } finally {
    loginBusy.value = false
  }
}

async function logout() {
  if(logoutBusy.value)return
  if (!saveAnswerDraftsBeforeExit(logout, '退出账号')) return
  logoutBusy.value=true
  try{await request('/api/v1/auth/logout',{method:'POST'});resetAuthenticatedSession()}
  catch(e){if(e instanceof ApiError&&e.status===401)resetAuthenticatedSession();else platformStatus.value='退出未能确认，请检查网络后重试。'}
  finally{logoutBusy.value=false}
}

function resetAuthenticatedSession() {
  versionDocumentId.value=''
  mobileNavigationOnTop.value=false
  mobileNavigation.reveal()
  lastPractice.value=null
  assignmentCreateOpen.value=false;questionEditorOpen.value=false;lateApprovalOpen.value=false;questionPreview.value=null;pendingQuestionDelete.value=null;pendingAssignmentStatus.value=null
  timetableFocusId.value='';timetableCourseFocus.value='';assignmentCourseFilter.value='';timetableDirty.value=false;timetableSaving.value=false
  accountCenterOpen.value = false; accountManagementOpen.value = false
  courseEditorId.value = ''; courseEditorDirty.value = false; courseEditorSaving.value = false
  workbenchOpen.value=false;workbenchDirty.value=false;workbenchSaving.value=false
  reviewEdits.clear()
  gradingDraft.persist(); teachingEditorDraft.persist(); gradingDraft.release(); teachingEditorDraft.release()
  pendingFormExit.value = null; modelConfigBaseline.value = null; modelApiKey.value = ''; newUserPassword.value = ''
  cancelDocumentOpen(); teachingEditingId = ''; gradingRemoteChanged.value = null; gradingResultUnknown.value = false
  newCourseTitle.value = ''; newCourseCode.value = ''; newCourseDescription.value = ''; newCourseCover.value = ''; newCourseSemester.value = '2026-2027 第一学期'
  newAssignmentTitle.value = ''; newAssignmentDueAt.value = ''; selectedQuestionIds.value = []; newUserName.value = ''; newUserDisplayName.value = ''; newUserRole.value = 'student'
  newKnowledgeBaseName.value = ''; newKnowledgeBaseDescription.value = ''; newSessionTitle.value = ''; newSessionDate.value = ''; newSessionLocation.value = ''; newSessionSectionId.value = ''; newCourseMemberUsername.value = ''; selectedFile.value = null
  newUserPassword.value = ''; modelApiKey.value = ''; adminRoleReason.value = ''; adminQuotaReason.value = ''; documentSharingReason.value = ''; draftGenerateTopic.value = ''
  listViewMemory.clear(); workspaceScroll.clear(); visitedPages.value = new Set(['dashboard']); visitedLearningTabs.value = new Set(['assignments']); visitedAdminTabs.value = new Set(['overview']); workspaceScrollTicket += 1
  courseDetailRequestId += 1
  courseDetailController?.abort()
  courseDetailController = null
  homeAssignmentReturn = null
  homeAssignmentOpening.value = ''
  platformLoading.value = false
  platformLoadError.value = ''
  gradingSaving.value = false
  pendingGradingExit.value = null
  assignmentSubmissionsLoading.value = false
  assignmentSubmissionsError.value = ''
  assignmentDraft.release(); practiceDraft.release(); draftCloseWarning.value = null
  learningTab.value = 'assignments'
  tutorPane.value = 'assistant'
  assistantPreferredMode.value = null
  platformDataSequence += 1
  questionPageSequence += 1
  dashboardRequestSequence += 1
  dashboardController?.abort()
  dashboardController = null
  dashboardRefreshing.value = false
  dashboardError.value = ''
  dashboardTaskKind.value = 'review'
  homeLateAssignmentId.value = ''
  homeLateAssignmentTitle.value = ''
  readerAnswer.value = null
  displayedAnswerQuestion.value = ''
  courseAnalysisOpen.value = false
  courseAnalysisCourseId.value = ''
  studentAnswerAnalysisRequestId += 1
  studentAnswerAnalysisController?.abort()
  studentAnswerAnalysis.value = null
  studentAnswerAnalysisBusy.value = false
  studentAnswerAnalysisLoading.value = false
  studentAnswerAnalysisError.value = ''
  selectedSubmission.value = null
  teacherInsightsRequestId += 1
  teacherInsightsController?.abort()
  teachingImpactRequestId += 1
  teachingImpactController?.abort()
  teacherInsights.value = null
  teachingImpact.value = null
  teacherInsightsBusy.value = false
  teachingImpactBusy.value = false
  teacherInsightsError.value = ''
  teachingImpactError.value = ''
  assistantDraftBusy.value = false
  platformBusy.value = false
  clearTeacherFocus()
  stopAnswerGeneration()
  assistantHistoryRequestId += 1
  assistantHistoryController?.abort()
  if (assistantHistorySearchTimer !== null) clearTimeout(assistantHistorySearchTimer)
  resetAssistantConversation()
  answerRequestId += 1
  tutorReceiptBusy.value = false
  tutorHistoryBusy.value = false
  tutorServerRequestId.value = ''
  tutorRequestState.value = null
  tutorRequestQuestion.value = ''
  startupError.value = ''
  tutorRestoredScope.value = null
  tutorHistoryNotice.value = ''
  token.value = ''
  loginError.value = ''
  studyNoteStatus.value = ''
  studyNoteStatusError.value = false
  user.value = null
  question.value = ''
  status.value = ''
  answer.value = null
  activeConversationId.value = null
  selectedFile.value = null
  selectedKnowledgeBaseId.value = ''
  showCreateForm.value = false
  knowledgeBases.value = []
  documents.value = []
  documentTotal.value = 0
  documentJobs.value = []
  history.value = []
  dashboardSummary.value = null
  platformCourses.value = []
  courseAnnouncements.value = []
  announcementTotal.value = 0
  announcementPageIndex.value = 1
  resetAnnouncementEditor()
  questionBank.value = []
  questionPageItems.value = []
  questionPageTotal.value = 0
  questionPageIndex.value = 1
  questionFilterCourse.value = ''
  questionFilterType.value = ''
  questionFilterKeyword.value = ''
  resetQuestionEditor()
  newQuestionCourseId.value = ''
  assignments.value = []
  wrongQuestions.value = []
  learningReports.value = []
  studentStudyPlans.value = []
  studyPlanBusy.value = false
  studentStudyNotes.value = []
  selectedPassage.value = null
  assistantAnswerPassage.value = null
  selectedDocumentContent.value = null
  courseAnalytics.value = null
  courseMembers.value = []
  selectedCourse.value = null
  selectedTeachingDraft.value = null
  selectedAssignment.value = null
  assignmentPublishedReview.value = null
  assignmentReviewMessage.value = ''
  teachingDrafts.value = []
  pendingReviewCount.value = 0
  draftQualityReport.value = null
  draftAIReviewConsent.value = false
  assistantDraftCourseId.value = ''
  studentCourseKnowledgeBases.value = {}
  studentCourseSessions.value = []
  assistantDraftTopic.value = ''
  assistantShareCourseMaterials.value = false
  globalAssistantOpen.value = false
  assistantView.value = 'chat'
  assistantHistory.value = []
  assistantHistoryQuery.value = ''
  assistantHistoryHasMore.value = false
  assistantHistoryError.value = ''
  assistantActionError.value = ''
  pendingAdminConfirmation.value = null
  adminMetrics.value = null
  adminUsers.value = []
  resetAdminUserSearch()
  courseCatalogFocus.value = 'all'
  courseCatalogFocusRevision.value = 0
  adminInsights.value = []
  adminReport.value = null
  adminReportError.value = ''
  auditLogs.value = []
  adminModelConfig.value = null
  activePage.value = 'dashboard'
  showMobileCatalog.value = false
  localStorage.removeItem('rag_token')
}

async function loadDocuments() {
  const sequence = ++documentLoadSequence
  const requestedToken = token.value
  const baseId = selectedKnowledgeBaseId.value
  if (!selectedKnowledgeBaseId.value) {
    documents.value = []
    documentTotal.value = 0
    return
  }
  const result = await pageLoader<DocumentRecord>('documents', baseId)(1, 10)
  if (sequence !== documentLoadSequence || requestedToken !== token.value || baseId !== selectedKnowledgeBaseId.value) return
  documents.value = result.items
  documentTotal.value = result.total
}

async function loadHealth() {
  try {
    const data = await request<{ status: string; indexed_chunks: number }>('/health')
    indexedChunks.value = data.indexed_chunks
  } catch {
    indexedChunks.value = 0
  }
}

async function loadHistory() {
  const sequence = ++historyLoadSequence
  const requestedToken = token.value
  const baseId = selectedKnowledgeBaseId.value
  if (!selectedKnowledgeBaseId.value) {
    history.value = []
    return
  }
  const records = await firstPage<HistoryItem>('history', baseId, '', 5)
  if (sequence === historyLoadSequence && requestedToken === token.value && baseId === selectedKnowledgeBaseId.value) history.value = records
}

async function loadKnowledgeBases() {
  const sequence = ++catalogLoadSequence
  const requestedToken = token.value
  loadingCatalog.value = true
  try {
    const list = await request<KnowledgeBase[]>('/api/v1/knowledge-bases')
    if (sequence !== catalogLoadSequence || requestedToken !== token.value) return
    knowledgeBases.value = list
    if (!list.some((item) => item.id === selectedKnowledgeBaseId.value)) {
      selectedKnowledgeBaseId.value = list[0]?.id ?? ''
    }
    await loadDocuments()
    await loadHistory()
  } catch (error) {
    if (sequence === catalogLoadSequence && requestedToken === token.value) status.value = error instanceof Error ? error.message : '资料库加载失败'
  } finally {
    if (sequence === catalogLoadSequence && requestedToken === token.value) loadingCatalog.value = false
  }
}

async function selectKnowledgeBase(id: string) {
  showMobileCatalog.value = false
  if (busy.value || id === selectedKnowledgeBaseId.value) return
  if (tutorHistoryBusy.value) { answerRequestId += 1; tutorHistoryBusy.value = false }
  selectedKnowledgeBaseId.value = id
  syncStudentCourseFromKnowledgeBase(id)
  answer.value = null
  activeConversationId.value = null
  status.value = ''
  try {
    await Promise.all([loadDocuments(), loadDocumentJobs()])
    await loadHistory()
  } catch (error) {
    status.value = error instanceof Error ? error.message : '文档列表加载失败'
  }
}

async function createKnowledgeBase() {
  if (!canManage.value || !newKnowledgeBaseName.value.trim() || !newKnowledgeBaseCourse.value.trim()) return
  busy.value = true
  try {
    const created = await request<KnowledgeBase>('/api/v1/knowledge-bases', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: newKnowledgeBaseName.value.trim(),
        course: newKnowledgeBaseCourse.value.trim(),
        description: newKnowledgeBaseDescription.value.trim() || null,
      }),
    })
    knowledgeBases.value = [...knowledgeBases.value, created]
    selectedKnowledgeBaseId.value = created.id
    documents.value = []
    newKnowledgeBaseName.value = ''
    newKnowledgeBaseDescription.value = ''
    showCreateForm.value = false
    status.value = `已创建资料库“${created.name}”。`
  } catch (error) {
    status.value = error instanceof Error ? error.message : '资料库创建失败'
  } finally {
    busy.value = false
  }
}

function chooseFile(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
  if (selectedFile.value) documentId.value = `upload-${Date.now()}`
}

async function uploadPdf() {
  if (!canManage.value || !selectedFile.value || !selectedKnowledgeBaseId.value) return
  busy.value = true
  status.value = '正在解析 PDF 并建立索引…'
  try {
    const form = new FormData()
    form.append('document_id', documentId.value)
    form.append('file', selectedFile.value)
    const job = await request<DocumentJob>(
      `/api/v1/knowledge-bases/${selectedKnowledgeBaseId.value}/document-jobs`,
      { method: 'POST', body: form },
    )
    documentJobs.value = [job, ...documentJobs.value.filter(item => item.id !== job.id)]
    status.value = `“${job.filename}”已进入处理队列，可继续使用其他功能。`
    selectedFile.value = null
    busy.value = false
    for (let count = 0; count < 60; count += 1) {
      await new Promise(resolve => window.setTimeout(resolve, 1000))
      const current = await request<DocumentJob>(`/api/v1/document-jobs/${job.id}`)
      documentJobs.value = documentJobs.value.map(item => item.id === current.id ? current : item)
      if (['completed','failed','cancelled'].includes(current.status)) {
        status.value = current.status === 'completed'
          ? `“${current.filename}”处理完成，建立 ${current.chunk_count} 个索引片段。`
          : `“${current.filename}”处理失败：${current.error_message}`
        await Promise.all([loadKnowledgeBases(), loadDocuments(), loadHealth()])
        break
      }
    }
  } catch (error) {
    status.value = error instanceof Error ? error.message : '上传失败'
  } finally {
    busy.value = false
  }
}

async function retryDocumentJob(job: DocumentJob) {
  if (busy.value || !['failed','cancelled'].includes(job.status)) return
  busy.value = true
  try {
    const queued = await request<DocumentJob>(`/api/v1/document-jobs/${job.id}/retry`, { method: 'POST' })
    documentJobs.value = documentJobs.value.map(item => item.id === queued.id ? queued : item)
    status.value = `已重新提交“${job.filename}”。`
    for (let count = 0; count < 60; count += 1) {
      await new Promise(resolve => window.setTimeout(resolve, 1000))
      const current = await request<DocumentJob>(`/api/v1/document-jobs/${job.id}`)
      documentJobs.value = documentJobs.value.map(item => item.id === current.id ? current : item)
      if (['completed','failed','cancelled'].includes(current.status)) {
        await Promise.all([loadDocuments(), loadHealth()])
        break
      }
    }
  } catch (error) { status.value = error instanceof Error ? error.message : '重试失败' }
  finally { busy.value = false }
}

async function cancelDocumentJob(job:DocumentJob){
  if(platformBusy.value||busy.value)return
  platformBusy.value=true
  try{const result=await request<DocumentJob>(`/api/v1/document-jobs/${job.id}/cancel`,{method:'POST'});documentJobs.value=documentJobs.value.map(j=>j.id===result.id?result:j);status.value='已取消资料处理。'}
  catch(e){platformStatus.value=e instanceof Error?e.message:'停止结果待核实，请刷新任务。'}
  finally{platformBusy.value=false}
}

async function openDocumentById(documentId: string, pageNumber: number | null = null) {
  versionDocumentId.value=''
  if (!guardFormExit(() => { void openDocumentById(documentId, pageNumber) }, '打开另一份资料', ['document'])) return
  const requestedToken = token.value
  const owner = user.value?.id
  documentReadController?.abort()
  const controller = new AbortController(), sequence = ++documentReadSequence
  documentReadController = controller
  documentOpening.value = documentId; documentOpenError.value = null
  const current = () => requestedToken === token.value && owner === user.value?.id && sequence === documentReadSequence && !controller.signal.aborted
  try {
    const content = await request<DocumentContent>(`/api/v1/documents/${documentId}/content`, { signal: controller.signal })
    if (!current()) return
    selectedDocumentContent.value = content
    selectedPassage.value = null
    documentPreviewTargetPage.value = pageNumber
    const sourceDocument = content.document
    syncStudentCourseFromKnowledgeBase(sourceDocument.knowledge_base_id)
    documentSourceUrl.value = sourceDocument.source_url || ''
    documentLicenseName.value = sourceDocument.license_name || ''
    documentLicenseUrl.value = sourceDocument.license_url || ''
    documentVersion.value = sourceDocument.version_label
    documentPublicationStatus.value = sourceDocument.publication_status
  } catch (error) { if (current()) documentOpenError.value = { id: documentId, page: pageNumber, message: error instanceof Error ? error.message : '无法打开引用资料' } }
  finally { if (current()) { documentOpening.value = null; documentReadController = null } }
}

async function openDocumentPreview(document: DocumentRecord) {
  await openDocumentById(document.id)
}

async function saveDocumentGovernance() {
  if (!selectedDocumentContent.value || !canManage.value || platformBusy.value) return
  const id = selectedDocumentContent.value.document.id, requestedToken = token.value
  platformBusy.value = true
  try {
  const updated = await request<DocumentRecord>(`/api/v1/documents/${selectedDocumentContent.value.document.id}`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({
      source_url: documentSourceUrl.value.trim() || null,
      license_name: documentLicenseName.value.trim() || null,
      license_url: documentLicenseUrl.value.trim() || null,
      version_label: documentVersion.value.trim() || '1.0',
      publication_status: documentPublicationStatus.value,
    }),
  })
  if (requestedToken !== token.value || selectedDocumentContent.value?.document.id !== id) return
  selectedDocumentContent.value.document = updated
  documentSourceUrl.value = updated.source_url || ''; documentLicenseName.value = updated.license_name || ''; documentLicenseUrl.value = updated.license_url || ''; documentVersion.value = updated.version_label; documentPublicationStatus.value = updated.publication_status
  status.value = '资料元数据与发布状态已保存。'
  await loadDocuments()
  } catch (cause) { if (requestedToken === token.value) status.value = cause instanceof Error ? cause.message : '资料信息保存结果未能确认，请重新核对。' }
  finally { if (requestedToken === token.value) platformBusy.value = false }
}

async function deleteDocument(document: DocumentRecord) {
  if (!canManage.value || busy.value || !window.confirm(`确定要移除“${document.name}”及其索引吗？`)) return
  busy.value = true
  try {
    await request<void>(`/api/v1/documents/${document.id}`, { method: 'DELETE', headers: { 'X-Confirm-Action': 'true' } })
    status.value = `已移除“${document.name}”。`
    await Promise.all([loadKnowledgeBases(), loadHealth()])
  } catch (error) {
    status.value = error instanceof Error ? error.message : '文档移除失败'
  } finally {
    busy.value = false
  }
}

async function ask(quickAction: 'follow_up' | 'simplify' | 'example' | 'practice' | null = null) {
  if (!canAsk.value || !user.value || tutorReceiptBusy.value) return
  if (quickAction && !activeConversationId.value) { status.value = '这条历史未能恢复原会话模式，请输入完整问题后开始新会话。'; return }
  if (tutorPendingMatches.value && tutorServerRequestId.value) {
    await recoverTutorRequest()
    return
  }
  const requestId = ++answerRequestId
  const requestedToken = token.value
  const owner = user.value.id
  const controller = new AbortController()
  answerAbortController = controller
  busy.value = true
  answer.value = null
  answerDraft.value = ''
  tutorServerRequestId.value = ''
  tutorRequestState.value = null
  tutorRequestQuestion.value = question.value
  tutorRequestContext.value = { kb: selectedKnowledgeBaseId.value, mode: answerMode.value }
  status.value = answerMode.value === 'general'
    ? '正在请求通用助手…'
    : answerMode.value === 'hybrid'
      ? '正在检索课程资料，并准备备用回答…'
      : '正在查找当前资料库中的课程证据…'
  try {
    const data = await sendAnswerRequest<AskResponse>(apiBase, requestedToken, owner, 'tutor', {
        question: question.value,
        knowledge_base_id: tutorRestoredScope.value ? tutorRestoredScope.value.requested_knowledge_base_id : selectedKnowledgeBaseId.value || null,
        answer_mode: answerMode.value,
        conversation_id: activeConversationId.value,
        assistant_course_id: tutorRestoredScope.value?.course_id || null,
        assistant_scope: tutorRestoredScope.value?.purpose || null,
        expected_domain_key: tutorRestoredScope.value?.domain_key || null,
        quick_action: quickAction,
    }, controller.signal, {
      onRequest: (id, state) => { if (requestId === answerRequestId) { tutorServerRequestId.value = id; tutorRequestState.value = state } },
      onStage: (label) => { if (requestId === answerRequestId) status.value = label },
      onDelta: (text) => { if (requestId === answerRequestId) answerDraft.value += text },
      onReset: () => { if (requestId === answerRequestId) answerDraft.value = '' },
    })
    if (requestId !== answerRequestId || requestedToken !== token.value) return
    answer.value = data
    displayedAnswerQuestion.value = tutorRequestQuestion.value
    answerDraft.value = ''
    activeConversationId.value = data.conversation_id
    status.value = data.message
    await loadHistory()
  } catch (error) {
    if (requestId !== answerRequestId) return
    answerDraft.value = ''
    status.value = error instanceof Error ? error.message : '问答失败'
  } finally {
    if (requestId === answerRequestId) {
      busy.value = false
      answerAbortController = null
    }
  }
}

async function stopAnswerGeneration(reason: 'user' | 'context_change' = 'user') {
  if (!busy.value) return
  const sequence = ++answerRequestId
  const requestedToken = token.value
  const owner = user.value?.id
  const kb = selectedKnowledgeBaseId.value
  const mode = answerMode.value
  const id = tutorServerRequestId.value
  const cancellation = id ? cancelAnswerRequest<AskResponse>(apiBase, requestedToken, id, reason) : null
  answerAbortController?.abort()
  answerAbortController = null
  busy.value = false
  answerDraft.value = ''
  tutorRequestState.value = cancellation ? 'unknown' : 'cancelled'
  status.value = cancellation ? '正在确认停止结果…' : '已停止发送，尚未开始生成。'
  if (!cancellation) return
  tutorReceiptBusy.value = true
  try {
    const receipt = await cancellation
    if (sequence !== answerRequestId || requestedToken !== token.value || owner !== user.value?.id) return
    tutorRequestState.value = receipt.status
    status.value = receipt.message
    if (receipt.answer && reason === 'user' && kb === selectedKnowledgeBaseId.value && mode === answerMode.value && question.value === tutorRequestQuestion.value) {
      answer.value = receipt.answer
      displayedAnswerQuestion.value = receipt.question
      activeConversationId.value = receipt.answer.conversation_id
      acknowledgeAnswer(owner!, 'tutor', id)
      await loadHistory()
    }
  } catch {
    if (sequence === answerRequestId && owner === user.value?.id) status.value = '停止结果尚未确认，请先查看处理结果。'
  } finally { if (sequence === answerRequestId) tutorReceiptBusy.value = false }
}

function restoreTutorRequest(value: AnswerReceipt) {
  if (busy.value || !user.value) return
  const receipt = value as AnswerReceipt<AskResponse>
  selectedKnowledgeBaseId.value = receipt.context.knowledge_base_id || ''
  answerMode.value = (receipt.context.answer_mode || 'hybrid') as AnswerMode
  question.value = receipt.question
  tutorRequestQuestion.value = receipt.question
  tutorRequestContext.value = { kb: receipt.context.knowledge_base_id || '', mode: receipt.context.answer_mode || 'hybrid' }
  tutorServerRequestId.value = receipt.request_id
  tutorRequestState.value = receipt.status
  answerDraft.value = ''
  answer.value = receipt.answer
  displayedAnswerQuestion.value = receipt.question
  activeConversationId.value = receipt.answer?.conversation_id || receipt.context.conversation_id || null
  const scope = receipt.answer?.answer_scope
  tutorRestoredScope.value = scope ? { ...scope, requested_knowledge_base_id: scope.requested_knowledge_base_id ?? null } : receipt.context.assistant_course_id || receipt.context.assistant_scope
    ? { course_id: receipt.context.assistant_course_id || null, requested_knowledge_base_id: receipt.context.knowledge_base_id || null, purpose: receipt.context.assistant_scope as AssistantMaterialScope['purpose'] } : null
  tutorHistoryNotice.value = '已恢复原请求设置；查看处理结果不会重新调用模型。'
  status.value = receipt.message
  if (receipt.answer) acknowledgeAnswer(user.value.id, 'tutor', receipt.request_id)
}

async function recoverTutorRequest() {
  if (!tutorServerRequestId.value || busy.value || tutorReceiptBusy.value) return
  const id = tutorServerRequestId.value
  const sequence = answerRequestId
  const requestedToken = token.value
  const originalQuestion = question.value
  const kb = selectedKnowledgeBaseId.value
  const mode = answerMode.value
  tutorReceiptBusy.value = true
  try {
    const receipt = await readAnswerReceipt<AskResponse>(apiBase, requestedToken, id)
    if (sequence !== answerRequestId || token.value !== requestedToken || id !== tutorServerRequestId.value) return
    tutorRequestState.value = receipt.status
    status.value = receipt.message
    if (originalQuestion === question.value && kb === selectedKnowledgeBaseId.value && mode === answerMode.value) restoreTutorRequest(receipt)
  } catch {
    if (sequence === answerRequestId && token.value === requestedToken) status.value = '暂时无法核对结果，请稍后再查看；本次没有重新调用模型。'
  } finally { if (sequence === answerRequestId) tutorReceiptBusy.value = false }
}

watch([selectedKnowledgeBaseId, answerMode], () => {
  if (busy.value) void stopAnswerGeneration('context_change')
  tutorRestoredScope.value = null
  tutorHistoryNotice.value = ''
  activeConversationId.value = null
}, { flush: 'sync' })

async function restoreHistory(selected: HistoryItem) {
  if (busy.value || tutorReceiptBusy.value) return
  const sequence = ++answerRequestId
  tutorHistoryBusy.value = true
  const requestedToken = token.value
  const requestedUserId = user.value?.id
  const requestedBase = selectedKnowledgeBaseId.value
  const previousDraft = question.value
  status.value = '正在核对并恢复这条回答…'
  try {
    const item = await request<HistoryItem>(`/api/v1/history/${selected.id}`)
    if (sequence !== answerRequestId || requestedToken !== token.value || requestedUserId !== user.value?.id ||
      requestedBase !== selectedKnowledgeBaseId.value) return
    if (question.value !== previousDraft) { status.value = '输入内容已改变，本次没有覆盖你的新问题。'; return }
    selectedKnowledgeBaseId.value = item.answer_scope?.requested_knowledge_base_id || item.knowledge_base_id || ''
    question.value = item.question
    const restoredMode = item.answer_mode
    if (restoredMode) {
      answerMode.value = restoredMode
      localStorage.setItem(answerModeStorageKey, restoredMode)
    }
    tutorRestoredScope.value = item.answer_scope ? { ...item.answer_scope, requested_knowledge_base_id: item.answer_scope.requested_knowledge_base_id ?? null } : null
    tutorServerRequestId.value = ''
    tutorRequestState.value = null
    tutorRequestQuestion.value = ''
    activeConversationId.value = restoredMode ? item.conversation_id : null
    answer.value = { ...item, answer_mode: restoredMode, history_id: item.id, conversation_id: item.conversation_id }
    displayedAnswerQuestion.value = item.question
    tutorHistoryNotice.value = restoredMode ? `原回答使用“${answerModeLabel(restoredMode)}”${item.answer_scope?.course_title ? `，课程为“${item.answer_scope.course_title}”` : ''}。这里只读回原记录；新提问请返回“对话与工具”并核对当前课程。`
      : '原回答模式未记录。这里只供查看；新提问请返回“对话与工具”，不会自动携带这条旧回答。'
    status.value = '已按当前权限恢复历史回答。'
  } catch (error) {
    if (sequence === answerRequestId && requestedToken === token.value && requestedUserId === user.value?.id) {
      status.value = error instanceof Error ? error.message : '此回答当前不可访问，请刷新历史记录。'
    }
  } finally {
    if (sequence === answerRequestId) tutorHistoryBusy.value = false
  }
}

function historyTime(value: string | null) {
  if (!value) return '刚刚'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '刚刚'
  return date.toLocaleString('zh-CN', { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

async function sendFeedback(rating: number) {
  if (!answer.value?.history_id || feedbackBusy.value) return
  feedbackBusy.value = true
  try {
    const updated = await request<HistoryItem>(`/api/v1/history/${answer.value.history_id}/feedback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rating }),
    })
    answer.value = { ...updated, answer_mode: answer.value.answer_mode, history_id: updated.id, conversation_id: updated.conversation_id }
    history.value = history.value.map((item) => (item.id === updated.id ? updated : item))
    status.value = rating >= 4 ? '感谢反馈，这条回答已标记为有帮助。' : '已记录改进反馈，我们会持续优化检索质量。'
  } catch (error) {
    status.value = error instanceof Error ? error.message : '反馈提交失败'
  } finally {
    feedbackBusy.value = false
  }
}

function newTutorConversation() {
  if (busy.value || tutorReceiptBusy.value) return
  answerRequestId += 1
  tutorHistoryBusy.value = false
  activeConversationId.value = null
  tutorRestoredScope.value = null
  tutorHistoryNotice.value = ''
  answer.value = null
  tutorServerRequestId.value = ''
  tutorRequestState.value = null
  tutorRequestQuestion.value = ''
  answerDraft.value = ''
  displayedAnswerQuestion.value = ''
  question.value = ''
  status.value = '已开始新的教学会话。'
}

async function toggleFavorite() {
  if (!answer.value?.history_id) return
  const updated = await request<HistoryItem>(`/api/v1/history/${answer.value.history_id}/favorite`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ favorite: !answer.value.favorite }),
  })
  answer.value = { ...answer.value, favorite: updated.favorite }
  history.value = history.value.map(item => item.id === updated.id ? updated : item)
  status.value = updated.favorite ? '回答已收藏。' : '已取消收藏。'
}

async function exportAnswer() {
  if (!answer.value?.history_id) return
  const exported = await request<{ filename: string; content: string }>(`/api/v1/history/${answer.value.history_id}/export`)
  const url = URL.createObjectURL(new Blob([exported.content], { type: 'text/markdown;charset=utf-8' }))
  const link = document.createElement('a')
  link.href = url
  link.download = exported.filename
  link.click()
  URL.revokeObjectURL(url)
}

function documentStatusLabel(value: string) {
  if (value === 'ready') return '已就绪'
  if (value === 'pending') return '处理中'
  if (value === 'error') return '失败'
  return value
}

function questionTypeLabel(value: string) {
  return ({ single_choice: '单选题', multiple_choice: '多选题', true_false: '判断题', fill_blank: '填空题', short_answer: '简答题' } as Record<string, string>)[value] || value
}

async function initialize() {
  authChecking.value = true
  startupError.value = ''
  let hadToken = Boolean(token.value)
  try {
    if(!token.value){
      try{
        const r=await request<{browser_session:string;user:User}>('/api/v1/auth/refresh',{method:'POST'})
        token.value='cookie-session:'+r.browser_session;user.value=r.user
        hadToken=true
      }catch(e){if(!(e instanceof ApiError&&[401,403,404,503].includes(e.status)))throw e}
    }
    if (token.value) {
      user.value = await request<User>('/api/v1/auth/me')
      if (user.value.role !== 'admin') setAnswerMode('hybrid')
    } else {
      const system = await request<SystemStatus>('/api/v1/system')
      modelStatus.value = system
      if (!system.auth_required) {
        user.value = { id: 'demo-admin', username: 'admin', display_name: '本地开发管理员', role: 'admin', role_label: '管理员' }
      }
    }
    if (user.value) await loadAppData()
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) {
      assignmentDraft.persist(); practiceDraft.persist()
      resetAuthenticatedSession()
      if (hadToken) loginError.value = '登录已过期，请重新登录。'
    } else {
      startupError.value = error instanceof Error ? error.message : '课程空间暂时无法加载。'
    }
  } finally {
    authChecking.value = false
  }
}

const pageAssetsStale = ref(false)
function markPageAssetsStale() { pageAssetsStale.value = true }
function reloadUpdatedPage() {
  if (busy.value || globalAssistantBusy.value) return
  if ((question.value.trim() || globalAssistantQuestion.value.trim()) &&
      !window.confirm('刷新将清除当前输入。已提交的问题可从历史或处理回执恢复。是否刷新？')) return
  window.location.reload()
}
onMounted(() => window.addEventListener('rag:assets-stale', markPageAssetsStale))
onUnmounted(() => window.removeEventListener('rag:assets-stale', markPageAssetsStale))
onMounted(() => window.addEventListener('beforeunload', warnBeforeGradingUnload))
onUnmounted(() => window.removeEventListener('beforeunload', warnBeforeGradingUnload))
onMounted(() => {
  void initialize()
  clockTimer = window.setInterval(() => { clockNow.value = Date.now() }, 30_000)
})
onUnmounted(() => {
  document.body.classList.remove('mobile-assistant-open')
  documentReadController?.abort()
  courseDetailController?.abort()
  assistantOlderController?.abort()
  dashboardController?.abort()
  studentAnswerAnalysisController?.abort()
  if (clockTimer !== null) window.clearInterval(clockTimer)
  answerAbortController?.abort()
  assistantAbortController?.abort()
  assistantHistoryController?.abort()
  assistantMaterialController?.abort()
  clearAssistantWaitTimer()
  teacherInsightsController?.abort()
  teachingImpactController?.abort()
  if (assistantHistorySearchTimer !== null) clearTimeout(assistantHistorySearchTimer)
})
</script>

<template>
  <section v-if="authChecking" class="auth-shell auth-loading">
    <div class="auth-card" role="status"><span class="ui-spinner" aria-hidden="true" />正在准备课程空间…</div>
  </section>

  <section v-else-if="startupError && !user && token" class="auth-shell"><div class="auth-card startup-error" role="alert"><h1>暂时无法加载课程空间</h1><p>{{ startupError }}</p><button type="button" @click="initialize">重新加载课程空间</button><button type="button" class="ghost-button" @click="resetAuthenticatedSession">返回登录</button></div></section>
  <AccountAccess v-else-if="!user || resetLinkSecret" :base="apiBase" :initial-invite="accountInvite" :reset-token="resetLinkSecret" :session-notice="loginError" @authenticated="accountAuthenticated" @consumed="consumeAccountLink" />

  <main v-else class="platform-shell" :style="{ '--mobile-nav-height': `${mobileNavigationHeight}px` }" :class="[`role-${user.role}`, { 'assistant-workspace-active': assistantInline, 'home-workspace-active': activePage === 'dashboard', 'mobile-navigation-collapsed': mobileNavigationCollapsed }]">
    <div class="mobile-nav-spacer" aria-hidden="true" />
    <Teleport to="body"><button v-if="compactViewport && mobileNavigationOnTop" type="button" class="mobile-nav-backdrop" aria-label="关闭平台导航" @click="closeMobileNavigation" /></Teleport>
    <aside ref="mobileSidebar" class="platform-sidebar" :role="mobileNavigationOnTop ? 'dialog' : undefined" :aria-modal="mobileNavigationOnTop ? true : undefined" aria-label="平台导航" :class="{ 'is-mobile-collapsed': mobileNavigationCollapsed, 'is-over-assistant': mobileNavigationOnTop }" :inert="mobileNavigationCollapsed" :aria-hidden="mobileNavigationCollapsed ? true : undefined" @keydown.esc="closeMobileNavigation">
      <div class="platform-brand">
        <span class="brand-mark">✦</span>
        <div><strong>智学助手</strong><small>{{ user.role === 'student' ? '学生学习空间' : user.role === 'teacher' ? '教师教学空间' : '平台管理空间' }}</small></div>
      </div>
      <div class="sidebar-context"><span>{{ user.role_label }}工作区</span><strong>{{ roleWorkspaceDescription }}</strong></div>
      <button class="mobile-nav-dismiss" type="button" aria-label="收起导航" @click="closeMobileNavigation">收起 ⌃</button>
      <nav id="platform-navigation" class="platform-navigation" aria-label="平台导航">
        <button
          v-for="item in workspaceItems"
          :key="item.value"
          type="button"
          :class="{ active: activeWorkspaceItem === item.value }"
          @click="openWorkspace(item.value)"
        >
          <span>{{ item.icon }}</span>{{ item.label }}
        </button>
      </nav>
      <div class="sidebar-account">
        <button class="profile-entry" type="button" aria-label="打开个人中心" :aria-expanded="accountCenterOpen" aria-haspopup="dialog" @click="accountCenterOpen = true">
          <AccountAvatar :name="user.display_name" :identity="user.username" :image="accountAvatar.image" />
          <span class="profile-entry-copy"><strong>个人中心</strong><small>{{ user.display_name }} · {{ user.role_label }}</small></span>
          <span class="profile-entry-arrow" aria-hidden="true">›</span>
        </button>
        <button class="account-signout" type="button" title="退出登录" @click="logout">退出</button>
      </div>
    </aside>

    <section class="platform-main">
      <header class="platform-topbar" :inert="mobileNavigationCollapsed" :aria-hidden="mobileNavigationCollapsed ? true : undefined">
        <Teleport to="body"><button v-if="mobileNavigationCollapsed && (!globalAssistantOpen || !compactViewport) && !selectedAssignment && !selectedPractice" type="button" class="mobile-nav-launcher" aria-label="展开导航" title="展开导航" aria-controls="platform-navigation" :aria-expanded="!mobileNavigationCollapsed" @click="mobileNavigation.reveal"><svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M4 6h16M4 12h16M4 18h16" /></svg></button></Teleport>
        <div><p class="section-kicker">SMART LEARNING PLATFORM</p><h1>{{ workspaceTitle }}</h1></div>
        <div v-if="isAdmin" class="topbar-status"><span class="live-dot" />{{ modelLabel }}</div>
        <div class="topbar-account">
          <button class="profile-entry" type="button" aria-label="打开个人中心" :aria-expanded="accountCenterOpen" aria-haspopup="dialog" @click="accountCenterOpen = true"><AccountAvatar :name="user.display_name" :identity="user.username" :image="accountAvatar.image" /><span>个人中心</span></button>
          <button class="account-signout" type="button" title="退出登录" @click="logout">退出</button>
        </div>
      </header>

      <p v-if="startupError" class="startup-error" role="alert">{{ startupError }} <button type="button" @click="initialize">重新加载课程空间</button></p>
      <PlatformUpdates :key="user.id" :owner="user.id" :active="activePage === 'dashboard'" :ready="!authChecking && !platformLoading && !platformBusy && !globalAssistantOpen && !selectedCourse && !selectedDocumentContent && !selectedAssignment && !selectedPractice && !readerAnswer" />
      <div v-if="platformLoading || assignmentOpenPending" class="page-loading-feedback" role="status"><span class="ui-spinner" aria-hidden="true" /><span>{{ assignmentOpenPending ? '正在打开作业详情…' : '正在读取课程与学习数据…' }}</span></div>

      <nav v-show="activePage === 'tutor'" class="assistant-workspace-tabs" aria-label="AI工作区视图">
        <button type="button" :class="{ active: tutorPane === 'assistant' }" :aria-pressed="tutorPane === 'assistant'" @click="openUnifiedAssistant">✦ 对话与工具</button>
        <button type="button" :class="{ active: tutorPane === 'materials' }" :aria-pressed="tutorPane === 'materials'" @click="tutorPane = 'materials'">▤ 资料与旧记录</button>
        <span>同一位助手，随处继续</span>
      </nav>
      <div id="assistant-workspace-host" v-show="assistantInline" class="assistant-workspace-host" />

      <section v-show="activePage === 'dashboard'" class="dashboard-page">
        <section v-if="user.role === 'student' && !platformLoading && !platformLoadError && !platformCourses.length" class="account-onboarding"><h2>欢迎加入智学助手</h2><p>向任课教师获取课程邀请码，加入后即可查看资料、作业和学习安排。已有选课申请可在个人中心查看审核进度。</p><button type="button" @click="accountCenterOpen = true">输入邀请码，加入课程</button></section>
        <div class="welcome-panel">
          <div>
            <p class="section-kicker">WELCOME BACK</p>
            <h2>{{ user.display_name }}，欢迎回来</h2>
            <p>{{ user.role === 'student' ? '从待完成作业、智能练习或课程问答继续今天的学习。' : user.role === 'teacher' ? '查看课程教学数据，快速进入题库、作业和AI问答审核。' : '查看平台运行、模型服务和课程建设情况。' }}</p>
          </div>
          <button type="button" @click="activePage = 'tutor'">打开 {{ tutorWorkspaceLabel }} <span aria-hidden="true">↗</span></button>
        </div>
        <div v-if="user.role === 'student'" class="metric-grid student-home-metrics">
          <button type="button" @click="openStudentShortcut('progress')"><span>课程学习进度</span><strong>{{ platformLoading ? '—' : `${learningReports.length} 门` }}</strong><small>查看每门课程进度</small><em>查看 ↓</em></button>
          <button type="button" @click="openStudentShortcut('assignments')"><span>作业完成程度</span><strong>{{ platformLoading ? '—' : `${assignmentCompletion}%` }}</strong><small>{{ pendingAssignments }} 项作业待处理<span v-if="overdueAssignments"> · {{ overdueAssignments }} 项需查看补交</span></small><i><b :style="{ width: `${assignmentCompletion}%` }" /></i><em>进入 ›</em></button>
          <button type="button" @click="openStudentShortcut('courses')"><span>我的课程</span><strong>{{ dashboardSummary?.course_count ?? 0 }}</strong><small>本学期课程</small><em>查看 ›</em></button>
          <button type="button" @click="openStudentShortcut('wrong')"><span>待掌握错题</span><strong>{{ platformLoading ? '—' : wrongQuestions.filter(item => !item.mastered).length }}</strong><small>进入错题本继续练习</small><em>练习 ›</em></button>
        </div>
        <div v-else class="metric-grid student-home-metrics role-home-metrics">
          <button type="button" @click="selectedCourse = null; activePage = 'courses'"><span>课程</span><strong>{{ dashboardSummary?.course_count ?? '—' }}</strong><small>当前可访问课程</small><em>查看 ›</em></button>
          <button type="button" @click="openHomeQuestions"><span>课程题目</span><strong>{{ dashboardSummary?.question_count ?? '—' }}</strong><small>进入课程题库</small><em>打开 ›</em></button>
          <button type="button" @click="selectedCourse = null; activePage = 'courses'"><span>在课学生</span><strong>{{ dashboardSummary?.student_count ?? '—' }}</strong><small>{{ dashboardSummary ? `${dashboardSummary.course_membership_count} 条课程成员记录` : '正在读取课程成员' }}</small><em>按课程查看 ›</em></button>
          <button v-if="user.role === 'teacher'" type="button" :disabled="!dashboardSummary" @click="showHomeTasks('review')"><span>待批改提交</span><strong>{{ dashboardSummary?.pending_review_count ?? '—' }}</strong><small>从下方待办进入具体作业</small><em>处理 ↓</em></button>
          <button v-else type="button" @click="openMaterialWorkspace"><span>课程资料</span><strong>{{ dashboardSummary?.document_count ?? '—' }}</strong><small>{{ dashboardSummary ? `${dashboardSummary.indexed_chunk_count} 个知识片段` : '正在读取资料' }}</small><em>打开资料库 ›</em></button>
        </div>
        <div v-if="user.role !== 'student'" class="home-summary-status"><span>{{ dashboardSummary?.as_of ? `统计读取于 ${historyTime(dashboardSummary.as_of)}` : '正在读取首页数据…' }}</span><button type="button" :disabled="dashboardRefreshing" @click="refreshDashboardSummary">{{ dashboardRefreshing ? '刷新中…' : '刷新数据' }}</button><p v-if="dashboardError" role="alert">{{ dashboardError }}</p></div>
        <div v-if="user.role === 'teacher' && dashboardSummary" ref="dashboardTeachingTasks" class="home-task-anchor" tabindex="-1"><DashboardTasks :key="user.id" :kind="dashboardTaskKind" :revision="dashboardSummary.as_of || ''" :busy="dashboardRefreshing || !!homeAssignmentOpening" :error="dashboardError" :counts="dashboardSummary" :request="request" @kind="dashboardTaskKind = $event" @refresh="refreshDashboardSummary" @assignment="openHomeAssignment" @insights="openCourseAnalysis" /></div>
        <StudentHome v-if="user.role === 'student'" :key="user.id" ref="studentHome" :assignments="assignments" :sessions="studentCourseSessions" :courses="platformCourses" :reports="learningReports" :plans="studentStudyPlans" :now="clockNow" :busy="platformLoading" :error="platformLoadError || dashboardError" :opening="homeAssignmentOpening" @assignment="openHomeAssignment" @course="openCourseDetail" @assistant="openUnifiedAssistant" @assignments="openStudentShortcut('assignments')" @courses="openStudentShortcut('courses')" @schedule="activePage='timetable'" @session="openTimetableSession" @plan="showStudyPlan" @retry="loadPlatformData" />
        <div v-else class="dashboard-grid">
          <section class="panel dashboard-courses">
            <div class="panel-heading"><div><p class="section-kicker">{{ user.role === 'student' ? 'COURSE SCHEDULE' : 'RECENT COURSES' }}</p><h2>{{ user.role === 'student' ? '我的课程表' : '最近课程' }}</h2></div><button class="text-button" @click="activePage = 'courses'">查看全部</button></div>
            <div v-if="dashboardSummary?.recent_courses.length" class="course-preview-list">
              <button v-for="course in dashboardSummary.recent_courses" :key="course.id" type="button" @click="openCourseDetail(course)">
                <span class="course-symbol">{{ course.code.slice(0, 2) }}</span>
                <span><strong>{{ course.title }}</strong><small v-if="user.role === 'student'">{{ course.schedule || '上课时间待通知' }} · {{ course.location || '地点待通知' }}</small><small v-else>{{ course.section_count }} 个章节 · {{ course.student_count }} 名学习者</small></span>
                <i>›</i>
              </button>
            </div>
            <p v-else-if="platformLoading" class="empty-state" role="status">正在读取可访问课程…</p>
            <p v-else-if="platformLoadError" class="empty-state" role="alert">{{ platformLoadError }}</p>
            <p v-else class="empty-state">还没有可访问课程。</p>
          </section>
          <section class="panel quick-panel">
            <p class="section-kicker">QUICK ACTIONS</p><h2>快捷入口</h2>
            <button type="button" @click="activePage = 'tutor'"><span>✦</span><div><strong>{{ user.role === 'student' ? '向课程导师提问' : `打开 ${tutorWorkspaceLabel}` }}</strong><small>{{ user.role === 'student' ? '使用课程资料获得可追溯解答' : user.role === 'teacher' ? '备课、出题与教学建议' : '了解运行情况与管理建议' }}</small></div></button>
            <button type="button" @click="activePage = user.role === 'admin' ? 'courses' : 'assessments'"><span>{{ user.role === 'admin' ? '▤' : '✓' }}</span><div><strong>{{ user.role === 'admin' ? '查看课程与资料' : user.role === 'teacher' ? '管理题库与作业' : '完成题目与作业' }}</strong><small>{{ user.role === 'student' ? `${pendingAssignments} 项作业待处理${overdueAssignments ? `，其中 ${overdueAssignments} 项需查看补交` : ''}` : user.role === 'teacher' ? `${questionBank.length} 道题可用于教学` : '核对课程、章节及资料状态' }}</small></div></button>
            <button type="button" @click="activePage = user.role === 'admin' ? 'admin' : 'courses'"><span>{{ user.role === 'admin' ? '⚙' : '▤' }}</span><div><strong>{{ user.role === 'admin' ? '系统管理' : user.role === 'teacher' ? '查看教学课程' : '查看我的课程' }}</strong><small>{{ user.role === 'admin' ? '用户、模型与运行审计' : '查看课程章节、资料与知识点' }}</small></div></button>
          </section>
        </div>
        <p v-if="platformStatus" class="platform-message">{{ platformStatus }}</p>
      </section>

      <TimetableWorkspace v-if="visitedPages.has('timetable')" v-show="activePage==='timetable'" :key="user.id" ref="timetableWorkspace" :base="apiBase" :token="token" :role="user.role" :active="activePage==='timetable'" :focus-id="timetableFocusId" :course-focus="timetableCourseFocus" @action="timetableAction" @changed="loadPlatformData" @dirty="timetableDirty=$event" @saving="timetableSaving=$event" />
      <section v-if="visitedPages.has('courses')" v-show="activePage === 'courses'" class="courses-page">
        <AssistantTaskPanel v-if="canManage && activePage === 'courses' && !globalAssistantOpen" :key="user.id" :request="request" :refresh="assistantTasksRevision" @open-draft="openCohortDraft" @open-work="openTeachingWorkbench('history','',$event)" />
        <button v-if="canManage" class="account-manage-entry" type="button" @click="openAccountManagement()">邀请学生与选课审核</button>
        <button v-else class="account-manage-entry" type="button" @click="accountCenterOpen = true">使用邀请码加入课程</button>
        <div class="page-intro"><div><h2>{{ user.role === 'admin' ? '课程目录与资料' : user.role === 'teacher' ? '教学课程目录' : '我的课程' }}</h2><p>课程统一承载章节、资料、问答、题目、作业和学习数据。</p></div><span>{{ platformCourses.length }} 门课程</span></div>
        <CourseDirectory :key="user.id" :request="request" :revision="courseCatalogRevision" :focus="courseCatalogFocus" :focus-revision="courseCatalogFocusRevision" @select="openCourseDetail" />
        <div v-if="canManage" class="inline-actions"><button type="button" @click="openTeachingWorkbench('materials')">资料选题与课程 AI 工具</button><button type="button" @click="openTeachingWorkbench('schedule')">AI {{ user.role==='teacher'?'调课申请':'辅助排课' }}</button></div>
        <details v-if="canManage" class="course-create-disclosure"><summary>＋ 创建课程</summary><div class="panel course-create-panel">
          <div><p class="section-kicker">CREATE COURSE</p><h2>创建课程</h2></div>
          <label>课程名称<input v-model="newCourseTitle" placeholder="例如：操作系统" /></label>
          <label>课程代码<input v-model="newCourseCode" placeholder="例如：OS-2026" /></label>
          <label>学期<input v-model="newCourseSemester" placeholder="例如：2026-2027 第一学期" /></label>
          <label>封面地址（可选）<input v-model="newCourseCover" placeholder="课程封面图片地址" /></label>
          <label>课程简介（可选）<input v-model="newCourseDescription" placeholder="简要介绍课程内容" /></label>
          <button :disabled="platformBusy || !newCourseTitle.trim() || !newCourseCode.trim()" @click="createPlatformCourse">创建课程</button>
        </div></details>
        <p v-if="platformStatus" class="platform-message">{{ platformStatus }}</p>
        <section v-if="canManage" class="panel teaching-draft-panel"><div class="panel-heading"><div><p class="section-kicker">AI TEACHING DRAFTS</p><h2>AI 教学草稿箱</h2><p>生成内容先在这里编辑和确认，不会自动发布。</p></div><span class="count-label">教学内容草稿</span></div><div class="draft-generator"><select v-model="draftGenerateCourseId"><option v-for="course in platformCourses" :key="course.id" :value="course.id">{{ course.title }}</option></select><select v-model="draftGenerateType"><option value="teaching_plan">教学计划</option><option value="lesson_plan">单次课教案</option><option value="question_set">混合题型题目</option></select><input v-model="draftGenerateTopic" :placeholder="draftGenerateType === 'question_set' ? '知识点或章节，例如 二叉树遍历' : '本次教学主题（可选）'" /><button :disabled="platformBusy || !draftGenerateCourseId" @click="generateTeachingDraft">{{ platformBusy ? '正在生成…' : 'AI 生成草稿' }}</button><label class="draft-share-consent"><input v-model="draftShareCourseMaterials" type="checkbox" />我确认有权使用本课程资料，并同意将检索到的相关片段发送给当前模型服务用于生成草稿</label></div><PagedList class="teaching-draft-list" :items="activeTeachingDrafts" :page-size="8" :load-page="pageLoader<TeachingDraft>('drafts')" label="教学草稿" v-slot="{ items: draftItems }"><button v-for="draft in draftItems" :key="draft.id" type="button" @click="openTeachingDraft(draft)"><span :class="`status-badge status-${draft.status === 'published' || draft.status === 'confirmed' ? 'completed' : 'processing'}`">{{ draft.status === 'published' ? (draft.draft_type === 'review' ? '讲评已发布' : '已入库') : draft.status === 'confirmed' ? '已确认' : '待确认' }}</span><div><strong>{{ draft.title }}</strong><small>{{ draft.course_title }} · {{ teachingDraftTypeLabel(draft.draft_type) }} · {{ historyTime(draft.updated_at) }}</small></div><i>查看 ›</i></button><p v-if="!draftItems.length" class="empty-state">暂无草稿。可在此生成，或保存右下角 AI 教学助理的回答。</p></PagedList></section>

      </section>

      <section v-if="visitedPages.has('assessments')" v-show="activePage === 'assessments'" class="module-page assessment-page" :class="{ 'student-assessments': user.role === 'student' }">
        <div v-if="['practice','questions','wrong','reviews'].includes(learningTab)" class="learning-tabs assessment-section-tabs" role="group" :aria-label="user.role==='student'?'练习中心分类':'题库管理分类'">
          <button :class="{ active: learningTab === 'questions' }" @click="learningTab = 'questions'">{{ user.role === 'student' ? '题库练习' : '课程题库' }}</button>
          <button v-if="user.role === 'student'" :class="{ active: learningTab === 'practice' }" @click="learningTab = 'practice'">智能练习 <span>{{ practiceRecommendations.length }}</span></button>
          <button v-if="user.role === 'student'" :class="{ active: learningTab === 'wrong' }" @click="learningTab = 'wrong'">错题本 <span>{{ wrongQuestions.length }}</span></button>
          <button v-if="user.role === 'teacher'" :class="{ active: learningTab === 'reviews' }" @click="learningTab = 'reviews'">问答审核 <span>{{ questionReviews.filter(item => item.review_status === 'pending').length }}</span></button>
        </div>
        <PagedList v-if="user.role === 'student' && visitedLearningTabs.has('reports') && learningReports.length" v-show="learningTab === 'reports'" :items="learningReports" :page-size="6" label="学习报告" v-slot="{ items: reportItems }"><section class="learning-report-grid">
          <article v-for="report in reportItems" :key="report.course_id" class="panel report-card"><div class="report-head"><div><p class="section-kicker">LEARNING REPORT</p><h2>{{ report.course_title }}</h2></div><strong>{{ report.progress_percent }}%</strong></div>
            <div class="progress-track"><i :style="{ width: `${report.progress_percent}%` }" /></div>
            <div class="report-metrics"><span><b>{{ report.completed_assignments }}/{{ report.assignment_count }}</b>作业完成</span><span><b>{{ report.average_score }}%</b>平均成绩</span><span><b>{{ report.wrong_question_count }}</b>待掌握错题</span></div>
            <div class="section-progress"><button v-for="section in report.sections" :key="section.section_id" @click="selectedLearningSection = { report, section }"><span>{{ section.section_title }}</span><b>{{ section.progress_percent }}%　›</b></button></div>
          </article>
        </section>
        </PagedList>
        <section v-if="user.role === 'teacher' && courseAnalytics && learningTab==='reports'" class="panel analytics-panel"><div class="panel-heading"><div><p class="section-kicker">AI LEARNING INSIGHTS</p><h2>{{ courseAnalytics.course_title }} · 全体学情</h2><p>{{ courseAnalytics.student_count }} 名学生 · {{ courseAnalytics.assignment_count }} 份作业</p></div><button type="button" @click="openCourseAnalysis(courseAnalytics.course_id)">✦ 查看成绩与 AI 综合分析</button></div>
          <p>集中查看成绩分布、各次作业与实名学生记录；由 AI 帮助梳理共性问题与具体辅导行动。</p>
        </section>
        <p v-if="platformStatus" class="platform-message">{{ platformStatus }}</p>

        <div v-if="visitedLearningTabs.has('assignments')" v-show="learningTab === 'assignments'" class="learning-layout">
          <AssignmentDirectory :key="user.id" :request="request" :role="user.role" :courses="platformCourses" :revision="assessmentRevision" :course-focus="assignmentCourseFilter" :opening="assignmentOpenPending>0" @open="openAssignment" @create="assignmentCreateOpen=true" @late="homeLateAssignmentId='';homeLateAssignmentTitle='';lateApprovalOpen=true" @assistant="prepareAssessmentAI" />
          <DetailDialog v-if="user.role!=='student' && assignmentCreateOpen" title="创建作业草稿" :close-disabled="platformBusy" @close="closeAssignmentCreate"><section class="panel publish-panel assessment-editor-panel">
            <p class="section-kicker">ASSIGNMENT DRAFT</p><h2>创建课程作业草稿</h2>
            <p v-if="platformStatus" class="platform-message" role="status">{{ platformStatus }}</p>
            <label class="due-field">所属课程<select v-model="newAssignmentCourseId" @change="selectedQuestionIds = []"><option value="">选择课程</option><option v-for="course in platformCourses" :key="course.id" :value="course.id">{{ course.title }}</option></select></label>
            <label class="due-field">作业名称<input v-model="newAssignmentTitle" placeholder="例如：第二章课后练习" /></label>
            <label class="due-field">截止时间（可选）<input v-model="newAssignmentDueAt" type="datetime-local" /></label>
            <PagedList class="question-picker" :items="assignmentQuestionOptions" :scope="newAssignmentCourseId" :load-page="assignmentPickerPage" :page-size="8" label="组卷题目" v-slot="{ items: pickerItems, loading: pickerLoading, error: pickerError }"><label v-for="item in pickerItems" :key="item.id"><input v-model="selectedQuestionIds" type="checkbox" :value="item.id" /><span>{{ item.stem }}</span></label><p v-if="!pickerLoading && !pickerError && !pickerItems.length" class="empty-state">{{ newAssignmentCourseId ? '该课程暂无题目，请先在题库添加或审核 AI 题目草稿。' : '请先选择所属课程。' }}</p></PagedList>
            <button :disabled="platformBusy || !newAssignmentCourseId || !newAssignmentTitle.trim() || !selectedQuestionIds.length" @click="createLearningAssignment">保存作业草稿</button>
            <p class="assignment-selected-count">已选择 {{ selectedQuestionIds.length }} 道题，保存后可核对并发布。</p>
          </section></DetailDialog>
          <DetailDialog v-if="user.role!=='student' && lateApprovalOpen" title="补交审批" :close-disabled="platformBusy" @close="lateApprovalOpen=false"><section ref="homeLateApprovalPanel" tabindex="-1" class="panel late-approval-panel"><div class="panel-heading"><div><p v-if="homeLateAssignmentId">{{ homeLateAssignmentTitle }} · 查看这份作业的申请与历史处理记录</p></div><span class="count-label">{{ lateSubmissionRequests.filter(item => item.status === 'pending' && (!homeLateAssignmentId || item.assignment_id === homeLateAssignmentId)).length }} 待处理</span><button v-if="homeLateAssignmentId" type="button" class="text-button" @click="homeLateAssignmentId = ''; homeLateAssignmentTitle = ''">查看全部申请</button></div>
            <PagedList :items="lateSubmissionRequests" :scope="homeLateAssignmentId" :load-page="pageLoader<LateSubmissionRequest>('late-requests', homeLateAssignmentId)" label="补交申请" v-slot="{ items: lateItems }">
            <article v-for="item in lateItems" :key="item.id" class="late-request-row"><div><strong>{{ item.student_name }} · {{ item.assignment_title }}</strong><small>{{ historyTime(item.requested_at) }} · {{ item.reason }}</small><p v-if="item.review_note">{{ item.review_note }}<span v-if="item.approved_until"> · 有效至 {{ historyTime(item.approved_until) }}</span></p></div><span :class="`status-badge status-${item.status}`">{{ item.status === 'pending' ? '待审批' : item.status === 'approved' ? '已批准' : item.status === 'used' ? '已补交' : '已驳回' }}</span><div v-if="item.status === 'pending'" class="review-actions"><button class="danger-soft" :disabled="platformBusy" @click="reviewLateSubmission(item, 'rejected')">驳回</button><button :disabled="platformBusy" @click="reviewLateSubmission(item, 'approved')">批准 7 天</button></div></article>
            <p v-if="!lateItems.length" class="empty-state">暂无补交申请。</p>
            </PagedList>
          </section></DetailDialog>
        </div>

        <div v-if="visitedLearningTabs.has('questions')" v-show="learningTab === 'questions'" class="learning-layout">
          <QuestionDirectory :key="user.id" :request="request" :role="user.role" :courses="platformCourses" :revision="assessmentRevision" @select="user.role==='student'?openQuestionPractice($event):questionPreview=$event" @create="resetQuestionEditor();questionEditorOpen=true" @assistant="prepareAssessmentAI" @compose="assignmentCreateOpen=true;learningTab='assignments'" />
          <DetailDialog v-if="user.role!=='student' && questionEditorOpen" :title="editingQuestionId?'编辑题目':'新建题目'" :close-disabled="platformBusy" @close="closeQuestionEditor"><section class="panel publish-panel assessment-editor-panel">
            <p class="section-kicker">QUESTION EDITOR</p><h2>{{ editingQuestionId ? '编辑题目' : '新增题目' }}</h2><p v-if="editingQuestionId" class="editor-mode">已用于作业或练习的题目不可修改 <button type="button" @click="guardFormExit(resetQuestionEditor, '取消编辑题目', ['question-editor'], true) && resetQuestionEditor()">取消编辑</button></p>
            <p v-if="platformStatus" class="platform-message" role="status">{{ platformStatus }}</p>
            <label class="due-field">所属课程<select v-model="newQuestionCourseId" :disabled="Boolean(editingQuestionId)"><option value="">选择所属课程</option><option v-for="course in platformCourses" :key="course.id" :value="course.id">{{ course.title }}</option></select></label>
            <label class="due-field">题目类型<select v-model="newQuestionType"><option value="single_choice">单选题</option><option value="multiple_choice">多选题</option><option value="true_false">判断题</option><option value="fill_blank">填空题</option><option value="short_answer">简答题</option></select></label>
            <label class="due-field">题干<textarea v-model="newQuestionStem" placeholder="输入完整题目" /></label>
            <label v-if="['single_choice', 'multiple_choice', 'true_false'].includes(newQuestionType)" class="due-field">选项<input v-model="newQuestionOptions" :placeholder="newQuestionType === 'true_false' ? '例如：正确，错误' : '选项，用逗号分隔'" /></label>
            <label class="due-field">正确答案<input v-model="newQuestionAnswer" :placeholder="newQuestionType === 'multiple_choice' ? '多个正确答案用逗号分隔' : newQuestionType === 'fill_blank' ? '多个空用 || 分隔，同一空的可接受答案用 / 分隔' : '正确答案'" /></label>
            <label class="due-field">知识点<input v-model="newQuestionPoint" placeholder="例如：二叉树" /></label>
            <label class="due-field">答案解析（可选）<textarea v-model="newQuestionExplanation" rows="3" placeholder="补充解题过程与易错点" /></label>
            <label class="due-field">难度<select v-model.number="newQuestionDifficulty"><option v-for="level in 5" :key="level" :value="level">{{ level }} 级</option></select></label>
            <button :disabled="platformBusy || !newQuestionCourseId || !newQuestionStem.trim() || !newQuestionAnswer.trim()" @click="createQuestionItem">{{ editingQuestionId ? '保存题目' : '加入题库' }}</button>
          </section></DetailDialog>
        </div>

        <section v-if="user.role === 'student' && visitedLearningTabs.has('practice')" v-show="learningTab === 'practice'" class="practice-hub">
          <header class="practice-hub-heading"><div><h2>从一道题开始</h2><p>按当前学习情况推荐，点击题目进入专注练习。</p></div><button type="button" class="ghost-button" @click="learningTab='questions'">浏览全部题库 ›</button></header>
          <button v-if="lastPractice" type="button" class="practice-continue" @click="openQuestionPractice(lastPractice.question,lastPractice.source,lastPractice.retry_count)">继续上次练习：{{ lastPractice.question.knowledge_point || '课程练习' }} ›</button>
          <PagedList :items="practiceRecommendations" :page-size="6" label="推荐练习" v-slot="{items:rows}"><div class="practice-recommendations"><button v-for="item in rows" :key="item.question.id" type="button" class="practice-recommendation" @click="openQuestionPractice(item.question,item.source,item.retry_count)"><span>{{ practiceSourceLabel(item.source) }}</span><strong>{{ item.question.knowledge_point || '综合练习' }}</strong><small>{{ questionTypeLabel(item.question.question_type) }} · 难度 {{ item.question.difficulty }}</small><p>{{ item.reason }}</p><b>练习 ›</b></button></div><p v-if="!rows.length" class="empty-state">暂无推荐练习，可到题库选择感兴趣的知识点。</p></PagedList>
        </section>

        <QuestionDirectory v-if="user.role==='student' && visitedLearningTabs.has('wrong')" v-show="learningTab==='wrong'" :key="user.id+'wrong'" :request="request" :role="user.role" :courses="platformCourses" :revision="assessmentRevision" wrong @select="openQuestionPractice($event,'wrong_question',$event.retry_count||0)" />

        <section v-if="user.role === 'teacher' && visitedLearningTabs.has('reviews')" v-show="learningTab === 'reviews'" class="panel learning-list review-list"><div class="panel-heading"><div><p class="section-kicker">ANSWER REVIEW</p><h2>AI 问答审核与精选沉淀</h2></div><span class="count-label">课程问答记录</span></div>
          <label class="inline-actions"><input v-model="reviewFeedbackOnly" type="checkbox" />只看有定位反馈的问答</label>
          <PagedList :items="questionReviews" :page-size="5" :scope="String(reviewFeedbackOnly)" :load-page="pageLoader<QuestionReview>('reviews','',reviewFeedbackOnly?'status=feedback':'')" label="问答审核" v-slot="{ items: reviewItems }">
          <article v-for="item in reviewItems" :key="item.id" class="review-card">
            <header><span :class="`review-status ${item.review_status}`">{{ item.review_status === 'pending' ? '待审核' : item.review_status === 'approved' ? '已通过' : '已驳回' }}</span><small>{{ historyTime(item.created_at) }} · 学生评分 {{ item.rating || '—' }}</small></header>
            <h3>{{ item.question }}</h3><div class="review-original"><b>AI 原回答</b><RichText :source="item.answer" :tools="false" /></div>
            <AnswerFeedbackReview :history-id="item.id" :request="request" />
            <label>教师修订答案<textarea v-model="item.revised_answer" placeholder="可直接采用原答案，也可在这里修订为更准确、适合教学的版本" /></label>
            <label>审核意见<textarea v-model="item.review_note" placeholder="记录错误点、改进建议或通过理由" /></label>
            <div class="review-actions"><button class="danger-soft" :disabled="platformBusy" @click="moderateAnswer(item, 'rejected', false)">驳回并记录</button><button class="ghost-button" :disabled="platformBusy" @click="moderateAnswer(item, 'approved', false)">仅审核通过</button><button :disabled="platformBusy || !item.knowledge_base_id" :title="item.knowledge_base_id ? '写入当前问答关联的知识库' : '该问答未关联知识库，不能沉淀'" @click="moderateAnswer(item, 'approved', true)">通过并沉淀知识库</button></div>
            <p v-if="item.published_document_id" class="curated-note">✓ 已作为“教师精选问答”建立向量索引</p>
          </article><p v-if="!reviewItems.length" class="empty-state">暂无待审核问答。</p>
          </PagedList>
        </section>

        <DetailDialog v-if="questionPreview&&user.role!=='student'" title="题目详情" :description="`${questionTypeLabel(questionPreview.question_type)} · ${questionPreview.knowledge_point || '综合知识'} · 难度 ${questionPreview.difficulty}`" @close="questionPreview=null"><RichText :source="questionPreview.stem" :tools="false" /><ol v-if="questionPreview.options.length" class="question-detail-options"><li v-for="option in questionPreview.options" :key="option">{{ option }}</li></ol><details class="question-detail-answer"><summary>查看答案与解析</summary><h4>参考答案</h4><RichText :source="questionPreview.correct_answer||'未提供参考答案'" :tools="false" /><h4>解析</h4><RichText :source="questionPreview.explanation||'暂未填写解析'" :tools="false" /></details><QuestionOrigin :key="questionPreview.id" :question-id="questionPreview.id" :request="request" /><QuestionStatistics :question-id="questionPreview.id" :request="request" /><template #footer><span>已用于作业或练习的题目不可覆盖修改</span><div class="inline-actions"><button type="button" class="danger-soft" :disabled="platformBusy" @click="deleteQuestionItem(questionPreview)">删除题目</button><button type="button" :disabled="platformBusy" @click="editQuestionItem(questionPreview)">编辑题目</button></div></template></DetailDialog>
        <DetailDialog v-if="pendingQuestionDelete" title="确认删除题目？" size="small" :close-disabled="platformBusy" @close="pendingQuestionDelete=null"><p>将删除这道尚未使用的题目，删除后不能在页面中恢复。已用于作业或练习的题目会由系统阻止删除。</p><p v-if="platformStatus" role="status" class="status">{{ platformStatus }}</p><template #footer><button type="button" :disabled="platformBusy" @click="pendingQuestionDelete=null">取消</button><button type="button" class="danger-soft" :disabled="platformBusy" @click="deleteQuestionItem(pendingQuestionDelete,true)">确认删除</button></template></DetailDialog>
        <DetailDialog v-if="pendingAssignmentStatus&&selectedAssignment" :title="pendingAssignmentStatus==='published'?'发布这份作业？':'关闭这份作业提交？'" size="small" :close-disabled="platformBusy" @close="pendingAssignmentStatus=null"><p>{{ selectedAssignment.title }}</p><p>{{ pendingAssignmentStatus==='published'?'发布后本课程学生可以查看和作答，请先核对题目与截止时间。':'关闭后学生将不能继续提交，已有作答与成绩会保留。' }}</p><p v-if="platformStatus" role="status" class="status">{{ platformStatus }}</p><template #footer><button type="button" :disabled="platformBusy" @click="pendingAssignmentStatus=null">取消</button><button type="button" :disabled="platformBusy" @click="updateAssignmentStatus(pendingAssignmentStatus)">{{ platformBusy?'正在处理…':'确认操作' }}</button></template></DetailDialog>
<AssignmentEditor v-if="assignmentEditingId && canManage" :key="user.id+assignmentEditingId" :assignment-id="assignmentEditingId" :request="request" @close="assignmentEditingId=null" @saved="assignmentEditorSaved" />
        <div v-if="selectedAssignment && !assignmentEditingId" class="assignment-modal" @click.self="closeAnswerDialog('assignment')">
          <section ref="assignmentDialog" class="assignment-sheet" :class="{ 'is-grading-workspace': user.role !== 'student','is-student-workspace':user.role==='student' }" role="dialog" aria-modal="true" aria-labelledby="assignment-dialog-title" tabindex="-1"><header><div><p class="section-kicker">{{ selectedAssignment.course_title }}</p><h2 id="assignment-dialog-title">{{ selectedAssignment.title }}</h2><p v-if="selectedAssignment.due_at" class="assignment-deadline">截止 {{ historyTime(selectedAssignment.due_at) }}</p></div><button aria-label="关闭作业" :disabled="gradingSaving || (user.role === 'student' && platformBusy)" @click="closeAnswerDialog('assignment')">{{ user.role==='student'?'返回':'×' }}</button></header>
            <StudentAssignmentWorkspace v-if="user.role==='student'" :key="user.id+selectedAssignment.id" :id="selectedAssignment.id" :questions="selectedAssignment.questions||[]" v-model:answers="assignmentAnswers" :submitted="selectedAssignment.submitted" :graded="selectedAssignment.submission_status==='graded'" :busy="platformBusy" :can-submit="selectedAssignment.status==='published'&&canSubmitAssignment(selectedAssignment)" :message="submissionMessage" :ai-policy="selectedAssignment.ai_policy" @assist="askAssignmentAssistant" @submit="submitLearningAssignment">
<template #notice><AnswerDraftNotice v-if="!selectedAssignment.submitted" :saved-at="assignmentDraft.savedAt.value" :restored="assignmentDraft.restored.value" :pending="assignmentDraft.pending.value" :error="assignmentDraft.error.value" :previous-version="assignmentDraft.previousVersion.value" :other-page="assignmentDraft.otherPage.value" @retry="assignmentDraft.persist()" @discard="assignmentDraft.discard()" @overwrite="assignmentDraft.persist(true)" @restore-other="assignmentDraft.restoreOtherPage()" /><div v-if="draftCloseWarning==='assignment'" class="answer-exit-warning" role="alert"><p>答案未能暂存，请先复制留存。</p><button type="button" @click="draftCloseWarning=null">继续填写</button><button type="button" @click="closeAnswerDialog('assignment',true)">放弃未暂存内容并关闭</button></div><p v-if="assignmentIsOverdue(selectedAssignment)&&!selectedAssignment.submitted&&canSubmitAssignment(selectedAssignment)" class="late-approved-note" role="status">补交已批准，可在有效期内完成并提交。</p><section v-if="assignmentIsOverdue(selectedAssignment)&&!selectedAssignment.submitted&&!canSubmitAssignment(selectedAssignment)" class="late-request-box"><strong>{{ selectedAssignment.late_request_status==='pending'?'补交申请等待教师审批':'作业已截止，请查看补交安排' }}</strong><p v-if="selectedAssignment.late_request_status==='approved'">补交批准已过期，可重新申请。</p><p v-else-if="selectedAssignment.late_request_status==='rejected'">上次申请未通过，可补充说明后重新申请。</p><textarea v-if="selectedAssignment.late_request_status!=='pending'" v-model="lateRequestReason" placeholder="说明逾期原因和计划完成时间" /><button v-if="selectedAssignment.late_request_status!=='pending'" :disabled="platformBusy||lateRequestReason.trim().length<2" @click="requestLateSubmission">提交补交申请</button></section></template>
              <template #feedback><section class="assignment-submission-state"><strong>{{ selectedAssignment.submission_status==='graded'?`已批改 · ${selectedAssignment.score}/${selectedAssignment.max_score} 分`:'已提交 · 待教师批改' }}</strong><p>{{ selectedAssignment.teacher_feedback || (selectedAssignment.submission_status==='graded'?'可切换到作答回看，查看每道题的解析。':'最终成绩与参考答案将在教师批改后显示。') }}</p></section><section v-if="assignmentPublishedReview&&!assignmentPublishedReview.stale" class="assignment-review-result"><h3>{{ assignmentPublishedReview.title }}</h3><RichText :source="assignmentPublishedReview.content" :tools="false" /></section></template>
            </StudentAssignmentWorkspace>
            <nav v-if="user.role !== 'student'" class="assignment-manager-tabs" aria-label="教师作业视图"><button type="button" :aria-pressed="assignmentManagerPane === 'overview'" :class="{ active: assignmentManagerPane === 'overview' }" @click="assignmentManagerPane = 'overview'">作业概览</button><button type="button" :aria-pressed="assignmentManagerPane === 'grading'" :class="{ active: assignmentManagerPane === 'grading' }" @click="assignmentManagerPane = 'grading'">学生作答与批改</button><button type="button" :aria-pressed="assignmentManagerPane === 'questions'" :class="{ active: assignmentManagerPane === 'questions' }" @click="assignmentManagerPane = 'questions'">题目与参考</button><button type="button" :aria-pressed="assignmentManagerPane === 'review'" :class="{ active: assignmentManagerPane === 'review' }" @click="assignmentManagerPane = 'review'">作业讲评</button><button type="button" :aria-pressed="assignmentManagerPane === 'settings'" :class="{ active: assignmentManagerPane === 'settings' }" @click="assignmentManagerPane = 'settings'">发布与来源</button><span v-if="gradingDirty" class="grading-unsaved-badge">有未保存批改</span></nav>
            <div v-if="user.role!=='student'" class="assignment-dialog-body" :class="{ 'is-grading': assignmentManagerPane === 'grading' }">
            <section v-if="assignmentManagerPane==='overview'" class="assignment-overview"><span class="assignment-overview-state">{{ selectedAssignment.status==='draft'?'草稿待核对':selectedAssignment.status==='closed'?'已关闭提交':'已发布' }}</span><h3>{{ selectedAssignment.course_title }}</h3><p>{{ selectedAssignment.description || '从提交情况开始，继续本次教学任务。' }}</p><div class="assignment-overview-metrics"><span><b>{{ selectedAssignment.question_count }}</b>道题目</span><span><b>{{ assignmentSubmissions.length }}</b>份提交</span><span><b>{{ assignmentSubmissions.filter(x=>x.status!=='graded').length }}</b>份待批改</span></div><div class="inline-actions"><button type="button" @click="assignmentManagerPane='grading'">进入学生作答与批改</button><button type="button" class="ghost-button" @click="assignmentManagerPane='questions'">核对题目</button><button type="button" class="ghost-button" @click="assignmentManagerPane='review'">准备讲评</button><button type="button" class="ghost-button" @click="assignmentManagerPane='settings'">发布与设置</button></div></section>
            <div v-if="user.role !== 'student'" v-show="assignmentManagerPane === 'grading'" class="assignment-grading-pane">
              <GradingWorkspace :key="selectedAssignment.id" :submissions="assignmentSubmissions" :selected="selectedSubmission" :questions="selectedAssignment.questions || []" :loading="assignmentSubmissionsLoading" :error="assignmentSubmissionsError" :busy="gradingSaving" @select="selectSubmissionById" @retry="reloadAssignmentSubmissions">
                <template #analysis><StudentAnswerAnalysisPanel v-if="selectedSubmission" :result="studentAnswerAnalysis" :busy="studentAnswerAnalysisBusy" :loading="studentAnswerAnalysisLoading" :error="studentAnswerAnalysisError" :student-name="selectedSubmission.student_name" :enabled="Boolean(modelStatus?.llm_configured && modelStatus.llm_provider !== 'offline') && !gradingSaving" :render-markdown="renderMarkdown" @generate="generateStudentAnswerAnalysis" @use-feedback="useStudentAnalysisFeedback" @open-draft="openStudentAnalysisDraft" /><p v-if="studentAnswerTaskMessage" role="status">{{ studentAnswerTaskMessage }}</p><AssistantTaskPanel :request="request" :refresh="assistantTasksRevision" @open-draft="openCohortDraft" @open-work="openTeachingWorkbench('history','',$event)" /></template>
                <template #grade>
                  <section v-if="selectedSubmission" class="grade-editor grading-score-editor">
                    <div class="grade-edit-fields">
                      <EditorDraftNotice :restored="gradingDraft.restored.value" :saved-at="gradingDraft.savedAt.value" :error="gradingDraft.error.value" :recovery="!!gradingDraft.recovery.value" :changed-elsewhere="gradingDraft.changedElsewhere.value" @recover="recoverGradeDraft" @keep="gradingDraft.keepCurrent" /><aside v-if="gradingRemoteChanged" class="grading-version-conflict" role="alert"><strong>服务器最新记录：{{ gradingRemoteChanged.score }}/{{ gradingRemoteChanged.max_score }} 分</strong><p>{{ gradingRemoteChanged.feedback || '暂无评语' }}</p><button type="button" :disabled="gradingSaving" @click="acceptRemoteGrade(false)">采用服务器记录</button><button type="button" :disabled="gradingSaving" @click="acceptRemoteGrade(true)">对照后保留本机编辑</button></aside><button v-if="gradingResultUnknown" type="button" :disabled="gradingSaving" @click="reconcileGrading">核对服务器记录</button>
                      <h3>成绩与评语</h3>
                      <p class="grading-saved-score">当前记录 <strong>{{ selectedSubmission.score }} / {{ selectedSubmission.max_score }}</strong><span>{{ selectedSubmission.status === 'graded' ? '已批改' : '待批改' }}</span></p>
                      <label>最终成绩<input v-model.number="gradeScore" type="number" min="0" :max="selectedSubmission.max_score" step="any" :disabled="gradingSaving" /></label>
                      <FeedbackReplaceConfirm v-if="pendingStudentFeedback" :previous="pendingStudentFeedback.previous" :proposed="pendingStudentFeedback.value" :busy="platformBusy" @confirm="confirmStudentFeedback" @cancel="pendingStudentFeedback = null" />
                      <label>教师评语<textarea v-model="gradeFeedback" maxlength="5000" :disabled="gradingSaving" placeholder="写下具体的改进建议或评价" /></label>
                      <small class="grading-feedback-count">{{ gradeFeedback.length }} / 5000 字符</small>
                      <p v-if="!gradeValid" class="grading-validation" role="alert">成绩应在0至{{ selectedSubmission.max_score }}之间，评语不超过5000字符。</p>
                    </div>
                    <div class="grade-edit-actions"><p :class="{ 'has-changes': gradingDirty }" role="status">{{ gradingSaving ? '正在保存，请稍候…' : gradingDirty ? '有未保存修改' : '未修改当前记录' }}</p><button type="button" :disabled="platformBusy || gradingResultUnknown || !!gradingRemoteChanged || !!gradingDraft.recovery.value || gradingDraft.changedElsewhere.value || !gradeValid || (!gradingDirty && selectedSubmission.status === 'graded')" @click="gradeSubmission">{{ gradingSaving ? '正在保存…' : '保存批改' }}</button><p v-if="submissionMessage" class="grading-save-message" role="status">{{ submissionMessage }}</p></div>
                  </section>
                </template>
              </GradingWorkspace>
            </div>
            <section v-if="user.role !== 'student' && assignmentManagerPane === 'questions'" class="assignment-reference-pane"><h3>题目与参考解析</h3><PagedList :items="selectedAssignment.questions || []" :page-size="5" label="作业题目" v-slot="{ items: referenceQuestions, page: referencePage, pageSize: referenceSize }"><article v-for="(item, index) in referenceQuestions" :key="item.id" class="assignment-readonly-question"><small>题目 {{ (referencePage - 1) * referenceSize + index + 1 }}</small><RichText :source="item.stem" :tools="false" /><ul v-if="item.options.length"><li v-for="option in item.options" :key="option">{{ option }}</li></ul><details><summary>查看参考答案与解析</summary><RichText :source="item.correct_answer || '未提供参考答案'" :tools="false" /><RichText v-if="item.explanation" :source="item.explanation" :tools="false" /></details></article></PagedList></section>
            <div v-if="user.role !== 'student' && assignmentManagerPane === 'settings'" class="assignment-toolbar"><span>状态：{{ selectedAssignment.status === 'published' ? '已发布' : selectedAssignment.status === 'closed' ? '已关闭' : '草稿' }}</span><button v-if="selectedAssignment.source_draft_id" class="ghost-button" @click="openAssignmentSourceDraft">查看来源草稿与本批回看 ↗</button><button v-if="selectedAssignment.status === 'draft'" :disabled="platformBusy" @click="assignmentEditingId=selectedAssignment.id">核对完成，发布给课程学生</button><button v-if="selectedAssignment.status === 'published'" :disabled="platformBusy" class="danger-soft" @click="pendingAssignmentStatus='closed'">关闭提交</button><button type="button" :disabled="platformBusy" @click="assignmentEditingId=selectedAssignment.id">{{ selectedAssignment.status==='draft'?'编辑题目、分值与辅助规则':'版本与修订草稿' }}</button></div>
            <section v-if="user.role !== 'student' && assignmentManagerPane === 'review'" class="assignment-review-workflow">
              <div><p class="section-kicker">TEACHING REVIEW</p><h3>作业讲评</h3><AssistantTaskPanel :request="request" :refresh="assistantTasksRevision" @open-draft="openCohortDraft" @open-work="openTeachingWorkbench('history','',$event)" /><p>AI 可结合学生姓名、具体作答和教师评语分析错误原因，不再局限于匿名统计。生成的班级讲评先由教师核对，再决定发布。</p><small>{{ assignmentSubmissions.length }} 份提交 · {{ assignmentSubmissions.filter(item => item.status !== 'graded').length }} 份待批改</small></div>
              <button type="button" :disabled="assignmentReviewBusy || !assignmentSubmissions.length" @click="generateAssignmentReview(true)">{{ assignmentReviewBusy ? '正在整理…' : '仅用站内统计生成提纲' }}</button>
              <p v-if="modelStatus?.llm_provider && modelStatus.llm_provider !== 'offline'" class="draft-ai-message">点击 AI 讲评将发送本次作业题目、所覆盖学生的姓名和作答用于分析；最多覆盖 30 份提交、12 道题，草稿标明实际范围。</p>
              <button v-if="modelStatus?.llm_provider && modelStatus.llm_provider !== 'offline'" type="button" :disabled="assignmentReviewBusy || !assignmentSubmissions.length || !modelStatus.llm_configured" @click="generateAssignmentReview(false)">{{ assignmentReviewBusy ? '正在分析作答并准备讲评…' : 'AI 分析学生作答并生成讲评' }}</button>
              <p v-if="assignmentReviewMessage" class="draft-ai-message">{{ assignmentReviewMessage }}</p>
            </section>
            <section v-if="assignmentPublishedReview && (user.role === 'student' || assignmentManagerPane === 'review')" class="assignment-review-result"><div class="assignment-review-result-head"><div><p class="section-kicker">TEACHER FEEDBACK</p><h3>{{ assignmentPublishedReview.title }}</h3><small>教师确认并发布 · {{ historyTime(assignmentPublishedReview.published_at) }}</small></div><span v-if="assignmentPublishedReview.stale" class="status-badge status-processing">提交或批改已变化</span><button v-if="user.role !== 'student' && !assignmentPublishedReview.stale" type="button" class="ghost-button" :disabled="platformBusy" @click="reviseAssignmentReview(assignmentPublishedReview.draft_id)">修订这份讲评 ↗</button></div><p v-if="assignmentPublishedReview.stale" class="draft-ai-message">这份讲评已不对应当前作业统计，学生端暂时不可见。请重新生成、核对并发布。</p><div class="answer-markdown" v-html="renderMarkdown(assignmentPublishedReview.content)" /></section>
            </div><footer v-if="user.role!=='student'"><span>{{ selectedAssignment.question_count }} 道题<span v-if="selectedAssignment.due_at"> · 截止 {{ historyTime(selectedAssignment.due_at) }}</span></span></footer>
          </section>
          <GradingLeaveConfirm v-if="pendingGradingExit" :student-name="selectedSubmission?.student_name || '当前学生'" :action-label="pendingGradingExit.label" @cancel="pendingGradingExit = null" @discard="discardGradingAndContinue" @stash="stashGradingAndContinue" />
        </div>
        <DetailDialog v-if="selectedLearningSection" :title="selectedLearningSection.section.section_title" :description="selectedLearningSection.report.course_title" kicker="SECTION DETAIL" close-label="关闭章节详情" size="small" @close="selectedLearningSection = null"><div class="section-detail-metrics"><span><small>章节作业进度</small><strong>{{ selectedLearningSection.section.progress_percent }}%</strong></span><span><small>知识掌握度</small><strong>{{ selectedLearningSection.section.mastery_percent }}%</strong></span></div><div class="progress-track"><i :style="{ width: `${selectedLearningSection.section.progress_percent}%` }" /></div><template #footer><button type="button" class="ghost-button" @click="selectedLearningSection = null">返回学习报告</button><button type="button" @click="openProgressCourse(selectedLearningSection.report.course_id)">查看课程大纲与资料 ↗</button></template></DetailDialog>
        <div v-if="selectedPractice" class="assignment-modal" @click.self="closeAnswerDialog('practice')">
          <section ref="practiceDialog" class="assignment-sheet practice-dialog" role="dialog" aria-modal="true" aria-labelledby="practice-dialog-title" tabindex="-1">
            <header><div><p class="section-kicker">{{ selectedPractice.source === 'wrong_question' ? 'WRONG QUESTION RETRY' : 'QUESTION PRACTICE' }}</p><h2 id="practice-dialog-title">{{ selectedPractice.source === 'wrong_question' ? '错题再练' : '题目练习' }}</h2><p>{{ questionTypeLabel(selectedPractice.question.question_type) }} · 难度 {{ selectedPractice.question.difficulty }}</p></div><button aria-label="关闭练习" :disabled="platformBusy" @click="closeAnswerDialog('practice')">×</button></header>
            <AnswerDraftNotice v-if="user.role === 'student' && (!practiceResults[selectedPractice.question.id] || practiceDraft.savedAt.value || practiceDraft.pending.value || practiceDraft.error.value)" :key="selectedPractice.question.id"
              :saved-at="practiceDraft.savedAt.value" :restored="practiceDraft.restored.value" :pending="practiceDraft.pending.value"
              :error="practiceDraft.error.value" :previous-version="practiceDraft.previousVersion.value" :other-page="practiceDraft.otherPage.value"
              @retry="practiceDraft.persist()" @discard="practiceDraft.discard()" @overwrite="practiceDraft.persist(true)" @restore-other="practiceDraft.restoreOtherPage()" />
            <div v-if="draftCloseWarning === 'practice'" class="answer-exit-warning" role="alert"><strong>当前答案未能暂存，请先复制留存。</strong><p>仍然关闭将丢失本页尚未保存的内容。</p><button type="button" @click="draftCloseWarning = null">继续填写</button><button type="button" class="danger-soft" @click="closeAnswerDialog('practice', true)">放弃未暂存内容并关闭</button></div>
            <article class="practice-card"><h3>{{ selectedPractice.question.stem }}</h3>
              <div v-if="selectedPractice.question.question_type === 'multiple_choice'" class="practice-options"><label v-for="option in selectedPractice.question.options" :key="option"><input type="checkbox" :disabled="platformBusy || practiceCoachBusy" :checked="answerValues(practiceAnswers, selectedPractice.question.id).includes(option)" @change="toggleAnswer(practiceAnswers, selectedPractice.question.id, option)" />{{ option }}</label></div>
              <div v-else-if="selectedPractice.question.options.length" class="practice-options"><label v-for="option in selectedPractice.question.options" :key="option"><input v-model="practiceAnswers[selectedPractice.question.id]" type="radio" :disabled="platformBusy || practiceCoachBusy" :name="`dialog-${selectedPractice.question.id}`" :value="option" />{{ option }}</label></div>
              <textarea v-else v-model="practiceAnswers[selectedPractice.question.id]" :disabled="platformBusy || practiceCoachBusy" :placeholder="selectedPractice.question.question_type === 'fill_blank' ? '依次填写答案，多个空用 || 分隔' : '输入你的答案和思路'" />
              <div v-if="practiceResults[selectedPractice.question.id]" :class="['practice-feedback', practiceResults[selectedPractice.question.id].is_correct === null ? 'pending' : practiceResults[selectedPractice.question.id].is_correct === false ? 'incorrect' : 'correct']"><strong>{{ practiceResults[selectedPractice.question.id].message }}</strong><p><b>相关知识点：</b>{{ selectedPractice.question.knowledge_point || '综合知识' }}</p><p v-if="practiceResults[selectedPractice.question.id].correct_answer"><b>参考答案：</b>{{ practiceResults[selectedPractice.question.id].correct_answer }}</p><p v-if="practiceResults[selectedPractice.question.id].explanation"><b>解析：</b>{{ practiceResults[selectedPractice.question.id].explanation }}</p></div>
              <footer><span /><button :disabled="platformBusy || practiceCoachBusy || (!practiceResults[selectedPractice.question.id] && !hasAnswer(practiceAnswers[selectedPractice.question.id]))" @click="practiceResults[selectedPractice.question.id] ? openQuestionPractice(selectedPractice.question, selectedPractice.source, selectedPractice.retry_count + 1) : submitPractice(selectedPractice)">{{ platformBusy ? '正在提交…' : practiceResults[selectedPractice.question.id] ? '再练本题' : '提交答案' }}</button></footer>
            </article>
            <PracticeFeedbackPanel v-if="user.role === 'student'" :key="`${user.id}:${selectedPractice.question.id}`" :question-id="selectedPractice.question.id" :attempt-id="practicePlanAttemptId || practiceResults[selectedPractice.question.id]?.attempt_id" :enabled="Boolean(modelStatus?.llm_configured && modelStatus.llm_provider !== 'offline')" :assistant-busy="globalAssistantBusy" :request="request" :render-markdown="renderMarkdown" @busy="practiceCoachBusy = $event" @practice="openQuestionPractice($event)" @explain="explainPracticeTopic" @plan="openPracticeStudyPlan" />
          </section>
        </div>
      </section>

      <section v-if="user.role === 'admin' && visitedPages.has('admin')" v-show="activePage === 'admin'" class="module-page">
        <div class="page-intro"><div><h2>管理控制台</h2><p>集中管理用户、模型服务、文档任务、评测和运行日志。</p></div></div>
        <div class="learning-tabs admin-tabs">
          <button :class="{ active: adminTab === 'overview' }" @click="adminTab = 'overview'">平台概览</button>
          <button :class="{ active: adminTab === 'tasks' }" @click="openAdminTaskCenter('jobs')">助手任务</button>
          <button :class="{ active: adminTab === 'users' }" @click="adminTab = 'users'">用户管理</button>
          <button type="button" @click="openAccountManagement()">注册与邀请</button>
          <button :class="{ active: adminTab === 'model' }" @click="adminTab = 'model'">模型与 RAG</button>
          <button :class="{ active: adminTab === 'quotas' }" @click="adminTab = 'quotas'">调用额度</button>
          <button :class="{ active: adminTab === 'evaluation' }" @click="adminTab = 'evaluation'">质量评测</button>
          <button :class="{ active: adminTab === 'security' }" @click="adminTab = 'security'">安全与运行</button>
          <button :class="{ active: adminTab === 'audit' }" @click="adminTab = 'audit'">审计日志</button>
        </div>
        <p v-if="platformStatus" class="platform-message">{{ platformStatus }}</p>
        <div v-show="adminTab === 'overview'">
          <section class="panel admin-insight-panel"><div class="panel-heading"><div><p class="section-kicker">MANAGEMENT ASSISTANT</p><h2>待处理事项</h2><p>依据当前平台数据生成，点击卡片进入对应模块。</p></div><div class="inline-actions"><span class="count-label">{{ adminInsights.length }} 项</span><button type="button" :disabled="adminReportBusy" @click="loadAdminReport(1)">生成今日巡检</button></div></div><div class="admin-insight-grid"><button v-for="action in adminInsights" :key="action.id" type="button" class="assistant-action-card" :class="`tone-${action.tone}`" @click="runAssistantAction(action)"><span>{{ action.eyebrow }}</span><div><strong>{{ action.title }}</strong><small>{{ action.detail }}</small></div><b>{{ action.button }} ›</b></button></div></section>
          <div class="metric-grid admin-metrics">
            <article><span>用户</span><strong>{{ adminMetrics?.user_count ?? 0 }}</strong><small>全部角色账号</small></article>
            <article><span>课程</span><strong>{{ adminMetrics?.course_count ?? 0 }}</strong><small>教学空间</small></article>
            <article><span>资料 / 索引</span><strong>{{ adminMetrics?.document_count ?? 0 }} / {{ adminMetrics?.indexed_chunk_count ?? 0 }}</strong><small>文档与检索片段</small></article>
            <article><span>题目 / 作业</span><strong>{{ adminMetrics?.question_count ?? 0 }} / {{ adminMetrics?.assignment_count ?? 0 }}</strong><small>教学活动</small></article>
          </div>
          <div class="dashboard-grid"><section class="panel admin-summary"><p class="section-kicker">RAG SERVICE</p><h2>AI 与检索服务</h2><div><span>生成模型<b>{{ modelStatus?.llm_model }}</b></span><span>服务状态<b>{{ modelStatus?.llm_configured ? '在线已配置' : '离线回退' }}</b></span><span>Embedding<b>{{ modelStatus?.embedding_provider }}</b></span><span>问答记录<b>{{ adminMetrics?.rag_question_count ?? 0 }}</b></span></div></section><section class="panel admin-summary"><p class="section-kicker">DOCUMENT PIPELINE</p><h2>文档处理状态</h2><div><span>知识库<b>{{ adminMetrics?.knowledge_base_count ?? 0 }}</b></span><span>就绪文档<b>{{ adminMetrics?.document_status.ready ?? 0 }}</b></span><span>异常文档<b>{{ adminMetrics?.document_status.error ?? 0 }}</b></span><span>平均反馈<b>{{ adminMetrics?.average_feedback || '—' }}</b></span></div></section></div>
          <section class="panel job-panel"><div class="panel-heading"><div><p class="section-kicker">INGESTION QUEUE</p><h2>最近文档任务</h2></div><span class="count-label">处理记录</span></div><PagedList class="job-list" :items="documentJobs" :page-size="8" :load-page="pageLoader<DocumentJob>('jobs')" label="文档任务" v-slot="{ items: jobItems }"><article v-for="job in jobItems" :key="job.id"><div><strong>{{ job.filename }}</strong><small>{{ historyTime(job.created_at) }} · 第 {{ job.attempts }} 次处理<span v-if="job.error_message"> · {{ job.error_message }}</span></small></div><span :class="`status-badge status-${job.status}`">{{ job.status === 'completed' ? '已完成' : job.status === 'failed' ? '失败' : job.status === 'cancelled' ? '已取消' : job.status === 'processing' ? `处理中 ${job.progress_percent}%` : '排队中' }}</span><button v-if="['failed','cancelled'].includes(job.status)" :disabled="platformBusy" @click="retryDocumentJob(job)">重试</button><button v-if="['queued','processing'].includes(job.status)" type="button" :disabled="platformBusy" @click="cancelDocumentJob(job)">取消处理</button></article><p v-if="!jobItems.length" class="empty-state">暂无文档处理任务。</p></PagedList></section>
        </div>
        <div v-if="visitedAdminTabs.has('tasks')" v-show="adminTab === 'tasks'"><AdminTaskCenter :key="user.id" :request="request" :focus="adminTaskFocus" :focus-revision="adminTaskFocusRevision" @changed="refreshAdminTaskSummary" @settings="adminTab = 'model'" @users="adminTab = 'users'" /></div>
        <section v-if="visitedAdminTabs.has('quotas')" v-show="adminTab === 'quotas'" class="panel model-quota-page">
          <div class="panel-heading"><div><p class="section-kicker">DAILY AI QUOTAS</p><h2>每日 AI 调用额度</h2><p>按用户角色设置每人每天可发起的在线模型请求次数。</p></div></div>
          <div class="model-quota-grid">
            <article v-for="item in modelQuotas" :key="item.role">
              <div><strong>{{ item.role === 'student' ? '学生' : item.role === 'teacher' ? '教师' : '管理员' }}</strong><small>每人每天</small></div>
              <input v-model.number="modelQuotaDrafts[item.role]" type="number" min="1" max="100000" :aria-label="`设置${item.role === 'student' ? '学生' : item.role === 'teacher' ? '教师' : '管理员'}每日模型额度`" />
              <span>次</span>
              <button :disabled="platformBusy" @click="saveModelQuota(item)">保存额度</button>
            </article>
          </div>
          <p class="config-note">额度按 UTC 日期归零。超额请求会明确提示，不会调用在线模型。</p>
        </section>
        <div v-if="visitedAdminTabs.has('users')" v-show="adminTab === 'users'" class="admin-split">
          <section class="panel admin-table-panel">
            <div class="panel-heading"><div><p class="section-kicker">USERS</p><h2>平台用户</h2></div><span class="count-label">{{ adminMetrics?.user_count ?? 0 }} 人</span></div>
            <form class="directory-toolbar user-directory-toolbar" @submit.prevent="searchAdminUsers">
              <label class="directory-keyword">搜索用户<input v-model="adminUserKeyword" type="search" maxlength="100" placeholder="姓名或登录账号" /></label>
              <label>用户角色<select v-model="adminUserRole"><option value="all">全部角色</option><option value="student">学生</option><option value="teacher">教师</option><option value="admin">管理员</option></select></label>
              <label>账号状态<select v-model="adminUserFilter"><option value="all">全部状态</option><option value="active">正常账号</option><option value="inactive">已停用账号</option></select></label>
              <div class="directory-filter-actions"><button type="submit">搜索</button><button type="button" class="ghost-button" @click="resetAdminUserSearch">重置</button></div>
            </form>
            <PagedList class="admin-user-list" :items="adminUsers" :scope="adminUserScope" :load-page="loadAdminUserPage" label="平台用户" v-slot="{ items: userItems, loading: usersLoading, error: usersError }"><article v-for="item in userItems" :key="item.id">
              <span class="account-avatar">{{ item.display_name.slice(0, 1) }}</span>
              <div><strong>{{ item.display_name }}</strong><small>{{ item.username }} · {{ item.role === 'admin' ? '管理员' : item.role === 'teacher' ? '教师' : '学生' }}</small></div>
              <b :class="{ disabled: !item.active }">{{ item.active ? '正常' : '已停用' }}</b>
              <div class="admin-user-controls"><select :value="pendingRoleChanges[item.id] || item.role" :disabled="platformBusy || item.id === user.id" :aria-label="`修改 ${item.display_name} 的角色`" @change="pendingRoleChanges[item.id] = ($event.target as HTMLSelectElement).value as AdminUser['role']"><option value="student">学生</option><option value="teacher">教师</option><option value="admin">管理员</option></select><button :disabled="platformBusy || item.id === user.id || !pendingRoleChanges[item.id] || pendingRoleChanges[item.id] === item.role" @click="requestAdminRoleChange(item)">修改角色</button><button :disabled="platformBusy || item.id === user.id" @click="toggleAdminUser(item)">{{ item.active ? '停用' : '启用' }}</button></div>
            </article><div v-if="!usersLoading && !usersError && !userItems.length" class="directory-empty"><strong>没有符合条件的用户</strong><p>请检查姓名、账号或筛选条件。</p><button type="button" class="ghost-button" @click="resetAdminUserSearch">清除筛选</button></div></PagedList>
          </section>
          <section class="panel admin-form"><p class="section-kicker">CREATE USER</p><h2>创建用户</h2><label>登录账号<input v-model="newUserName" autocomplete="off" placeholder="用于登录系统" /></label><label>显示名称<input v-model="newUserDisplayName" placeholder="姓名或显示名称" /></label><label>用户角色<select v-model="newUserRole"><option value="student">学生</option><option value="teacher">教师</option><option value="admin">管理员</option></select></label><label>初始密码<input v-model="newUserPassword" type="password" autocomplete="new-password" placeholder="至少 8 位" /></label><button :disabled="platformBusy || !newUserName.trim() || !newUserDisplayName.trim() || newUserPassword.length < 8" @click="createAdminUser">创建账号</button></section>
        </div>
        <section v-if="visitedAdminTabs.has('model') && adminModelConfig" v-show="adminTab === 'model'" class="model-admin-page"><div v-if="modelUsageOverview" class="metric-grid admin-metrics model-usage-metrics"><article><span>平台 AI 请求</span><strong>{{ modelUsageOverview.total_calls }}</strong><small>近 {{ modelUsageOverview.days }} 天 · 已记录上游 {{ modelUsageOverview.recorded_upstream_requests }} 次尝试 · {{ modelUsageOverview.upstream_untracked_requests }} 条未细分</small></article><article><span>成功率</span><strong>{{ modelUsageOverview.success_rate }}%</strong><small>{{ modelUsageOverview.failed_calls }} 次失败</small></article><article><span>Token 统计</span><strong>{{ (modelUsageOverview.input_tokens + modelUsageOverview.output_tokens).toLocaleString() }}</strong><small>输入 {{ modelUsageOverview.input_tokens.toLocaleString() }} / 输出 {{ modelUsageOverview.output_tokens.toLocaleString() }}</small></article><article><span>平均耗时</span><strong>{{ Math.round(modelUsageOverview.average_duration_ms) }} ms</strong><small>在线生成请求</small></article></div><section class="panel model-config-panel"><div class="panel-heading"><div><p class="section-kicker">MODEL & RETRIEVAL</p><h2>模型与 RAG 参数</h2></div><span class="model-status" :class="{ online: adminModelConfig.configured }">{{ adminModelConfig.configured ? '在线可用' : '离线模式' }}</span></div><div class="config-grid"><label>生成服务<select v-model="adminModelConfig.provider"><option value="offline">离线证据回答</option><option value="compatible">OpenAI 兼容接口（千问等）</option><option value="openai">OpenAI 官方接口</option></select></label><label>模型名称<input v-model="adminModelConfig.model" /></label><label>接口地址<input v-model="adminModelConfig.api_base" /></label><label>API Key<input v-model="modelApiKey" type="password" placeholder="留空则保留当前配置" /></label><label>检索数量<input v-model.number="adminModelConfig.retrieval_top_k" type="number" min="1" max="20" /></label><label>最低置信度<input v-model.number="adminModelConfig.retrieval_min_score" type="number" min="0" max="1" step="0.05" /></label><label>向量权重<input v-model.number="adminModelConfig.retrieval_vector_weight" type="number" min="0" max="1" step="0.05" /></label><label>超时时间（秒）<input v-model.number="adminModelConfig.timeout_seconds" type="number" min="3" max="300" /></label><label class="check-label"><input v-model="adminModelConfig.fallback_offline" type="checkbox" />在线失败时回退离线证据回答</label></div><div class="config-note">Embedding：{{ adminModelConfig.embedding_provider }} · {{ adminModelConfig.embedding_model }}。设置保存到数据库，新填入的 API Key 加密保存且不会通过查询接口返回；工具问答优先使用服务方回报，缺失时估算；其他记录仍可能为估算。平台额度按一次用户操作计额，多步上游尝试另记，旧记录不猜测补算。</div><button :disabled="platformBusy" @click="saveModelConfig">保存并即时应用</button></section><section v-if="modelUsageOverview" class="panel model-usage-list"><div class="panel-heading"><div><p class="section-kicker">MODEL ACTIVITY</p><h2>平台请求与模型用量</h2></div><span class="count-label">一次平台请求可能包含多步上游尝试</span></div><PagedList class="job-list" :items="modelUsageOverview.recent" :load-page="pageLoader<ModelUsageOverview['recent'][number]>('model-calls')" label="平台 AI 请求" v-slot="{ items: callItems }"><article v-for="item in callItems" :key="item.id"><div><strong>{{ item.feature }} · {{ item.role }}</strong><small>{{ item.model }} · {{ item.tokens }} Token · {{ Math.round(item.duration_ms) }} ms · {{ historyTime(item.created_at) }}</small><small v-if="item.usage_detail">上游尝试 {{ item.usage_detail.upstream_requests }} 次 · {{ item.usage_detail.token_source === 'provider' ? 'Token 为服务方回报' : item.usage_detail.token_source === 'mixed' ? 'Token 含估算' : 'Token 估算' }}</small><small v-else>未记录上游细分次数 · Token 按原估算口径</small></div><span :class="`status-badge status-${item.successful ? 'completed' : 'failed'}`">{{ item.successful ? '成功' : item.error_type || '失败' }}</span></article><p v-if="!callItems.length" class="empty-state">尚无模型调用记录，新产生的问答和教学草稿会显示在这里。</p></PagedList></section></section>
        <section v-if="visitedAdminTabs.has('evaluation')" v-show="adminTab === 'evaluation'" class="evaluation-page"><EvaluationWorkbench :base="apiBase" :token="token" /></section>
        <section v-if="visitedAdminTabs.has('security') && securityOverview" v-show="adminTab === 'security'" class="security-page"><section class="panel"><DataExports :base="apiBase" :token="token" admin /></section>
          <div class="metric-grid admin-metrics"><article><span>失败登录</span><strong>{{ securityOverview.failed_logins_24h }}</strong><small>最近 24 小时</small></article><article><span>限流请求</span><strong>{{ securityOverview.rate_limited_requests_24h }}</strong><small>HTTP 429</small></article><article><span>服务异常</span><strong>{{ securityOverview.server_errors_24h }}</strong><small>HTTP 5xx</small></article><article><span>平均响应</span><strong>{{ securityOverview.average_duration_ms_24h }} ms</strong><small>最近 24 小时</small></article></div>
          <div class="security-grid"><section class="panel"><div class="panel-heading"><div><p class="section-kicker">LOGIN SECURITY</p><h2>登录事件</h2></div></div><PagedList class="security-list" :items="securityOverview.login_attempts" :load-page="pageLoader<SecurityOverview['login_attempts'][number]>('logins')" label="登录事件" v-slot="{ items: loginItems }"><article v-for="item in loginItems" :key="item.id"><span :class="item.successful ? 'security-ok' : 'security-fail'">{{ item.successful ? '成功' : '失败' }}</span><div><strong>{{ item.username }}</strong><small>{{ item.ip_address }} · {{ historyTime(item.created_at) }}</small></div></article><p v-if="!loginItems.length" class="empty-state">暂无登录事件。</p></PagedList></section>
          <section class="panel"><div class="panel-heading"><div><p class="section-kicker">REQUEST TRACE</p><h2>最近请求</h2></div></div><PagedList class="security-list request-log-list" :items="securityOverview.request_logs" :load-page="pageLoader<SecurityOverview['request_logs'][number]>('requests')" label="请求记录" v-slot="{ items: requestItems }"><article v-for="item in requestItems" :key="item.id"><span :class="item.status_code >= 400 ? 'security-fail' : 'security-ok'">{{ item.status_code }}</span><div><strong>{{ item.method }} {{ item.path }}</strong><small>{{ item.duration_ms }} ms · {{ item.request_id.slice(0, 8) }} · {{ historyTime(item.created_at) }}</small></div></article></PagedList></section></div>
        </section>
        <section v-if="visitedAdminTabs.has('audit')" v-show="adminTab === 'audit'" class="panel audit-panel"><div class="panel-heading"><div><p class="section-kicker">AUDIT LOG</p><h2>管理操作记录</h2></div><span class="count-label">全部操作记录</span></div><PagedList class="audit-list" :items="auditLogs" :load-page="pageLoader<AuditLog>('audits')" label="审计日志" v-slot="{ items: logItems }"><article v-for="item in logItems" :key="item.id"><span>{{ auditActionLabel(item.action) }}</span><div><strong>{{ item.actor_name }} · {{ auditResourceLabel(item.resource_type) }}</strong><small>{{ historyTime(item.created_at) }} · {{ item.resource_id || '全局配置' }}<template v-if="item.action === 'change_role'"> · {{ item.detail.from_role }} → {{ item.detail.to_role }}</template></small></div></article><p v-if="!logItems.length" class="empty-state">尚无管理操作记录。</p></PagedList></section>
      </section>

      <div v-if="visitedPages.has('tutor')" v-show="activePage === 'tutor' && tutorPane === 'materials'" class="tutor-shell tutor-materials-workspace">
    <header class="hero">
      <div>
        <p class="eyebrow">{{ tutorHeroKicker }}</p>
        <h2 class="tutor-hero-title">课程资料与来源</h2>
        <p class="subtitle">阅读教材与讲义，回看旧回答及引用。新的问答、备课和管理任务请进入“对话与工具”。</p>
      </div>
      <div class="hero-side">
        <div class="hero-metrics">
          <span>{{ knowledgeBases.length }} 个资料库</span>
          <span>{{ totalDocuments }} 本资料</span>
          <span v-if="isAdmin">{{ indexedChunks }} 个索引片段</span>
        </div>
      </div>
    </header>

    <button class="mobile-library-toggle" type="button" aria-controls="tutor-catalog" :aria-expanded="showMobileCatalog" @click="showMobileCatalog = !showMobileCatalog">
      <span><small>当前资料库</small><strong>{{ selectedKnowledgeBase?.name ?? '请选择资料库' }}</strong></span>
      <span>{{ showMobileCatalog ? '收起' : '切换' }} ▾</span>
    </button>
    <section class="workspace-grid">
      <aside id="tutor-catalog" class="panel catalog-panel" :class="{ 'mobile-open': showMobileCatalog }">
        <div class="panel-heading">
          <div>
            <p class="section-kicker">KNOWLEDGE BASES</p>
            <h2>课程资料库</h2>
          </div>
          <button v-if="canManage" class="icon-button" type="button" title="新建资料库" @click="showCreateForm = !showCreateForm">+</button>
        </div>

        <div v-if="loadingCatalog" class="empty-state">正在读取资料库…</div>
        <div v-else-if="!knowledgeBases.length" class="empty-state">还没有资料库，请先创建一个。</div>
        <PagedList v-else class="catalog-list" :items="knowledgeBases" :page-size="6" label="资料库" v-slot="{ items: baseItems }">
          <button
            v-for="item in baseItems"
            :key="item.id"
            class="catalog-item"
            :class="{ active: item.id === selectedKnowledgeBaseId }"
            type="button"
            @click="selectKnowledgeBase(item.id)"
          >
            <span class="catalog-dot" />
            <span class="catalog-copy">
              <strong>{{ item.name }}</strong>
              <small>{{ item.course }} · {{ item.document_count }} 本资料</small>
            </span>
            <span class="catalog-arrow">›</span>
          </button>
        </PagedList>
        <form v-if="showCreateForm" class="create-form" @submit.prevent="createKnowledgeBase">
          <input v-model="newKnowledgeBaseName" aria-label="资料库名称" placeholder="资料库名称" maxlength="200" required />
          <input v-model="newKnowledgeBaseCourse" aria-label="课程名称" placeholder="课程名称" maxlength="200" required />
          <textarea v-model="newKnowledgeBaseDescription" aria-label="资料库简介" placeholder="简介（可选）" rows="2" maxlength="2000" />
          <div class="form-actions">
            <button class="ghost-button" type="button" @click="showCreateForm = false">取消</button>
            <button type="submit" :disabled="busy">创建资料库</button>
          </div>
        </form>

        <div class="sidebar-guide">
          <p class="section-kicker">HOW IT WORKS</p>
          <strong>{{ user.role === 'teacher' ? '课程 → 草稿 → 审核' : user.role === 'admin' ? '状态 → 分析 → 确认' : '资料 → 检索 → 讲解' }}</strong>
          <span>{{ tutorGuideDescription }}</span>
          <div class="guide-steps">
            <span><b>01</b> {{ user.role === 'admin' ? '看状态' : '选课程' }}</span>
            <span><b>02</b> {{ user.role === 'teacher' ? '定目标' : '提问题' }}</span>
            <span><b>03</b> {{ user.role === 'student' ? '看证据' : '核建议' }}</span>
          </div>
        </div>
      </aside>

      <section class="main-column">
        <section v-if="canManage" class="panel upload-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">INGESTION</p>
              <h2>导入到当前资料库</h2>
              <p class="muted">{{ selectedKnowledgeBase?.name ?? '请先选择资料库' }} · 支持文字型 PDF</p>
            </div>
            <span class="live-pill"><span class="live-dot" />持久化索引</span>
          </div>
          <div class="upload-row">
            <label class="file-picker">
              <input type="file" accept="application/pdf" @change="chooseFile" />
              <span>{{ selectedFile?.name ?? '选择 PDF 文件' }}</span>
            </label>
            <button class="secondary" :disabled="!selectedFile || busy || !selectedKnowledgeBaseId || !canManage" @click="uploadPdf">{{ canManage ? '上传并索引' : '教师/管理员可导入' }}</button>
          </div>
          <div class="pipeline" aria-label="RAG 处理流程">
            <span class="pipeline-active">PDF 解析</span><i>→</i><span>章节分块</span><i>→</i><span>向量索引</span><i>→</i><span>混合检索</span>
          </div>
          <PagedList v-if="canManage" class="job-list compact" :items="documentJobs" :scope="selectedKnowledgeBaseId" :load-page="pageLoader<DocumentJob>('jobs', selectedKnowledgeBaseId)" :page-size="5" label="文档任务" v-slot="{ items: jobItems }"><article v-for="job in jobItems" :key="job.id"><div><strong>{{ job.filename }}</strong><small>第 {{ job.attempts }} 次 · {{ job.error_message || (job.status === 'completed' ? `${job.page_count} 页 / ${job.chunk_count} 个片段` : '后台处理中，可继续提问或浏览') }}</small><i><span :style="{ width: `${job.progress_percent}%` }" /></i></div><span :class="`status-badge status-${job.status}`">{{ job.status === 'completed' ? '已完成' : job.status === 'failed' ? '失败' : job.status === 'cancelled' ? '已取消' : job.status === 'processing' ? `${job.progress_percent}%` : '排队中' }}</span><button v-if="['failed','cancelled'].includes(job.status)" type="button" :disabled="busy" @click="retryDocumentJob(job)">重试</button><button v-if="['queued','processing'].includes(job.status)" type="button" :disabled="platformBusy" @click="cancelDocumentJob(job)">取消处理</button></article></PagedList>
        </section>

        <section class="panel documents-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">DOCUMENTS</p>
              <h2>资料清单</h2>
            </div>
            <span class="count-label">共 {{ documentTotal }} 份资料</span>
          </div>
          <PagedList v-if="selectedKnowledgeBaseId" class="document-list" :items="documents" :scope="selectedKnowledgeBaseId" :load-page="pageLoader<DocumentRecord>('documents', selectedKnowledgeBaseId)" label="资料清单" v-slot="{ items: documentItems }">
            <div v-for="document in documentItems" :key="document.id" class="document-row">
              <div class="document-icon">文</div>
              <button class="document-copy document-preview-button" type="button" @click="openDocumentPreview(document)">
                <strong>{{ document.name }}</strong>
                <span>版本 {{ document.version_label }} · {{ document.page_count ?? '—' }} 页 · {{ document.chunk_count }} 个文本块<span v-if="document.error_message"> · {{ document.error_message }}</span></span>
              </button>
              <span class="status-badge" :class="`status-${document.publication_status}`">{{ document.publication_status === 'published' ? '已发布' : document.publication_status === 'archived' ? '已归档' : '草稿' }}</span>
              <span class="status-badge" :class="`status-${document.status}`">{{ documentStatusLabel(document.status) }}</span>
              <button v-if="canManage" class="document-delete" type="button" :disabled="busy" title="移除文档" @click="deleteDocument(document)">×</button>
            </div>
            <div v-if="!documentItems.length" class="empty-state">当前资料库还没有文档。</div>
          </PagedList>
          <div v-else class="empty-state">请选择资料库。</div>
        </section>

        <section class="panel ask-panel">
          <div class="panel-heading ask-heading">
            <div>
              <p class="section-kicker">{{ tutorHeroKicker }}</p>
              <h2>资料库问答旧记录</h2>
              <p class="ask-lede">保留旧入口的回答和处理回执。新提问统一在助手中进行，课程与对话不会因切换入口而分开。</p>
            </div>
            <div class="ask-badges">
              <span v-if="selectedKnowledgeBase" class="current-library">{{ selectedKnowledgeBase.name }}</span>
              <span v-if="tutorRestoredScope?.course_id" class="current-library">{{ tutorRestoredScope.course_title || '原课程范围' }}</span>
              <span v-if="isAdmin" class="model-status" :class="{ online: modelStatus?.llm_configured }">{{ modelLabel }}</span>
              <button class="text-button" type="button" @click="openUnifiedAssistant">打开助手对话 ↗</button>
            </div>
          </div>
          <button v-if="busy" type="button" @click="stopAnswerGeneration()">停止上次生成</button>
          <p v-if="status" class="status">{{ status }}</p>
          <button v-if="!busy && tutorServerRequestId && (tutorRequestState === 'unknown' || tutorRequestState === 'in_progress')" type="button" class="stream-stop-button" :disabled="tutorReceiptBusy" @click="recoverTutorRequest">查看上次处理结果</button>
          <p v-if="tutorHistoryNotice" class="tutor-restored-notice" role="status">{{ tutorHistoryNotice }}<span v-if="answer && !answer.answer_mode"> 下一问：{{ answerModeLabel(answerMode) }}。</span></p>
          <AnswerRecoveryNotice v-if="user" :base="apiBase" :token="token" :owner="user.id" surface="tutor" :known-ids="tutorServerRequestId ? [tutorServerRequestId] : []" :busy="busy || tutorReceiptBusy || tutorHistoryBusy" @restore="restoreTutorRequest" />
        </section>

        <section class="panel history-panel">
          <div class="panel-heading">
            <div>
              <p class="section-kicker">RECENT QUESTIONS</p>
              <h2>最近问过</h2>
            </div>
            <span class="count-label">历史记录</span>
          </div>
          <p class="assistant-history-hint">仅展示当前可访问的回答。旧平台统计记录若缺少完整来源，会保留存档但不在此回读，可按当前课程重新查询。</p>
          <PagedList class="history-list" :items="history" :page-size="5" :scope="selectedKnowledgeBaseId" :load-page="pageLoader<HistoryItem>('history', selectedKnowledgeBaseId)" label="问答记录" v-slot="{ items: historyItems }">
            <button
              v-for="item in historyItems"
              :key="item.id"
              class="history-row"
              type="button"
              :disabled="busy || tutorReceiptBusy"
              @click="restoreHistory(item)"
            >
              <span class="history-status" :class="{ accepted: item.accepted }">{{ item.accepted ? '✓' : '!' }}</span>
              <span class="history-copy">
                <strong>{{ item.question }}</strong>
                <small>{{ historyTime(item.created_at) }} · {{ answerModeLabel(item.answer_mode) }} · {{ item.citations.length }} 条证据</small>
              </span>
              <span class="catalog-arrow">›</span>
            </button>
            <p v-if="!historyItems.length" class="empty-state">提问后，这里会保留当前资料库的记录。</p>
          </PagedList>
        </section>

        <section v-if="busy && answerDraft" class="panel answer-panel stream-preview" aria-label="正在生成的回答" aria-busy="true">
          <div class="stream-status"><span class="assistant-typing-dots" aria-hidden="true"><i /><i /><i /></span><strong>AI 正在解答</strong><small>生成中 · 完成后可查看引用与收藏</small></div>
          <RichText :source="answerDraft" streaming />
        </section>
        <section v-if="answer" class="result-grid">
          <article class="panel answer-panel">
            <div class="result-heading">
              <div>
                <p class="section-kicker">{{ !answer.answer_mode ? 'SAVED ANSWER' : answer.answer_mode === 'general' ? 'GENERAL ANSWER' : answer.answer_mode === 'hybrid' ? 'HYBRID ANSWER' : 'GROUNDED ANSWER' }}</p>
                <h2>回答</h2>
              </div>
              <div class="result-tags">
                <span class="mode-tag">{{ answerModeLabel(answer.answer_mode) }}</span>
                <span class="model-tag">{{ answerProvenanceLabel(answer) }}</span>
                <span v-if="isAdmin" class="model-tag">{{ answer.model }}</span>
              </div>
            </div>
            <div class="answer-reading-actions"><span>把思路看清楚，再回到资料核对。</span><button type="button" @click="readAnswer(answer, displayedAnswerQuestion)">专注阅读 ↗</button></div>
            <RichText :source="answer.answer" navigation :evidence-count="answer.citations.length" @evidence="openAnswerEvidence(answer!, $event)" />
            <AnswerReviewPanel v-if="answer.answer_review" :review="answer.answer_review" @source="openAnswerEvidence(answer!, $event)" />
            <AnswerAnnotation v-if="answer.history_id" :key="user.id + answer.history_id" :history-id="answer.history_id" :answer="answer.answer" :citation-count="answer.citations.length" :request="request" />
            <CalculationReceipts v-if="answer.calculations?.length" :records="answer.calculations" :base="apiBase" :token="token" />
            <div v-if="answer.history_id" class="quick-teaching-actions"><button type="button" @click="openUnifiedAssistant">在助手中提问 ↗</button><button :class="{ selected: answer.favorite }" @click="toggleFavorite">{{ answer.favorite ? '已收藏' : '收藏回答' }}</button><button @click="exportAnswer">导出 Markdown</button></div>
            <div v-if="answer.history_id" class="feedback-row">
              <span>这条回答对你有帮助吗？</span>
              <button type="button" :class="{ selected: answer.rating === 5 }" :disabled="feedbackBusy" @click="sendFeedback(5)">有帮助</button>
              <button type="button" :class="{ selected: answer.rating === 2 }" :disabled="feedbackBusy" @click="sendFeedback(2)">需要改进</button>
            </div>
          </article>
          <aside class="panel citation-panel">
            <div class="result-heading">
              <div>
                <p class="section-kicker">{{ answer.citations.length ? 'EVIDENCE' : 'ANSWER NOTE' }}</p>
                <h2>{{ answer.citations.length ? '证据溯源' : '回答说明' }}</h2>
              </div>
              <span class="count-label">{{ answer.citations.length }} 条</span>
            </div>
            <div v-if="answer.citations.length" class="citations">
              <div v-for="citation in answer.citations" :key="`${citation.document_name}-${citation.page_number}-${citation.text}`" class="citation">
                <strong>{{ citation.document_name }}</strong>
                <span class="citation-meta">第 {{ citation.page_number }} 页 · 匹配度 {{ Math.round(citation.score * 100) }}%</span>
                <span v-if="citation.chapter" class="chapter">{{ citation.chapter }}</span>
                <p>{{ citation.text }}</p>
                <button class="citation-open" type="button" :disabled="!citation.document_id" @click="openCitation(citation)">{{ citation.document_id ? '打开原文定位 ›' : '旧记录无精确定位' }}</button>
              </div>
            </div>
            <p v-else class="muted">
              {{ answerEvidenceNote(answer) }}
            </p>
          </aside>
        </section>
      </section>
    </section>
      </div>
    </section>
    <DetailDialog v-if="documentOpening" title="正在打开资料…" kicker="COURSE READER" close-label="取消打开资料" @close="cancelDocumentOpen"><p class="course-detail-loading" role="status"><span class="pagination-spinner" />正在载入原文，请稍候…</p></DetailDialog>
    <DetailDialog v-if="documentOpenError" title="资料暂时无法打开" close-label="关闭资料提示" size="small" @close="documentOpenError = null"><p role="alert">{{ documentOpenError.message }}</p><template #footer><button type="button" @click="openDocumentById(documentOpenError.id, documentOpenError.page)">重试打开</button><button type="button" class="ghost-button" @click="documentOpenError = null">返回</button></template></DetailDialog>
    <DocumentPreview v-if="selectedDocumentContent" :key="`${user.id}:${selectedDocumentContent.document.id}`" :content="selectedDocumentContent" :initial-page="documentPreviewTargetPage" :busy="platformBusy || studyNoteBusy" :return-label="selectedCourse ? '返回课程' : selectedTeachingDraft ? '返回教学草稿' : readerAnswer ? '返回回答阅读' : '返回原页面'" @close="closeDocumentPreview" @selection="captureDocumentSelection">
      <template #information><button v-if="canManage" type="button" @click="versionDocumentId=selectedDocumentContent.document.id">版本记录与恢复</button><div v-if="selectedDocumentContent.document.source_url || selectedDocumentContent.document.license_name" class="document-source-note"><div><strong>资料来源与使用说明</strong><p>{{ selectedDocumentContent.document.license_name || '许可信息待核对' }}<span v-if="selectedDocumentContent.document.name.includes('文字摘编')"> · 文字摘编按主题编排，本系统页码不是原文页码</span></p></div><div class="document-source-links"><a v-if="safeMaterialLink(selectedDocumentContent.document.source_url)" :href="safeMaterialLink(selectedDocumentContent.document.source_url) || undefined" target="_blank" rel="noopener noreferrer">查看来源 ↗</a><a v-if="safeMaterialLink(selectedDocumentContent.document.license_url)" :href="safeMaterialLink(selectedDocumentContent.document.license_url) || undefined" target="_blank" rel="noopener noreferrer">查看许可 ↗</a></div></div>
            <section v-if="canManage" class="document-governance-form"><h3>资料信息维护</h3><label>资料来源网址<input v-model="documentSourceUrl" placeholder="资料来源网址" /></label><label>授权名称<input v-model="documentLicenseName" placeholder="授权名称，例如 CC BY 4.0" /></label><label>授权说明网址<input v-model="documentLicenseUrl" placeholder="授权说明网址" /></label><label>资料版本<input v-model="documentVersion" placeholder="版本，例如 2.1" /></label><label>发布状态<select v-model="documentPublicationStatus"><option value="draft">草稿</option><option value="published">已发布</option><option value="archived">已归档</option></select></label><button :disabled="platformBusy" @click="saveDocumentGovernance">保存资料信息</button></section>
            <section v-if="user.role === 'admin'" class="document-external-sharing"><div><strong>外部模型资料授权</strong><p>{{ selectedDocumentContent.document.external_model_allowed ? '已核准：在线模型可使用这份资料的检索片段' : '未核准：资料仅供本地检索，不会自动发送给外部模型' }}</p></div><button type="button" :disabled="platformBusy" @click="requestDocumentExternalSharing">{{ selectedDocumentContent.document.external_model_allowed ? '撤销外发' : '复核并批准' }}</button></section>
<p v-if="status" class="platform-message" role="status">{{ status }}</p></template>
      <template #notice>            <div v-if="user.role === 'student'" class="document-selection-tip">在正文中选中 10—1200 个字，可保存摘录；资料获准外发且模型可用时，也可请求解释、总结或整理学习笔记。</div>
            <p v-if="user.role === 'student' && modelStatus && (!modelStatus.llm_configured || !selectedDocumentContent.document.external_model_allowed)" class="study-note-status">{{ !modelStatus.llm_configured ? '当前在线 AI 模型不可用；可以阅读和保存原文摘录。' : '这份资料仅供站内阅读与检索，尚不能发送给外部 AI 模型；可以保存原文摘录。' }}</p>
<p v-if="user.role === 'student' && studyNoteStatus" class="study-note-status" :class="{ 'is-error': studyNoteStatusError }" :role="studyNoteStatusError ? 'alert' : 'status'">{{ studyNoteStatus }}</p></template>
      <template #actions>            <div v-if="selectedPassage && selectedPassage.documentId === selectedDocumentContent.document.id" class="document-selection-actions"><span>已选第 {{ selectedPassage.pageNumber }} 页：{{ selectedPassage.text.slice(0, 70) }}{{ selectedPassage.text.length > 70 ? '…' : '' }}</span><div><button type="button" @click="askSelectedPassage('explain')">解释选段</button><button type="button" @click="askSelectedPassage('summary')">总结选段</button><button type="button" @click="askSelectedPassage('note')">生成笔记</button><button type="button" :disabled="studyNoteBusy" @click="saveStudyNote(selectedPassage, 'excerpt')">保存摘录</button></div></div>
</template>
    </DocumentPreview>
    <DetailDialog v-if="selectedTeachingDraft" :key="`${user.id}:${selectedTeachingDraft.id}`" :title="selectedTeachingDraft.title" :description="`${selectedTeachingDraft.course_title} · ${teachingDraftTypeLabel(selectedTeachingDraft.draft_type)}`" kicker="TEACHING EDITOR" close-label="关闭教学草稿" :close-disabled="platformBusy" :view-key="draftView" @close="closeTeachingDraft">
      <aside v-if="selectedTeachingDraft.source_context.teaching_quality?.findings?.length" class="draft-ai-message"><strong>有概念表述需要核对</strong><p v-for="(finding,index) in selectedTeachingDraft.source_context.teaching_quality.findings" :key="index">{{finding.message}}</p></aside>
      <p v-if="selectedTeachingDraft.source_context.concept_corrections?.length" class="draft-ai-message">已修订已知的概念泛化表述，请结合课程资料核对后使用。</p>
      <template #navigation><nav class="course-detail-tabs" aria-label="教学草稿视图"><button v-for="tab in [{ id: 'edit', label: '编辑内容' }, { id: 'preview', label: '阅读预览' }, { id: 'sources', label: '流程与依据' }]" :key="tab.id" type="button" :aria-pressed="draftView === tab.id" @click="draftView = tab.id as typeof draftView">{{ tab.label }}</button><span v-if="teachingDraftHasUnsavedChanges(selectedTeachingDraft)" class="grading-unsaved-badge">有未保存修改</span></nav></template>
      <EditorDraftNotice :restored="teachingEditorDraft.restored.value" :saved-at="teachingEditorDraft.savedAt.value" :error="teachingEditorDraft.error.value" :recovery="!!teachingEditorDraft.recovery.value" :changed-elsewhere="teachingEditorDraft.changedElsewhere.value" @recover="recoverTeachingDraft" @keep="teachingEditorDraft.keepCurrent" />
      <fieldset :disabled="platformBusy" class="dialog-editor-fields"><section v-show="draftView === 'sources'">
            <div v-if="selectedTeachingDraft.source_context.origin === 'ai_generated'" class="draft-evidence-note"><strong>{{ teachingDraftEvidence(selectedTeachingDraft).length ? '本课程检索资料' : '未命中课程资料' }}</strong><p>{{ teachingDraftEvidence(selectedTeachingDraft).length ? '以下为本次检索定位；请核对资料与草稿，不把命中资料视为内容已经正确。' : '这份草稿没有可用的课程资料依据，仅供参考，请先核对后再确认。' }}</p><ul v-if="teachingDraftEvidence(selectedTeachingDraft).length"><li v-for="item in teachingDraftEvidence(selectedTeachingDraft)" :key="item.chunk_id">{{ item.document_name }} · 第 {{ item.page_number }} 页</li></ul></div>
            <div v-if="selectedTeachingDraft.draft_type === 'review'" class="draft-evidence-note"><strong>{{ selectedTeachingDraft.source_context.model === 'local-statistics' ? '站内统计提纲 · 未使用在线模型' : '在线 AI 辅助草稿 · 教师核对' }}</strong><p>已提交 {{ selectedTeachingDraft.source_context.submission_count }} 人 · 已批改 {{ selectedTeachingDraft.source_context.graded_count }} 人 · 待批改 {{ selectedTeachingDraft.source_context.pending_review_count }} 人<span v-if="selectedTeachingDraft.source_context.average_percent !== null"> · 已批改平均得分率 {{ selectedTeachingDraft.source_context.average_percent }}%</span>。<span v-if="selectedTeachingDraft.source_context.includes_student_answers">已提供 {{ selectedTeachingDraft.source_context.student_work_included }}/{{ selectedTeachingDraft.source_context.student_work_total }} 份具体作答供 AI 分析；班级讲评应聚焦共性问题。</span><span v-else>本草稿依据汇总统计。</span>请核对题目、统计与教学建议。</p></div>
            <div v-if="selectedTeachingDraft.draft_type === 'student_analysis'" class="draft-evidence-note"><strong>学生个人作答诊断 · 教师侧草稿</strong><p>基于该学生本次具体作答与已保存的批改记录，覆盖 {{ selectedTeachingDraft.source_context.question_count_analyzed }}/{{ selectedTeachingDraft.source_context.question_count_total }} 题；不自动发布为班级讲评或修改成绩。</p></div>
            <div v-if="selectedTeachingDraft.draft_type === 'course_analysis'" class="draft-evidence-note"><strong>课程全体学情 · 教师侧分析草稿</strong><p>基于生成时的全体统计和实名成绩记录，供综合判断与教学跟进；不自动改分或通知学生。可回到学情总览查看当前记录与更新报告。</p><button type="button" @click="openCourseAnalysis(selectedTeachingDraft.course_id); selectedTeachingDraft = null">回到学情总览 ↗</button></div>
            <div v-if="selectedTeachingDraft.source_context.model === 'local-statistics' && selectedTeachingDraft.draft_type !== 'review'" class="draft-evidence-note"><strong>站内记录提纲 · 未调用在线模型</strong><p>依据当前课程统计准备的可编辑框架。教材讲解、示例与参考答案仍需教师补充。</p></div>
            <div v-if="selectedTeachingDraft.source_context.model === 'offline-template'" class="draft-evidence-note"><strong>离线提纲 · 非在线 AI 结果</strong><p>请结合课程资料补充教学内容，核对后再确认。</p></div>
            <TeachingImpactPanel v-if="selectedTeachingDraft.source_context.teaching_snapshot" :impact="teachingImpact" :busy="teachingImpactBusy" :error="teachingImpactError" :hide-batch-practice="selectedTeachingDraft.draft_type === 'question_set'" @refresh="loadTeachingImpact" />
            <AnalysisBasisPanel v-if="['review', 'student_analysis'].includes(selectedTeachingDraft.draft_type)" :key="`${user.id}:${selectedTeachingDraft.id}`" :base="apiBase" :token="token" :owner="user.id" :draft-id="selectedTeachingDraft.id" @open-assignment="openWorkflowAssignment" />
            <TeachingWorkflowPanel v-if="selectedTeachingDraft.draft_type === 'question_set'" :key="`${user.id}:${selectedTeachingDraft.id}`" :draft-id="selectedTeachingDraft.id" :status="selectedTeachingDraft.status" :request="request" @open-assignment="openWorkflowAssignment" @changed="refreshWorkflowAssignments" />
</section><section v-show="draftView === 'edit'">            <label>草稿标题<input v-model="selectedTeachingDraft.title" maxlength="200" :disabled="selectedTeachingDraft.status === 'published'" /></label>
            <template v-if="selectedTeachingDraft.draft_type === 'question_set'">
              <div class="draft-question-heading"><h3>逐题审核 · {{ selectedTeachingDraft.questions.length }} 道</h3><button v-if="selectedTeachingDraft.status !== 'published'" type="button" @click="addDraftQuestion">添加题目</button></div>
              <label v-if="selectedTeachingDraft.status !== 'published'" class="draft-ai-consent"><input v-model="draftAIReviewConsent" type="checkbox" /><span>我已核对本题和相关课程资料的使用范围，同意点击“AI 复核本题”时将题目、答案、解析及检索到的资料片段发送给当前模型服务。未经点击不会发送。</span></label>
              <p v-if="!selectedTeachingDraft.questions.length" class="empty-state">这份旧草稿尚无结构化题目。可在这里逐题添加，或重新生成一份题目草稿。</p>
<PagedList :items="draftQuestionsWithIndex" :page-size="3" :scope="selectedTeachingDraft.id" label="草稿审核题目" v-slot="{ items: draftPageItems }">              <article v-for="{ item, index } in draftPageItems" :key="index" class="draft-question-editor">
                <div class="draft-question-heading"><strong>第 {{ index + 1 }} 题</strong><div v-if="selectedTeachingDraft.status !== 'published'" class="draft-question-actions"><button type="button" class="ghost-button" @click="selectedTeachingDraft.questions.splice(index, 1)">移除</button></div></div>
                <div class="draft-question-fields"><label>题型<select v-model="item.question_type" :disabled="selectedTeachingDraft.status === 'published'"><option value="single_choice">单选</option><option value="multiple_choice">多选</option><option value="true_false">判断</option><option value="fill_blank">填空</option><option value="short_answer">简答</option></select></label><label>难度（1–5）<input v-model.number="item.difficulty" type="number" min="1" max="5" :disabled="selectedTeachingDraft.status === 'published'" /></label><label>知识点<input v-model="item.knowledge_point" :disabled="selectedTeachingDraft.status === 'published'" /></label></div>
                <label>题干<textarea v-model="item.stem" rows="3" :disabled="selectedTeachingDraft.status === 'published'" /></label>
                <label v-if="['single_choice','multiple_choice','true_false'].includes(item.question_type)">选项（每行一个）<textarea :value="item.options.join('\n')" rows="4" :disabled="selectedTeachingDraft.status === 'published'" @input="item.options = ($event.target as HTMLTextAreaElement).value.split('\n').filter(Boolean)" /></label>
                <div class="draft-question-fields"><label>参考答案<textarea v-model="item.correct_answer" rows="3" maxlength="2000" :disabled="selectedTeachingDraft.status === 'published'" /></label><label>解析<textarea v-model="item.explanation" rows="5" maxlength="5000" :disabled="selectedTeachingDraft.status === 'published'" /></label></div>
                <details v-if="item.explanation" class="draft-raw-content"><summary>解析排版预览</summary><RichText :source="item.explanation" /></details>
                <QuestionReviewPanel :key="`${selectedTeachingDraft.id}-${index + 1}`" :base="apiBase" :token="token" :owner="user.id" :draft-id="selectedTeachingDraft.id" :index="index + 1" :question="item" :saved="!teachingDraftHasUnsavedChanges(selectedTeachingDraft)" :published="selectedTeachingDraft.status === 'published'" :consent="draftAIReviewConsent" @adopt="adoptReviewedChange" @source="openDocumentById" />
              </article></PagedList>
              <section v-if="selectedTeachingDraft.status !== 'published'" class="draft-quality-panel">
                <div class="draft-quality-heading"><div><strong>入库前质量检查</strong><p>检查重复题、选项和答案对应关系；知识正确性仍由教师判断。</p></div><button type="button" :disabled="draftQualityBusy || platformBusy || teachingDraftHasUnsavedChanges(selectedTeachingDraft)" @click="checkDraftQuestions">{{ draftQualityBusy ? '检查中…' : '检查题目' }}</button></div>
                <p v-if="teachingDraftHasUnsavedChanges(selectedTeachingDraft)" class="draft-quality-hint">有未保存修改，请先保存再检查。</p>
                <template v-else-if="draftQualityReport && draftQualityIsCurrent(selectedTeachingDraft)">
                  <p class="draft-quality-summary" :class="{ 'has-errors': draftQualityReport.error_count > 0 }">{{ draftQualityReport.error_count }} 项需修正 · {{ draftQualityReport.warning_count }} 项待核对</p>
                  <ul v-if="draftQualityReport.findings.length"><li v-for="(finding, index) in draftQualityReport.findings" :key="`${finding.code}-${finding.question_index}-${index}`" :class="finding.severity"><b>第 {{ finding.question_index }} 题 · {{ finding.severity === 'error' ? '需修正' : '请核对' }}</b><span>{{ finding.message }}</span></li></ul>
                  <p v-else class="draft-quality-hint">未发现确定性问题。请继续人工检查题意、答案和解析。</p>
                </template>
                <p v-else class="draft-quality-hint">尚未检查当前版本的题目。</p>
              </section>
            </template>
            <section v-if="selectedTeachingDraft.draft_type === 'review'" class="review-draft-body"><p v-if="selectedTeachingDraft.source_context.revision_of" class="draft-ai-message">这是保留原版的修订草稿；保存不会替换学生讲评，仍需核对、确认后发布。原数据已变化时应重新生成讲评。</p><button v-if="selectedTeachingDraft.status === 'published'" type="button" class="ghost-button" :disabled="platformBusy" @click="reviseAssignmentReview(selectedTeachingDraft.id)">创建可编辑修订稿 ↗</button><label v-if="selectedTeachingDraft.status !== 'published'">讲评正文（Markdown）<textarea v-model="selectedTeachingDraft.content" rows="15" /></label><div class="review-draft-preview"><strong>学生端阅读预览</strong><div class="answer-markdown" v-html="renderMarkdown(selectedTeachingDraft.content)" /></div></section>
            <section v-else-if="['course_analysis', 'student_analysis'].includes(selectedTeachingDraft.draft_type)" class="review-draft-body"><label>{{ selectedTeachingDraft.draft_type === 'student_analysis' ? '个人诊断正文（Markdown）' : '学情分析正文（Markdown）' }}<textarea v-model="selectedTeachingDraft.content" rows="15" /></label><div class="review-draft-preview"><strong>教师阅读预览 · 与原始AI建议分开保存</strong><RichText :source="selectedTeachingDraft.content" /></div></section>
            <details v-else-if="selectedTeachingDraft.draft_type === 'question_set'" class="draft-raw-content"><summary>查看 AI 原始输出</summary><label>原始正文（Markdown）<textarea v-model="selectedTeachingDraft.content" rows="16" :disabled="selectedTeachingDraft.status === 'published'" /></label></details>
            <label v-else class="draft-main-content">草稿正文（Markdown）<textarea v-model="selectedTeachingDraft.content" rows="16" :disabled="selectedTeachingDraft.status === 'published'" /></label>
            <p v-if="teachingDraftFeedback.message" class="draft-workflow-status" :class="{ 'is-error': teachingDraftFeedback.error }" :role="teachingDraftFeedback.error ? 'alert' : 'status'">{{ teachingDraftFeedback.message }}</p>

            <p class="config-note">{{ ['course_analysis', 'student_analysis'].includes(selectedTeachingDraft.draft_type) ? '分析仅供教师核对，可修改、保存或归档；不自动修改成绩或发布给学生。' : selectedTeachingDraft.draft_type === 'review' ? '讲评需教师保存、确认后发布；学生提交或批改变化后，应重新生成并发布。统计和模型建议均需教师核对。' : selectedTeachingDraft.draft_type === 'question_set' ? '题目需先保存、教师确认并运行质量检查，才能入库；检查结果不能代替教师判断题意和答案。入库操作不可重复。' : '结合课程资料完善教学目标、课堂安排与课后任务，再保存或确认。确认教案不会自动排课、布置作业或改变课程进度。' }}</p>
</section></fieldset>
      <section v-if="draftView === 'preview'" class="teaching-reader-preview"><RichText :source="selectedTeachingDraft.content" /><PagedList v-if="selectedTeachingDraft.questions.length" :items="draftQuestionsWithIndex" :page-size="5" :scope="selectedTeachingDraft.id" label="草稿阅读题目" v-slot="{ items: previewItems }"><article v-for="{ item, index } in previewItems" :key="index"><h3>第 {{ index + 1 }} 题</h3><RichText :source="item.stem" /><ol v-if="item.options.length"><li v-for="option in item.options" :key="option">{{ option }}</li></ol><details><summary>参考答案与解析</summary><RichText :source="item.correct_answer" /><RichText :source="item.explanation || '暂无解析'" /></details></article></PagedList></section>
      <template #footer>            <div v-if="selectedTeachingDraft.status !== 'published'" class="draft-review-actions"><button :disabled="platformBusy" @click="updateTeachingDraft()">保存修改</button><button v-if="selectedTeachingDraft.status !== 'confirmed'" :disabled="platformBusy" @click="updateTeachingDraft('confirmed')">确认内容</button><button v-if="selectedTeachingDraft.status === 'confirmed' && selectedTeachingDraft.draft_type === 'question_set'" :disabled="platformBusy || !selectedTeachingDraft.questions.length || teachingDraftHasUnsavedChanges(selectedTeachingDraft)" @click="publishDraftQuestions">将已确认题目写入题库</button><button v-if="selectedTeachingDraft.status === 'confirmed' && selectedTeachingDraft.draft_type === 'review'" :disabled="platformBusy || teachingDraftHasUnsavedChanges(selectedTeachingDraft)" @click="publishAssignmentReview">发布讲评给已提交学生</button><button class="ghost-button" :disabled="platformBusy" @click="updateTeachingDraft('archived')">归档</button></div><span v-if="selectedTeachingDraft.status === 'published'">已发布内容只读；修改请从原业务入口创建修订稿。</span></template>
    </DetailDialog>
    <DetailDialog v-if="selectedCourse" :key="selectedCourse.id" close-label="关闭课程详情" :title="selectedCourse.title" :kicker="`COURSE SPACE · ${selectedCourse.semester || '未设置学期'}`" :description="selectedCourse.description" :view-key="courseDetailTab" :close-disabled="platformBusy" @close="closeCourseDetail">
      <DataExports v-if="canManage" :base="apiBase" :token="token" :course-id="selectedCourse.id" />
      <template #navigation><nav class="course-detail-tabs" aria-label="课程详情栏目"><button v-for="tab in [{ id: 'overview', label: '课程概览' }, { id: 'materials', label: '资料与知识点' }, { id: 'sessions', label: '课次安排' }, ...(canManage ? [{ id: 'members', label: '课程成员' }] : [])]" :key="tab.id" type="button" :aria-pressed="courseDetailTab === tab.id" :disabled="courseDetailLoading || !!courseDetailError" @click="courseDetailTab = tab.id as typeof courseDetailTab">{{ tab.label }}</button></nav></template>
      <div v-if="courseDetailLoading" class="course-detail-loading" role="status"><span class="pagination-spinner" /><strong>正在打开课程…</strong><p>读取课程大纲、资料和本学期安排</p></div>
      <div v-else-if="courseDetailError" class="course-detail-error" role="alert"><strong>课程暂时无法完整读取</strong><p>{{ courseDetailError }}</p><button type="button" @click="openCourseDetail(selectedCourse)">重试</button></div>
      <template v-else>
        <p v-if="platformStatus" class="course-action-status" role="status">{{ platformStatus }}</p>
        <div v-show="courseDetailTab === 'overview'">
            <div v-if="canManage" class="inline-actions"><button type="button" :disabled="courseDetailLoading || !!courseDetailError" @click="openCourseEditor">编辑课程</button></div>
            <details v-if="selectedCourse.description" class="course-intro"><summary>课程介绍</summary><RichText :source="selectedCourse.description" :tools="false" /></details>
            <details v-if="selectedCourse.learning_objectives" class="course-intro"><summary>学习目标</summary><RichText :source="selectedCourse.learning_objectives" :tools="false" /></details>
            <details v-if="selectedCourse.assessment" class="course-intro"><summary>考核方式</summary><RichText :source="selectedCourse.assessment" :tools="false" /></details>
            <div class="course-facts"><span><small>授课教师</small><strong>{{ selectedCourse.teacher_name || '暂未公布' }}</strong></span><span><small>上课时间与场地</small><button type="button" class="text-button" @click="openTimetableCourse(selectedCourse.id)">打开本课程课表 ›</button></span><span><small>课次安排</small><strong>{{ courseSessions.length }} 节</strong></span></div>
            <section class="course-announcement-panel">
              <div class="panel-heading"><div><p class="section-kicker">COURSE NOTICES</p><h3>课程公告</h3></div><span class="count-label">{{ announcementTotal }} 条</span></div>
              <details v-if="canManage" class="course-compose-disclosure" :open="!!editingAnnouncementId"><summary>{{ editingAnnouncementId ? '编辑课程公告' : '发布课程公告' }}</summary><div class="course-announcement-compose">
                <p v-if="editingAnnouncementId" class="editor-mode">正在编辑公告 <button type="button" @click="resetAnnouncementEditor">取消编辑</button></p>
                <label>公告标题<input v-model="newAnnouncementTitle" maxlength="200" placeholder="公告标题" /></label>
                <label>公告正文<textarea v-model="newAnnouncementContent" maxlength="10000" rows="3" placeholder="面向本课程所有学生发布学习安排或重要通知" /></label>
                <button :disabled="platformBusy || !newAnnouncementTitle.trim() || !newAnnouncementContent.trim()" @click="publishCourseAnnouncement">{{ editingAnnouncementId ? '保存公告' : '发布到本课程' }}</button>
              </div></details>
              <p v-if="announcementStatus" class="platform-message" role="alert">{{ announcementStatus }}</p>
              <div class="course-announcement-list"><article v-for="item in courseAnnouncements" :key="item.id"><details class="course-notice"><summary><strong>{{ item.title }}</strong><small>{{ item.author_name }} · {{ historyTime(item.published_at || '') }}</small></summary><p>{{ item.content }}</p></details><div v-if="canManage" class="row-actions"><button type="button" @click="editCourseAnnouncement(item)">编辑</button><button type="button" class="danger-action" @click="deleteCourseAnnouncement(item)">删除</button></div></article><p v-if="!courseAnnouncements.length" class="empty-state">本课程暂无公告。</p></div>
              <div v-if="announcementTotal > 5" class="list-pager"><span>第 {{ announcementPageIndex }} / {{ announcementPageCount }} 页</span><button type="button" :disabled="announcementPageIndex <= 1" @click="loadCourseAnnouncements(announcementPageIndex - 1)">上一页</button><button type="button" :disabled="announcementPageIndex >= announcementPageCount" @click="loadCourseAnnouncements(announcementPageIndex + 1)">下一页</button></div>
            </section>

        <details v-if="canManage" class="course-management-actions"><summary>课程状态管理</summary><div class="inline-actions"><button type="button" :disabled="platformBusy || selectedCourse.status === 'published'" @click="updateCourseStatus('published')">发布课程</button><button type="button" :disabled="platformBusy || selectedCourse.status === 'draft'" @click="updateCourseStatus('draft')">转为草稿</button><button type="button" :disabled="platformBusy || selectedCourse.status === 'archived'" @click="updateCourseStatus('archived')">归档课程</button></div><p v-if="platformStatus" role="status">{{ platformStatus }}</p></details>
        </div>
            <div v-show="courseDetailTab === 'overview' || courseDetailTab === 'materials'" class="course-detail-grid is-tabbed">
              <section v-show="courseDetailTab === 'overview'"><h3>课程大纲</h3><button v-for="section in selectedCourse.sections" :key="section.id" type="button" class="course-detail-item" @click="selectedOutlineSection = section"><span>{{ section.position }}</span><div><strong>{{ section.title }}</strong><small>{{ section.description || '点击查看章节内容' }}</small></div><i>›</i></button><p v-if="!selectedCourse.sections.length" class="empty-state">课程大纲尚未公布。</p><div v-if="selectedOutlineSection" class="outline-detail"><strong>第 {{ selectedOutlineSection.position }} 章 · {{ selectedOutlineSection.title }}</strong><RichText :source="selectedOutlineSection.description || '该章节详细内容正在建设中。'" /><ChapterReadings :key="selectedOutlineSection.id" :section-id="selectedOutlineSection.id" :materials="courseMaterials" :manage="canManage" :request="request" @open="openDocumentById" /><button type="button" @click="selectedOutlineSection = null">收起</button></div><PracticePolicyPanel v-if="canManage" :key="selectedCourse.id" :course-id="selectedCourse.id" :request="request" /></section>
              <section v-show="courseDetailTab === 'materials'">
                <div class="panel-heading"><h3>对应资料</h3><button v-if="canManage" type="button" class="text-button" @click="openCourseEditor">编辑课程</button></div>
                <PagedList :items="courseMaterials" :page-size="6" label="课程资料" v-slot="{ items: materialItems }"><button v-for="material in materialItems" :key="material.id" type="button" class="course-detail-item" @click="openCourseMaterial(material)"><span>资</span><div><strong>{{ material.name }}</strong><small>{{ material.page_count || 0 }} 页 · {{ material.version_label }} · 点击查看原文</small></div><i>›</i></button><p v-if="!courseMaterials.length" class="empty-state">该课程暂未发布学习资料。</p></PagedList>
                <h3>课程知识点</h3>
                <PagedList :items="courseKnowledgePoints" :page-size="12" label="课程知识点" v-slot="{ items: pointItems }"><div class="point-cloud"><button v-for="point in pointItems" :key="point.id" type="button" :aria-pressed="selectedCoursePoint?.id === point.id" @click="selectedCoursePoint = selectedCoursePoint?.id === point.id ? null : point">{{ point.name }} ›</button></div></PagedList>
                <div v-if="selectedCoursePoint" class="outline-detail"><strong>{{ selectedCoursePoint.name }}</strong><RichText :source="selectedCoursePoint.description || '该知识点暂无详细说明。'" :tools="false" /><button type="button" @click="selectedCoursePoint = null">收起说明</button></div>
              </section>
            </div>

            <section v-show="courseDetailTab === 'sessions'" class="course-session-panel"><div class="panel-heading"><div><h3>本学期课次安排</h3><p>查看本学期的授课主题、时间与地点。</p></div><span class="count-label">{{ courseSessions.filter(item => item.completed).length }}/{{ courseSessions.length }} 已完成</span></div>
              <button type="button" @click="openTimetableCourse(selectedCourse.id)">{{ user.role==='admin'?'打开排课管理':user.role==='teacher'?'查看课表 / 申请调课':'打开课程课表' }} ›</button>
              <PagedList class="session-list" :items="courseSessions" :scope="selectedCourse.id" :load-page="pageLoader<CourseSessionRecord>('sessions', selectedCourse.id)" label="课程课次" v-slot="{ items: sessionItems }"><article v-for="item in sessionItems" :key="item.id"><span :class="['session-state', { done: item.completed }]">{{ item.schedule_status==='cancelled'?'已停课':item.completed ? '已上课' : '待授课' }}</span><div><button type="button" class="text-button" @click="openTimetableSession(item.id)">{{ item.title }} ›</button><small>{{ historyTime(item.session_date) }} · {{ item.location || '地点待定' }} · {{ item.duration_minutes }} 分钟<span v-if="item.section_title"> · {{ item.section_title }}</span></small></div><button v-if="canManage && item.schedule_status!=='cancelled' && (item.completed || Date.parse(item.session_date)<=clockNow)" :disabled="platformBusy" :class="item.completed ? 'ghost-button' : ''" @click="toggleCourseSession(item)">{{ item.completed ? '撤销完成' : '标记已上课' }}</button></article></PagedList>
            </section>

            <section v-if="canManage" v-show="courseDetailTab === 'members'" class="course-member-panel"><div class="panel-heading"><div><h3>课程成员</h3><p>只按本课程管理学生访问，不按班级分配。</p></div><span class="count-label">{{ courseMembers.filter(item => item.status === 'active').length }} 名学生</span></div><div class="course-member-add"><label>学生账号<input v-model="newCourseMemberUsername" placeholder="输入学生账号" @keyup.enter="addCourseMember" /></label><button :disabled="platformBusy || !newCourseMemberUsername.trim()" @click="addCourseMember">加入课程</button></div><PagedList class="course-member-list" :items="courseMembers" :scope="selectedCourse.id" :load-page="pageLoader<ClassMember>('members', selectedCourse.id)" label="课程成员" v-slot="{ items: memberItems }"><article v-for="member in memberItems" :key="member.user_id"><div><strong>{{ member.display_name }}</strong><small>{{ member.username }} · {{ member.status === 'active' ? '课程成员' : '已移出' }}</small></div><button :class="member.status === 'active' ? 'danger-soft' : 'ghost-button'" :disabled="platformBusy" @click="setCourseMemberStatus(member, member.status === 'active' ? 'removed' : 'active')">{{ member.status === 'active' ? '移出课程' : '恢复访问' }}</button></article><p v-if="!memberItems.length" class="empty-state">暂无课程成员，可按学生账号添加。</p></PagedList></section>

      </template>
      <template #footer><span>{{ selectedCourse.code }} · {{ selectedCourse.status === 'published' ? '已发布' : selectedCourse.status === 'archived' ? '已归档' : '草稿' }}</span><button v-if="canManage" type="button" class="text-button" :disabled="platformBusy || courseDetailLoading || !!courseDetailError" @click="openCourseAnalysis(selectedCourse.id); closeCourseDetail()">全体学情与 AI 分析 ↗</button><button v-else type="button" class="text-button" @click="closeCourseDetail">返回继续浏览</button></template>
    </DetailDialog>
    <button v-if="!globalAssistantOpen && !readerAnswer && !selectedAssignment && !selectedPractice" ref="assistantFab" class="assistant-fab" type="button" :class="{ busy: globalAssistantBusy, unread: assistantHasUnread }" aria-controls="global-ai-assistant" :aria-expanded="globalAssistantOpen" :aria-label="assistantHasUnread ? '助手已回复' : globalAssistantBusy ? '正在回答…' : assistantRoleTitle" :title="assistantRoleTitle" @click="globalAssistantOpen = true"><span aria-hidden="true">✦</span><b>{{ assistantHasUnread ? '助手已回复' : globalAssistantBusy ? '正在回答…' : assistantRoleTitle }}</b><i v-if="assistantHasUnread" aria-label="有新回答" /></button>
    <CourseEditor v-if="courseEditorId && canManage" :key="`${user.id}:${courseEditorId}`" ref="courseEditorPanel" :course-id="courseEditorId" :role="user.role" :teacher-name="selectedCourse?.teacher_name" :request="request" @close="closeCourseEditor()" @materials="closeCourseEditor(true)" @assist="openCourseAssistant" @published="courseEditorChanged = true" @dirty="courseEditorDirty = $event" @saving="courseEditorSaving = $event" />
    <TeachingWorkbench v-if="workbenchOpen&&canManage" :key="`${user.id}:${workbenchConfig.courseId}:${workbenchConfig.resultId}:${workbenchConfig.tab}`" ref="workbenchPanel" :role="user.role" :courses="platformCourses" :initial-course-id="workbenchConfig.courseId" :initial-tab="workbenchConfig.tab" :initial-prompt="workbenchConfig.prompt" :initial-result-id="workbenchConfig.resultId" :request="request" :token="token" :base="apiBase" @close="closeTeachingWorkbench" @changed="workbenchChanged=true" @open-draft="openWorkbenchDraft" @edit-course="editWorkbenchCourse" @dirty="workbenchDirty=$event" @saving="workbenchSaving=$event" />
    <Teleport :to="assistantInline ? '#assistant-workspace-host' : 'body'" :disabled="!assistantInline" defer>
    <DocumentVersions v-if="versionDocumentId && canManage" :key="user.id+versionDocumentId" :document-id="versionDocumentId" :request="request" :base="apiBase" :token="token" @close="versionDocumentId=''" @changed="loadDocuments();openDocumentById(versionDocumentId)" />
    <aside v-if="globalAssistantOpen" id="global-ai-assistant" class="global-assistant-panel" :class="{ 'is-workspace': assistantInline }" :style="viewportStyle" :role="compactViewport ? 'dialog' : undefined" :aria-modal="compactViewport && !mobileNavigationOnTop ? true : undefined" :aria-label="assistantRoleTitle" tabindex="-1" @keydown="assistantMobileKeys">
      <header class="assistant-panel-header">
        <div class="assistant-identity"><button v-if="compactViewport" type="button" class="assistant-avatar assistant-nav-entry" aria-label="打开平台导航" @click="openAssistantNavigation">☰</button><span v-else class="assistant-avatar">✦</span><div><strong>{{ assistantRoleTitle }}</strong><small>{{ assistantInline ? (user.role === 'admin' ? '查看平台状态，继续你的管理任务' : '选择课程，继续你的对话与任务') : `随时陪你完成当前任务 · ${workspaceTitle}` }}</small></div></div>
        <div class="assistant-header-actions"><button v-if="compactViewport" type="button" aria-label="查看资料与旧记录" @click="openMaterialWorkspace">资料</button><button type="button" title="开始新对话" :disabled="!assistantTurns.length && !globalAssistantBusy" @click="resetAssistantConversation">新对话</button><button type="button" :aria-label="assistantInline ? '返回首页' : '收起助手'" @click="assistantInline ? activePage = 'dashboard' : globalAssistantOpen = false">{{ assistantInline ? '返回首页' : '×' }}</button></div>
      </header>
      <nav class="assistant-panel-nav" aria-label="助手功能"><button type="button" :class="{ active: assistantView === 'chat' }" @click="assistantView = 'chat'">对话<span v-if="assistantHasUnread" class="assistant-tab-dot" /></button><button type="button" :class="{ active: assistantView === 'tools' }" @click="assistantView = 'tools'">{{ user.role === 'student' ? '学习工具' : user.role === 'teacher' ? '备课工具' : '管理工具' }}</button><button type="button" :class="{ active: assistantView === 'history' }" @click="assistantView = 'history'">历史</button></nav>
      <p v-if="assistantActionError" class="assistant-action-error" role="alert">{{ assistantActionError }}</p>
      <div v-if="canManage&&assistantView==='tools'" class="inline-actions"><button type="button" @click="openTeachingWorkbench('materials')">从资料选编题目</button><button type="button" @click="openTeachingWorkbench('course')">AI 完善课程</button><button type="button" @click="openTeachingWorkbench('schedule')">AI {{ user.role==='teacher'?'调课申请':'辅助排课' }}</button></div>
      <template v-if="assistantView === 'chat'">
        <div class="assistant-context-shell" :class="{ 'is-expanded': assistantContextExpanded }">
        <button type="button" class="assistant-context-toggle" :aria-expanded="assistantContextExpanded" aria-controls="assistant-context-options" @click="assistantContextExpanded = !assistantContextExpanded"><span><strong>{{ user.role === 'admin' ? '管理问答' : assistantSelectedCourse?.title || '全部可访问课程' }}</strong><small>{{ answerModeLabel(assistantActiveMode) }}<template v-if="assistantMaterialScopeBusy"> · 读取资料中</template><template v-else-if="assistantMaterialScopeError"> · 资料读取失败</template></small></span><span v-if="assistantMaterialScopeBusy" class="ui-spinner" aria-hidden="true" /><b>{{ assistantContextExpanded ? '收起设置 ↑' : '课程与设置 ↓' }}</b></button>
        <div v-if="assistantAssignmentContext" class="assistant-focus-banner"><span>{{ assistantAssignmentContext.title }} · {{ assistantAssignmentContext.policy==='guided'?'分步辅导':'思路提示' }}</span><button type="button" :disabled="globalAssistantBusy" @click="assistantAssignmentContext=null; resetAssistantConversation()">结束本题辅导</button></div>
        <div id="assistant-context-options" class="assistant-fixed-context">
          <div class="assistant-chat-context"><span>{{ user.role_label }} · {{ workspaceTitle }}</span><label v-if="user.role !== 'admin'">课程<select v-model="assistantDraftCourseId" :aria-label="user.role === 'student' ? '选择学习课程' : '选择教学课程'"><option value="">未指定课程 · 全部可访问范围</option><option v-for="course in platformCourses" :key="course.id" :value="course.id">{{ course.title }} · {{ course.code }}{{ course.semester ? ` · ${course.semester}` : '' }}</option></select></label></div>
          <div v-if="user.role !== 'admin'" class="assistant-answer-modes" role="group" aria-label="回答模式"><button v-for="option in answerModeOptions" :key="option.value" type="button" :class="{ active: assistantActiveMode === option.value }" :aria-pressed="assistantActiveMode === option.value" :disabled="globalAssistantBusy || assistantHistoryBusy || assistantOlderBusy" @click="setAssistantMode(option.value)">{{ option.label }}</button></div>
          <section v-if="user.role !== 'admin'" class="assistant-material-scope" :class="{ 'is-empty': assistantMaterialScope && !assistantMaterialScope.ready_document_count }" aria-label="当前课程资料范围" :aria-busy="assistantMaterialScopeBusy">
            <p v-if="assistantMaterialScopeBusy" role="status"><span class="ui-spinner" aria-hidden="true" />正在核对课程资料范围…</p>
            <div v-else-if="assistantMaterialScopeError" role="alert"><p>{{ assistantMaterialScopeError }}</p><button type="button" @click="loadAssistantMaterialScope">重新核对 ›</button></div>
            <details v-else-if="assistantMaterialScope"><summary class="assistant-material-heading"><strong>{{ assistantMaterialScope.course_id ? '本课程资料' : '可访问资料' }}</strong><span>{{ assistantMaterialScope.ready_document_count }} 份可检索</span><small>查看范围⌄</small></summary><p>{{ assistantMaterialScope.notice }}</p><ul v-if="assistantMaterialScope.knowledge_bases.length"><li v-for="base in assistantMaterialScope.knowledge_bases" :key="base.id">{{ base.name }}</li></ul><button v-if="assistantMaterialScope.course_id" type="button" @click="openAssistantCourseMaterials(assistantMaterialScope.course_id)">查看本课程资料 ›</button></details>
          </section>
        </div>
        </div>
        <div v-if="globalAssistantBusy" class="assistant-live-progress" role="status"><span class="ui-spinner" aria-hidden="true" /><span><strong>{{ assistantWaitLabel }}</strong><small aria-live="off">已等待 {{ assistantWaitSeconds }} 秒 · 回答会保留在当前对话</small></span><button type="button" @click="stopAssistantWaiting">停止</button></div>
        <div ref="assistantChatScroll" class="assistant-chat-scroll" role="log" aria-label="AI 助手对话" aria-live="polite" aria-relevant="additions text" @scroll.passive="trackAssistantScroll" @wheel.passive="assistantViewport.release" @touchstart.passive="assistantViewport.release" @pointerdown="assistantViewport.release" @keydown="assistantViewport.release">
          <AnswerRecoveryNotice :base="apiBase" :token="token" :owner="user.id" surface="assistant" :known-ids="assistantTurns.flatMap(item => item.requestId ? [item.requestId] : [])" :busy="globalAssistantBusy" @restore="restoreAssistantRequest" />
          <details v-if="assistantHistoryScopeNotice" class="assistant-scope-notice"><summary>历史范围说明 · 续问前请核对</summary><p>{{ assistantHistoryScopeNotice }}</p></details>
          <div v-if="!assistantTurns.length" class="assistant-welcome"><span class="assistant-welcome-icon">✦</span><h3>现在需要我帮你做什么？</h3><p>{{ user.role === 'student' ? '问课程知识、课表或作业。我会优先结合你能访问的课程资料作答，并给出可打开的下一步。' : user.role === 'teacher' ? '备课、出题和分析教学情况；生成内容先由你审核。' : '查看运行情况、解释异常和管理影响；重要操作仍由你确认。' }}</p><div class="assistant-welcome-examples"><button v-for="prompt in assistantPrompts.slice(0, 3)" :key="prompt" type="button" @click="askGlobalAssistant(prompt)">{{ prompt }} <span>↗</span></button></div></div>
          <section v-if="assistantPagedConversationId && (assistantMessageHasMore || assistantLoadedMessageCount > 1)" class="assistant-message-pager" aria-label="会话消息分页">
            <div><strong>已载入 {{ assistantLoadedMessageCount }} 条问答<span v-if="assistantMessageCount !== null"> · 当前可读 {{ assistantMessageCount }} 条</span></strong><small>{{ assistantMessageHasMore ? '更早内容分批读取，不会再次调用模型。' : '已读到这段会话当前可读记录的开头。' }}</small></div>
            <button v-if="assistantMessageHasMore" type="button" :disabled="assistantOlderBusy || globalAssistantBusy || assistantHistoryBusy" @click="loadOlderAssistantMessages"><span v-if="assistantOlderBusy" class="assistant-typing-dots" aria-hidden="true"><i /><i /><i /></span>{{ assistantOlderBusy ? '正在读取更早消息…' : '加载更早的问答 ↑' }}</button>
            <p v-if="assistantOlderError" role="alert">{{ assistantOlderError }} <button type="button" :disabled="assistantOlderBusy || globalAssistantBusy || assistantHistoryBusy" @click="resumeAssistantConversation({ id: assistantPagedConversationId })">重新打开会话</button></p>
          </section>
          <button v-else-if="globalAssistantConversationId && !assistantPagedConversationId" type="button" class="assistant-open-saved" :disabled="globalAssistantBusy || assistantHistoryBusy || assistantOlderBusy" @click="resumeAssistantConversation({ id: globalAssistantConversationId })">查看这段已保存会话 ↗</button>
          <div class="assistant-message-stack">
          <article v-for="turn in assistantTurns" :key="turn.id" class="assistant-turn" :data-message-key="turn.answer?.history_id || `turn-${turn.id}`">
            <p v-if="turn.contextChanged" class="assistant-context-change">已按当前课程、资料与回答模式开启新会话；上方历史仍可查看。</p>
            <div class="assistant-user-message"><small>你<span v-if="turn.courseTitle"> · {{ turn.courseTitle }}</span></small><p>{{ turn.displayQuestion }}</p></div>
            <p v-if="turn.answer?.answer_scope" class="assistant-answer-scope">{{ answerScopeLabel(turn.answer) }}</p>
            <div v-if="turn.answer" class="assistant-response"><div class="assistant-answer-heading"><span>✦</span><div><strong>解答正文</strong><small>{{ answerModeLabel(turn.answer.answer_mode) }} · {{ answerProvenanceLabel(turn.answer) }}</small></div><button type="button" class="assistant-read-button" @click="readAnswer(turn.answer!, turn.question)">专注阅读 ↗</button></div><div v-if="turn.answer.citations.length" class="assistant-reading-links"><button type="button" @click="jumpToAssistantSources($event)">资料依据 · {{ turn.answer.citations.length }} 条 ↓</button><span>点击正文资料编号可查看原文</span></div><RichText :source="turn.answer.answer" navigation presentation :evidence-count="turn.answer.citations.length" @evidence="openAnswerEvidence(turn.answer!, $event)" @layout="assistantAnswerLayout(turn.id)" /><AnswerReviewPanel v-if="turn.answer.answer_review" :review="turn.answer.answer_review" @source="openAnswerEvidence(turn.answer!, $event)" />
            <AnswerAnnotation v-if="turn.answer?.history_id" :key="user.id + turn.answer.history_id" :history-id="turn.answer.history_id" :answer="turn.answer.answer" :citation-count="turn.answer.citations.length" :request="request" />
              <CalculationReceipts v-if="turn.answer.calculations?.length" :records="turn.answer.calculations" :base="apiBase" :token="token" />
              <div v-if="turn.answer.actions?.length" class="assistant-result-actions"><strong>可以继续</strong><button v-for="(action, index) in turn.answer.actions" :key="`${action.kind}-${action.target_id}-${index}`" type="button" @click="openAssistantResponseAction(action)"><span>{{ action.title }}<small>{{ action.detail }}</small></span><b>打开 ›</b></button></div>
              <button v-if="user.role === 'teacher'" class="assistant-save-draft" type="button" :disabled="platformBusy || !turn.courseId" @click="saveAssistantAsTeachingDraft(turn)">保存为教学草稿</button>
              <div v-if="assistantAnswerPassage && assistantNoteTurnId === turn.id" class="assistant-note-editor"><strong>整理为个人笔记 · {{ assistantAnswerPassage.sourceTitle }} 第 {{ assistantAnswerPassage.pageNumber }} 页</strong><textarea v-model="studyNoteDraft" maxlength="10000" rows="5" aria-label="学习笔记内容" /><button type="button" :disabled="studyNoteBusy || !studyNoteDraft.trim()" @click="saveStudyNote(assistantAnswerPassage, 'assistant')">保存学习笔记</button></div>
              <details v-if="turn.answer.citations.length" class="assistant-sources" :open="turn.sourcesExpanded" @toggle="turn.sourcesExpanded=($event.target as HTMLDetailsElement).open;assistantAnswerLayout(turn.id)"><summary><strong>资料依据 · {{ turn.answer.citations.length }} 条</strong><span>{{ turn.sourcesExpanded ? '收起资料 ⌃' : '展开核对原文 ⌄' }}</span></summary><div class="assistant-source-list"><button v-for="(citation,index) in turn.answer.citations" :key="`${citation.document_name}-${citation.page_number}-${index}`" type="button" :disabled="!citation.document_id" @click="openCitation(citation)"><b>{{ index+1 }}</b><span>{{ citation.document_name }}<small>第 {{ citation.page_number }} 页{{ citation.document_id ? '' : ' · 旧记录无定位' }}</small></span><i aria-hidden="true">↗</i></button></div></details>
              <p v-if="turn.answer.model === 'local-evidence'" class="assistant-evidence-note">课程资料尚未获准发送给外部模型。以上只是站内检索片段，并非 AI 归纳或讲解。</p><p v-else-if="turn.answer.model === 'offline-fallback' || turn.answer.model === 'offline'" class="assistant-evidence-note">当前回答由离线方式提供，并非在线 AI 讲解；请核对资料原文。</p><p v-else-if="turn.answer.model === 'platform-data'" class="assistant-evidence-note">以上建议与安排来自平台当前记录；打开后以最新权限和状态为准。</p><div v-else-if="user.role === 'student' && !turn.answer.citations.length" class="assistant-evidence-note">{{ answerEvidenceNote(turn.answer) }}<button v-if="turn.courseId" type="button" @click="openAssistantCourseMaterials(turn.courseId)">查看本课程资料 ›</button></div>
            </div>
            <div v-else-if="turn.partial && globalAssistantBusy" class="assistant-response stream-preview" aria-busy="true"><div class="assistant-answer-heading"><span>✦</span><div><strong>{{ assistantRoleTitle }}</strong><small>正在生成 · 内容尚未完成</small></div></div><RichText :source="turn.partial" streaming @layout="assistantAnswerLayout(turn.id)" /><div class="stream-status"><span class="assistant-typing-dots" aria-hidden="true"><i /><i /><i /></span><small>{{ assistantWaitSeconds }} 秒</small><button type="button" class="stream-stop-button" @click="stopAssistantWaiting">停止生成</button></div></div>
            <div v-else-if="turn.error" class="assistant-turn-error" role="alert"><strong>{{ turn.requestState === 'unknown' || turn.requestState === 'in_progress' ? '处理结果待确认' : turn.requestState === 'cancelled' ? '本次请求已停止' : '这次没有得到完整回答' }}</strong><p>{{ turn.error }}</p><button type="button" :disabled="globalAssistantBusy || turn.checkingReceipt" @click="retryAssistantTurn(turn)">{{ turn.checkingReceipt ? '核对中…' : turn.requestState === 'unknown' || turn.requestState === 'in_progress' ? '查看处理结果 ›' : '重新尝试 ›' }}</button></div>
            <div v-else class="assistant-thinking" role="status"><span class="assistant-thinking-avatar">✦</span><div class="assistant-thinking-body"><strong>{{ assistantWaitLabel }}</strong><div class="assistant-typing-dots" aria-hidden="true"><i /><i /><i /></div><div class="assistant-skeleton" aria-hidden="true"><i /><i /></div><small aria-live="off">已等待 {{ assistantWaitSeconds }} 秒 · {{ assistantWaitingHint }}</small><button type="button" @click="stopAssistantWaiting">停止等待</button></div></div>
          </article>
          </div>
        </div>
        <div v-if="assistantContentBelow || (!assistantFollowing && assistantTurns.length > 1)" class="assistant-return-latest"><span>{{ assistantContentBelow ? (globalAssistantBusy ? '下方有新内容，当前阅读位置已保留' : '回答已更新，当前阅读位置已保留') : '正在查看较早内容' }}</span><button type="button" @click="scrollAssistantToBottom">查看最新 ↓</button></div>
        <div v-if="assistantTurns.length" class="assistant-prompt-strip" aria-label="快捷提问"><button v-for="prompt in assistantPrompts.slice(0, 3)" :key="prompt" type="button" :disabled="globalAssistantBusy" @click="askGlobalAssistant(prompt)">{{ prompt }}</button></div>
      </template>
      <div v-else-if="assistantView === 'tools'" class="assistant-tools-scroll">
        <div v-if="assistantDraftBusy || studyPlanBusy || adminReportBusy" class="assistant-task-progress" role="status"><div class="assistant-typing-dots" aria-hidden="true"><i /><i /><i /></div><strong>{{ assistantDraftBusy ? '正在生成教学草稿…' : studyPlanBusy ? '正在整理学习计划…' : '正在汇总平台运行记录…' }}</strong><small>{{ assistantDraftBusy ? '完成后会打开草稿箱，内容仍需教师审核。' : '完成后会在这里显示结果。' }}</small></div>
        <section v-if="user.role === 'student'" class="assistant-draft-context"><div class="assistant-section-title"><strong>当前学习课程</strong><small>{{ assistantSelectedCourse?.title || '未指定' }}</small></div><p v-if="assistantDraftCourseId && studentCourseKnowledgeBases[assistantDraftCourseId]?.length">优先使用「{{ studentCourseKnowledgeBases[assistantDraftCourseId].map(base => base.name).join('、') }}」中的资料。</p><p v-else-if="assistantDraftCourseId">该课程暂未关联资料，回答会标明未引用课程证据。</p><p v-else>可在“对话”中选择课程。</p></section>
<AssistantTaskPanel v-if="canManage" :key="user.id" :request="request" :refresh="assistantTasksRevision" @open-draft="openCohortDraft" @open-work="openTeachingWorkbench('history','',$event)" />
        <section v-if="user.role === 'teacher'" ref="teacherDraftSettings" class="assistant-draft-context">
          <div class="assistant-section-title"><strong>教学草稿设置</strong><small>生成后由教师审核</small></div>
          <label>选择课程<select v-model="assistantDraftCourseId" :disabled="assistantDraftBusy"><option value="">请选择课程</option><option v-for="course in platformCourses" :key="course.id" :value="course.id">{{ course.title }} · {{ course.code }}</option></select></label>
          <div v-if="teacherFocusTopic" class="assistant-focus-banner"><span>正在准备 · {{ teacherFocusTopic }}</span><button type="button" :disabled="assistantDraftBusy" @click="clearTeacherFocus">取消针对性设置</button></div>
          <label>主题或知识点<input v-model="assistantDraftTopic" :readonly="Boolean(teacherFocusTopic)" maxlength="300" placeholder="可选，例如：二叉树遍历" /></label>
          <label class="assistant-share-consent"><input v-model="assistantShareCourseMaterials" type="checkbox" /><span>我确认有权使用本课程资料，并同意将检索到的相关片段发送给当前模型服务用于生成草稿</span></label>
          <label v-if="teacherFocusTopic" class="assistant-share-consent"><input v-model="teacherAnalysisConsent" type="checkbox" /><span>我同意本次生成时发送本课程匿名学情汇总，不包含学生姓名或原始作答</span></label>
          <div v-if="teacherFocusTopic" class="assistant-focus-actions"><button type="button" :disabled="assistantDraftBusy || platformBusy || (!teacherAnalysisConsent && modelStatus?.llm_provider !== 'offline')" @click="generateAssistantTeachingDraft(teacherDraftIntent)">{{ teacherDraftIntent === 'question_set' ? '生成补充练习草稿' : '生成针对性教案' }}</button><button type="button" class="ghost-button" :disabled="assistantDraftBusy || platformBusy" @click="generateAssistantTeachingDraft('lesson_plan', true)">仅用站内记录准备提纲</button></div>
          <p v-if="!assistantDraftCourseId">选择课程后，可以生成教学计划、教案和题目草稿。</p>
          <p v-else-if="teacherFocusTopic">站内提纲不向模型发送数据。在线草稿会保留本次学情，方便后续回看。</p>
        </section>
        <TeacherInsightsPanel v-if="user.role === 'teacher'" :insights="teacherInsights" :busy="teacherInsightsBusy" :error="teacherInsightsError" :course-id="assistantDraftCourseId" @refresh="loadTeacherInsights" @prepare="prepareTeacherFocus" @review="openTeacherReview" @assignments="openTeacherAssignments" @cohort="openCourseAnalysis(assistantDraftCourseId)" />
        <section class="assistant-action-section"><div class="assistant-section-title"><strong>建议下一步</strong><small>依据当前数据</small></div><button v-for="action in assistantActions" :key="action.id" type="button" class="assistant-action-card" :class="`tone-${action.tone}`" :disabled="platformBusy || (action.id.startsWith('teacher-') && ['teacher-plan', 'teacher-lesson', 'teacher-quiz'].includes(action.id) && !assistantDraftCourseId)" @click="runAssistantAction(action)"><span>{{ action.eyebrow }}</span><div><strong>{{ action.title }}</strong><small>{{ action.detail }}</small></div><b>{{ action.button }} ›</b></button></section>
        <StudyPlanPanel v-if="user.role === 'student'" :key="`${user.id}:${selectedStudyCourseId}`" class="assistant-study-plan" :plan="selectedStudyPlan" :course-id="selectedStudyCourseId" :busy="studyPlanBusy" :request="request" @create="createStudyPlan" @refresh="refreshStudyPlan" @open="openStudyPlanTask" @reload="reloadStudyPlan" />
        <section v-if="user.role === 'student'" class="assistant-study-notes"><div class="assistant-section-title"><strong>我的学习笔记</strong><small>{{ visibleStudyNotes.length }} 条</small></div><p v-if="studyNoteStatus" class="study-note-status" :class="{ 'is-error': studyNoteStatusError }" :role="studyNoteStatusError ? 'alert' : 'status'">{{ studyNoteStatus }}</p><p v-if="!visibleStudyNotes.length">当前课程暂无笔记。打开资料，选中原文即可创建。</p><PagedList :items="visibleStudyNotes" :scope="assistantDraftCourseId" :load-page="pageLoader<StudyNote>('notes', assistantDraftCourseId)" :page-size="6" label="学习笔记" v-slot="{ items: noteItems }"><article v-for="note in noteItems" :key="note.id" class="study-note-card"><strong>{{ note.source_title }} · 第 {{ note.page_number }} 页</strong><small>{{ note.course_title }} · {{ historyTime(note.created_at) }}</small><p>{{ note.content.slice(0, 130) }}{{ note.content.length > 130 ? '…' : '' }}</p><div><button type="button" :disabled="!note.source_available" @click="openStudyNote(note)">{{ note.source_available ? '查看原文 ›' : '原文已下架' }}</button><button type="button" class="danger-soft" :disabled="studyNoteBusy" @click="deleteStudyNote(note)">删除</button></div></article></PagedList></section>
        <section v-if="user.role === 'admin' && (adminReport || adminReportBusy || adminReportError)" class="assistant-report"><div class="assistant-section-title"><strong>平台运行报告</strong><small v-if="adminReport">{{ historyTime(adminReport.generated_at) }}</small></div><div class="assistant-report-periods"><button v-for="days in adminReportPeriods" :key="days" type="button" :class="{ active: adminReport?.period_days === days }" :disabled="adminReportBusy" @click="loadAdminReport(days)">{{ days === 1 ? '今日' : days === 7 ? '本周' : '近30天' }}</button></div><p v-if="adminReportBusy" class="assistant-report-note">正在汇总平台记录…</p><p v-if="adminReportError" class="assistant-report-error">{{ adminReportError }}</p><template v-if="adminReport"><div class="assistant-report-summary" :class="adminReport.overall_status"><strong>{{ adminReport.overall_status === 'healthy' ? '运行正常' : '有待处理事项' }}</strong><small>统计从 {{ historyTime(adminReport.period_start) }} 起</small></div><div class="assistant-report-metrics"><span>课程问答<b>{{ adminReport.metrics.period_rag_questions ?? 0 }}</b></span><span>模型调用<b>{{ adminReport.metrics.period_model_calls ?? 0 }}</b></span><span>异常事件<b>{{ (adminReport.metrics.period_server_errors ?? 0) + (adminReport.metrics.period_model_failures ?? 0) }}</b></span></div><button v-for="check in adminReport.checks" :key="check.id" type="button" class="assistant-report-check" :class="check.status" @click="runAssistantAction({ id: check.action_id, eyebrow: '', title: check.title, detail: check.detail, button: '', tone: 'neutral' })"><span>{{ check.status === 'warning' ? '!' : check.status === 'healthy' ? '✓' : '·' }}</span><div><strong>{{ check.title }}</strong><small>{{ check.detail }}</small></div><b>查看 ›</b></button><button type="button" class="assistant-report-download" @click="downloadAdminReport">下载 Markdown 报告</button></template></section>
      </div>
      <div v-else class="assistant-history-scroll"><div class="assistant-history-heading"><strong>我的对话</strong><span>仅显示当前账号的记录</span></div><p class="assistant-history-hint">搜索当前可访问的历史问题和回答。旧平台统计若缺少完整来源，将保留存档但不回读，可按当前课程重新查询。</p><input v-model="assistantHistoryQuery" class="assistant-history-search" type="search" maxlength="120" aria-label="搜索全部历史对话" placeholder="搜索问题、回答或关键词…" /><p v-if="assistantHistoryBusy" class="assistant-history-loading" role="status"><span class="assistant-typing-dots" aria-hidden="true"><i /><i /><i /></span>正在查找对话…</p><p v-if="assistantHistoryError" class="assistant-history-error" role="alert">{{ assistantHistoryError }} <button type="button" @click="loadAssistantHistory(true)">重试</button></p><button v-for="record in filteredAssistantHistory" :key="record.id" type="button" class="assistant-history-item" :disabled="assistantHistoryBusy || globalAssistantBusy" @click="resumeAssistantConversation(record)"><strong>{{ record.title }}</strong><span>{{ record.message_count }} 条提问 · {{ historyTime(record.updated_at) }}<b v-if="record.id === globalAssistantConversationId">当前</b></span></button><p v-if="!assistantHistoryBusy && !assistantHistoryError && !filteredAssistantHistory.length" class="assistant-history-empty">{{ assistantHistoryQuery.trim() ? '没有匹配的对话，可换个关键词。' : '暂无历史对话，先问一个问题试试。' }}</p><button v-if="assistantHistoryHasMore" class="assistant-history-more" type="button" :disabled="assistantHistoryBusy" @click="loadAssistantHistory(false)">{{ assistantHistoryBusy ? '正在加载…' : '加载更多对话 ↓' }}</button></div>
      <PromptComposer v-if="!compactViewport || assistantView === 'chat'" v-model="globalAssistantQuestion" class="assistant-composer" label="向 AI 助手提问" :placeholder="user.role === 'student' ? '问知识、作业或学习安排…' : user.role === 'teacher' ? '输入备课、出题或教学计划需求…' : '输入平台管理或异常分析需求…'" :send-disabled="globalAssistantBusy || assistantHistoryBusy || assistantOlderBusy" :can-stop="globalAssistantBusy" :submit-label="globalAssistantBusy ? '回答中…' : assistantHistoryBusy || assistantOlderBusy ? '正在读取…' : '发送 ↗'" @submit="askGlobalAssistant()" @stop="stopAssistantWaiting" />
    </aside>
    </Teleport>
    <AccountCenter v-if="accountCenterOpen" :key="user.id" :base="apiBase" :token="token" :user="user" :avatar="accountAvatar" :initial-invite="accountInvite" @close="accountCenterOpen = false; accountInvite = ''" @updated="user.display_name = $event" @avatar-updated="updateAccountAvatar" @changed="loadAppData()" @signout="resetAuthenticatedSession" />
    <AccountManagement v-if="accountManagementOpen && canManage" :key="user.id" :base="apiBase" :token="token" :user="user" :courses="platformCourses" :course-id="accountManagementCourse" @close="accountManagementOpen = false" @changed="loadAppData()" />
    <CourseCohortAnalysisPanel v-if="courseAnalysisOpen && canManage" :course-id="courseAnalysisCourseId" :courses="platformCourses" :enabled="Boolean(modelStatus?.llm_configured && modelStatus.llm_provider !== 'offline')" :request="request" :render-markdown="renderMarkdown" @close="courseAnalysisOpen = false" @course="courseAnalysisCourseId = $event" @assignment="openCohortAssignment" @student="openCohortStudent" @draft="openCohortDraft" @prepare="prepareFromCohort" />
    <AnswerReader v-if="readerAnswer" :question="readerAnswer.question" :content="readerAnswer.answer.answer" :provenance="`${answerModeLabel(readerAnswer.answer.answer_mode)} · ${answerProvenanceLabel(readerAnswer.answer)}`" :citations="readerAnswer.answer.citations" :calculations="readerAnswer.answer.calculations" :base="apiBase" :token="token" @close="readerAnswer = null" @source="openReaderSource" />
    <DetailDialog v-if="pendingAdminConfirmation" :title="pendingAdminConfirmation.title" kicker="确认操作" close-label="取消确认操作" :close-disabled="platformBusy" size="small" alert @close="pendingAdminConfirmation = null"><fieldset :disabled="platformBusy" class="dialog-editor-fields">        <p>{{ pendingAdminConfirmation.detail }}</p>
        <label v-if="pendingAdminConfirmation.kind === 'user_role'" class="admin-confirm-reason">修改原因<textarea v-model="adminRoleReason" minlength="5" maxlength="500" rows="3" placeholder="例如：经课程负责人确认，需调整为教师账号" /></label>
        <label v-if="pendingAdminConfirmation.kind === 'model_quota'" class="admin-confirm-reason">修改原因<textarea v-model="adminQuotaReason" minlength="5" maxlength="500" rows="3" placeholder="例如：课程试用期间调整每日调用额度" /></label>
        <label v-if="pendingAdminConfirmation.kind === 'document_sharing'" class="admin-confirm-reason">核验依据或撤销原因<textarea v-model="documentSharingReason" minlength="8" maxlength="500" rows="3" placeholder="写明已核验的许可及模型服务范围，或撤销原因" /></label>
</fieldset><template #footer>        <div class="admin-confirm-actions"><button type="button" class="secondary" @click="pendingAdminConfirmation = null">取消</button><button type="button" :disabled="platformBusy || (pendingAdminConfirmation.kind === 'user_role' && adminRoleReason.trim().length < 5) || (pendingAdminConfirmation.kind === 'model_quota' && adminQuotaReason.trim().length < 5) || (pendingAdminConfirmation.kind === 'document_sharing' && documentSharingReason.trim().length < 8)" @click="confirmAdminAction">确认执行</button></div>
</template></DetailDialog>
    <UnsavedChangesDialog v-if="pendingFormExit" :labels="pendingFormExit.groups.map(item => item.label)" :action="pendingFormExit.action" :can-stash="pendingFormExit.groups.every(item => item.id === 'draft')" @cancel="pendingFormExit = null" @discard="discardFormsAndContinue" @stash="stashTeachingAndContinue" />
  </main>
  <aside v-if="pageAssetsStale" class="page-update-notice" role="alert"><div><strong>页面资源已更新</strong><p>{{ busy || globalAssistantBusy ? '请先停止或等待当前生成结束，再刷新界面。' : '请刷新加载完整页面。已提交的问题可从历史或处理回执恢复，当前输入不会被自动清除。' }}</p></div><button type="button" :disabled="busy || globalAssistantBusy" @click="reloadUpdatedPage">刷新界面</button></aside>
</template>
