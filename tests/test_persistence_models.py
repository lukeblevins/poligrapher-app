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
