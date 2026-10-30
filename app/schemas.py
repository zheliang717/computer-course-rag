from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field
from app.calculations import CalculationReceipt


AnswerMode = Literal["rag", "general", "hybrid"]
PageItem = TypeVar("PageItem")


class PageResponse(BaseModel, Generic[PageItem]):
    items: list[PageItem]
    total: int
    page: int
    page_size: int


class TextPageInput(BaseModel):
    document_id: str = Field(min_length=1)
    document_name: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    text: str = Field(min_length=1)
    chapter: str | None = None


class ImportTextsRequest(BaseModel):
    pages: list[TextPageInput] = Field(min_length=1)


class TextDocumentPageInput(BaseModel):
    page_number: int = Field(ge=1)
    text: str = Field(min_length=10, max_length=100000)
    chapter: str | None = Field(default=None, max_length=500)
    index_for_retrieval: bool = True


class TextDocumentImportRequest(BaseModel):
    document_id: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=500)
    source_url: str = Field(min_length=1, max_length=3000)
    license_name: str = Field(min_length=1, max_length=200)
    license_url: str = Field(min_length=1, max_length=3000)
    version_label: str = Field(min_length=1, max_length=80)
    publication_status: Literal["draft", "published"] = "draft"
    chunk_size: int | None = Field(default=None, ge=100, le=2000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=500)
    structure_aware: bool = False
    pages: list[TextDocumentPageInput] = Field(min_length=1, max_length=100)


class ImportTextsResponse(BaseModel):
    imported_chunks: int
    total_chunks: int


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    course: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class KnowledgeBaseUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    course: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class KnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    course: str
    description: str | None
    document_count: int
    created_at: datetime | None


class DocumentResponse(BaseModel):
    id: str
    knowledge_base_id: str
    name: str
    source_url: str | None
    license_name: str | None
    license_url: str | None
    external_model_allowed: bool = False
    version_label: str
    publication_status: str
    status: str
    page_count: int | None
    chunk_count: int
    error_message: str | None
    created_at: datetime | None


class DocumentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=500)
    source_url: str | None = Field(default=None, max_length=3000)
    license_name: str | None = Field(default=None, max_length=200)
    license_url: str | None = Field(default=None, max_length=3000)
    version_label: str | None = Field(default=None, min_length=1, max_length=80)
    publication_status: Literal["draft", "published", "archived"] | None = None


class DocumentExternalSharingUpdate(BaseModel):
    allowed: bool
    reason: str = Field(min_length=8, max_length=500)
    confirmed: bool = False


class DocumentChunkPreview(BaseModel):
    id: str
    page_number: int
    chapter: str | None
    position: int
    content: str


class DocumentPagePreview(BaseModel):
    page_number: int
    chapter: str | None
    content: str
    chunks: list[DocumentChunkPreview]


class DocumentContentResponse(BaseModel):
    document: DocumentResponse
    pages: list[DocumentPagePreview]


class DocumentImportResponse(ImportTextsResponse):
    document: DocumentResponse


class DocumentIngestionJobResponse(BaseModel):
    id: str
    knowledge_base_id: str
    document_id: str
    filename: str
    status: Literal["queued", "processing", "completed", "failed", "cancelled"]
    progress_percent: int
    attempts: int
    page_count: int | None
    chunk_count: int | None
    error_message: str | None
    created_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None


class RetrieveRequest(BaseModel):
    request_id: UUID | None = None
    question: str = Field(min_length=1)
    knowledge_base_id: str | None = None
    answer_mode: AnswerMode = "hybrid"
    conversation_id: str | None = None
    quick_action: Literal["follow_up", "simplify", "example", "practice"] | None = None
    assistant_scope: Literal["course_qa", "teaching", "management"] | None = None
    assistant_course_id: UUID | None = None
    assistant_assignment_id: UUID | None = None
    assistant_assignment_question_id: UUID | None = None
    source_document_id: UUID | None = None
    page_context: str | None = Field(default=None, max_length=1000)
    expected_domain_key: str | None = Field(default=None, pattern=r'^[0-9a-f]{64}$')


class Citation(BaseModel):
    document_name: str
    page_number: int
    chapter: str | None
    text: str
    score: float
    document_id: str | None = None
    chunk_id: str | None = None


class RetrieveResponse(BaseModel):
    accepted: bool
    message: str
    citations: list[Citation]


class AssistantResponseAction(BaseModel):
    kind: Literal["course", "assignment", "wrong_question", "study_plan", "teacher_plan", "teacher_questions", "course_analysis", "admin_tasks"]
    target_id: str
    title: str
    detail: str
    topic: str | None = Field(default=None, max_length=200)


