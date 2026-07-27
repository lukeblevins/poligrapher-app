"""Workspace-level retention cleanup for durable analysis records and blobs."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from poligrapher_app.api.models import AnalysisResult, Policy
from poligrapher_app.services.storage import get_storage


def retention_cutoff(older_than_days: int) -> datetime:
    if older_than_days <= 0:
        raise ValueError("Retention interval must be greater than zero days")
    return datetime.now(timezone.utc) - timedelta(days=older_than_days)


def policies_older_than(db: Session, cutoff: datetime) -> list[Policy]:
    return db.query(Policy).filter(Policy.created_at < cutoff).order_by(Policy.created_at).all()


def preview_retention(db: Session, older_than_days: int) -> dict:
    cutoff = retention_cutoff(older_than_days)
    policies = policies_older_than(db, cutoff)
    policy_ids = [policy.id for policy in policies]
    analysis_result_count = (
        db.query(func.count(AnalysisResult.id))
        .filter(AnalysisResult.policy_id.in_(policy_ids))
        .scalar()
        if policy_ids
        else 0
    )
    artifact_count = sum(
        bool(policy.source_blob_key) + bool(policy.artifact_blob_key)
        for policy in policies
    )
    return {
        "older_than_days": older_than_days,
        "cutoff": cutoff,
        "policy_count": len(policies),
        "analysis_result_count": analysis_result_count or 0,
        "artifact_count": artifact_count,
        "provider_count": len({policy.provider_id for policy in policies}),
    }


def cleanup_retention(older_than_days: int, *, registry=None, task_id: str | None = None) -> dict:
    """Delete eligible policy history only after its retained blobs are gone.

    A failed blob deletion leaves its database record intact so retention never
    claims a record was removed while keeping a reachable private artifact.
    """

    from poligrapher_app.api.database import SessionLocal

    cutoff = retention_cutoff(older_than_days)
    removed = 0
    failed = 0
    storage = get_storage()
    with SessionLocal() as db:
        policies = policies_older_than(db, cutoff)
        for policy in policies:
            if registry and task_id and registry.is_cancelled(task_id):
                db.commit()
                return {"removed": removed, "failed": failed, "cancelled": True}
            try:
                for key in {policy.source_blob_key, policy.artifact_blob_key} - {None}:
                    if storage.exists(key):
                        storage.delete(key)
                db.delete(policy)
                db.commit()
                removed += 1
                if registry and task_id:
                    registry.incr(task_id, "completed")
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                failed += 1
                if registry and task_id:
                    registry.append_output(task_id, f"Could not remove policy {policy.id}: {exc}\n")
                    registry.incr(task_id, "failed")
    return {"removed": removed, "failed": failed, "cancelled": False}
