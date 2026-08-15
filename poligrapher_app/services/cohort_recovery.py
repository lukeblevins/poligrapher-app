"""State-safe primitives for repeatable cohort source recovery."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import uuid

from sqlalchemy.orm import Session

from poligrapher_app.api.models import Policy, Provider


@dataclass(frozen=True)
class ProviderSourceSnapshot:
    source_url: str | None
    source_status: str
    source_checked_at: datetime | None
    source_http_status: int | None
    source_final_url: str | None

    @classmethod
    def capture(cls, provider: Provider) -> "ProviderSourceSnapshot":
        return cls(
            source_url=provider.source_url,
            source_status=provider.source_status,
            source_checked_at=provider.source_checked_at,
            source_http_status=provider.source_http_status,
            source_final_url=provider.source_final_url,
        )

    def restore(self, provider: Provider) -> None:
        provider.source_url = self.source_url
        provider.source_status = self.source_status
        provider.source_checked_at = self.source_checked_at
        provider.source_http_status = self.source_http_status
        provider.source_final_url = self.source_final_url


def recovery_url(result: dict) -> str | None:
    """Return only a resolver-validated URL that is safe to auto-try."""

    if result.get("status") in {"current_valid", "retry_current"}:
        return result.get("current_resolved_url") or result.get("source_url")
    if result.get("status") == "replacement_found":
        return result.get("replacement_url")
    return None


def stage_source(db: Session, provider: Provider, url: str) -> ProviderSourceSnapshot:
    snapshot = ProviderSourceSnapshot.capture(provider)
    provider.source_url = url
    provider.source_status = "unchecked"
    provider.source_checked_at = None
    provider.source_http_status = None
    provider.source_final_url = None
    db.commit()
    return snapshot


def restore_source(db: Session, provider: Provider, snapshot: ProviderSourceSnapshot) -> None:
    snapshot.restore(provider)
    db.commit()


def accept_source(db: Session, provider: Provider, url: str) -> None:
    provider.source_url = url
    provider.source_status = "available"
    provider.source_checked_at = datetime.now(timezone.utc)
    provider.source_final_url = url
    db.commit()


def has_completed_graph(db: Session, provider_id: uuid.UUID) -> bool:
    return any(
        isinstance(graph_data, dict) and bool(graph_data.get("elements"))
        for graph_data, in db.query(Policy.graph_data)
        .filter(Policy.provider_id == provider_id)
        .all()
    )
