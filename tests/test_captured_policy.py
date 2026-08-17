from datetime import date
from types import SimpleNamespace

import fitz
import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from poligrapher_app.api.database import Base
from poligrapher_app.api.models import Policy, Provider
from poligrapher_app.api.routers.runs import _persist_uploaded_policy
from poligrapher_app.api.schemas import CapturedPolicyText
from poligrapher_app.services.policy_documents import render_captured_policy_pdf
from poligrapher_app.services.storage import LocalObjectStorage


def test_captured_policy_requires_official_http_source_and_substantive_text():
    with pytest.raises(ValidationError):
        CapturedPolicyText(title="Policy", source_url="javascript:alert(1)", text="x" * 600)

    with pytest.raises(ValidationError):
        CapturedPolicyText(title="Policy", source_url="https://example.test/privacy", text="short")


def test_render_captured_policy_pdf_preserves_text_and_provenance(tmp_path):
    target = tmp_path / "captured.pdf"
    policy_text = ("We collect account information to provide the service.\n\n" * 80).strip()

    render_captured_policy_pdf(
        target,
        title="Example Privacy Notice",
        source_url="https://example.test/privacy",
        capture_date=date(2026, 8, 17).isoformat(),
        text=policy_text,
    )

    with fitz.open(target) as document:
        extracted = "\n".join(page.get_text() for page in document)
        assert document.page_count > 1
    assert "Example Privacy Notice" in extracted
    assert "https://example.test/privacy" in extracted
    assert "Captured: 2026-08-17" in extracted
    assert "We collect account information" in extracted


def test_persist_captured_document_keeps_official_url_and_queues_standard_upload(
    tmp_path, monkeypatch
):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    storage = LocalObjectStorage(tmp_path / "objects")
    monkeypatch.setattr("poligrapher_app.services.storage.get_storage", lambda: storage)

    class Registry:
        def __init__(self):
            self.payload = None

        def create(self, **_kwargs):
            return "task-1"

        def enqueue(self, _task_id, payload):
            self.payload = payload

        def get(self, task_id):
            return {"task_id": task_id, "status": "running", "total": 1,
                    "completed": 0, "failed": 0, "error": None, "label": None}

    registry = Registry()
    request = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(tasks=registry)))
    source = tmp_path / "captured.pdf"
    render_captured_policy_pdf(
        source,
        title="Example Privacy Notice",
        source_url="https://example.test/privacy",
        capture_date="2026-08-17",
        text=("We use account data to provide the service. " * 40),
    )

    with Session(engine) as db:
        provider = Provider(name="Example")
        db.add(provider)
        db.commit()
        _persist_uploaded_policy(
            provider=provider,
            request=request,
            db=db,
            source_path=str(source),
            filename="captured-policy-2026-08-17.pdf",
            policy_url="https://example.test/privacy",
            capture_date=date(2026, 8, 17),
            method="captured_text",
        )
        policy = db.query(Policy).one()
        assert policy.method == "captured_text"
        assert policy.url == "https://example.test/privacy"
        assert policy.source_filename == "captured-policy-2026-08-17.pdf"
        assert policy.source_blob_key and storage.exists(policy.source_blob_key)
        assert registry.payload == {"kind": "upload", "policy_id": str(policy.id)}
