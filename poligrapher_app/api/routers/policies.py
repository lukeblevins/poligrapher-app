import uuid
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, Response, UploadFile, status
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.mapping import policy_doc_from_db, sync_policy_from_doc
from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.api.schemas import PolicyRead, TaskStatus

router = APIRouter(tags=["policies"])

Db = Annotated[Session, Depends(get_db)]

OUTPUT_BASE = Path(__file__).parent.parent.parent.parent / "output"


def _task_status(registry, task_id: str) -> TaskStatus:
    task = registry.get(task_id) or {"status": "running"}
    return TaskStatus(task_id=task_id, **{k: task[k] for k in
                      ("status", "error", "label", "total", "completed", "failed") if k in task})


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

    provider_slug = provider.name.replace(" ", "_")
    parsed_date = date.fromisoformat(capture_date) if capture_date else date.today()
    output_dir = OUTPUT_BASE / provider_slug / f"{parsed_date.isoformat()}_{source}"

    if source == "pdf":
        if not pdf_file or not pdf_file.filename:
            raise HTTPException(status_code=422, detail="A PDF file is required when source is 'pdf'")
        output_dir.mkdir(parents=True, exist_ok=True)
        dest = output_dir / pdf_file.filename
        dest.write_bytes(await pdf_file.read())
        policy_url = str(dest)
    else:
        if not url:
            raise HTTPException(status_code=422, detail="A URL is required when source is 'webpage'")
        policy_url = url

    policy = Policy(
        provider_id=provider_id,
        url=policy_url,
        source=source,
        capture_date=parsed_date,
        output_dir=str(output_dir),
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return policy


# ── Single-policy routes ──────────────────────────────────────────────────────

@router.delete("/api/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_policy(policy_id: uuid.UUID, db: Db):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    db.delete(policy)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/api/policies/{policy_id}/generate", response_model=TaskStatus)
def trigger_generate(policy_id: uuid.UUID, request: Request, db: Db):
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    registry = request.app.state.tasks
    task_id = registry.create(policy_id=str(policy_id))
    doc = policy_doc_from_db(policy)

    def _run():
        from poligrapher_app.api.database import SessionLocal
        from poligrapher_app.services.pipeline import generate_graph

        db2 = SessionLocal()
        try:
            try:
                generate_graph(doc)
                sync_policy_from_doc(db2.get(Policy, policy_id), doc, db2)
                registry.set_done(task_id)
            except Exception as exc:
                registry.set_failed(task_id, str(exc))
                failed = db2.get(Policy, policy_id)
                if failed:
                    failed.pipeline_status = "failed"
                    failed.pipeline_errors = doc.errors
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
    task_id = registry.create(policy_id=str(policy_id))
    doc = policy_doc_from_db(policy)

    def _run():
        from poligrapher_app.api.database import SessionLocal
        from poligrapher_app.services.scoring import score_gdpr, score_privacy

        db2 = SessionLocal()
        try:
            score_privacy(doc)
            score_gdpr(doc)
            sync_policy_from_doc(db2.get(Policy, policy_id), doc, db2)
            registry.set_done(task_id)
        finally:
            db2.close()

    registry.submit(task_id, _run)
    return _task_status(registry, task_id)


@router.post("/api/refresh", response_model=TaskStatus)
def refresh_all(request: Request, db: Db):
    policy_ids = [p.id for p in db.query(Policy).filter(Policy.pipeline_status == "pending").all()]
    registry = request.app.state.tasks
    task_id = registry.create(label="Refresh pending", total=len(policy_ids))

    def _run():
        from poligrapher_app.api.database import SessionLocal
        from poligrapher_app.services.pipeline import generate_graph

        db2 = SessionLocal()
        try:
            for pid in policy_ids:
                p = db2.get(Policy, pid)
                if not p:
                    continue
                doc = policy_doc_from_db(p)
                try:
                    generate_graph(doc)
                    sync_policy_from_doc(p, doc, db2)
                except Exception:
                    p.pipeline_status = "failed"
                    p.pipeline_errors = doc.errors
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
    policy_ids = [p.id for p in db.query(Policy).filter(Policy.has_results == True).all()]  # noqa: E712
    registry = request.app.state.tasks
    task_id = registry.create(label="Score all", total=len(policy_ids))

    def _run():
        from poligrapher_app.api.database import SessionLocal
        from poligrapher_app.services.scoring import score_gdpr, score_privacy

        db2 = SessionLocal()
        try:
            for pid in policy_ids:
                p = db2.get(Policy, pid)
                if not p:
                    continue
                doc = policy_doc_from_db(p)
                try:
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
