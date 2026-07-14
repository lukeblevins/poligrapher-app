"""add durable task queue state

Revision ID: 20260711_03
"""

from alembic import op
import sqlalchemy as sa

revision = "20260711_03"
down_revision = "20260710_02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    if "tasks" in sa.inspect(op.get_bind()).get_table_names():
        return
    op.create_table(
        "tasks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="running"),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("label", sa.String(length=255), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("kind", sa.String(length=40), nullable=True),
        sa.Column("total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("policy_id", sa.String(length=36), nullable=True),
        sa.Column("provider_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tasks_status", "tasks", ["status"], unique=False)
    op.create_index("ix_tasks_kind", "tasks", ["kind"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_tasks_kind", table_name="tasks")
    op.drop_index("ix_tasks_status", table_name="tasks")
    op.drop_table("tasks")
