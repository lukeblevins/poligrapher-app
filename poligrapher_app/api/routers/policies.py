import uuid
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import CompanyCollection, Policy, Provider
from poligrapher_app.api.schemas import (
    BulkActionPreview,
    BulkActionRequest,
    BulkSelection,
    PolicyRead,
    RetentionPreview,
    RetentionRequest,
    TaskStatus,
)
from poligrapher_app.services.retention import preview_retention

router = APIRouter(tags=["policies"])

Db = Annotated[Session, Depends(get_db)]


def _task_status(registry, task_id: str) -> TaskStatus:
    task = registry.get(task_id) or {"task_id": task_id, "status": "running"}
    return TaskStatus(**task)


def _selected_providers(selection: BulkSelection, db: Session) -> list[Provider]:
    provider_ids = set(selection.provider_ids)
    collections = (
        db.query(CompanyCollection)
        .filter(CompanyCollection.id.in_(selection.collection_ids))
        .all()
        if selection.collection_ids
        else []
    )
    if len(collections) != len(set(selection.collection_ids)):
        raise HTTPException(status_code=422, detail="One or more collections do not exist")
    provider_ids.update(provider.id for collection in collections for provider in collection.providers)
    if not provider_ids:
        raise HTTPException(status_code=422, detail="Select at least one company or collection")
    providers = db.query(Provider).filter(Provider.id.in_(provider_ids)).order_by(Provider.name).all()
    if len(providers) != len(provider_ids):
        raise HTTPException(status_code=422, detail="One or more companies do not exist")
    return providers


def _bulk_targets(body: BulkActionRequest, db: Session) -> tuple[list[Provider], list[Policy], list[str]]:
    providers = _selected_providers(body, db)
    provider_ids = [provider.id for provider in providers]
    query = db.query(Policy).filter(Policy.provider_id.in_(provider_ids))
    if body.operation == "score":
        query = query.filter(Policy.pipeline_status == "succeeded")
    candidates = query.order_by(Policy.provider_id, Policy.created_at.desc()).all()
    latest_by_provider: dict[uuid.UUID, Policy] = {}
    for policy in candidates:
        latest_by_provider.setdefault(policy.provider_id, policy)

    policies: list[Policy] = []
    skipped: list[str] = []
    for provider in providers:
        policy = latest_by_provider.get(provider.id)
        if policy is None:
            reason = "no completed analysis to score" if body.operation == "score" else "no analysis to generate"
            skipped.append(f"{provider.name} has {reason}")
        else:
            policies.append(policy)
    return providers, policies, skipped


def _bulk_analysis_targets(body: BulkActionRequest, db: Session) -> tuple[list[Provider], list[Provider], list[str]]:
    providers = _selected_providers(body, db)
    provider_ids = [provider.id for provider in providers]
    analyzed_ids = {
        provider_id
        for provider_id, graph_data in (
            db.query(Policy.provider_id, Policy.graph_data)
            .filter(Policy.provider_id.in_(provider_ids))
            .all()
        )
        if isinstance(graph_data, dict) and graph_data.get("elements")
    }

    eligible: list[Provider] = []
    skipped: list[str] = []
    for provider in providers:
        if provider.id in analyzed_ids:
            skipped.append(f"{provider.name} already has an analysis")
        elif provider.source_url:
            eligible.append(provider)
        else:
            skipped.append(f"{provider.name} has no policy source")
    return providers, eligible, skipped


@router.post("/api/bulk/preview", response_model=BulkActionPreview)
def preview_bulk_action(body: BulkActionRequest, db: Db):
    if body.operation == "generate":
        providers, eligible, skipped = _bulk_analysis_targets(body, db)
        eligible_names = [provider.name for provider in eligible]
    else:
        providers, policies, skipped = _bulk_targets(body, db)
        eligible = policies
        eligible_names = [policy.provider.name for policy in policies]
    return BulkActionPreview(
        operation=body.operation,
        provider_count=len(providers),
        eligible_count=len(eligible),
        skipped_count=len(skipped),
        collection_count=len(body.collection_ids),
        providers=eligible_names,
        skipped=skipped,
    )


@router.post("/api/bulk/run", response_model=TaskStatus)
def run_bulk_action(body: BulkActionRequest, request: Request, db: Db):
    if body.operation == "generate":
        providers, eligible_providers, skipped = _bulk_analysis_targets(body, db)
        eligible_count = len(eligible_providers)
    else:
        providers, policies, skipped = _bulk_targets(body, db)
        eligible_count = len(policies)
    if not eligible_count:
        raise HTTPException(status_code=422, detail="None of the selected companies has an eligible analysis")
    registry = request.app.state.tasks
    kind = "collection-analysis" if body.operation == "generate" else "bulk-score"
    unit = "companies" if body.operation == "generate" else "policies"
    task_id = registry.create(
        kind=kind,
        title=f"{'Analyze' if body.operation == 'generate' else 'Score'} · {eligible_count} {unit}",
        total=eligible_count,
    )
    registry.append_output(
        task_id,
        f"Selected {len(providers)} companies; {eligible_count} {unit} are eligible for {body.operation}.\n",
    )
    if skipped:
        registry.append_output(task_id, "Skipped: " + "; ".join(skipped) + "\n")
    payload = {
        "kind": kind,
        "provider_ids": [
            str(provider.id)
            for provider in (eligible_providers if body.operation == "generate" else providers)
        ],
        "skipped": skipped,
    }
    if body.operation == "score":
        payload["policy_ids"] = [str(policy.id) for policy in policies]
    registry.enqueue(task_id, payload)
    return _task_status(registry, task_id)


@router.post("/api/retention/preview", response_model=RetentionPreview)
def preview_retention_cleanup(body: RetentionRequest, db: Db):
    return RetentionPreview(**preview_retention(db, body.older_than_days))


@router.post("/api/retention/cleanup", response_model=TaskStatus)
def start_retention_cleanup(body: RetentionRequest, request: Request, db: Db):
    if not body.confirmed:
        raise HTTPException(status_code=422, detail="Retention cleanup requires explicit confirmation")
    preview = preview_retention(db, body.older_than_days)
    registry = request.app.state.tasks
    task_id = registry.create(
        kind="retention-cleanup",
        title=f"Retention cleanup · {body.older_than_days} days",
        total=preview["policy_count"],
    )
    registry.append_output(
        task_id,
        "Retention cleanup queued for "
        f"{preview['policy_count']} policies and up to {preview['artifact_count']} stored files.\n",
    )
    registry.enqueue(task_id, {
        "kind": "retention-cleanup",
        "older_than_days": body.older_than_days,
    })
    return _task_status(registry, task_id)


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
