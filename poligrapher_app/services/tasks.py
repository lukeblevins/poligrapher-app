"""Background task registry.

A tiny in-memory task tracker backed by a thread pool. Routers create a task,
submit a callable, and later poll its status; the registry owns all the
bookkeeping (status, error, bulk progress counters, and cancellation) so
routers don't hand-roll task dicts.

Cancellation is cooperative: each task carries a ``threading.Event`` that a
worker checks between coarse-grained steps. A task that hasn't started yet is
cancelled outright via its ``Future``.
"""

import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Callable

# Public field names surfaced to API clients (kept in one place so routers and
# schemas agree on the shape of a serialized task).
PUBLIC_FIELDS = (
    "status",
    "error",
    "label",
    "title",
    "kind",
    "total",
    "completed",
    "failed",
    "created_at",
    "cancelable",
    "policy_id",
    "provider_name",
)

# Settled tasks older than this (seconds) are pruned so ``list`` stays
# "active + recent" rather than growing without bound.
_PRUNE_AFTER_SECONDS = 15 * 60

_TERMINAL = ("done", "failed", "cancelled")


class TaskRegistry:
    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(
        self,
        *,
        label: str | None = None,
        title: str | None = None,
        kind: str | None = None,
        total: int = 0,
        **extra,
    ) -> str:
        """Register a new task (status='running') and return its id."""
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = {
                "status": "running",
                "error": None,
                "label": label,
                "title": title or label,
                "kind": kind,
                "total": total,
                "completed": 0,
                "failed": 0,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "cancel_event": threading.Event(),
                "future": None,
                "settled_at": None,
                **extra,
            }
        return task_id

    def submit(self, task_id: str, fn: Callable[[], None]) -> None:
        """Run ``fn`` on the thread pool. Uncaught errors mark the task failed."""

        def _wrapped():
            try:
                fn()
            except Exception as exc:  # noqa: BLE001 — surface any failure to the client
                self.set_failed(task_id, str(exc))

        future = self._executor.submit(_wrapped)
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task["future"] = future

    def get(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return self._public(task) if task is not None else None

    def list(self) -> list[dict]:
        """Return all (non-pruned) tasks, newest first."""
        self._prune()
        with self._lock:
            tasks = [self._public(t) | {"task_id": tid} for tid, t in self._tasks.items()]
        tasks.sort(key=lambda t: t.get("created_at") or "", reverse=True)
        return tasks

    def update(self, task_id: str, **fields) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.update(fields)

    def incr(self, task_id: str, field: str, by: int = 1) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task[field] = task.get(field, 0) + by

    def cancel_event(self, task_id: str) -> threading.Event | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return task["cancel_event"] if task is not None else None

    def is_cancelled(self, task_id: str) -> bool:
        event = self.cancel_event(task_id)
        return bool(event and event.is_set())

    def cancel(self, task_id: str) -> bool:
        """Request cancellation. Returns False if the task is unknown.

        If the worker hasn't started yet the ``Future`` is cancelled and the
        task settles immediately; otherwise the cancel event is set and the
        task moves to 'cancelling' until the worker finalizes it.
        """
        with self._lock:
            task = self._tasks.get(task_id)
            if task is None:
                return False
            if task["status"] in _TERMINAL:
                return True
            future = task.get("future")
            if future is not None and future.cancel():
                task["status"] = "cancelled"
                task["settled_at"] = time.monotonic()
            else:
                task["cancel_event"].set()
                if task["status"] == "running":
                    task["status"] = "cancelling"
        return True

    def set_done(self, task_id: str) -> None:
        self._settle(task_id, "done")

    def set_failed(self, task_id: str, error: str) -> None:
        self._settle(task_id, "failed", error=error)

    def set_cancelled(self, task_id: str) -> None:
        self._settle(task_id, "cancelled")

    # ── internal ──────────────────────────────────────────────────────────────

    def _settle(self, task_id: str, status: str, **fields) -> None:
        with self._lock:
            task = self._tasks.get(task_id)
            if task is not None:
                task.update(status=status, settled_at=time.monotonic(), **fields)

    @staticmethod
    def _public(task: dict) -> dict:
        """Project a task down to client-visible fields (drops Event/Future)."""
        out = {k: task[k] for k in PUBLIC_FIELDS if k in task}
        out["cancelable"] = task["status"] == "running"
        return out

    def _prune(self) -> None:
        now = time.monotonic()
        with self._lock:
            stale = [
                tid
                for tid, t in self._tasks.items()
                if t["status"] in _TERMINAL
                and t.get("settled_at") is not None
                and now - t["settled_at"] > _PRUNE_AFTER_SECONDS
            ]
            for tid in stale:
                del self._tasks[tid]
