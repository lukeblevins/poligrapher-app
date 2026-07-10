import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ProviderCreate(BaseModel):
    name: str
    industry: str | None = None


class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    industry: str | None
    domain: str | None = None
    source_url: str | None = None
    created_at: datetime
    policy_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0


class PolicyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    url: str
    source: str
    method: str = "website"
    run_group: uuid.UUID | None = None
    scheduled: bool = False
    content_hash: str | None = None
    capture_date: date | None
    # Deprecated legacy field; always omitted from new cloud-native runs.
    output_dir: str | None = None
    has_results: bool
    pipeline_status: str
    pipeline_errors: list
    privacy_score: float | None
    gdpr_score: float | None
    graph_kind: str
    created_at: datetime


class RunGroup(BaseModel):
    """A comparison run (website + pdf_from_page) or a one-off uploaded PDF."""

    run_group: str | None
    kind: str  # 'comparison' | 'upload'
    scheduled: bool
    capture_date: date | None
    created_at: datetime
    runs: list[PolicyRead]


class ProviderSourceUpdate(BaseModel):
    source_url: str


class ScheduleToggle(BaseModel):
    enabled: bool
    cadence: str | None = None


class TaskStatus(BaseModel):
    model_config = ConfigDict(extra="ignore")

    task_id: str
    status: str  # 'running', 'cancelling', 'cancelled', 'done', 'failed'
    error: str | None = None
    label: str | None = None
    title: str | None = None
    kind: str | None = None
    total: int = 0
    completed: int = 0
    failed: int = 0
    created_at: str | None = None
    cancelable: bool = False
    policy_id: str | None = None
    provider_name: str | None = None


class ImportSummary(BaseModel):
    created: int
    skipped: int
    errors: int


# ── Scheduling ────────────────────────────────────────────────────────────────

class ScheduleCreate(BaseModel):
    cadence: str = "weekly"
    enabled: bool = True
    source_override_url: str | None = None


class ScheduleUpdate(BaseModel):
    cadence: str | None = None
    enabled: bool | None = None
    source_override_url: str | None = None


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    provider_id: uuid.UUID
    cadence: str
    enabled: bool
    source_override_url: str | None
    last_run_at: datetime | None
    next_run_at: datetime | None
    last_status: str
    last_source_url: str | None
    last_strategy: str | None
    last_confidence: float | None
    last_content_hash: str | None
    needs_attention: bool
    created_at: datetime


class SourcePreview(BaseModel):
    """A resolved candidate source shown to the user for confirmation."""

    url: str | None
    strategy: str | None
    confidence: float
    auto: bool
    select: object | None = None
    notes: str = ""
    resolved: bool


class GraphElements(BaseModel):
    elements: list[dict]


class GraphStats(BaseModel):
    stats: dict | None


class Assessments(BaseModel):
    privacy: dict | None
    gdpr: dict | None
    readability: dict | None
