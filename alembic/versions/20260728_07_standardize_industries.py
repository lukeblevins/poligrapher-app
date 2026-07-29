"""standardize provider industries"""

from alembic import op

revision = "20260728_07"
down_revision = "20260715_06"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE providers SET industry = 'Health Care' "
        "WHERE lower(trim(industry)) = 'healthcare'"
    )


def downgrade() -> None:
    # The legacy spelling cannot be distinguished from canonical values once
    # normalized, so this data cleanup is intentionally irreversible.
    pass
