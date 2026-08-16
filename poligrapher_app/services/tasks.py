"""Durable task registry and queue publisher.

PostgreSQL is the source of truth for status and cancellation. Production sends
small task-id messages to Azure Queue Storage; local development executes the
same dispatcher in a background thread without requiring Azure resources.
"""

from __future__ import annotations

import json
import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl, quote, quote_plus, unquote, urlsplit

from sqlalchemy import and_, or_

from poligrapher_app.api.database import SessionLocal
from poligrapher_app.api.models import Provider, TaskIssue, TaskRecord

_TERMINAL = ("done", "failed", "cancelled")
_RECENT = timedelta(minutes=15)
_FAILED_RECENT = timedelta(days=7)
_MAX_OUTPUT_CHARS = 250_000
_TRUNCATION_NOTICE = "[Earlier terminal output was truncated.]\n"
_REDACTION = "[REDACTED]"
_DEFAULT_CLAIM_RECOVERY_SECONDS = 20 * 60
_SENSITIVE_ENV_NAMES = (
    "DATABASE_URL",
    "AZURE_STORAGE_CONNECTION_STRING",
    "AZURE_QUEUE_CONNECTION_STRING",
    "EXPORT_TOKEN",
    "CRAWL_PROXY",
    "CRAWL_PROXY_USERNAME",
    "CRAWL_PROXY_PASSWORD",
    "SCRAPE_API_URL",
    "SCRAPE_API_KEY",
    "GITHUB_TOKEN",
)
_SENSITIVE_COMPONENT_NAMES = ("key", "password", "secret", "signature", "token")


def _sensitive_output_values() -> list[str]:
    values: set[str] = set()

    def add(value: str | None) -> None:
        if value and len(value) >= 6:
            values.add(value)
            decoded = unquote(value)
            if len(decoded) >= 6:
                values.add(decoded)
                values.add(quote(decoded, safe=""))
                values.add(quote_plus(decoded, safe=""))

    for name in _SENSITIVE_ENV_NAMES:
        value = (os.getenv(name) or "").strip()
        if not value:
            continue
        add(value)

        if "://" in value:
            parsed = urlsplit(value)
            add(parsed.password)
            for key, component in parse_qsl(parsed.query, keep_blank_values=True):
                if any(marker in key.lower() for marker in _SENSITIVE_COMPONENT_NAMES):
                    add(component)

        for part in value.split(";"):
            key, separator, component = part.partition("=")
            if separator and any(
                marker in key.lower() for marker in _SENSITIVE_COMPONENT_NAMES
            ):
                add(component)

    return sorted(values, key=len, reverse=True)


def _redact_output(value: str) -> str:
    for sensitive in _sensitive_output_values():
        value = value.replace(sensitive, _REDACTION)
    return value


def _now() -> datetime:
    return datetime.now(timezone.utc)


def task_public(task: TaskRecord, provider_names: dict[str, str] | None = None) -> dict:
    provider_names = provider_names or {}
    outcome = task.outcome
    if not outcome:
        if task.status == "cancelled":
            outcome = "cancelled"
        elif task.status == "failed":
            outcome = "failed"
        elif task.status == "done":
            outcome = "partially_succeeded" if (task.failed or 0) > 0 else "succeeded"
    return {
        "task_id": str(task.id),
        "status": task.status,
        "outcome": outcome,
        "error": task.error,
        "label": task.label,
        "title": task.title,
        "kind": task.kind,
        "total": task.total or 0,
        "completed": task.completed or 0,
        "failed": task.failed or 0,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "started_at": task.started_at.isoformat() if task.started_at else None,
        "cancelable": task.status == "running",
        "policy_id": task.policy_id,
        "provider_id": task.provider_id,
        "run_id": task.run_id,
        "provider_name": task.provider_name,
        "has_output": bool(task.output),
        "issues": [
            {
                "issue_id": str(issue.id),
                "code": issue.code,
                "stage": issue.stage,
                "severity": issue.severity,
                "retryability": issue.retryability,
                "summary": issue.summary,
                "technical_detail": issue.technical_detail,
                "provider_id": issue.provider_id,
                "provider_name": provider_names.get(issue.provider_id or ""),
                "policy_id": issue.policy_id,
                "actions": list(issue.actions or []),
                "occurred_at": issue.occurred_at.isoformat() if issue.occurred_at else None,
            }
            for issue in task.issues
        ],
    }


