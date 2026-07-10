"""add durable graph and blob metadata

Revision ID: 20260710_01
"""
from alembic import op
import sqlalchemy as sa

revision = "20260710_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "policies" not in inspector.get_table_names():
        from poligrapher_app.api.database import Base
        import poligrapher_app.api.models  # noqa: F401
        Base.metadata.create_all(bind=bind)
        return

    provider_columns = {column["name"] for column in inspector.get_columns("providers")}
    with op.batch_alter_table("providers") as batch:
        if "domain" not in provider_columns:
            batch.add_column(sa.Column("domain", sa.String(length=255), nullable=True))
        if "source_url" not in provider_columns:
            batch.add_column(sa.Column("source_url", sa.String(), nullable=True))

    columns = {column["name"] for column in inspector.get_columns("policies")}
    additions = {
        "method": sa.Column("method", sa.String(length=20), server_default="website"),
        "run_group": sa.Column("run_group", sa.Uuid(), nullable=True),
        "scheduled": sa.Column("scheduled", sa.Boolean(), server_default=sa.false()),
        "content_hash": sa.Column("content_hash", sa.String(length=64), nullable=True),
        "graph_data": sa.Column("graph_data", sa.JSON(), nullable=True),
        "graph_stats": sa.Column("graph_stats", sa.JSON(), nullable=True),
        "source_blob_key": sa.Column("source_blob_key", sa.String(), nullable=True),
        "source_filename": sa.Column("source_filename", sa.String(), nullable=True),
        "artifact_blob_key": sa.Column("artifact_blob_key", sa.String(), nullable=True),
        "persistence_status": sa.Column("persistence_status", sa.String(length=20), nullable=False,
                                        server_default="pending"),
    }
    with op.batch_alter_table("policies") as batch:
        for name, column in additions.items():
            if name not in columns:
                batch.add_column(column)


def downgrade() -> None:
    with op.batch_alter_table("policies") as batch:
        for name in ("persistence_status", "artifact_blob_key", "source_filename",
                     "source_blob_key", "graph_stats", "graph_data"):
            batch.drop_column(name)
