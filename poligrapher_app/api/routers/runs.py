import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import Policy, Provider, Schedule
from poligrapher_app.api.schemas import (
    ProviderRead,
    ProviderSourceUpdate,
    RunGroup,
    ScheduleRead,
    ScheduleToggle,
    TaskStatus,
)
from poligrapher_app.api.utils import provider_slug
from poligrapher_app.services import runs as runs_service
from poligrapher_app.services import scheduler as sched_engine

router = APIRouter(tags=["runs"])

Db = Annotated[Session, Depends(get_db)]

OUTPUT_BASE = Path(__file__).parent.parent.parent.parent / "output"


def _provider_or_404(provider_id: uuid.UUID, db: Session) -> Provider:
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


def _task_of(registry, task_id: str) -> TaskStatus:
    return TaskStatus(task_id=task_id, **(registry.get(task_id) or {"status": "running"}))


def _submit(registry, task_id, fn) -> None:
    """Run ``fn`` (returns a status string) and settle the task accordingly."""

    def _wrapped():
        result = fn()
        if result == "cancelled":
            registry.set_cancelled(task_id)
        elif result in ("needs_source", "gone"):
            registry.set_failed(task_id, f"Run did not complete: {result}")
        else:
            registry.update(task_id, completed=1)
            registry.set_done(task_id)

    registry.submit(task_id, _wrapped)


# ── Provider source ───────────────────────────────────────────────────────────

@router.patch("/api/providers/{provider_id}/source", response_model=ProviderRead)
def set_source(provider_id: uuid.UUID, body: ProviderSourceUpdate, db: Db):
    provider = _provider_or_404(provider_id, db)
    provider.source_url = body.source_url.strip() or None
    db.commit()
    db.refresh(provider)
    from poligrapher_app.api.routers.providers import _provider_read

    return _provider_read(provider)


# ── Runs list ─────────────────────────────────────────────────────────────────

@router.get("/api/providers/{provider_id}/runs", response_model=list[RunGroup])
def list_runs(provider_id: uuid.UUID, db: Db):
    provider = _provider_or_404(provider_id, db)
    policies = sorted(provider.policies, key=lambda p: p.created_at, reverse=True)

    groups: dict[str, RunGroup] = {}
    ordered: list[RunGroup] = []
    for p in policies:
        if p.method == "pdf_upload" or p.run_group is None:
            ordered.append(RunGroup(
                run_group=None, kind="upload", scheduled=p.scheduled,
                capture_date=p.capture_date, created_at=p.created_at, runs=[p],
            ))
            continue
        key = str(p.run_group)
        if key not in groups:
            groups[key] = RunGroup(
                run_group=key, kind="comparison", scheduled=p.scheduled,
                capture_date=p.capture_date, created_at=p.created_at, runs=[],
            )
            ordered.append(groups[key])
        groups[key].runs.append(p)
    return ordered


# ── Trigger a comparison run now ──────────────────────────────────────────────

@router.post("/api/providers/{provider_id}/runs", response_model=TaskStatus)
def run_now(provider_id: uuid.UUID, request: Request, db: Db):
    provider = _provider_or_404(provider_id, db)
    registry = request.app.state.tasks
    task_id = registry.create(kind="comparison", title=f"Compare · {provider.name}",
                              provider_name=provider.name, total=1)
    pid = provider.id
    _submit(registry, task_id, lambda: runs_service.run_comparison(
        pid, scheduled=False, registry=registry, task_id=task_id))
    return _task_of(registry, task_id)


# ── One-off uploaded PDF ──────────────────────────────────────────────────────

@router.post("/api/providers/{provider_id}/uploads", response_model=TaskStatus)
async def upload_pdf(provider_id: uuid.UUID, request: Request, db: Db,
                     pdf_file: UploadFile = File(...)):
    provider = _provider_or_404(provider_id, db)
    if not pdf_file.filename:
        raise HTTPException(status_code=422, detail="A PDF file is required")

    day = date.today()
    out_dir = OUTPUT_BASE / provider_slug(provider.name) / f"{day.isoformat()}_upload_{uuid.uuid4().hex[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / Path(pdf_file.filename).name
    dest.write_bytes(await pdf_file.read())

    policy = Policy(provider_id=provider.id, url=str(dest), source="pdf", method="pdf_upload",
                    scheduled=False, capture_date=day, output_dir=str(out_dir),
                    content_hash=runs_service.file_hash(str(dest)))
    db.add(policy)
    db.commit()
    db.refresh(policy)

    registry = request.app.state.tasks
    task_id = registry.create(kind="upload", title=f"Upload · {provider.name}",
                              provider_name=provider.name, policy_id=str(policy.id), total=1)
    pid = policy.id
    _submit(registry, task_id, lambda: runs_service.run_upload(
        pid, registry=registry, task_id=task_id))
    return _task_of(registry, task_id)


# ── Schedule toggle (one schedule per provider, source = provider.source_url) ──

@router.put("/api/providers/{provider_id}/schedule", response_model=ScheduleRead)
def toggle_schedule(provider_id: uuid.UUID, body: ScheduleToggle, db: Db):
    provider = _provider_or_404(provider_id, db)
    if body.enabled and not provider.source_url:
        raise HTTPException(
            status_code=400,
            detail="Set a website policy source before enabling scheduled acquisition.",
        )
    sched = provider.schedules[0] if provider.schedules else None
    if sched is None:
        sched = Schedule(provider_id=provider.id, cadence=body.cadence or "weekly",
                         enabled=body.enabled)
        db.add(sched)
    else:
        sched.enabled = body.enabled
        if body.cadence:
            sched.cadence = body.cadence
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
