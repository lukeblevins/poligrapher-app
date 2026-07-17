import json
import logging
import sys
import tomllib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from poligrapher_app.api.database import Base
from poligrapher_app.services import tasks as task_module
from poligrapher_app.services.task_execution import execute_task
from poligrapher_app.services.task_output import capture_task_output


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
