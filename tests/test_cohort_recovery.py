from datetime import datetime, timezone
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from poligrapher_app.api import database
from poligrapher_app.api.database import Base
from poligrapher_app.api.models import CompanyCollection, Policy, Provider, TaskIssue, TaskRecord
from poligrapher_app.api.routers.collections import recover_collection_failures
from poligrapher_app.api.schemas import CohortRecoveryRequest
from poligrapher_app.services import cohort_audit, task_execution
from poligrapher_app.services.cohort_recovery import (
    accept_source,
    has_completed_graph,
    recovery_url,
    restore_source,
    stage_source,
)


def test_recovery_url_only_allows_pipeline_validated_candidates():
    assert recovery_url({
        "status": "current_valid",
        "source_url": "https://example.test/privacy",
    }) == "https://example.test/privacy"
    assert recovery_url({
        "status": "replacement_found",
        "replacement_url": "https://example.test/privacy-policy",
    }) == "https://example.test/privacy-policy"
    assert recovery_url({
        "status": "retry_current",
        "source_url": "https://example.test/privacy",
    }) == "https://example.test/privacy"
    assert recovery_url({
        "status": "review_required",
        "replacement_url": "https://other.test/privacy",
    }) is None
    assert recovery_url({"status": "unresolved"}) is None


def test_failed_candidate_restores_every_source_field():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    checked_at = datetime(2026, 8, 1, tzinfo=timezone.utc)
    with Session(engine, expire_on_commit=False) as db:
        provider = Provider(
            name="Example",
            source_url="https://example.test/old",
            source_status="broken",
            source_checked_at=checked_at,
            source_http_status=403,
            source_final_url="https://example.test/blocked",
        )
        db.add(provider)
        db.commit()

        snapshot = stage_source(db, provider, "https://example.test/new")
        assert provider.source_url == "https://example.test/new"
        assert provider.source_status == "unchecked"

        restore_source(db, provider, snapshot)

        assert provider.source_url == "https://example.test/old"
        assert provider.source_status == "broken"
        assert provider.source_checked_at == checked_at
        assert provider.source_http_status == 403
        assert provider.source_final_url == "https://example.test/blocked"


def test_successful_candidate_is_accepted_only_with_nonempty_graph():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as db:
        provider = Provider(name="Example", source_url="https://example.test/old")
        db.add(provider)
        db.flush()
        db.add(Policy(
            provider_id=provider.id,
            url="https://example.test/new",
            source="webpage",
            graph_data={"elements": []},
        ))
        db.commit()
        assert has_completed_graph(db, provider.id) is False

        db.add(Policy(
            provider_id=provider.id,
            url="https://example.test/new",
            source="webpage",
            graph_data={"elements": [{"data": {"id": "node"}}]},
        ))
        db.commit()
        assert has_completed_graph(db, provider.id) is True

        accept_source(db, provider, "https://example.test/new")
        assert provider.source_url == "https://example.test/new"
        assert provider.source_status == "available"
        assert provider.source_final_url == "https://example.test/new"
        assert provider.source_checked_at is not None


