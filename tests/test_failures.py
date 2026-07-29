import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import TaskRecord
from poligrapher_app.services.failures import classify_failure
from poligrapher_app.services import tasks as task_module
from poligrapher_app.services.tasks import TaskRegistry


def test_failure_classifier_exposes_stable_codes_and_safe_actions():
    issue = classify_failure(
        "html_crawler failure: Chromium navigation failed and the HTTP source fallback was unavailable"
    )

    assert issue["code"] == "crawl.navigation_failed"
    assert issue["stage"] == "acquisition"
    assert issue["retryability"] == "transient"
    assert [action["action"] for action in issue["actions"]] == [
        "retry",
        "use_archive",
        "replace_source",
    ]


def test_task_issues_survive_output_truncation_and_drive_partial_outcome(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'issues.db'}")
    session = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    monkeypatch.setattr(task_module, "SessionLocal", session)
    registry = TaskRegistry()

    with session() as db:
        task = TaskRecord(
            id=uuid.uuid4(),
            kind="collection-analysis",
            total=1,
            failed=1,
            output=task_module._TRUNCATION_NOTICE + "tail",
        )
        db.add(task)
        db.commit()
        task_id = str(task.id)

    registry.record_issue(
        task_id,
        classify_failure("Provider analysis exceeded 900 seconds"),
        provider_id="11111111-1111-1111-1111-111111111111",
    )
    registry.set_done(task_id)
    public = registry.get(task_id)

    assert public["status"] == "done"
    assert public["outcome"] == "partially_succeeded"
    assert public["issues"][0]["code"] == "execution.timeout"
    assert registry.retryable_provider_ids(task_id) == [
        "11111111-1111-1111-1111-111111111111"
    ]
