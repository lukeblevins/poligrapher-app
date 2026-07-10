import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poligrapher_app.api.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    industry: Mapped[str | None] = mapped_column(String(255))
    # Stable discovery anchor for scheduled acquisition (e.g. "abbott.com").
    domain: Mapped[str | None] = mapped_column(String(255))
    # Provider-level website policy source; drives scheduled comparison runs.
    source_url: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    policies: Mapped[list["Policy"]] = relationship(
        "Policy", back_populates="provider", cascade="all, delete-orphan"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="provider", cascade="all, delete-orphan"
    )


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # 'pdf' or 'webpage'
    # Analysis method: 'website' | 'pdf_from_page' | 'pdf_upload'. The first two
    # are the two halves of a single comparison run (grouped by run_group).
    method: Mapped[str] = mapped_column(String(20), default="website")
    run_group: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    # True for source/scheduled runs; False for one-off uploaded-PDF runs.
    scheduled: Mapped[bool] = mapped_column(Boolean, default=False)
    # Website extracted-text hash or uploaded-PDF file hash, for change detection.
    content_hash: Mapped[str | None] = mapped_column(String(64))
    capture_date: Mapped[date | None] = mapped_column(Date)
    output_dir: Mapped[str | None] = mapped_column(String)
    # Durable, cloud-safe analysis products. output_dir remains only for the
    # one-time legacy importer and will be removed after migration.
    graph_data: Mapped[dict | None] = mapped_column(JSON)
    graph_stats: Mapped[dict | None] = mapped_column(JSON)
    source_blob_key: Mapped[str | None] = mapped_column(String)
    source_filename: Mapped[str | None] = mapped_column(String)
    artifact_blob_key: Mapped[str | None] = mapped_column(String)
    persistence_status: Mapped[str] = mapped_column(String(20), default="pending")
    has_results: Mapped[bool] = mapped_column(Boolean, default=False)
    pipeline_status: Mapped[str] = mapped_column(String(20), default="pending")
    pipeline_errors: Mapped[list] = mapped_column(JSON, default=list)
    privacy_score: Mapped[float | None] = mapped_column(Float)
    gdpr_score: Mapped[float | None] = mapped_column(Float)
    graph_kind: Mapped[str] = mapped_column(String(20), default="none")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    provider: Mapped["Provider"] = relationship("Provider", back_populates="policies")
    analysis_results: Mapped[list["AnalysisResult"]] = relationship(
        "AnalysisResult", back_populates="policy", cascade="all, delete-orphan"
    )


class Schedule(Base):
    """A recurring 'acquire → generate → score' job for a provider."""

    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    # 'daily' | 'weekly' | 'monthly' | raw cron ("m h dom mon dow")
    cadence: Mapped[str] = mapped_column(String(64), default="weekly")
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    # A user-confirmed canonical URL that overrides discovery (strategy 'override').
    source_override_url: Mapped[str | None] = mapped_column(String)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_status: Mapped[str] = mapped_column(String(32), default="idle")
    last_source_url: Mapped[str | None] = mapped_column(String)
    last_strategy: Mapped[str | None] = mapped_column(String(32))
    last_confidence: Mapped[float | None] = mapped_column(Float)
    last_content_hash: Mapped[str | None] = mapped_column(String(64))
    # Set when acquisition could not confidently resolve a source and needs a human.
    needs_attention: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    provider: Mapped["Provider"] = relationship("Provider", back_populates="schedules")


class AnalysisResult(Base):
    __tablename__ = "analysis_results"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    policy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("policies.id", ondelete="CASCADE"), nullable=False
    )
    analysis_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'privacy' or 'gdpr'
    score: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    policy: Mapped["Policy"] = relationship("Policy", back_populates="analysis_results")
