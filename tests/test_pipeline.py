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


def _stub_remaining_stages(monkeypatch):
    monkeypatch.setattr(init_document, "main", lambda **_kwargs: None)
    monkeypatch.setattr(run_annotators, "main", lambda: None)
    monkeypatch.setattr(build_graph, "main", lambda: None)


def test_live_navigation_dead_end_retries_once_from_wayback(monkeypatch, tmp_path):
    live_url = "https://example.com/privacy"
    archive_url = "https://web.archive.org/web/20260701/https://example.com/privacy"
    crawled = []

    probes = []

    def probe(url):
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
    monkeypatch.setattr(pipeline, "test_document_url", lambda url: True)
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
    monkeypatch.setattr(pipeline, "test_document_url", lambda url: True)
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

    monkeypatch.setattr(pipeline, "test_document_url", lambda _url: True)
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

    monkeypatch.setattr(pipeline, "test_document_url", lambda _url: True)
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