class AskResponse(RetrieveResponse):
    assignment_context: dict | None = None
    answer: str
    model: str
    answer_mode: AnswerMode
    history_id: str | None = None
    conversation_id: str | None = None
    actions: list[AssistantResponseAction] = Field(default_factory=list)
    answer_scope: dict | None = None
    calculations: list[CalculationReceipt] = Field(default_factory=list)
    answer_review: dict | None = None


class AnswerRequestState(BaseModel):
    request_id: str
    status: Literal['in_progress', 'completed', 'cancelled', 'failed']
    question: str
    context: dict
    answer: AskResponse | None = None
    error_status: int | None = None
    message: str
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None
    can_retry: bool


class AnswerCancelRequest(BaseModel):
    reason: Literal['user', 'context_change', 'reset'] = 'user'


class HistoryItem(BaseModel):
    assignment_context: dict | None = None
    id: str
    answer_mode: AnswerMode | None = None
    answer_mode_source: Literal['saved', 'request_receipt', 'unknown'] = 'unknown'
    knowledge_base_id: str | None
    conversation_id: str | None = None
    assistant_course_id: str | None = None
    assistant_scope: Literal['course_qa', 'teaching', 'management'] | None = None
    context_verified: bool = False
    answer_scope: dict | None = None
    calculations: list[CalculationReceipt] = Field(default_factory=list)
    answer_review: dict | None = None
    question: str
    answer: str
    message: str
    model: str
    accepted: bool
    citations: list[Citation]
    actions: list[AssistantResponseAction] = Field(default_factory=list)
    rating: int | None
    feedback: str | None
    favorite: bool = False
    created_at: datetime | None


class TutorConversationResponse(BaseModel):
    id: str
    knowledge_base_id: str | None
    title: str
    message_count: int
    created_at: datetime | None
    updated_at: datetime | None


class TutorMessagePage(BaseModel):
    conversation_id: str
    knowledge_base_id: str | None
    items: list[HistoryItem]
    message_count: int
    has_more: bool
    next_before: str | None


class FavoriteUpdate(BaseModel):
    favorite: bool


class AnswerExportResponse(BaseModel):
    filename: str
    content: str


class FeedbackRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    feedback: str | None = Field(default=None, max_length=2000)


class QuestionReviewRequest(BaseModel):
    status: Literal["approved", "rejected"]
    revised_answer: str | None = Field(default=None, max_length=20000)
    review_note: str | None = Field(default=None, max_length=3000)
    publish_to_knowledge_base: bool = False


class QuestionReviewItem(HistoryItem):
    review_status: Literal["pending", "approved", "rejected"]
    revised_answer: str | None = None
    review_note: str | None = None
    reviewer_name: str | None = None
    published_document_id: str | None = None
    reviewed_at: datetime | None = None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=80)
    password: str = Field(min_length=1, max_length=200)
    remember_me: bool = Field(default=False, strict=True)
    challenge_id: str = Field(default='', max_length=80)
    challenge_answer: str = Field(default='', max_length=12)


class UserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    role_label: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 8 * 60 * 60
    remember_me: bool = False
    browser_session: str | None = None
    user: UserResponse


class SystemStatusResponse(BaseModel):
    auth_required: bool
    llm_provider: str
    llm_model: str
    llm_configured: bool
    embedding_provider: str
    indexed_chunks: int


class CourseCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    code: str = Field(min_length=2, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    description: str | None = Field(default=None, max_length=3000)
    semester: str | None = Field(default=None, max_length=80)
    cover_image_url: str | None = Field(default=None, max_length=1000)
    schedule: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    status: Literal["draft", "published", "archived"] = "draft"


class CourseUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=3000)
    semester: str | None = Field(default=None, max_length=80)
    cover_image_url: str | None = Field(default=None, max_length=1000)
    schedule: str | None = Field(default=None, max_length=200)
    location: str | None = Field(default=None, max_length=200)
    status: Literal["draft", "published", "archived"] | None = None


class CourseSectionCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    position: int = Field(ge=1, le=999)


class CourseSectionResponse(BaseModel):
    id: str
    title: str
    description: str | None
    position: int


class CourseSessionCreate(BaseModel):
    section_id: str | None = None
    title: str = Field(min_length=1, max_length=200)
    session_date: datetime
    duration_minutes: int = Field(default=90, ge=15, le=480)
    location: str | None = Field(default=None, max_length=200)


class CourseSessionUpdate(BaseModel):
    completed: bool | None = None
    session_date: datetime | None = None
    duration_minutes: int | None = Field(default=None, ge=15, le=480)
    location: str | None = Field(default=None, max_length=200)


class CourseSessionResponse(BaseModel):
    id: str
    course_id: str
    section_id: str | None
    section_title: str | None
    title: str
    session_date: datetime
    duration_minutes: int
    location: str | None
    completed: bool
    schedule_status: str = 'scheduled'
    revision: int = 1
    rule_id: str | None = None


