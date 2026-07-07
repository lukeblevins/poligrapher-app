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
    capture_date: date | None
    output_dir: str | None
    has_results: bool
    pipeline_status: str
    pipeline_errors: list
    privacy_score: float | None
    gdpr_score: float | None
    graph_kind: str
    created_at: datetime


class TaskStatus(BaseModel):
    task_id: str
    status: str  # 'running', 'done', 'failed'
    error: str | None = None
    label: str | None = None
    total: int = 0
    completed: int = 0
    failed: int = 0


class ImportSummary(BaseModel):
    created: int
    skipped: int
    errors: int


class GraphElements(BaseModel):
    elements: list[dict]


class GraphStats(BaseModel):
    stats: dict | None


class Assessments(BaseModel):
    privacy: dict | None
    gdpr: dict | None
    readability: dict | None
