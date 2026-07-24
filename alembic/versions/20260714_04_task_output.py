"""Persist terminal output for durable tasks."""

from alembic import op
import sqlalchemy as sa

revision = "20260714_04"
down_revision = "20260711_03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tasks")}
    if "output" not in columns:
        op.add_column(
            "tasks",
            sa.Column("output", sa.Text(), nullable=False, server_default=""),
        )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("tasks")}
    if "output" in columns:
        op.drop_column("tasks", "output")
