import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Column, Date, DateTime, Float, ForeignKey, Integer, JSON, String, Table, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from poligrapher_app.api.database import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


collection_members = Table(
    "collection_members",
    Base.metadata,
    Column("collection_id", Uuid, ForeignKey("company_collections.id", ondelete="CASCADE"), primary_key=True),
    Column("provider_id", Uuid, ForeignKey("providers.id", ondelete="CASCADE"), primary_key=True),
)


class Provider(Base):
    __tablename__ = "providers"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    industry: Mapped[str | None] = mapped_column(String(255))
    # Stable discovery anchor for scheduled acquisition (e.g. "abbott.com").
    domain: Mapped[str | None] = mapped_column(String(255))
    # Provider-level website policy source; drives scheduled comparison runs.
    source_url: Mapped[str | None] = mapped_column(String)
    # Stable public-company metadata used by refreshable index collections.
    ticker: Mapped[str | None] = mapped_column(String(32))
    tickers: Mapped[list] = mapped_column(JSON, default=list)
    cik: Mapped[str | None] = mapped_column(String(20), index=True)
    # Last lightweight availability check of the configured policy source.
    source_status: Mapped[str] = mapped_column(String(20), default="unchecked")
    source_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    source_http_status: Mapped[int | None] = mapped_column(Integer)
    source_final_url: Mapped[str | None] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    policies: Mapped[list["Policy"]] = relationship(
        "Policy", back_populates="provider", cascade="all, delete-orphan"
    )
    schedules: Mapped[list["Schedule"]] = relationship(
        "Schedule", back_populates="provider", cascade="all, delete-orphan"
    )
    collections: Mapped[list["CompanyCollection"]] = relationship(
        "CompanyCollection", secondary=collection_members, back_populates="providers"
    )


class CompanyCollection(Base):
    """A reusable provider cohort, either system-managed or researcher-created."""

    __tablename__ = "company_collections"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String)
    kind: Mapped[str] = mapped_column(String(20), default="custom")
    source_url: Mapped[str | None] = mapped_column(String)
    snapshot_date: Mapped[date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    providers: Mapped[list[Provider]] = relationship(
        Provider, secondary=collection_members, back_populates="collections"
    )


class Policy(Base):
    __tablename__ = "policies"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False
    )
    url: Mapped[str] = mapped_column(String, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)  # 'pdf' or 'webpage'
    # Analysis method: 'website' | 'pdf_from_page' | 'pdf_upload' |
    # 'captured_text'. The first two are the halves of a comparison run.
    method: Mapped[str] = mapped_column(String(20), default="website")
    run_group: Mapped[uuid.UUID | None] = mapped_column(Uuid)
    rerun_of_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("policies.id", ondelete="SET NULL")
    )
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

    @property
    def graph_artifacts_available(self) -> bool:
        """Expose download eligibility without leaking the private blob key."""

        return bool(
            self.artifact_blob_key
            and self.persistence_status == "persisted"
            and self.pipeline_status == "succeeded"
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


class TaskRecord(Base):
    """Durable queue/task state shared by the web service and analysis workers."""

    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(20), default="running", index=True)
    outcome: Mapped[str | None] = mapped_column(String(24), index=True)
    error: Mapped[str | None] = mapped_column(String)
    label: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    kind: Mapped[str | None] = mapped_column(String(40), index=True)
    total: Mapped[int] = mapped_column(Integer, default=0)
    completed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    cancel_requested: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    policy_id: Mapped[str | None] = mapped_column(String(36))
    provider_id: Mapped[str | None] = mapped_column(String(36), index=True)
    run_id: Mapped[str | None] = mapped_column(String(36), index=True)
    provider_name: Mapped[str | None] = mapped_column(String(255))
    output: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    issues: Mapped[list["TaskIssue"]] = relationship(
        "TaskIssue",
        back_populates="task",
        cascade="all, delete-orphan",
        order_by="TaskIssue.occurred_at",
    )


class TaskIssue(Base):
    """A durable, actionable failure or degradation attached to a task."""

    __tablename__ = "task_issues"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    stage: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    severity: Mapped[str] = mapped_column(String(16), nullable=False, default="error")
    retryability: Mapped[str] = mapped_column(String(20), nullable=False, default="manual")
    summary: Mapped[str] = mapped_column(String(255), nullable=False)
    technical_detail: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict] = mapped_column(JSON, default=dict)
    provider_id: Mapped[str | None] = mapped_column(String(36), index=True)
    policy_id: Mapped[str | None] = mapped_column(String(36), index=True)
    actions: Mapped[list] = mapped_column(JSON, default=list)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    task: Mapped[TaskRecord] = relationship("TaskRecord", back_populates="issues")


class RecoveryCandidateObservation(Base):
    """Pre-decision evidence and eventual outcome for one recovery candidate."""

    __tablename__ = "recovery_candidate_observations"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    task_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("providers.id", ondelete="CASCADE"), nullable=False, index=True
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, ForeignKey("policies.id", ondelete="SET NULL"), index=True
    )
    candidate_url: Mapped[str] = mapped_column(String, nullable=False)
    strategy: Mapped[str] = mapped_column(String(32), nullable=False)
    features: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    heuristic_confidence: Mapped[float] = mapped_column(Float, nullable=False)
    hard_rule_status: Mapped[str] = mapped_column(String(24), nullable=False)
    hard_rule_reasons: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    model_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="off")
    model_version: Mapped[str | None] = mapped_column(String(128))
    model_score: Mapped[float | None] = mapped_column(Float)
    decision: Mapped[str] = mapped_column(String(24), nullable=False, default="unselected")
    outcome_code: Mapped[str | None] = mapped_column(String(64), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    attempted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
