from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from poligrapher_app.api import database
from poligrapher_app.api.database import Base
from poligrapher_app.api.models import AnalysisResult, CompanyCollection, Policy, Provider
from poligrapher_app.api.routers.policies import (
    _bulk_analysis_targets,
    _bulk_targets,
    _selected_providers,
    run_bulk_action,
    start_retention_cleanup,
)
from poligrapher_app.api.schemas import BulkActionRequest, BulkSelection, RetentionRequest
from poligrapher_app.services.retention import cleanup_retention, preview_retention
from poligrapher_app.services.storage import LocalObjectStorage


def _upload(storage: LocalObjectStorage, tmp_path, key: str, content: bytes = b"artifact") -> None:
    source = tmp_path / key.replace("/", "-")
    source.write_bytes(content)
    storage.upload_file(key, source)


def test_bulk_targets_merge_collection_and_direct_selection():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = Provider(name="First")
        second = Provider(name="Second")
        third = Provider(name="Third")
        cohort = CompanyCollection(name="Cohort", providers=[first, second])
        db.add_all([cohort, third])
        db.flush()
        db.add_all([
            Policy(provider_id=first.id, url="https://first.test/privacy", source="webpage"),
            Policy(provider_id=second.id, url="https://second.test/privacy", source="webpage"),
        ])
        db.commit()

        providers, policies, skipped = _bulk_targets(
            BulkActionRequest(operation="generate", provider_ids=[third.id], collection_ids=[cohort.id]), db,
        )

        assert [provider.name for provider in providers] == ["First", "Second", "Third"]
        assert len(policies) == 2
        assert skipped == ["Third has no analysis to generate"]


def test_bulk_analysis_targets_use_sources_and_skip_existing_graphs():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        complete = Provider(name="Complete", source_url="https://complete.test/privacy")
        ready = Provider(name="Ready", source_url="https://ready.test/privacy")
        missing = Provider(name="Missing")
        cohort = CompanyCollection(name="Cohort", providers=[complete, ready, missing])
        db.add(cohort)
        db.flush()
        db.add(Policy(
            provider_id=complete.id,
            url=complete.source_url,
            source="webpage",
            graph_data={"elements": [{"data": {"id": "node"}}]},
        ))
        db.commit()

        providers, eligible, skipped = _bulk_analysis_targets(
            BulkActionRequest(operation="generate", collection_ids=[cohort.id]), db,
        )

        assert [provider.name for provider in providers] == ["Complete", "Missing", "Ready"]
        assert [provider.name for provider in eligible] == ["Ready"]
        assert skipped == [
            "Complete already has an analysis",
            "Missing has no policy source",
        ]


def test_bulk_analysis_targets_do_not_count_empty_graph_payloads():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        provider = Provider(name="Ready", source_url="https://ready.test/privacy")
        db.add(provider)
        db.flush()
        db.add(Policy(
            provider_id=provider.id,
            url=provider.source_url,
            source="webpage",
            graph_data={"elements": []},
        ))
        db.commit()

        _, eligible, skipped = _bulk_analysis_targets(
            BulkActionRequest(operation="generate", provider_ids=[provider.id]), db,
        )

        assert [item.name for item in eligible] == ["Ready"]
        assert skipped == []


def test_bulk_targets_use_a_bounded_number_of_queries_for_collections():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        providers = [Provider(name=f"Provider {index:03}") for index in range(30)]
        cohort = CompanyCollection(name="Large cohort", providers=providers)
        db.add(cohort)
        db.flush()
        db.add_all([
            Policy(provider_id=provider.id, url=f"https://example.test/{index}", source="webpage")
            for index, provider in enumerate(providers)
        ])
        db.commit()
        collection_id = cohort.id
        db.expire_all()

        selects = 0

        def count_selects(_conn, _cursor, statement, _parameters, _context, _executemany):
            nonlocal selects
            if statement.lstrip().upper().startswith("SELECT"):
                selects += 1

        event.listen(engine, "before_cursor_execute", count_selects)
        try:
            _, policies, skipped = _bulk_targets(
                BulkActionRequest(operation="generate", collection_ids=[collection_id]), db,
            )
        finally:
            event.remove(engine, "before_cursor_execute", count_selects)

        assert len(policies) == 30
        assert skipped == []
        assert selects <= 4