class TaskRegistry:
    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self.backend = os.getenv("TASK_BACKEND", "local").lower()

    def create(
        self,
        *,
        label: str | None = None,
        title: str | None = None,
        kind: str | None = None,
        total: int = 0,
        **extra,
    ) -> str:
        task = TaskRecord(
            label=label,
            title=title or label,
            kind=kind,
            total=total,
            policy_id=str(extra.get("policy_id")) if extra.get("policy_id") else None,
            provider_id=str(extra.get("provider_id")) if extra.get("provider_id") else None,
            run_id=str(extra.get("run_id")) if extra.get("run_id") else None,
            provider_name=extra.get("provider_name"),
        )
        with SessionLocal() as db:
            db.add(task)
            db.commit()
            db.refresh(task)
            return str(task.id)

    def enqueue(self, task_id: str, payload: dict) -> None:
        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            if task is None:
                raise KeyError(task_id)
            task.payload = payload
            db.commit()
        try:
            if self.backend == "azure_queue":
                self._queue_client().send_message(json.dumps({"task_id": task_id}))
            elif self.backend == "local":
                self._executor.submit(self._execute_local, task_id)
            else:
                raise RuntimeError(f"Unsupported TASK_BACKEND: {self.backend}")
        except Exception as exc:
            message = f"Could not enqueue task: {exc}"
            self.append_output(task_id, f"ERROR: {message}\n")
            self.set_failed(task_id, message)
            raise

    def _execute_local(self, task_id: str) -> None:
        from poligrapher_app.services.task_execution import execute_task

        execute_task(task_id, self)

    @staticmethod
    def _queue_client():
        from azure.storage.queue import QueueClient

        connection = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
        if not connection:
            raise RuntimeError("AZURE_STORAGE_CONNECTION_STRING is required for queued tasks")
        name = os.getenv("AZURE_STORAGE_QUEUE_NAME", "analysis-tasks")
        return QueueClient.from_connection_string(connection, name)

    def get(self, task_id: str) -> dict | None:
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return None
        with SessionLocal() as db:
            task = db.get(TaskRecord, task_uuid)
            if task is None:
                return None
            provider_ids = {
                issue.provider_id for issue in task.issues if issue.provider_id
            }
            provider_names = {
                str(provider.id): provider.name
                for provider in db.query(Provider).filter(
                    Provider.id.in_([uuid.UUID(provider_id) for provider_id in provider_ids])
                ).all()
            }
            return task_public(task, provider_names)

    def list(self) -> list[dict]:
        cutoff = _now() - _RECENT
        failed_cutoff = _now() - _FAILED_RECENT
        with SessionLocal() as db:
            tasks = (
                db.query(TaskRecord)
                .filter(or_(
                    TaskRecord.settled_at.is_(None),
                    TaskRecord.settled_at >= cutoff,
                    and_(
                        TaskRecord.settled_at >= failed_cutoff,
                        or_(
                            TaskRecord.status == "failed",
                            TaskRecord.failed > 0,
                            TaskRecord.outcome == "partially_succeeded",
                        ),
                    ),
                ))
                .order_by(TaskRecord.created_at.desc())
                .all()
            )
            provider_ids = {
                issue.provider_id
                for task in tasks
                for issue in task.issues
                if issue.provider_id
            }
            provider_names = {
                str(provider.id): provider.name
                for provider in db.query(Provider).filter(
                    Provider.id.in_([uuid.UUID(provider_id) for provider_id in provider_ids])
                ).all()
            }
            return [task_public(task, provider_names) for task in tasks]

    def append_output(self, task_id: str, chunk: str) -> None:
        if not chunk:
            return
        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            if task is None:
                return
            output = _redact_output((task.output or "") + chunk.replace("\x00", ""))
            if len(output) > _MAX_OUTPUT_CHARS:
                keep = _MAX_OUTPUT_CHARS - len(_TRUNCATION_NOTICE)
                output = _TRUNCATION_NOTICE + output[-keep:]
            task.output = output
            db.commit()

    def record_issue(
        self,
        task_id: str,
        issue: dict,
        *,
        provider_id: str | uuid.UUID | None = None,
        policy_id: str | uuid.UUID | None = None,
    ) -> str | None:
        """Persist one structured issue independently of the bounded console output."""

        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            if task is None:
                return None
            existing = (
                db.query(TaskIssue)
                .filter(
                    TaskIssue.task_id == task.id,
                    TaskIssue.code == issue["code"],
                    TaskIssue.provider_id == (str(provider_id) if provider_id else None),
                    TaskIssue.policy_id == (str(policy_id) if policy_id else None),
                )
                .first()
            )
            if existing is not None:
                return str(existing.id)
            record = TaskIssue(
                task_id=task.id,
                code=issue["code"],
                stage=issue["stage"],
                severity=issue.get("severity", "error"),
                retryability=issue.get("retryability", "manual"),
                summary=issue["summary"],
                technical_detail=_redact_output(issue.get("technical_detail") or ""),
                provider_id=str(provider_id) if provider_id else None,
                policy_id=str(policy_id) if policy_id else None,
                actions=list(issue.get("actions") or []),
            )
            db.add(record)
            db.commit()
            db.refresh(record)
            return str(record.id)

    def retryable_provider_ids(self, task_id: str) -> list[str]:
        with SessionLocal() as db:
            rows = (
                db.query(
                    TaskIssue.provider_id,
                    TaskIssue.retryability,
                    TaskIssue.severity,
                )
                .filter(
                    TaskIssue.task_id == uuid.UUID(task_id),
                    TaskIssue.provider_id.isnot(None),
                )
                .all()
            )
            retryability_by_provider: dict[str, set[str]] = {}
            for provider_id, retryability, severity in rows:
                if provider_id and severity == "error":
                    retryability_by_provider.setdefault(provider_id, set()).add(retryability)
            return sorted(
                provider_id
                for provider_id, retryabilities in retryability_by_provider.items()
                if "transient" in retryabilities
                and not retryabilities.intersection({"manual", "blocked"})
            )

    def retry_failed_subtasks(self, task_id: str) -> str | None:
        provider_ids = self.retryable_provider_ids(task_id)
        if not provider_ids:
            return None
        with SessionLocal() as db:
            original = db.get(TaskRecord, uuid.UUID(task_id))
            if original is None:
                return None
            if original.kind == "collection-analysis":
                kind = "collection-analysis"
                title = f"Retry failed companies from {original.title or 'company analysis'}"
                payload = {"kind": kind, "provider_ids": provider_ids}
            elif original.kind == "cohort-recovery":
                kind = "cohort-recovery"
                title = f"Retry transient failures from {original.title or 'cohort recovery'}"
                payload = {"kind": kind, "provider_ids": provider_ids, "deep": True}
            else:
                return None
        retry_id = self.create(
            kind=kind,
            title=title,
            total=len(provider_ids),
        )
        self.enqueue(retry_id, payload)
        return retry_id

    def get_output(self, task_id: str) -> dict | None:
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return None
        with SessionLocal() as db:
            task = db.get(TaskRecord, task_uuid)
            if task is None:
                return None
            output = task.output or ""
            return {
                "task_id": str(task.id),
                "status": task.status,
                "output": output,
                "truncated": output.startswith(_TRUNCATION_NOTICE),
            }

    def update(self, task_id: str, **fields) -> None:
        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            if task:
                for key, value in fields.items():
                    if hasattr(task, key):
                        setattr(task, key, value)
                db.commit()

    def incr(self, task_id: str, field: str, by: int = 1) -> None:
        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            if task and field in ("completed", "failed"):
                setattr(task, field, (getattr(task, field) or 0) + by)
                db.commit()

    def claim(self, task_id: str) -> dict | None:
        """Atomically claim an unstarted task; duplicate queue deliveries no-op."""
        with SessionLocal() as db:
            task = (
                db.query(TaskRecord)
                .filter(TaskRecord.id == uuid.UUID(task_id))
                .with_for_update()
                .first()
            )
            if not task or task.status in _TERMINAL:
                return None
            if task.started_at is not None:
                started_at = task.started_at
                if started_at.tzinfo is None:
                    started_at = started_at.replace(tzinfo=timezone.utc)
                # Production renews the queue lease while work is healthy. A
                # message that remains visible past this shorter grace period
                # is a crash recovery, not a concurrent duplicate delivery.
                recovery_seconds = int(os.getenv(
                    "TASK_CLAIM_RECOVERY_SECONDS",
                    str(_DEFAULT_CLAIM_RECOVERY_SECONDS),
                ))
                if _now() - started_at < timedelta(seconds=recovery_seconds):
                    return None
            if task.cancel_requested:
                task.status = "cancelled"
                task.outcome = "cancelled"
                task.settled_at = _now()
                db.commit()
                return None
            task.started_at = _now()
            task.status = "running"
            db.commit()
            return dict(task.payload or {})

    def is_cancelled(self, task_id: str) -> bool:
        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            return bool(task and (task.cancel_requested or task.status == "cancelled"))

    def cancel(self, task_id: str) -> bool:
        try:
            task_uuid = uuid.UUID(task_id)
        except ValueError:
            return False
        with SessionLocal() as db:
            task = db.get(TaskRecord, task_uuid)
            if task is None:
                return False
            if task.status in _TERMINAL:
                return True
            task.cancel_requested = True
            if task.started_at is None:
                task.status = "cancelled"
                task.outcome = "cancelled"
                task.settled_at = _now()
            else:
                task.status = "cancelling"
            db.commit()
            return True

    def set_done(self, task_id: str, *, has_issues: bool = False) -> None:
        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            failed = int(task.failed or 0) if task else 0
        self._settle(
            task_id,
            "done",
            outcome="partially_succeeded" if failed or has_issues else "succeeded",
        )

    def set_failed(self, task_id: str, error: str) -> None:
        self._settle(task_id, "failed", error=error, outcome="failed")

    def set_cancelled(self, task_id: str) -> None:
        self._settle(task_id, "cancelled", outcome="cancelled")

    def _settle(self, task_id: str, status: str, **fields) -> None:
        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            if task:
                task.status = status
                task.settled_at = _now()
                for key, value in fields.items():
                    setattr(task, key, value)
                db.commit()
