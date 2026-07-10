from pathlib import Path
from types import SimpleNamespace

from poligrapher_app.services.persistence import create_artifact_archive, temporary_document
from poligrapher_app.services.storage import LocalObjectStorage, artifact_key, source_key


def test_deterministic_private_keys():
    policy_id = "1234"
    assert source_key(policy_id, "../policy.pdf") == "sources/1234/policy.pdf"
    assert artifact_key(policy_id) == "artifacts/1234/artifacts.zip"
    assert artifact_key(policy_id, failed=True) == "artifacts/1234/failure.zip"


def test_local_storage_round_trip(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")
    source = tmp_path / "source.pdf"
    source.write_bytes(b"pdf")
    storage.upload_file("sources/id/source.pdf", source)
    destination = tmp_path / "download.pdf"
    storage.download_file("sources/id/source.pdf", destination)
    assert destination.read_bytes() == b"pdf"
    assert storage.open_bytes("sources/id/source.pdf") == b"pdf"
    storage.delete("sources/id/source.pdf")
    assert not storage.exists("sources/id/source.pdf")


def test_archive_includes_canonical_files_only(tmp_path):
    output = tmp_path / "output"
    output.mkdir()
    (output / "graph-original.yml").write_text("nodes: []")
    (output / "run.log").write_text("ok")
    (output / "document.pickle").write_bytes(b"large")
    archive = tmp_path / "artifacts.zip"
    assert create_artifact_archive(output, archive) == 2
    import zipfile
    with zipfile.ZipFile(archive) as zipped:
        assert set(zipped.namelist()) == {"graph-original.yml", "run.log"}


def test_temporary_workspace_is_removed(monkeypatch, tmp_path):
    monkeypatch.setenv("TEMP_WORKSPACE_ROOT", str(tmp_path))
    policy = SimpleNamespace(
        source="webpage", url="https://example.com", capture_date=None,
        has_results=False, pipeline_errors=[], source_blob_key=None,
        artifact_blob_key=None,
    )
    with temporary_document(policy) as (doc, workspace):
        path = Path(workspace)
        assert path.exists()
        assert doc.output_dir.endswith("output")
    assert not path.exists()
