"""Make assignments course-scoped while retaining legacy class links.

Revision ID: 20260923_0014
Revises: 20260923_0013
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260923_0014"
down_revision = "20260923_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("assignments", sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.execute("UPDATE assignments AS a SET course_id = c.course_id FROM course_classes AS c WHERE a.class_id = c.id")
    op.alter_column("assignments", "course_id", nullable=False)
    op.create_index("ix_assignments_course_id", "assignments", ["course_id"])
    op.create_foreign_key("fk_assignments_course_id", "assignments", "courses", ["course_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("assignments_class_id_fkey", "assignments", type_="foreignkey")
    op.create_foreign_key("fk_assignments_class_id_legacy", "assignments", "course_classes", ["class_id"], ["id"], ondelete="SET NULL")
    op.alter_column("assignments", "class_id", nullable=True)


def downgrade() -> None:
    if op.get_bind().execute(sa.text("SELECT count(*) FROM assignments WHERE class_id IS NULL")).scalar_one():
        raise RuntimeError("Course-scoped assignments without a class cannot be downgraded safely.")
    op.alter_column("assignments", "class_id", nullable=False)
    op.drop_constraint("fk_assignments_class_id_legacy", "assignments", type_="foreignkey")
    op.create_foreign_key("assignments_class_id_fkey", "assignments", "course_classes", ["class_id"], ["id"], ondelete="CASCADE")
    op.drop_constraint("fk_assignments_course_id", "assignments", type_="foreignkey")
    op.drop_index("ix_assignments_course_id", table_name="assignments")
    op.drop_column("assignments", "course_id")
