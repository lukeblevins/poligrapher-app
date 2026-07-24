import zipfile
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from poligrapher_app.api import database
from poligrapher_app.api.database import Base
from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.api.routers.runs import _rerun_availability, delete_run
from poligrapher_app.services.runs import run_archived_comparison
from poligrapher_app.services.storage import LocalObjectStorage
from poligrapher_app.services.task_execution import _rerun_upload


def _upload(storage, tmp_path, key, content):
    source = tmp_path / key.replace("/", "-")
    source.write_bytes(content)
    storage.upload_file(key, source)


def test_upload_rerun_requires_original_source(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "objects"))
    storage = LocalObjectStorage(tmp_path / "objects")
    policy = SimpleNamespace(method="pdf_upload", source_blob_key="sources/policy/source.pdf")

    assert not _rerun_availability([policy]).available
    _upload(storage, tmp_path, policy.source_blob_key, b"pdf")
    assert _rerun_availability([policy]).available


def test_website_rerun_requires_html_and_pdf(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "objects"))
    storage = LocalObjectStorage(tmp_path / "objects")
    archive = tmp_path / "capture.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("cleaned.html", "<html></html>")
        zipped.writestr("output.pdf", b"pdf")
    key = "artifacts/policy/artifacts.zip"
    storage.upload_file(key, archive)
    policy = SimpleNamespace(method="website", artifact_blob_key=key)

    availability = _rerun_availability([policy])
    assert availability.available
    assert availability.reason is None


def test_incomplete_website_archive_is_not_rerunnable(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "objects"))
    storage = LocalObjectStorage(tmp_path / "objects")
    archive = tmp_path / "capture.zip"
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("cleaned.html", "<html></html>")
    key = "artifacts/policy/artifacts.zip"
    storage.upload_file(key, archive)
    policy = SimpleNamespace(method="website", artifact_blob_key=key)

    availability = _rerun_availability([policy])
    assert not availability.available
    assert availability.reason == "The saved website copy is incomplete"


def test_grouped_delete_removes_both_methods_and_owned_blobs(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "objects"))
    storage = LocalObjectStorage(tmp_path / "objects")
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    run_id = uuid.uuid4()

    with Session(engine) as db:
        provider = Provider(name="Example")
        db.add(provider)
        db.flush()
        policies = [
            Policy(
                provider_id=provider.id,
                url="https://example.com/privacy",
                source=source,
                method=method,
                run_group=run_id,
                artifact_blob_key=f"artifacts/{uuid.uuid4()}/artifacts.zip",
            )
            for source, method in (("webpage", "website"), ("pdf", "pdf_from_page"))
        ]
        db.add_all(policies)
        db.commit()
        provider_id = provider.id
        keys = [policy.artifact_blob_key for policy in policies]
        for key in keys:
            _upload(storage, tmp_path, key, b"artifact")

        response = delete_run(provider_id, run_id, db)

        assert response.status_code == 204
        assert db.query(Policy).filter(Policy.run_group == run_id).count() == 0
        assert all(not storage.exists(key) for key in keys)


def test_archived_rerun_marks_rows_failed_when_blob_download_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "objects"))
    engine = create_engine(f"sqlite:///{tmp_path / 'archived.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", sessions)

    with sessions() as db:
        provider = Provider(name="Example")
        original = Policy(
            provider=provider,
            url="https://example.com/privacy",
            source="webpage",
            method="website",
            artifact_blob_key="artifacts/missing.zip",
        )
        website = Policy(
            provider=provider,
            url=original.url,
            source="webpage",
            method="website",
        )
        pdf = Policy(
            provider=provider,
            url=original.url,
            source="pdf",
            method="pdf_from_page",
        )
        db.add_all([original, website, pdf])
        db.commit()
        ids = original.id, website.id, pdf.id

    with pytest.raises(FileNotFoundError):
        run_archived_comparison(*ids)

    with sessions() as db:
        assert db.get(Policy, ids[1]).pipeline_status == "failed"
        assert db.get(Policy, ids[2]).pipeline_status == "failed"


def test_upload_rerun_marks_row_failed_when_blob_download_fails(monkeypatch, tmp_path):
    monkeypatch.setenv("STORAGE_BACKEND", "local")
    monkeypatch.setenv("LOCAL_STORAGE_ROOT", str(tmp_path / "objects"))
    engine = create_engine(f"sqlite:///{tmp_path / 'upload.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    monkeypatch.setattr(database, "SessionLocal", sessions)

    with sessions() as db:
        provider = Provider(name="Example")
        original = Policy(
            provider=provider,
            url="source.pdf",
            source="pdf",
            method="pdf_upload",
            source_blob_key="sources/missing.pdf",
        )
        rerun = Policy(
            provider=provider,
            url="source.pdf",
            source="pdf",
            method="pdf_upload",
        )
        db.add_all([original, rerun])
        db.commit()
        original_id, rerun_id = original.id, rerun.id

    with pytest.raises(FileNotFoundError):
        _rerun_upload(
            "00000000-0000-0000-0000-000000000001",
            {"original_policy_id": str(original_id), "policy_id": str(rerun_id)},
            SimpleNamespace(),
        )

    with sessions() as db:
        assert db.get(Policy, rerun_id).pipeline_status == "failed"
