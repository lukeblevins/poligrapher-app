import io

from poligrapher_app.services import acquisition, runs


class _Response:
    def __init__(self, content: bytes):
        self.content = content

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def raise_for_status(self):
        return None

    def iter_bytes(self, _size):
        yield self.content


class _Client:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def stream(self, _method, _url):
        if self.error:
            raise self.error
        return self.response


def test_remote_pdf_download_retries_transient_failure(monkeypatch):
    attempts = []

    def client(_timeout, proxy):
        attempts.append(proxy)
        if len(attempts) == 1:
            return _Client(error=TimeoutError("read timed out"))
        return _Client(response=_Response(b"%PDF-1.7\npolicy"))

    monkeypatch.setattr(acquisition, "open_client", client)
    monkeypatch.setattr(acquisition, "httpx_proxy", lambda: None)
    destination = io.BytesIO()

    runs._download_remote_pdf("https://example.com/privacy.pdf", destination)

    assert destination.getvalue() == b"%PDF-1.7\npolicy"
    assert attempts == [None, None]


def test_remote_pdf_download_rejects_non_pdf(monkeypatch):
    monkeypatch.setattr(
        acquisition,
        "open_client",
        lambda *_args: _Client(response=_Response(b"<html>blocked</html>")),
    )
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
    monkeypatch.setattr(
        acquisition,
        "open_client",
        lambda *_args: _Client(error=TimeoutError("read timed out")),
    )
    monkeypatch.setattr(acquisition, "httpx_proxy", lambda: None)

    try:
        runs._download_remote_pdf(
            "https://example.com/privacy.pdf", io.BytesIO()
        )
    except TimeoutError as exc:
        assert "Remote policy PDF download timed out" in str(exc)
    else:
        raise AssertionError("expected exhausted PDF timeouts to be classified")
