import json
import tomllib

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from poligrapher_app.api.database import Base
from poligrapher_app.services import tasks as task_module


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

    task_id = registry.create(kind="comparison", title="Compare", total=1)
    registry.enqueue(task_id, {"kind": "comparison", "provider_id": "provider"})
    assert queue.messages == [{"task_id": task_id}]
    assert registry.get(task_id)["status"] == "running"
    assert registry.claim(task_id) == {"kind": "comparison", "provider_id": "provider"}
    assert registry.claim(task_id) is None

    assert registry.cancel(task_id)
    assert registry.get(task_id)["status"] == "cancelling"
    assert registry.is_cancelled(task_id)
    registry.set_cancelled(task_id)
    assert registry.get(task_id)["status"] == "cancelled"


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
