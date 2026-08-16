from types import SimpleNamespace

from poligrapher_app.services import persistence, pipeline, runs


class FakeSession:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_comparison_source_retries_live_url_after_browser_challenge():
    provider = SimpleNamespace(
        source_url="https://example.test/privacy",
        source_final_url=(
            "https://web.archive.org/web/20260701/https://example.test/privacy"
        ),
        source_status="available",
        source_http_status=403,
    )

    assert runs._comparison_source_url(provider) == provider.source_url

    provider.source_http_status = 200
    assert runs._comparison_source_url(provider) == provider.source_final_url

    provider.source_http_status = 403
    provider.source_final_url = "https://r.jina.ai/https://example.test/privacy"
    assert runs._comparison_source_url(provider) == provider.source_final_url


def test_comparison_method_failure_preserves_sibling_result(tmp_path, monkeypatch):
    website = SimpleNamespace(
        method="website",
        graph_data=None,
        pipeline_status="pending",
        pipeline_errors=[],
        content_hash=None,
    )
    pdf = SimpleNamespace(
        method="pdf_from_page",
        graph_data=None,
        pipeline_status="pending",
        pipeline_errors=[],
        content_hash=None,
    )
    website_doc = object()
    pdf_doc = object()
    db = FakeSession()

    monkeypatch.setattr(runs, "_score", lambda *_args: None)
    monkeypatch.setattr(runs, "_website_text_hash", lambda *_args: "website-hash")

    def persist(policy, doc, _archive):
        if doc is website_doc:
            raise RuntimeError("Pipeline produced no canonical graph elements")
        policy.graph_data = {"elements": [{"data": {"id": "pdf-result"}}]}
        policy.pipeline_status = "complete"

    monkeypatch.setattr(persistence, "persist_workspace", persist)

    website_error = runs._persist_generated_method(
        website,
        website_doc,
        tmp_path / "website.zip",
        db,
        record_content_hash=True,
    )
    pdf_error = runs._persist_generated_method(
        pdf,
        pdf_doc,
        tmp_path / "pdf.zip",
        db,
    )

    assert str(website_error) == "Pipeline produced no canonical graph elements"
    assert website.pipeline_status == "failed"
    assert website.pipeline_errors == [
        "website failed: Pipeline produced no canonical graph elements"
    ]
    assert website.content_hash is None
    assert pdf_error is None
    assert pdf.pipeline_status == "complete"
    assert pdf.graph_data["elements"]
    assert db.rollbacks == 1
    assert db.commits == 2


def test_pdf_generation_failure_preserves_generated_website(tmp_path, monkeypatch):
    calls = []

    def generate(path, output_dir, capture_pdf, **kwargs):
        calls.append((path, output_dir, capture_pdf, kwargs.get("emit_pdf")))
        if capture_pdf:
            raise RuntimeError("Content language UNKNOWN isn't English")
        website = tmp_path / "website"
        website.mkdir()
        (website / "output.pdf").write_bytes(b"%PDF-1.7")

    monkeypatch.setattr(pipeline, "generate_graph_from_html", generate)

    error = pipeline.generate_comparison(
        "https://example.com/privacy",
        str(tmp_path / "website"),
        str(tmp_path / "pdf"),
    )

    assert str(error) == "Content language UNKNOWN isn't English"
    assert calls[0][2:] == (False, True)
    assert calls[1][0] == str(tmp_path / "website" / "output.pdf")
    assert calls[1][2] is True
