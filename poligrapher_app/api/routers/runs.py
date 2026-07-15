import uuid
import os
import tempfile
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import Policy, Provider, Schedule, TaskRecord
from poligrapher_app.api.schemas import (
    ProviderRead,
    ProviderSourceUpdate,
    RunGroup,
    ScheduleRead,
    ScheduleToggle,
    TaskStatus,
)
from poligrapher_app.services import scheduler as sched_engine
from poligrapher_app.services.tasks import task_public

router = APIRouter(tags=["runs"])

Db = Annotated[Session, Depends(get_db)]

def _provider_or_404(provider_id: uuid.UUID, db: Session) -> Provider:
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider


def _task_of(registry, task_id: str) -> TaskStatus:
    return TaskStatus(**(registry.get(task_id) or {"task_id": task_id, "status": "running"}))


# ── Provider source ───────────────────────────────────────────────────────────

@router.patch("/api/providers/{provider_id}/source", response_model=ProviderRead)
def set_source(provider_id: uuid.UUID, body: ProviderSourceUpdate, db: Db):
    provider = _provider_or_404(provider_id, db)
    provider.source_url = body.source_url.strip() or None
    provider.source_status = "unchecked" if provider.source_url else "missing"
    provider.source_checked_at = None
    provider.source_http_status = None
    provider.source_final_url = None
    db.commit()
    db.refresh(provider)
    from poligrapher_app.api.routers.providers import _provider_read

    return _provider_read(provider)


# ── Runs list ─────────────────────────────────────────────────────────────────

@router.get("/api/providers/{provider_id}/runs", response_model=list[RunGroup])
def list_runs(provider_id: uuid.UUID, db: Db):
    provider = _provider_or_404(provider_id, db)
    policies = sorted(provider.policies, key=lambda p: p.created_at, reverse=True)
    linked_tasks: dict[str, TaskStatus] = {}
    tasks = (
        db.query(TaskRecord)
        .filter(TaskRecord.provider_id == str(provider_id), TaskRecord.run_id.isnot(None))
        .order_by(TaskRecord.created_at.desc())
        .all()
    )
    for task in tasks:
        linked_tasks.setdefault(task.run_id, TaskStatus(**task_public(task)))

    groups: dict[str, RunGroup] = {}
    ordered: list[RunGroup] = []
    for p in policies:
        if p.method == "pdf_upload":
            ordered.append(RunGroup(
                run_id=str(p.id), run_group=None, kind="upload", scheduled=p.scheduled,
                capture_date=p.capture_date, created_at=p.created_at, runs=[p],
                task=linked_tasks.get(str(p.id)),
            ))
            continue
        if p.run_group is None:
            # Imported records predate method/run-group metadata. Keep them
            # standalone and do not infer how the source was processed.
            ordered.append(RunGroup(
                run_id=str(p.id), run_group=None, kind="legacy", scheduled=p.scheduled,
                capture_date=p.capture_date, created_at=p.created_at, runs=[p],
                task=linked_tasks.get(str(p.id)),
            ))
            continue
        key = str(p.run_group)
        if key not in groups:
            groups[key] = RunGroup(
                run_id=key, run_group=key, kind="comparison", scheduled=p.scheduled,
                capture_date=p.capture_date, created_at=p.created_at, runs=[],
                task=linked_tasks.get(key),
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
                              provider_id=provider.id, provider_name=provider.name, total=1)
    registry.enqueue(task_id, {
        "kind": "comparison", "provider_id": str(provider.id), "scheduled": False
    })
    return _task_of(registry, task_id)


# ── One-off uploaded PDF ──────────────────────────────────────────────────────

@router.post("/api/providers/{provider_id}/uploads", response_model=TaskStatus)
async def upload_pdf(provider_id: uuid.UUID, request: Request, db: Db,
                     pdf_file: UploadFile = File(...)):
    provider = _provider_or_404(provider_id, db)
    if not pdf_file.filename:
        raise HTTPException(status_code=422, detail="A PDF file is required")

    from poligrapher_app.services.storage import get_storage, source_key

    day = date.today()
    filename = os.path.basename(pdf_file.filename)
    policy = Policy(provider_id=provider.id, url=filename, source="pdf", method="pdf_upload",
                    scheduled=False, capture_date=day, source_filename=filename)
    db.add(policy)
    db.commit()
    db.refresh(policy)

    temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
    try:
        with tempfile.NamedTemporaryFile(prefix="poligrapher-upload-", suffix=".pdf",
                                         dir=temp_root) as upload:
            while chunk := await pdf_file.read(1024 * 1024):
                upload.write(chunk)
            upload.flush()
            from poligrapher_app.services.runs import file_hash
            policy.content_hash = file_hash(upload.name)
            policy.source_blob_key = source_key(policy.id, filename)
            get_storage().upload_file(policy.source_blob_key, upload.name,
                                      content_type="application/pdf")
            db.commit()
    except Exception:
        db.delete(policy)
        db.commit()
        raise

    registry = request.app.state.tasks
    task_id = registry.create(kind="upload", title=f"Upload · {provider.name}",
                              provider_id=provider.id, provider_name=provider.name,
                              policy_id=str(policy.id), run_id=policy.id, total=1)
    registry.enqueue(task_id, {"kind": "upload", "policy_id": str(policy.id)})
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
