"""Dispatch durable task payloads inside the analysis worker image."""

from __future__ import annotations

import logging
import uuid

from poligrapher_app.services.task_output import capture_task_output

logger = logging.getLogger(__name__)


def execute_task(task_id: str, registry) -> None:
    payload = registry.claim(task_id)
    if payload is None:
        return
    with capture_task_output(task_id, registry):
        try:
            kind = payload.get("kind")
            logger.info("Task %s started (kind=%s)", task_id, kind)
            if kind == "comparison":
                _comparison(task_id, payload, registry)
            elif kind == "upload":
                _upload(task_id, payload, registry)
            elif kind == "rerun-upload":
                _rerun_upload(task_id, payload, registry)
            elif kind == "rerun-comparison":
                _rerun_comparison(task_id, payload, registry)
            elif kind == "generate":
                _generate(task_id, payload, registry)
            elif kind == "score":
                _score(task_id, payload, registry)
            elif kind == "refresh":
                _refresh(task_id, payload, registry)
            elif kind == "score-all":
                _score_all(task_id, payload, registry)
            elif kind == "source-verification":
                _verify_sources(task_id, payload, registry)
            elif kind == "collection-analysis":
                _analyze_collection(task_id, payload, registry)
            elif kind == "schedule":
                _schedule(task_id, payload, registry)
            else:
                raise ValueError(f"Unknown task kind: {kind}")
            logger.info("Task %s finished with status %s", task_id, registry.get(task_id)["status"])
        except Exception as exc:  # noqa: BLE001
            logger.exception("Task %s failed", task_id)
            registry.set_failed(task_id, str(exc))


def _settle_result(task_id: str, result: str, registry) -> None:
    if result == "cancelled":
        registry.set_cancelled(task_id)
    elif result in ("needs_source", "gone"):
        registry.set_failed(task_id, f"Run did not complete: {result}")
    else:
        registry.update(task_id, completed=1)
        registry.set_done(task_id)


