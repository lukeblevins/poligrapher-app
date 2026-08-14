import io
import tempfile
import time
from pathlib import Path

from poligrapher_app.services import acquisition, runs


def test_remote_pdf_download_retries_transient_failure(monkeypatch):
    attempts = []

    def attempt(_url, path, _max_bytes, proxy, _max_attempt_seconds):
        attempts.append(proxy)
        if len(attempts) == 1:
            raise TimeoutError("read timed out")
        Path(path).write_bytes(b"%PDF-1.7\npolicy")

    monkeypatch.setattr(runs, "_run_pdf_download_attempt", attempt)
    monkeypatch.setattr(acquisition, "httpx_proxy", lambda: None)
    destination = io.BytesIO()

    runs._download_remote_pdf("https://example.com/privacy.pdf", destination)

    assert destination.getvalue() == b"%PDF-1.7\npolicy"
    assert attempts == [None, None]


def test_remote_pdf_download_rejects_non_pdf(monkeypatch):
    def attempt(*_args):
        raise ValueError("Remote policy source did not return a PDF")

    monkeypatch.setattr(runs, "_run_pdf_download_attempt", attempt)
    monkeypatch.setattr(acquisition, "httpx_proxy", lambda: None)

    try:
        runs._download_remote_pdf(
            "https://example.com/privacy.pdf", io.BytesIO()
        )
    except ValueError as exc:
        assert "did not return a PDF" in str(exc)
    else:
        raise AssertionError("expected a non-PDF response to be rejected")


def test_remote_pdf_download_reports_exhausted_timeouts(monkeypatch):
    def attempt(*_args):
        raise TimeoutError("read timed out")

    monkeypatch.setattr(runs, "_run_pdf_download_attempt", attempt)
    monkeypatch.setattr(acquisition, "httpx_proxy", lambda: None)

    try:
        runs._download_remote_pdf(
            "https://example.com/privacy.pdf", io.BytesIO()
        )
    except TimeoutError as exc:
        assert "Remote policy PDF download timed out" in str(exc)
    else:
        raise AssertionError("expected exhausted PDF timeouts to be classified")


def test_remote_pdf_download_stops_before_response_headers(monkeypatch):
    def blocked_attempt(*_args):
        time.sleep(1)

    monkeypatch.setattr(runs, "_download_pdf_attempt", blocked_attempt)

    started = time.monotonic()
    with tempfile.TemporaryDirectory() as directory:
        try:
            runs._run_pdf_download_attempt(
                "https://example.com/privacy.pdf",
                str(Path(directory) / "policy.pdf"),
                1024,
                None,
                0.02,
            )
        except TimeoutError as exc:
            assert "Remote policy PDF download timed out" in str(exc)
        else:
            raise AssertionError("expected a pre-response stall to hit the deadline")
    assert time.monotonic() - started < 0.5


def test_remote_pdf_download_stops_a_trickling_stream(monkeypatch):
    def blocked_attempt(*_args):
        while True:
            time.sleep(0.01)

    monkeypatch.setattr(runs, "_download_pdf_attempt", blocked_attempt)
    with tempfile.TemporaryDirectory() as directory:
        try:
            runs._run_pdf_download_attempt(
                "https://example.com/privacy.pdf",
                str(Path(directory) / "policy.pdf"),
                1024,
                None,
                0.02,
            )
        except TimeoutError as exc:
            assert "Remote policy PDF download timed out" in str(exc)
        else:
            raise AssertionError("expected a trickling stream to hit the deadline")
