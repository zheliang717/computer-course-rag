from app.models import Base


def test_expected_database_tables_are_registered() -> None:
    assert {
        "knowledge_bases",
        "documents",
        "chunks",
        "courses",
        "course_sections",
        "course_classes",
        "class_enrollments",
        "question_bank_items",
        "assignments",
        "assignment_questions",
        "assignment_submissions",
        "wrong_questions",
        "course_knowledge_bases",
        "knowledge_points",
        "learning_progress",
        "audit_logs",
        "submission_reviews",
        "question_reviews",
        "document_ingestion_jobs",
        "login_attempts",
        "request_logs",
        "evaluation_runs",
        "practice_attempts",
        "late_submission_requests",
    }.issubset(Base.metadata.tables)


def test_chunk_embedding_dimension_is_fixed_for_bge_small_zh() -> None:
    embedding_type = Base.metadata.tables["chunks"].c.embedding.type
    assert embedding_type.dim == 512