class CourseResponse(BaseModel):
    id: str
    title: str
    code: str
    description: str | None
    learning_objectives: str = ''
    assessment: str = ''
    semester: str | None
    cover_image_url: str | None
    teacher_name: str | None
    schedule: str | None
    location: str | None
    status: str
    owner_id: str | None
    section_count: int
    class_count: int
    student_count: int
    created_at: datetime | None
    sections: list[CourseSectionResponse] = Field(default_factory=list)


class CourseClassCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    invite_code: str | None = Field(default=None, min_length=4, max_length=32, pattern=r"^[A-Za-z0-9_-]+$")


class CourseClassResponse(BaseModel):
    id: str
    course_id: str
    course_title: str
    name: str
    invite_code: str
    status: str
    teacher_id: str | None
    student_count: int
    created_at: datetime | None


class JoinClassRequest(BaseModel):
    invite_code: str = Field(min_length=4, max_length=32)


class ClassMemberResponse(BaseModel):
    enrollment_id: str
    user_id: str
    username: str
    display_name: str
    status: str
    joined_at: datetime | None


class ClassMemberUpdate(BaseModel):
    status: Literal["active", "removed"]


class CourseMemberAdd(BaseModel):
    username: str = Field(min_length=1, max_length=80)


class ClassAnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)


class ClassAnnouncementResponse(BaseModel):
    id: str
    class_id: str
    title: str
    content: str
    author_name: str
    published_at: datetime | None


class CourseAnnouncementCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=10000)


class CourseAnnouncementResponse(BaseModel):
    id: str
    course_id: str
    title: str
    content: str
    author_name: str
    published_at: datetime | None


class CourseAnnouncementPageResponse(BaseModel):
    items: list[CourseAnnouncementResponse]
    total: int
    page: int
    page_size: int


class DashboardSummaryResponse(BaseModel):
    role: str
    course_count: int
    class_count: int
    student_count: int
    pending_tasks: int
    question_count: int = 0
    course_membership_count: int = 0
    pending_review_count: int = 0
    pending_late_count: int = 0
    overdue_unsubmitted_count: int = 0
    document_count: int = 0
    indexed_chunk_count: int = 0
    as_of: datetime | None = None
    recent_courses: list[CourseResponse]


class QuestionCreate(BaseModel):
    course_id: str
    section_id: str | None = None
    question_type: Literal["single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"] = "single_choice"
    stem: str = Field(min_length=2, max_length=5000)
    options: list[str] = Field(default_factory=list, max_length=10)
    correct_answer: str = Field(min_length=1, max_length=2000)
    explanation: str | None = Field(default=None, max_length=5000)
    difficulty: int = Field(default=2, ge=1, le=5)
    knowledge_point: str | None = Field(default=None, max_length=200)


class QuestionResponse(BaseModel):
    id: str
    course_id: str
    section_id: str | None
    question_type: str
    stem: str
    options: list[str]
    correct_answer: str | None = None
    explanation: str | None = None
    difficulty: int
    knowledge_point: str | None


class QuestionUpdate(BaseModel):
    section_id: str | None = None
    question_type: Literal["single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"] | None = None
    stem: str | None = Field(default=None, min_length=2, max_length=5000)
    options: list[str] | None = Field(default=None, max_length=10)
    correct_answer: str | None = Field(default=None, min_length=1, max_length=2000)
    explanation: str | None = Field(default=None, max_length=5000)
    difficulty: int | None = Field(default=None, ge=1, le=5)
    knowledge_point: str | None = Field(default=None, max_length=200)


class QuestionPageResponse(BaseModel):
    items: list[QuestionResponse]
    total: int
    page: int
    page_size: int


class TeachingDraftCreate(BaseModel):
    course_id: str
    draft_type: Literal["teaching_plan", "lesson_plan", "question_set", "assignment", "review"]
    title: str = Field(min_length=2, max_length=200)
    content: str = Field(min_length=2, max_length=30000)
    source_context: dict = Field(default_factory=dict)


class TeachingDraftGenerate(BaseModel):
    course_id: str
    draft_type: Literal["teaching_plan", "lesson_plan", "question_set", "assignment", "review"]
    topic: str | None = Field(default=None, max_length=300)
    question_count: int = Field(default=5, ge=1, le=20)
    share_course_materials: bool = False
    include_course_insights: bool = False
    focus_knowledge_point: str | None = Field(default=None, min_length=1, max_length=200)
    confirm_external_analysis: bool = False
    local_only: bool = False


class TeachingDraftUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    content: str | None = Field(default=None, min_length=2, max_length=30000)
    status: Literal["draft", "confirmed", "archived"] | None = None
    questions: list["QuestionDraftItem"] | None = Field(default=None, max_length=50)


