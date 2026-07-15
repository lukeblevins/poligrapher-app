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

from sqlalchemy import and_, or_

from poligrapher_app.api.database import SessionLocal
from poligrapher_app.api.models import TaskRecord

_TERMINAL = ("done", "failed", "cancelled")
_RECENT = timedelta(minutes=15)
_FAILED_RECENT = timedelta(days=7)
_MAX_OUTPUT_CHARS = 250_000
_TRUNCATION_NOTICE = "[Earlier terminal output was truncated.]\n"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def task_public(task: TaskRecord) -> dict:
    return {
        "task_id": str(task.id),
        "status": task.status,
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
            return task_public(task) if task else None

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
                        or_(TaskRecord.status == "failed", TaskRecord.failed > 0),
                    ),
                ))
                .order_by(TaskRecord.created_at.desc())
                .all()
            )
            return [task_public(task) for task in tasks]

    def append_output(self, task_id: str, chunk: str) -> None:
        if not chunk:
            return
        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            if task is None:
                return
            output = (task.output or "") + chunk.replace("\x00", "")
            if len(output) > _MAX_OUTPUT_CHARS:
                keep = _MAX_OUTPUT_CHARS - len(_TRUNCATION_NOTICE)
                output = _TRUNCATION_NOTICE + output[-keep:]
            task.output = output
            db.commit()

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
                # A visible queue message after the worker's two-hour lease is
                # a crash recovery, not a concurrent duplicate delivery.
                if _now() - started_at < timedelta(hours=2):
                    return None
            if task.cancel_requested:
                task.status = "cancelled"
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
                task.settled_at = _now()
            else:
                task.status = "cancelling"
            db.commit()
            return True

    def set_done(self, task_id: str) -> None:
        self._settle(task_id, "done")

    def set_failed(self, task_id: str, error: str) -> None:
        self._settle(task_id, "failed", error=error)

    def set_cancelled(self, task_id: str) -> None:
        self._settle(task_id, "cancelled")

    def _settle(self, task_id: str, status: str, **fields) -> None:
        with SessionLocal() as db:
            task = db.get(TaskRecord, uuid.UUID(task_id))
            if task:
                task.status = status
                task.settled_at = _now()
                for key, value in fields.items():
                    setattr(task, key, value)
                db.commit()
