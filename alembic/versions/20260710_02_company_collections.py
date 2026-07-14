"""add company collections and source health metadata

Revision ID: 20260710_02
"""

from alembic import op
import sqlalchemy as sa

revision = "20260710_02"
down_revision = "20260710_01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    provider_columns = {column["name"] for column in inspector.get_columns("providers")}
    additions = {
        "ticker": sa.Column("ticker", sa.String(length=32), nullable=True),
        "tickers": sa.Column("tickers", sa.JSON(), nullable=True),
        "cik": sa.Column("cik", sa.String(length=20), nullable=True),
        "source_status": sa.Column(
            "source_status", sa.String(length=20), nullable=False, server_default="unchecked"
        ),
        "source_checked_at": sa.Column("source_checked_at", sa.DateTime(timezone=True), nullable=True),
        "source_http_status": sa.Column("source_http_status", sa.Integer(), nullable=True),
        "source_final_url": sa.Column("source_final_url", sa.String(), nullable=True),
    }
    with op.batch_alter_table("providers") as batch:
        for name, column in additions.items():
            if name not in provider_columns:
                batch.add_column(column)
        if "cik" not in provider_columns:
            batch.create_index("ix_providers_cik", ["cik"], unique=False)

    tables = set(inspector.get_table_names())
    if "company_collections" not in tables:
        op.create_table(
            "company_collections",
            sa.Column("id", sa.Uuid(), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("description", sa.String(), nullable=True),
            sa.Column("kind", sa.String(length=20), nullable=False, server_default="custom"),
            sa.Column("source_url", sa.String(), nullable=True),
            sa.Column("snapshot_date", sa.Date(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("name"),
        )
    if "collection_members" not in tables:
        op.create_table(
            "collection_members",
            sa.Column("collection_id", sa.Uuid(), nullable=False),
            sa.Column("provider_id", sa.Uuid(), nullable=False),
            sa.ForeignKeyConstraint(["collection_id"], ["company_collections.id"], ondelete="CASCADE"),
            sa.ForeignKeyConstraint(["provider_id"], ["providers.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("collection_id", "provider_id"),
        )


def downgrade() -> None:
    op.drop_table("collection_members")
    op.drop_table("company_collections")
    with op.batch_alter_table("providers") as batch:
        batch.drop_index("ix_providers_cik")
        for name in (
            "source_final_url",
            "source_http_status",
            "source_checked_at",
            "source_status",
            "cik",
            "tickers",
            "ticker",
        ):
            batch.drop_column(name)
