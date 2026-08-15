from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

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

    assert [(target.provider_name, target.root_code) for target in targets] == [
        ("Graph Failed", "graph.empty"),
        ("Source Failed", "crawl.navigation_failed"),
    ]
    assert [target.root_retryability for target in targets] == ["manual", "transient"]


def test_source_audit_targets_ignore_failed_recovery_experiments():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        provider = Provider(
            name="Example",
            domain="example.test",
            source_url="https://example.test/privacy",
        )
        original = TaskRecord(kind="collection-analysis", status="done")
        recovery = TaskRecord(kind="cohort-recovery", status="done")
        db.add_all([provider, original, recovery])
        db.flush()
        db.add_all([
            TaskIssue(
                task_id=original.id,
                code="source.not_policy",
                stage="validation",
                severity="error",
                retryability="manual",
                summary="Original source was not a policy",
                provider_id=str(provider.id),
                occurred_at=datetime.now(timezone.utc) - timedelta(minutes=1),
            ),
            TaskIssue(
                task_id=recovery.id,
                code="crawl.navigation_failed",
                stage="acquisition",
                severity="error",
                retryability="transient",
                summary="Candidate experiment failed",
                provider_id=str(provider.id),
                occurred_at=datetime.now(timezone.utc),
            ),
        ])
        db.commit()

        targets = cohort_audit.source_audit_targets(db, [provider.id])

    assert len(targets) == 1
    assert targets[0].root_code == "source.not_policy"


def test_source_audit_targets_include_bounded_pdf_timeouts():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        provider = Provider(
            name="Example PDF",
            domain="example.test",
            source_url="https://example.test/privacy.pdf",
        )
        task = TaskRecord(kind="collection-analysis", status="done")
        db.add_all([provider, task])
        db.flush()
        db.add(TaskIssue(
            task_id=task.id,
            code="pdf.download_timeout",
            stage="acquisition",
            severity="error",
            retryability="transient",
            summary="PDF download timed out",
            provider_id=str(provider.id),
        ))
        db.commit()

        targets = cohort_audit.source_audit_targets(db, [provider.id])

    assert len(targets) == 1
    assert targets[0].root_code == "pdf.download_timeout"


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
    monkeypatch.setattr(cohort_audit, "fetch_validated_policy_html", lambda _url, **_kwargs: "")
    result = cohort_audit.audit_source_target(target)

    assert result["status"] == "replacement_found"
    assert result["current_valid"] is False
    assert result["replacement_url"] == "https://example.com/privacy"
    assert result["replacement_confidence"] == 0.84


def test_audit_source_target_retries_transient_current_source_without_discovery(monkeypatch):
    target = cohort_audit.SourceAuditTarget(
        provider_id=uuid.uuid4(),
        provider_name="Example",
        domain="example.com",
        source_url="https://example.com/privacy",
        root_code="crawl.navigation_failed",
        root_retryability="transient",
    )

    monkeypatch.setattr(
        cohort_audit,
        "PolicySourceResolver",
        lambda **_kwargs: (_ for _ in ()).throw(
            AssertionError("transient retries must not spend time on discovery")
        ),
    )

    result = cohort_audit.audit_source_target(target, deep=True)

    assert result["status"] == "retry_current"
    assert result["current_resolved_url"] == target.source_url


def test_audit_source_target_requires_review_for_off_domain_candidate(monkeypatch):
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

        def resolve(self, *_args):
            return None

        def resolve_candidate(self, *_args, **_kwargs):
            return SimpleNamespace(
                url="https://example-privacy.com/privacy",
                strategy="search",
                confidence=0.76,
                notes="validated public search result",
            )

    monkeypatch.setattr(cohort_audit, "PolicySourceResolver", Resolver)
    monkeypatch.setattr(cohort_audit, "fetch_validated_policy_html", lambda _url, **_kwargs: "")

    result = cohort_audit.audit_source_target(target)

    assert result["status"] == "review_required"
    assert result["replacement_url"] == "https://example-privacy.com/privacy"


def test_audit_source_target_requires_review_below_auto_confidence(monkeypatch):
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

        def resolve_candidate(self, *_args, **_kwargs):
            return SimpleNamespace(
                url="https://privacy.example.com/privacy-policy",
                strategy="sitemap",
                confidence=0.6,
                notes="validated but ambiguous sitemap result",
            )

    monkeypatch.setattr(cohort_audit, "PolicySourceResolver", Resolver)
    monkeypatch.setattr(
        cohort_audit,
        "fetch_validated_policy_html",
        lambda url, **_kwargs: (
            "<html>policy</html>" if url == "https://privacy.example.com/privacy-policy" else ""
        ),
    )

    result = cohort_audit.audit_source_target(target, deep=True)

    assert result["status"] == "review_required"
    assert result["replacement_url"] == "https://privacy.example.com/privacy-policy"
    assert result["replacement_confidence"] == 0.6


