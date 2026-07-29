import json
import io
import logging
import sys
import tomllib
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import TaskRecord
from poligrapher_app.api.routers.analysis import get_task_output
from poligrapher_app.services import task_execution
from poligrapher_app.services import tasks as task_module
from poligrapher_app.services.task_execution import execute_task
from poligrapher_app.services.task_output import _TaskLogSink, capture_task_output


class FakeQueue:
    def __init__(self):
        self.messages = []

    def send_message(self, message):
        self.messages.append(json.loads(message))


def test_durable_task_lifecycle_and_queue_publish(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'tasks.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(task_module, "SessionLocal", session)

    queue = FakeQueue()
    registry = task_module.TaskRegistry()
    registry.backend = "azure_queue"
    monkeypatch.setattr(registry, "_queue_client", lambda: queue)

    task_id = registry.create(
        kind="comparison", title="Compare", provider_id="provider",
        run_id="run", total=1,
    )
    registry.enqueue(task_id, {"kind": "comparison", "provider_id": "provider"})
    assert queue.messages == [{"task_id": task_id}]
    assert registry.get(task_id)["status"] == "running"
    assert registry.get(task_id)["provider_id"] == "provider"
    assert registry.get(task_id)["run_id"] == "run"
    assert registry.claim(task_id) == {"kind": "comparison", "provider_id": "provider"}
    assert registry.get(task_id)["started_at"] is not None
    assert registry.claim(task_id) is None

    assert registry.cancel(task_id)
    assert registry.get(task_id)["status"] == "cancelling"
    assert registry.is_cancelled(task_id)
    registry.set_cancelled(task_id)
    assert registry.get(task_id)["status"] == "cancelled"


def test_task_output_is_persisted(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'output.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(task_module, "SessionLocal", session)

    registry = task_module.TaskRegistry()
    task_id = registry.create(kind="comparison", title="Compare", total=1)
    registry.append_output(task_id, "first line\n")
    registry.append_output(task_id, "second line\n")

    assert registry.get(task_id)["has_output"] is True
    assert registry.get_output(task_id) == {
        "task_id": task_id,
        "status": "running",
        "output": "first line\nsecond line\n",
        "truncated": False,
    }


def test_task_output_batches_short_lines():
    class RecordingRegistry:
        chunks = []

        def append_output(self, task_id, value):
            self.chunks.append((task_id, value))

    registry = RecordingRegistry()
    sink = _TaskLogSink("task", registry)
    for _ in range(100):
        sink("short line\n")

    assert registry.chunks == []
    sink.flush()
    assert registry.chunks == [("task", "short line\n" * 100)]


def test_task_output_endpoint_is_public():
    class Registry:
        @staticmethod
        def get_output(task_id):
            return {
                "task_id": task_id,
                "status": "done",
                "output": "safe output",
                "truncated": False,
            }

    request = SimpleNamespace(
        app=SimpleNamespace(state=SimpleNamespace(tasks=Registry())),
    )

    assert get_task_output("task-id", request).output == "safe output"


def test_task_output_redacts_environment_secrets(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'redaction.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(task_module, "SessionLocal", session)
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql+psycopg://admin:database%40password@example.test/database",
    )
    monkeypatch.setenv(
        "AZURE_STORAGE_CONNECTION_STRING",
        "DefaultEndpointsProtocol=https;AccountName=example;AccountKey=storage-secret-key",
    )
    monkeypatch.setenv("CRAWL_PROXY_PASSWORD", "proxy-secret-password")
    monkeypatch.setenv("SCRAPE_API_KEY", "scrape-secret-key")
    monkeypatch.setenv("EXPORT_TOKEN", "export-secret-token")

    registry = task_module.TaskRegistry()
    task_id = registry.create(kind="comparison", title="Redaction", total=1)
    registry.append_output(
        task_id,
        " ".join([
            "postgresql+psycopg://admin:database%40password@example.test/database",
            "database@password",
            "storage-secret-key",
            "proxy-secret-password",
            "scrape-secret-key",
            "export-secret-token",
        ]),
    )

    output = registry.get_output(task_id)["output"]
    for secret in (
        "database%40password",
        "database@password",
        "storage-secret-key",
        "proxy-secret-password",
        "scrape-secret-key",
        "export-secret-token",
    ):
        assert secret not in output
    assert output.count("[REDACTED]") >= 5


def test_task_output_captures_streams_and_logging(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'streams.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(task_module, "SessionLocal", session)

    registry = task_module.TaskRegistry()
    task_id = registry.create(kind="comparison", title="Stream capture")
    with capture_task_output(task_id, registry):
        print("standard output")
        print("standard error", file=sys.stderr)
        logging.getLogger("poligrapher.capture-test").warning("logging output")

    output = registry.get_output(task_id)["output"]
    assert "standard output" in output
    assert "standard error" in output
    assert "logging output" in output


def test_failed_task_captures_traceback(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'failure.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(task_module, "SessionLocal", session)

    registry = task_module.TaskRegistry()
    task_id = registry.create(kind="unknown", title="Broken task")
    registry.update(task_id, payload={"kind": "unknown"})

    execute_task(task_id, registry)

    task = registry.get(task_id)
    output = registry.get_output(task_id)["output"]
    assert task["status"] == "failed"
    assert task["error"] == "Unknown task kind: unknown"
    assert "Traceback" in output
    assert "Unknown task kind: unknown" in output


def test_collection_analysis_resumes_and_settles_with_subtask_failures(monkeypatch):
    provider_ids = [str(uuid.uuid4()) for _ in range(3)]

    class Registry:
        state = {
            "completed": 1,
            "failed": 0,
            "status": "running",
            "error": None,
        }
        output = ""

        def get(self, _task_id):
            return dict(self.state)

        @staticmethod
        def is_cancelled(_task_id):
            return False

        def incr(self, _task_id, field, by=1):
            self.state[field] += by

        def append_output(self, _task_id, chunk):
            self.output += chunk

        def update(self, _task_id, **fields):
            self.state.update(fields)

        def set_done(self, _task_id):
            self.state["status"] = "done"

        def set_cancelled(self, _task_id):
            self.state["status"] = "cancelled"

        def record_issue(self, _task_id, issue, **context):
            self.issues.append((issue, context))

    calls = []

    def run_subtask(_task_id, provider_id, _registry):
        calls.append(str(provider_id))
        if len(calls) == 1:
            raise task_execution.CollectionSubtaskTimeoutError(
                "Provider analysis exceeded 900 seconds"
            )
        return "ok"

    monkeypatch.setattr(task_execution, "_run_collection_subtask", run_subtask)
    marked_failures = []
    monkeypatch.setattr(
        task_execution,
        "_mark_collection_provider_failed",
        lambda provider_id, message: marked_failures.append((str(provider_id), message)),
    )
    registry = Registry()
    registry.issues = []

    task_execution._analyze_collection(
        "parent-task",
        {"provider_ids": provider_ids},
        registry,
    )

    assert calls == provider_ids[1:]
    assert registry.state == {
        "completed": 3,
        "failed": 1,
        "status": "done",
        "error": "Completed with 1 subtask failure.",
    }
    assert "SUBTASK FAILED" in registry.output
    assert provider_ids[1] in registry.output
    assert marked_failures == [
        (provider_ids[1], "Provider analysis exceeded 900 seconds"),
    ]
    assert registry.issues[0][0]["code"] == "execution.timeout"
    assert registry.issues[0][1]["provider_id"] == uuid.UUID(provider_ids[1])


def test_collection_subtask_timeout_terminates_process(monkeypatch):
    class Process:
        stdout = io.StringIO("")
        returncode = None
        terminated = False

        def poll(self):
            return self.returncode

        def terminate(self):
            self.terminated = True
            self.returncode = -15

        def wait(self, timeout=None):
            return self.returncode

        def kill(self):
            self.returncode = -9

    class Registry:
        @staticmethod
        def is_cancelled(_task_id):
            return False

        @staticmethod
        def append_output(_task_id, _chunk):
            return None

    process = Process()
    monkeypatch.setattr(task_execution.subprocess, "Popen", lambda *args, **kwargs: process)
    monotonic_values = iter((0.0, 2.0))
    monkeypatch.setattr(task_execution.time, "monotonic", lambda: next(monotonic_values))
    monkeypatch.setattr(task_execution.time, "sleep", lambda _seconds: None)

    with pytest.raises(
        task_execution.CollectionSubtaskTimeoutError,
        match="exceeded 1 seconds",
    ):
        task_execution._run_collection_subtask(
            "parent-task",
            uuid.uuid4(),
            Registry(),
            timeout_seconds=1,
        )

    assert process.terminated


def test_stale_task_claim_resumes_after_recovery_grace(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'recovery.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(task_module, "SessionLocal", session)
    monkeypatch.setenv("TASK_CLAIM_RECOVERY_SECONDS", "1200")

    registry = task_module.TaskRegistry()
    task_id = registry.create(kind="collection-analysis", title="Analyze", total=3)
    registry.update(
        task_id,
        payload={"kind": "collection-analysis", "provider_ids": ["a", "b", "c"]},
    )
    assert registry.claim(task_id) is not None

    with session() as db:
        task = db.get(TaskRecord, uuid.UUID(task_id))
        task.started_at = datetime.now(timezone.utc) - timedelta(minutes=21)
        task.completed = 1
        db.commit()

    payload = registry.claim(task_id)
    assert payload == {
        "kind": "collection-analysis",
        "provider_ids": ["a", "b", "c"],
    }
    assert registry.get(task_id)["completed"] == 1


def test_web_dependencies_exclude_analysis_stack():
    with open("pyproject.toml", "rb") as file:
        project = tomllib.load(file)["project"]
    core = "\n".join(project["dependencies"]).lower()
    analysis = "\n".join(project["optional-dependencies"]["analysis"]).lower()
    for package in ("torch", "spacy", "playwright", "poligrapher", "sentence-transformers"):
        assert package not in core
        assert package in analysis


def test_dockerfile_exposes_separate_web_and_worker_targets():
    dockerfile = open("Dockerfile", encoding="utf-8").read()
    assert " AS web" in dockerfile
    assert " AS worker" in dockerfile
    assert "pip install --user --no-cache-dir ." in dockerfile
    assert "pip install --user --no-cache-dir '.[analysis]'" in dockerfile


def test_azure_deploy_uses_oidc_and_gated_migrations():
    workflow = open(".github/workflows/deploy-azure.yml").read()
    infrastructure = open("infra/main.bicep").read()
    entrypoint = open("docker/entrypoint.sh").read()

    assert "id-token: write" in workflow
    assert "azure/login@v2" in workflow
    assert "azure-production" in workflow
    assert "az containerapp job start" in workflow
    assert "Verify deployed application" in workflow
    assert "triggerType: 'Manual'" in infrastructure
    assert "replicaTimeout: 43200" in infrastructure
    assert "AZURE_QUEUE_VISIBILITY_TIMEOUT_SECONDS" in infrastructure
    assert "COLLECTION_SUBTASK_TIMEOUT_SECONDS" in infrastructure
    assert "alembic upgrade head && python -m poligrapher_app.sync_source_catalog" in infrastructure
    assert "{ name: 'RUN_MIGRATIONS', value: 'false' }" in infrastructure
    assert "RUN_MIGRATIONS:-true" in entrypoint