class QuestionDraftItem(BaseModel):
    question_type: Literal["single_choice", "multiple_choice", "true_false", "fill_blank", "short_answer"]
    stem: str = Field(min_length=2, max_length=5000)
    options: list[str] = Field(default_factory=list, max_length=10)
    correct_answer: str = Field(default='', max_length=2000)
    source_id: str | None = Field(default=None, max_length=64)
    explanation: str | None = Field(default=None, max_length=5000)
    difficulty: int = Field(default=2, ge=1, le=5)
    knowledge_point: str | None = Field(default=None, max_length=200)


class AnalysisBasisResponse(BaseModel):
    draft_id: str
    kind: Literal['review', 'student_analysis']
    assignment_id: str
    status: Literal['saved', 'legacy', 'unavailable']
    captured_at: datetime | None
    input_kind: Literal['online', 'local_outline'] | None
    stale: bool | None
    facts: dict
    questions: PageResponse[dict]
    work: PageResponse[dict]
    notice: str
    scope_note: str
    content_edited: bool | None = None
    original_content: str | None = None
    content_notes: list[dict] = Field(default_factory=list)


class TeachingDraftResponse(BaseModel):
    id: str
    course_id: str
    course_title: str
    creator_id: str | None
    draft_type: str
    title: str
    content: str
    source_context: dict
    questions: list[QuestionDraftItem]
    status: str
    confirmed_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None


class StudentAnswerAnalysisRequest(BaseModel):
    confirm_external_analysis: bool = False


class StudentAnswerQuestionAnalysis(BaseModel):
    question_id: str
    observation: str = Field(min_length=2, max_length=1800)
    next_step: str = Field(min_length=2, max_length=1200)


class StudentAnswerAnalysisContent(BaseModel):
    summary: str = Field(min_length=2, max_length=2000)
    question_reviews: list[StudentAnswerQuestionAnalysis] = Field(min_length=1, max_length=12)
    teaching_suggestions: list[str] = Field(min_length=1, max_length=6)
    feedback_draft: str = Field(min_length=2, max_length=2000)


class StudentAnswerAnalysisResponse(BaseModel):
    draft: TeachingDraftResponse
    analysis: StudentAnswerAnalysisContent
    student_name: str
    stale: bool
    question_count_total: int
    question_count_analyzed: int
    content_edited: bool | None = None


class CourseCohortStudentSuggestion(BaseModel):
    student_id: str
    reason: str = Field(min_length=2, max_length=1000)
    next_step: str = Field(min_length=2, max_length=1000)


class CourseCohortAnalysisContent(BaseModel):
    summary: str = Field(min_length=2, max_length=2500)
    strengths: list[str] = Field(max_length=6)
    concerns: list[str] = Field(min_length=1, max_length=6)
    teaching_actions: list[str] = Field(min_length=1, max_length=6)
    student_suggestions: list[CourseCohortStudentSuggestion] = Field(max_length=12)
    evidence_note: str | None = None


class CourseCohortAnalysisRequest(BaseModel):
    confirm_external_analysis: bool = False


class CourseCohortCoverage(BaseModel):
    student_count_total: int
    student_count_included: int
    assignment_count_total: int
    assignment_count_included: int


class CourseCohortAnalysisResponse(BaseModel):
    draft: TeachingDraftResponse
    analysis: CourseCohortAnalysisContent
    stale: bool
    coverage: CourseCohortCoverage
    students: list[dict]
    overview: dict


class DraftQualityFinding(BaseModel):
    question_index: int
    severity: Literal["error", "warning"]
    code: str
    message: str
    related_question_index: int | None = None
    related_question_id: str | None = None


class DraftQualityReport(BaseModel):
    draft_id: str
    question_count: int
    error_count: int
    warning_count: int
    findings: list[DraftQualityFinding]


class DraftAIReviewRequest(BaseModel):
    question_index: int = Field(ge=1, le=50)
    confirm_external_review: bool = False
    request_id: UUID | None = None
    require_calculation: bool = False


class DraftReviewAnchor(BaseModel):
    kind: Literal['question', 'source', 'calculation']
    field: Literal['stem', 'options', 'correct_answer', 'explanation', 'knowledge_point'] | None = None
    source_index: int | None = Field(default=None, ge=1, le=3)
    reference: str | None = Field(default=None, max_length=20)
    step_index: int | None = Field(default=None, ge=1, le=20)
    quote: str | None = Field(default=None, min_length=1, max_length=500)


class DraftAIReviewProposal(BaseModel):
    category: Literal["ambiguity", "answer", "explanation", "other"]
    detail: str = Field(min_length=2, max_length=600)
    suggestion: str = Field(min_length=2, max_length=600)
    assessment: Literal['issue', 'improvement', 'uncertain'] = 'uncertain'
    claim_type: Literal['internal_consistency', 'numeric', 'source_conflict', 'teaching_improvement', 'open_question'] = 'open_question'
    anchors: list[DraftReviewAnchor] = Field(default_factory=list, max_length=3)