def test_bulk_selection_rejects_empty_cohort():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db, pytest.raises(HTTPException, match="Select at least one"):
        _selected_providers(BulkSelection(), db)


def test_bulk_action_queues_a_durable_task_with_selection_summary():
    class Registry:
        def __init__(self):
            self.created = None
            self.payload = None
            self.output = []

        def create(self, **kwargs):
            self.created = kwargs
            return "00000000-0000-0000-0000-000000000001"

        def append_output(self, task_id, output):
            self.output.append((task_id, output))

        def enqueue(self, task_id, payload):
            self.payload = (task_id, payload)

        def get(self, task_id):
            return {"task_id": task_id, "status": "running"}

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    registry = Registry()
    with Session(engine) as db:
        provider = Provider(name="Example", source_url="https://example.test/privacy")
        db.add(provider)
        db.commit()

        task = run_bulk_action(
            BulkActionRequest(operation="generate", provider_ids=[provider.id]),
            SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tasks=registry))),
            db,
        )

    assert task.kind is None
    assert registry.created == {"kind": "collection-analysis", "title": "Analyze · 1 companies", "total": 1}
    assert registry.payload == ("00000000-0000-0000-0000-000000000001", {
        "kind": "collection-analysis", "provider_ids": [str(provider.id)], "skipped": [],
    })
    assert "1 companies are eligible" in registry.output[0][1]


def test_retention_cleanup_requires_explicit_confirmation():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db, pytest.raises(HTTPException, match="explicit confirmation"):
        start_retention_cleanup(
            RetentionRequest(older_than_days=30),
            SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tasks=object()))),
            db,
        )


def test_retention_preview_and_cleanup_remove_old_records_and_blobs(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "objects"))
    storage = LocalObjectStorage(tmp_path / "objects")
    engine = create_engine(f"sqlite:///{tmp_path / 'retention.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", sessions)
    old_time = datetime.now(timezone.utc) - timedelta(days=31)
    recent_time = datetime.now(timezone.utc) - timedelta(days=2)

    with sessions() as db:
        provider = Provider(name="Example")
        old_policy = Policy(
            provider=provider,
            url="https://example.test/old",
            source="webpage",
            source_blob_key="sources/old.html",
            artifact_blob_key="artifacts/old.zip",
            created_at=old_time,
        )
        recent_policy = Policy(
            provider=provider,
            url="https://example.test/recent",
            source="webpage",
            source_blob_key="sources/recent.html",
            created_at=recent_time,
        )
        db.add_all([old_policy, recent_policy])
        db.flush()
        db.add(AnalysisResult(policy_id=old_policy.id, analysis_type="privacy", score=88))
        db.commit()
        old_id, recent_id = old_policy.id, recent_policy.id

        preview = preview_retention(db, 7)
        assert preview["policy_count"] == 1
        assert preview["analysis_result_count"] == 1
        assert preview["artifact_count"] == 2
        assert preview["provider_count"] == 1

    for key in ("sources/old.html", "artifacts/old.zip", "sources/recent.html"):
        _upload(storage, tmp_path, key)

    result = cleanup_retention(7)

    assert result == {"removed": 1, "failed": 0, "cancelled": False}
    assert not storage.exists("sources/old.html")
    assert not storage.exists("artifacts/old.zip")
    assert storage.exists("sources/recent.html")
    with sessions() as db:
        assert db.get(Policy, old_id) is None
        assert db.get(Policy, recent_id) is not None
        assert db.query(AnalysisResult).count() == 0
