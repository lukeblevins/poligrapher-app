"""Track the source analysis used for historical reruns."""

from alembic import op
import sqlalchemy as sa

revision = "20260715_06"
down_revision = "20260715_05"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("policies")}
    if "rerun_of_policy_id" not in columns:
        with op.batch_alter_table("policies") as batch:
            batch.add_column(sa.Column("rerun_of_policy_id", sa.Uuid(), nullable=True))
            batch.create_foreign_key(
                "fk_policies_rerun_of_policy_id",
                "policies",
                ["rerun_of_policy_id"],
                ["id"],
                ondelete="SET NULL",
            )


def downgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("policies")}
    if "rerun_of_policy_id" in columns:
        with op.batch_alter_table("policies") as batch:
            batch.drop_constraint("fk_policies_rerun_of_policy_id", type_="foreignkey")
            batch.drop_column("rerun_of_policy_id")
