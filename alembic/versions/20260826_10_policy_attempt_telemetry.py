"""Add versioned acquisition telemetry to policy attempts."""

from alembic import op
import sqlalchemy as sa


revision = "20260826_10"
down_revision = "20260817_09"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("policies")}
    if "acquisition_telemetry" not in columns:
        op.add_column(
            "policies",
            sa.Column("acquisition_telemetry", sa.JSON(), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {column["name"] for column in inspector.get_columns("policies")}
    if "acquisition_telemetry" in columns:
        op.drop_column("policies", "acquisition_telemetry")
