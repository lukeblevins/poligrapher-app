from types import SimpleNamespace

from poligrapher_app.services import attempt_telemetry


class _Context:
    def __init__(self, value):
        self.value = value

    def __enter__(self):
        return self.value

    def __exit__(self, *_args):
        return False


def test_probe_collects_identity_free_response_metadata(monkeypatch):
    response = SimpleNamespace(
        headers={"content-type": "text/html; charset=utf-8", "content-length": "4096"},
        status_code=200,
        history=[object(), object()],
        url="https://privacy.example.net/policy",
    )
    client = SimpleNamespace(stream=lambda *_args: _Context(response))
    monkeypatch.setattr(
        "poligrapher_app.services.acquisition.open_client",
        lambda _timeout: _Context(client),
    )

    result = attempt_telemetry.probe_source_metadata(
        "https://www.example.com/privacy"
    )

    assert result["succeeded"] is True
    assert result["http_status"] == 200
    assert result["content_type"] == "text/html"
    assert result["content_length"] == 4096
    assert result["redirect_count"] == 2
    assert result["cross_domain_redirect"] is True
    assert "url" not in result


def test_capture_snapshot_records_pre_graph_artifact_quality(tmp_path):
    (tmp_path / "readability.json").write_text(
        '{"length": 1234, "reason": "http_fallback"}'
    )
    (tmp_path / "cleaned.html").write_bytes(b"x" * 50)
    (tmp_path / "accessibility_tree.json").write_bytes(b"x" * 25)
    telemetry = attempt_telemetry.new_attempt_telemetry(analysis_path="website")

    attempt_telemetry.record_capture_snapshot(
        telemetry,
        str(tmp_path),
        elapsed_ms=12.3456,
    )

    assert telemetry["capture"] == {
        "succeeded": True,
        "elapsed_ms": 12.346,
        "readability_text_chars": 1234,
        "cleaned_html_bytes": 50,
        "accessibility_tree_bytes": 25,
        "rendered_pdf_bytes": None,
        "fallback_kind": "http_fallback",
    }


def test_enriched_features_omit_failure_outcomes_and_source_identity():
    telemetry = attempt_telemetry.new_attempt_telemetry(
        analysis_path="website",
        probe={
            "succeeded": True,
            "http_status": 403,
            "content_type": "text/html",
            "challenge_detected": True,
        },
    )
    telemetry["failure"] = {
        "stage": "Building standard graph",
        "error_type": "RuntimeError",
    }

    features = attempt_telemetry.enriched_ml_features(telemetry)

    assert features["probe_http_status"] == "403"
    assert features["probe_challenge_detected"] is True
    assert not any("failure" in name or "url" in name for name in features)
