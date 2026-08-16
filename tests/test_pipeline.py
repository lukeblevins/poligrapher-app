import json
import time

from poligrapher.scripts import build_graph, html_crawler, init_document, run_annotators

from poligrapher_app.services import pipeline


def test_url_probe_attempt_has_hard_wall_clock_deadline(monkeypatch):
    def hang(*_args):
        time.sleep(5)
        return 200

    monkeypatch.setattr(pipeline, "_url_probe_attempt", hang)

    started = time.monotonic()
    status, error = pipeline._run_url_probe_attempt(
        "https://example.test/privacy",
        1.0,
        None,
        max_attempt_seconds=0.05,
    )

    assert time.monotonic() - started < 1.0
    assert status is None
    assert error == "reachability probe exceeded 0.05 seconds"


def test_browser_challenge_status_skips_slow_proxy_fallback(monkeypatch):
    attempts = []

    def probe(_url, _timeout, proxy):
        attempts.append(proxy)
        return 403, None

    monkeypatch.setattr(pipeline, "_run_url_probe_attempt", probe)
    monkeypatch.setattr(pipeline, "httpx_proxy", lambda: "http://proxy.test")
    monkeypatch.setattr(pipeline, "crawl_proxy_mode", lambda: "fallback")

    assert pipeline.test_document_url(
        "https://example.test/privacy",
        allow_browser_challenge=True,
    )
    assert attempts == [None]


def test_document_probe_keeps_browser_challenge_status_strict(monkeypatch):
    monkeypatch.setattr(
        pipeline,
        "_run_url_probe_attempt",
        lambda *_args: (403, None),
    )
    monkeypatch.setattr(pipeline, "httpx_proxy", lambda: None)

    assert not pipeline.test_document_url("https://example.test/privacy.pdf")


def _stub_remaining_stages(monkeypatch):
    monkeypatch.setattr(init_document, "main", lambda **_kwargs: None)
    monkeypatch.setattr(run_annotators, "main", lambda: None)
    monkeypatch.setattr(build_graph, "main", lambda: None)


def test_fallback_proxy_mode_prefers_direct_browser_render(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setenv("CRAWL_PROXY", "http://proxy.test")
    monkeypatch.setenv("CRAWL_PROXY_USERNAME", "user")
    monkeypatch.setattr(pipeline, "httpx_proxy", lambda: "http://user@proxy.test")
    monkeypatch.setattr(pipeline, "crawl_proxy_mode", lambda: "fallback")

    def crawl(_path, output, pdf_output=None):
        calls.append(("CRAWL_PROXY" in pipeline.os.environ, pdf_output))
        pipeline.os.makedirs(output, exist_ok=True)
        with open(pipeline.os.path.join(output, "readability.json"), "w") as stream:
            json.dump({"applied": True}, stream)

    crawler = type("Crawler", (), {"main": staticmethod(crawl)})
    pipeline._crawl_html(
        crawler,
        "https://example.test/privacy",
        str(tmp_path / "out"),
    )

    assert calls == [(False, None)]
    assert pipeline.os.environ["CRAWL_PROXY"] == "http://proxy.test"
    assert pipeline.os.environ["CRAWL_PROXY_USERNAME"] == "user"


def test_fallback_proxy_replaces_static_shell_with_rendered_capture(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("CRAWL_PROXY", "http://proxy.test")
    monkeypatch.setattr(pipeline, "httpx_proxy", lambda: "http://proxy.test")
    monkeypatch.setattr(pipeline, "crawl_proxy_mode", lambda: "fallback")
    calls = []

    def crawl(_path, output, pdf_output=None):
        proxied = "CRAWL_PROXY" in pipeline.os.environ
        calls.append(proxied)
        pipeline.os.makedirs(output, exist_ok=True)
        reason = "rendered" if proxied else "http_fallback"
        with open(pipeline.os.path.join(output, "readability.json"), "w") as stream:
            json.dump({"reason": reason}, stream)
        with open(pipeline.os.path.join(output, "cleaned.html"), "w") as stream:
            stream.write(reason)
        if pdf_output:
            with open(pdf_output, "wb") as stream:
                stream.write(reason.encode())

    crawler = type("Crawler", (), {"main": staticmethod(crawl)})
    output = tmp_path / "out"
    pipeline._crawl_html(
        crawler,
        "https://example.test/privacy",
        str(output),
        pdf_output=str(output / "output.pdf"),
    )

    assert calls == [False, True]
    assert (output / "cleaned.html").read_text() == "rendered"
    assert (output / "output.pdf").read_bytes() == b"rendered"


def test_live_navigation_dead_end_retries_once_from_wayback(monkeypatch, tmp_path):
    live_url = "https://example.com/privacy"
    archive_url = "https://web.archive.org/web/20260701/https://example.com/privacy"
    crawled = []

    probes = []

    def probe(url, **_kwargs):
        probes.append(url)
        return url == live_url

    monkeypatch.setattr(pipeline, "test_document_url", probe)
    monkeypatch.setattr(pipeline, "fetch_validated_policy_html", lambda _url: "")
    monkeypatch.setattr(
        pipeline,
        "wayback_snapshot_url",
        lambda url, raw: archive_url if url == live_url and raw is False else None,
    )
    monkeypatch.setattr(pipeline, "fetch_wayback", lambda _url: "")

    def crawl(path, _staging, pdf_output=None):
        crawled.append((path, pdf_output is not None))
        if path == live_url:
            raise RuntimeError(
                "html_crawler failure: Chromium navigation failed and the HTTP source "
                "fallback was unavailable"
            )

    monkeypatch.setattr(html_crawler, "main", crawl)
    _stub_remaining_stages(monkeypatch)

    output = tmp_path / "output"
    pipeline.generate_graph_from_html(
        live_url, str(output), capture_pdf=False, emit_pdf=True
    )

    assert crawled == [(live_url, True), (archive_url, True)]
    assert probes == [live_url]
    assert output.is_dir()
    assert not list(tmp_path.glob("output.staging-*"))


def test_validation_failure_does_not_try_archive(monkeypatch, tmp_path):
    archive_lookups = []
    monkeypatch.setattr(pipeline, "test_document_url", lambda url, **_kwargs: True)
    monkeypatch.setattr(pipeline, "fetch_validated_policy_html", lambda _url: "")
    monkeypatch.setattr(
        pipeline,
        "wayback_snapshot_url",
        lambda *args, **kwargs: archive_lookups.append((args, kwargs)),
    )
    monkeypatch.setattr(pipeline, "fetch_wayback", lambda _url: "")
    monkeypatch.setattr(
        html_crawler,
        "main",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError("The webpage is not like a privacy policy")
        ),
    )
    _stub_remaining_stages(monkeypatch)

    try:
        pipeline.generate_graph_from_html(
            "https://example.com/about", str(tmp_path / "output"), capture_pdf=False
        )
    except RuntimeError as exc:
        assert "not like a privacy policy" in str(exc)
    else:
        raise AssertionError("expected the validation failure to propagate")

    assert archive_lookups == []


def test_archive_navigation_dead_end_is_not_retried(monkeypatch, tmp_path):
    archive_url = "https://web.archive.org/web/20260701/https://example.com/privacy"
    archive_lookups = []
    monkeypatch.setattr(pipeline, "test_document_url", lambda url, **_kwargs: True)
    monkeypatch.setattr(pipeline, "fetch_validated_policy_html", lambda _url: "")
    monkeypatch.setattr(
        pipeline,
        "wayback_snapshot_url",
        lambda *args, **kwargs: archive_lookups.append((args, kwargs)),
    )
    monkeypatch.setattr(pipeline, "fetch_wayback", lambda _url: "")
    monkeypatch.setattr(
        html_crawler,
        "main",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            RuntimeError(
                "html_crawler failure: Chromium navigation failed and the HTTP source "
                "fallback was unavailable"
            )
        ),
    )
    _stub_remaining_stages(monkeypatch)

    try:
        pipeline.generate_graph_from_html(
            archive_url, str(tmp_path / "output"), capture_pdf=False
        )
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected the archive crawl failure to propagate")

    assert archive_lookups == []