def test_recovery_task_keeps_proven_source_and_rolls_back_failed_candidate(
    monkeypatch,
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    sessions = lambda: Session(engine, expire_on_commit=False)  # noqa: E731
    monkeypatch.setattr(database, "SessionLocal", sessions)
    with sessions() as db:
        succeeds = Provider(
            name="Succeeds",
            domain="succeeds.test",
            source_url="https://succeeds.test/old",
            source_status="broken",
        )
        fails = Provider(
            name="Fails",
            domain="fails.test",
            source_url="https://fails.test/old",
            source_status="restricted",
            source_http_status=403,
        )
        db.add_all([succeeds, fails])
        db.commit()
        succeed_id, fail_id = succeeds.id, fails.id

    targets = [
        cohort_audit.SourceAuditTarget(
            provider_id=succeed_id,
            provider_name="Succeeds",
            domain="succeeds.test",
            source_url="https://succeeds.test/old",
            root_code="source.not_policy",
        ),
        cohort_audit.SourceAuditTarget(
            provider_id=fail_id,
            provider_name="Fails",
            domain="fails.test",
            source_url="https://fails.test/old",
            root_code="source.not_policy",
        ),
    ]
    monkeypatch.setattr(
        cohort_audit,
        "source_audit_targets",
        lambda _db, provider_ids: [target for target in targets if target.provider_id in provider_ids],
    )

    def audit(targets, *, on_result, **_kwargs):
        for target in targets:
            on_result({
                **target.__dict__,
                "provider_id": str(target.provider_id),
                "status": "replacement_found",
                "replacement_url": f"https://{target.domain}/privacy-policy",
            })
        return {"checked": len(targets)}

    monkeypatch.setattr(cohort_audit, "audit_source_targets", audit)

    def analyze(_task_id, provider_id, _registry):
        if provider_id == succeed_id:
            with sessions() as db:
                db.add(Policy(
                    provider_id=provider_id,
                    url="https://succeeds.test/privacy-policy",
                    source="webpage",
                    graph_data={"elements": [{"data": {"id": "node"}}]},
                ))
                db.commit()
        return "ok"

    monkeypatch.setattr(task_execution, "_run_collection_subtask", analyze)

    class Registry:
        def __init__(self):
            self.task = {"completed": 0, "failed": 0}
            self.output = ""

        def get(self, _task_id):
            return dict(self.task)

        def is_cancelled(self, _task_id):
            return False

        def incr(self, _task_id, field, by=1):
            self.task[field] = self.task.get(field, 0) + by

        def append_output(self, _task_id, value):
            self.output += value

        def update(self, _task_id, **values):
            self.task.update(values)

        def set_done(self, _task_id):
            self.task["status"] = "done"

    registry = Registry()
    task_execution._recover_cohort(
        "task-id",
        {
            "provider_ids": [str(succeed_id), str(fail_id)],
            "deep": False,
        },
        registry,
    )

    with sessions() as db:
        succeeds = db.get(Provider, succeed_id)
        fails = db.get(Provider, fail_id)
        assert succeeds.source_url == "https://succeeds.test/privacy-policy"
        assert succeeds.source_status == "available"
        assert fails.source_url == "https://fails.test/old"
        assert fails.source_status == "restricted"
        assert fails.source_http_status == 403
    assert registry.task["completed"] == 2
    assert registry.task["failed"] == 1
    assert '"recovered": 1' in registry.output
    assert '"rolled_back": 1' in registry.output


def test_collection_recovery_endpoint_queues_only_unresolved_members():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    class Registry:
        def create(self, **values):
            self.created = values
            return "00000000-0000-0000-0000-000000000001"

        def enqueue(self, task_id, payload):
            self.enqueued = (task_id, payload)

        def get(self, task_id):
            return {"task_id": task_id, "status": "running"}

    registry = Registry()
    with Session(engine, expire_on_commit=False) as db:
        unresolved = Provider(
            name="Unresolved",
            source_url="https://unresolved.test/privacy",
        )
        complete = Provider(
            name="Complete",
            source_url="https://complete.test/privacy",
        )
        collection = CompanyCollection(
            name="Cohort",
            providers=[unresolved, complete],
        )
        original = TaskRecord(kind="collection-analysis", status="done")
        db.add_all([collection, original])
        db.flush()
        db.add(TaskIssue(
            task_id=original.id,
            code="source.not_policy",
            stage="validation",
            severity="error",
            retryability="manual",
            summary="Not a policy",
            provider_id=str(unresolved.id),
        ))
        db.add(Policy(
            provider_id=complete.id,
            url=complete.source_url,
            source="webpage",
            graph_data={"elements": [{"data": {"id": "node"}}]},
        ))
        db.commit()

        task = recover_collection_failures(
            collection.id,
            CohortRecoveryRequest(deep=True),
            SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tasks=registry))),
            db,
        )

    assert task.status == "running"
    assert registry.created == {
        "kind": "cohort-recovery",
        "title": "Recover 1 failed company sources",
        "total": 1,
    }
    assert registry.enqueued[1] == {
        "kind": "cohort-recovery",
        "provider_ids": [str(unresolved.id)],
        "deep": True,
    }
