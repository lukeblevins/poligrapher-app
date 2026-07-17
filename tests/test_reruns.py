import zipfile
import uuid
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.api.routers.runs import _rerun_availability, delete_run
from poligrapher_app.services.storage import LocalObjectStorage


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
