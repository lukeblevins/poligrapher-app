from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import Policy, Provider, TaskIssue, TaskRecord
from poligrapher_app.services import cohort_audit


def test_source_audit_targets_select_latest_unresolved_source_failure():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    with session() as db:
        source_failed = Provider(name="Source Failed", domain="failed.example", source_url="https://failed.example/privacy")
        graph_failed = Provider(name="Graph Failed", domain="graph.example", source_url="https://graph.example/privacy")
        analyzed = Provider(name="Analyzed", domain="analyzed.example", source_url="https://analyzed.example/privacy")
        db.add_all([source_failed, graph_failed, analyzed])
        db.flush()
        old_task = TaskRecord(kind="collection-analysis", status="done")
        new_task = TaskRecord(kind="collection-analysis", status="done")
        db.add_all([old_task, new_task])
        db.flush()
        db.add_all(
            [
                TaskIssue(
                    task_id=old_task.id,
                    code="source.not_policy",
                    stage="validation",
                    severity="error",
                    retryability="manual",
                    summary="Old",
                    provider_id=str(source_failed.id),
                    occurred_at=now - timedelta(minutes=1),
                ),
                TaskIssue(
                    task_id=new_task.id,
                    code="crawl.navigation_failed",
                    stage="acquisition",
                    severity="error",
                    retryability="transient",
                    summary="Latest",
                    provider_id=str(source_failed.id),
                    occurred_at=now,
                ),
                TaskIssue(
                    task_id=new_task.id,
                    code="graph.empty",
                    stage="graph",
                    severity="error",
                    retryability="manual",
                    summary="Graph",
                    provider_id=str(graph_failed.id),
                    occurred_at=now,
                ),
            ]
        )
        db.add(
            Policy(
                provider_id=analyzed.id,
                url=analyzed.source_url,
                source="webpage",
                method="website",
                graph_data={"elements": [{"data": {"id": "complete"}}]},
            )
        )
        db.commit()

        targets = cohort_audit.source_audit_targets(
            db,
            [source_failed.id, graph_failed.id, analyzed.id],
        )

    assert len(targets) == 1
    assert targets[0].provider_name == "Source Failed"
    assert targets[0].root_code == "crawl.navigation_failed"


def test_audit_source_target_returns_only_validated_replacement(monkeypatch):
    target = cohort_audit.SourceAuditTarget(
        provider_id=uuid.uuid4(),
        provider_name="Example",
        domain="example.com",
        source_url="https://example.com/wrong",
        root_code="source.not_policy",
    )

    class Resolver:
        def __init__(self, allow_headless=False):
            assert allow_headless is False

        def resolve(self, _name, _domain, url):
            if url.endswith("/privacy"):
                return SimpleNamespace(url="https://example.com/privacy")
            return None

        def resolve_candidate(self, *_args, **kwargs):
            assert kwargs["require_validation"] is True
            assert kwargs["exclude_urls"] == {"https://example.com/wrong"}
            return SimpleNamespace(
                url="https://example.com/privacy",
                strategy="search",
                confidence=0.84,
                notes="validated public search result",
            )

    monkeypatch.setattr(cohort_audit, "PolicySourceResolver", Resolver)
    result = cohort_audit.audit_source_target(target)

    assert result["status"] == "replacement_found"
    assert result["current_valid"] is False
    assert result["replacement_url"] == "https://example.com/privacy"
    assert result["replacement_confidence"] == 0.84
