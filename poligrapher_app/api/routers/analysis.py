import uuid
import hmac
import io
import os
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import AnalysisResult, Policy
from poligrapher_app.api.schemas import Assessments, GraphElements, GraphStats, TaskStatus
from poligrapher_app.services.graph import gdpr_report, readability_from_gdpr

router = APIRouter(tags=["analysis"])

Db = Annotated[Session, Depends(get_db)]


def _get_policy_or_404(policy_id: uuid.UUID, db: Session) -> Policy:
    policy = db.get(Policy, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


def _latest_details(policy_id: uuid.UUID, analysis_type: str, db: Session) -> dict | None:
    result = (
        db.query(AnalysisResult)
        .filter_by(policy_id=policy_id, analysis_type=analysis_type)
        .order_by(AnalysisResult.created_at.desc())
        .first()
    )
    return result.details if result else None


@router.get("/api/policies/{policy_id}/graph", response_model=GraphElements)
def get_graph(policy_id: uuid.UUID, db: Db):
    policy = _get_policy_or_404(policy_id, db)
    if not policy.graph_data:
        raise HTTPException(status_code=404, detail="No graph artifacts found for this policy")
    return GraphElements(elements=policy.graph_data.get("elements", []))


@router.get("/api/policies/{policy_id}/stats", response_model=GraphStats)
def get_stats(policy_id: uuid.UUID, db: Db):
    policy = _get_policy_or_404(policy_id, db)
    return GraphStats(stats=policy.graph_stats)


@router.get("/api/policies/{policy_id}/export")
def export_canonical(policy_id: uuid.UUID, db: Db):
    policy = _get_policy_or_404(policy_id, db)
    if not policy.graph_data:
        raise HTTPException(status_code=404, detail="No persisted analysis found")
    return JSONResponse({
        "policy_id": str(policy.id),
        "source": policy.source,
        "method": policy.method,
        "capture_date": policy.capture_date.isoformat() if policy.capture_date else None,
        "graph": policy.graph_data,
        "statistics": policy.graph_stats,
        "privacy": _latest_details(policy.id, "privacy", db),
        "gdpr": _latest_details(policy.id, "gdpr", db),
    })


def _require_export_token(authorization: str | None) -> None:
    expected = os.getenv("EXPORT_TOKEN")
    supplied = authorization.removeprefix("Bearer ") if authorization else ""
    if not expected or not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="A valid export token is required")


@router.get("/api/policies/{policy_id}/artifacts")
def download_artifacts(policy_id: uuid.UUID, db: Db,
                       authorization: str | None = Header(default=None)):
    _require_export_token(authorization)
    policy = _get_policy_or_404(policy_id, db)
    if not policy.artifact_blob_key:
        raise HTTPException(status_code=404, detail="No artifact archive found")
    from poligrapher_app.services.storage import get_storage

    payload = get_storage().open_bytes(policy.artifact_blob_key)
    return StreamingResponse(io.BytesIO(payload), media_type="application/zip",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{policy.id}-artifacts.zip"'})


@router.get("/api/policies/{policy_id}/source")
def download_source(policy_id: uuid.UUID, db: Db,
                    authorization: str | None = Header(default=None)):
    _require_export_token(authorization)
    policy = _get_policy_or_404(policy_id, db)
    if not policy.source_blob_key:
        raise HTTPException(status_code=404, detail="No retained source file found")
    from poligrapher_app.services.storage import get_storage

    payload = get_storage().open_bytes(policy.source_blob_key)
    filename = policy.source_filename or "source.pdf"
    return StreamingResponse(io.BytesIO(payload), media_type="application/pdf",
                             headers={"Content-Disposition":
                                      f'attachment; filename="{filename}"'})


@router.get("/api/policies/{policy_id}/assessments", response_model=Assessments)
def get_assessments(policy_id: uuid.UUID, db: Db):
    _get_policy_or_404(policy_id, db)

    privacy_details = _latest_details(policy_id, "privacy", db)
    privacy = privacy_details if privacy_details and privacy_details.get("success") else None

    gdpr_details = _latest_details(policy_id, "gdpr", db)
    return Assessments(
        privacy=privacy,
        gdpr=gdpr_report(gdpr_details),
        readability=readability_from_gdpr(gdpr_details),
    )


@router.get("/api/tasks", response_model=list[TaskStatus])
def list_tasks(request: Request):
    return [TaskStatus(**task) for task in request.app.state.tasks.list()]


@router.get("/api/tasks/{task_id}", response_model=TaskStatus)
def get_task_status(task_id: str, request: Request):
    task = request.app.state.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatus(task_id=task_id, **task)


@router.post("/api/tasks/{task_id}/cancel", response_model=TaskStatus)
def cancel_task(task_id: str, request: Request):
    registry = request.app.state.tasks
    if not registry.cancel(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatus(task_id=task_id, **registry.get(task_id))
