from poligrapher_app.services.acquisition import (
    is_privacy_document,
    reader_snapshot_url,
    search_result_links,
)
from poligrapher_app.services.task_execution import _is_pdf_source
from poligrapher_app.services import source_verification
from types import SimpleNamespace
import httpx


def test_search_result_links_unwraps_duckduckgo_redirects():
    html = """
      <a class="result__a"
         href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fprivacy.pdf">
        Example privacy policy
      </a>
    """

    assert search_result_links(html) == [
        ("Example privacy policy", "https://example.com/privacy.pdf")
    ]


def test_search_result_links_unwraps_yahoo_redirects():
    html = """
      <a href="https://r.search.yahoo.com/x/RU=https%3A%2F%2Fexample.com%2Fprivacy%2F/RK=2/RS=x">
        Example privacy policy
      </a>
    """

    assert search_result_links(html) == [
        ("Example privacy policy", "https://example.com/privacy/")
    ]


def test_privacy_document_accepts_official_domain_without_brand_repetition():
    text = "Privacy policy " + ("personal information and your rights " * 30)

    assert is_privacy_document(text, "Example Corporation", same_domain=True)


def test_privacy_document_requires_brand_for_cross_domain_result():
    generic = "Privacy policy " + ("personal information and your rights " * 30)

    assert not is_privacy_document(generic, "Example Corporation", same_domain=False)
    assert is_privacy_document(
        generic + " Example customers may contact us.",
        "Example Corporation",
        same_domain=False,
    )


def test_reader_snapshot_requires_privacy_document(monkeypatch):
    text = "Privacy policy " + ("personal information and your rights " * 30)
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.fetch_static",
        lambda *_args, **_kwargs: (200, text),
    )

    result = reader_snapshot_url(
        "https://example.com/legal/privacy?region=us",
        "Example Corporation",
    )

    assert result == "https://r.jina.ai/https://example.com/legal/privacy?region=us"


def test_collection_analysis_routes_only_pdf_paths_to_pdf_ingestion():
    assert _is_pdf_source("https://example.com/policies/privacy.pdf?download=1")
    assert not _is_pdf_source("https://example.com/privacy?format=pdf")
    assert not _is_pdf_source(None)


def test_verifier_retains_discovered_url_when_lightweight_probe_times_out(monkeypatch):
    candidate = SimpleNamespace(url="https://example.com/privacy")
    monkeypatch.setattr(
        source_verification.PolicySourceResolver,
        "resolve_candidate",
        lambda *_args, **_kwargs: candidate,
    )
    monkeypatch.setattr(source_verification, "wayback_snapshot_url", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(source_verification, "reader_snapshot_url", lambda *_args, **_kwargs: None)

    class Client:
        def stream(self, *_args, **_kwargs):
            raise httpx.ReadTimeout("blocked")

    provider = SimpleNamespace(
        id="provider-id",
        name="Example Corporation",
        domain="example.com",
        source_url=None,
    )

    result = source_verification._check(Client(), provider)

    assert result.status == "error"
    assert result.final_url == candidate.url


def test_verifier_marks_archive_backed_source_available(monkeypatch):
    monkeypatch.setattr(
        source_verification,
        "wayback_snapshot_url",
        lambda *_args, **_kwargs: "https://web.archive.org/web/20260101/https://example.com/privacy",
    )

    class Response:
        status_code = 403
        url = "https://example.com/privacy"

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def iter_bytes(self, *_args):
            yield b"blocked"

    class Client:
        def stream(self, *_args, **_kwargs):
            return Response()

    provider = SimpleNamespace(
        id="provider-id",
        name="Example Corporation",
        domain="example.com",
        source_url="https://example.com/privacy",
    )

    result = source_verification._check(Client(), provider)

    assert result.status == "available"
    assert result.http_status == 403
    assert result.final_url.startswith("https://web.archive.org/")
