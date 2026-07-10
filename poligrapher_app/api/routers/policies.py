import uuid
import os
import tempfile
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.mapping import sync_policy_from_doc
from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.api.schemas import PolicyRead, TaskStatus

router = APIRouter(tags=["policies"])

Db = Annotated[Session, Depends(get_db)]


def _task_status(registry, task_id: str) -> TaskStatus:
    task = registry.get(task_id) or {"status": "running"}
    return TaskStatus(task_id=task_id, **task)


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
        provider_name=policy.provider.name,
        policy_id=str(policy_id),
        total=1,
    )
    def _run():
        from poligrapher_app.api.database import SessionLocal
        from poligrapher_app.services.pipeline import PipelineCancelled, generate_graph
        from poligrapher_app.services.persistence import persist_workspace, temporary_document

        db2 = SessionLocal()
        try:
            try:
                policy2 = db2.get(Policy, policy_id)
                if policy2:
                    with temporary_document(policy2) as (doc2, workspace):
                        generate_graph(doc2, should_cancel=lambda: registry.is_cancelled(task_id))
                        persist_workspace(policy2, doc2, workspace / "artifacts.zip")
                        sync_policy_from_doc(policy2, doc2, db2)
                registry.incr(task_id, "completed")
                registry.set_done(task_id)
            except PipelineCancelled:
                # Staging is discarded by the pipeline; nothing to roll back here.
                registry.set_cancelled(task_id)
            except Exception as exc:
                registry.set_failed(task_id, str(exc))
                failed = db2.get(Policy, policy_id)
                if failed:
                    if not failed.graph_data:
                        failed.pipeline_status = "failed"
                    failed.pipeline_errors = list(failed.pipeline_errors or []) + [
                        {"message": str(exc)}
                    ]
                    db2.commit()
        finally:
            db2.close()

    registry.submit(task_id, _run)
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
        provider_name=policy.provider.name,
        policy_id=str(policy_id),
        total=1,
    )
    def _run():
        from poligrapher_app.api.database import SessionLocal
        from poligrapher_app.services.scoring import score_gdpr, score_privacy
        from poligrapher_app.services.persistence import temporary_document

        db2 = SessionLocal()
        try:
            if registry.is_cancelled(task_id):
                registry.set_cancelled(task_id)
                return
            policy2 = db2.get(Policy, policy_id)
            if not policy2:
                registry.set_failed(task_id, "Policy no longer exists")
                return
            with temporary_document(policy2, restore_artifacts=True) as (doc, _):
                score_privacy(doc)
                score_gdpr(doc)
            # Skip persistence if cancelled mid-scoring so results are all-or-nothing.
            if registry.is_cancelled(task_id):
                registry.set_cancelled(task_id)
                return
            if policy2:  # may have been deleted mid-run
                sync_policy_from_doc(policy2, doc, db2)
            registry.incr(task_id, "completed")
            registry.set_done(task_id)
        finally:
            db2.close()

    registry.submit(task_id, _run)
    return _task_status(registry, task_id)


@router.post("/api/refresh", response_model=TaskStatus)
def refresh_all(request: Request, db: Db):
    policy_ids = [p.id for p in db.query(Policy).filter(Policy.pipeline_status == "pending").all()]
    registry = request.app.state.tasks
    task_id = registry.create(
        label="Refresh pending", title="Refresh pending", kind="refresh", total=len(policy_ids)
    )

    def _run():
        from poligrapher_app.api.database import SessionLocal
        from poligrapher_app.services.pipeline import PipelineCancelled, generate_graph
        from poligrapher_app.services.persistence import persist_workspace, temporary_document

        db2 = SessionLocal()
        try:
            for pid in policy_ids:
                if registry.is_cancelled(task_id):
                    registry.set_cancelled(task_id)
                    return
                p = db2.get(Policy, pid)
                if not p:
                    continue
                try:
                    with temporary_document(p) as (doc, workspace):
                        generate_graph(doc, should_cancel=lambda: registry.is_cancelled(task_id))
                        persist_workspace(p, doc, workspace / "artifacts.zip")
                        sync_policy_from_doc(p, doc, db2)
                except PipelineCancelled:
                    registry.set_cancelled(task_id)
                    return
                except Exception:
                    if not p.graph_data:
                        p.pipeline_status = "failed"
                    p.pipeline_errors = list(p.pipeline_errors or []) + [
                        {"message": "Refresh failed"}
                    ]
                    db2.commit()
                    registry.incr(task_id, "failed")
                registry.incr(task_id, "completed")
            registry.set_done(task_id)
        finally:
            db2.close()

    registry.submit(task_id, _run)
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

    def _run():
        from poligrapher_app.api.database import SessionLocal
        from poligrapher_app.services.scoring import score_gdpr, score_privacy
        from poligrapher_app.services.persistence import temporary_document

        db2 = SessionLocal()
        try:
            for pid in policy_ids:
                if registry.is_cancelled(task_id):
                    registry.set_cancelled(task_id)
                    return
                p = db2.get(Policy, pid)
                if not p:
                    continue
                try:
                    with temporary_document(p, restore_artifacts=True) as (doc, _):
                        score_privacy(doc)
                        score_gdpr(doc)
                        sync_policy_from_doc(p, doc, db2)
                except Exception:
                    registry.incr(task_id, "failed")
                registry.incr(task_id, "completed")
            registry.set_done(task_id)
        finally:
            db2.close()

    registry.submit(task_id, _run)
    return _task_status(registry, task_id)