def _comparison(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.services.runs import run_comparison

    result = run_comparison(
        uuid.UUID(payload["provider_id"]),
        scheduled=bool(payload.get("scheduled")),
        registry=registry,
        task_id=task_id,
    )
    _settle_result(task_id, result, registry)


def _upload(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.services.runs import run_upload

    _settle_result(
        task_id,
        run_upload(uuid.UUID(payload["policy_id"]), registry=registry, task_id=task_id),
        registry,
    )


def _rerun_upload(task_id: str, payload: dict, registry) -> None:
    import os
    import tempfile
    from pathlib import Path

    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Policy
    from poligrapher_app.services.runs import file_hash, run_upload
    from poligrapher_app.services.storage import get_storage, source_key

    original_id = uuid.UUID(payload["original_policy_id"])
    policy_id = uuid.UUID(payload["policy_id"])
    with SessionLocal() as db:
        original = db.get(Policy, original_id)
        policy = db.get(Policy, policy_id)
        if not original or not policy or not original.source_blob_key:
            registry.set_failed(task_id, "The original PDF is not available")
            return
        temp_root = os.getenv("TEMP_WORKSPACE_ROOT") or None
        with tempfile.TemporaryDirectory(prefix="poligrapher-rerun-upload-", dir=temp_root) as workspace:
            source = Path(workspace) / (original.source_filename or "source.pdf")
            storage = get_storage()
            storage.download_file(original.source_blob_key, source)
            policy.source_blob_key = source_key(policy.id, policy.source_filename or source.name)
            storage.upload_file(policy.source_blob_key, source, content_type="application/pdf")
            policy.content_hash = file_hash(str(source))
            db.commit()
    _settle_result(
        task_id,
        run_upload(policy_id, registry=registry, task_id=task_id),
        registry,
    )


def _rerun_comparison(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.services.runs import run_archived_comparison

    result = run_archived_comparison(
        uuid.UUID(payload["original_policy_id"]),
        uuid.UUID(payload["website_policy_id"]),
        uuid.UUID(payload["pdf_policy_id"]),
        registry=registry,
        task_id=task_id,
    )
    _settle_result(task_id, result, registry)


def _generate(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.mapping import sync_policy_from_doc
    from poligrapher_app.api.models import Policy
    from poligrapher_app.services.persistence import persist_workspace, temporary_document
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_graph

    policy_id = uuid.UUID(payload["policy_id"])
    with SessionLocal() as db:
        try:
            policy = db.get(Policy, policy_id)
            if policy is None:
                registry.set_failed(task_id, "Policy no longer exists")
                return
            with temporary_document(policy) as (doc, workspace):
                generate_graph(doc, should_cancel=lambda: registry.is_cancelled(task_id))
                persist_workspace(policy, doc, workspace / "artifacts.zip")
                sync_policy_from_doc(policy, doc, db)
            registry.incr(task_id, "completed")
            registry.set_done(task_id)
        except PipelineCancelled:
            registry.set_cancelled(task_id)
        except Exception as exc:
            failed = db.get(Policy, policy_id)
            if failed:
                if not failed.graph_data:
                    failed.pipeline_status = "failed"
                failed.pipeline_errors = list(failed.pipeline_errors or []) + [{"message": str(exc)}]
                db.commit()
            raise


def _score(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.mapping import sync_policy_from_doc
    from poligrapher_app.api.models import Policy
    from poligrapher_app.services.persistence import temporary_document
    from poligrapher_app.services.scoring import score_gdpr, score_privacy

    with SessionLocal() as db:
        if registry.is_cancelled(task_id):
            registry.set_cancelled(task_id)
            return
        policy = db.get(Policy, uuid.UUID(payload["policy_id"]))
        if policy is None:
            registry.set_failed(task_id, "Policy no longer exists")
            return
        with temporary_document(policy, restore_artifacts=True) as (doc, _):
            score_privacy(doc)
            score_gdpr(doc)
        if registry.is_cancelled(task_id):
            registry.set_cancelled(task_id)
            return
        sync_policy_from_doc(policy, doc, db)
        registry.incr(task_id, "completed")
        registry.set_done(task_id)


def _refresh(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.mapping import sync_policy_from_doc
    from poligrapher_app.api.models import Policy
    from poligrapher_app.services.persistence import persist_workspace, temporary_document
    from poligrapher_app.services.pipeline import PipelineCancelled, generate_graph

    with SessionLocal() as db:
        for raw_id in payload.get("policy_ids", []):
            if registry.is_cancelled(task_id):
                registry.set_cancelled(task_id)
                return
            policy = db.get(Policy, uuid.UUID(raw_id))
            if policy is None:
                continue
            try:
                with temporary_document(policy) as (doc, workspace):
                    generate_graph(doc, should_cancel=lambda: registry.is_cancelled(task_id))
                    persist_workspace(policy, doc, workspace / "artifacts.zip")
                    sync_policy_from_doc(policy, doc, db)
            except PipelineCancelled:
                registry.set_cancelled(task_id)
                return
            except Exception:
                logger.exception("Refresh failed for policy %s", policy.id)
                if not policy.graph_data:
                    policy.pipeline_status = "failed"
                policy.pipeline_errors = list(policy.pipeline_errors or []) + [{"message": "Refresh failed"}]
                db.commit()
                registry.incr(task_id, "failed")
            registry.incr(task_id, "completed")
        registry.set_done(task_id)


def _score_all(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.mapping import sync_policy_from_doc
    from poligrapher_app.api.models import Policy
    from poligrapher_app.services.persistence import temporary_document
    from poligrapher_app.services.scoring import score_gdpr, score_privacy

    with SessionLocal() as db:
        for raw_id in payload.get("policy_ids", []):
            if registry.is_cancelled(task_id):
                registry.set_cancelled(task_id)
                return
            policy = db.get(Policy, uuid.UUID(raw_id))
            if policy is None:
                continue
            try:
                with temporary_document(policy, restore_artifacts=True) as (doc, _):
                    score_privacy(doc)
                    score_gdpr(doc)
                    sync_policy_from_doc(policy, doc, db)
            except Exception:
                logger.exception("Scoring failed for policy %s", policy.id)
                registry.incr(task_id, "failed")
            registry.incr(task_id, "completed")
        registry.set_done(task_id)


def _verify_sources(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Provider
    from poligrapher_app.services.source_verification import verify_provider_sources

    provider_ids = [uuid.UUID(value) for value in payload.get("provider_ids", [])]
    with SessionLocal() as db:
        providers = db.query(Provider).filter(Provider.id.in_(provider_ids)).all()
        verify_provider_sources(
            db,
            providers,
            on_result=lambda _check: registry.incr(task_id, "completed"),
            should_cancel=lambda: registry.is_cancelled(task_id),
        )
    registry.set_cancelled(task_id) if registry.is_cancelled(task_id) else registry.set_done(task_id)


def _analyze_collection(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.services.runs import run_comparison

    for raw_id in payload.get("provider_ids", []):
        if registry.is_cancelled(task_id):
            registry.set_cancelled(task_id)
            return
        try:
            result = run_comparison(
                uuid.UUID(raw_id), scheduled=False, registry=registry,
                task_id=task_id, link_task=False,
            )
            if result not in ("ok", "unchanged"):
                registry.incr(task_id, "failed")
        except Exception:
            logger.exception("Collection analysis failed for provider %s", raw_id)
            registry.incr(task_id, "failed")
        registry.incr(task_id, "completed")
    registry.set_done(task_id)


def _schedule(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.services.scheduler import run_schedule_job

    run_schedule_job(payload["schedule_id"], task_id=task_id, registry=registry)