class DraftResolvedAnchor(DraftReviewAnchor):
    matched: bool
    label: str
    excerpt: str
    reason: str
    document_id: str | None = None
    page_number: int | None = None


class DraftAIReviewFinding(BaseModel):
    category: Literal['ambiguity', 'answer', 'explanation', 'other']
    detail: str
    suggestion: str
    id: str | None = None
    assessment: Literal['issue', 'improvement', 'uncertain'] = 'uncertain'
    original_assessment: str | None = None
    claim_type: str = 'open_question'
    basis_status: Literal['linked', 'missing', 'invalid', 'legacy'] = 'legacy'
    basis_note: str = '旧版未记录逐条依据，不能据此确认缺陷。'
    anchors: list[DraftResolvedAnchor] = Field(default_factory=list)


class DraftAIReviewEvidence(BaseModel):
    document_id: str
    document_name: str
    page_number: int
    chunk_id: str


class DraftAIReviewResponse(BaseModel):
    draft_id: str
    question_index: int
    summary: str = Field(min_length=2, max_length=800)
    findings: list[DraftAIReviewFinding] = Field(max_length=8)
    suggested_stem: str | None = Field(default=None, max_length=5000)
    evidence: list[DraftAIReviewEvidence]
    grounded: bool
    review_id: str | None = None
    suggested_correct_answer: str | None = Field(default=None, max_length=2000)
    suggested_explanation: str | None = Field(default=None, max_length=5000)
    calculations: list[CalculationReceipt] = Field(default_factory=list)
    analysis_version: int = 1
    basis_summary: str = '旧版未记录逐条依据；原概述未经逐句核实。'
    suggestion_basis: dict[str, list[str]] = Field(default_factory=dict)
    suggestion_notes: dict[str, str] = Field(default_factory=dict)


class ReviewDecisionCreate(BaseModel):
    request_id: UUID
    finding_id: str = Field(pattern=r'^[0-9a-f]{32}$')
    expected_question_fingerprint: str = Field(pattern=r'^[0-9a-f]{64}$')
    decision: Literal['follow_up', 'dismissed', 'needs_check']
    reason: str = Field(min_length=5, max_length=500)


class ReviewDecisionResponse(BaseModel):
    id: str
    review_id: str
    finding_id: str
    actor_name: str
    decision: str
    reason: str
    question_fingerprint: str
    created_at: datetime


class QuestionReviewCreate(BaseModel):
    request_id: UUID
    question_index: int = Field(ge=1, le=50)
    expected_question: QuestionDraftItem
    confirm_external_review: bool = False
    require_calculation: bool = False


class QuestionReviewState(BaseModel):
    id: str
    request_id: str
    draft_id: str
    question_index: int
    question_fingerprint: str
    calculation_required: bool = False
    question_snapshot: QuestionDraftItem
    status: Literal['processing', 'completed', 'cancelled', 'failed']
    stage: str
    message: str
    stale: bool
    source_available: bool
    result: DraftAIReviewResponse | None
    created_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class AssignmentCreate(BaseModel):
    course_id: str | None = None
    class_id: str | None = None
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=3000)
    question_ids: list[str] = Field(min_length=1, max_length=100)
    due_at: datetime | None = None
    status: Literal["draft", "published"] | None = None


class AssignmentResponse(BaseModel):
    id: str
    course_id: str
    class_id: str | None
    course_title: str
    source_draft_id: str | None = None
    revision: int = 1
    ai_policy: Literal['disabled', 'hints', 'guided'] = 'hints'
    previous_version_id: str | None = None
    title: str
    description: str | None
    status: str
    due_at: datetime | None
    question_count: int
    submission_count: int
    submitted: bool
    submission_status: str | None = None
    submitted_answers: dict[str, str] | None = None
    score: float | None = None
    max_score: float | None = None
    teacher_feedback: str | None = None
    late_request_status: str | None = None
    late_approved_until: datetime | None = None
    created_at: datetime | None


class AssignmentDetailResponse(AssignmentResponse):
    questions: list[QuestionResponse]


class DraftAssignmentCreate(BaseModel):
    model_config = {'extra': 'forbid'}
    request_id: UUID
    expected_signature: str = Field(pattern=r'^[0-9a-f]{64}$')
    title: str = Field(min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=3000)
    due_at: datetime | None = None
    confirmed: Literal[True]


class DraftAssignmentPreview(BaseModel):
    draft_id: str
    course_id: str
    course_title: str
    request_id: str
    expected_signature: str
    default_title: str
    question_count: int
    questions: list[dict]
    current_student_count: int
    ready: bool
    problems: list[str]
    findings: list[dict]
    notice: str


class DraftAssignmentReceipt(BaseModel):
    assignment_id: str
    source_draft_id: str
    course_id: str
    title: str
    status: str
    created_at: datetime
    reused: bool


