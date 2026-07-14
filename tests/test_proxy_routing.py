from types import SimpleNamespace

from poligrapher_app.services import acquisition


class _Client:
    def __init__(self, response):
        self.response = response

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def get(self, _url):
        return self.response


def test_proxy_credentials_are_kept_separate_and_encoded(monkeypatch):
    monkeypatch.setenv("CRAWL_PROXY", "http://gate.decodo.com:7000")
    monkeypatch.setenv("CRAWL_PROXY_USERNAME", "user name")
    monkeypatch.setenv("CRAWL_PROXY_PASSWORD", "p@ss")

    assert acquisition.httpx_proxy() == (
        "http://user%20name:p%40ss@gate.decodo.com:7000"
    )
    assert acquisition.playwright_proxy() == {
        "server": "http://gate.decodo.com:7000",
        "username": "user name",
        "password": "p@ss",
    }


def test_fallback_mode_spends_proxy_bandwidth_only_when_forced(monkeypatch):
    monkeypatch.setenv("CRAWL_PROXY", "http://gate.decodo.com:7000")
    monkeypatch.setenv("CRAWL_PROXY_MODE", "fallback")
    routes = []

    def fake_client(_timeout, proxy):
        routes.append(proxy)
        return _Client(SimpleNamespace(status_code=200, text="policy"))

    monkeypatch.setattr(acquisition, "open_client", fake_client)
    acquisition.fetch_static("https://example.com/privacy", attempts=1)
    acquisition.fetch_static("https://example.com/privacy", attempts=1, force_proxy=True)

    assert routes == [None, "http://gate.decodo.com:7000"]


def test_invalid_proxy_mode_defaults_to_fallback(monkeypatch):
    monkeypatch.setenv("CRAWL_PROXY_MODE", "surprise")
    assert acquisition.crawl_proxy_mode() == "fallback"