def test_live_navigation_dead_end_prefers_materialized_wayback_html(monkeypatch, tmp_path):
    live_url = "https://example.com/privacy"
    archived_html = "<html><body>Example privacy policy</body></html>"
    crawled = []
    snapshot_lookups = []

    monkeypatch.setattr(pipeline, "test_document_url", lambda _url, **_kwargs: True)
    monkeypatch.setattr(pipeline, "fetch_validated_policy_html", lambda _url: "")
    monkeypatch.setattr(pipeline, "fetch_wayback", lambda url: archived_html if url == live_url else "")
    monkeypatch.setattr(
        pipeline,
        "wayback_snapshot_url",
        lambda *args, **kwargs: snapshot_lookups.append((args, kwargs)),
    )

    def crawl(path, _staging, pdf_output=None):
        if path == live_url:
            raise RuntimeError(
                "html_crawler failure: Chromium navigation failed and the HTTP source "
                "fallback was unavailable"
            )
        with open(path, encoding="utf-8") as archived_file:
            assert archived_file.read() == archived_html
        crawled.append((path, pdf_output is not None))

    monkeypatch.setattr(html_crawler, "main", crawl)
    _stub_remaining_stages(monkeypatch)

    output = tmp_path / "output"
    pipeline.generate_graph_from_html(
        live_url, str(output), capture_pdf=False, emit_pdf=True
    )

    assert len(crawled) == 1
    assert crawled[0][1] is True
    assert not (tmp_path / crawled[0][0]).exists()
    assert not list(tmp_path.glob("poligrapher-wayback-*.html"))
    assert snapshot_lookups == []


def test_live_navigation_dead_end_prefers_validated_direct_html(monkeypatch, tmp_path):
    live_url = "https://example.com/privacy"
    direct_html = "<html><body>Example privacy policy</body></html>"
    crawled = []

    monkeypatch.setattr(pipeline, "test_document_url", lambda _url, **_kwargs: True)
    monkeypatch.setattr(
        pipeline,
        "fetch_validated_policy_html",
        lambda url: direct_html if url == live_url else "",
    )
    monkeypatch.setattr(
        pipeline,
        "fetch_wayback",
        lambda _url: (_ for _ in ()).throw(
            AssertionError("validated direct HTML must precede archive fallback")
        ),
    )

    def crawl(path, _staging, pdf_output=None):
        if path == live_url:
            raise RuntimeError(
                "html_crawler failure: Chromium navigation failed and the HTTP source "
                "fallback was unavailable"
            )
        with open(path, encoding="utf-8") as direct_file:
            assert direct_file.read() == direct_html
        crawled.append((path, pdf_output is not None))

    monkeypatch.setattr(html_crawler, "main", crawl)
    _stub_remaining_stages(monkeypatch)

    output = tmp_path / "output"
    pipeline.generate_graph_from_html(
        live_url, str(output), capture_pdf=False, emit_pdf=True
    )

    assert len(crawled) == 1
    assert crawled[0][1] is True
    assert not list(tmp_path.glob("poligrapher-direct-*.html"))
