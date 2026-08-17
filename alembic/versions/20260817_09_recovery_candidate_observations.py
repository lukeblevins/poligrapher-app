"""Add durable recovery candidate observations for shadow ranking."""

from alembic import op
import sqlalchemy as sa


revision = "20260817_09"
down_revision = "20260729_08"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    task_issue_columns = {column["name"] for column in inspector.get_columns("task_issues")}
    if "details" not in task_issue_columns:
        op.add_column("task_issues", sa.Column("details", sa.JSON(), nullable=True))
    inspector = sa.inspect(bind)
    if "recovery_candidate_observations" in inspector.get_table_names():
        return
    op.create_table(
        "recovery_candidate_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=False),
        sa.Column("provider_id", sa.Uuid(), nullable=False),
        sa.Column("policy_id", sa.Uuid(), nullable=True),
        sa.Column("candidate_url", sa.String(), nullable=False),
        sa.Column("strategy", sa.String(length=32), nullable=False),
        sa.Column("features", sa.JSON(), nullable=False),
        sa.Column("heuristic_confidence", sa.Float(), nullable=False),
        sa.Column("hard_rule_status", sa.String(length=24), nullable=False),
        sa.Column("hard_rule_reasons", sa.JSON(), nullable=False),
        sa.Column("model_mode", sa.String(length=16), nullable=False),
        sa.Column("model_version", sa.String(length=128), nullable=True),
        sa.Column("model_score", sa.Float(), nullable=True),
        sa.Column("decision", sa.String(length=24), nullable=False),
        sa.Column("outcome_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("settled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recovery_candidate_observations_task_id", "recovery_candidate_observations", ["task_id"])
    op.create_index("ix_recovery_candidate_observations_provider_id", "recovery_candidate_observations", ["provider_id"])
    op.create_index("ix_recovery_candidate_observations_policy_id", "recovery_candidate_observations", ["policy_id"])
    op.create_index("ix_recovery_candidate_observations_outcome_code", "recovery_candidate_observations", ["outcome_code"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "recovery_candidate_observations" in inspector.get_table_names():
        op.drop_table("recovery_candidate_observations")
    inspector = sa.inspect(bind)
    if "details" in {column["name"] for column in inspector.get_columns("task_issues")}:
        op.drop_column("task_issues", "details")
