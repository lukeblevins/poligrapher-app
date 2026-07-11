import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import CompanyCollection, Provider
from poligrapher_app.api.schemas import (
    CompanyCollectionCreate,
    CompanyCollectionRead,
    CompanyCollectionUpdate,
    IndexSyncSummary,
    TaskStatus,
)
from poligrapher_app.services.sp500_catalog import sync_sp500

router = APIRouter(prefix="/api/collections", tags=["collections"])
Db = Annotated[Session, Depends(get_db)]


def _read(collection: CompanyCollection) -> CompanyCollectionRead:
    provider_ids = [provider.id for provider in collection.providers]
    return CompanyCollectionRead(
        id=collection.id,
        name=collection.name,
        description=collection.description,
        kind=collection.kind,
        source_url=collection.source_url,
        snapshot_date=collection.snapshot_date,
        provider_ids=provider_ids,
        provider_count=len(provider_ids),
        created_at=collection.created_at,
    )


def _providers(db: Session, ids: list[uuid.UUID]) -> list[Provider]:
    providers = db.query(Provider).filter(Provider.id.in_(ids)).all() if ids else []
    if len(providers) != len(set(ids)):
        raise HTTPException(status_code=422, detail="One or more companies do not exist")
    return providers


@router.get("", response_model=list[CompanyCollectionRead])
def list_collections(db: Db):
    collections = db.query(CompanyCollection).order_by(CompanyCollection.kind.desc(), CompanyCollection.name).all()
    return [_read(collection) for collection in collections]


@router.post("", response_model=CompanyCollectionRead, status_code=status.HTTP_201_CREATED)
def create_collection(body: CompanyCollectionCreate, db: Db):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Collection name is required")
    if db.query(CompanyCollection).filter_by(name=name).first():
        raise HTTPException(status_code=409, detail="A collection with that name already exists")
    collection = CompanyCollection(
        name=name,
        description=body.description.strip() if body.description else None,
        kind="custom",
        providers=_providers(db, body.provider_ids),
    )
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return _read(collection)


@router.patch("/{collection_id}", response_model=CompanyCollectionRead)
def update_collection(collection_id: uuid.UUID, body: CompanyCollectionUpdate, db: Db):
    collection = db.get(CompanyCollection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    if collection.kind == "system" and (body.name is not None or body.provider_ids is not None):
        raise HTTPException(status_code=409, detail="System collections are updated by synchronization")
    if body.name is not None:
        name = body.name.strip()
        if not name:
            raise HTTPException(status_code=422, detail="Collection name is required")
        duplicate = db.query(CompanyCollection).filter(CompanyCollection.name == name, CompanyCollection.id != collection.id).first()
        if duplicate:
            raise HTTPException(status_code=409, detail="A collection with that name already exists")
        collection.name = name
    if body.description is not None:
        collection.description = body.description.strip() or None
    if body.provider_ids is not None:
        collection.providers = _providers(db, body.provider_ids)
    db.commit()
    db.refresh(collection)
    return _read(collection)


@router.delete("/{collection_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_collection(collection_id: uuid.UUID, db: Db):
    collection = db.get(CompanyCollection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    if collection.kind == "system":
        raise HTTPException(status_code=409, detail="System collections cannot be deleted")
    db.delete(collection)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/sp500/sync", response_model=IndexSyncSummary)
def synchronize_sp500(db: Db):
    return IndexSyncSummary(**sync_sp500(db))


@router.post("/{collection_id}/verify-sources", response_model=TaskStatus)
def verify_collection_sources(collection_id: uuid.UUID, request: Request, db: Db):
    collection = db.get(CompanyCollection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    provider_ids = [provider.id for provider in collection.providers]
    registry = request.app.state.tasks
    task_id = registry.create(
        kind="source-verification",
        title=f"Verify sources · {collection.name}",
        total=len(provider_ids),
    )

    def _run():
        from poligrapher_app.api.database import SessionLocal
        from poligrapher_app.services.source_verification import verify_provider_sources

        db2 = SessionLocal()
        try:
            providers = db2.query(Provider).filter(Provider.id.in_(provider_ids)).all()
            verify_provider_sources(
                db2,
                providers,
                on_result=lambda _check: registry.incr(task_id, "completed"),
                should_cancel=lambda: registry.is_cancelled(task_id),
            )
            if registry.is_cancelled(task_id):
                registry.set_cancelled(task_id)
            else:
                registry.set_done(task_id)
        finally:
            db2.close()

    registry.submit(task_id, _run)
    return TaskStatus(task_id=task_id, **registry.get(task_id))


@router.post("/{collection_id}/runs", response_model=TaskStatus)
def analyze_collection(collection_id: uuid.UUID, request: Request, db: Db):
    collection = db.get(CompanyCollection, collection_id)
    if collection is None:
        raise HTTPException(status_code=404, detail="Collection not found")
    provider_ids = [provider.id for provider in collection.providers if provider.source_url]
    registry = request.app.state.tasks
    task_id = registry.create(
        kind="collection-analysis",
        title=f"Analyze collection · {collection.name}",
        total=len(provider_ids),
    )

    def _run():
        from poligrapher_app.services import runs as runs_service

        for provider_id in provider_ids:
            if registry.is_cancelled(task_id):
                registry.set_cancelled(task_id)
                return
            try:
                result = runs_service.run_comparison(
                    provider_id, scheduled=False, registry=registry, task_id=task_id
                )
                if result not in ("ok", "unchanged"):
                    registry.incr(task_id, "failed")
            except Exception:
                registry.incr(task_id, "failed")
            registry.incr(task_id, "completed")
        registry.set_done(task_id)

    registry.submit(task_id, _run)
    return TaskStatus(task_id=task_id, **registry.get(task_id))
