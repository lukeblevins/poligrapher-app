import io
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from poligrapher_app.api.database import Base
from poligrapher_app.api.deps import get_db
from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.api.routers import analysis
from poligrapher_app.api.routers.analysis import build_public_graph_archive


def _archive(entries: dict[str, bytes]) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return payload.getvalue()


def test_public_graph_archive_exposes_only_allowlisted_graph_files():
    payload = build_public_graph_archive(_archive({
        "graph.yml": b"graph: final",
        "nested/graph-original.graphml": b"<graphml />",
        "output.html": b"private policy text",
        "run.log": b"private diagnostics",
        "accessibility_tree.json": b"{}",
        "output.pdf": b"%PDF",
    }))

    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        assert set(archive.namelist()) == {"graph.yml", "graph-original.graphml"}
        assert archive.read("graph.yml") == b"graph: final"


def test_public_graph_archive_rejects_missing_graph_files():
    with pytest.raises(FileNotFoundError, match="No graph artifacts"):
        build_public_graph_archive(_archive({"run.log": b"private"}))


def test_public_graph_archive_ignores_unsafe_graph_paths():
    with pytest.raises(FileNotFoundError, match="No graph artifacts"):
        build_public_graph_archive(_archive({"../graph.yml": b"unsafe"}))


def test_public_graph_archive_rejects_invalid_zip():
    with pytest.raises(ValueError, match="valid ZIP"):
        build_public_graph_archive(b"not-a-zip")


def test_public_graph_archive_enforces_expanded_size(monkeypatch):
    monkeypatch.setattr(
        "poligrapher_app.api.routers.analysis.MAX_PUBLIC_GRAPH_EXPANDED_BYTES",
        4,
    )
    with pytest.raises(ValueError, match="exceeds public download limits"):
        build_public_graph_archive(_archive({"graph.yml": b"12345"}))


def test_public_graph_archive_enforces_private_archive_size(monkeypatch):
    monkeypatch.setattr(
        "poligrapher_app.api.routers.analysis.MAX_PRIVATE_ARTIFACT_BYTES",
        4,
    )
    with pytest.raises(ValueError, match="exceeds public download limits"):
        build_public_graph_archive(_archive({"graph.yml": b"1"}))


def test_public_graph_download_route_exposes_only_graph_files(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        provider = Provider(name="Example")
        db.add(provider)
        db.flush()
        policy = Policy(
            provider_id=provider.id,
            url="https://example.com/privacy",
            source="webpage",
            artifact_blob_key="artifacts/example/artifacts.zip",
            persistence_status="persisted",
            pipeline_status="succeeded",
        )
        db.add(policy)
        db.commit()
        policy_id = policy.id

    class Storage:
        @staticmethod
        def open_bytes(key):
            assert key == "artifacts/example/artifacts.zip"
            return _archive({"graph.yml": b"graph: final", "run.log": b"private"})

    monkeypatch.setattr("poligrapher_app.services.storage.get_storage", lambda: Storage())
    app = FastAPI()
    app.include_router(analysis.router)

    def session_override():
        with Session(engine) as db:
            yield db

    app.dependency_overrides[get_db] = session_override
    client = TestClient(app)

    response = client.get(f"/api/policies/{policy_id}/graph-artifacts")

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["x-content-type-options"] == "nosniff"
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert archive.namelist() == ["graph.yml"]
        assert archive.read("graph.yml") == b"graph: final"

    private_response = client.get(f"/api/policies/{policy_id}/artifacts")
    assert private_response.status_code == 401
