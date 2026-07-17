"""Capture worker terminal output into the durable task registry."""

from __future__ import annotations

import logging
import sys
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Callable, Iterator, TextIO

_current_sink: ContextVar[Callable[[str], None] | None] = ContextVar(
    "task_output_sink",
    default=None,
)
_install_lock = threading.Lock()
_log_handler: logging.Handler | None = None


class _ContextStream:
    def __init__(self, stream: TextIO):
        self.stream = stream

    def write(self, value: str) -> int:
        written = self.stream.write(value)
        sink = _current_sink.get()
        if sink is not None and value:
            sink(value)
        return written if isinstance(written, int) else len(value)

    def flush(self) -> None:
        self.stream.flush()

    def __getattr__(self, name: str):
        return getattr(self.stream, name)


class _TaskLogHandler(logging.Handler):
    def __init__(self, terminal: TextIO):
        super().__init__(logging.INFO)
        self.terminal = terminal
        self.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)s %(name)s: %(message)s",
            datefmt="%H:%M:%S",
        ))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record) + "\n"
            sink = _current_sink.get()
            if sink is not None:
                sink(message)
            self.terminal.write(message)
            self.terminal.flush()
        except Exception:
            self.handleError(record)


class _TaskLogSink:
    def __init__(self, task_id: str, registry):
        self.task_id = task_id
        self.registry = registry
        self.chunks: list[str] = []
        self.size = 0
        self.lock = threading.Lock()
        self.writing = False

    def __call__(self, value: str) -> None:
        if self.writing:
            return
        with self.lock:
            self.chunks.append(value)
            self.size += len(value)
            if "\n" in value or self.size >= 4096:
                self._flush_locked()

    def flush(self) -> None:
        with self.lock:
            self._flush_locked()

    def _flush_locked(self) -> None:
        if not self.chunks:
            return
        value = "".join(self.chunks)
        self.chunks.clear()
        self.size = 0
        self.writing = True
        try:
            self.registry.append_output(self.task_id, value)
        finally:
            self.writing = False


def _install_capture() -> None:
    global _log_handler
    with _install_lock:
        if not isinstance(sys.stdout, _ContextStream):
            sys.stdout = _ContextStream(sys.stdout)
        if not isinstance(sys.stderr, _ContextStream):
            sys.stderr = _ContextStream(sys.stderr)
        terminal = sys.stderr.stream if isinstance(sys.stderr, _ContextStream) else sys.stderr
        if _log_handler is None:
            _log_handler = _TaskLogHandler(terminal)
            for name in ("poligrapher_app", "poligrapher"):
                project_logger = logging.getLogger(name)
                project_logger.addHandler(_log_handler)
                project_logger.setLevel(logging.INFO)
                project_logger.propagate = False
        else:
            _log_handler.terminal = terminal


@contextmanager
def capture_task_output(task_id: str, registry) -> Iterator[None]:
    _install_capture()
    sink = _TaskLogSink(task_id, registry)
    token = _current_sink.set(sink)
    try:
        yield
    finally:
        sink.flush()
        _current_sink.reset(token)
