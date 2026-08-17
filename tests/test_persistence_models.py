import uuid
import os
import subprocess
import sys

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import Policy, Provider
from fastapi import HTTPException
import pytest

from poligrapher_app.api.routers.analysis import _require_export_token, get_graph, get_stats
from poligrapher_app.domain.policy_analysis import DocumentCaptureSource, PolicyDocumentInfo


def test_pdf_text_extraction_accepts_uppercase_extension(monkeypatch, tmp_path):
    (tmp_path / "PRIVACY-NOTICE.PDF").write_bytes(b"%PDF")

    class Page:
        @staticmethod
        def get_text():
            return "Privacy notice text"

    monkeypatch.setattr(
        "poligrapher_app.domain.policy_analysis.pymupdf4llm.pymupdf.open",
        lambda _path: [Page()],
    )
    document = PolicyDocumentInfo(
        "source.PDF",
        str(tmp_path),
        DocumentCaptureSource.PDF,
        None,
        False,
    )

    assert document.get_document_text() == "Privacy notice text\n"


def test_canonical_json_round_trip():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        provider = Provider(name="Example")
        db.add(provider)
        db.flush()
        policy = Policy(
            provider_id=provider.id,
            url="https://example.com/privacy",
            source="webpage",
            graph_data={"elements": [{"data": {"id": "n1"}}]},
            graph_stats={"nodes": 1, "edges": 0},
            artifact_blob_key=f"artifacts/{uuid.uuid4()}/artifacts.zip",
            persistence_status="persisted",
        )
        db.add(policy)
        db.commit()
        db.expire_all()
        stored = db.get(Policy, policy.id)
        assert stored.graph_data["elements"][0]["data"]["id"] == "n1"
        assert stored.graph_stats == {"nodes": 1, "edges": 0}
        assert stored.output_dir is None
        assert get_graph(stored.id, db).elements == [{"data": {"id": "n1"}}]
        assert get_stats(stored.id, db).stats == {"nodes": 1, "edges": 0}


def test_private_export_requires_matching_token(monkeypatch):
    monkeypatch.setenv("EXPORT_TOKEN", "secret")
    with pytest.raises(HTTPException) as denied:
        _require_export_token("Bearer wrong")
    assert denied.value.status_code == 401
    _require_export_token("Bearer secret")


def test_production_rejects_sqlite():
    env = os.environ | {
        "APP_ENV": "production",
        "DATABASE_URL": "sqlite:///should-not-start.db",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import poligrapher_app.api.database"],
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Production requires a persistent PostgreSQL" in result.stderr
