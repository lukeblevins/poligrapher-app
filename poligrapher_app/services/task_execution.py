"""Dispatch durable task payloads inside the analysis worker image."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
import urllib.parse
import uuid

from poligrapher_app.services.task_output import capture_task_output
from poligrapher_app.services.failures import classify_failure

logger = logging.getLogger(__name__)

_DEFAULT_COLLECTION_SUBTASK_TIMEOUT_SECONDS = 15 * 60
_SUBTASK_CANCEL_POLL_SECONDS = 1.0
_SUBTASK_TERMINATE_GRACE_SECONDS = 10.0


class CollectionSubtaskTimeoutError(TimeoutError):
    """Raised when one provider exceeds the collection-analysis time budget."""


def _is_pdf_source(url: str | None) -> bool:
    return bool(url and urllib.parse.urlparse(url).path.casefold().endswith(".pdf"))


def _collection_subtask_timeout_seconds() -> float:
    raw = os.getenv(
        "COLLECTION_SUBTASK_TIMEOUT_SECONDS",
        str(_DEFAULT_COLLECTION_SUBTASK_TIMEOUT_SECONDS),
    )
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("COLLECTION_SUBTASK_TIMEOUT_SECONDS must be a number") from exc
    if value <= 0:
        raise ValueError("COLLECTION_SUBTASK_TIMEOUT_SECONDS must be greater than zero")
    return value


def _stop_subtask(process: subprocess.Popen[str]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=_SUBTASK_TERMINATE_GRACE_SECONDS)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _capture_subtask_output(process: subprocess.Popen[str], task_id: str, registry) -> None:
    if process.stdout is None:
        return
    for chunk in iter(process.stdout.readline, ""):
        registry.append_output(task_id, chunk)


def _run_collection_subtask(
    task_id: str,
    provider_id: uuid.UUID,
    registry,
    *,
    timeout_seconds: float | None = None,
) -> str:
    """Run one provider in an isolated process so a hung NLP stage is killable."""

    timeout_seconds = timeout_seconds or _collection_subtask_timeout_seconds()
    command = [
        sys.executable,
        "-m",
        "poligrapher_app.collection_subtask",
        str(provider_id),
        task_id,
    ]
    process = subprocess.Popen(  # noqa: S603
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    output_thread = threading.Thread(
        target=_capture_subtask_output,
        args=(process, task_id, registry),
        daemon=True,
    )
    output_thread.start()
    deadline = time.monotonic() + timeout_seconds
    try:
        while process.poll() is None:
            if registry.is_cancelled(task_id):
                _stop_subtask(process)
                return "cancelled"
            if time.monotonic() >= deadline:
                _stop_subtask(process)
                raise CollectionSubtaskTimeoutError(
                    f"Provider analysis exceeded {timeout_seconds:g} seconds"
                )
            time.sleep(_SUBTASK_CANCEL_POLL_SECONDS)
    finally:
        output_thread.join(timeout=_SUBTASK_TERMINATE_GRACE_SECONDS)

    if process.returncode == 0:
        return "ok"
    if process.returncode == 3:
        return "cancelled"
    if process.returncode == 2:
        return "needs_source"
    raise RuntimeError(f"Provider analysis subprocess exited with code {process.returncode}")


def execute_task(task_id: str, registry) -> bool:
    payload = registry.claim(task_id)
    if payload is None:
        return False
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
            elif kind == "bulk-generate":
                _refresh(task_id, payload, registry)
            elif kind == "bulk-score":
                _score_all(task_id, payload, registry)
            elif kind == "retention-cleanup":
                _retention_cleanup(task_id, payload, registry)
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
            registry.record_issue(
                task_id,
                classify_failure(exc),
                provider_id=payload.get("provider_id"),
                policy_id=payload.get("policy_id"),
            )
            registry.set_failed(task_id, str(exc))
    return True


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
            try:
                storage = get_storage()
                storage.download_file(original.source_blob_key, source)
                policy.source_blob_key = source_key(policy.id, policy.source_filename or source.name)
                storage.upload_file(policy.source_blob_key, source, content_type="application/pdf")
                policy.content_hash = file_hash(str(source))
                db.commit()
            except Exception as exc:
                policy.pipeline_status = "failed"
                policy.pipeline_errors = list(policy.pipeline_errors or []) + [
                    f"Saved PDF could not be restored: {exc}"
                ]
                db.commit()
                raise
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
                registry.incr(task_id, "completed")
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
                registry.incr(task_id, "completed")
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


def analyze_collection_provider(provider_id: uuid.UUID, task_id: str, registry) -> str:
    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Provider
    from poligrapher_app.services.acquisition import PolicySourceResolver, wayback_snapshot_url
    from poligrapher_app.services.runs import run_comparison, run_remote_pdf

    with SessionLocal() as db:
        provider = db.get(Provider, provider_id)
        source_url = provider.source_url if provider else None
        if (
            provider
            and source_url
            and provider.source_status not in ("available", "unchecked")
            and not _is_pdf_source(source_url)
            and not wayback_snapshot_url(source_url, timeout=8.0, raw=False)
        ):
            fallback = PolicySourceResolver(allow_headless=False).resolve_candidate(
                provider.name,
                provider.domain,
                exclude_urls={source_url},
                require_validation=True,
            )
            if fallback:
                source_url = fallback.url
                provider.source_url = fallback.url
                provider.source_status = "unchecked"
                db.commit()
    is_pdf = _is_pdf_source(source_url)
    runner = run_remote_pdf if is_pdf else run_comparison
    if is_pdf:
        return runner(provider_id, scheduled=False, registry=registry, task_id=task_id)
    return runner(
        provider_id,
        scheduled=False,
        registry=registry,
        task_id=task_id,
        link_task=False,
    )


def _mark_collection_provider_failed(provider_id: uuid.UUID, message: str) -> None:
    """Set any policies abandoned by a killed subtask to a terminal state."""

    from poligrapher_app.api.database import SessionLocal
    from poligrapher_app.api.models import Policy

    with SessionLocal() as db:
        pending = (
            db.query(Policy)
            .filter(
                Policy.provider_id == provider_id,
                Policy.pipeline_status == "pending",
            )
            .all()
        )
        for policy in pending:
            policy.pipeline_status = "failed"
            policy.pipeline_errors = list(policy.pipeline_errors or []) + [
                {"message": message}
            ]
        if pending:
            db.commit()


def _analyze_collection(task_id: str, payload: dict, registry) -> None:
    provider_ids = payload.get("provider_ids", [])
    task = registry.get(task_id) or {}
    # completed is a durable cursor because every attempted provider increments
    # it exactly once. A queue lease/job restart therefore resumes at the next
    # provider instead of repeating the batch from the beginning.
    start_index = min(int(task.get("completed") or 0), len(provider_ids))
    if start_index:
        logger.info(
            "Resuming collection analysis at provider %d of %d",
            start_index + 1,
            len(provider_ids),
        )

    for raw_id in provider_ids[start_index:]:
        if registry.is_cancelled(task_id):
            registry.set_cancelled(task_id)
            return
        provider_id = None
        try:
            provider_id = uuid.UUID(raw_id)
            registry.append_output(
                task_id,
                f"SUBTASK STARTED: provider {provider_id}\n",
            )
            result = _run_collection_subtask(task_id, provider_id, registry)
            if result == "cancelled":
                registry.set_cancelled(task_id)
                return
            if result not in ("ok", "unchanged"):
                registry.incr(task_id, "failed")
                logger.warning(
                    "Collection analysis did not complete for provider %s: %s",
                    raw_id,
                    result,
                )
        except Exception as exc:
            logger.exception("Collection analysis failed for provider %s", raw_id)
            if isinstance(exc, CollectionSubtaskTimeoutError):
                registry.record_issue(
                    task_id,
                    classify_failure(exc),
                    provider_id=provider_id,
                )
            if provider_id is not None:
                _mark_collection_provider_failed(provider_id, str(exc))
            registry.append_output(
                task_id,
                f"SUBTASK FAILED: provider {raw_id}: {exc}\n",
            )
            registry.incr(task_id, "failed")
        registry.incr(task_id, "completed")
    settled = registry.get(task_id) or {}
    failed = int(settled.get("failed") or 0)
    if failed:
        registry.update(
            task_id,
            error=f"Completed with {failed} subtask failure{'s' if failed != 1 else ''}.",
        )
    registry.set_done(task_id)


def _schedule(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.services.scheduler import run_schedule_job

    run_schedule_job(payload["schedule_id"], task_id=task_id, registry=registry)


def _retention_cleanup(task_id: str, payload: dict, registry) -> None:
    from poligrapher_app.services.retention import cleanup_retention

    result = cleanup_retention(
        int(payload["older_than_days"]), registry=registry, task_id=task_id,
    )
    if result["cancelled"]:
        registry.set_cancelled(task_id)
    else:
        registry.append_output(
            task_id,
            f"Retention cleanup removed {result['removed']} policies; {result['failed']} could not be removed.\n",
        )
        registry.set_done(task_id)
