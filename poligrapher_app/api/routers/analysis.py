import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from poligrapher_app.api.deps import get_db
from poligrapher_app.api.mapping import policy_doc_from_db
from poligrapher_app.api.models import AnalysisResult, Policy
from poligrapher_app.api.schemas import Assessments, GraphElements, GraphStats, TaskStatus
from poligrapher_app.services.graph import (
    build_cytoscape_elements,
    gdpr_report,
    graph_statistics,
    readability_from_gdpr,
)

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
    doc = policy_doc_from_db(policy)
    if not doc.has_graph() and not doc.has_graphml():
        raise HTTPException(status_code=404, detail="No graph artifacts found for this policy")
    return GraphElements(elements=build_cytoscape_elements(doc))


@router.get("/api/policies/{policy_id}/stats", response_model=GraphStats)
def get_stats(policy_id: uuid.UUID, db: Db):
    policy = _get_policy_or_404(policy_id, db)
    doc = policy_doc_from_db(policy)
    try:
        stats = graph_statistics(doc)
    except Exception:
        stats = None
    return GraphStats(stats=stats)


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


@router.get("/api/tasks/{task_id}", response_model=TaskStatus)
def get_task_status(task_id: str, request: Request):
    task = request.app.state.tasks.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return TaskStatus(
        task_id=task_id,
        **{k: task[k] for k in ("status", "error", "label", "total", "completed", "failed") if k in task},
    )
