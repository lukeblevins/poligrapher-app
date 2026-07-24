import uuid
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.api.schemas import PolicyRead, TaskStatus

router = APIRouter(tags=["policies"])

Db = Annotated[Session, Depends(get_db)]


def _task_status(registry, task_id: str) -> TaskStatus:
    task = registry.get(task_id) or {"task_id": task_id, "status": "running"}
    return TaskStatus(**task)


# ── Provider-scoped policy routes ─────────────────────────────────────────────

@router.get("/api/providers/{provider_id}/policies", response_model=list[PolicyRead])
def list_policies(provider_id: uuid.UUID, db: Db):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")
    return provider.policies


@router.post(
    "/api/providers/{provider_id}/policies",
    response_model=PolicyRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_policy(
    provider_id: uuid.UUID,
    db: Db,
    url: str = Form(default=""),
    source: str = Form(...),
    capture_date: str = Form(default=""),
    pdf_file: UploadFile | None = File(default=None),
):
    provider = db.get(Provider, provider_id)
    if not provider:
        raise HTTPException(status_code=404, detail="Provider not found")

    if source not in ("webpage", "pdf"):
        raise HTTPException(status_code=422, detail="source must be 'webpage' or 'pdf'")

    parsed_date = date.fromisoformat(capture_date) if capture_date else date.today()
    if source == "pdf":
        if not pdf_file or not pdf_file.filename:
            raise HTTPException(status_code=422, detail="A PDF file is required when source is 'pdf'")
        policy_url = Path(pdf_file.filename).name
    else:
        if not url:
            raise HTTPException(status_code=422, detail="A URL is required when source is 'webpage'")
        policy_url = url

    policy = Policy(
        provider_id=provider_id,
        url=policy_url,
        source=source,
        capture_date=parsed_date,
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    if source == "pdf":
        from poligrapher_app.services.runs import file_hash
        from poligrapher_app.services.storage import get_storage, source_key

        temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
        try:
            with tempfile.NamedTemporaryFile(prefix="poligrapher-upload-", suffix=".pdf",
                                             dir=temp_root) as upload:
                while chunk := await pdf_file.read(1024 * 1024):
                    upload.write(chunk)
                upload.flush()
                policy.source_filename = policy_url
                policy.source_blob_key = source_key(policy.id, policy_url)
                policy.content_hash = file_hash(upload.name)
                get_storage().upload_file(policy.source_blob_key, upload.name,
                                          content_type="application/pdf")
                db.commit()
                db.refresh(policy)
        except Exception:
            db.delete(policy)
            db.commit()
            raise
    return policy


# ── Single-policy routes ──────────────────────────────────────────────────────

@router.delete("/api/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(policy_id: uuid.UUID, db: Db):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    blob_keys = [policy.source_blob_key, policy.artifact_blob_key]
    db.delete(policy)
    db.commit()
    from poligrapher_app.services.storage import get_storage

    storage = get_storage()
    for key in filter(None, blob_keys):
        try:
            storage.delete(key)
        except Exception:
            # The database delete is authoritative; storage lifecycle/operations
            # can clean an orphan without resurrecting the policy record.
            pass
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/policies/{policy_id}/generate", response_model=TaskStatus)
def trigger_generate(policy_id: uuid.UUID, request: Request, db: Db):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    registry = request.app.state.tasks
    task_id = registry.create(
        kind="generate",
        title=f"Generate · {policy.provider.name}",
        provider_id=policy.provider_id,
        provider_name=policy.provider.name,
        policy_id=str(policy_id),
        run_id=policy.run_group or policy.id,
        total=1,
    )
    registry.enqueue(task_id, {"kind": "generate", "policy_id": str(policy_id)})
    return _task_status(registry, task_id)


@router.post("/api/policies/{policy_id}/score", response_model=TaskStatus)
def trigger_score(policy_id: uuid.UUID, request: Request, db: Db):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    registry = request.app.state.tasks
    task_id = registry.create(
        kind="score",
        title=f"Score · {policy.provider.name}",
        provider_id=policy.provider_id,
        provider_name=policy.provider.name,
        policy_id=str(policy_id),
        run_id=policy.run_group or policy.id,
        total=1,
    )
    registry.enqueue(task_id, {"kind": "score", "policy_id": str(policy_id)})
    return _task_status(registry, task_id)


@router.post("/api/refresh", response_model=TaskStatus)
def refresh_all(request: Request, db: Db):
    policy_ids = [p.id for p in db.query(Policy).filter(Policy.pipeline_status == "pending").all()]
    registry = request.app.state.tasks
    task_id = registry.create(
        label="Refresh pending", title="Refresh pending", kind="refresh", total=len(policy_ids)
    )

    registry.enqueue(task_id, {
        "kind": "refresh", "policy_ids": [str(policy_id) for policy_id in policy_ids]
    })
    return _task_status(registry, task_id)


@router.post("/api/score-all", response_model=TaskStatus)
def score_all(request: Request, db: Db):
    # Score every policy that has graph artifacts (a graph is required to score).
    policy_ids = [
        p.id for p in db.query(Policy).filter(Policy.pipeline_status == "succeeded").all()
    ]
    registry = request.app.state.tasks
    task_id = registry.create(
        label="Score all", title="Score all", kind="score-all", total=len(policy_ids)
    )

    registry.enqueue(task_id, {
        "kind": "score-all", "policy_ids": [str(policy_id) for policy_id in policy_ids]
    })
    return _task_status(registry, task_id)
