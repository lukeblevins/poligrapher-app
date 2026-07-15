import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class ProviderCreate(BaseModel):
    name: str
    industry: str | None = None
    domain: str | None = None
    source_url: str | None = None


class CompanyCatalogResult(BaseModel):
    id: str
    name: str
    domain: str | None = None
    source_url: str
    source: str
    attribution_url: str
    requires_javascript: bool = False


class CompanyCatalogSearch(BaseModel):
    results: list[CompanyCatalogResult]
    source_available: bool = True


class ProviderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    industry: str | None
    domain: str | None = None
    source_url: str | None = None
    ticker: str | None = None
    tickers: list[str] = []
    cik: str | None = None
    source_status: str = "unchecked"
    source_checked_at: datetime | None = None
    source_http_status: int | None = None
    source_final_url: str | None = None
    collection_ids: list[uuid.UUID] = []
    created_at: datetime
    policy_count: int = 0
    succeeded_count: int = 0
    failed_count: int = 0


class CompanyCollectionCreate(BaseModel):
    name: str
    description: str | None = None
    provider_ids: list[uuid.UUID] = []


class CompanyCollectionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    provider_ids: list[uuid.UUID] | None = None


class CompanyCollectionRead(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    kind: str
    source_url: str | None
    snapshot_date: date | None
    provider_ids: list[uuid.UUID]
    provider_count: int
    created_at: datetime


class IndexSyncSummary(BaseModel):
    collection_id: uuid.UUID
    securities: int
    companies: int
    created: int
    updated: int
    snapshot_date: date


class SourceVerificationSummary(BaseModel):
    checked: int
    available: int
    restricted: int
    broken: int
    errors: int
    missing: int


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
    """A grouped analysis, uploaded PDF, or standalone legacy result."""

    run_group: str | None
    kind: str  # 'comparison' | 'upload' | 'legacy'
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
    has_output: bool = False


class TaskOutput(BaseModel):
    task_id: str
    status: str
    output: str
    truncated: bool = False


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
