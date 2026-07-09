import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import Provider
from poligrapher_app.api.schemas import ImportSummary, ProviderCreate, ProviderRead
from poligrapher_app.services.importer import import_policies, read_policy_csv

router = APIRouter(prefix="/api/providers", tags=["providers"])

Db = Annotated[Session, Depends(get_db)]


def _provider_read(provider: Provider) -> ProviderRead:
    succeeded = sum(1 for p in provider.policies if p.pipeline_status == "succeeded")
    failed = sum(1 for p in provider.policies if p.pipeline_status == "failed")
    return ProviderRead(
        id=provider.id,
        name=provider.name,
        industry=provider.industry,
        domain=provider.domain,
        source_url=provider.source_url,
        created_at=provider.created_at,
        policy_count=len(provider.policies),
        succeeded_count=succeeded,
        failed_count=failed,
    )


@router.get("", response_model=list[ProviderRead])
def list_providers(db: Db):
    providers = db.query(Provider).order_by(Provider.name).all()
    return [_provider_read(p) for p in providers]


@router.post("", response_model=ProviderRead, status_code=status.HTTP_201_CREATED)
def create_provider(body: ProviderCreate, db: Db):
    existing = db.query(Provider).filter_by(name=body.name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Provider already exists")
    provider = Provider(name=body.name, industry=body.industry)
    db.add(provider)
    db.commit()
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