class TeachingWorkflowResponse(BaseModel):
    draft_id: str
    course_id: str
    course_title: str
    draft_status: str
    generated_at: datetime
    published_at: datetime | None
    published_question_count: int
    available_question_count: int
    missing_question_count: int
    current_student_count: int
    linked_assignment_count: int
    assignment_statuses: dict[str, int]
    independent_practice: dict | None
    note: str


class DraftAssignmentProgress(BaseModel):
    id: str
    title: str
    status: str
    due_at: datetime | None
    created_at: datetime
    question_count: int
    current_student_count: int
    active_submission_count: int
    all_submission_count: int
    graded_count: int
    pending_review_count: int
    unsubmitted_count: int | None
    submission_percent: float | None
    average_score_percent: float | None
    has_published_review: bool


class AssignmentReviewDraftRequest(BaseModel):
    confirm_external_analysis: bool = False
    local_only: bool = False
    include_student_answers: bool = False


class AssignmentPublishedReviewResponse(BaseModel):
    assignment_id: str
    draft_id: str
    title: str
    content: str
    published_at: datetime | None
    stale: bool = False


class AssignmentSubmitRequest(BaseModel):
    answers: dict[str, str]


class SubmissionResponse(BaseModel):
    id: str
    assignment_id: str
    score: float
    max_score: float
    correct_count: int
    total_count: int
    status: str
    submitted_at: datetime | None


class AssignmentStatusUpdate(BaseModel):
    status: Literal["draft", "published", "closed"]


class LateSubmissionCreate(BaseModel):
    reason: str = Field(min_length=2, max_length=2000)


class LateSubmissionReview(BaseModel):
    status: Literal["approved", "rejected"]
    review_note: str | None = Field(default=None, max_length=2000)
    approved_until: datetime | None = None


class LateSubmissionResponse(BaseModel):
    id: str
    assignment_id: str
    assignment_title: str
    student_id: str
    student_name: str
    reason: str
    status: str
    reviewer_name: str | None
    review_note: str | None
    approved_until: datetime | None
    requested_at: datetime | None
    reviewed_at: datetime | None
    used_at: datetime | None


class SubmissionGradeRequest(BaseModel):
    score: float = Field(ge=0)
    feedback: str | None = Field(default=None, max_length=5000)
    expected_version: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')


class SubmissionDetailResponse(BaseModel):
    id: str
    assignment_id: str
    student_id: str
    student_name: str
    answers: dict[str, str]
    score: float
    max_score: float
    status: str
    feedback: str | None
    submitted_at: datetime | None
    graded_at: datetime | None
    grading_version: str = ''


class WrongQuestionResponse(BaseModel):
    id: str
    question: QuestionResponse
    wrong_count: int
    retry_count: int = 0
    correct_streak: int = 0
    last_answer: str | None
    mastered: bool
    last_practiced_at: datetime | None = None
    updated_at: datetime | None


class PracticeRecommendationResponse(BaseModel):
    question: QuestionResponse
    priority: int
    reason: str
    source: Literal["wrong_question", "diagnostic", "spaced_review", "weak_variant", "taught_review"]
    policy_mix: dict[str, int] = Field(default_factory=dict)
    retry_count: int


class PracticeAttemptRequest(BaseModel):
    answer: str = Field(max_length=10000)
    request_id: UUID | None = None


class PracticeAttemptResponse(BaseModel):
    attempt_id: str | None = None
    question_id: str
    is_correct: bool | None
    needs_review: bool
    correct_answer: str | None
    explanation: str | None
    correct_streak: int
    mastered: bool
    message: str


class PracticeFeedbackContent(BaseModel):
    summary: str = Field(min_length=2, max_length=500)
    strengths: list[str] = Field(max_length=3)
    misconceptions: list[str] = Field(max_length=3)
    explanation: str = Field(min_length=2, max_length=5000)
    next_steps: list[str] = Field(min_length=1, max_length=3)
    self_check: str = Field(min_length=2, max_length=600)


class PracticeFeedbackResponse(BaseModel):
    attempt_id: str
    question_id: str
    course_id: str
    course_title: str
    knowledge_point: str
    submitted_answer: str
    attempted_at: datetime
    is_correct: bool | None
    question_attempt_count: int
    question_correct_count: int
    analysis: PracticeFeedbackContent | None
    state: Literal["not_generated", "processing", "ready", "failed"]
    stale: bool
    reused: bool = False
    next_question: QuestionResponse | None = None
    source_label: str = "题目、解析与本次作答；不含教材检索引用"


class KnowledgeBaseBindingRequest(BaseModel):
    knowledge_base_id: str


class CourseKnowledgeBaseResponse(BaseModel):
    id: str
    name: str
    course: str
    description: str | None
    created_at: datetime | None


class KnowledgePointCreate(BaseModel):
    section_id: str | None = None
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=3000)


