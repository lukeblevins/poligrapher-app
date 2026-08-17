from poligrapher_app.services.acquisition import (
    PolicySourceResolver,
    discover_links,
    fetch_validated_policy_html,
    is_privacy_document,
    narrow_policy_reason,
    privacy_document_text,
    reader_snapshot_url,
    search_result_links,
    validate_policy_html,
    validate_policy_source_url,
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


def test_pdf_policy_text_uses_pymupdf(monkeypatch):
    class Page:
        @staticmethod
        def get_text():
            return "Privacy notice personal information and consumer rights"

    class Document:
        def __getitem__(self, _slice):
            return [Page()]

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr("fitz.open", lambda **_kwargs: Document())

    assert privacy_document_text(
        b"%PDF test",
        "application/pdf",
        "https://example.com/privacy.pdf",
    ) == "Privacy notice personal information and consumer rights"


def test_fetch_validated_policy_html_matches_pipeline_contract(monkeypatch):
    html = """
    <html><body>
      <header>Navigation</header>
      <main aria-hidden="true">
        <h1>Privacy Policy</h1>
        <p>This privacy policy explains how we collect, use, disclose, and
        protect personal information when customers use our products and
        services. We retain information only as long as needed and provide
        choices about data processing and marketing communications.</p>
      </main>
      <script>tracking()</script>
    </body></html>
    """
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.fetch_static",
        lambda *_args, **_kwargs: (200, html),
    )

    validated = fetch_validated_policy_html("https://example.com/privacy")

    assert "Privacy Policy" in validated
    assert 'aria-hidden="false"' in validated
    assert "Navigation" not in validated
    assert "tracking()" not in validated

    assert validate_policy_html(html) == validated


def test_fetch_validated_policy_html_rejects_non_english_policy(monkeypatch):
    html = """
    <html><body><main><h1>Política de privacidad</h1>
    <p>Esta política explica cómo recopilamos, utilizamos, compartimos y
    protegemos los datos personales de nuestros clientes cuando utilizan
    nuestros productos y servicios. También describe sus derechos y opciones
    con respecto al tratamiento de información personal.</p></main></body></html>
    """
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.fetch_static",
        lambda *_args, **_kwargs: (200, html),
    )

    assert fetch_validated_policy_html("https://example.com/privacy") == ""


def test_validate_policy_source_url_accepts_pdf(monkeypatch):
    text = "Privacy notice " + ("personal information and your rights " * 30)
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.privacy_document_text",
        lambda *_args: text,
    )

    class Response:
        status_code = 200
        headers = {"content-type": "application/pdf"}
        url = "https://example.com/privacy-notice.pdf"
        encoding = "utf-8"

        @staticmethod
        def iter_bytes(_size):
            yield b"%PDF" + b"x" * 600

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    class Client:
        @staticmethod
        def stream(*_args, **_kwargs):
            return Response()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.open_client",
        lambda *_args, **_kwargs: Client(),
    )

    assert validate_policy_source_url(
        "https://example.com/privacy-notice.pdf",
        "Example Corporation",
        "example.com",
    ) == "https://example.com/privacy-notice.pdf"


def test_resolver_prefers_validated_policy_link_from_current_hub(monkeypatch):
    resolver = PolicySourceResolver(allow_headless=False)
    html = """
      <a href="https://vendor.test/privacy-policy">Privacy policy</a>
      <a href="/careers/applicant-privacy">Applicant privacy notice</a>
      <a href="/files/privacy-notice.pdf">Company privacy notice</a>
    """
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.fetch_static",
        lambda *_args, **_kwargs: (200, html),
    )
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.validate_policy_source_url",
        lambda url, *_args, **_kwargs: url,
    )

    result = resolver.resolve_linked_candidate(
        "Example Corporation",
        "example.com",
        "https://www.example.com/privacy-center",
    )

    assert result is not None
    assert result.url == "https://www.example.com/files/privacy-notice.pdf"
    assert result.strategy == "linked"
    assert result.confidence == 0.86
    assert result.validated is True


def test_resolver_keeps_weak_linked_policy_section_below_auto_threshold(monkeypatch):
    resolver = PolicySourceResolver(allow_headless=False)
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.fetch_static",
        lambda *_args, **_kwargs: (
            200,
            '<a href="/privacy-statement/retention/">Retention details</a>',
        ),
    )
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.validate_policy_source_url",
        lambda url, *_args, **_kwargs: url,
    )

    result = resolver.resolve_linked_candidate(
        "Example Corporation",
        "example.com",
        "https://www.example.com/privacy-statement/",
    )

    assert result is not None
    assert result.confidence == 0.7
    assert result.confidence < 0.75


def test_resolver_excludes_current_url_from_site_discovery(monkeypatch):
    resolver = PolicySourceResolver(allow_headless=False)
    monkeypatch.setattr(resolver, "_search_candidate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(resolver, "_sitemap_candidate", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.fetch_html",
        lambda *_args, **_kwargs: '<a href="/privacy/">Privacy policy</a>',
    )

    result = resolver.resolve_candidate(
        "Example",
        "example.com",
        exclude_urls={"https://www.example.com/privacy"},
    )

    assert result is None


def test_site_discovery_rejects_audience_specific_privacy_pages():
    html = """
      <a href="/privacy-policy">Privacy policy</a>
      <a href="/investors/privacy-policy">Investor privacy policy</a>
      <a href="/careers/applicant-privacy">Applicant privacy notice</a>
      <a href="/human-resources-hr-information-system-privacy-notices">HR privacy notices</a>
      <a href="/newsletter-subscription-privacy-notice">Newsletter privacy notice</a>
      <a href="https://ir.example.com/privacy-policy">IR privacy policy</a>
    """

    assert discover_links(html, "https://example.com", "example.com") == [
        (9, "https://example.com/privacy-policy")
    ]


def test_narrow_policy_rejections_have_stable_reason_codes():
    assert narrow_policy_reason("/careers/applicant-privacy") == "audience.workforce"
    assert narrow_policy_reason("/investors/privacy-policy") == "audience.investor"
    assert narrow_policy_reason("/2025-annual-report-privacy") == "document.report"
    assert narrow_policy_reason("/newsletter-subscription-privacy") == "document.subscription"
    assert narrow_policy_reason("/privacy-notice-faq.pdf") == "document.support"
    assert narrow_policy_reason("/vulnerability-disclosure-policy.pdf") == "document.security"
    assert narrow_policy_reason("/privacy-policy") is None


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
