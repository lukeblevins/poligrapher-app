import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import Provider, Schedule
from poligrapher_app.api.schemas import ScheduleCreate, ScheduleRead, ScheduleUpdate, SourcePreview
from poligrapher_app.services import scheduler as sched_engine
from poligrapher_app.services.acquisition import PolicySourceResolver, provider_domain_from_urls

router = APIRouter(tags=["schedules"])

Db = Annotated[Session, Depends(get_db)]


def _ensure_domain(provider: Provider, db: Session) -> str | None:
    """Backfill and persist a provider's discovery domain if missing."""
    if not provider.domain:
        derived = provider_domain_from_urls([p.url for p in provider.policies])
        if derived:
            provider.domain = derived
            db.commit()
    return provider.domain


@router.get("/api/providers/{provider_id}/schedules", response_model=list[ScheduleRead])
def list_schedules(provider_id: uuid.UUID, db: Db):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider.schedules


@router.post(
    "/api/providers/{provider_id}/schedules",
    response_model=ScheduleRead,
    status_code=status.HTTP_201_CREATED,
)
def create_schedule(provider_id: uuid.UUID, body: ScheduleCreate, db: Db):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    _ensure_domain(provider, db)

    sched = Schedule(
        provider_id=provider_id,
        cadence=body.cadence,
        enabled=body.enabled,
        source_override_url=body.source_override_url or None,
    )
    db.add(sched)
    db.commit()
    db.refresh(sched)
    if sched.enabled:
        sched_engine.register_job(sched)
        db.refresh(sched)
    return sched


@router.patch("/api/schedules/{schedule_id}", response_model=ScheduleRead)
def update_schedule(schedule_id: uuid.UUID, body: ScheduleUpdate, db: Db):
    sched = db.get(Schedule, schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    if body.cadence is not None:
        sched.cadence = body.cadence
    if body.enabled is not None:
        sched.enabled = body.enabled
    if body.source_override_url is not None:
        sched.source_override_url = body.source_override_url or None
    db.commit()
    db.refresh(sched)

    if sched.enabled:
        sched_engine.register_job(sched)
    else:
        sched_engine.unregister_job(str(sched.id))
        sched.next_run_at = None
        db.commit()
    db.refresh(sched)
    return sched


@router.delete("/api/schedules/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: uuid.UUID, db: Db):
    sched = db.get(Schedule, schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    sched_engine.unregister_job(str(sched.id))
    db.delete(sched)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/schedules/{schedule_id}/run", response_model=ScheduleRead)
def run_schedule_now(schedule_id: uuid.UUID, request: Request, db: Db):
    sched = db.get(Schedule, schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    # Request is accepted immediately; status appears in the shared task center.
    # The event-driven analysis worker scales from zero when the queue receives it.
    sched_engine.trigger_now(str(sched.id), request.app.state.tasks)
    return sched


class ConfirmSource(BaseModel):
    url: str


@router.post("/api/schedules/{schedule_id}/confirm-source", response_model=ScheduleRead)
def confirm_source(schedule_id: uuid.UUID, body: ConfirmSource, db: Db):
    sched = db.get(Schedule, schedule_id)
    if not sched:
        raise HTTPException(status_code=404, detail="Schedule not found")
    sched.source_override_url = body.url
    sched.needs_attention = False
    sched.last_status = "idle"
    db.commit()
    db.refresh(sched)
    return sched


@router.get("/api/providers/{provider_id}/source-preview", response_model=SourcePreview)
def source_preview(provider_id: uuid.UUID, request: Request, db: Db):
    """Resolve a candidate source (no fetch of full text) for the confirm UI."""
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    domain = _ensure_domain(provider, db)

    # Browser rendering belongs to the queued analysis worker. The web image
    # deliberately stays lightweight and uses static/API discovery here.
    resolver = PolicySourceResolver(allow_headless=False)
    cand = resolver.resolve_candidate(provider.name, domain)
    if not cand:
        return SourcePreview(url=None, strategy=None, confidence=0.0, auto=False,
                             notes="No source could be resolved", resolved=False)
    from poligrapher_app.services.acquisition import AUTO_CONFIDENCE

    return SourcePreview(
        url=cand.url,
        strategy=cand.strategy,
        confidence=cand.confidence,
        auto=cand.confidence >= AUTO_CONFIDENCE,
        select=cand.select,
        notes=cand.notes,
        resolved=True,
    )
