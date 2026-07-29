"""Add structured task outcomes and actionable issues."""

from alembic import op
import sqlalchemy as sa


revision = "20260729_08"
down_revision = "20260728_07"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    if "outcome" not in task_columns:
        op.add_column("tasks", sa.Column("outcome", sa.String(length=24), nullable=True))

    inspector = sa.inspect(bind)
    task_indexes = {index["name"] for index in inspector.get_indexes("tasks")}
    if "ix_tasks_outcome" not in task_indexes:
        op.create_index("ix_tasks_outcome", "tasks", ["outcome"])

    if "task_issues" not in inspector.get_table_names():
        op.create_table(
            "task_issues",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("task_id", sa.Uuid(), nullable=False),
            sa.Column("code", sa.String(length=80), nullable=False),
            sa.Column("stage", sa.String(length=32), nullable=False),
            sa.Column("severity", sa.String(length=16), nullable=False),
            sa.Column("retryability", sa.String(length=20), nullable=False),
            sa.Column("summary", sa.String(length=255), nullable=False),
            sa.Column("technical_detail", sa.Text(), nullable=True),
            sa.Column("provider_id", sa.String(length=36), nullable=True),
            sa.Column("policy_id", sa.String(length=36), nullable=True),
            sa.Column("actions", sa.JSON(), nullable=False),
            sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
            sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_task_issues_task_id", "task_issues", ["task_id"])
        op.create_index("ix_task_issues_code", "task_issues", ["code"])
        op.create_index("ix_task_issues_stage", "task_issues", ["stage"])
        op.create_index("ix_task_issues_provider_id", "task_issues", ["provider_id"])
        op.create_index("ix_task_issues_policy_id", "task_issues", ["policy_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "task_issues" in inspector.get_table_names():
        op.drop_table("task_issues")

    inspector = sa.inspect(bind)
    task_indexes = {index["name"] for index in inspector.get_indexes("tasks")}
    if "ix_tasks_outcome" in task_indexes:
        op.drop_index("ix_tasks_outcome", table_name="tasks")
    task_columns = {column["name"] for column in inspector.get_columns("tasks")}
    if "outcome" in task_columns:
        op.drop_column("tasks", "outcome")