class KnowledgePointResponse(BaseModel):
    id: str
    course_id: str
    section_id: str | None
    name: str
    description: str | None


class LearningProgressUpdate(BaseModel):
    course_id: str
    section_id: str
    progress_percent: float = Field(ge=0, le=100)


class SectionProgressResponse(BaseModel):
    section_id: str
    section_title: str
    progress_percent: float
    mastery_percent: float


class LearningReportResponse(BaseModel):
    course_id: str
    course_title: str
    progress_percent: float
    mastery_percent: float
    assignment_count: int
    completed_assignments: int
    average_score: float
    wrong_question_count: int
    completed_sessions: int
    session_count: int
    sections: list[SectionProgressResponse]


class StudyPlanPreferences(BaseModel):
    focus: Literal["balanced", "assignments", "review"] = "balanced"
    daily_minutes: Literal[10, 20, 40, 60] = 20


class StudyPlanCreate(BaseModel):
    course_id: str
    preferences: StudyPlanPreferences | None = None


class StudyPlanRefresh(BaseModel):
    model_config = {"extra": "forbid"}
    preferences: StudyPlanPreferences | None = None


class StudyPlanItemResponse(BaseModel):
    id: str
    kind: Literal["assignment", "wrong_review", "section_preview", "course_review", "wrong_question", "practice_question"]
    target_id: str | None
    title: str
    detail: str
    due_at: datetime | None
    available: bool
    completed: bool | None
    status: str = "pending"
    status_message: str = ""
    action_label: str = "打开"
    estimated_minutes: int | None = None
    knowledge_point: str | None = None
    attempt_id: str | None = None
    completed_at: datetime | None = None


class StudyPlanResponse(BaseModel):
    id: str
    course_id: str
    course_title: str
    created_at: datetime | None
    items: list[StudyPlanItemResponse]
    actionable_count: int
    completed_count: int
    revision: int = 1
    previous_plan_id: str | None = None
    preferences: StudyPlanPreferences = Field(default_factory=StudyPlanPreferences)
    needs_refresh: bool = False
    legacy_plan: bool = False
    refresh_notice: str = ""
    change_summary: dict = Field(default_factory=dict)
    next_item_id: str | None = None
    feedback: str = ""
    source_label: str = "依据本人课程、作业和练习记录整理；不是模型生成的能力评价"


class StudyPlanTargetResponse(BaseModel):
    kind: Literal["assignment", "question", "practice_feedback", "section", "course"]
    course_id: str
    target_id: str
    attempt_id: str | None = None
    practice_source: Literal["wrong_question", "diagnostic"] | None = None


class StudyNoteCreate(BaseModel):
    course_id: UUID
    document_id: UUID
    page_number: int = Field(ge=1)
    excerpt: str = Field(min_length=10, max_length=1200)
    content: str = Field(min_length=1, max_length=10000)
    origin: Literal["excerpt", "assistant"] = "excerpt"


class StudyNoteResponse(BaseModel):
    id: str
    course_id: str
    course_title: str
    document_id: str | None
    source_title: str
    page_number: int
    excerpt: str
    content: str
    origin: Literal["excerpt", "assistant"]
    source_available: bool
    created_at: datetime | None


class ClassAnalyticsResponse(BaseModel):
    class_id: str
    class_name: str
    course_title: str
    student_count: int
    assignment_count: int
    submission_rate: float
    average_score: float
    average_progress: float
    weak_knowledge_points: list[str]


class CourseAnalyticsResponse(BaseModel):
    course_id: str
    course_title: str
    student_count: int
    assignment_count: int
    submission_rate: float
    average_score: float
    average_progress: float
    weak_knowledge_points: list[str]


class TeachingWeakPointResponse(BaseModel):
    topic: str
    unresolved_students: int
    unresolved_questions: int
    recorded_mistakes: int


class TeachingInsightsResponse(BaseModel):
    course_id: str
    course_title: str
    generated_at: datetime
    student_count: int
    assignment_count: int
    pending_review_count: int
    weak_points: list[TeachingWeakPointResponse]
    focus: dict | None = None
    assignments: list[dict]


class TeachingImpactResponse(BaseModel):
    draft_id: str
    course_id: str
    topic: str | None
    generated_at: datetime
    baseline: dict
    current_focus: dict | None
    current_student_count: int
    published_at: datetime | None
    published_question_count: int
    published_question_practice: dict | None
    note: str


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=3, max_length=80, pattern=r"^[A-Za-z0-9_-]+$")
    display_name: str = Field(min_length=1, max_length=120)
    role: Literal["student", "teacher", "admin"]
    password: str = Field(min_length=8, max_length=200)
    confirmed: bool = False


class AdminUserUpdate(BaseModel):
    active: bool
    confirmed: bool = False


