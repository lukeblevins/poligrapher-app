import uuid
import io
import os
import tempfile
import zipfile
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import Policy, Provider, Schedule, TaskRecord
from poligrapher_app.api.schemas import (
    ProviderRead,
    ProviderSourceUpdate,
    RerunAvailability,
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


def _policies_for_run(provider_id: uuid.UUID, run_id: uuid.UUID, db: Session) -> list[Policy]:
    grouped = (
        db.query(Policy)
        .filter(Policy.provider_id == provider_id, Policy.run_group == run_id)
        .order_by(Policy.created_at)
        .all()
    )
    if grouped:
        return grouped
    policy = db.get(Policy, run_id)
    return [policy] if policy and policy.provider_id == provider_id else []


def _rerun_availability(policies: list[Policy]) -> RerunAvailability:
    if not policies:
        return RerunAvailability(available=False, reason="Run not found")
    from poligrapher_app.services.storage import get_storage

    storage = get_storage()
    upload = next((policy for policy in policies if policy.method == "pdf_upload"), None)
    if upload:
        available = bool(upload.source_blob_key and storage.exists(upload.source_blob_key))
        return RerunAvailability(
            available=available,
            reason=None if available else "The original PDF is not available",
        )

    website = next((policy for policy in policies if policy.method == "website"), None)
    if not website or not website.artifact_blob_key or not storage.exists(website.artifact_blob_key):
        return RerunAvailability(available=False, reason="The saved website copy is not available")
    try:
        with zipfile.ZipFile(io.BytesIO(storage.open_bytes(website.artifact_blob_key))) as archive:
            names = {os.path.basename(name) for name in archive.namelist()}
    except (OSError, zipfile.BadZipFile):
        return RerunAvailability(available=False, reason="The saved website copy cannot be read")
    available = bool(names.intersection({"output.html", "cleaned.html"}) and "output.pdf" in names)
    return RerunAvailability(
        available=available,
        reason=None if available else "The saved website copy is incomplete",
    )


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


@router.get(
    "/api/providers/{provider_id}/runs/{run_id}/rerun-availability",
    response_model=RerunAvailability,
)
def rerun_availability(provider_id: uuid.UUID, run_id: uuid.UUID, db: Db):
    _provider_or_404(provider_id, db)
    return _rerun_availability(_policies_for_run(provider_id, run_id, db))


@router.post(
    "/api/providers/{provider_id}/runs/{run_id}/rerun",
    response_model=TaskStatus,
)
def rerun(provider_id: uuid.UUID, run_id: uuid.UUID, request: Request, db: Db):
    provider = _provider_or_404(provider_id, db)
    originals = _policies_for_run(provider_id, run_id, db)
    availability = _rerun_availability(originals)
    if not availability.available:
        raise HTTPException(status_code=409, detail=availability.reason)

    registry = request.app.state.tasks
    upload = next((policy for policy in originals if policy.method == "pdf_upload"), None)
    if upload:
        policy = Policy(
            provider_id=provider.id,
            url=upload.url,
            source="pdf",
            method="pdf_upload",
            scheduled=False,
            capture_date=upload.capture_date,
            source_filename=upload.source_filename,
            rerun_of_policy_id=upload.id,
        )
        db.add(policy)
        db.commit()
        db.refresh(policy)
        task_id = registry.create(
            kind="rerun-upload",
            title=f"Re-run PDF · {provider.name}",
            provider_id=provider.id,
            provider_name=provider.name,
            policy_id=policy.id,
            run_id=policy.id,
            total=1,
        )
        registry.enqueue(task_id, {
            "kind": "rerun-upload",
            "original_policy_id": str(upload.id),
            "policy_id": str(policy.id),
        })
        return _task_of(registry, task_id)

    website = next(policy for policy in originals if policy.method == "website")
    original_pdf = next((policy for policy in originals if policy.method == "pdf_from_page"), None)
    group_id = uuid.uuid4()
    new_website = Policy(
        provider_id=provider.id,
        url=website.url,
        source="webpage",
        method="website",
        run_group=group_id,
        scheduled=False,
        capture_date=website.capture_date,
        rerun_of_policy_id=website.id,
    )
    new_pdf = Policy(
        provider_id=provider.id,
        url=website.url,
        source="pdf",
        method="pdf_from_page",
        run_group=group_id,
        scheduled=False,
        capture_date=website.capture_date,
        rerun_of_policy_id=original_pdf.id if original_pdf else website.id,
    )
    db.add_all([new_website, new_pdf])
    db.commit()
    db.refresh(new_website)
    db.refresh(new_pdf)
    task_id = registry.create(
        kind="rerun-comparison",
        title=f"Re-run comparison · {provider.name}",
        provider_id=provider.id,
        provider_name=provider.name,
        run_id=group_id,
        total=1,
    )
    registry.enqueue(task_id, {
        "kind": "rerun-comparison",
        "original_policy_id": str(website.id),
        "website_policy_id": str(new_website.id),
        "pdf_policy_id": str(new_pdf.id),
    })
    return _task_of(registry, task_id)


@router.delete(
    "/api/providers/{provider_id}/runs/{run_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_run(provider_id: uuid.UUID, run_id: uuid.UUID, db: Db):
    _provider_or_404(provider_id, db)
    policies = _policies_for_run(provider_id, run_id, db)
    if not policies:
        raise HTTPException(status_code=404, detail="Run not found")
    blob_keys = {
        key
        for policy in policies
        for key in (policy.source_blob_key, policy.artifact_blob_key)
        if key
    }
    for policy in policies:
        db.delete(policy)
    db.commit()

    from poligrapher_app.services.storage import get_storage

    storage = get_storage()
    for key in blob_keys:
        try:
            storage.delete(key)
        except Exception:
            pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