def test_graph_empty_audit_skips_current_source_and_finds_alternate(monkeypatch):
    target = cohort_audit.SourceAuditTarget(
        provider_id=uuid.uuid4(),
        provider_name="Example",
        domain="example.com",
        source_url="https://example.com/privacy-shell",
        root_code="graph.empty",
    )

    class Resolver:
        def __init__(self, allow_headless=False):
            assert allow_headless is False

        def resolve(self, *_args):
            raise AssertionError("graph-empty audits must not revalidate the current source")

        def resolve_candidate(self, *_args, **kwargs):
            assert kwargs["exclude_urls"] == {"https://example.com/privacy-shell"}
            assert kwargs["require_validation"] is True
            return SimpleNamespace(
                url="https://www.example.com/privacy-policy",
                strategy="search",
                confidence=0.84,
                notes="validated public search result",
            )

    monkeypatch.setattr(cohort_audit, "PolicySourceResolver", Resolver)
    monkeypatch.setattr(
        cohort_audit,
        "fetch_validated_policy_html",
        lambda _url, **_kwargs: (_ for _ in ()).throw(
            AssertionError("graph-empty audits must not revalidate the current source")
        ),
    )

    result = cohort_audit.audit_source_target(target)

    assert result["status"] == "replacement_found"
    assert result["replacement_url"] == "https://www.example.com/privacy-policy"


def test_audit_current_source_requires_pipeline_valid_html(monkeypatch):
    target = cohort_audit.SourceAuditTarget(
        provider_id=uuid.uuid4(),
        provider_name="Example",
        domain="example.com",
        source_url="https://example.com/privacy",
        root_code="crawl.navigation_failed",
    )

    class Resolver:
        def __init__(self, allow_headless=False):
            assert allow_headless is False

        def resolve_candidate(self, *_args, **_kwargs):
            raise AssertionError("a pipeline-valid current source needs no replacement")

    monkeypatch.setattr(cohort_audit, "PolicySourceResolver", Resolver)
    monkeypatch.setattr(
        cohort_audit,
        "fetch_validated_policy_html",
        lambda url, **_kwargs: "<html>policy</html>" if url == target.source_url else "",
    )

    result = cohort_audit.audit_source_target(target)

    assert result["status"] == "current_valid"
    assert result["current_resolved_url"] == target.source_url


def test_audit_rejects_superficially_different_current_url(monkeypatch):
    target = cohort_audit.SourceAuditTarget(
        provider_id=uuid.uuid4(),
        provider_name="Example",
        domain="example.com",
        source_url="https://www.example.com/privacy/",
        root_code="graph.empty",
    )

    class Resolver:
        def __init__(self, allow_headless=False):
            assert allow_headless is False

        def resolve_candidate(self, *_args, **_kwargs):
            return SimpleNamespace(
                url="https://example.com/privacy",
                strategy="discovery",
                confidence=0.8,
                notes="same source",
            )

    monkeypatch.setattr(cohort_audit, "PolicySourceResolver", Resolver)
    result = cohort_audit.audit_source_target(target)

    assert result["status"] == "unresolved"
    assert result["replacement_url"] is None


def test_deep_audit_revalidates_discovered_candidate(monkeypatch):
    target = cohort_audit.SourceAuditTarget(
        provider_id=uuid.uuid4(),
        provider_name="Example",
        domain="example.com",
        source_url="https://example.com/old",
        root_code="graph.empty",
    )

    class Resolver:
        def __init__(self, allow_headless=False):
            assert allow_headless is False

        def resolve_candidate(self, *_args, **kwargs):
            assert kwargs["allow_site_discovery"] is True
            return SimpleNamespace(
                url="https://example.com/privacy",
                strategy="discovery",
                confidence=0.8,
                notes="footer link",
            )

    monkeypatch.setattr(cohort_audit, "PolicySourceResolver", Resolver)
    monkeypatch.setattr(
        cohort_audit,
        "fetch_validated_policy_html",
        lambda url, **_kwargs: "<html>policy</html>" if url.endswith("/privacy") else "",
    )

    result = cohort_audit.audit_source_target(target, deep=True)

    assert result["status"] == "replacement_found"
    assert result["replacement_url"] == "https://example.com/privacy"


def test_audit_subprocess_is_terminated_at_wall_clock_deadline():
    target = cohort_audit.SourceAuditTarget(
        provider_id=uuid.uuid4(),
        provider_name="Stalled",
        domain="stalled.example",
        source_url="https://stalled.example/privacy",
        root_code="source.inaccessible",
    )

    class Connection:
        def __init__(self):
            self.closed = False

        def close(self):
            self.closed = True

        def poll(self):
            return False

    class Process:
        exitcode = None

        def __init__(self):
            self.alive = True
            self.terminated = False

        def start(self):
            return None

        def join(self, _timeout):
            return None

        def is_alive(self):
            return self.alive

        def terminate(self):
            self.terminated = True
            self.alive = False

    class Context:
        def __init__(self):
            self.receiver = Connection()
            self.sender = Connection()
            self.process = Process()

        def Pipe(self, duplex=False):
            assert duplex is False
            return self.receiver, self.sender

        def Process(self, **kwargs):
            assert kwargs["target"] is cohort_audit._audit_source_target_child
            assert kwargs["daemon"] is True
            return self.process

    context = Context()
    result = cohort_audit._run_audit_source_target(
        target,
        deep=True,
        timeout_seconds=0.01,
        context=context,
    )

    assert context.process.terminated is True
    assert result["status"] == "audit_error"
    assert result["error"] == "Source audit exceeded 0.01 seconds"
