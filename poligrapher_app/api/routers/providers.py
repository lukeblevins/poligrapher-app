import uuid
from datetime import timezone
from typing import Annotated
import urllib.parse

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import Provider
from poligrapher_app.api.schemas import (
    CompanyCatalogSearch,
    ImportSummary,
    ProviderCreate,
    ProviderRead,
)
from poligrapher_app.services.importer import import_policies, read_policy_csv
from poligrapher_app.services.company_catalog import search_open_terms
from poligrapher_app.services.source_verification import verify_provider_sources

router = APIRouter(prefix="/api/providers", tags=["providers"])

Db = Annotated[Session, Depends(get_db)]


def _provider_read(provider: Provider) -> ProviderRead:
    succeeded = sum(1 for p in provider.policies if p.pipeline_status == "succeeded")
    failed = sum(1 for p in provider.policies if p.pipeline_status == "failed")
    source_checked_at = provider.source_checked_at
    if source_checked_at is not None and source_checked_at.tzinfo is None:
        source_checked_at = source_checked_at.replace(tzinfo=timezone.utc)
    return ProviderRead(
        id=provider.id,
        name=provider.name,
        industry=provider.industry,
        domain=provider.domain,
        source_url=provider.source_url,
        ticker=provider.ticker,
        tickers=provider.tickers or [],
        cik=provider.cik,
        source_status=provider.source_status,
        source_checked_at=source_checked_at,
        source_http_status=provider.source_http_status,
        source_final_url=provider.source_final_url,
        collection_ids=[collection.id for collection in provider.collections],
        created_at=provider.created_at,
        policy_count=len(provider.policies),
        succeeded_count=succeeded,
        failed_count=failed,
    )


@router.get("", response_model=list[ProviderRead])
def list_providers(db: Db):
    providers = db.query(Provider).order_by(Provider.name).all()
    return [_provider_read(p) for p in providers]


@router.get("/catalog/search", response_model=CompanyCatalogSearch)
def search_company_catalog(q: Annotated[str, Query(min_length=2, max_length=100)]):
    results, available = search_open_terms(q)
    return CompanyCatalogSearch(results=results, source_available=available)


def _normalize_domain(value: str | None) -> str | None:
    if not value:
        return None
    candidate = value.strip()
    parsed = urllib.parse.urlparse(candidate if "://" in candidate else f"https://{candidate}")
    return parsed.hostname.removeprefix("www.").lower() if parsed.hostname else None


@router.post("", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
def create_provider(body: ProviderCreate, db: Db):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Company name is required")
    existing = db.query(Provider).filter_by(name=name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Provider already exists")
    provider = Provider(
        name=name,
        industry=body.industry.strip() if body.industry else None,
        domain=_normalize_domain(body.domain),
        source_url=body.source_url.strip() if body.source_url else None,
    )
    db.add(provider)
    db.commit()
    db.refresh(provider)
    return _provider_read(provider)


@router.post("/{provider_id}/verify-source", response_model=ProviderRead)
def verify_provider_source(provider_id: uuid.UUID, db: Db):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    verify_provider_sources(db, [provider], max_workers=1)
    db.refresh(provider)
    return _provider_read(provider)


@router.delete("/{provider_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_provider(provider_id: uuid.UUID, db: Db):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    db.delete(provider)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/import", response_model=ImportSummary)
async def import_csv(db: Db, file: UploadFile = File(...)):
    try:
        df = read_policy_csv(await file.read())
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {exc}") from exc
    return ImportSummary(**import_policies(df, db))
