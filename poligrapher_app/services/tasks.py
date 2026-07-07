"""Background task registry.

A tiny in-memory task tracker backed by a thread pool. Routers create a task,
submit a callable, and later poll its status; the registry owns all the
bookkeeping (status, error, and bulk progress counters) so routers don't
hand-roll task dicts.
"""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Callable


class TaskRegistry:
    def __init__(self, max_workers: int = 4):
        self._executor = ThreadPoolExecutor(max_workers=max_workers)
        self._tasks: dict[str, dict] = {}
        self._lock = threading.Lock()

    def create(self, *, label: str | None = None, total: int = 0, **extra) -> str:
        """Register a new task (status='running') and return its id."""
        task_id = str(uuid.uuid4())
        with self._lock:
            self._tasks[task_id] = {
                "status": "running",
                "error": None,
                "label": label,
                "total": total,
                "completed": 0,
                "failed": 0,
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

        self._executor.submit(_wrapped)

    def get(self, task_id: str) -> dict | None:
        with self._lock:
            task = self._tasks.get(task_id)
            return dict(task) if task is not None else None

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

    def set_done(self, task_id: str) -> None:
        self.update(task_id, status="done")

    def set_failed(self, task_id: str, error: str) -> None:
        self.update(task_id, status="failed", error=error)
