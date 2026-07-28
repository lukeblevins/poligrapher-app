"""Import a versioned catalog of verified company policy sources."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.orm import Session

from poligrapher_app.api.models import Provider

CATALOG_PATH = Path(__file__).parents[1] / "data" / "sp500_sources.json"
CATALOG_VERSION = 1


@dataclass(frozen=True)
class SourceCatalogSummary:
    entries: int
    updated: int
    unchanged: int
    newer_preserved: int
    missing: tuple[str, ...]


def _parse_timestamp(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _utc_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def load_source_catalog(path: str | Path = CATALOG_PATH) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text())
    if payload.get("version") != CATALOG_VERSION:
        raise ValueError(f"Unsupported source catalog version: {payload.get('version')!r}")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise ValueError("Source catalog must contain a sources list")
    return sources


def apply_source_catalog(
    db: Session,
    sources: list[dict[str, Any]],
    *,
    require_all: bool = True,
) -> SourceCatalogSummary:
    """Upsert source metadata without replacing unrelated production data.

    Providers are matched by stable CIK first, then ticker. A production check
    newer than the snapshot wins so repeat deployments cannot roll back fresher
    source verification.
    """
    providers = db.query(Provider).all()
    by_cik = {provider.cik: provider for provider in providers if provider.cik}
    by_ticker = {
        ticker: provider
        for provider in providers
        for ticker in (provider.tickers or ([provider.ticker] if provider.ticker else []))
    }
    updated = unchanged = newer_preserved = 0
    missing: list[str] = []

    for source in sources:
        provider = by_cik.get(source.get("cik"))
        if provider is None:
            provider = next(
                (by_ticker[ticker] for ticker in source.get("tickers", []) if ticker in by_ticker),
                None,
            )
        if provider is None:
            missing.append(source.get("name") or source.get("cik") or "unknown provider")
            continue

        snapshot_checked_at = _utc_timestamp(
            _parse_timestamp(source.get("source_checked_at"))
        )
        if (
            _utc_timestamp(provider.source_checked_at)
            and snapshot_checked_at
            and _utc_timestamp(provider.source_checked_at) > snapshot_checked_at
        ):
            newer_preserved += 1
            continue

        values = {
            "domain": source.get("domain"),
            "source_url": source.get("source_url"),
            "source_status": source.get("source_status", "unchecked"),
            "source_checked_at": snapshot_checked_at,
            "source_http_status": source.get("source_http_status"),
            "source_final_url": source.get("source_final_url"),
        }
        changed = any(
            (
                _utc_timestamp(getattr(provider, field)) != _utc_timestamp(value)
                if field == "source_checked_at"
                else getattr(provider, field) != value
            )
            for field, value in values.items()
        )
        if changed:
            for field, value in values.items():
                setattr(provider, field, value)
            updated += 1
        else:
            unchanged += 1

    if missing and require_all:
        db.rollback()
        raise ValueError(
            f"Source catalog did not match {len(missing)} providers: {', '.join(missing[:5])}"
        )
    db.commit()
    return SourceCatalogSummary(
        entries=len(sources),
        updated=updated,
        unchanged=unchanged,
        newer_preserved=newer_preserved,
        missing=tuple(missing),
    )
