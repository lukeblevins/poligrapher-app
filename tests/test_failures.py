import uuid

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import TaskRecord
from poligrapher_app.services.failures import classify_failure
from poligrapher_app.services import tasks as task_module
from poligrapher_app.services.task_execution import _settle_result
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


@pytest.mark.parametrize(
    ("detail", "code", "stage", "retryability", "first_action"),
    [
        (
            "Page.goto: Download is starting",
            "source.direct_pdf",
            "acquisition",
            "manual",
            "use_pdf_method",
        ),
        (
            "Page.evaluate: Readability.js failed to parse the document",
            "extraction.readability_failed",
            "extraction",
            "manual",
            "try_other_method",
        ),
        (
            "code=4: no font file for digest",
            "pdf.extraction_failed",
            "extraction",
            "manual",
            "try_other_method",
        ),
        (
            "Page.goto: net::ERR_HTTP2_PROTOCOL_ERROR",
            "crawl.navigation_failed",
            "acquisition",
            "transient",
            "retry",
        ),
        (
            "Invalid role: emphasis",
            "document.unsupported_structure",
            "extraction",
            "blocked",
            "try_other_method",
        ),
        (
            "Graph generation pipeline exited",
            "execution.pipeline_failed",
            "execution",
            "transient",
            "retry",
        ),
        (
            "Provider analysis subprocess exited with code -9",
            "execution.subprocess_failed",
            "execution",
            "transient",
            "retry",
        ),
    ],
)
def test_failure_classifier_recognizes_pipeline_failures(
    detail, code, stage, retryability, first_action
):
    issue = classify_failure(detail)

    assert issue["code"] == code
    assert issue["stage"] == stage
    assert issue["retryability"] == retryability
    assert issue["actions"][0]["action"] == first_action


@pytest.mark.parametrize(
    ("result", "expected_code"),
    [
        ("needs_source", "source.missing"),
        ("gone", "source.inaccessible"),
    ],
)
def test_terminal_source_results_persist_structured_issues(result, expected_code):
    class Registry:
        def __init__(self):
            self.issue = None
            self.error = None

        @staticmethod
        def get(_task_id):
            return {"provider_id": "provider-1", "policy_id": "policy-1"}

        def record_issue(self, _task_id, issue, **context):
            self.issue = (issue, context)

        def set_failed(self, _task_id, error):
            self.error = error

    registry = Registry()
    _settle_result("task-1", result, registry)

    assert registry.issue[0]["code"] == expected_code
    assert registry.issue[1] == {
        "provider_id": "provider-1",
        "policy_id": "policy-1",
    }
    assert registry.error


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

    registry.record_issue(
        task_id,
        classify_failure("Pipeline produced no canonical graph elements"),
        provider_id="11111111-1111-1111-1111-111111111111",
    )
    assert registry.retryable_provider_ids(task_id) == []
