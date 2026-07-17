"""Link durable tasks to providers and analysis runs."""

from alembic import op
import sqlalchemy as sa

revision = "20260715_05"
down_revision = "20260714_04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tasks")}
    if "provider_id" not in columns:
        op.add_column("tasks", sa.Column("provider_id", sa.String(length=36), nullable=True))
        op.create_index("ix_tasks_provider_id", "tasks", ["provider_id"])
    if "run_id" not in columns:
        op.add_column("tasks", sa.Column("run_id", sa.String(length=36), nullable=True))
        op.create_index("ix_tasks_run_id", "tasks", ["run_id"])


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tasks")}
    if "run_id" in columns:
        op.drop_index("ix_tasks_run_id", table_name="tasks")
        op.drop_column("tasks", "run_id")
    if "provider_id" in columns:
        op.drop_index("ix_tasks_provider_id", table_name="tasks")
        op.drop_column("tasks", "provider_id")