class AdminUserRoleUpdate(BaseModel):
    role: Literal["student", "teacher", "admin"]
    reason: str = Field(min_length=5, max_length=500)
    confirmed: bool = False


class AdminUserResponse(BaseModel):
    id: str
    username: str
    display_name: str
    role: str
    active: bool
    created_at: datetime | None


class AdminMetricsResponse(BaseModel):
    user_count: int
    course_count: int
    class_count: int
    knowledge_base_count: int
    document_count: int
    indexed_chunk_count: int
    question_count: int
    assignment_count: int
    rag_question_count: int
    average_feedback: float
    document_status: dict[str, int]


class ModelConfigValues(BaseModel):
    provider: Literal["offline", "openai", "compatible"]
    model: str = Field(min_length=1, max_length=200)
    api_base: str = Field(min_length=8, max_length=500)
    api_key: str | None = Field(default=None, max_length=1000)
    timeout_seconds: float = Field(default=60, ge=3, le=300)
    fallback_offline: bool = True
    retrieval_top_k: int = Field(default=5, ge=1, le=20)
    retrieval_min_score: float = Field(default=0.4, ge=0, le=1)
    retrieval_vector_weight: float = Field(default=0.9, ge=0, le=1)


class AdminOperationPreviewRequest(BaseModel):
    model_config = {"extra": "forbid"}
    kind: Literal["retry_document", "set_model_quota", "set_user_active", "set_user_role", "set_model_config"]
    target_id: str = Field(min_length=1, max_length=100)
    daily_limit: int | None = Field(default=None, ge=1, le=100000)
    active: bool | None = None
    role: Literal["student", "teacher", "admin"] | None = None
    config: ModelConfigValues | None = None
    reason: str = Field(min_length=5, max_length=500)


class AdminOperationConfirmRequest(BaseModel):
    model_config = {"extra": "forbid"}
    confirmed: bool = False


class AdminOperationResponse(BaseModel):
    id: str
    kind: str
    target_id: str
    title: str
    reason: str
    before: dict
    proposed: dict
    result: dict
    status: Literal["prepared", "applied", "cancelled", "expired", "stale"]
    expires_at: datetime
    created_at: datetime
    executed_at: datetime | None


class AdminInsightResponse(BaseModel):
    id: str
    eyebrow: str
    title: str
    detail: str
    button: str
    tone: Literal["primary", "warning", "neutral"]


class AdminReportCheckResponse(BaseModel):
    id: str
    status: Literal["healthy", "warning", "neutral"]
    title: str
    detail: str
    action_id: str


class AdminOperationsReportResponse(BaseModel):
    period_days: int
    generated_at: datetime
    period_start: datetime
    overall_status: Literal["healthy", "warning"]
    metrics: dict[str, int]
    checks: list[AdminReportCheckResponse]


class ModelUsageOverviewResponse(BaseModel):
    days: int
    total_calls: int
    recorded_upstream_requests: int = 0
    upstream_untracked_requests: int = 0
    successful_calls: int
    failed_calls: int
    pending_calls: int = 0
    cancelled_calls: int = 0
    success_rate: float
    input_tokens: int
    output_tokens: int
    average_duration_ms: float
    by_model: list[dict]
    recent: list[dict]


class ModelQuotaUpdate(BaseModel):
    daily_limit: int = Field(ge=1, le=100000)
    reason: str = Field(default="", max_length=500)
    confirmed: bool = False


class ModelQuotaResponse(BaseModel):
    role: Literal["student", "teacher", "admin"]
    daily_limit: int


class AuditLogResponse(BaseModel):
    id: str
    actor_name: str
    action: str
    resource_type: str
    resource_id: str | None
    detail: dict
    created_at: datetime | None


class LoginAttemptResponse(BaseModel):
    id: str
    username: str
    ip_address: str
    successful: bool
    created_at: datetime | None


class RequestLogResponse(BaseModel):
    id: str
    request_id: str
    method: str
    path: str
    status_code: int
    duration_ms: float
    ip_address: str
    created_at: datetime | None


class SecurityOverviewResponse(BaseModel):
    failed_logins_24h: int
    rate_limited_requests_24h: int
    server_errors_24h: int
    average_duration_ms_24h: float
    login_attempts: list[LoginAttemptResponse]
    request_logs: list[RequestLogResponse]


class EvaluationRunResponse(BaseModel):
    id: str
    name: str
    dataset_version: str
    case_count: int
    metrics: dict
    details: list[dict]
    created_by: str
    created_at: datetime | None


class ModelConfigResponse(BaseModel):
    provider: str
    model: str
    api_base: str
    configured: bool
    timeout_seconds: float
    fallback_offline: bool
    embedding_provider: str
    embedding_model: str
    retrieval_top_k: int
    retrieval_min_score: float
    retrieval_vector_weight: float


class ModelConfigUpdate(ModelConfigValues):
    confirmed: bool = False
