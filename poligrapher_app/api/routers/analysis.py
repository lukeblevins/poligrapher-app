import uuid
import hmac
import io
import os
from pathlib import PurePosixPath
import zipfile
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import AnalysisResult, Policy
from poligrapher_app.api.schemas import Assessments, GraphElements, GraphStats, TaskOutput, TaskStatus
from poligrapher_app.services.graph import gdpr_report, readability_from_gdpr

router = APIRouter(tags=["analysis"])

Db = Annotated[Session, Depends(get_db)]

PUBLIC_GRAPH_ARTIFACT_NAMES = frozenset({
    "graph.yml",
    "graph.graphml",
    "graph-original.yml",
    "graph-original.full.yml",
    "graph-original.graphml",
})
MAX_PUBLIC_GRAPH_ENTRIES = 10
MAX_PRIVATE_ARTIFACT_BYTES = 256 * 1024 * 1024
MAX_PRIVATE_ARTIFACT_ENTRIES = 500
MAX_PUBLIC_GRAPH_EXPANDED_BYTES = 100 * 1024 * 1024


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


def build_public_graph_archive(payload: bytes) -> bytes:
    """Return a graph-only ZIP from a private pipeline artifact archive."""

    if len(payload) > MAX_PRIVATE_ARTIFACT_BYTES:
        raise ValueError("Artifact archive exceeds public download limits")
    output = io.BytesIO()
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as source:
            if len(source.infolist()) > MAX_PRIVATE_ARTIFACT_ENTRIES:
                raise ValueError("Artifact archive contains too many entries")
            selected: list[zipfile.ZipInfo] = []
            selected_names: set[str] = set()
            expanded_bytes = 0
            for info in source.infolist():
                path = PurePosixPath(info.filename)
                if (
                    info.is_dir()
                    or path.is_absolute()
                    or ".." in path.parts
                    or path.name not in PUBLIC_GRAPH_ARTIFACT_NAMES
                    or path.name in selected_names
                ):
                    continue
                expanded_bytes += info.file_size
                if (
                    len(selected) >= MAX_PUBLIC_GRAPH_ENTRIES
                    or expanded_bytes > MAX_PUBLIC_GRAPH_EXPANDED_BYTES
                ):
                    raise ValueError("Graph artifact archive exceeds public download limits")
                selected.append(info)
                selected_names.add(path.name)
            if not selected:
                raise FileNotFoundError("No graph artifacts found in archive")
            with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as target:
                for info in selected:
                    target.writestr(path_name(info.filename), source.read(info))
    except zipfile.BadZipFile as exc:
        raise ValueError("Artifact archive is not a valid ZIP") from exc
    return output.getvalue()


def path_name(value: str) -> str:
    """Use a stable flat filename for an allowlisted ZIP member."""

    return PurePosixPath(value).name


@router.get("/api/policies/{policy_id}/graph-artifacts")
def download_graph_artifacts(policy_id: uuid.UUID, db: Db):
    policy = _get_policy_or_404(policy_id, db)
    if not policy.graph_artifacts_available:
        raise HTTPException(status_code=404, detail="No graph artifact archive found")
    from poligrapher_app.services.storage import get_storage

    try:
        private_payload = get_storage().open_bytes(policy.artifact_blob_key)
        payload = build_public_graph_archive(private_payload)
    except (FileNotFoundError, OSError):
        raise HTTPException(status_code=404, detail="No graph artifact archive found") from None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return StreamingResponse(
        io.BytesIO(payload),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{policy.id}-graph-artifacts.zip"',
            "X-Content-Type-Options": "nosniff",
        },
    )


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
    return TaskStatus(**task)


@router.get("/api/tasks/{task_id}/output", response_model=TaskOutput)
def get_task_output(task_id: str, request: Request):
    output = request.app.state.tasks.get_output(task_id)
    if output is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskOutput(**output)


@router.post("/api/tasks/{task_id}/cancel", response_model=TaskStatus)
def cancel_task(task_id: str, request: Request):
    registry = request.app.state.tasks
    if not registry.cancel(task_id):
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatus(**registry.get(task_id))


@router.post("/api/tasks/{task_id}/retry-failures", response_model=TaskStatus)
def retry_task_failures(task_id: str, request: Request):
    registry = request.app.state.tasks
    retry_id = registry.retry_failed_subtasks(task_id)
    if retry_id is None:
        raise HTTPException(
            status_code=409,
            detail="This task has no transient failed subtasks that can be retried automatically",
        )
    return TaskStatus(**registry.get(retry_id))
